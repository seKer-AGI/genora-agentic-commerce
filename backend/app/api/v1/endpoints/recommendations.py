"""/api/v1/recommendations."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentPrincipal, DbSession
from app.services.recommendation_service import RecommendationResult, RecommendationService

router = APIRouter(prefix="/recommendations", tags=["recommendations"])
Limit = Annotated[int, Query(ge=1, le=24)]


@router.get("/popular", response_model=RecommendationResult)
def popular(db: DbSession, limit: Limit = 12, days: Annotated[int, Query(ge=1, le=365)] = 30) -> RecommendationResult:
    return RecommendationService(db).popular(limit, days)


@router.get("/for-you", response_model=RecommendationResult)
def for_you(principal: CurrentPrincipal, db: DbSession, limit: Limit = 12) -> RecommendationResult:
    return RecommendationService(db).for_user(principal.user_id, limit)


@router.get("/similar/{product_id}", response_model=RecommendationResult)
def similar(product_id: uuid.UUID, db: DbSession, limit: Limit = 8) -> RecommendationResult:
    return RecommendationService(db).similar(product_id, limit)


@router.get("/also-bought/{product_id}", response_model=RecommendationResult)
def also_bought(product_id: uuid.UUID, db: DbSession, limit: Limit = 8) -> RecommendationResult:
    return RecommendationService(db).also_bought(product_id, limit)


@router.get("/category/{category}", response_model=RecommendationResult)
def by_category(category: str, db: DbSession, limit: Limit = 12) -> RecommendationResult:
    return RecommendationService(db).category(category, limit)


@router.get("/semantic", response_model=RecommendationResult)
def semantic(db: DbSession, q: Annotated[str, Query(min_length=2, max_length=200)], limit: Limit = 8) -> RecommendationResult:
    return RecommendationService(db).semantic(q, limit)
