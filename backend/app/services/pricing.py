"""Server-side pricing engine. The ONLY place where prices, discounts, tax and totals are computed.

Precedence per line (no stacking between these):
  negotiated price (1 unit, buyer-specific)  >  bundle discount  >  best automatic offer
Then a coupon applies to the eligible discounted subtotal, then shipping and tax per seller.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import utcnow
from app.models.catalog import Category, Negotiation, Product, ProductVariant
from app.models.enums import DiscountType, NegotiationStatus, ProductStatus, SellerStatus
from app.models.promotions import Bundle, Coupon, Offer

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def q(v: Decimal) -> Decimal:
    return v.quantize(CENT, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------- tax/shipping
class TaxCalculator(ABC):
    @abstractmethod
    def tax(self, taxable_amount: Decimal, shipping_address: dict | None) -> Decimal: ...


class FlatRateTaxCalculator(TaxCalculator):
    """Single configurable rate. Replace with a jurisdiction-aware provider (e.g. Stripe Tax, Avalara)."""

    def __init__(self, rate: Decimal) -> None:
        self.rate = rate

    def tax(self, taxable_amount: Decimal, shipping_address: dict | None) -> Decimal:
        return q(max(taxable_amount, ZERO) * self.rate)


class ShippingCalculator(ABC):
    @abstractmethod
    def shipping(self, seller_id: uuid.UUID, merchandise_total: Decimal, units: int) -> Decimal: ...


class FlatRateShippingCalculator(ShippingCalculator):
    def __init__(self, flat: Decimal, free_threshold: Decimal) -> None:
        self.flat, self.free_threshold = flat, free_threshold

    def shipping(self, seller_id: uuid.UUID, merchandise_total: Decimal, units: int) -> Decimal:
        if units == 0 or merchandise_total >= self.free_threshold:
            return ZERO
        return self.flat


# ---------------------------------------------------------------- data classes
@dataclass
class LineInput:
    product: Product
    quantity: int
    variant: ProductVariant | None = None
    bundle_id: uuid.UUID | None = None
    line_id: uuid.UUID | None = None


@dataclass
class AppliedDiscount:
    source: str  # offer | bundle | negotiation | coupon
    source_id: uuid.UUID | None
    description: str
    amount: Decimal


@dataclass
class PricedLine:
    input: LineInput
    unit_price: Decimal  # base unit price (sale price if set) before discounts
    list_price: Decimal  # original list price (for display)
    quantity: int
    subtotal: Decimal
    discounts: list[AppliedDiscount] = field(default_factory=list)
    available: int = 0
    issues: list[str] = field(default_factory=list)

    @property
    def discount_total(self) -> Decimal:
        return q(sum((d.amount for d in self.discounts), ZERO))

    @property
    def total(self) -> Decimal:
        return q(self.subtotal - self.discount_total)

    @property
    def seller_id(self) -> uuid.UUID:
        return self.input.product.seller_id


@dataclass
class SellerTotals:
    seller_id: uuid.UUID
    store_name: str
    subtotal: Decimal = ZERO
    line_discounts: Decimal = ZERO
    coupon_discount: Decimal = ZERO
    shipping: Decimal = ZERO
    tax: Decimal = ZERO

    @property
    def discount_total(self) -> Decimal:
        return q(self.line_discounts + self.coupon_discount)

    @property
    def total(self) -> Decimal:
        return q(self.subtotal - self.discount_total + self.shipping + self.tax)


@dataclass
class PricedCart:
    lines: list[PricedLine]
    sellers: dict[uuid.UUID, SellerTotals]
    coupon: Coupon | None
    coupon_discount: Decimal
    coupon_message: str | None
    currency: str = "USD"

    @property
    def subtotal(self) -> Decimal:
        return q(sum((s.subtotal for s in self.sellers.values()), ZERO))

    @property
    def discount_total(self) -> Decimal:
        return q(sum((s.discount_total for s in self.sellers.values()), ZERO))

    @property
    def shipping_total(self) -> Decimal:
        return q(sum((s.shipping for s in self.sellers.values()), ZERO))

    @property
    def tax_total(self) -> Decimal:
        return q(sum((s.tax for s in self.sellers.values()), ZERO))

    @property
    def total(self) -> Decimal:
        return q(sum((s.total for s in self.sellers.values()), ZERO))

    @property
    def issues(self) -> list[str]:
        return [i for line in self.lines for i in line.issues]


@dataclass
class ProductQuote:
    list_price: Decimal
    base_price: Decimal
    final_price: Decimal
    offer: Offer | None


# ---------------------------------------------------------------- engine
class PricingEngine:
    def __init__(
        self,
        db: Session,
        tax: TaxCalculator | None = None,
        shipping: ShippingCalculator | None = None,
        now: datetime | None = None,
    ) -> None:
        s = get_settings()
        self.db = db
        self.tax_calc = tax or FlatRateTaxCalculator(s.tax_rate)
        self.ship_calc = shipping or FlatRateShippingCalculator(s.shipping_flat_rate, s.free_shipping_threshold)
        self.now = now or utcnow()
        self._offers: list[Offer] | None = None
        self._ancestors: dict[uuid.UUID, list[uuid.UUID]] | None = None

    # --- lookups ---------------------------------------------------------
    def active_offers(self) -> list[Offer]:
        if self._offers is None:
            self._offers = list(
                self.db.scalars(
                    select(Offer).where(
                        Offer.is_active.is_(True),
                        Offer.deleted_at.is_(None),
                        or_(Offer.starts_at.is_(None), Offer.starts_at <= self.now),
                        or_(Offer.ends_at.is_(None), Offer.ends_at > self.now),
                    )
                )
            )
        return self._offers

    def category_ancestors(self, category_id: uuid.UUID | None) -> list[uuid.UUID]:
        if category_id is None:
            return []
        if self._ancestors is None:
            parents = dict(self.db.execute(select(Category.id, Category.parent_id)).tuples().all())
            self._ancestors = {}
            for cid in parents:
                chain, cur = [], cid
                while cur is not None and cur not in chain:
                    chain.append(cur)
                    cur = parents.get(cur)
                self._ancestors[cid] = chain
        return self._ancestors.get(category_id, [category_id])

    def offer_applies(self, offer: Offer, product: Product, quantity: int = 1) -> bool:
        if quantity < offer.min_quantity:
            return False
        if offer.seller_id is not None and offer.seller_id != product.seller_id:
            return False
        if offer.product_id is not None:
            return offer.product_id == product.id
        if offer.category_id is not None:
            return offer.category_id in self.category_ancestors(product.category_id)
        return True  # seller-wide (seller_id set) or marketplace-wide (seller_id NULL)

    @staticmethod
    def unit_discount(discount_type: DiscountType, value: Decimal, base: Decimal) -> Decimal:
        if discount_type == DiscountType.PERCENTAGE:
            return q(base * Decimal(value) / 100)
        return q(min(Decimal(value), base))

    def best_offer(self, product: Product, base: Decimal, quantity: int = 1) -> tuple[Offer | None, Decimal]:
        best, best_amt = None, ZERO
        for o in self.active_offers():
            if self.offer_applies(o, product, quantity):
                amt = self.unit_discount(o.discount_type, o.value, base)
                if amt > best_amt:
                    best, best_amt = o, amt
        return best, best_amt

    def applicable_offers(self, product: Product, quantity: int | None = None) -> list[Offer]:
        """All active offers relevant to the product (min-quantity ignored when quantity is None)."""
        return [o for o in self.active_offers() if self.offer_applies(o, product, quantity or o.min_quantity)]

    @staticmethod
    def base_price(product: Product, variant: ProductVariant | None = None) -> Decimal:
        if variant is not None and variant.price_override is not None:
            return q(variant.price_override)
        return q(product.effective_list_price)

    def quote(self, product: Product, quantity: int = 1) -> ProductQuote:
        base = self.base_price(product)
        offer, amt = self.best_offer(product, base, quantity)
        return ProductQuote(list_price=q(product.price), base_price=base, final_price=q(base - amt), offer=offer)

    def negotiated_prices(self, buyer_id: uuid.UUID, product_ids: list[uuid.UUID]) -> dict[uuid.UUID, Negotiation]:
        if not product_ids:
            return {}
        rows = self.db.scalars(
            select(Negotiation)
            .where(
                Negotiation.buyer_id == buyer_id,
                Negotiation.product_id.in_(product_ids),
                Negotiation.status == NegotiationStatus.ACCEPTED,
                Negotiation.expires_at > self.now,
            )
            .order_by(Negotiation.agreed_price.asc())
        )
        out: dict[uuid.UUID, Negotiation] = {}
        for n in rows:
            out.setdefault(n.product_id, n)
        return out

    def _bundle_map(self, ids: set[uuid.UUID]) -> dict[uuid.UUID, Bundle]:
        if not ids:
            return {}
        bundles = self.db.scalars(
            select(Bundle).where(
                Bundle.id.in_(ids), Bundle.is_active.is_(True), Bundle.deleted_at.is_(None),
                or_(Bundle.starts_at.is_(None), Bundle.starts_at <= self.now),
                or_(Bundle.ends_at.is_(None), Bundle.ends_at > self.now),
            )
        )
        return {b.id: b for b in bundles}

    # --- cart pricing ---------------------------------------------------
    def price_lines(
        self,
        lines: list[LineInput],
        *,
        buyer_id: uuid.UUID | None = None,
        coupon: Coupon | None = None,
        coupon_uses_by_buyer: int = 0,
        shipping_address: dict | None = None,
    ) -> PricedCart:
        negotiated = self.negotiated_prices(buyer_id, [li.product.id for li in lines]) if buyer_id else {}
        bundles = self._bundle_map({li.bundle_id for li in lines if li.bundle_id})
        priced: list[PricedLine] = []

        for li in lines:
            p = li.product
            base = self.base_price(p, li.variant)
            available = self._available(p, li.variant)
            pl = PricedLine(li, base, q(p.price), li.quantity, q(base * li.quantity), available=available)
            if p.status != ProductStatus.ACTIVE or p.deleted_at is not None or p.seller.status != SellerStatus.ACTIVE:
                pl.issues.append(f"'{p.name}' is no longer available")
            elif li.quantity > available:
                pl.issues.append(f"Only {available} unit(s) of '{p.name}' are in stock")
            priced.append(pl)

        # bundle discounts: only when every bundle product is present with this bundle id
        by_bundle: dict[uuid.UUID, list[PricedLine]] = defaultdict(list)
        for pl in priced:
            if pl.input.bundle_id in bundles:
                by_bundle[pl.input.bundle_id].append(pl)
        bundled: set[int] = set()
        for bid, bl in by_bundle.items():
            bundle = bundles[bid]
            needed = {bi.product_id: bi.quantity for bi in bundle.items}
            present = {pl.input.product.id: pl for pl in bl}
            if set(needed) - set(present):
                continue
            sets = min(present[pid].quantity // qty for pid, qty in needed.items())
            if sets < 1:
                continue
            set_value = sum((present[pid].unit_price * qty for pid, qty in needed.items()), ZERO)
            total_disc = (
                q(set_value * Decimal(bundle.value) / 100) if bundle.discount_type == DiscountType.PERCENTAGE
                else q(min(Decimal(bundle.value), set_value))
            ) * sets
            allocated = ZERO
            items = list(needed.items())
            for idx, (pid, qty) in enumerate(items):
                pl = present[pid]
                share = (
                    total_disc - allocated if idx == len(items) - 1
                    else q(total_disc * (pl.unit_price * qty) / set_value)
                )
                allocated += share
                pl.discounts.append(AppliedDiscount("bundle", bundle.id, f"Bundle: {bundle.name}", share))
                bundled.add(id(pl))

        for pl in priced:
            if id(pl) in bundled:
                continue
            p = pl.input.product
            neg = negotiated.get(p.id)
            if neg is not None and neg.agreed_price is not None and neg.agreed_price < pl.unit_price:
                pl.discounts.append(AppliedDiscount(
                    "negotiation", neg.id, "Negotiated price (1 unit)", q(pl.unit_price - neg.agreed_price)
                ))
                continue
            offer, amt = self.best_offer(p, pl.unit_price, pl.quantity)
            if offer is not None and amt > 0:
                pl.discounts.append(AppliedDiscount("offer", offer.id, f"Offer: {offer.name}", q(amt * pl.quantity)))

        # per-seller totals
        sellers: dict[uuid.UUID, SellerTotals] = {}
        for pl in priced:
            st = sellers.setdefault(pl.seller_id, SellerTotals(pl.seller_id, pl.input.product.seller.store_name))
            st.subtotal = q(st.subtotal + pl.subtotal)
            st.line_discounts = q(st.line_discounts + pl.discount_total)

        coupon_discount, coupon_msg = ZERO, None
        if coupon is not None:
            ok, coupon_msg = self.coupon_eligibility(coupon, sellers, coupon_uses_by_buyer)
            if ok:
                eligible = {sid: st for sid, st in sellers.items() if coupon.seller_id in (None, sid)}
                base_total = sum((st.subtotal - st.line_discounts for st in eligible.values()), ZERO)
                if base_total > 0:
                    coupon_discount = (
                        q(base_total * Decimal(coupon.value) / 100)
                        if coupon.discount_type == DiscountType.PERCENTAGE
                        else q(min(Decimal(coupon.value), base_total))
                    )
                    allocated = ZERO
                    items = list(eligible.values())
                    for idx, st in enumerate(items):
                        share = (
                            coupon_discount - allocated if idx == len(items) - 1
                            else q(coupon_discount * (st.subtotal - st.line_discounts) / base_total)
                        )
                        st.coupon_discount = share
                        allocated += share
                    coupon_msg = f"Coupon {coupon.code} applied"

        for st in sellers.values():
            units = sum(pl.quantity for pl in priced if pl.seller_id == st.seller_id)
            merchandise = q(st.subtotal - st.discount_total)
            st.shipping = self.ship_calc.shipping(st.seller_id, merchandise, units)
            st.tax = self.tax_calc.tax(merchandise, shipping_address)

        return PricedCart(priced, sellers, coupon if coupon_discount > 0 else None, coupon_discount, coupon_msg)

    def coupon_eligibility(
        self, coupon: Coupon, sellers: dict[uuid.UUID, SellerTotals], uses_by_buyer: int
    ) -> tuple[bool, str]:
        if not coupon.is_active or coupon.deleted_at is not None:
            return False, "This coupon is not active"
        if coupon.starts_at and coupon.starts_at > self.now:
            return False, "This coupon is not valid yet"
        if coupon.ends_at and coupon.ends_at <= self.now:
            return False, "This coupon has expired"
        if coupon.usage_limit is not None and coupon.used_count >= coupon.usage_limit:
            return False, "This coupon has reached its usage limit"
        if uses_by_buyer >= coupon.per_user_limit:
            return False, "You have already used this coupon"
        eligible = [st for sid, st in sellers.items() if coupon.seller_id in (None, sid)]
        if not eligible:
            return False, "This coupon does not apply to the items in your cart"
        subtotal = sum((st.subtotal - st.line_discounts for st in eligible), ZERO)
        if subtotal < coupon.min_subtotal:
            return False, f"Spend at least ${coupon.min_subtotal} on eligible items to use this coupon"
        return True, "Coupon is valid"

    @staticmethod
    def _available(product: Product, variant: ProductVariant | None) -> int:
        vid = variant.id if variant else None
        rows = [i for i in product.inventory if i.variant_id == vid] or (product.inventory if vid is None else [])
        return sum(i.available for i in rows)
