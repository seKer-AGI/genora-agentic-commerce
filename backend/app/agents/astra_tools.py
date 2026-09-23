"""Backend implementations of GenOra Astra tools (always scoped to the calling seller)."""

from __future__ import annotations

import random
import re
import uuid
from datetime import timedelta
from decimal import Decimal

from genora.agents.astra import tools as spec
from genora.contracts.seller import (
    CategorySuggestion,
    CreateOfferInput,
    CreateProductInput,
    DiscountStrategyInput,
    DiscountStrategyOutput,
    DraftListingInput,
    ForecastInput,
    ForecastOutput,
    InventoryInput,
    InventoryItem,
    InventoryOutput,
    ListingDraftOutput,
    Metric,
    OfferCreatedOutput,
    PerfItem,
    PeriodInput,
    ProductChangeOutput,
    ProductPerformanceInput,
    ProductPerformanceOutput,
    ResolveSellerProductInput,
    ResolveSellerProductOutput,
    SalesSummaryOutput,
    SellerProductRef,
    StrategySuggestion,
    UpdatePriceInput,
    UpdateStockInput,
)
from genora.core.tools import ToolContext
from genora.errors import ToolExecutionError
from genora.listing import ListingFacts, LLMListingGenerator, TemplateListingGenerator
from genora.nlu.catalog import CATEGORY_SYNONYMS
from genora.providers.embeddings import cosine
from sqlalchemy import func, or_, select

from app.agents.base import AgentServices, guarded, note_price, services
from app.core.security import utcnow
from app.models.catalog import Category, Product
from app.schemas.analytics import Kpi, ProductPerf
from app.schemas.catalog import InventoryUpdate, ProductCreate, ProductUpdate
from app.schemas.promotions import OfferIn
from app.services.ai_runtime import get_embedding_provider, get_llm_provider
from app.services.analytics_service import AnalyticsService
from app.services.catalog_service import InventoryService, ProductService
from app.services.forecasting_service import ForecastingService, ForecastRequest
from app.services.pricing import PricingEngine
from app.services.promotion_service import PromotionService
from app.services.seller_insights import SellerInsights


def _seller(ctx: ToolContext) -> tuple[AgentServices, uuid.UUID]:
    svc = services(ctx)
    if svc.principal.seller_id is None:
        raise ToolExecutionError("An active seller profile is required", code="SELLER_REQUIRED")
    return svc, svc.principal.seller_id


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ToolExecutionError("invalid id", code="INVALID_ID") from exc


def _metric(k: Kpi) -> Metric:
    return Metric(value=k.value, previous=k.previous, change_pct=k.change_pct)


def _perf(p: ProductPerf) -> PerfItem:
    return PerfItem(product_id=str(p.product_id), name=p.name, revenue=p.revenue, units=p.units, orders=p.orders,
                    views=p.views, conversion_rate=p.conversion_rate, rating_avg=p.rating_avg, stock=p.stock)


def _change(p: Product, changes: dict[str, object]) -> ProductChangeOutput:
    return ProductChangeOutput(product_id=str(p.id), name=p.name, status=p.status.value, price=float(p.price),
                               sale_price=float(p.sale_price) if p.sale_price is not None else None, stock=p.stock,
                               url=f"/seller/products/{p.id}", changes=changes)


class SellerInventory(spec.SellerInventoryTool):
    @guarded
    def run(self, ctx: ToolContext, args: InventoryInput) -> InventoryOutput:
        svc, seller_id = _seller(ctx)
        rows = InventoryService(svc.db).list(seller_id, low_only=False)
        sold = SellerInsights(svc.db).units_sold([r.product_id for r in rows], 30) if rows else {}
        items = []
        for r in rows:
            if args.low_only and (not r.is_low or r.status == "archived"):
                continue
            s30 = sold.get(r.product_id, 0)
            cover = round(r.available / (s30 / 30), 1) if s30 else None
            items.append(InventoryItem(product_id=str(r.product_id), name=r.product_name, sku=r.sku, status=r.status,
                                       available=r.available, low_stock_threshold=r.low_stock_threshold, is_low=r.is_low,
                                       sold_last_30d=s30, days_of_cover=cover))
        items.sort(key=lambda i: (i.available, -(i.sold_last_30d)))
        return InventoryOutput(items=items, total_products=len(rows))


class SellerSalesSummary(spec.SellerSalesSummaryTool):
    @guarded
    def run(self, ctx: ToolContext, args: PeriodInput) -> SalesSummaryOutput:
        svc, seller_id = _seller(ctx)
        ov = AnalyticsService(svc.db).seller_overview(seller_id, args.days)
        note_price(ctx, ov.revenue.value, ov.average_order_value.value)
        return SalesSummaryOutput(
            period_days=ov.period_days, revenue=_metric(ov.revenue), orders=_metric(ov.orders),
            units_sold=_metric(ov.units_sold), average_order_value=_metric(ov.average_order_value),
            views=_metric(ov.views), conversion_rate=_metric(ov.conversion_rate),
            series=[p.model_dump(mode="json") for p in ov.series], top_products=[_perf(p) for p in ov.top_products],
            low_performers=[_perf(p) for p in ov.low_performers], definitions=ov.definitions,
        )


class SellerProductPerformance(spec.SellerProductPerformanceTool):
    @guarded
    def run(self, ctx: ToolContext, args: ProductPerformanceInput) -> ProductPerformanceOutput:
        svc, seller_id = _seller(ctx)
        end = utcnow()
        items = AnalyticsService(svc.db).product_performance(end - timedelta(days=args.days), end, seller_id,
                                                             limit=args.limit, worst=args.order == "worst")
        return ProductPerformanceOutput(period_days=args.days, order=args.order, items=[_perf(p) for p in items])


class ResolveSellerProduct(spec.ResolveSellerProductTool):
    @guarded
    def run(self, ctx: ToolContext, args: ResolveSellerProductInput) -> ResolveSellerProductOutput:
        svc, seller_id = _seller(ctx)
        ref = args.reference.strip()
        sim = func.similarity(Product.name, ref)
        words = [w for w in re.findall(r"[a-z0-9]+", ref.lower()) if len(w) > 1]
        conds = [Product.sku.ilike(ref), Product.name.ilike(f"%{ref}%"), sim > 0.2]
        conds += [Product.name.ilike(f"%{w}%") for w in words]
        rows = list(svc.db.scalars(
            select(Product).where(Product.seller_id == seller_id, Product.deleted_at.is_(None), or_(*conds))
            .order_by(sim.desc()).limit(20)).unique())
        scored = sorted(rows, key=lambda p: (p.sku.lower() == ref.lower(), sum(w in p.name.lower() for w in words),
                                             p.name.lower() == ref.lower()), reverse=True)
        significant = [w for w in words if w not in {"the", "my", "of", "for", "and"}]
        need = max(1, (len(significant) + 1) // 2)  # at least half of the words must match
        scored = [p for p in scored if p.sku.lower() == ref.lower()
                  or sum(w in p.name.lower() for w in significant) >= need]
        best = scored[:5]
        top_hits = sum(w in best[0].name.lower() for w in words) if best else 0
        ties = [p for p in best if sum(w in p.name.lower() for w in words) == top_hits]
        confident = bool(best) and (best[0].sku.lower() == ref.lower() or best[0].name.lower() == ref.lower()
                                    or len(ties) == 1)
        return ResolveSellerProductOutput(
            candidates=[SellerProductRef(id=str(p.id), name=p.name, sku=p.sku, price=float(p.price),
                                         sale_price=float(p.sale_price) if p.sale_price is not None else None,
                                         status=p.status.value, stock=p.stock) for p in best],
            confident=confident)


class DraftListing(spec.DraftListingTool):
    @guarded
    def run(self, ctx: ToolContext, args: DraftListingInput) -> ListingDraftOutput:
        svc, seller_id = _seller(ctx)
        cats = list(svc.db.scalars(select(Category).where(Category.deleted_at.is_(None), Category.is_active.is_(True))))
        leaves = [c for c in cats if not any(o.parent_id == c.id for o in cats)]
        text = f"{args.product_name} {args.brand or ''} {args.notes or ''} " + " ".join(map(str, args.attributes.values()))
        emb = get_embedding_provider()
        qv = emb.embed_one(text)
        cvs = emb.embed([f"{c.name} {c.name} {' '.join(CATEGORY_SYNONYMS.get(c.slug, ()))} {c.description or ''}"
                         for c in leaves])
        low = text.lower()
        scored = []
        for c, v in zip(leaves, cvs, strict=True):
            score = cosine(qv, v)
            if any(re.search(rf"\b{re.escape(s)}\b", low) for s in (c.name.lower(), *CATEGORY_SYNONYMS.get(c.slug, ()))):
                score += 0.5
            scored.append((round(score, 3), c))
        scored.sort(key=lambda t: t[0], reverse=True)
        suggestions = [CategorySuggestion(id=str(c.id), name=c.name, slug=c.slug, score=s) for s, c in scored[:3]]
        facts = ListingFacts(args.product_name, args.brand, args.notes, args.attributes,
                             suggestions[0].name if suggestions else None, args.price)
        llm = get_llm_provider()
        generator = LLMListingGenerator(llm) if llm.available else TemplateListingGenerator()
        draft = generator.generate(facts)
        prefix = re.sub(r"[^A-Z0-9]", "", (args.brand or args.product_name).upper())[:4] or "SKU"
        sku = f"{prefix}-{random.randint(1000, 9999)}"  # noqa: S311 - not security-sensitive
        while svc.db.scalar(select(Product.id).where(Product.seller_id == seller_id, Product.sku == sku)):
            sku = f"{prefix}-{random.randint(1000, 9999)}"  # noqa: S311
        if args.price is not None:
            note_price(ctx, args.price)
        warnings = list(draft.warnings)
        if not args.attributes:
            warnings.append("No specifications were provided — add them before publishing for better search ranking")
        return ListingDraftOutput(title=draft.title, description=draft.description, seo_description=draft.seo_description,
                                  tags=draft.tags, attributes=draft.attributes, brand=args.brand, price=args.price,
                                  suggested_sku=sku, category_suggestions=suggestions, generated_by=draft.generated_by,
                                  warnings=warnings)


class CreateProduct(spec.CreateProductTool):
    @guarded
    def run(self, ctx: ToolContext, args: CreateProductInput) -> ProductChangeOutput:
        svc, _ = _seller(ctx)
        data = ProductCreate(
            name=args.name, sku=args.sku, description=args.description, seo_description=args.seo_description,
            brand=args.brand, category_id=_uuid(args.category_id) if args.category_id else None,
            price=Decimal(str(args.price)), stock=args.stock, tags=args.tags, attributes=args.attributes,
            status=args.status,
        )
        p = ProductService(svc.db).create(data, svc.principal)
        return _change(p, {"created": True, "status": p.status.value})


class UpdatePrice(spec.UpdatePriceTool):
    @guarded
    def run(self, ctx: ToolContext, args: UpdatePriceInput) -> ProductChangeOutput:
        svc, _ = _seller(ctx)
        payload: dict[str, object] = {}
        if args.price is not None:
            payload["price"] = Decimal(str(args.price))
        if args.sale_price is not None:
            payload["sale_price"] = Decimal(str(args.sale_price))
        before = ProductService(svc.db).get_manageable(_uuid(args.product_id), svc.principal)
        old = (float(before.price), float(before.sale_price) if before.sale_price is not None else None)
        p = ProductService(svc.db).update(_uuid(args.product_id),
                                          ProductUpdate(**payload, clear_sale_price=args.clear_sale_price), svc.principal)
        note_price(ctx, float(p.price), float(p.sale_price) if p.sale_price is not None else None)
        return _change(p, {"before": {"price": old[0], "sale_price": old[1]}})


class UpdateStock(spec.UpdateStockTool):
    @guarded
    def run(self, ctx: ToolContext, args: UpdateStockInput) -> ProductChangeOutput:
        svc, _ = _seller(ctx)
        out = InventoryService(svc.db).update(_uuid(args.product_id), InventoryUpdate(quantity_on_hand=args.quantity_on_hand),
                                              svc.principal)
        p = ProductService(svc.db).get_manageable(_uuid(args.product_id), svc.principal)
        return _change(p, {"quantity_on_hand": out.quantity_on_hand})


class CreateOffer(spec.CreateOfferTool):
    @guarded
    def run(self, ctx: ToolContext, args: CreateOfferInput) -> OfferCreatedOutput:
        svc, _ = _seller(ctx)
        p = ProductService(svc.db).get_manageable(_uuid(args.product_id), svc.principal)
        now = utcnow()
        name = args.name or f"{args.percent_off:g}% off {p.name}"[:120]
        offer = PromotionService(svc.db).create_offer(
            OfferIn(name=name, description="Created with GenOra Astra", discount_type="percentage",
                    value=Decimal(str(args.percent_off)), product_id=p.id, starts_at=now,
                    ends_at=now + timedelta(days=args.days)), svc.principal)
        svc.db.refresh(p)
        final = float(PricingEngine(svc.db).quote(p).final_price)
        note_price(ctx, final)
        return OfferCreatedOutput(offer_id=str(offer.id), name=offer.name, product_name=p.name,
                                  percent_off=args.percent_off, ends_at=offer.ends_at.isoformat() if offer.ends_at else "",
                                  new_final_price=final)


class DiscountStrategy(spec.DiscountStrategyTool):
    @guarded
    def run(self, ctx: ToolContext, args: DiscountStrategyInput) -> DiscountStrategyOutput:
        svc, seller_id = _seller(ctx)
        ids = [_uuid(i) for i in args.product_ids] or None
        items = SellerInsights(svc.db).discount_strategy(seller_id, args.days, ids)
        return DiscountStrategyOutput(
            period_days=args.days, suggestions=[StrategySuggestion.model_validate(i) for i in items],
            method="Rule-based analysis of your views, conversion, units sold vs the previous period, stock levels and "
                   "category median prices. No prices were changed.",
        )


class RunForecast(spec.ForecastTool):
    @guarded
    def run(self, ctx: ToolContext, args: ForecastInput) -> ForecastOutput:
        svc, _ = _seller(ctx)
        out = ForecastingService(svc.db).run(
            ForecastRequest(target=args.target, entity_id=_uuid(args.entity_id) if args.entity_id else None,
                            horizon=args.horizon_days, provider=args.provider, scope="seller"), svc.principal)
        return ForecastOutput(id=str(out.id) if out.id else None, target=out.target, provider=out.provider,
                              model_name=out.model_name, status=out.status, horizon=out.horizon, history=out.history,
                              points=out.points, metrics=out.metrics, error=out.error)


ASTRA_TOOL_IMPLEMENTATIONS = [
    SellerInventory(), SellerSalesSummary(), SellerProductPerformance(), ResolveSellerProduct(), DraftListing(),
    CreateProduct(), UpdatePrice(), UpdateStock(), CreateOffer(), DiscountStrategy(), RunForecast(),
]
