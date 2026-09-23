"""Offers, coupons and bundles."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

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
)
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Money, SoftDeleteMixin, TimestampMixin, UUIDPkMixin, str_enum
from app.models.enums import DiscountType

if TYPE_CHECKING:
    from app.models.catalog import Product

_VALUE_CHECK = "(discount_type = 'percentage' AND value > 0 AND value <= 90) OR (discount_type = 'fixed' AND value > 0)"


class Offer(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Automatically applied promotion.

    Scope is determined by which target is set: product → that product; category → products in it;
    neither → every product of the seller (or the whole marketplace when `seller_id` is NULL).
    """

    __tablename__ = "offers"
    __table_args__ = (
        CheckConstraint(_VALUE_CHECK, name="value_valid"),
        CheckConstraint("ends_at IS NULL OR starts_at IS NULL OR ends_at > starts_at", name="window_valid"),
        Index("ix_offers_active_window", "is_active", "starts_at", "ends_at"),
    )

    seller_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("seller_profiles.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    discount_type: Mapped[DiscountType] = mapped_column(str_enum(DiscountType), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    min_quantity: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class Coupon(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "coupons"
    __table_args__ = (CheckConstraint(_VALUE_CHECK, name="value_valid"),)

    code: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    seller_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("seller_profiles.id", ondelete="CASCADE"))
    description: Mapped[str | None] = mapped_column(String(255))
    discount_type: Mapped[DiscountType] = mapped_column(str_enum(DiscountType), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    min_subtotal: Mapped[Decimal] = mapped_column(Money, default=0, server_default="0")
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    usage_limit: Mapped[int | None] = mapped_column(Integer)
    per_user_limit: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    used_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Bundle(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "bundles"
    __table_args__ = (CheckConstraint(_VALUE_CHECK, name="value_valid"),)

    seller_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("seller_profiles.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(180), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    discount_type: Mapped[DiscountType] = mapped_column(str_enum(DiscountType), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    items: Mapped[list[BundleItem]] = relationship(
        back_populates="bundle", cascade="all, delete-orphan", lazy="selectin"
    )


class BundleItem(UUIDPkMixin, Base):
    __tablename__ = "bundle_items"
    __table_args__ = (
        UniqueConstraint("bundle_id", "product_id", name="uq_bundle_items_product"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
    )

    bundle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bundles.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    bundle: Mapped[Bundle] = relationship(back_populates="items")
    product: Mapped[Product] = relationship(lazy="joined")
