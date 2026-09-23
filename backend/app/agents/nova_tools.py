"""Backend implementations of GenOra Nova tools."""

from __future__ import annotations

import re
import uuid
from decimal import Decimal

from genora.agents.nova import tools as spec
from genora.contracts.commerce import (
    AcceptCounterInput,
    AccessoriesInput,
    AccessoriesOutput,
    AddBundleToCartInput,
    AddToCartInput,
    AnalyzeImageInput,
    BundleInfo,
    CartSummaryOutput,
    ExternalPricesOutput,
    ExternalQuote,
    ImageAnalysisOutput,
    NegotiationPolicyOutput,
    NegotiationResultOutput,
    OfferInfo,
    ProductBundlesOutput,
    ProductDetailsOutput,
    ProductIdInput,
    ProductListOutput,
    ProductOffersOutput,
    RecommendationsInput,
    ResolveProductInput,
    ResolveProductOutput,
    ReviewInsightsOutput,
    SearchProductsInput,
    SubmitNegotiationInput,
)
from genora.core.tools import ToolContext
from genora.errors import ToolExecutionError
from genora.providers.embeddings import STOPWORDS
from sqlalchemy import select

from app.agents.base import guarded, note_price, services, summarize_product
from app.models.catalog import Product
from app.models.promotions import Bundle, BundleItem
from app.schemas.search import SearchQuery
from app.services.accessory_service import AccessoryService
from app.services.ai_runtime import get_vision_provider
from app.services.cart_service import CartService
from app.services.catalog_service import ProductService, is_negotiable, public_product_filter
from app.services.external_price_service import ExternalPriceService
from app.services.negotiation_service import NegotiationService
from app.services.pricing import PricingEngine
from app.services.promotion_service import PromotionService, is_bundle_live
from app.services.recommendation_service import RecommendationService
from app.services.review_service import ReviewService
from app.services.search_service import SearchService


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ToolExecutionError("invalid product id", code="INVALID_ID") from exc


def _visible(ctx: ToolContext, product_id: str) -> Product:
    svc = services(ctx)
    return ProductService(svc.db).get_visible(str(_uuid(product_id)), svc.principal)


class SearchProducts(spec.SearchProductsTool):
    @guarded
    def run(self, ctx: ToolContext, args: SearchProductsInput) -> ProductListOutput:
        svc = services(ctx)
        params = SearchQuery(
            q=args.query, category=args.category, min_price=args.min_price, max_price=args.max_price,
            brands=args.brands, min_rating=args.min_rating, in_stock=args.in_stock_only, mode=args.mode,
            sort=args.sort if (args.query or args.sort != "relevance") else "popularity", page_size=args.limit,
        )
        res = SearchService(svc.db).search(params, svc.principal, source="nova")
        engine = PricingEngine(svc.db)
        scores = {i.id: i.score for i in res.items}
        products = ProductService(svc.db).get_many([i.id for i in res.items])
        return ProductListOutput(
            products=[summarize_product(ctx, p, engine, scores.get(p.id)) for p in products], total=res.total,
            applied_filters=params.model_dump(mode="json", exclude_defaults=True, exclude={"page", "page_size"}),
        )


class ResolveProduct(spec.ResolveProductTool):
    @guarded
    def run(self, ctx: ToolContext, args: ResolveProductInput) -> ResolveProductOutput:
        svc = services(ctx)
        search = SearchService(svc.db)
        ranked = search.rank(args.reference, public_product_filter(select(Product.id)), "hybrid")
        products = ProductService(svc.db).get_many(ranked.ids[: args.limit])
        engine = PricingEngine(svc.db)
        words = [w for w in re.findall(r"[a-z0-9]+", args.reference.lower()) if w not in STOPWORDS]

        def coverage(p: Product) -> int:
            name = f"{p.name} {p.brand or ''}".lower()
            return sum(1 for w in words if re.search(rf"\b{re.escape(w)}", name))

        ordered = sorted(products, key=coverage, reverse=True)  # stable: keeps search rank among ties
        exact = [p for p in products if p.name.lower() == args.reference.lower().strip()]
        top = coverage(ordered[0]) if ordered else 0
        second = coverage(ordered[1]) if len(ordered) > 1 else -1
        confident = bool(exact) or (top > 0 and top > second and (top == len(words) or top >= 2))
        if exact:
            ordered = exact + [p for p in ordered if p not in exact]
        if words and top == 0:
            ordered = []  # nothing in the catalog is named like this
        return ResolveProductOutput(candidates=[summarize_product(ctx, p, engine) for p in ordered],
                                    confident=confident)


class ProductDetails(spec.ProductDetailsTool):
    @guarded
    def run(self, ctx: ToolContext, args: ProductIdInput) -> ProductDetailsOutput:
        svc = services(ctx)
        p = _visible(ctx, args.product_id)
        return ProductDetailsOutput(
            product=summarize_product(ctx, p, PricingEngine(svc.db)), description=p.description,
            attributes=dict(p.attributes or {}),
            variants=[{"id": str(v.id), "name": v.name, "sku": v.sku, "attributes": v.attributes} for v in p.variants],
            negotiable=is_negotiable(svc.db, p),
            low_stock=any(i.available <= i.low_stock_threshold for i in p.inventory),
        )


class ProductOffers(spec.ProductOffersTool):
    @guarded
    def run(self, ctx: ToolContext, args: ProductIdInput) -> ProductOffersOutput:
        svc = services(ctx)
        p = _visible(ctx, args.product_id)
        offers = PromotionService(svc.db).offers_for_product(p)
        for o in offers:
            note_price(ctx, float(o.discount_per_unit), float(o.price_after_offer))
        return ProductOffersOutput(
            product=summarize_product(ctx, p, PricingEngine(svc.db)),
            offers=[OfferInfo(name=o.name, description=o.description, scope=o.scope, discount_type=o.discount_type,
                              value=float(o.value), discount_per_unit=float(o.discount_per_unit),
                              price_after_offer=float(o.price_after_offer), min_quantity=o.min_quantity,
                              eligible_for_single_unit=o.eligible, ends_at=o.ends_at, conditions=o.conditions)
                    for o in offers],
        )


class ProductBundles(spec.ProductBundlesTool):
    @guarded
    def run(self, ctx: ToolContext, args: ProductIdInput) -> ProductBundlesOutput:
        svc = services(ctx)
        p = _visible(ctx, args.product_id)
        engine = PricingEngine(svc.db)
        promo = PromotionService(svc.db)
        bundles = []
        stmt = select(Bundle).where(Bundle.deleted_at.is_(None),
                                    Bundle.id.in_(select(BundleItem.bundle_id).where(BundleItem.product_id == p.id)))
        for b in svc.db.scalars(stmt):
            if is_bundle_live(b):
                out = promo.bundle_out(b, engine)
                members = ProductService(svc.db).get_many([c.id for c in out.products])
                note_price(ctx, float(out.items_total), float(out.bundle_price), float(out.savings))
                bundles.append(BundleInfo(id=str(b.id), name=b.name, description=b.description,
                                          products=[summarize_product(ctx, m, engine) for m in members],
                                          items_total=float(out.items_total), bundle_price=float(out.bundle_price),
                                          savings=float(out.savings), available=out.available))
        return ProductBundlesOutput(product=summarize_product(ctx, p, engine), bundles=bundles)


class FindAccessories(spec.FindAccessoriesTool):
    @guarded
    def run(self, ctx: ToolContext, args: AccessoriesInput) -> AccessoriesOutput:
        svc = services(ctx)
        p = _visible(ctx, args.product_id)
        engine = PricingEngine(svc.db)
        matches, cats = AccessoryService(svc.db).find(p, args.limit, args.max_price)
        return AccessoriesOutput(
            product=summarize_product(ctx, p, engine),
            accessories=[summarize_product(ctx, m.product, engine) for m in matches],
            compatibility={str(m.product.id): m.evidence for m in matches if m.evidence},
            categories_searched=cats,
        )


class ReviewInsights(spec.ReviewInsightsTool):
    @guarded
    def run(self, ctx: ToolContext, args: ProductIdInput) -> ReviewInsightsOutput:
        svc = services(ctx)
        p = _visible(ctx, args.product_id)
        s = ReviewService(svc.db).summary(p.id)
        return ReviewInsightsOutput(product=summarize_product(ctx, p, PricingEngine(svc.db)), insights=s.insights,
                                    disclaimer=s.disclaimer)


class NegotiationPolicy(spec.NegotiationPolicyTool):
    @guarded
    def run(self, ctx: ToolContext, args: ProductIdInput) -> NegotiationPolicyOutput:
        svc = services(ctx)
        p = _visible(ctx, args.product_id)
        engine = PricingEngine(svc.db)
        allowed, reason = NegotiationService(svc.db).policy(p)
        if svc.principal.seller_id == p.seller_id:
            allowed, reason = False, "You cannot negotiate on your own product"
        return NegotiationPolicyOutput(product=summarize_product(ctx, p, engine), negotiable=allowed, reason=reason,
                                       current_price=float(engine.quote(p).final_price))


def _negotiation_out(ctx: ToolContext, n: object) -> NegotiationResultOutput:
    from app.schemas.promotions import NegotiationOut

    assert isinstance(n, NegotiationOut)
    note_price(ctx, float(n.list_price), float(n.offered_price),
               float(n.counter_price) if n.counter_price is not None else None,
               float(n.agreed_price) if n.agreed_price is not None else None)
    return NegotiationResultOutput(
        id=str(n.id), product_name=n.product_name, status=n.status, list_price=float(n.list_price),
        offered_price=float(n.offered_price), counter_price=float(n.counter_price) if n.counter_price is not None else None,
        agreed_price=float(n.agreed_price) if n.agreed_price is not None else None, reason=n.reason, expires_at=n.expires_at,
    )


class SubmitNegotiation(spec.SubmitNegotiationTool):
    @guarded
    def run(self, ctx: ToolContext, args: SubmitNegotiationInput) -> NegotiationResultOutput:
        svc = services(ctx)
        n = NegotiationService(svc.db).propose(_uuid(args.product_id), Decimal(str(args.offered_price)), svc.principal,
                                               "Submitted via GenOra Nova")
        return _negotiation_out(ctx, n)


class AcceptCounterOffer(spec.AcceptCounterOfferTool):
    @guarded
    def run(self, ctx: ToolContext, args: AcceptCounterInput) -> NegotiationResultOutput:
        svc = services(ctx)
        return _negotiation_out(ctx, NegotiationService(svc.db).accept_counter(_uuid(args.negotiation_id), svc.principal))


class ExternalPrices(spec.ExternalPricesTool):
    @guarded
    def run(self, ctx: ToolContext, args: ProductIdInput) -> ExternalPricesOutput:
        svc = services(ctx)
        p = _visible(ctx, args.product_id)
        engine = PricingEngine(svc.db)
        ext = ExternalPriceService(svc.db)
        quotes, errors = ext.lookup(p)
        note_price(ctx, *[q.price for q in quotes])
        return ExternalPricesOutput(
            product=summarize_product(ctx, p, engine), our_price=float(engine.quote(p).final_price),
            quotes=[ExternalQuote(provider=q.provider, marketplace=q.marketplace, price=q.price, currency=q.currency,
                                  url=q.url, in_stock=q.in_stock, retrieved_at=q.retrieved_at, is_test_data=q.is_test_data)
                    for q in quotes],
            providers_configured=ext.configured(), errors=errors,
        )


def _cart_summary(ctx: ToolContext, cart: object, added: str) -> CartSummaryOutput:
    from app.schemas.commerce import CartOut

    assert isinstance(cart, CartOut)
    note_price(ctx, float(cart.subtotal), float(cart.total), float(cart.discount_total))
    return CartSummaryOutput(item_count=cart.item_count, subtotal=float(cart.subtotal),
                             discount_total=float(cart.discount_total), total=float(cart.total), added=added)


class AddToCart(spec.AddToCartTool):
    @guarded
    def run(self, ctx: ToolContext, args: AddToCartInput) -> CartSummaryOutput:
        svc = services(ctx)
        p = _visible(ctx, args.product_id)
        cart = CartService(svc.db, svc.principal.user_id).add(p.id, args.quantity, source="nova")
        return _cart_summary(ctx, cart, f"{args.quantity} × {p.name}")


class AddBundleToCart(spec.AddBundleToCartTool):
    @guarded
    def run(self, ctx: ToolContext, args: AddBundleToCartInput) -> CartSummaryOutput:
        svc = services(ctx)
        b = svc.db.get(Bundle, _uuid(args.bundle_id))
        cart = CartService(svc.db, svc.principal.user_id).add_bundle(_uuid(args.bundle_id), source="nova")
        return _cart_summary(ctx, cart, f"the {b.name if b else 'bundle'} bundle")


class Recommendations(spec.RecommendationsTool):
    @guarded
    def run(self, ctx: ToolContext, args: RecommendationsInput) -> ProductListOutput:
        svc = services(ctx)
        recs = RecommendationService(svc.db)
        if args.strategy == "popular":
            res = recs.popular(args.limit)
        elif args.strategy in ("similar", "also_bought") and args.product_id:
            res = (recs.similar if args.strategy == "similar" else recs.also_bought)(_uuid(args.product_id), args.limit)
        else:
            res = recs.for_user(svc.principal.user_id, args.limit)
        engine = PricingEngine(svc.db)
        products = ProductService(svc.db).get_many([i.id for i in res.items])
        return ProductListOutput(products=[summarize_product(ctx, p, engine) for p in products], total=len(products),
                                 applied_filters={"strategy": res.strategy})


class AnalyzeImage(spec.AnalyzeImageTool):
    @guarded
    def run(self, ctx: ToolContext, args: AnalyzeImageInput) -> ImageAnalysisOutput:
        if args.attachment_id not in ctx.attachments:
            raise ToolExecutionError("attachment not found", code="ATTACHMENT_NOT_FOUND")
        data, mime = ctx.attachments[args.attachment_id]
        provider = get_vision_provider()
        analysis = provider.analyze_product_image(data, mime)
        return ImageAnalysisOutput(**analysis.model_dump(), provider=provider.name)


NOVA_TOOL_IMPLEMENTATIONS = [
    SearchProducts(), ResolveProduct(), ProductDetails(), ProductOffers(), ProductBundles(), FindAccessories(),
    ReviewInsights(), NegotiationPolicy(), SubmitNegotiation(), AcceptCounterOffer(), ExternalPrices(), AddToCart(),
    AddBundleToCart(), Recommendations(), AnalyzeImage(),
]
