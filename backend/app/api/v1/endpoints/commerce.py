"""/api/v1/cart, /wishlist, /addresses, /orders, /negotiations."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Header, Query, Response, status
from sqlalchemy import select, update

from app.api.deps import CurrentPrincipal, DbSession
from app.core.errors import NotFoundError
from app.core.rbac import P
from app.core.security import utcnow
from app.models.enums import OrderStatus
from app.models.identity import Address
from app.schemas.catalog import ProductCard
from app.schemas.commerce import (
    AddCartItem,
    AddressIn,
    AddressOut,
    ApplyCoupon,
    CartOut,
    CheckoutRequest,
    CheckoutResponse,
    OrderOut,
    OrderStatusUpdate,
    UpdateCartItem,
)
from app.schemas.common import Page
from app.schemas.promotions import NegotiationOut
from app.services.cart_service import CartService, WishlistService
from app.services.negotiation_service import NegotiationService
from app.services.order_service import OrderService

cart = APIRouter(prefix="/cart", tags=["cart"])
wishlist = APIRouter(prefix="/wishlist", tags=["wishlist"])
addresses = APIRouter(prefix="/addresses", tags=["addresses"])
orders = APIRouter(prefix="/orders", tags=["orders"])
negotiations = APIRouter(prefix="/negotiations", tags=["negotiations"])


def _cart(principal: CurrentPrincipal, db: DbSession) -> CartService:
    principal.require(P.CART_MANAGE)
    return CartService(db, principal.user_id)


# ------------------------------------------------------------------ cart
@cart.get("", response_model=CartOut)
def get_cart(principal: CurrentPrincipal, db: DbSession) -> CartOut:
    return _cart(principal, db).view()


@cart.post("/items", response_model=CartOut, status_code=status.HTTP_201_CREATED)
def add_item(body: AddCartItem, principal: CurrentPrincipal, db: DbSession) -> CartOut:
    return _cart(principal, db).add(body.product_id, body.quantity, body.variant_id)


@cart.patch("/items/{item_id}", response_model=CartOut)
def update_item(item_id: uuid.UUID, body: UpdateCartItem, principal: CurrentPrincipal, db: DbSession) -> CartOut:
    return _cart(principal, db).update(item_id, body.quantity)


@cart.delete("/items/{item_id}", response_model=CartOut)
def remove_item(item_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> CartOut:
    return _cart(principal, db).remove(item_id)


@cart.post("/bundles/{bundle_id}", response_model=CartOut, status_code=status.HTTP_201_CREATED)
def add_bundle(bundle_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> CartOut:
    return _cart(principal, db).add_bundle(bundle_id)


@cart.post("/coupon", response_model=CartOut)
def apply_coupon(body: ApplyCoupon, principal: CurrentPrincipal, db: DbSession) -> CartOut:
    return _cart(principal, db).apply_coupon(body.code)


@cart.delete("/coupon", response_model=CartOut)
def remove_coupon(principal: CurrentPrincipal, db: DbSession) -> CartOut:
    return _cart(principal, db).remove_coupon()


@cart.delete("", response_model=CartOut)
def clear_cart(principal: CurrentPrincipal, db: DbSession) -> CartOut:
    return _cart(principal, db).clear()


# ------------------------------------------------------------------ wishlist
@wishlist.get("", response_model=list[ProductCard])
def get_wishlist(principal: CurrentPrincipal, db: DbSession) -> list[ProductCard]:
    principal.require(P.WISHLIST_MANAGE)
    return WishlistService(db, principal.user_id).view()


@wishlist.post("/{product_id}", response_model=list[ProductCard], status_code=status.HTTP_201_CREATED)
def add_wishlist(product_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> list[ProductCard]:
    principal.require(P.WISHLIST_MANAGE)
    return WishlistService(db, principal.user_id).add(product_id)


@wishlist.delete("/{product_id}", response_model=list[ProductCard])
def remove_wishlist(product_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> list[ProductCard]:
    principal.require(P.WISHLIST_MANAGE)
    return WishlistService(db, principal.user_id).remove(product_id)


# ------------------------------------------------------------------ addresses
@addresses.get("", response_model=list[AddressOut])
def list_addresses(principal: CurrentPrincipal, db: DbSession) -> list[AddressOut]:
    rows = db.scalars(select(Address).where(Address.user_id == principal.user_id, Address.deleted_at.is_(None))
                      .order_by(Address.is_default.desc(), Address.created_at))
    return [AddressOut.model_validate(a) for a in rows]


@addresses.post("", response_model=AddressOut, status_code=status.HTTP_201_CREATED)
def create_address(body: AddressIn, principal: CurrentPrincipal, db: DbSession) -> AddressOut:
    if body.is_default:
        db.execute(update(Address).where(Address.user_id == principal.user_id).values(is_default=False))
    a = Address(user_id=principal.user_id, **body.model_dump())
    db.add(a)
    db.commit()
    return AddressOut.model_validate(a)


@addresses.delete("/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_address(address_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> Response:
    a = db.get(Address, address_id)
    if a is None or a.user_id != principal.user_id or a.deleted_at is not None:
        raise NotFoundError("Address was not found", code="ADDRESS_NOT_FOUND")
    a.deleted_at = utcnow()
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------ orders
@orders.post("/checkout", response_model=CheckoutResponse, status_code=status.HTTP_201_CREATED)
def checkout(
    body: CheckoutRequest, principal: CurrentPrincipal, db: DbSession,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=100)] = None,
) -> CheckoutResponse:
    """Converts the cart into one order per seller. Prices and totals are computed server-side."""
    return OrderService(db).checkout(principal, body, idempotency_key)


@orders.get("", response_model=Page[OrderOut])
def my_orders(
    principal: CurrentPrincipal, db: DbSession, status_: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1, page_size: Annotated[int, Query(ge=1, le=50)] = 10,
) -> Page[OrderOut]:
    principal.require(P.ORDERS_READ_OWN)
    if status_:
        OrderStatus(status_)
    items, total = OrderService(db).list(buyer_id=principal.user_id, status=status_, offset=(page - 1) * page_size,
                                         limit=page_size, principal=principal)
    return Page(items=items, total=total, page=page, page_size=page_size)


@orders.get("/{order_id}", response_model=OrderOut)
def get_order(order_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> OrderOut:
    return OrderService(db).get(order_id, principal)


@orders.post("/{order_id}/status", response_model=OrderOut)
def change_status(order_id: uuid.UUID, body: OrderStatusUpdate, principal: CurrentPrincipal, db: DbSession) -> OrderOut:
    """Buyers may cancel pending/confirmed orders; sellers fulfil their orders; admins manage all orders."""
    return OrderService(db).update_status(order_id, OrderStatus(body.status), principal, body.note, body.tracking_number)


# ------------------------------------------------------------------ negotiations
@negotiations.get("", response_model=list[NegotiationOut])
def my_negotiations(principal: CurrentPrincipal, db: DbSession) -> list[NegotiationOut]:
    return NegotiationService(db).list_for_buyer(principal.user_id)


@negotiations.post("/{negotiation_id}/accept", response_model=NegotiationOut)
def accept_counter(negotiation_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> NegotiationOut:
    return NegotiationService(db).accept_counter(negotiation_id, principal)
