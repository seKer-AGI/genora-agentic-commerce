"""Analytics schemas."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

ClientEventType = Literal[
    "product_view", "category_view", "search_click", "recommendation_click", "bundle_view", "nova_open", "astra_open",
]


class EventIn(BaseModel):
    event_type: ClientEventType
    product_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    session_key: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")
    properties: dict[str, Any] = Field(default_factory=dict)


class Kpi(BaseModel):
    value: float
    previous: float
    change_pct: float | None


class SeriesPoint(BaseModel):
    date: date
    revenue: float
    orders: int
    units: int = 0


class ProductPerf(BaseModel):
    product_id: uuid.UUID
    name: str
    slug: str
    image_url: str | None = None
    revenue: float
    units: int
    orders: int
    views: int
    conversion_rate: float | None
    rating_avg: float
    stock: int | None = None


class SellerOverview(BaseModel):
    period_days: int
    currency: str = "USD"
    revenue: Kpi
    orders: Kpi
    units_sold: Kpi
    average_order_value: Kpi
    views: Kpi
    conversion_rate: Kpi
    series: list[SeriesPoint]
    top_products: list[ProductPerf]
    low_performers: list[ProductPerf]
    status_breakdown: dict[str, int]
    low_stock_count: int
    rating_avg: float
    definitions: dict[str, str]


class AdminOverview(BaseModel):
    period_days: int
    totals: dict[str, float]
    gmv: Kpi
    revenue: Kpi
    orders: Kpi
    new_users: Kpi
    series: list[SeriesPoint]
    top_products: list[ProductPerf]
    top_categories: list[dict[str, Any]]
    seller_performance: list[dict[str, Any]]
    status_breakdown: dict[str, int]


class AgentUsage(BaseModel):
    period_days: int
    totals: dict[str, Any]
    by_agent: list[dict[str, Any]]
    by_intent: list[dict[str, Any]]
    by_status: dict[str, int]
    tool_calls: list[dict[str, Any]]
    series: list[dict[str, Any]]
    runtime: dict[str, Any]


class SearchAnalytics(BaseModel):
    period_days: int
    total_searches: int
    zero_result_rate: float
    top_queries: list[dict[str, Any]]
    zero_result_queries: list[dict[str, Any]]
    by_source: dict[str, int]
    series: list[dict[str, Any]]
