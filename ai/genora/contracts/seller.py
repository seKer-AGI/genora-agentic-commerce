"""Typed contracts for seller-side (Astra) tools. Seller identity always comes from the ToolContext."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class InventoryInput(BaseModel):
    low_only: bool = True


class InventoryItem(BaseModel):
    product_id: str
    name: str
    sku: str
    status: str
    available: int
    low_stock_threshold: int
    is_low: bool
    sold_last_30d: int = 0
    days_of_cover: float | None = None  # available / avg daily units (last 30d)


class InventoryOutput(BaseModel):
    items: list[InventoryItem]
    total_products: int


class PeriodInput(BaseModel):
    days: int = Field(default=30, ge=1, le=365)


class Metric(BaseModel):
    value: float
    previous: float
    change_pct: float | None


class PerfItem(BaseModel):
    product_id: str
    name: str
    revenue: float
    units: int
    orders: int
    views: int
    conversion_rate: float | None
    rating_avg: float
    stock: int | None = None


class SalesSummaryOutput(BaseModel):
    period_days: int
    revenue: Metric
    orders: Metric
    units_sold: Metric
    average_order_value: Metric
    views: Metric
    conversion_rate: Metric
    series: list[dict[str, Any]]
    top_products: list[PerfItem]
    low_performers: list[PerfItem]
    definitions: dict[str, str]


class ProductPerformanceInput(PeriodInput):
    order: Literal["best", "worst"] = "worst"
    limit: int = Field(default=5, ge=1, le=20)


class ProductPerformanceOutput(BaseModel):
    period_days: int
    order: str
    items: list[PerfItem]


class ResolveSellerProductInput(BaseModel):
    reference: str = Field(min_length=2, max_length=160)


class SellerProductRef(BaseModel):
    id: str
    name: str
    sku: str
    price: float
    sale_price: float | None
    status: str
    stock: int


class ResolveSellerProductOutput(BaseModel):
    candidates: list[SellerProductRef]
    confident: bool


class DraftListingInput(BaseModel):
    product_name: str = Field(min_length=3, max_length=200)
    brand: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=2000)
    attributes: dict[str, Any] = Field(default_factory=dict)
    price: float | None = Field(default=None, gt=0, le=1_000_000)


class CategorySuggestion(BaseModel):
    id: str
    name: str
    slug: str
    score: float


class ListingDraftOutput(BaseModel):
    title: str
    description: str
    seo_description: str
    tags: list[str]
    attributes: dict[str, Any]
    brand: str | None
    price: float | None
    suggested_sku: str
    category_suggestions: list[CategorySuggestion]
    generated_by: str  # "template" | "llm:<model>"
    warnings: list[str] = Field(default_factory=list)


class CreateProductInput(BaseModel):
    name: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=10, max_length=10_000)
    seo_description: str | None = Field(default=None, max_length=320)
    sku: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._\-]+$")
    brand: str | None = Field(default=None, max_length=80)
    category_id: str | None = None
    price: float = Field(gt=0, le=1_000_000)
    stock: int = Field(default=0, ge=0, le=1_000_000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    attributes: dict[str, Any] = Field(default_factory=dict)
    status: Literal["draft", "active"] = "draft"


class ProductChangeOutput(BaseModel):
    product_id: str
    name: str
    status: str
    price: float
    sale_price: float | None
    stock: int
    url: str
    changes: dict[str, Any] = Field(default_factory=dict)


class UpdatePriceInput(BaseModel):
    product_id: str
    price: float | None = Field(default=None, gt=0, le=1_000_000)
    sale_price: float | None = Field(default=None, gt=0, le=1_000_000)
    clear_sale_price: bool = False

    @model_validator(mode="after")
    def _something(self) -> UpdatePriceInput:
        if self.price is None and self.sale_price is None and not self.clear_sale_price:
            raise ValueError("nothing to change")
        return self


class UpdateStockInput(BaseModel):
    product_id: str
    quantity_on_hand: int = Field(ge=0, le=1_000_000)


class CreateOfferInput(BaseModel):
    product_id: str
    percent_off: float = Field(gt=0, le=50)
    days: int = Field(default=14, ge=1, le=90)
    name: str | None = Field(default=None, max_length=120)


class OfferCreatedOutput(BaseModel):
    offer_id: str
    name: str
    product_name: str
    percent_off: float
    ends_at: str
    new_final_price: float


class DiscountStrategyInput(BaseModel):
    days: int = Field(default=30, ge=7, le=180)
    product_ids: list[str] = Field(default_factory=list, max_length=20)


class StrategySuggestion(BaseModel):
    product_id: str
    product_name: str
    action: Literal["discount", "price_review", "bundle", "improve_listing", "hold", "restock"]
    headline: str
    rationale: str
    evidence: list[str]
    proposed_percent_off: float | None = None


class DiscountStrategyOutput(BaseModel):
    period_days: int
    suggestions: list[StrategySuggestion]
    method: str


class ForecastInput(BaseModel):
    target: Literal["sales", "revenue", "product_demand", "category_demand"] = "revenue"
    entity_id: str | None = None
    horizon_days: int = Field(default=14, ge=1, le=90)
    provider: str | None = None


class ForecastOutput(BaseModel):
    id: str | None
    target: str
    provider: str
    model_name: str
    status: str
    horizon: int
    history: list[dict[str, Any]]
    points: list[dict[str, Any]]
    metrics: dict[str, Any]
    error: str | None = None
