"""Product reviews and aggregated ratings."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPkMixin, str_enum
from app.models.enums import ReviewStatus

if TYPE_CHECKING:
    from app.models.identity import User


class Review(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("product_id", "user_id", name="uq_reviews_product_user"),
        CheckConstraint("rating BETWEEN 1 AND 5", name="rating_range"),
        Index("ix_reviews_product_status", "product_id", "status"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"))
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ReviewStatus] = mapped_column(
        str_enum(ReviewStatus), default=ReviewStatus.PENDING, server_default=ReviewStatus.PENDING.value
    )
    is_verified_purchase: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    helpful_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    moderation_reason: Mapped[str | None] = mapped_column(String(255))
    moderated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    moderated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    author: Mapped[User] = relationship(foreign_keys=[user_id], lazy="joined")


class Rating(Base):
    """Aggregated rating per product (maintained by ReviewService on moderation changes)."""

    __tablename__ = "ratings"

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)
    average: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=0, server_default="0")
    count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    distribution: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
