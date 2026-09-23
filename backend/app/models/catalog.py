"""Catalog: categories, products, images, variants, inventory, negotiation rules."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Computed,
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
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Money, SoftDeleteMixin, TimestampMixin, UUIDPkMixin, str_enum
from app.models.enums import NegotiationStatus, ProductStatus

if TYPE_CHECKING:
    from app.models.identity import SellerProfile

# Fixed by the migration; changing it requires a new migration + re-embedding.
EMBEDDING_DIM = 384

SEARCH_VECTOR_SQL = (
    "setweight(to_tsvector('english', coalesce(name, '')), 'A') || "
    "setweight(to_tsvector('english', coalesce(brand, '')), 'A') || "
    "setweight(to_tsvector('english', coalesce(keywords, '')), 'B') || "
    "setweight(to_tsvector('english', coalesce(description, '')), 'C')"
)


class Category(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "categories"

    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    icon: Mapped[str | None] = mapped_column(String(48))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    parent: Mapped[Category | None] = relationship(remote_side="Category.id", back_populates="children")
    children: Mapped[list[Category]] = relationship(back_populates="parent")


class Product(UUIDPkMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("seller_id", "sku", name="uq_products_seller_sku"),
        CheckConstraint("price >= 0", name="price_non_negative"),
        CheckConstraint("sale_price IS NULL OR (sale_price >= 0 AND sale_price <= price)", name="sale_price_valid"),
        Index("ix_products_search_vector", "search_vector", postgresql_using="gin"),
        Index("ix_products_name_trgm", "name", postgresql_using="gin", postgresql_ops={"name": "gin_trgm_ops"}),
        Index("ix_products_tags", "tags", postgresql_using="gin"),
        Index("ix_products_status_category", "status", "category_id"),
        Index(
            "ix_products_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    seller_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("seller_profiles.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(240), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    seo_description: Mapped[str | None] = mapped_column(String(320))
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(80), index=True)
    price: Mapped[Decimal] = mapped_column(Money, nullable=False)
    sale_price: Mapped[Decimal | None] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3), default="USD", server_default="USD")
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(48)), default=list, server_default="{}")
    keywords: Mapped[str | None] = mapped_column(Text)  # derived: tags + attribute values + category
    status: Mapped[ProductStatus] = mapped_column(
        str_enum(ProductStatus), default=ProductStatus.DRAFT, server_default=ProductStatus.DRAFT.value
    )
    rating_avg: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=0, server_default="0")
    rating_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    sold_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    search_vector: Mapped[Any] = mapped_column(TSVECTOR, Computed(SEARCH_VECTOR_SQL, persisted=True))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    embedding_model: Mapped[str | None] = mapped_column(String(80))

    seller: Mapped[SellerProfile] = relationship(back_populates="products", lazy="joined")
    category: Mapped[Category | None] = relationship(lazy="joined")
    images: Mapped[list[ProductImage]] = relationship(
        back_populates="product", order_by="ProductImage.sort_order", cascade="all, delete-orphan", lazy="selectin"
    )
    variants: Mapped[list[ProductVariant]] = relationship(
        back_populates="product", cascade="all, delete-orphan", lazy="selectin"
    )
    inventory: Mapped[list[Inventory]] = relationship(
        back_populates="product", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def effective_list_price(self) -> Decimal:
        return self.sale_price if self.sale_price is not None else self.price

    @property
    def stock(self) -> int:
        return sum(max(i.quantity_on_hand - i.quantity_reserved, 0) for i in self.inventory)

    @property
    def primary_image_url(self) -> str | None:
        if not self.images:
            return None
        primary = next((i for i in self.images if i.is_primary), self.images[0])
        return primary.url


class ProductImage(UUIDPkMixin, Base):
    __tablename__ = "product_images"

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(String(512), nullable=False)
    alt_text: Mapped[str | None] = mapped_column(String(200))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    product: Mapped[Product] = relationship(back_populates="images")


class ProductVariant(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "product_variants"
    __table_args__ = (UniqueConstraint("product_id", "sku", name="uq_product_variants_product_sku"),)

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    price_override: Mapped[Decimal | None] = mapped_column(Money)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    product: Mapped[Product] = relationship(back_populates="variants")


class Inventory(UUIDPkMixin, Base):
    __tablename__ = "inventory"
    __table_args__ = (
        UniqueConstraint("product_id", "variant_id", name="uq_inventory_product_variant", postgresql_nulls_not_distinct=True),
        CheckConstraint("quantity_on_hand >= 0", name="on_hand_non_negative"),
        CheckConstraint("quantity_reserved >= 0", name="reserved_non_negative"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    variant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("product_variants.id", ondelete="CASCADE"))
    quantity_on_hand: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    quantity_reserved: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    low_stock_threshold: Mapped[int] = mapped_column(Integer, default=5, server_default="5")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    product: Mapped[Product] = relationship(back_populates="inventory")

    @property
    def available(self) -> int:
        return max(self.quantity_on_hand - self.quantity_reserved, 0)


class NegotiationRule(UUIDPkMixin, TimestampMixin, Base):
    """Seller-defined negotiation limits. `product_id IS NULL` = seller-wide default."""

    __tablename__ = "negotiation_rules"
    __table_args__ = (
        UniqueConstraint("seller_id", "product_id", name="uq_negotiation_rules_seller_product", postgresql_nulls_not_distinct=True),
        CheckConstraint("max_discount_percent >= 0 AND max_discount_percent <= 90", name="max_discount_range"),
        CheckConstraint("auto_accept_percent >= 0 AND auto_accept_percent <= max_discount_percent", name="auto_accept_range"),
    )

    seller_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("seller_profiles.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    max_discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    auto_accept_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)


class Negotiation(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "negotiations"
    __table_args__ = (Index("ix_negotiations_buyer_product", "buyer_id", "product_id"),)

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    buyer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    seller_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("seller_profiles.id", ondelete="CASCADE"), index=True)
    list_price: Mapped[Decimal] = mapped_column(Money, nullable=False)
    offered_price: Mapped[Decimal] = mapped_column(Money, nullable=False)
    counter_price: Mapped[Decimal | None] = mapped_column(Money)
    agreed_price: Mapped[Decimal | None] = mapped_column(Money)
    status: Mapped[NegotiationStatus] = mapped_column(str_enum(NegotiationStatus), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
