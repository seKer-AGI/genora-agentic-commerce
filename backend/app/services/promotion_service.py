"""Offers, coupons and bundles (seller/admin management + public discovery)."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationFailed
from app.core.principal import Principal
from app.core.rbac import P
from app.core.security import utcnow
from app.models.catalog import Category, Product
from app.models.enums import DiscountType, ProductStatus
from app.models.identity import SellerProfile
from app.models.promotions import Bundle, BundleItem, Coupon, Offer
from app.schemas.promotions import (
    BundleIn,
    BundleOut,
    BundleUpdate,
    CouponIn,
    CouponOut,
    OfferIn,
    OfferOut,
    OfferUpdate,
    ProductOfferOut,
)
from app.services.audit import audit
from app.services.pricing import PricingEngine, q


def _live(is_active: bool, starts_at: datetime | None, ends_at: datetime | None, now: datetime | None = None) -> str:
    now = now or utcnow()
    if not is_active:
        return "disabled"
    if starts_at and starts_at > now:
        return "scheduled"
    if ends_at and ends_at <= now:
        return "expired"
    return "active"


def is_bundle_live(b: Bundle) -> bool:
    return b.deleted_at is None and _live(b.is_active, b.starts_at, b.ends_at) == "active"


def _describe_value(discount_type: DiscountType, value: Decimal) -> str:
    return f"{value.normalize():f}% off" if discount_type == DiscountType.PERCENTAGE else f"${q(value)} off"


class PromotionService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ============================================================ offers
    def offer_out(self, o: Offer) -> OfferOut:
        scope = "product" if o.product_id else "category" if o.category_id else "seller" if o.seller_id else "marketplace"
        seller = self.db.get(SellerProfile, o.seller_id) if o.seller_id else None
        product = self.db.get(Product, o.product_id) if o.product_id else None
        category = self.db.get(Category, o.category_id) if o.category_id else None
        conditions = [_describe_value(o.discount_type, o.value) + " per unit"]
        if o.min_quantity > 1:
            conditions.append(f"Minimum quantity: {o.min_quantity}")
        if scope == "category" and category:
            conditions.append(f"Applies to products in {category.name}")
        if scope == "seller" and seller:
            conditions.append(f"Applies to all products from {seller.store_name}")
        if scope == "marketplace":
            conditions.append("Applies marketplace-wide")
        if o.ends_at:
            conditions.append(f"Ends {o.ends_at:%Y-%m-%d %H:%M} UTC")
        conditions.append("Does not stack with bundle or negotiated prices; the best single offer is applied")
        return OfferOut(
            id=o.id, name=o.name, description=o.description, discount_type=o.discount_type.value, value=o.value,
            scope=scope, seller_id=o.seller_id, seller_name=seller.store_name if seller else None,
            product_id=o.product_id, product_name=product.name if product else None, category_id=o.category_id,
            min_quantity=o.min_quantity, starts_at=o.starts_at, ends_at=o.ends_at, is_active=o.is_active,
            status=_live(o.is_active, o.starts_at, o.ends_at), conditions=conditions,
        )

    def list_offers(self, *, seller_id: uuid.UUID | None = None, active_only: bool = True,
                    product_id: uuid.UUID | None = None) -> list[OfferOut]:
        stmt = select(Offer).where(Offer.deleted_at.is_(None)).order_by(Offer.created_at.desc())
        if seller_id:
            stmt = stmt.where(Offer.seller_id == seller_id)
        if product_id:
            stmt = stmt.where(Offer.product_id == product_id)
        offers = [self.offer_out(o) for o in self.db.scalars(stmt)]
        return [o for o in offers if o.status == "active"] if active_only else offers

    def offers_for_product(self, product: Product) -> list[ProductOfferOut]:
        """Every active offer relevant to a product, with eligibility for a single unit."""
        engine = PricingEngine(self.db)
        base = engine.base_price(product)
        out = []
        for o in engine.applicable_offers(product):
            per_unit = engine.unit_discount(o.discount_type, o.value, base)
            out.append(ProductOfferOut(
                **self.offer_out(o).model_dump(), eligible=o.min_quantity <= 1, discount_per_unit=per_unit,
                price_after_offer=q(base - per_unit),
            ))
        out.sort(key=lambda x: x.discount_per_unit, reverse=True)
        return out

    def _authorize_scope(self, principal: Principal, product_id: uuid.UUID | None,
                         category_id: uuid.UUID | None) -> uuid.UUID | None:
        """Returns the seller_id the offer is bound to (None for marketplace-wide admin offers)."""
        if principal.has(P.OFFERS_MANAGE_ALL) and principal.seller_id is None:
            seller_id = None
        else:
            principal.require(P.OFFERS_MANAGE_OWN)
            seller_id = principal.require_seller()
        if product_id:
            p = self.db.get(Product, product_id)
            if p is None or p.deleted_at is not None or (seller_id and p.seller_id != seller_id):
                raise NotFoundError("Product was not found", code="PRODUCT_NOT_FOUND")
            if seller_id is None:
                seller_id = p.seller_id
        if category_id and self.db.get(Category, category_id) is None:
            raise ValidationFailed("Unknown category", code="CATEGORY_NOT_FOUND")
        return seller_id

    def _get_offer(self, offer_id: uuid.UUID, principal: Principal) -> Offer:
        o = self.db.get(Offer, offer_id)
        if o is None or o.deleted_at is not None:
            raise NotFoundError("Offer was not found", code="OFFER_NOT_FOUND")
        if not principal.has(P.OFFERS_MANAGE_ALL) and o.seller_id != principal.seller_id:
            raise NotFoundError("Offer was not found", code="OFFER_NOT_FOUND")
        return o

    def create_offer(self, data: OfferIn, principal: Principal) -> OfferOut:
        seller_id = self._authorize_scope(principal, data.product_id, data.category_id)
        o = Offer(**{**data.model_dump(), "discount_type": DiscountType(data.discount_type)}, seller_id=seller_id,
                  created_by=principal.user_id)
        self.db.add(o)
        self.db.flush()
        audit(self.db, principal.user_id, "offer.create", "offer", o.id, data.model_dump(mode="json"))
        self.db.commit()
        return self.offer_out(o)

    def update_offer(self, offer_id: uuid.UUID, data: OfferUpdate, principal: Principal) -> OfferOut:
        o = self._get_offer(offer_id, principal)
        changes = data.model_dump(exclude_unset=True)
        for k, v in changes.items():
            setattr(o, k, v)
        if o.discount_type == DiscountType.PERCENTAGE and o.value > 90:
            raise ValidationFailed("percentage discounts cannot exceed 90%", code="INVALID_DISCOUNT")
        audit(self.db, principal.user_id, "offer.update", "offer", o.id, changes)
        self.db.commit()
        return self.offer_out(o)

    def delete_offer(self, offer_id: uuid.UUID, principal: Principal) -> None:
        o = self._get_offer(offer_id, principal)
        o.deleted_at, o.is_active = utcnow(), False
        audit(self.db, principal.user_id, "offer.delete", "offer", o.id)
        self.db.commit()

    # ============================================================ coupons
    @staticmethod
    def coupon_out(c: Coupon) -> CouponOut:
        return CouponOut(
            id=c.id, code=c.code, description=c.description, discount_type=c.discount_type.value, value=c.value,
            min_subtotal=c.min_subtotal, seller_id=c.seller_id, starts_at=c.starts_at, ends_at=c.ends_at,
            usage_limit=c.usage_limit, per_user_limit=c.per_user_limit, used_count=c.used_count, is_active=c.is_active,
        )

    def list_coupons(self, seller_id: uuid.UUID | None) -> list[CouponOut]:
        stmt = select(Coupon).where(Coupon.deleted_at.is_(None)).order_by(Coupon.created_at.desc())
        if seller_id:
            stmt = stmt.where(Coupon.seller_id == seller_id)
        return [self.coupon_out(c) for c in self.db.scalars(stmt)]

    def create_coupon(self, data: CouponIn, principal: Principal) -> CouponOut:
        seller_id = self._authorize_scope(principal, None, None)
        if self.db.scalar(select(Coupon.id).where(Coupon.code == data.code)):
            raise ConflictError("Coupon code already exists", code="COUPON_CODE_TAKEN")
        c = Coupon(**{**data.model_dump(), "discount_type": DiscountType(data.discount_type)}, seller_id=seller_id)
        self.db.add(c)
        self.db.flush()
        audit(self.db, principal.user_id, "coupon.create", "coupon", c.id, {"code": c.code})
        self.db.commit()
        return self.coupon_out(c)

    def delete_coupon(self, coupon_id: uuid.UUID, principal: Principal) -> None:
        c = self.db.get(Coupon, coupon_id)
        if c is None or c.deleted_at or (not principal.has(P.OFFERS_MANAGE_ALL) and c.seller_id != principal.seller_id):
            raise NotFoundError("Coupon was not found", code="COUPON_NOT_FOUND")
        c.deleted_at, c.is_active = utcnow(), False
        audit(self.db, principal.user_id, "coupon.delete", "coupon", c.id)
        self.db.commit()

    # ============================================================ bundles
    def bundle_out(self, b: Bundle, engine: PricingEngine | None = None) -> BundleOut:
        from app.services.catalog_service import product_card

        engine = engine or PricingEngine(self.db)
        products = [bi.product for bi in b.items]
        items_total = q(sum((engine.base_price(p) * bi.quantity for p, bi in zip(products, b.items, strict=True)),
                            Decimal(0)))
        savings = (
            q(items_total * b.value / 100) if b.discount_type == DiscountType.PERCENTAGE
            else q(min(b.value, items_total))
        )
        available = is_bundle_live(b) and all(
            p.status == ProductStatus.ACTIVE and p.deleted_at is None and p.stock >= bi.quantity
            for p, bi in zip(products, b.items, strict=True)
        )
        seller = self.db.get(SellerProfile, b.seller_id) if b.seller_id else None
        return BundleOut(
            id=b.id, name=b.name, slug=b.slug, description=b.description, seller_id=b.seller_id,
            seller_name=seller.store_name if seller else None, discount_type=b.discount_type.value, value=b.value,
            products=[product_card(p, engine) for p in products], items_total=items_total,
            bundle_price=q(items_total - savings), savings=savings, is_active=b.is_active, available=available,
            starts_at=b.starts_at, ends_at=b.ends_at,
        )

    def list_bundles(self, *, seller_id: uuid.UUID | None = None, product_id: uuid.UUID | None = None,
                     active_only: bool = True) -> list[BundleOut]:
        stmt = select(Bundle).where(Bundle.deleted_at.is_(None)).order_by(Bundle.created_at.desc())
        if seller_id:
            stmt = stmt.where(Bundle.seller_id == seller_id)
        if product_id:
            stmt = stmt.where(Bundle.id.in_(select(BundleItem.bundle_id).where(BundleItem.product_id == product_id)))
        bundles = list(self.db.scalars(stmt))
        if active_only:
            bundles = [b for b in bundles if is_bundle_live(b)]
        engine = PricingEngine(self.db)
        return [self.bundle_out(b, engine) for b in bundles]

    def get_bundle(self, id_or_slug: str) -> BundleOut:
        stmt = select(Bundle).where(Bundle.deleted_at.is_(None))
        try:
            stmt = stmt.where(Bundle.id == uuid.UUID(id_or_slug))
        except ValueError:
            stmt = stmt.where(Bundle.slug == id_or_slug)
        b = self.db.scalar(stmt)
        if b is None:
            raise NotFoundError("Bundle was not found", code="BUNDLE_NOT_FOUND")
        return self.bundle_out(b)

    def create_bundle(self, data: BundleIn, principal: Principal) -> BundleOut:
        seller_id = self._authorize_scope(principal, None, None)
        if len(set(data.product_ids)) != len(data.product_ids):
            raise ValidationFailed("Bundle products must be unique", code="DUPLICATE_PRODUCTS")
        products = self.db.scalars(select(Product).where(Product.id.in_(data.product_ids), Product.deleted_at.is_(None))).all()
        if len(products) != len(data.product_ids):
            raise ValidationFailed("One or more products were not found", code="PRODUCT_NOT_FOUND")
        if seller_id and any(p.seller_id != seller_id for p in products):
            raise ValidationFailed("Sellers can only bundle their own products", code="FOREIGN_PRODUCT")
        slug = re.sub(r"[^a-z0-9]+", "-", data.name.lower()).strip("-")
        if self.db.scalar(select(Bundle.id).where(Bundle.slug == slug)):
            slug = f"{slug}-{uuid.uuid4().hex[:6]}"
        b = Bundle(**{**data.model_dump(exclude={"product_ids"}), "discount_type": DiscountType(data.discount_type)},
                   slug=slug, seller_id=seller_id,
                   created_by=principal.user_id)
        b.items = [BundleItem(product_id=pid, quantity=1) for pid in data.product_ids]
        self.db.add(b)
        self.db.flush()
        audit(self.db, principal.user_id, "bundle.create", "bundle", b.id, {"name": b.name})
        self.db.commit()
        self.db.refresh(b)
        return self.bundle_out(b)

    def _get_bundle_owned(self, bundle_id: uuid.UUID, principal: Principal) -> Bundle:
        b = self.db.get(Bundle, bundle_id)
        if b is None or b.deleted_at or (not principal.has(P.OFFERS_MANAGE_ALL) and b.seller_id != principal.seller_id):
            raise NotFoundError("Bundle was not found", code="BUNDLE_NOT_FOUND")
        return b

    def update_bundle(self, bundle_id: uuid.UUID, data: BundleUpdate, principal: Principal) -> BundleOut:
        b = self._get_bundle_owned(bundle_id, principal)
        for k, v in data.model_dump(exclude_unset=True).items():
            setattr(b, k, v)
        audit(self.db, principal.user_id, "bundle.update", "bundle", b.id, data.model_dump(mode="json", exclude_unset=True))
        self.db.commit()
        return self.bundle_out(b)

    def delete_bundle(self, bundle_id: uuid.UUID, principal: Principal) -> None:
        b = self._get_bundle_owned(bundle_id, principal)
        b.deleted_at, b.is_active = utcnow(), False
        audit(self.db, principal.user_id, "bundle.delete", "bundle", b.id)
        self.db.commit()


def active_offer_filter(now: datetime):  # type: ignore[no-untyped-def]
    return (
        Offer.is_active.is_(True),
        Offer.deleted_at.is_(None),
        or_(Offer.starts_at.is_(None), Offer.starts_at <= now),
        or_(Offer.ends_at.is_(None), Offer.ends_at > now),
    )
