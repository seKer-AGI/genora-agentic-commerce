"""Forecasting jobs: builds history from real order data, runs a provider and persists the result."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import date
from functools import lru_cache
from typing import Any, Literal

from genora.errors import ProviderUnavailableError
from genora.forecasting.base import TimeSeries
from genora.forecasting.providers import ForecastingRegistry
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import NotFoundError, PermissionDenied, ValidationFailed
from app.core.logging import log_event
from app.core.principal import Principal
from app.core.rbac import P
from app.models.analytics import ForecastResult
from app.models.catalog import Category, Product
from app.models.enums import ForecastStatus
from app.services.analytics_service import AnalyticsService

logger = logging.getLogger("app.forecasting")
Target = Literal["sales", "revenue", "product_demand", "category_demand"]


class ForecastRequest(BaseModel):
    target: Target = "revenue"
    entity_id: uuid.UUID | None = None
    horizon: int = Field(14, ge=1, le=365)
    provider: str | None = None
    history_days: int = Field(180, ge=21, le=730)
    scope: Literal["seller", "marketplace"] = "seller"


class ForecastOut(BaseModel):
    id: uuid.UUID | None
    target: str
    entity_id: uuid.UUID | None
    provider: str
    model_name: str
    status: str
    horizon: int
    frequency: str
    interval: float | None
    history: list[dict[str, Any]]
    points: list[dict[str, Any]]
    metrics: dict[str, Any]
    params: dict[str, Any] = {}
    error: str | None
    created_at: str | None = None


@lru_cache
def get_forecasting_registry() -> ForecastingRegistry:
    return ForecastingRegistry()


class ForecastingService:
    def __init__(self, db: Session, registry: ForecastingRegistry | None = None) -> None:
        self.db = db
        self.registry = registry or get_forecasting_registry()
        self.settings = get_settings()

    def providers(self) -> list[dict[str, Any]]:
        return self.registry.describe()

    def _authorize(self, req: ForecastRequest, principal: Principal) -> uuid.UUID | None:
        """Returns the seller scope (None = whole marketplace, admins only)."""
        if req.scope == "marketplace" or principal.seller_id is None:
            principal.require(P.FORECAST_RUN_ALL)
            seller_id = None
        else:
            principal.require(P.FORECAST_RUN_OWN, P.FORECAST_RUN_ALL)
            seller_id = principal.seller_id
        if req.target in ("product_demand", "category_demand") and req.entity_id is None:
            raise ValidationFailed("entity_id is required for demand forecasts", code="ENTITY_REQUIRED")
        if req.target == "product_demand":
            p = self.db.get(Product, req.entity_id)
            if p is None or (seller_id and p.seller_id != seller_id and not principal.has(P.FORECAST_RUN_ALL)):
                raise NotFoundError("Product was not found", code="PRODUCT_NOT_FOUND")
        if req.target == "category_demand" and self.db.get(Category, req.entity_id) is None:
            raise NotFoundError("Category was not found", code="CATEGORY_NOT_FOUND")
        return seller_id

    def run(self, req: ForecastRequest, principal: Principal) -> ForecastOut:
        if req.horizon > self.settings.forecast_max_horizon_days:
            raise ValidationFailed(f"horizon must be <= {self.settings.forecast_max_horizon_days} days",
                                   code="HORIZON_TOO_LONG")
        seller_id = self._authorize(req, principal)
        provider = req.provider or self.settings.forecast_default_provider
        history = AnalyticsService(self.db).history(req.target, days=req.history_days, seller_id=seller_id,
                                                    entity_id=req.entity_id)
        # drop the current (incomplete) day
        history = history[:-1] if len(history) > 1 else history
        series = TimeSeries([d for d, _ in history], [v for _, v in history])
        hist_out = [{"date": d.isoformat(), "value": round(v, 2)} for d, v in history]
        started = time.perf_counter()
        row = ForecastResult(target=req.target, entity_id=req.entity_id, seller_id=seller_id, provider=provider,
                             horizon=req.horizon, frequency="D", requested_by=principal.user_id,
                             history_start=history[0][0] if history else None,
                             history_end=history[-1][0] if history else None, history_points=len(history))
        try:
            if sum(1 for _, v in history if v) < 7:
                raise ValueError("not enough non-zero history to forecast (need at least 7 active days)")
            fc = self.registry.run(provider, series, req.horizon)
            row.model_name, row.status = fc.model_name, ForecastStatus.COMPLETED
            row.points = [p.as_dict() for p in fc.points]
            row.metrics = {**fc.metrics, "interval": fc.interval, "params": fc.params}
            interval, params = fc.interval, fc.params
        except (ProviderUnavailableError, ValueError) as exc:
            row.model_name, row.status = provider, ForecastStatus.FAILED
            row.error = exc.message if isinstance(exc, ProviderUnavailableError) else str(exc)
            row.points, row.metrics = [], {}
            interval, params = None, {}
        self.db.add(row)
        self.db.commit()
        log_event(logger, "forecast_job", target=req.target, provider=provider, status=row.status.value,
                  history_points=len(history), latency_ms=int((time.perf_counter() - started) * 1000))
        return ForecastOut(
            id=row.id, target=row.target, entity_id=row.entity_id, provider=row.provider, model_name=row.model_name,
            status=row.status.value, horizon=row.horizon, frequency=row.frequency, interval=interval,
            history=hist_out[-90:], points=row.points,
            metrics={k: v for k, v in row.metrics.items() if k not in ("params", "interval")}, params=params,
            error=row.error, created_at=row.created_at.isoformat() if row.created_at else None,
        )

    def list(self, principal: Principal, target: str | None = None, limit: int = 20) -> list[ForecastOut]:
        stmt = select(ForecastResult).order_by(ForecastResult.created_at.desc()).limit(limit)
        if not principal.has(P.FORECAST_RUN_ALL):
            if principal.seller_id is None:
                raise PermissionDenied()
            stmt = stmt.where(ForecastResult.seller_id == principal.seller_id)
        if target:
            stmt = stmt.where(ForecastResult.target == target)
        return [self._out(r) for r in self.db.scalars(stmt)]

    def get(self, forecast_id: uuid.UUID, principal: Principal) -> ForecastOut:
        r = self.db.get(ForecastResult, forecast_id)
        if r is None or (not principal.has(P.FORECAST_RUN_ALL) and r.seller_id != principal.seller_id):
            raise NotFoundError("Forecast was not found", code="FORECAST_NOT_FOUND")
        return self._out(r)

    @staticmethod
    def _out(r: ForecastResult) -> ForecastOut:
        return ForecastOut(
            id=r.id, target=r.target, entity_id=r.entity_id, provider=r.provider, model_name=r.model_name,
            status=r.status.value, horizon=r.horizon, frequency=r.frequency, interval=r.metrics.get("interval"),
            history=[], points=r.points, metrics={k: v for k, v in r.metrics.items() if k not in ("params", "interval")},
            params=r.metrics.get("params", {}), error=r.error, created_at=r.created_at.isoformat(),
        )


def _iso(d: date) -> str:
    return d.isoformat()
