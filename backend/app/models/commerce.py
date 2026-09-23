"""Carts, wishlists, orders, payments, applied discounts."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Money, TimestampMixin, UUIDPkMixin, str_enum
from app.models.enums import DiscountSource, OrderStatus, PaymentStatus

if TYPE_CHECKING:
    from app.models.catalog import Product


class Cart(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "carts"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    coupon_code: Mapped[str | None] = mapped_column(String(40))

    items: Mapped[list[CartItem]] = relationship(
        back_populates="cart", cascade="all, delete-orphan", order_by="CartItem.created_at", lazy="selectin"
    )


class CartItem(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "cart_items"
    __table_args__ = (
        UniqueConstraint(
            "cart_id", "product_id", "variant_id", "bundle_id",
            name="uq_cart_items_line", postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint("quantity > 0 AND quantity <= 99", name="quantity_range"),
    )

    cart_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("carts.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    variant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("product_variants.id", ondelete="CASCADE"))
    bundle_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bundles.id", ondelete="SET NULL"))
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    cart: Mapped[Cart] = relationship(back_populates="items")
    product: Mapped[Product] = relationship(lazy="joined")


class Wishlist(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "wishlists"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    items: Mapped[list[WishlistItem]] = relationship(
        back_populates="wishlist", cascade="all, delete-orphan", lazy="selectin"
    )


class WishlistItem(UUIDPkMixin, Base):
    __tablename__ = "wishlist_items"
    __table_args__ = (UniqueConstraint("wishlist_id", "product_id", name="uq_wishlist_items_product"),)

    wishlist_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("wishlists.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    wishlist: Mapped[Wishlist] = relationship(back_populates="items")
    product: Mapped[Product] = relationship(lazy="joined")


class Order(UUIDPkMixin, TimestampMixin, Base):
    """One order per seller; orders from the same checkout share `checkout_group_id`."""

    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_seller_status", "seller_id", "status"),
        Index("ix_orders_buyer_placed", "buyer_id", "placed_at"),
        Index("ix_orders_placed_at", "placed_at"),
    )

    order_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    checkout_group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    buyer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    seller_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("seller_profiles.id", ondelete="RESTRICT"))
    status: Mapped[OrderStatus] = mapped_column(
        str_enum(OrderStatus), default=OrderStatus.PENDING, server_default=OrderStatus.PENDING.value
    )
    currency: Mapped[str] = mapped_column(String(3), default="USD", server_default="USD")
    subtotal: Mapped[Decimal] = mapped_column(Money, nullable=False)
    discount_total: Mapped[Decimal] = mapped_column(Money, default=0, server_default="0")
    tax_total: Mapped[Decimal] = mapped_column(Money, default=0, server_default="0")
    shipping_total: Mapped[Decimal] = mapped_column(Money, default=0, server_default="0")
    total: Mapped[Decimal] = mapped_column(Money, nullable=False)
    shipping_address: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    tracking_number: Mapped[str | None] = mapped_column(String(64))
    notes: Mapped[str | None] = mapped_column(Text)
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    items: Mapped[list[OrderItem]] = relationship(back_populates="order", cascade="all, delete-orphan", lazy="selectin")
    payments: Mapped[list[Payment]] = relationship(back_populates="order", cascade="all, delete-orphan", lazy="selectin")
    discounts: Mapped[list[Discount]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    status_events: Mapped[list[OrderStatusEvent]] = relationship(
        cascade="all, delete-orphan", order_by="OrderStatusEvent.created_at", lazy="selectin"
    )


class OrderItem(UUIDPkMixin, Base):
    __tablename__ = "order_items"
    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)

    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), index=True)
    variant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("product_variants.id", ondelete="SET NULL"))
    bundle_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bundles.id", ondelete="SET NULL"))
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)  # snapshot
    sku: Mapped[str] = mapped_column(String(64), nullable=False)  # snapshot
    unit_price: Mapped[Decimal] = mapped_column(Money, nullable=False)  # price before discounts
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Money, default=0, server_default="0")
    line_total: Mapped[Decimal] = mapped_column(Money, nullable=False)

    order: Mapped[Order] = relationship(back_populates="items")


class OrderStatusEvent(UUIDPkMixin, Base):
    __tablename__ = "order_status_events"

    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    note: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Payment(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "payments"

    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_reference: Mapped[str | None] = mapped_column(String(128), index=True)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(str_enum(PaymentStatus), nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(String(255))
    provider_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")

    order: Mapped[Order] = relationship(back_populates="payments")


class Discount(UUIDPkMixin, Base):
    """A discount that was actually applied to an order (audit trail of pricing)."""

    __tablename__ = "discounts"

    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    order_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("order_items.id", ondelete="CASCADE"))
    source: Mapped[DiscountSource] = mapped_column(str_enum(DiscountSource), nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
