"""Review schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ReviewIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    title: str | None = Field(default=None, max_length=160)
    body: str = Field(min_length=10, max_length=5000)


class ReviewUpdate(BaseModel):
    rating: int | None = Field(default=None, ge=1, le=5)
    title: str | None = Field(default=None, max_length=160)
    body: str | None = Field(default=None, min_length=10, max_length=5000)


class ReviewOut(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    product_name: str | None = None
    author_name: str
    rating: int
    title: str | None
    body: str
    status: str
    is_verified_purchase: bool
    helpful_count: int
    moderation_reason: str | None = None
    created_at: datetime
    is_mine: bool = False


class ReviewModeration(BaseModel):
    status: Literal["approved", "rejected"]
    reason: str | None = Field(default=None, max_length=255)


class RatingSummary(BaseModel):
    average: float
    count: int
    distribution: dict[str, int]


class ReviewSummaryOut(BaseModel):
    product_id: uuid.UUID
    rating: RatingSummary
    insights: dict[str, Any]
    disclaimer: str = "Derived from customer reviews; not verified product specifications."


class ReviewEligibility(BaseModel):
    can_review: bool
    reason: str | None
    existing_review_id: uuid.UUID | None = None
