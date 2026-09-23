"""/api/v1/forecasting — providers, forecast jobs and stored results."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter

from app.api.deps import CurrentPrincipal, DbSession
from app.services.forecasting_service import ForecastingService, ForecastOut, ForecastRequest

router = APIRouter(prefix="/forecasting", tags=["forecasting"])


@router.get("/providers")
def providers(principal: CurrentPrincipal, db: DbSession) -> list[dict[str, Any]]:
    """Registered forecasting providers and whether each is actually available in this deployment."""
    return ForecastingService(db).providers()


@router.post("/run", response_model=ForecastOut)
def run(body: ForecastRequest, principal: CurrentPrincipal, db: DbSession) -> ForecastOut:
    """Forecast sales, revenue, product demand or category demand from historical order data.

    Sellers forecast their own store; admins may use `scope=marketplace`.
    """
    return ForecastingService(db).run(body, principal)


@router.get("/results", response_model=list[ForecastOut])
def results(principal: CurrentPrincipal, db: DbSession, target: str | None = None) -> list[ForecastOut]:
    return ForecastingService(db).list(principal, target)


@router.get("/results/{forecast_id}", response_model=ForecastOut)
def result(forecast_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> ForecastOut:
    return ForecastingService(db).get(forecast_id, principal)
