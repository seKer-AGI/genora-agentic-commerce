"""/api/v1/analytics — event ingestion and dashboards."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import DbSession, OptionalPrincipal, SellerPrincipal, require_permission
from app.core.principal import Principal
from app.core.rate_limit import rate_limiter
from app.core.rbac import P
from app.schemas.analytics import AdminOverview, AgentUsage, EventIn, SearchAnalytics, SellerOverview
from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])
Days = Annotated[int, Query(ge=1, le=365)]
AdminAnalytics = Annotated[Principal, Depends(require_permission(P.ANALYTICS_READ_ALL))]


@router.post("/events", status_code=status.HTTP_202_ACCEPTED)
def track(body: EventIn, db: DbSession, principal: OptionalPrincipal) -> Response:
    """Client-side behavioural events (whitelisted types only)."""
    rate_limiter.hit(f"events:{principal.user_id if principal else body.session_key}", 120)
    AnalyticsService(db).record(body, principal)
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.get("/seller/overview", response_model=SellerOverview)
def seller_overview(principal: SellerPrincipal, db: DbSession, days: Days = 30) -> SellerOverview:
    principal.require(P.ANALYTICS_READ_OWN)
    assert principal.seller_id
    return AnalyticsService(db).seller_overview(principal.seller_id, days)


@router.get("/admin/overview", response_model=AdminOverview)
def admin_overview(_: AdminAnalytics, db: DbSession, days: Days = 30) -> AdminOverview:
    return AnalyticsService(db).admin_overview(days)


@router.get("/admin/agents", response_model=AgentUsage)
def agent_usage(_: Annotated[Principal, Depends(require_permission(P.AGENTS_MONITOR))], db: DbSession,
                days: Days = 30) -> AgentUsage:
    return AnalyticsService(db).agent_usage(days)


@router.get("/admin/search", response_model=SearchAnalytics)
def search_analytics(_: AdminAnalytics, db: DbSession, days: Days = 30) -> SearchAnalytics:
    return AnalyticsService(db).search_analytics(days)
