"""Recommendation engine composed of independent strategies.

Strategies
----------
* popular      — units sold in the last N days, damped by rating (Bayesian average)
* similar      — nearest neighbours in embedding space, boosted when in the same category
* also_bought  — item-to-item co-purchase counts ("customers who bought X also bought Y")
* category     — best sellers within a category subtree
* semantic     — vector search from free text
* for_you      — blends category affinity (views/purchases/wishlist), co-purchase and recent-search semantics
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta

from pydantic import BaseModel
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.core.security import utcnow
from app.models.analytics import AnalyticsEvent, Recommendation, SearchHistory
from app.models.catalog import Product
from app.models.commerce import Order, OrderItem, Wishlist, WishlistItem
from app.models.enums import OrderStatus
from app.schemas.catalog import ProductCard
from app.services.ai_runtime import get_embedding_provider
from app.services.catalog_service import CategoryService, ProductService, product_card, public_product_filter
from app.services.pricing import PricingEngine
from app.services.vector_store import PgVectorProductStore

EXCLUDED = (OrderStatus.CANCELLED, OrderStatus.REFUNDED)


class RecommendationResult(BaseModel):
    strategy: str
    items: list[ProductCard]
    reasons: dict[str, str] = {}


@dataclass
class Scored:
    scores: dict[uuid.UUID, float] = field(default_factory=lambda: defaultdict(float))
    reasons: dict[uuid.UUID, str] = field(default_factory=dict)

    def add(self, pid: uuid.UUID, score: float, reason: str) -> None:
        self.scores[pid] += score
        self.reasons.setdefault(pid, reason)

    def top(self, n: int, exclude: set[uuid.UUID] = frozenset()) -> list[uuid.UUID]:  # type: ignore[assignment]
        return [pid for pid, _ in sorted(self.scores.items(), key=lambda kv: kv[1], reverse=True) if pid not in exclude][:n]


class RecommendationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.products = ProductService(db)

    def _result(self, strategy: str, ids: list[uuid.UUID], reasons: dict[uuid.UUID, str] | None = None
                ) -> RecommendationResult:
        engine = PricingEngine(self.db)
        items = [product_card(p, engine) for p in self.products.get_many(ids)]
        return RecommendationResult(strategy=strategy, items=items,
                                    reasons={str(k): v for k, v in (reasons or {}).items() if k in set(ids)})

    # ------------------------------------------------------------ strategies
    def popular_scores(self, days: int = 30, category_ids: list[uuid.UUID] | None = None, limit: int = 50) -> Scored:
        since = utcnow() - timedelta(days=days)
        stmt = (
            public_product_filter(select(Product.id, func.coalesce(func.sum(OrderItem.quantity), 0), Product.rating_avg,
                                         Product.rating_count))
            .outerjoin(OrderItem, OrderItem.product_id == Product.id)
            .outerjoin(Order, (Order.id == OrderItem.order_id) & (Order.placed_at >= since) & Order.status.not_in(EXCLUDED))
            .group_by(Product.id).order_by(func.coalesce(func.sum(OrderItem.quantity), 0).desc()).limit(limit)
        )
        if category_ids:
            stmt = stmt.where(Product.category_id.in_(category_ids))
        s = Scored()
        for pid, units, avg, count in self.db.execute(stmt).all():
            bayes = (float(avg) * count + 4.0 * 5) / (count + 5)  # prior of 4.0 with weight 5
            s.add(pid, float(units) * (bayes / 5), "Popular right now")
        return s

    def popular(self, limit: int = 12, days: int = 30) -> RecommendationResult:
        s = self.popular_scores(days)
        return self._result("popular", s.top(limit), s.reasons)

    def category(self, category: str, limit: int = 12) -> RecommendationResult:
        svc = CategoryService(self.db)
        cat = svc.get(category)
        s = self.popular_scores(90, svc.descendants(cat.id))
        return self._result("category", s.top(limit), s.reasons)

    def similar_scores(self, product: Product, k: int = 20) -> Scored:
        s = Scored()
        if product.embedding is None:
            return s
        hits = PgVectorProductStore(self.db).nearest(
            list(product.embedding), k + 1, base_query=public_product_filter(select(Product.id)), exclude=[product.id]
        )
        cats = dict(self.db.execute(select(Product.id, Product.category_id).where(
            Product.id.in_([h.id for h in hits]))).tuples().all())
        for h in hits:
            same = cats.get(h.id) == product.category_id
            s.add(h.id, h.similarity + (0.15 if same else 0.0), f"Similar to {product.name}")
        return s

    def similar(self, product_id: uuid.UUID, limit: int = 8) -> RecommendationResult:
        p = self.db.get(Product, product_id)
        if p is None:
            return RecommendationResult(strategy="similar", items=[])
        s = self.similar_scores(p, limit * 2)
        return self._result("similar", s.top(limit, {product_id}), s.reasons)

    def also_bought_scores(self, product_ids: list[uuid.UUID], limit: int = 30) -> Scored:
        s = Scored()
        if not product_ids:
            return s
        buyers = select(distinct(Order.buyer_id)).join(OrderItem, OrderItem.order_id == Order.id).where(
            OrderItem.product_id.in_(product_ids), Order.status.not_in(EXCLUDED))
        rows = self.db.execute(
            select(OrderItem.product_id, func.count(distinct(Order.buyer_id)))
            .join(Order, Order.id == OrderItem.order_id)
            .where(Order.buyer_id.in_(buyers), OrderItem.product_id.not_in(product_ids), Order.status.not_in(EXCLUDED))
            .group_by(OrderItem.product_id).order_by(func.count(distinct(Order.buyer_id)).desc()).limit(limit)
        ).all()
        for pid, n in rows:
            s.add(pid, float(n), "Customers who bought this also bought")
        return s

    def also_bought(self, product_id: uuid.UUID, limit: int = 8) -> RecommendationResult:
        s = self.also_bought_scores([product_id])
        return self._result("also_bought", s.top(limit), s.reasons)

    def semantic(self, text: str, limit: int = 8) -> RecommendationResult:
        vec = get_embedding_provider().embed_one(text)
        hits = PgVectorProductStore(self.db).nearest(vec, limit, base_query=public_product_filter(select(Product.id)))
        return self._result("semantic", [h.id for h in hits], {h.id: f"Matches '{text[:40]}'" for h in hits})

    # ------------------------------------------------------------ personalised
    def for_user(self, user_id: uuid.UUID, limit: int = 12, record: bool = True) -> RecommendationResult:
        since = utcnow() - timedelta(days=90)
        purchased = set(self.db.scalars(
            select(distinct(OrderItem.product_id)).join(Order, Order.id == OrderItem.order_id)
            .where(Order.buyer_id == user_id, Order.status.not_in(EXCLUDED))))
        viewed = list(self.db.scalars(
            select(AnalyticsEvent.product_id).where(AnalyticsEvent.user_id == user_id, AnalyticsEvent.product_id.is_not(None),
                                                    AnalyticsEvent.created_at >= since)
            .order_by(AnalyticsEvent.created_at.desc()).limit(50)))
        wished = list(self.db.scalars(select(WishlistItem.product_id).join(Wishlist).where(Wishlist.user_id == user_id)))
        affinity: dict[uuid.UUID, float] = defaultdict(float)
        for pid, weight in [*((p, 3.0) for p in purchased), *((p, 1.0) for p in viewed), *((p, 2.0) for p in wished)]:
            cat = self.db.scalar(select(Product.category_id).where(Product.id == pid))
            if cat:
                affinity[cat] += weight
        blended = Scored()
        if affinity:
            top_cats = sorted(affinity, key=lambda c: affinity[c], reverse=True)[:3]
            pop = self.popular_scores(90, top_cats)
            mx = max(pop.scores.values(), default=1.0) or 1.0
            for pid, sc in pop.scores.items():
                blended.add(pid, 0.5 * sc / mx, "Based on categories you like")
        co = self.also_bought_scores(list(purchased)[:20])
        mx = max(co.scores.values(), default=1.0) or 1.0
        for pid, sc in co.scores.items():
            blended.add(pid, 0.35 * sc / mx, "Customers with similar purchases bought this")
        queries = list(self.db.scalars(select(SearchHistory.query).where(SearchHistory.user_id == user_id)
                                       .order_by(SearchHistory.created_at.desc()).limit(5)))
        if queries:
            vec = get_embedding_provider().embed_one(" ".join(queries))
            for h in PgVectorProductStore(self.db).nearest(vec, 15, base_query=public_product_filter(select(Product.id))):
                blended.add(h.id, 0.3 * max(h.similarity, 0), f"Related to your search '{queries[0][:30]}'")
        ids = blended.top(limit, purchased)
        strategy = "for_you"
        if len(ids) < limit:
            pop = self.popular_scores(30)
            for pid in pop.top(limit * 2, purchased | set(ids)):
                if len(ids) >= limit:
                    break
                ids.append(pid)
                blended.reasons.setdefault(pid, "Popular right now")
            if not affinity and not queries:
                strategy = "popular_fallback"
        if record and ids:
            for rank, pid in enumerate(ids):
                self.db.add(Recommendation(user_id=user_id, recommended_product_id=pid, strategy=strategy,
                                           score=round(blended.scores.get(pid, 0.0), 4), rank=rank))
            self.db.commit()
        return self._result(strategy, ids, blended.reasons)
