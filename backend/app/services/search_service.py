"""Hybrid product search: Postgres full-text + trigram (keyword) and pgvector (semantic), fused with RRF."""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, and_, case, func, literal, or_, select
from sqlalchemy.orm import Session

from app.core.principal import Principal
from app.models.analytics import AnalyticsEvent, SearchHistory
from app.models.catalog import Category, Inventory, Product
from app.models.identity import SellerProfile
from app.schemas.search import Facet, SearchFilters, SearchQuery, SearchResponse, SuggestResponse
from app.services.ai_runtime import get_embedding_provider
from app.services.catalog_service import CategoryService, ProductService, product_card, public_product_filter
from app.services.pricing import PricingEngine
from app.services.vector_store import PgVectorProductStore, VectorStore

_WORD = re.compile(r"[A-Za-z0-9]+")
RRF_K = 60
CANDIDATES = 200
# Minimum cosine similarity for vector-only hits to be included in hybrid results.
MIN_VECTOR_SIMILARITY = {"hashing": 0.22, "fastembed": 0.55, "openai_compatible": 0.30}


@dataclass
class RankedIds:
    ids: list[uuid.UUID]
    scores: dict[uuid.UUID, float]
    total: int


class SearchService:
    def __init__(self, db: Session, vector_store: VectorStore | None = None) -> None:
        self.db = db
        self.vectors = vector_store or PgVectorProductStore(db)
        self.embedder = get_embedding_provider()

    # ------------------------------------------------------------ filters
    def filtered(self, f: SearchFilters) -> Select[Any]:
        stmt = public_product_filter(select(Product.id))
        if f.category:
            cat = CategoryService(self.db).get(f.category)
            stmt = stmt.where(Product.category_id.in_(CategoryService(self.db).descendants(cat.id)))
        effective = func.coalesce(Product.sale_price, Product.price)
        if f.min_price is not None:
            stmt = stmt.where(effective >= f.min_price)
        if f.max_price is not None:
            stmt = stmt.where(effective <= f.max_price)
        if f.seller:
            try:
                stmt = stmt.where(Product.seller_id == uuid.UUID(f.seller))
            except ValueError:
                stmt = stmt.where(SellerProfile.slug == f.seller)
        if f.brands:
            stmt = stmt.where(func.lower(Product.brand).in_([b.lower() for b in f.brands]))
        if f.min_rating is not None:
            stmt = stmt.where(Product.rating_avg >= f.min_rating)
        if f.tags:
            stmt = stmt.where(Product.tags.overlap([t.lower() for t in f.tags]))
        if f.in_stock:
            stock = (
                select(func.coalesce(func.sum(Inventory.quantity_on_hand - Inventory.quantity_reserved), 0))
                .where(Inventory.product_id == Product.id)
                .scalar_subquery()
            )
            stmt = stmt.where(stock > 0)
        return stmt

    @staticmethod
    def _order(sort: str) -> list[Any]:
        effective = func.coalesce(Product.sale_price, Product.price)
        return {
            "price_asc": [effective.asc()],
            "price_desc": [effective.desc()],
            "rating": [Product.rating_avg.desc(), Product.rating_count.desc()],
            "newest": [Product.published_at.desc().nullslast()],
        }.get(sort, [Product.sold_count.desc(), Product.rating_avg.desc()])

    # ------------------------------------------------------------ retrieval
    def keyword_ranked(self, base: Select[Any], text: str, limit: int = CANDIDATES) -> list[tuple[uuid.UUID, float]]:
        words = [w.lower() for w in _WORD.findall(text)][:12]
        if not words:
            return []
        or_q = func.to_tsquery("english", " | ".join(words))
        and_q = func.plainto_tsquery("english", " ".join(words))
        sim = func.similarity(Product.name, text)
        score = (
            func.ts_rank_cd(Product.search_vector, or_q, 32)
            + case((Product.search_vector.op("@@")(and_q), literal(1.0)), else_=literal(0.0))
            + sim
        )
        stmt = (
            base.with_only_columns(Product.id, score.label("score"))
            .where(or_(Product.search_vector.op("@@")(or_q), sim > 0.3))
            .order_by(score.desc())
            .limit(limit)
        )
        return [(pid, float(s)) for pid, s in self.db.execute(stmt).all()]

    def vector_ranked(self, base: Select[Any], text: str, limit: int = CANDIDATES, min_similarity: float | None = None
                      ) -> list[tuple[uuid.UUID, float]]:
        vec = self.embedder.embed_one(text)
        hits = self.vectors.nearest(vec, limit, base_query=base)
        threshold = MIN_VECTOR_SIMILARITY.get(self.embedder.name, 0.3) if min_similarity is None else min_similarity
        return [(h.id, h.similarity) for h in hits if h.similarity >= threshold]

    def rank(self, text: str, base: Select[Any], mode: str, semantic_weight: float = 0.5) -> RankedIds:
        kw = self.keyword_ranked(base, text) if mode in ("keyword", "hybrid") else []
        vec = self.vector_ranked(base, text) if mode in ("semantic", "hybrid") else []
        fused: dict[uuid.UUID, float] = {}
        for rank_, (pid, _) in enumerate(kw):
            fused[pid] = fused.get(pid, 0.0) + (1 - semantic_weight) / (RRF_K + rank_ + 1)
        for rank_, (pid, _) in enumerate(vec):
            fused[pid] = fused.get(pid, 0.0) + semantic_weight / (RRF_K + rank_ + 1)
        if mode == "hybrid" and kw:
            # vector-only hits must be meaningfully similar to be included alongside keyword matches
            kw_ids = {pid for pid, _ in kw}
            strong = {pid for pid, s in vec if s >= 0.35 or pid in kw_ids}
            fused = {pid: s for pid, s in fused.items() if pid in kw_ids or pid in strong}
        ordered = sorted(fused, key=lambda i: fused[i], reverse=True)
        top = fused[ordered[0]] if ordered else 1.0
        return RankedIds(ordered, {pid: round(fused[pid] / top, 4) for pid in ordered}, len(ordered))

    # ------------------------------------------------------------ public API
    def search(
        self, params: SearchQuery, principal: Principal | None = None, *, source: str = "web",
        semantic_weight: float = 0.5, record: bool = True,
    ) -> SearchResponse:
        started = time.perf_counter()
        base = self.filtered(params)
        engine = PricingEngine(self.db)
        text = (params.q or "").strip()
        offset = (params.page - 1) * params.page_size
        if text:
            ranked = self.rank(text, base, params.mode, semantic_weight)
            ids = ranked.ids
            if params.sort != "relevance" and ids:
                ids = list(self.db.scalars(select(Product.id).where(Product.id.in_(ids)).order_by(*self._order(params.sort))))
            page_ids = ids[offset: offset + params.page_size]
            total, scores, id_scope = ranked.total, ranked.scores, ids
        else:
            total = self.db.scalar(select(func.count()).select_from(base.subquery())) or 0
            page_ids = list(self.db.scalars(base.order_by(*self._order(params.sort)).offset(offset).limit(params.page_size)))
            scores, id_scope = {}, None
        products = ProductService(self.db).get_many(page_ids)
        items = [product_card(p, engine, scores.get(p.id)) for p in products]
        facets, price_range = self._facets(base, id_scope)
        latency = int((time.perf_counter() - started) * 1000)
        if text and record:
            self._record(text, params, principal, total, latency, source)
        return SearchResponse(
            items=items, total=total, page=params.page, page_size=params.page_size, query=text or None,
            mode=params.mode, sort=params.sort, facets=facets, price_range=price_range,
            engine={"keyword": "postgres-fts+trigram", "vector": self.embedder.describe(), "fusion": "rrf"},
            latency_ms=latency,
        )

    def _facets(self, base: Select[Any], ids: list[uuid.UUID] | None) -> tuple[dict[str, list[Facet]], dict[str, float | None]]:
        scope = base if ids is None else select(Product.id).where(Product.id.in_(ids or [uuid.uuid4()]))
        sub = scope.with_only_columns(Product.id).subquery()
        brand_rows = self.db.execute(
            select(Product.brand, func.count()).where(Product.id.in_(select(sub.c.id)), Product.brand.is_not(None))
            .group_by(Product.brand).order_by(func.count().desc()).limit(15)
        ).all()
        cat_rows = self.db.execute(
            select(Category.slug, Category.name, func.count())
            .join(Product, Product.category_id == Category.id)
            .where(Product.id.in_(select(sub.c.id)))
            .group_by(Category.slug, Category.name).order_by(func.count().desc()).limit(15)
        ).all()
        effective = func.coalesce(Product.sale_price, Product.price)
        lo, hi = self.db.execute(select(func.min(effective), func.max(effective)).where(Product.id.in_(select(sub.c.id)))).one()
        return (
            {
                "brands": [Facet(value=b, label=b, count=n) for b, n in brand_rows],
                "categories": [Facet(value=s, label=nm, count=n) for s, nm, n in cat_rows],
            },
            {"min": float(lo) if lo is not None else None, "max": float(hi) if hi is not None else None},
        )

    def _record(self, text: str, params: SearchQuery, principal: Principal | None, total: int, latency: int,
                source: str) -> None:
        filters = params.model_dump(mode="json", exclude={"q", "page", "page_size", "mode", "sort"}, exclude_defaults=True)
        uid = principal.user_id if principal else None
        self.db.add(SearchHistory(user_id=uid, query=text[:300], filters=filters, mode=params.mode, source=source,
                                  result_count=total, latency_ms=latency))
        self.db.add(AnalyticsEvent(event_type="search", user_id=uid,
                                   properties={"query": text[:200], "result_count": total, "source": source}))
        self.db.commit()

    def suggest(self, prefix: str, limit: int = 8) -> SuggestResponse:
        prefix = prefix.strip()
        if len(prefix) < 2:
            return SuggestResponse(products=[], categories=[])
        sim = func.similarity(Product.name, prefix)
        rows = self.db.execute(
            public_product_filter(select(Product.name, Product.slug))
            .where(or_(Product.name.ilike(f"%{prefix}%"), sim > 0.25))
            .order_by(sim.desc(), Product.sold_count.desc())
            .limit(limit)
        ).all()
        cats = self.db.execute(
            select(Category.name, Category.slug)
            .where(and_(Category.deleted_at.is_(None), Category.is_active.is_(True), Category.name.ilike(f"%{prefix}%")))
            .limit(4)
        ).all()
        return SuggestResponse(
            products=[{"name": n, "slug": s} for n, s in rows],
            categories=[{"name": n, "slug": s} for n, s in cats],
        )


def to_decimal(v: float | None) -> Decimal | None:
    return Decimal(str(v)) if v is not None else None
