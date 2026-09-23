"""Structured response blocks rendered by the GenOra UI (product cards, tables, …).

Blocks are built only from tool outputs, never from free-form model text.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Block(BaseModel):
    type: str


class ProductListBlock(Block):
    type: Literal["product_list"] = "product_list"
    title: str
    products: list[dict[str, Any]]
    reasons: dict[str, list[str]] = Field(default_factory=dict)  # product_id -> why it was recommended
    note: str | None = None


class ComparisonBlock(Block):
    type: Literal["comparison"] = "comparison"
    products: list[dict[str, Any]]
    rows: list[dict[str, Any]]  # {label, values: [..], highlight: index|None, source: "catalog"|"reviews"}
    notes: list[str] = Field(default_factory=list)


class OffersBlock(Block):
    type: Literal["offers"] = "offers"
    product: dict[str, Any] | None = None
    offers: list[dict[str, Any]]
    note: str | None = None


class ReviewSummaryBlock(Block):
    type: Literal["review_summary"] = "review_summary"
    product: dict[str, Any]
    insights: dict[str, Any]
    disclaimer: str


class BundleBlock(Block):
    type: Literal["bundles"] = "bundles"
    product: dict[str, Any]
    bundles: list[dict[str, Any]]
    accessories: list[dict[str, Any]]
    note: str | None = None


class NegotiationBlock(Block):
    type: Literal["negotiation"] = "negotiation"
    product: dict[str, Any]
    outcome: dict[str, Any]


class ExternalPricesBlock(Block):
    type: Literal["external_prices"] = "external_prices"
    product: dict[str, Any]
    our_price: float
    quotes: list[dict[str, Any]]
    providers_configured: list[str]
    note: str


class ConfirmationBlock(Block):
    type: Literal["confirmation"] = "confirmation"
    action_id: str
    summary: str
    details: list[str]
    expires_at: str


class ImageAnalysisBlock(Block):
    type: Literal["image_analysis"] = "image_analysis"
    analysis: dict[str, Any]


class KpiBlock(Block):
    type: Literal["kpis"] = "kpis"
    title: str
    kpis: list[dict[str, Any]]  # {label, value, format, change_pct}
    series: list[dict[str, Any]] = Field(default_factory=list)


class TableBlock(Block):
    type: Literal["table"] = "table"
    title: str
    columns: list[dict[str, str]]  # {key, label, format?}
    rows: list[dict[str, Any]]
    note: str | None = None


class ListingDraftBlock(Block):
    type: Literal["listing_draft"] = "listing_draft"
    draft: dict[str, Any]
    generated_by: str
    note: str


class ForecastBlock(Block):
    type: Literal["forecast"] = "forecast"
    forecast: dict[str, Any]


class RecommendationBlock(Block):
    type: Literal["recommendations"] = "recommendations"
    title: str
    items: list[dict[str, Any]]  # {title, rationale, evidence: [..], action?: {...}}


class NoticeBlock(Block):
    type: Literal["notice"] = "notice"
    level: Literal["info", "warning", "error", "success"] = "info"
    text: str
