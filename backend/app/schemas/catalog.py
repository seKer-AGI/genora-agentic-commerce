"""Catalog schemas: categories, products, variants, images."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.common import MoneyOut, ORMModel


class CategoryOut(ORMModel):
    id: uuid.UUID
    parent_id: uuid.UUID | None
    name: str
    slug: str
    description: str | None
    icon: str | None
    sort_order: int
    is_active: bool
    product_count: int = 0


class CategoryTree(CategoryOut):
    children: list[CategoryTree] = Field(default_factory=list)


class CategoryCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    slug: str | None = Field(default=None, pattern=r"^[a-z0-9-]{2,100}$")
    parent_id: uuid.UUID | None = None
    description: str | None = Field(default=None, max_length=500)
    icon: str | None = Field(default=None, max_length=48)
    sort_order: int = 0
    is_active: bool = True


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    parent_id: uuid.UUID | None = None
    description: str | None = Field(default=None, max_length=500)
    icon: str | None = Field(default=None, max_length=48)
    sort_order: int | None = None
    is_active: bool | None = None


class SellerMini(ORMModel):
    id: uuid.UUID
    store_name: str
    slug: str
    rating_avg: MoneyOut


class CategoryMini(ORMModel):
    id: uuid.UUID
    name: str
    slug: str


class ImageOut(ORMModel):
    id: uuid.UUID
    url: str
    alt_text: str | None
    is_primary: bool
    sort_order: int


class VariantOut(ORMModel):
    id: uuid.UUID
    sku: str
    name: str
    attributes: dict[str, Any]
    price_override: MoneyOut | None
    is_active: bool


class AppliedOfferOut(BaseModel):
    id: uuid.UUID
    name: str
    discount_type: str
    value: MoneyOut
    ends_at: datetime | None
    min_quantity: int


class ProductCard(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    brand: str | None
    price: MoneyOut
    sale_price: MoneyOut | None
    final_price: MoneyOut  # after the best automatically applied offer, quantity 1
    currency: str
    rating_avg: MoneyOut
    rating_count: int
    image_url: str | None
    in_stock: bool
    stock: int
    sold_count: int
    seller: SellerMini
    category: CategoryMini | None
    offer: AppliedOfferOut | None = None
    tags: list[str] = Field(default_factory=list)
    status: str
    score: float | None = None  # relevance score when returned from search


class ProductDetail(ProductCard):
    sku: str
    description: str
    seo_description: str | None
    attributes: dict[str, Any]
    images: list[ImageOut]
    variants: list[VariantOut]
    low_stock: bool
    rating_distribution: dict[str, int] = Field(default_factory=dict)
    negotiable: bool = False
    created_at: datetime
    updated_at: datetime


class VariantIn(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    attributes: dict[str, Any] = Field(default_factory=dict)
    price_override: Decimal | None = Field(default=None, ge=0, le=1_000_000)
    stock: int = Field(default=0, ge=0, le=1_000_000)


class ProductBase(BaseModel):
    description: str | None = Field(default=None, max_length=10_000)
    seo_description: str | None = Field(default=None, max_length=320)
    brand: str | None = Field(default=None, max_length=80)
    category_id: uuid.UUID | None = None
    attributes: dict[str, Any] | None = None
    tags: list[str] | None = Field(default=None, max_length=20)
    images: list[str] | None = Field(default=None, max_length=10, description="Image URLs (first = primary)")

    @field_validator("tags")
    @classmethod
    def _norm_tags(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        out = []
        for t in v:
            t = t.strip().lower().replace(" ", "-")[:48]
            if t and t not in out:
                out.append(t)
        return out

    @field_validator("attributes")
    @classmethod
    def _limit_attrs(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        if v is not None and len(v) > 40:
            raise ValueError("at most 40 attributes")
        return v

    @field_validator("images")
    @classmethod
    def _image_urls(cls, v: list[str] | None) -> list[str] | None:
        for url in v or []:
            if not (url.startswith("https://") or url.startswith("/api/v1/media/")):
                raise ValueError("images must be https URLs or uploaded media")
        return v


class ProductCreate(ProductBase):
    name: str = Field(min_length=3, max_length=200)
    sku: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._\-]+$")
    description: str = Field(min_length=10, max_length=10_000)
    price: Decimal = Field(gt=0, le=1_000_000, decimal_places=2)
    sale_price: Decimal | None = Field(default=None, gt=0, le=1_000_000, decimal_places=2)
    currency: Literal["USD"] = "USD"
    status: Literal["draft", "active"] = "draft"
    stock: int = Field(default=0, ge=0, le=1_000_000)
    low_stock_threshold: int = Field(default=5, ge=0, le=10_000)
    variants: list[VariantIn] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def _sale_below_price(self) -> ProductCreate:
        if self.sale_price is not None and self.sale_price > self.price:
            raise ValueError("sale_price must not exceed price")
        return self


class ProductUpdate(ProductBase):
    name: str | None = Field(default=None, min_length=3, max_length=200)
    sku: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._\-]+$")
    price: Decimal | None = Field(default=None, gt=0, le=1_000_000, decimal_places=2)
    sale_price: Decimal | None = Field(default=None, ge=0, le=1_000_000, decimal_places=2)
    clear_sale_price: bool = False
    status: Literal["draft", "active", "archived"] | None = None


class InventoryOut(BaseModel):
    product_id: uuid.UUID
    product_name: str
    sku: str
    status: str
    quantity_on_hand: int
    quantity_reserved: int
    available: int
    low_stock_threshold: int
    is_low: bool
    sold_count: int
    image_url: str | None


class InventoryUpdate(BaseModel):
    quantity_on_hand: int | None = Field(default=None, ge=0, le=1_000_000)
    adjust_by: int | None = Field(default=None, ge=-1_000_000, le=1_000_000)
    low_stock_threshold: int | None = Field(default=None, ge=0, le=10_000)

    @model_validator(mode="after")
    def _one_of(self) -> InventoryUpdate:
        if self.quantity_on_hand is not None and self.adjust_by is not None:
            raise ValueError("use either quantity_on_hand or adjust_by, not both")
        return self


CategoryTree.model_rebuild()
