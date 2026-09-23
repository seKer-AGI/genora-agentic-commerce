"""Cart, wishlist, checkout, order and address schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.catalog import ProductCard
from app.schemas.common import MoneyOut, ORMModel


class DiscountOut(BaseModel):
    source: str
    description: str
    amount: MoneyOut


class CartLineOut(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    product_slug: str
    product_name: str
    image_url: str | None
    seller_id: uuid.UUID
    seller_name: str
    variant_id: uuid.UUID | None
    bundle_id: uuid.UUID | None
    quantity: int
    unit_price: MoneyOut
    list_price: MoneyOut
    subtotal: MoneyOut
    discounts: list[DiscountOut]
    total: MoneyOut
    available: int
    issues: list[str]


class SellerGroupOut(BaseModel):
    seller_id: uuid.UUID
    store_name: str
    subtotal: MoneyOut
    discount_total: MoneyOut
    shipping: MoneyOut
    tax: MoneyOut
    total: MoneyOut


class CartOut(BaseModel):
    id: uuid.UUID
    items: list[CartLineOut]
    sellers: list[SellerGroupOut]
    coupon_code: str | None
    coupon_message: str | None
    coupon_discount: MoneyOut
    subtotal: MoneyOut
    discount_total: MoneyOut
    shipping_total: MoneyOut
    tax_total: MoneyOut
    total: MoneyOut
    currency: str
    item_count: int
    issues: list[str]


class AddCartItem(BaseModel):
    product_id: uuid.UUID
    variant_id: uuid.UUID | None = None
    quantity: int = Field(1, ge=1, le=99)


class UpdateCartItem(BaseModel):
    quantity: int = Field(ge=1, le=99)


class ApplyCoupon(BaseModel):
    code: str = Field(min_length=3, max_length=40, pattern=r"^[A-Za-z0-9_\-]+$")


class AddressIn(BaseModel):
    label: str | None = Field(default=None, max_length=40)
    recipient_name: str = Field(min_length=2, max_length=120)
    line1: str = Field(min_length=3, max_length=200)
    line2: str | None = Field(default=None, max_length=200)
    city: str = Field(min_length=2, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    postal_code: str = Field(min_length=3, max_length=20, pattern=r"^[A-Za-z0-9 \-]+$")
    country: str = Field(min_length=2, max_length=2, pattern=r"^[A-Z]{2}$")
    phone: str | None = Field(default=None, max_length=32)
    is_default: bool = False


class AddressOut(ORMModel, AddressIn):
    id: uuid.UUID


class CheckoutRequest(BaseModel):
    address_id: uuid.UUID | None = None
    address: AddressIn | None = None
    payment_method: str = Field(
        "pm_card_visa", min_length=3, max_length=100,
        description="Payment method token from the payment provider's client SDK (sandbox: pm_card_visa / pm_card_declined)",
    )
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _address(self) -> CheckoutRequest:
        if (self.address_id is None) == (self.address is None):
            raise ValueError("provide exactly one of address_id or address")
        return self


class OrderItemOut(ORMModel):
    id: uuid.UUID
    product_id: uuid.UUID
    variant_id: uuid.UUID | None
    bundle_id: uuid.UUID | None
    product_name: str
    sku: str
    unit_price: MoneyOut
    quantity: int
    discount_amount: MoneyOut
    line_total: MoneyOut
    image_url: str | None = None
    product_slug: str | None = None


class PaymentOut(ORMModel):
    id: uuid.UUID
    provider: str
    status: str
    amount: MoneyOut
    currency: str
    failure_reason: str | None
    created_at: datetime


class StatusEventOut(ORMModel):
    from_status: str | None
    to_status: str
    note: str | None
    created_at: datetime


class OrderDiscountOut(ORMModel):
    source: str
    description: str
    amount: MoneyOut


class OrderOut(BaseModel):
    id: uuid.UUID
    order_number: str
    checkout_group_id: uuid.UUID
    status: str
    currency: str
    subtotal: MoneyOut
    discount_total: MoneyOut
    tax_total: MoneyOut
    shipping_total: MoneyOut
    total: MoneyOut
    placed_at: datetime
    seller: dict[str, Any]
    buyer: dict[str, Any] | None = None
    item_count: int
    items: list[OrderItemOut] = Field(default_factory=list)
    payments: list[PaymentOut] = Field(default_factory=list)
    discounts: list[OrderDiscountOut] = Field(default_factory=list)
    status_history: list[StatusEventOut] = Field(default_factory=list)
    shipping_address: dict[str, Any] | None = None
    tracking_number: str | None = None
    notes: str | None = None
    allowed_transitions: list[str] = Field(default_factory=list)


class CheckoutResponse(BaseModel):
    checkout_group_id: uuid.UUID
    orders: list[OrderOut]
    total_charged: MoneyOut
    payment_status: str


class OrderStatusUpdate(BaseModel):
    status: Literal["confirmed", "processing", "shipped", "delivered", "cancelled", "refunded"]
    note: str | None = Field(default=None, max_length=255)
    tracking_number: str | None = Field(default=None, max_length=64)


class WishlistOut(BaseModel):
    items: list[ProductCard]
