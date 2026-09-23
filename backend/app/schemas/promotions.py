"""Offer, coupon, bundle and negotiation schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.catalog import ProductCard
from app.schemas.common import MoneyOut

DiscountTypeIn = Literal["percentage", "fixed"]


class _DiscountIn(BaseModel):
    discount_type: DiscountTypeIn
    value: Decimal = Field(gt=0, le=100_000)
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @model_validator(mode="after")
    def _check(self):  # type: ignore[no-untyped-def]
        if self.discount_type == "percentage" and self.value > 90:
            raise ValueError("percentage discounts cannot exceed 90%")
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class OfferIn(_DiscountIn):
    name: str = Field(min_length=3, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    product_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    min_quantity: int = Field(1, ge=1, le=100)
    is_active: bool = True


class OfferUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    value: Decimal | None = Field(default=None, gt=0, le=100_000)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    min_quantity: int | None = Field(default=None, ge=1, le=100)
    is_active: bool | None = None


class OfferOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    discount_type: str
    value: MoneyOut
    scope: Literal["product", "category", "seller", "marketplace"]
    seller_id: uuid.UUID | None
    seller_name: str | None
    product_id: uuid.UUID | None
    product_name: str | None
    category_id: uuid.UUID | None
    min_quantity: int
    starts_at: datetime | None
    ends_at: datetime | None
    is_active: bool
    status: Literal["active", "scheduled", "expired", "disabled"]
    conditions: list[str]


class ProductOfferOut(OfferOut):
    eligible: bool
    discount_per_unit: MoneyOut
    price_after_offer: MoneyOut


class CouponIn(_DiscountIn):
    code: str = Field(min_length=3, max_length=40, pattern=r"^[A-Za-z0-9_\-]+$")
    description: str | None = Field(default=None, max_length=255)
    min_subtotal: Decimal = Field(Decimal(0), ge=0)
    usage_limit: int | None = Field(default=None, ge=1)
    per_user_limit: int = Field(1, ge=1, le=100)
    is_active: bool = True


class CouponOut(BaseModel):
    id: uuid.UUID
    code: str
    description: str | None
    discount_type: str
    value: MoneyOut
    min_subtotal: MoneyOut
    seller_id: uuid.UUID | None
    starts_at: datetime | None
    ends_at: datetime | None
    usage_limit: int | None
    per_user_limit: int
    used_count: int
    is_active: bool


class BundleIn(_DiscountIn):
    name: str = Field(min_length=3, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    product_ids: list[uuid.UUID] = Field(min_length=2, max_length=10)
    is_active: bool = True


class BundleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    value: Decimal | None = Field(default=None, gt=0)
    is_active: bool | None = None
    ends_at: datetime | None = None


class BundleOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    seller_id: uuid.UUID | None
    seller_name: str | None
    discount_type: str
    value: MoneyOut
    products: list[ProductCard]
    items_total: MoneyOut
    bundle_price: MoneyOut
    savings: MoneyOut
    is_active: bool
    available: bool
    starts_at: datetime | None
    ends_at: datetime | None


class NegotiationRequest(BaseModel):
    offered_price: Decimal = Field(gt=0, le=1_000_000, decimal_places=2)
    message: str | None = Field(default=None, max_length=300)


class NegotiationOut(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    product_slug: str
    status: str
    list_price: MoneyOut
    offered_price: MoneyOut
    counter_price: MoneyOut | None
    agreed_price: MoneyOut | None
    reason: str | None
    expires_at: datetime | None
    created_at: datetime


class NegotiationRuleIn(BaseModel):
    product_id: uuid.UUID | None = None
    is_enabled: bool = True
    max_discount_percent: Decimal = Field(ge=0, le=90)
    auto_accept_percent: Decimal = Field(ge=0, le=90)

    @model_validator(mode="after")
    def _check(self) -> NegotiationRuleIn:
        if self.auto_accept_percent > self.max_discount_percent:
            raise ValueError("auto_accept_percent must be <= max_discount_percent")
        return self


class NegotiationRuleOut(NegotiationRuleIn):
    id: uuid.UUID
    product_name: str | None = None
