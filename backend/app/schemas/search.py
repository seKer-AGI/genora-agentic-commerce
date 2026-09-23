"""Search request/response schemas."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.catalog import ProductCard

SortOption = Literal["relevance", "price_asc", "price_desc", "rating", "newest", "popularity"]
SearchMode = Literal["keyword", "semantic", "hybrid"]


class SearchFilters(BaseModel):
    category: str | None = Field(default=None, description="Category id or slug (includes sub-categories)")
    min_price: Decimal | None = Field(default=None, ge=0)
    max_price: Decimal | None = Field(default=None, ge=0)
    seller: str | None = Field(default=None, description="Seller id or slug")
    brands: list[str] = Field(default_factory=list, max_length=20)
    min_rating: float | None = Field(default=None, ge=0, le=5)
    in_stock: bool = False
    tags: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def _price_range(self) -> SearchFilters:
        if self.min_price is not None and self.max_price is not None and self.min_price > self.max_price:
            raise ValueError("min_price must be <= max_price")
        return self


class SearchQuery(SearchFilters):
    q: str | None = Field(default=None, max_length=200)
    mode: SearchMode = "hybrid"
    sort: SortOption = "relevance"
    page: int = Field(1, ge=1, le=500)
    page_size: int = Field(20, ge=1, le=60)


class Facet(BaseModel):
    value: str
    label: str
    count: int


class SearchResponse(BaseModel):
    items: list[ProductCard]
    total: int
    page: int
    page_size: int
    query: str | None
    mode: SearchMode
    sort: SortOption
    facets: dict[str, list[Facet]]
    price_range: dict[str, float | None]
    engine: dict[str, object]
    latency_ms: int


class SuggestResponse(BaseModel):
    products: list[dict[str, str]]
    categories: list[dict[str, str]]


class SearchHit(BaseModel):
    product_id: uuid.UUID
    score: float
