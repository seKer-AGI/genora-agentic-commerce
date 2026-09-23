"""Controlled price negotiation evaluated strictly against seller-defined rules.

Outcome policy (the seller's floor price is never revealed):
* offer >= auto-accept price           → ACCEPTED at the offered price
* floor <= offer < auto-accept price   → COUNTERED at the midpoint of (offer, auto-accept price)
* offer < floor                         → REJECTED, with a counter at the auto-accept price
An accepted price is reserved for the buyer for one unit and expires after NEGOTIATED_PRICE_TTL_HOURS.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError, PermissionDenied, RateLimited, ValidationFailed
from app.core.principal import Principal
from app.core.rbac import P
from app.core.security import utcnow
from app.models.catalog import Negotiation, NegotiationRule, Product
from app.models.enums import NegotiationStatus, ProductStatus
from app.models.identity import Notification, SellerProfile, SystemSetting
from app.schemas.promotions import NegotiationOut, NegotiationRuleIn, NegotiationRuleOut
from app.services.audit import audit
from app.services.catalog_service import negotiation_rule_for
from app.services.pricing import PricingEngine, q

MAX_ATTEMPTS_PER_DAY = 3


class NegotiationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    def to_out(self, n: Negotiation) -> NegotiationOut:
        p = self.db.get(Product, n.product_id)
        return NegotiationOut(
            id=n.id, product_id=n.product_id, product_name=p.name if p else "", product_slug=p.slug if p else "",
            status=n.status.value, list_price=n.list_price, offered_price=n.offered_price, counter_price=n.counter_price,
            agreed_price=n.agreed_price, reason=n.reason, expires_at=n.expires_at, created_at=n.created_at,
        )

    def policy(self, product: Product) -> tuple[bool, str | None]:
        enabled = self.db.get(SystemSetting, "agents.negotiation.enabled")
        if enabled is not None and not enabled.value:
            return False, "Negotiation is currently disabled on the marketplace"
        rule = negotiation_rule_for(self.db, product)
        if rule is None or not rule.is_enabled or rule.max_discount_percent <= 0:
            return False, "The seller does not accept price offers for this product"
        return True, None

    def propose(self, product_id: uuid.UUID, offered: Decimal, principal: Principal, message: str | None = None
                ) -> NegotiationOut:
        principal.require(P.NEGOTIATE)
        product = self.db.scalar(select(Product).where(Product.id == product_id, Product.deleted_at.is_(None)))
        if product is None or product.status != ProductStatus.ACTIVE:
            raise NotFoundError("Product was not found", code="PRODUCT_NOT_FOUND")
        if principal.seller_id == product.seller_id:
            raise PermissionDenied("You cannot negotiate on your own product", code="OWN_PRODUCT")
        allowed, reason = self.policy(product)
        if not allowed:
            raise ConflictError(reason or "Not negotiable", code="NOT_NEGOTIABLE")
        since = utcnow() - timedelta(hours=24)
        attempts = self.db.scalar(
            select(func.count()).select_from(Negotiation).where(
                Negotiation.buyer_id == principal.user_id, Negotiation.product_id == product.id,
                Negotiation.created_at >= since)
        ) or 0
        if attempts >= MAX_ATTEMPTS_PER_DAY:
            raise RateLimited("You have reached the daily limit of price offers for this product",
                              code="NEGOTIATION_LIMIT")

        rule = negotiation_rule_for(self.db, product)
        assert rule is not None
        engine = PricingEngine(self.db)
        list_price = engine.quote(product).final_price  # current best public price
        offered = q(offered)
        if offered >= list_price:
            raise ValidationFailed("Your offer is at or above the current price — just add it to your cart",
                                   code="OFFER_NOT_BELOW_PRICE")
        floor = q(list_price * (1 - rule.max_discount_percent / 100))
        auto = q(list_price * (1 - rule.auto_accept_percent / 100))
        expires = utcnow() + timedelta(hours=self.settings.negotiated_price_ttl_hours)
        n = Negotiation(product_id=product.id, buyer_id=principal.user_id, seller_id=product.seller_id,
                        list_price=list_price, offered_price=offered, expires_at=expires)
        if offered >= auto:
            n.status, n.agreed_price, n.reason = NegotiationStatus.ACCEPTED, offered, "Offer accepted by the seller's pricing rules"
        elif offered >= floor:
            n.status, n.counter_price = NegotiationStatus.COUNTERED, q((offered + auto) / 2)
            n.reason = "The seller proposes a counter-offer"
        else:
            n.status, n.counter_price = NegotiationStatus.REJECTED, auto
            n.reason = "Offer is below what the seller can accept; the best available counter-offer is shown"
        self.db.add(n)
        self.db.flush()
        seller = self.db.get(SellerProfile, product.seller_id)
        if seller:
            self.db.add(Notification(user_id=seller.user_id, type="negotiation", title=f"Price offer on {product.name}",
                                     body=f"Offer ${offered} → {n.status.value}", data={"negotiation_id": str(n.id)}))
        audit(self.db, principal.user_id, "negotiation.propose", "negotiation", n.id,
              {"product_id": str(product.id), "offered": str(offered), "status": n.status.value, "message": message})
        self.db.commit()
        return self.to_out(n)

    def accept_counter(self, negotiation_id: uuid.UUID, principal: Principal) -> NegotiationOut:
        n = self.db.scalar(select(Negotiation).where(Negotiation.id == negotiation_id).with_for_update())
        if n is None or n.buyer_id != principal.user_id:
            raise NotFoundError("Negotiation was not found", code="NEGOTIATION_NOT_FOUND")
        if n.status not in (NegotiationStatus.COUNTERED, NegotiationStatus.REJECTED) or n.counter_price is None:
            raise ConflictError("There is no counter-offer to accept", code="NO_COUNTER_OFFER")
        if n.expires_at and n.expires_at <= utcnow():
            n.status = NegotiationStatus.EXPIRED
            self.db.commit()
            raise ConflictError("This counter-offer has expired", code="NEGOTIATION_EXPIRED")
        n.status, n.agreed_price = NegotiationStatus.ACCEPTED, n.counter_price
        n.reason = "Counter-offer accepted by buyer"
        audit(self.db, principal.user_id, "negotiation.accept_counter", "negotiation", n.id, {"price": str(n.agreed_price)})
        self.db.commit()
        return self.to_out(n)

    def list_for_buyer(self, user_id: uuid.UUID) -> list[NegotiationOut]:
        rows = self.db.scalars(select(Negotiation).where(Negotiation.buyer_id == user_id)
                               .order_by(Negotiation.created_at.desc()).limit(50))
        return [self.to_out(n) for n in rows]

    def list_for_seller(self, seller_id: uuid.UUID) -> list[NegotiationOut]:
        rows = self.db.scalars(select(Negotiation).where(Negotiation.seller_id == seller_id)
                               .order_by(Negotiation.created_at.desc()).limit(100))
        return [self.to_out(n) for n in rows]

    # ------------------------------------------------------------ seller rules
    def rules(self, seller_id: uuid.UUID) -> list[NegotiationRuleOut]:
        out = []
        for r in self.db.scalars(select(NegotiationRule).where(NegotiationRule.seller_id == seller_id)):
            name = self.db.scalar(select(Product.name).where(Product.id == r.product_id)) if r.product_id else None
            out.append(NegotiationRuleOut(id=r.id, product_id=r.product_id, is_enabled=r.is_enabled,
                                          max_discount_percent=r.max_discount_percent,
                                          auto_accept_percent=r.auto_accept_percent, product_name=name))
        return out

    def upsert_rule(self, data: NegotiationRuleIn, principal: Principal) -> NegotiationRuleOut:
        principal.require(P.OFFERS_MANAGE_OWN)
        seller_id = principal.require_seller()
        if data.product_id:
            p = self.db.get(Product, data.product_id)
            if p is None or p.seller_id != seller_id:
                raise NotFoundError("Product was not found", code="PRODUCT_NOT_FOUND")
        rule = self.db.scalar(select(NegotiationRule).where(
            NegotiationRule.seller_id == seller_id,
            NegotiationRule.product_id == data.product_id if data.product_id else NegotiationRule.product_id.is_(None)))
        if rule is None:
            rule = NegotiationRule(seller_id=seller_id, product_id=data.product_id)
            self.db.add(rule)
        rule.is_enabled = data.is_enabled
        rule.max_discount_percent = data.max_discount_percent
        rule.auto_accept_percent = data.auto_accept_percent
        if data.product_id is None:
            seller = self.db.get(SellerProfile, seller_id)
            if seller:
                seller.negotiation_enabled = data.is_enabled
        audit(self.db, principal.user_id, "negotiation_rule.upsert", "negotiation_rule", data.product_id,
              data.model_dump(mode="json"))
        self.db.commit()
        return next(r for r in self.rules(seller_id) if r.id == rule.id)
