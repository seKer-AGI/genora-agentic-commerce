"""Compatible accessories for a product: complementary categories + explicit compatibility attributes."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Category, Product
from app.services.catalog_service import CategoryService, public_product_filter
from app.services.recommendation_service import RecommendationService

# Marketplace merchandising configuration: which categories complement which.
COMPLEMENTS: dict[str, list[str]] = {
    "cameras": ["camera-accessories"],
    "laptops": ["computer-accessories", "bags", "audio"],
    "smartphones": ["audio", "wearables"],
    "running-shoes": ["wearables", "fitness", "outerwear"],
    "fitness": ["wearables", "running-shoes"],
    "camping": ["bags", "outerwear"],
    "kitchen-appliances": ["kitchen-appliances"],
    "furniture": ["computer-accessories", "furniture"],
    "audio": ["smartphones"],
    "beauty": ["beauty"],
}
# Keyword a target product category is known by in `compatible_with` attributes.
CATEGORY_KEYWORD = {"cameras": "camera", "laptops": "laptop", "smartphones": "phone"}


@dataclass
class AccessoryMatch:
    product: Product
    evidence: str | None
    score: float


class AccessoryService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def find(self, product: Product, limit: int = 6, max_price: float | None = None) -> tuple[list[AccessoryMatch], list[str]]:
        cat = product.category
        slug = cat.slug if cat else None
        target_slugs = COMPLEMENTS.get(slug or "", [])
        if not target_slugs and cat and cat.parent_id:
            parent = self.db.get(Category, cat.parent_id)
            target_slugs = COMPLEMENTS.get(parent.slug if parent else "", [])
        cats = CategoryService(self.db)
        cat_ids: list[uuid.UUID] = []
        for s in target_slugs:
            try:
                cat_ids += cats.descendants(cats.get(s).id)
            except Exception:  # noqa: BLE001 - missing category in a customised catalog
                continue
        if not cat_ids:
            return [], target_slugs
        stmt = public_product_filter(select(Product)).where(Product.category_id.in_(cat_ids), Product.id != product.id)
        if max_price is not None:
            stmt = stmt.where(Product.price <= max_price)
        candidates = list(self.db.scalars(stmt).unique())
        also = RecommendationService(self.db).also_bought_scores([product.id]).scores
        mount = (product.attributes or {}).get("mount")
        keyword = CATEGORY_KEYWORD.get(slug or "")
        matches: list[AccessoryMatch] = []
        for c in candidates:
            attrs = c.attributes or {}
            evidence = None
            score = 0.0
            mounts = attrs.get("compatible_mounts")
            if mounts:
                if not mount or mount not in mounts:
                    continue  # explicitly incompatible
                evidence, score = f"fits {mount}", 3.0
            compat = attrs.get("compatible_with")
            if compat and keyword:
                if keyword in compat:
                    evidence, score = evidence or f"works with any {keyword}", max(score, 2.0)
                elif not mounts:
                    continue
            if c.id in also:
                score += 1.0 + min(also[c.id], 5) / 5
                evidence = evidence or "frequently bought together"
            score += min(c.sold_count, 50) / 100 + float(c.rating_avg) / 10
            if product.effective_list_price and c.effective_list_price > product.effective_list_price:
                score -= 1.0  # accessories should usually cost less than the main product
            matches.append(AccessoryMatch(c, evidence, score))
        matches.sort(key=lambda m: m.score, reverse=True)
        return matches[:limit], target_slugs
