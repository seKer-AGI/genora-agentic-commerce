"""Typed contracts for buyer-side (Nova) tools. The host application implements the tools."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ProductSummary(BaseModel):
    id: str
    slug: str
    name: str
    brand: str | None = None
    price: float
    sale_price: float | None = None
    final_price: float
    currency: str = "USD"
    rating_avg: float = 0
    rating_count: int = 0
    in_stock: bool = True
    stock: int = 0
    seller_id: str
    seller_name: str
    category: str | None = None
    category_slug: str | None = None
    image_url: str | None = None
    url: str
    tags: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)
    offer_name: str | None = None
    score: float | None = None


class SearchProductsInput(BaseModel):
    query: str | None = Field(default=None, max_length=200)
    category: str | None = Field(default=None, max_length=100, description="category slug")
    min_price: float | None = Field(default=None, ge=0)
    max_price: float | None = Field(default=None, ge=0)
    brands: list[str] = Field(default_factory=list, max_length=10)
    min_rating: float | None = Field(default=None, ge=0, le=5)
    in_stock_only: bool = False
    sort: Literal["relevance", "price_asc", "price_desc", "rating", "popularity", "newest"] = "relevance"
    mode: Literal["keyword", "semantic", "hybrid"] = "hybrid"
    limit: int = Field(default=8, ge=1, le=20)


class ProductListOutput(BaseModel):
    products: list[ProductSummary]
    total: int
    applied_filters: dict[str, Any] = Field(default_factory=dict)


class ResolveProductInput(BaseModel):
    reference: str = Field(min_length=2, max_length=160)
    limit: int = Field(default=5, ge=1, le=10)


class ResolveProductOutput(BaseModel):
    candidates: list[ProductSummary]
    confident: bool  # a single clear match


class ProductIdInput(BaseModel):
    product_id: str = Field(min_length=8, max_length=64)


class ProductDetailsOutput(BaseModel):
    product: ProductSummary
    description: str
    attributes: dict[str, Any]
    variants: list[dict[str, Any]] = Field(default_factory=list)
    negotiable: bool = False
    low_stock: bool = False


class OfferInfo(BaseModel):
    name: str
    description: str | None = None
    scope: str
    discount_type: str
    value: float
    discount_per_unit: float
    price_after_offer: float
    min_quantity: int
    eligible_for_single_unit: bool
    ends_at: datetime | None = None
    conditions: list[str]


class ProductOffersOutput(BaseModel):
    product: ProductSummary
    offers: list[OfferInfo]


class BundleInfo(BaseModel):
    id: str
    name: str
    description: str | None = None
    products: list[ProductSummary]
    items_total: float
    bundle_price: float
    savings: float
    available: bool


class ProductBundlesOutput(BaseModel):
    product: ProductSummary
    bundles: list[BundleInfo]


class AccessoriesInput(ProductIdInput):
    limit: int = Field(default=6, ge=1, le=12)
    max_price: float | None = Field(default=None, ge=0)


class AccessoriesOutput(BaseModel):
    product: ProductSummary
    accessories: list[ProductSummary]
    compatibility: dict[str, str]  # product_id -> evidence (e.g. "compatible mount: LX-mount")
    categories_searched: list[str]


class ReviewInsightsOutput(BaseModel):
    product: ProductSummary
    insights: dict[str, Any]
    disclaimer: str


class NegotiationPolicyOutput(BaseModel):
    product: ProductSummary
    negotiable: bool
    reason: str | None = None
    current_price: float


class SubmitNegotiationInput(ProductIdInput):
    offered_price: float = Field(gt=0, le=1_000_000)


class AcceptCounterInput(BaseModel):
    negotiation_id: str = Field(min_length=8, max_length=64)


class NegotiationResultOutput(BaseModel):
    id: str
    product_name: str
    status: str
    list_price: float
    offered_price: float
    counter_price: float | None = None
    agreed_price: float | None = None
    reason: str | None = None
    expires_at: datetime | None = None


class ExternalQuote(BaseModel):
    provider: str
    marketplace: str
    price: float
    currency: str
    url: str | None = None
    in_stock: bool | None = None
    retrieved_at: datetime
    is_test_data: bool = False


class ExternalPricesOutput(BaseModel):
    product: ProductSummary
    our_price: float
    quotes: list[ExternalQuote]
    providers_configured: list[str]
    errors: list[str] = Field(default_factory=list)


class AddToCartInput(ProductIdInput):
    quantity: int = Field(default=1, ge=1, le=10)


class AddBundleToCartInput(BaseModel):
    bundle_id: str = Field(min_length=8, max_length=64)


class CartSummaryOutput(BaseModel):
    item_count: int
    subtotal: float
    discount_total: float
    total: float
    added: str


class RecommendationsInput(BaseModel):
    strategy: Literal["for_you", "popular", "similar", "also_bought"] = "for_you"
    product_id: str | None = None
    limit: int = Field(default=6, ge=1, le=12)


class AnalyzeImageInput(BaseModel):
    attachment_id: str = Field(min_length=4, max_length=64)


class ImageAnalysisOutput(BaseModel):
    product_type: str
    category_hint: str | None = None
    brand: str | None = None
    colors: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    attributes: dict[str, str] = Field(default_factory=dict)
    search_query: str
    confidence: float
    provider: str
