"""Analytics events, search history, recommendations and forecast results."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Money, UUIDPkMixin, str_enum
from app.models.enums import ForecastStatus


class AnalyticsEvent(UUIDPkMixin, Base):
    __tablename__ = "analytics_events"
    __table_args__ = (
        Index("ix_analytics_events_type_created", "event_type", "created_at"),
        Index("ix_analytics_events_product_type", "product_id", "event_type"),
        Index("ix_analytics_events_seller_created", "seller_id", "created_at"),
        Index("ix_analytics_events_user_created", "user_id", "created_at"),
    )

    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    session_key: Mapped[str | None] = mapped_column(String(64))
    product_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"))
    seller_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("seller_profiles.id", ondelete="SET NULL"))
    category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"))
    value: Mapped[Decimal | None] = mapped_column(Money)
    properties: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SearchHistory(UUIDPkMixin, Base):
    __tablename__ = "search_history"
    __table_args__ = (Index("ix_search_history_created", "created_at"),)

    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    query: Mapped[str] = mapped_column(String(300), nullable=False)
    filters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(String(16), default="web", server_default="web")  # web | nova
    result_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Recommendation(UUIDPkMixin, Base):
    """Recommendations that were served (for analytics, CTR and offline evaluation)."""

    __tablename__ = "recommendations"
    __table_args__ = (Index("ix_recommendations_user_created", "user_id", "created_at"),)

    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    context_product_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    recommended_product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    strategy: Mapped[str] = mapped_column(String(32), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ForecastResult(UUIDPkMixin, Base):
    __tablename__ = "forecast_results"
    __table_args__ = (Index("ix_forecast_results_target_entity", "target", "entity_id", "created_at"),)

    target: Mapped[str] = mapped_column(String(32), nullable=False)  # sales|revenue|product_demand|category_demand
    entity_id: Mapped[uuid.UUID | None] = mapped_column()  # product/category id when relevant
    seller_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("seller_profiles.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model_name: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[ForecastStatus] = mapped_column(str_enum(ForecastStatus), nullable=False)
    frequency: Mapped[str] = mapped_column(String(8), default="D", server_default="D")
    horizon: Mapped[int] = mapped_column(Integer, nullable=False)
    history_start: Mapped[date | None] = mapped_column(Date)
    history_end: Mapped[date | None] = mapped_column(Date)
    history_points: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    points: Mapped[list[Any]] = mapped_column(JSONB, default=list, server_default="[]")
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    error: Mapped[str | None] = mapped_column(Text)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
