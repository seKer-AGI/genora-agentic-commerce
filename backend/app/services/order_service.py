"""Checkout, order lifecycle (state machine) and order queries."""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, PermissionDenied, ValidationFailed
from app.core.logging import log_event
from app.core.principal import Principal
from app.core.rbac import P
from app.core.security import utcnow
from app.integrations.payments import PaymentProvider, get_payment_provider
from app.models.analytics import AnalyticsEvent
from app.models.catalog import Inventory, Negotiation
from app.models.commerce import Discount, Order, OrderItem, OrderStatusEvent, Payment
from app.models.enums import DiscountSource, NegotiationStatus, OrderStatus, PaymentStatus
from app.models.identity import Address, Notification, SellerProfile, User
from app.models.promotions import Coupon
from app.schemas.commerce import (
    AddressIn,
    CheckoutRequest,
    CheckoutResponse,
    OrderDiscountOut,
    OrderItemOut,
    OrderOut,
    PaymentOut,
    StatusEventOut,
)
from app.services.audit import audit
from app.services.cart_service import CartService

logger = logging.getLogger("app.orders")

# Allowed transitions and who may perform them.
TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.PENDING: {OrderStatus.CONFIRMED, OrderStatus.CANCELLED},
    OrderStatus.CONFIRMED: {OrderStatus.PROCESSING, OrderStatus.CANCELLED},
    OrderStatus.PROCESSING: {OrderStatus.SHIPPED, OrderStatus.CANCELLED},
    OrderStatus.SHIPPED: {OrderStatus.DELIVERED},
    OrderStatus.DELIVERED: {OrderStatus.REFUNDED},
    OrderStatus.CANCELLED: set(),
    OrderStatus.REFUNDED: set(),
}
BUYER_ALLOWED = {OrderStatus.CANCELLED}
BUYER_CANCELLABLE_FROM = {OrderStatus.PENDING, OrderStatus.CONFIRMED}
SELLER_ALLOWED = {OrderStatus.CONFIRMED, OrderStatus.PROCESSING, OrderStatus.SHIPPED, OrderStatus.DELIVERED,
                  OrderStatus.CANCELLED}


def _address_snapshot(a: Address | AddressIn) -> dict[str, str | None]:
    return {k: getattr(a, k) for k in ("recipient_name", "line1", "line2", "city", "state", "postal_code", "country", "phone")}


class OrderService:
    def __init__(self, db: Session, payments: PaymentProvider | None = None) -> None:
        self.db = db
        self.payments = payments or get_payment_provider()

    # ============================================================ checkout
    def checkout(self, principal: Principal, req: CheckoutRequest, idempotency_key: str | None = None
                 ) -> CheckoutResponse:
        principal.require(P.ORDERS_PLACE)
        group_id = (
            uuid.uuid5(uuid.NAMESPACE_OID, f"{principal.user_id}:{idempotency_key}") if idempotency_key else uuid.uuid4()
        )
        existing = list(self.db.scalars(select(Order).where(Order.checkout_group_id == group_id)))
        if existing:  # idempotent replay
            return self._checkout_response(group_id, existing)

        if req.address_id:
            addr = self.db.scalar(select(Address).where(Address.id == req.address_id, Address.user_id == principal.user_id,
                                                        Address.deleted_at.is_(None)))
            if addr is None:
                raise NotFoundError("Address was not found", code="ADDRESS_NOT_FOUND")
            shipping_address = _address_snapshot(addr)
        else:
            assert req.address is not None
            shipping_address = _address_snapshot(req.address)

        carts = CartService(self.db, principal.user_id)
        cart = carts.cart(lock=True)
        if not cart.items:
            raise ValidationFailed("Your cart is empty", code="CART_EMPTY")

        # Lock inventory rows in a stable order to avoid deadlocks, then re-price with fresh stock.
        product_ids = sorted({i.product_id for i in cart.items})
        inventory = list(self.db.scalars(
            select(Inventory).where(Inventory.product_id.in_(product_ids)).order_by(Inventory.id).with_for_update()
        ))
        self.db.expire_all()
        cart = carts.cart(lock=True)
        cart, priced = carts.price(cart, shipping_address)
        if priced.issues:
            raise ConflictError("Some items in your cart need attention", code="CART_INVALID",
                                details={"issues": priced.issues})

        orders: list[Order] = []
        seq_base = self.db.scalar(select(func.count()).select_from(Order)) or 0
        for n, (seller_id, totals) in enumerate(priced.sellers.items(), start=1):
            order = Order(
                order_number=f"GO-{utcnow():%y%m%d}-{seq_base + n:05d}-{uuid.uuid4().hex[:4].upper()}",
                checkout_group_id=group_id, buyer_id=principal.user_id, seller_id=seller_id,
                status=OrderStatus.PENDING, currency=priced.currency, subtotal=totals.subtotal,
                discount_total=totals.discount_total, tax_total=totals.tax, shipping_total=totals.shipping,
                total=totals.total, shipping_address=shipping_address, notes=req.notes,
            )
            order.status_events.append(OrderStatusEvent(to_status=OrderStatus.PENDING.value, actor_user_id=principal.user_id,
                                                        note="Order placed"))
            for pl in (x for x in priced.lines if x.seller_id == seller_id):
                p = pl.input.product
                item = OrderItem(product_id=p.id, variant_id=pl.input.variant.id if pl.input.variant else None,
                                 bundle_id=pl.input.bundle_id, product_name=p.name, sku=p.sku, unit_price=pl.unit_price,
                                 quantity=pl.quantity, discount_amount=pl.discount_total, line_total=pl.total)
                order.items.append(item)
                for d in pl.discounts:
                    order.discounts.append(Discount(source=DiscountSource(d.source), source_id=d.source_id,
                                                    description=d.description, amount=d.amount))
                    if d.source == "negotiation" and d.source_id:
                        neg = self.db.get(Negotiation, d.source_id)
                        if neg:
                            neg.status = NegotiationStatus.USED
                self._decrement_stock(inventory, p.id, pl.input.variant.id if pl.input.variant else None, pl.quantity)
                p.sold_count += pl.quantity
            if totals.coupon_discount > 0 and priced.coupon is not None:
                order.discounts.append(Discount(source=DiscountSource.COUPON, source_id=priced.coupon.id,
                                                description=f"Coupon {priced.coupon.code}", amount=totals.coupon_discount))
            self.db.add(order)
            orders.append(order)
        if priced.coupon is not None:
            coupon = self.db.scalar(select(Coupon).where(Coupon.id == priced.coupon.id).with_for_update())
            if coupon:
                coupon.used_count += 1
        self.db.flush()

        # Payment — one charge per seller order so refunds map cleanly to orders.
        payment_status = PaymentStatus.CAPTURED
        charged: list[tuple[str, Decimal, uuid.UUID]] = []
        for order in orders:
            result = self.payments.charge(
                amount=order.total, currency=order.currency, payment_method=req.payment_method,
                idempotency_key=f"{group_id}:{order.id}", description=f"GenOra order {order.order_number}",
                metadata={"order_id": str(order.id), "checkout_group_id": str(group_id)},
            )
            if not result.succeeded and result.status != PaymentStatus.PENDING:
                # Compensate: refund charges already taken for earlier seller orders in this checkout.
                for ref, amount, oid in charged:
                    self.payments.refund(provider_reference=ref, amount=amount, idempotency_key=f"rollback:{oid}")
                self.db.rollback()
                log_event(logger, "payment_failed", logging.WARNING, provider=self.payments.name,
                          reason=result.failure_reason)
                raise ValidationFailed(result.failure_reason or "Payment failed", code="PAYMENT_FAILED")
            order.payments.append(Payment(provider=self.payments.name, provider_reference=result.provider_reference,
                                          amount=order.total, currency=order.currency, status=result.status,
                                          provider_metadata=result.metadata))
            if result.succeeded and result.provider_reference:
                charged.append((result.provider_reference, order.total, order.id))
            if result.succeeded:
                self._transition(order, OrderStatus.CONFIRMED, principal.user_id, "Payment received")
            else:
                payment_status = PaymentStatus.PENDING

        cart.items.clear()
        cart.coupon_code = None
        buyer = self.db.get(User, principal.user_id)
        for order in orders:
            for item in order.items:
                self.db.add(AnalyticsEvent(event_type="purchase", user_id=principal.user_id, product_id=item.product_id,
                                           seller_id=order.seller_id, order_id=order.id, value=item.line_total,
                                           properties={"quantity": item.quantity}))
            seller = self.db.get(SellerProfile, order.seller_id)
            if seller:
                self.db.add(Notification(user_id=seller.user_id, type="order.new", title=f"New order {order.order_number}",
                                         body=f"{len(order.items)} item(s), total ${order.total}",
                                         data={"order_id": str(order.id)}))
        self.db.add(Notification(user_id=principal.user_id, type="order.placed", title="Order placed",
                                 body=f"Thanks {buyer.full_name if buyer else ''}! {len(orders)} order(s) placed.",
                                 data={"checkout_group_id": str(group_id)}))
        audit(self.db, principal.user_id, "order.checkout", "checkout", group_id,
              {"orders": [o.order_number for o in orders], "total": str(sum(o.total for o in orders))})
        self.db.commit()
        log_event(logger, "checkout_completed", orders=len(orders), group=str(group_id))
        return self._checkout_response(group_id, orders, payment_status)

    @staticmethod
    def _decrement_stock(inventory: list[Inventory], product_id: uuid.UUID, variant_id: uuid.UUID | None, qty: int) -> None:
        rows = [i for i in inventory if i.product_id == product_id and i.variant_id == variant_id] or \
               [i for i in inventory if i.product_id == product_id and i.variant_id is None]
        remaining = qty
        for inv in rows:
            take = min(inv.quantity_on_hand - inv.quantity_reserved, remaining)
            if take > 0:
                inv.quantity_on_hand -= take
                remaining -= take
        if remaining > 0:
            raise ConflictError("An item sold out while you were checking out", code="INSUFFICIENT_STOCK")

    def _checkout_response(self, group_id: uuid.UUID, orders: list[Order],
                           payment_status: PaymentStatus | None = None) -> CheckoutResponse:
        if payment_status is None:
            statuses = {p.status for o in orders for p in o.payments}
            payment_status = PaymentStatus.PENDING if PaymentStatus.PENDING in statuses else PaymentStatus.CAPTURED
        return CheckoutResponse(
            checkout_group_id=group_id, orders=[self.to_out(o, detail=True) for o in orders],
            total_charged=sum((o.total for o in orders), Decimal(0)), payment_status=payment_status.value,
        )

    # ============================================================ lifecycle
    def _transition(self, order: Order, to: OrderStatus, actor: uuid.UUID | None, note: str | None = None) -> None:
        if to not in TRANSITIONS[order.status]:
            raise ConflictError(f"Cannot change order from {order.status.value} to {to.value}",
                                code="INVALID_STATUS_TRANSITION")
        now = utcnow()
        order.status_events.append(OrderStatusEvent(from_status=order.status.value, to_status=to.value,
                                                    actor_user_id=actor, note=note))
        order.status = to
        if to == OrderStatus.CONFIRMED:
            order.confirmed_at = now
        elif to == OrderStatus.SHIPPED:
            order.shipped_at = now
        elif to == OrderStatus.DELIVERED:
            order.delivered_at = now
        elif to == OrderStatus.CANCELLED:
            order.cancelled_at = now

    def allowed_transitions(self, order: Order, principal: Principal) -> list[str]:
        nxt = TRANSITIONS[order.status]
        if principal.has(P.ORDERS_MANAGE_ALL):
            return sorted(s.value for s in nxt)
        if principal.seller_id == order.seller_id:
            return sorted(s.value for s in nxt & SELLER_ALLOWED)
        if order.buyer_id == principal.user_id and order.status in BUYER_CANCELLABLE_FROM:
            return sorted(s.value for s in nxt & BUYER_ALLOWED)
        return []

    def update_status(self, order_id: uuid.UUID, to: OrderStatus, principal: Principal, note: str | None = None,
                      tracking_number: str | None = None) -> OrderOut:
        order = self.db.scalar(select(Order).where(Order.id == order_id).with_for_update())
        if order is None or not self._can_view(order, principal):
            raise NotFoundError("Order was not found", code="ORDER_NOT_FOUND")
        if to.value not in self.allowed_transitions(order, principal):
            if to in TRANSITIONS[order.status]:
                raise PermissionDenied("You are not allowed to make this status change", code="TRANSITION_FORBIDDEN")
            raise ConflictError(f"Cannot change order from {order.status.value} to {to.value}",
                                code="INVALID_STATUS_TRANSITION")
        if to == OrderStatus.SHIPPED and tracking_number:
            order.tracking_number = tracking_number
        previous = order.status
        self._transition(order, to, principal.user_id, note)
        if to == OrderStatus.CANCELLED:
            self._restock(order)
            self._refund_payments(order)
        elif to == OrderStatus.REFUNDED:
            self._refund_payments(order)
        self.db.add(Notification(user_id=order.buyer_id, type="order.status",
                                 title=f"Order {order.order_number} is now {to.value}", data={"order_id": str(order.id)}))
        audit(self.db, principal.user_id, "order.status", "order", order.id,
              {"from": previous.value, "to": to.value, "note": note})
        self.db.commit()
        return self.to_out(order, detail=True, principal=principal)

    def _restock(self, order: Order) -> None:
        for item in order.items:
            inv = self.db.scalar(
                select(Inventory).where(Inventory.product_id == item.product_id,
                                        Inventory.variant_id == item.variant_id if item.variant_id
                                        else Inventory.variant_id.is_(None)).with_for_update()
            )
            if inv:
                inv.quantity_on_hand += item.quantity

    def _refund_payments(self, order: Order) -> None:
        for pay in order.payments:
            if pay.status in (PaymentStatus.CAPTURED, PaymentStatus.AUTHORIZED) and pay.provider_reference:
                res = self.payments.refund(provider_reference=pay.provider_reference, amount=pay.amount,
                                           idempotency_key=f"refund:{pay.id}")
                if res.status != PaymentStatus.REFUNDED:
                    raise ConflictError(res.failure_reason or "Refund failed", code="REFUND_FAILED")
                pay.status = PaymentStatus.REFUNDED

    # ============================================================ queries
    @staticmethod
    def _can_view(order: Order, principal: Principal) -> bool:
        return (
            order.buyer_id == principal.user_id
            or (principal.seller_id is not None and order.seller_id == principal.seller_id)
            or principal.has(P.ORDERS_MANAGE_ALL)
        )

    def get(self, order_id: uuid.UUID, principal: Principal) -> OrderOut:
        order = self.db.get(Order, order_id)
        if order is None or not self._can_view(order, principal):
            raise NotFoundError("Order was not found", code="ORDER_NOT_FOUND")
        return self.to_out(order, detail=True, principal=principal)

    def list(self, *, buyer_id: uuid.UUID | None = None, seller_id: uuid.UUID | None = None, status: str | None = None,
             q: str | None = None, offset: int = 0, limit: int = 20, principal: Principal | None = None
             ) -> tuple[list[OrderOut], int]:
        stmt = select(Order)
        if buyer_id:
            stmt = stmt.where(Order.buyer_id == buyer_id)
        if seller_id:
            stmt = stmt.where(Order.seller_id == seller_id)
        if status:
            stmt = stmt.where(Order.status == OrderStatus(status))
        if q:
            stmt = stmt.where(Order.order_number.ilike(f"%{q}%"))
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        orders = self.db.scalars(stmt.order_by(Order.placed_at.desc()).offset(offset).limit(limit)).all()
        return [self.to_out(o, principal=principal, include_buyer=buyer_id is None) for o in orders], total

    def to_out(self, o: Order, *, detail: bool = False, principal: Principal | None = None,
               include_buyer: bool = True) -> OrderOut:
        seller = self.db.get(SellerProfile, o.seller_id)
        buyer = self.db.get(User, o.buyer_id) if include_buyer else None
        items = []
        if detail:
            from app.models.catalog import Product

            for it in o.items:
                p = self.db.get(Product, it.product_id)
                out = OrderItemOut.model_validate(it)
                out.image_url = p.primary_image_url if p else None
                out.product_slug = p.slug if p else None
                items.append(out)
        return OrderOut(
            id=o.id, order_number=o.order_number, checkout_group_id=o.checkout_group_id, status=o.status.value,
            currency=o.currency, subtotal=o.subtotal, discount_total=o.discount_total, tax_total=o.tax_total,
            shipping_total=o.shipping_total, total=o.total, placed_at=o.placed_at,
            seller={"id": str(o.seller_id), "store_name": seller.store_name if seller else None,
                    "slug": seller.slug if seller else None},
            buyer={"id": str(buyer.id), "full_name": buyer.full_name} if buyer else None,
            item_count=sum(i.quantity for i in o.items),
            items=items,
            payments=[PaymentOut(id=p.id, provider=p.provider, status=p.status.value, amount=p.amount,
                                 currency=p.currency, failure_reason=p.failure_reason, created_at=p.created_at)
                      for p in o.payments] if detail else [],
            discounts=[OrderDiscountOut(source=d.source.value, description=d.description, amount=d.amount)
                       for d in o.discounts] if detail else [],
            status_history=[StatusEventOut.model_validate(e) for e in o.status_events] if detail else [],
            shipping_address=o.shipping_address if detail else None,
            tracking_number=o.tracking_number, notes=o.notes if detail else None,
            allowed_transitions=self.allowed_transitions(o, principal) if principal else [],
        )
