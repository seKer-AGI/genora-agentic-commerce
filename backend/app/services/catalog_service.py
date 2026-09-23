"""Categories, products and inventory (with ownership rules)."""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, PermissionDenied, ValidationFailed
from app.core.principal import Principal
from app.core.rbac import P
from app.core.security import utcnow
from app.models.catalog import Category, Inventory, NegotiationRule, Product, ProductImage, ProductVariant
from app.models.enums import ProductStatus, SellerStatus
from app.models.identity import SellerProfile
from app.models.reviews import Rating
from app.schemas.catalog import (
    AppliedOfferOut,
    CategoryCreate,
    CategoryMini,
    CategoryTree,
    CategoryUpdate,
    ImageOut,
    InventoryOut,
    InventoryUpdate,
    ProductCard,
    ProductCreate,
    ProductDetail,
    ProductUpdate,
    SellerMini,
    VariantOut,
)
from app.services.audit import audit
from app.services.catalog_indexing import index_products
from app.services.pricing import PricingEngine


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:200] or "item"


# ============================================================ categories
class CategoryService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def all(self, include_inactive: bool = False) -> list[Category]:
        stmt = select(Category).where(Category.deleted_at.is_(None)).order_by(Category.sort_order, Category.name)
        if not include_inactive:
            stmt = stmt.where(Category.is_active.is_(True))
        return list(self.db.scalars(stmt))

    def descendants(self, category_id: uuid.UUID) -> list[uuid.UUID]:
        children: dict[uuid.UUID | None, list[uuid.UUID]] = {}
        for cid, pid in self.db.execute(select(Category.id, Category.parent_id).where(Category.deleted_at.is_(None))):
            children.setdefault(pid, []).append(cid)
        out, stack = [], [category_id]
        while stack:
            cur = stack.pop()
            if cur in out:
                continue
            out.append(cur)
            stack.extend(children.get(cur, []))
        return out

    def get(self, id_or_slug: str) -> Category:
        stmt = select(Category).where(Category.deleted_at.is_(None))
        try:
            stmt = stmt.where(Category.id == uuid.UUID(id_or_slug))
        except ValueError:
            stmt = stmt.where(Category.slug == id_or_slug)
        cat = self.db.scalar(stmt)
        if cat is None:
            raise NotFoundError("Category was not found", code="CATEGORY_NOT_FOUND")
        return cat

    def tree(self, include_inactive: bool = False) -> list[CategoryTree]:
        cats = self.all(include_inactive)
        direct = dict(
            self.db.execute(
                select(Product.category_id, func.count())
                .where(Product.status == ProductStatus.ACTIVE, Product.deleted_at.is_(None))
                .group_by(Product.category_id)
            ).tuples().all()
        )
        nodes = {c.id: CategoryTree.model_validate(c, from_attributes=True) for c in cats}
        roots: list[CategoryTree] = []
        for c in cats:
            node = nodes[c.id]
            node.product_count = direct.get(c.id, 0)
            if c.parent_id and c.parent_id in nodes:
                nodes[c.parent_id].children.append(node)
            else:
                roots.append(node)

        def total(n: CategoryTree) -> int:
            n.product_count += sum(total(ch) for ch in n.children)
            return n.product_count

        for r in roots:
            total(r)
        return roots

    def create(self, data: CategoryCreate, actor: Principal) -> Category:
        slug = data.slug or slugify(data.name)
        if self.db.scalar(select(Category.id).where(Category.slug == slug)):
            raise ConflictError("Category slug already exists", code="CATEGORY_SLUG_TAKEN")
        if data.parent_id:
            self.get(str(data.parent_id))
        cat = Category(**data.model_dump(exclude={"slug"}), slug=slug)
        self.db.add(cat)
        self.db.flush()
        audit(self.db, actor.user_id, "category.create", "category", cat.id, {"name": cat.name})
        self.db.commit()
        return cat

    def update(self, category_id: str, data: CategoryUpdate, actor: Principal) -> Category:
        cat = self.get(category_id)
        changes = data.model_dump(exclude_unset=True)
        if changes.get("parent_id") and changes["parent_id"] in self.descendants(cat.id):
            raise ValidationFailed("A category cannot be moved under its own descendant", code="CATEGORY_CYCLE")
        for k, v in changes.items():
            setattr(cat, k, v)
        audit(self.db, actor.user_id, "category.update", "category", cat.id, changes)
        self.db.commit()
        return cat

    def delete(self, category_id: str, actor: Principal) -> None:
        cat = self.get(category_id)
        in_use = self.db.scalar(
            select(func.count()).select_from(Product).where(Product.category_id == cat.id, Product.deleted_at.is_(None))
        )
        if in_use:
            raise ConflictError(f"Category has {in_use} product(s); reassign them first", code="CATEGORY_IN_USE")
        cat.deleted_at = utcnow()
        audit(self.db, actor.user_id, "category.delete", "category", cat.id)
        self.db.commit()


# ============================================================ presenters
def _offer_out(offer: Any) -> AppliedOfferOut | None:
    if offer is None:
        return None
    return AppliedOfferOut(id=offer.id, name=offer.name, discount_type=offer.discount_type.value, value=offer.value,
                           ends_at=offer.ends_at, min_quantity=offer.min_quantity)


def product_card(p: Product, engine: PricingEngine, score: float | None = None) -> ProductCard:
    quote = engine.quote(p)
    stock = p.stock
    return ProductCard(
        id=p.id, slug=p.slug, name=p.name, brand=p.brand, price=p.price, sale_price=p.sale_price,
        final_price=quote.final_price, currency=p.currency, rating_avg=p.rating_avg, rating_count=p.rating_count,
        image_url=p.primary_image_url, in_stock=stock > 0, stock=stock, sold_count=p.sold_count,
        seller=SellerMini.model_validate(p.seller), category=CategoryMini.model_validate(p.category) if p.category else None,
        offer=_offer_out(quote.offer), tags=list(p.tags or []), status=p.status.value, score=score,
    )


def product_detail(db: Session, p: Product, engine: PricingEngine) -> ProductDetail:
    card = product_card(p, engine)
    rating = db.get(Rating, p.id)
    low = any(i.quantity_on_hand - i.quantity_reserved <= i.low_stock_threshold for i in p.inventory)
    return ProductDetail(
        **card.model_dump(),
        sku=p.sku, description=p.description, seo_description=p.seo_description, attributes=p.attributes or {},
        images=[ImageOut.model_validate(i) for i in p.images],
        variants=[VariantOut.model_validate(v) for v in p.variants if v.is_active],
        low_stock=low, rating_distribution=(rating.distribution if rating else {}),
        negotiable=is_negotiable(db, p), created_at=p.created_at, updated_at=p.updated_at,
    )


def negotiation_rule_for(db: Session, product: Product) -> NegotiationRule | None:
    rules = db.scalars(
        select(NegotiationRule).where(
            NegotiationRule.seller_id == product.seller_id,
            or_(NegotiationRule.product_id == product.id, NegotiationRule.product_id.is_(None)),
        )
    ).all()
    specific = next((r for r in rules if r.product_id == product.id), None)
    if specific is not None:
        return specific
    default = next((r for r in rules if r.product_id is None), None)
    if default is not None and product.seller.negotiation_enabled:
        return default
    return None


def is_negotiable(db: Session, product: Product) -> bool:
    rule = negotiation_rule_for(db, product)
    return bool(rule and rule.is_enabled and rule.max_discount_percent > 0)


# ============================================================ products
def public_product_filter(stmt: Select[Any]) -> Select[Any]:
    return (
        stmt.join(SellerProfile, SellerProfile.id == Product.seller_id)
        .where(Product.status == ProductStatus.ACTIVE, Product.deleted_at.is_(None))
        .where(SellerProfile.status == SellerStatus.ACTIVE)
    )


class ProductService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- reads -----------------------------------------------------------
    def _lookup(self, id_or_slug: str) -> Product | None:
        stmt = select(Product).where(Product.deleted_at.is_(None))
        try:
            stmt = stmt.where(Product.id == uuid.UUID(id_or_slug))
        except ValueError:
            stmt = stmt.where(Product.slug == id_or_slug)
        return self.db.scalar(stmt)

    def get_visible(self, id_or_slug: str, principal: Principal | None) -> Product:
        """Public products are visible to all; drafts/archived only to their seller or admins."""
        p = self._lookup(id_or_slug)
        if p is None:
            raise NotFoundError("Product was not found", code="PRODUCT_NOT_FOUND")
        public = p.status == ProductStatus.ACTIVE and p.seller.status == SellerStatus.ACTIVE
        if not public and not self._can_manage(p, principal):
            raise NotFoundError("Product was not found", code="PRODUCT_NOT_FOUND")
        return p

    def get_many(self, ids: Sequence[uuid.UUID], public_only: bool = True) -> list[Product]:
        if not ids:
            return []
        stmt = select(Product).where(Product.id.in_(ids))
        if public_only:
            stmt = public_product_filter(stmt)
        found = {p.id: p for p in self.db.scalars(stmt).unique()}
        return [found[i] for i in ids if i in found]

    def list_for_seller(self, seller_id: uuid.UUID, status: str | None, q: str | None, offset: int, limit: int
                        ) -> tuple[list[Product], int]:
        stmt = select(Product).where(Product.seller_id == seller_id, Product.deleted_at.is_(None))
        if status:
            stmt = stmt.where(Product.status == ProductStatus(status))
        if q:
            stmt = stmt.where(or_(Product.name.ilike(f"%{q}%"), Product.sku.ilike(f"%{q}%")))
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        items = list(self.db.scalars(stmt.order_by(Product.updated_at.desc()).offset(offset).limit(limit)).unique())
        return items, total

    def list_all(self, status: str | None, q: str | None, seller_id: uuid.UUID | None, offset: int, limit: int
                 ) -> tuple[list[Product], int]:
        stmt = select(Product).where(Product.deleted_at.is_(None))
        if status:
            stmt = stmt.where(Product.status == ProductStatus(status))
        if seller_id:
            stmt = stmt.where(Product.seller_id == seller_id)
        if q:
            stmt = stmt.where(or_(Product.name.ilike(f"%{q}%"), Product.sku.ilike(f"%{q}%"), Product.brand.ilike(f"%{q}%")))
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        items = list(self.db.scalars(stmt.order_by(Product.created_at.desc()).offset(offset).limit(limit)).unique())
        return items, total

    # --- authorization ----------------------------------------------------
    @staticmethod
    def _can_manage(p: Product, principal: Principal | None) -> bool:
        if principal is None:
            return False
        if principal.has(P.PRODUCTS_MANAGE_ALL):
            return True
        return principal.has(P.PRODUCTS_MANAGE_OWN) and principal.seller_id == p.seller_id

    def get_manageable(self, product_id: uuid.UUID, principal: Principal) -> Product:
        p = self.db.scalar(select(Product).where(Product.id == product_id, Product.deleted_at.is_(None)))
        if p is None:
            raise NotFoundError("Product was not found", code="PRODUCT_NOT_FOUND")
        if not self._can_manage(p, principal):
            # Do not reveal the existence of other sellers' products.
            raise NotFoundError("Product was not found", code="PRODUCT_NOT_FOUND")
        return p

    # --- writes -------------------------------------------------------------
    def _unique_slug(self, name: str) -> str:
        base = slugify(name)
        slug, n = base, 1
        while self.db.scalar(select(Product.id).where(Product.slug == slug)):
            n += 1
            slug = f"{base}-{n}"
        return slug

    def _check_category(self, category_id: uuid.UUID | None) -> Category | None:
        if category_id is None:
            return None
        cat = self.db.scalar(select(Category).where(Category.id == category_id, Category.deleted_at.is_(None)))
        if cat is None:
            raise ValidationFailed("Unknown category", code="CATEGORY_NOT_FOUND")
        return cat

    def create(self, data: ProductCreate, principal: Principal) -> Product:
        principal.require(P.PRODUCTS_MANAGE_OWN)
        seller_id = principal.require_seller()
        if self.db.scalar(select(Product.id).where(Product.seller_id == seller_id, Product.sku == data.sku)):
            raise ConflictError("You already have a product with this SKU", code="SKU_TAKEN")
        cat = self._check_category(data.category_id)
        p = Product(
            seller_id=seller_id, category_id=data.category_id, name=data.name.strip(), slug=self._unique_slug(data.name),
            description=data.description, seo_description=data.seo_description, sku=data.sku, brand=data.brand,
            price=data.price, sale_price=data.sale_price, currency=data.currency, attributes=data.attributes or {},
            tags=data.tags or [], status=ProductStatus(data.status),
            published_at=utcnow() if data.status == "active" else None,
        )
        p.images = [ProductImage(url=u, alt_text=p.name, is_primary=i == 0, sort_order=i)
                    for i, u in enumerate(data.images or [])]
        p.inventory = [Inventory(quantity_on_hand=data.stock, low_stock_threshold=data.low_stock_threshold)]
        for v in data.variants:
            variant = ProductVariant(sku=v.sku, name=v.name, attributes=v.attributes, price_override=v.price_override)
            p.variants.append(variant)
        self.db.add(p)
        self.db.flush()
        for variant, vin in zip(p.variants, data.variants, strict=True):
            self.db.add(Inventory(product_id=p.id, variant_id=variant.id, quantity_on_hand=vin.stock,
                                  low_stock_threshold=data.low_stock_threshold))
        self.db.refresh(p)
        index_products([p], {cat.id: cat.name} if cat else None)
        if not p.images:
            self._generate_art(p)
        audit(self.db, principal.user_id, "product.create", "product", p.id, {"sku": p.sku, "status": p.status.value})
        self.db.commit()
        return p

    def _generate_art(self, p: Product) -> None:
        from app.integrations.storage import get_storage
        from app.services.product_art import render_product_svg

        root = p.category
        while root is not None and root.parent is not None:
            root = root.parent
        url = get_storage().save(f"products/{p.id.hex}.svg",
                                 render_product_svg(p.name, p.brand, root.slug if root else None), "image/svg+xml")
        p.images.append(ProductImage(url=url, alt_text=p.name, is_primary=True, sort_order=0))

    def update(self, product_id: uuid.UUID, data: ProductUpdate, principal: Principal) -> Product:
        p = self.get_manageable(product_id, principal)
        changes = data.model_dump(exclude_unset=True, exclude={"images", "clear_sale_price"})
        if "sku" in changes and changes["sku"] != p.sku and self.db.scalar(
            select(Product.id).where(Product.seller_id == p.seller_id, Product.sku == changes["sku"])
        ):
            raise ConflictError("You already have a product with this SKU", code="SKU_TAKEN")
        if "category_id" in changes:
            self._check_category(changes["category_id"])
        if p.status == ProductStatus.BLOCKED and not principal.has(P.PRODUCTS_MANAGE_ALL):
            raise PermissionDenied("This product was blocked by marketplace moderation", code="PRODUCT_BLOCKED")
        new_price = changes.get("price", p.price)
        new_sale = None if data.clear_sale_price else changes.get("sale_price", p.sale_price)
        if new_sale is not None and new_sale > new_price:
            raise ValidationFailed("sale_price must not exceed price", code="INVALID_SALE_PRICE")
        price_before = (p.price, p.sale_price)
        for k, v in changes.items():
            if k == "status":
                v = ProductStatus(v)
                if v == ProductStatus.ACTIVE and p.published_at is None:
                    p.published_at = utcnow()
            setattr(p, k, v)
        if data.clear_sale_price:
            p.sale_price = None
        if data.images is not None:
            p.images.clear()
            self.db.flush()
            p.images.extend(ProductImage(url=u, alt_text=p.name, is_primary=i == 0, sort_order=i)
                            for i, u in enumerate(data.images))
        self.db.flush()
        self.db.refresh(p)
        index_products([p])
        audit(self.db, principal.user_id, "product.update", "product", p.id,
              {"fields": sorted(changes), "price_before": [str(x) for x in price_before],
               "price_after": [str(p.price), str(p.sale_price)]})
        self.db.commit()
        return p

    def delete(self, product_id: uuid.UUID, principal: Principal) -> None:
        p = self.get_manageable(product_id, principal)
        p.deleted_at = utcnow()
        p.status = ProductStatus.ARCHIVED
        audit(self.db, principal.user_id, "product.delete", "product", p.id, {"sku": p.sku})
        self.db.commit()

    def moderate(self, product_id: uuid.UUID, status: ProductStatus, principal: Principal, reason: str | None) -> Product:
        principal.require(P.PRODUCTS_MANAGE_ALL)
        p = self.get_manageable(product_id, principal)
        p.status = status
        audit(self.db, principal.user_id, "product.moderate", "product", p.id, {"status": status.value, "reason": reason})
        self.db.commit()
        return p


# ============================================================ inventory
class InventoryService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def to_out(p: Product) -> InventoryOut:
        inv = [i for i in p.inventory if i.variant_id is None] or p.inventory
        on_hand = sum(i.quantity_on_hand for i in inv)
        reserved = sum(i.quantity_reserved for i in inv)
        threshold = inv[0].low_stock_threshold if inv else 0
        available = max(on_hand - reserved, 0)
        return InventoryOut(
            product_id=p.id, product_name=p.name, sku=p.sku, status=p.status.value, quantity_on_hand=on_hand,
            quantity_reserved=reserved, available=available, low_stock_threshold=threshold,
            is_low=available <= threshold, sold_count=p.sold_count, image_url=p.primary_image_url,
        )

    def list(self, seller_id: uuid.UUID, low_only: bool = False) -> list[InventoryOut]:
        products = self.db.scalars(
            select(Product).where(Product.seller_id == seller_id, Product.deleted_at.is_(None)).order_by(Product.name)
        ).unique()
        rows = [self.to_out(p) for p in products]
        if low_only:
            rows = [r for r in rows if r.is_low and r.status != ProductStatus.ARCHIVED.value]
            rows.sort(key=lambda r: r.available)
        return rows

    def update(self, product_id: uuid.UUID, data: InventoryUpdate, principal: Principal) -> InventoryOut:
        principal.require(P.INVENTORY_MANAGE_OWN, P.PRODUCTS_MANAGE_ALL)
        p = ProductService(self.db).get_manageable(product_id, principal)
        inv = self.db.scalar(
            select(Inventory).where(Inventory.product_id == p.id, Inventory.variant_id.is_(None)).with_for_update()
        )
        if inv is None:
            inv = Inventory(product_id=p.id, quantity_on_hand=0)
            self.db.add(inv)
        before = inv.quantity_on_hand
        if data.quantity_on_hand is not None:
            inv.quantity_on_hand = data.quantity_on_hand
        if data.adjust_by is not None:
            new = inv.quantity_on_hand + data.adjust_by
            if new < inv.quantity_reserved or new < 0:
                raise ValidationFailed("Stock cannot go below the reserved quantity", code="INVALID_STOCK")
            inv.quantity_on_hand = new
        if data.low_stock_threshold is not None:
            inv.low_stock_threshold = data.low_stock_threshold
        audit(self.db, principal.user_id, "inventory.update", "product", p.id,
              {"before": before, "after": inv.quantity_on_hand})
        self.db.commit()
        self.db.refresh(p)
        return self.to_out(p)
