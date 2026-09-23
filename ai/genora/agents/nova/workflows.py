"""GenOra Nova — buyer workflows.

Every statement about products, prices, offers, reviews and availability comes from a tool result.
Write actions (cart, negotiation) are proposed as pending actions and only run after confirmation.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from genora.agents.nova.common import Unresolved, card, money, product_by_id, remember, resolve_target
from genora.contracts.commerce import (
    AccessoriesOutput,
    CartSummaryOutput,
    ExternalPricesOutput,
    ImageAnalysisOutput,
    NegotiationPolicyOutput,
    NegotiationResultOutput,
    ProductBundlesOutput,
    ProductDetailsOutput,
    ProductListOutput,
    ProductOffersOutput,
    ProductSummary,
    ReviewInsightsOutput,
)
from genora.core.blocks import (
    BundleBlock,
    ComparisonBlock,
    ExternalPricesBlock,
    ImageAnalysisBlock,
    NegotiationBlock,
    NoticeBlock,
    OffersBlock,
    ProductListBlock,
    ReviewSummaryBlock,
)
from genora.core.engine import ConfirmableWorkflow
from genora.core.memory import PendingAction
from genora.core.tools import ToolResult
from genora.core.workflow import Workflow, WorkflowContext, WorkflowResult, WorkflowStatus
from genora.nlu.catalog import CatalogMatcher
from genora.nlu.extractors import (
    NO_BUDGET,
    Budget,
    extract_attribute_constraints,
    extract_budget,
    extract_offer_price,
    extract_ordinals,
    extract_quantity,
    extract_top_n,
    extract_use_cases,
    split_compare_targets,
)

HIGH_TICKET = {"laptops", "smartphones", "cameras", "furniture"}
_FILLER = re.compile(
    r"\b(i\s+need|i\s+want|i'?m\s+looking\s+for|looking\s+for|can\s+you|could\s+you|please|find\s+me|find|show\s+me|"
    r"show|search\s+for|search|recommend(?:\s+me)?|suggest|get\s+me|help\s+me\s+(?:choose|pick|find)|what'?s\s+the\s+best|"
    r"best|good|some|any|a|an|the|me|for\s+me|do\s+you\s+(?:have|sell)|list)\b", re.I)
_BUDGET_SPAN = re.compile(
    r"\b(under|below|less than|max(?:imum)?|up to|no more than|at most|within|over|above|more than|at least|around|"
    r"about|between|budget(?:\s+is|\s+of)?)?\s*\$?\s?\d[\d,]*(?:\.\d+)?\s?k?\b(?:\s*(?:-|to|and)\s*\$?\s?\d[\d,]*k?)?"
    r"(?:\s*(?:dollars|usd|bucks))?", re.I)


def _matcher(ctx: WorkflowContext) -> CatalogMatcher:
    return CatalogMatcher(ctx.hints)


def _clean_query(text: str) -> str:
    q = _BUDGET_SPAN.sub(" ", text)
    q = _FILLER.sub(" ", q)
    q = re.sub(r"[^\w\s\-]", " ", q)
    return re.sub(r"\s+", " ", q).strip()


def _search(ctx: WorkflowContext, **kwargs: Any) -> ProductListOutput:
    out = ctx.call("search_products", **kwargs)
    assert isinstance(out, ProductListOutput)
    return out


def _attr_value(p: ProductSummary, key: str) -> Any:
    return p.attributes.get(key)


def _satisfies(p: ProductSummary, constraint: dict[str, Any]) -> bool | None:
    """True/False when the attribute is known, None when the seller did not provide it."""
    v = _attr_value(p, str(constraint["attribute"]))
    if v is None:
        return None
    try:
        if constraint["op"] == ">=":
            return float(v) >= float(constraint["value"])
        if constraint["op"] == "<=":
            return float(v) <= float(constraint["value"])
        return bool(v) == bool(constraint["value"])
    except (TypeError, ValueError):
        return None


# ============================================================================ discovery
class ProductDiscoveryWorkflow(Workflow):
    name = "product_discovery"
    intents = ("product_discovery",)
    description = "Understand requirements, search the catalog and rank products with reasons."

    def run(self, ctx: WorkflowContext) -> WorkflowResult:
        slots = ctx.state.slots
        matcher = _matcher(ctx)
        text = ctx.text
        answered = ctx.intent.slots.get("answered")

        # ---- 1. requirement extraction (merged with conversational memory)
        if answered == "budget" and NO_BUDGET.search(text):
            slots["budget_skipped"] = True
        budget = extract_budget(text, allow_bare_number=answered == "budget")
        if not budget.empty:
            slots["budget_min"] = float(budget.min) if budget.min is not None else None
            slots["budget_max"] = float(budget.max) if budget.max is not None else None
            slots.pop("budget_skipped", None)
        cat = matcher.category(text)
        if cat and cat.slug != slots.get("category"):
            if slots.get("category"):  # new product type → budget from the old task no longer applies
                for k in ("budget_min", "budget_max", "budget_skipped", "use_cases", "constraints", "query"):
                    slots.pop(k, None)
                if not budget.empty:
                    slots["budget_min"] = float(budget.min) if budget.min is not None else None
                    slots["budget_max"] = float(budget.max) if budget.max is not None else None
            slots["category"] = cat.slug
        brand = matcher.brand(text)
        if brand:
            slots["brand"] = brand
        use_cases = extract_use_cases(text)
        if use_cases:
            slots["use_cases"] = sorted(set(slots.get("use_cases", [])) | set(use_cases))
        constraints = extract_attribute_constraints(text)
        if constraints:
            slots["constraints"] = constraints
        if answered != "budget":
            q = _clean_query(text)
            if q:
                slots["query"] = q

        # ---- 2. clarify what is missing
        if not slots.get("category") and not slots.get("query"):
            return WorkflowResult.ask(ctx.state, self.name, "category", "What kind of product are you looking for?",
                                      matcher.top_categories())
        if (slots.get("category") in HIGH_TICKET and slots.get("budget_max") is None
                and slots.get("budget_min") is None and not slots.get("budget_skipped")):
            name = (matcher.category_name(slots["category"]) or "product").lower()
            return WorkflowResult.ask(ctx.state, self.name, "budget", f"What's your budget for the {name.rstrip('s')}?",
                                      ["Under $500", "Under $1000", "Under $1500", "No budget"])

        # ---- 3. search
        ctx.status("Searching products…")
        query_terms = " ".join(filter(None, [slots.get("query"), " ".join(slots.get("use_cases", []))])).strip()
        base: dict[str, Any] = {
            "query": query_terms or matcher.category_name(slots.get("category")),
            "category": slots.get("category"),
            "min_price": slots.get("budget_min"),
            "max_price": slots.get("budget_max"),
            "brands": [slots["brand"]] if slots.get("brand") else [],
            "limit": 12,
        }
        result = _search(ctx, **base)
        relaxed: list[str] = []
        if not result.products and base["brands"]:
            base["brands"] = []
            relaxed.append(f"no {slots['brand']} products matched, so I included other brands")
            result = _search(ctx, **base)
        if not result.products and base["query"] and base["category"]:
            base["query"] = matcher.category_name(base["category"])
            result = _search(ctx, **base)
        if not result.products and base["max_price"]:
            widened = round(base["max_price"] * 1.15, 2)
            base["max_price"] = widened
            relaxed.append(f"nothing matched your exact budget, so I looked up to {money(widened)}")
            result = _search(ctx, **base)
        if not result.products:
            where = matcher.category_name(slots.get("category")) or "the catalog"
            return WorkflowResult(WorkflowStatus.COMPLETED,
                                  f"I couldn't find anything in {where} matching those requirements. "
                                  "Try a higher budget or fewer constraints.",
                                  suggestions=["Show me popular products", "No budget"])

        # ---- 4. rank with explanations
        ctx.status("Ranking the best matches…")
        ranked = self._rank(result.products, slots)
        top = [p for p, _, _ in ranked[:4]]
        reasons = {p.id: why for p, _, why in ranked[:4]}
        remember(ctx, top, focus=top[0] if len(top) == 1 else None)
        for p in top:
            ctx.tool_ctx.seen_prices.add(f"{p.final_price:.2f}")

        cat_name = (matcher.category_name(slots.get("category")) or "products").lower()
        budget_txt = ""
        if slots.get("budget_max") is not None:
            budget_txt = f" under {money(slots['budget_max'])}"
        use_txt = f" for {', '.join(slots['use_cases'])}" if slots.get("use_cases") else ""
        intro = f"Here are the best {cat_name}{budget_txt}{use_txt} I found:"
        if relaxed:
            intro = "Note: " + "; ".join(relaxed) + ".\n" + intro
        facts = [f"{p.name}: {money(p.final_price)}, rated {p.rating_avg:.1f}/5 ({p.rating_count} reviews); "
                 + "; ".join(reasons[p.id]) for p in top]
        lines = [intro] + [f"{i + 1}. **{p.name}** — {money(p.final_price)} · {p.rating_avg:.1f}★ · {reasons[p.id][0]}"
                           for i, p in enumerate(top)]
        return WorkflowResult(
            WorkflowStatus.COMPLETED, "\n".join(lines),
            [ProductListBlock(title=f"Recommended {cat_name}", products=[card(p) for p in top], reasons=reasons,
                              note=f"{result.total} matching products considered")],
            suggestions=["Compare the top 3", "What do reviews say about the first one?", "Any discounts on #1?"],
            facts=[intro, *facts],
        )

    @staticmethod
    def _rank(products: list[ProductSummary], slots: dict[str, Any]) -> list[tuple[ProductSummary, float, list[str]]]:
        constraints = slots.get("constraints", [])
        use_cases = slots.get("use_cases", [])
        max_score = max((p.score or 0.0) for p in products) or 1.0
        out = []
        for idx, p in enumerate(products):
            why: list[str] = []
            if constraints:
                checks = [_satisfies(p, c) for c in constraints]
                if any(c is False for c in checks):
                    continue
                for c, ok in zip(constraints, checks, strict=True):
                    label = str(c["attribute"]).replace("_", " ")
                    if ok:
                        why.append(f"{label}: {_attr_value(p, str(c['attribute']))}")
                    else:
                        why.append(f"{label} not specified by seller")
            relevance = (p.score or 0.0) / max_score if p.score is not None else 1 - idx / max(len(products), 1)
            fit = 0.0
            tags = {t.lower() for t in p.tags}
            for uc in use_cases:
                if uc in tags or uc in p.name.lower() or any(uc in str(v).lower() for v in p.attributes.values()):
                    fit += 1
                    why.insert(0, f"Suited to {uc}")
            if slots.get("budget_max") is not None:
                why.append(f"Within your {money(slots['budget_max'])} budget at {money(p.final_price)}")
            if p.rating_count:
                why.append(f"Rated {p.rating_avg:.1f}★ by {p.rating_count} customers")
            if p.offer_name:
                why.append(f"Offer: {p.offer_name}")
            if not p.in_stock:
                why.append("Currently out of stock")
            bayes = (p.rating_avg * p.rating_count + 4.0 * 3) / (p.rating_count + 3)
            score = 0.45 * relevance + 0.2 * (bayes / 5) + 0.2 * min(fit, 2) / 2 + (0.15 if p.in_stock else -0.3)
            out.append((p, score, why or ["Matches your search"]))
        out.sort(key=lambda t: t[1], reverse=True)
        return out


# ============================================================================ search
class ProductSearchWorkflow(Workflow):
    name = "product_search"
    intents = ("product_search",)

    def run(self, ctx: WorkflowContext) -> WorkflowResult:
        matcher = _matcher(ctx)
        budget = extract_budget(ctx.text)
        cat = matcher.category(ctx.text)
        brand = matcher.brand(ctx.text)
        query = _clean_query(ctx.text)
        if not query and not cat:
            return WorkflowResult.ask(ctx.state, "product_discovery", "category", "What would you like me to search for?",
                                      matcher.top_categories())
        ctx.status("Searching products…")
        params: dict[str, Any] = {
            "query": query or (cat.name if cat else None), "category": cat.slug if cat else None,
            "min_price": float(budget.min) if budget.min else None, "max_price": float(budget.max) if budget.max else None,
            "brands": [brand] if brand else [], "limit": 8,
        }
        # Capitalised words that are not known brands/categories are probably brands we don't carry (e.g. "Nike").
        unknown = [w for w in re.findall(r"\b[A-Z][a-zA-Z]+\b", ctx.text)
                   if not matcher.brand(w) and not matcher.category(w)
                   and w.lower() not in {"find", "show", "search", "i", "me", "please", "can", "could", "do", "any"}]
        res = _search(ctx, **params)
        note = None
        missing = [w for w in unknown if not any(w.lower() in f"{p.name} {p.brand or ''}".lower() for p in res.products)]
        if missing:
            stripped = " ".join(w for w in (query or "").split() if w not in missing)
            if not res.products and stripped:
                res = _search(ctx, **{**params, "query": stripped})
            if res.products:
                note = (f"I couldn't find any {', '.join(missing)} products on GenOra. "
                        f"Here are the closest matches{' for ' + stripped if stripped else ''} from other brands:")
        if not res.products and params["category"]:
            res = _search(ctx, **{**params, "query": None})
        if not res.products:
            return WorkflowResult(WorkflowStatus.COMPLETED,
                                  f"I couldn't find products matching “{query or ctx.text}”. Try different words or fewer filters.",
                                  suggestions=["Show me popular products"])
        remember(ctx, res.products[:8])
        title = f"Results for “{params['query']}”" if params["query"] else "Search results"
        text = note or f"I found {res.total} product{'s' if res.total != 1 else ''}. Here are the top matches:"
        return WorkflowResult(
            WorkflowStatus.COMPLETED, text, [ProductListBlock(title=title, products=[card(p) for p in res.products[:8]])],
            suggestions=["Compare the first two", "Show reviews for the first one", "Any discounts?"],
            facts=[text, *[f"{p.name}: {money(p.final_price)}" for p in res.products[:5]]],
        )


# ============================================================================ compare
class CompareWorkflow(Workflow):
    name = "compare"
    intents = ("compare",)
    MAX = 4

    def _targets(self, ctx: WorkflowContext) -> list[ProductSummary]:
        state = ctx.state
        ordinals = extract_ordinals(ctx.text)
        top_n = extract_top_n(ctx.text)
        refers = re.search(r"\b(these|those|them|all|both|the top|the first|results)\b", ctx.text, re.I)
        ids: list[str] = []
        if ordinals and state.referenced_products:
            ids = [state.referenced_products[i].id for i in ordinals if -len(state.referenced_products) <= i < len(state.referenced_products)]
        elif (top_n or refers) and state.referenced_products:
            n = top_n or (2 if re.search(r"\bboth\b", ctx.text, re.I) else 3)
            ids = [p.id for p in state.referenced_products[:n]]
        if ids:
            return [product_by_id(ctx, i) for i in ids[: self.MAX]]
        names = split_compare_targets(ctx.text)
        found: list[ProductSummary] = []
        for name in names[: self.MAX]:
            res = ctx.try_call("resolve_product", reference=name)
            if res.ok and res.output.candidates:  # type: ignore[union-attr]
                cand = res.output.candidates[0]  # type: ignore[union-attr]
                if all(cand.id != f.id for f in found):
                    found.append(cand)
        if len(found) < 2 and state.focus_product and all(f.id != state.focus_product.id for f in found):
            found.insert(0, product_by_id(ctx, state.focus_product.id))
        return found

    def run(self, ctx: WorkflowContext) -> WorkflowResult:
        ctx.status("Identifying products to compare…")
        products = self._targets(ctx)
        if len(products) < 2:
            return WorkflowResult.ask(ctx.state, self.name, "choice",
                                      "Which products should I compare? Name two or more, or search first and say "
                                      "“compare the top 3”.", [p.name for p in ctx.state.referenced_products[:3]])
        ctx.status("Comparing prices, ratings and specifications…")
        details: list[ProductDetailsOutput] = []
        insights: list[dict[str, Any]] = []
        for p in products:
            d = ctx.call("get_product_details", product_id=p.id)
            assert isinstance(d, ProductDetailsOutput)
            details.append(d)
            r = ctx.try_call("get_review_insights", product_id=p.id)
            insights.append(r.output.insights if r.ok else {})  # type: ignore[union-attr]
        prods = [d.product for d in details]
        remember(ctx, prods)

        def best(values: list[float | None], low: bool) -> int | None:
            vals = [(v, i) for i, v in enumerate(values) if v is not None]
            if len(vals) < 2 or len({v for v, _ in vals}) == 1:
                return None
            return (min(vals) if low else max(vals))[1]

        prices = [p.final_price for p in prods]
        ratings = [p.rating_avg if p.rating_count else None for p in prods]
        rows: list[dict[str, Any]] = [
            {"label": "Price", "values": [money(v) for v in prices], "highlight": best(prices, True), "source": "catalog"},
            {"label": "List price", "values": [money(p.price) for p in prods], "highlight": None, "source": "catalog"},
            {"label": "Rating", "values": [f"{p.rating_avg:.1f}★ ({p.rating_count})" if p.rating_count else "No reviews"
                                          for p in prods], "highlight": best(ratings, False), "source": "reviews"},
            {"label": "Seller", "values": [p.seller_name for p in prods], "highlight": None, "source": "catalog"},
            {"label": "Availability", "values": [("In stock" if p.stock > 5 else f"Only {p.stock} left") if p.in_stock
                                                 else "Out of stock" for p in prods], "highlight": None, "source": "catalog"},
            {"label": "Active offer", "values": [p.offer_name or "—" for p in prods], "highlight": None, "source": "catalog"},
        ]
        keys = Counter(k for d in details for k in d.attributes)
        for key, _ in keys.most_common(10):
            vals = [d.attributes.get(key) for d in details]
            rendered = [(", ".join(map(str, v)) if isinstance(v, list) else ("Yes" if v is True else "No" if v is False else str(v)))
                        if v is not None else "—" for v in vals]
            numeric = [float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None for v in vals]
            lower_better = key in ("weight_kg", "weight_g", "drop_mm")
            higher_better = key.endswith(("_gb", "_hours", "_days", "_mah", "_mp", "_hz")) or key in ("capacity_l",)
            hl = best(numeric, True) if lower_better else best(numeric, False) if higher_better else None
            rows.append({"label": key.replace("_", " ").capitalize(), "values": rendered, "highlight": hl, "source": "catalog"})
        rows.append({"label": "Pros (from reviews)", "values": [", ".join(i.get("top_positive", [])) or "—" for i in insights],
                     "highlight": None, "source": "reviews"})
        rows.append({"label": "Cons (from reviews)", "values": [", ".join(i.get("top_negative", [])) or "—" for i in insights],
                     "highlight": None, "source": "reviews"})

        cheapest = prods[prices.index(min(prices))]
        rated = [p for p in prods if p.rating_count]
        top_rated = max(rated, key=lambda p: (p.rating_avg, p.rating_count)) if rated else None
        summary = [f"Cheapest: **{cheapest.name}** at {money(cheapest.final_price)}."]
        if top_rated:
            summary.append(f"Highest rated: **{top_rated.name}** ({top_rated.rating_avg:.1f}★ from {top_rated.rating_count} reviews).")
        text = f"Here's a side-by-side comparison of {len(prods)} products. " + " ".join(summary)
        return WorkflowResult(
            WorkflowStatus.COMPLETED, text,
            [ComparisonBlock(products=[card(p) for p in prods], rows=rows, notes=[
                "“—” means the seller did not provide that detail; GenOra does not guess missing specifications.",
                "Pros and cons are derived from customer reviews, not verified specifications."])],
            suggestions=[f"Add {cheapest.name} to my cart", "Any discounts on these?"],
            facts=[text],
        )


# ============================================================================ image search
class ImageSearchWorkflow(Workflow):
    name = "image_search"
    intents = ("image_search",)

    def run(self, ctx: WorkflowContext) -> WorkflowResult:
        attachments = list(ctx.tool_ctx.attachments)
        if not attachments:
            return WorkflowResult(WorkflowStatus.NEEDS_CLARIFICATION,
                                  "Please attach a photo of the product and I'll look for similar items.")
        ctx.status("Analyzing the image…")
        res = ctx.try_call("analyze_product_image", attachment_id=attachments[-1])
        if not res.ok:
            unavailable = res.error_code in ("PROVIDER_UNAVAILABLE", "TOOL_EXECUTION_FAILED")
            msg = ("Image search is currently unavailable — no vision-capable model is configured for this marketplace, "
                   "so I can't analyse photos. Describe the product in words (type, colour, brand) and I'll search for it."
                   if unavailable else f"I couldn't analyse that image: {res.error_message}")
            return WorkflowResult(WorkflowStatus.COMPLETED, msg, [NoticeBlock(level="warning", text=msg)],
                                  suggestions=["Find black running shoes", "Show me mirrorless cameras"])
        analysis = res.output
        assert isinstance(analysis, ImageAnalysisOutput)
        ctx.status("Searching for similar products…")
        cat = _matcher(ctx).category(f"{analysis.category_hint or ''} {analysis.product_type}")
        out = _search(ctx, query=analysis.search_query, category=cat.slug if cat else None, limit=8, mode="hybrid")
        if not out.products and cat:
            out = _search(ctx, query=analysis.search_query, limit=8)
        blocks: list[Any] = [ImageAnalysisBlock(analysis=analysis.model_dump())]
        if not out.products:
            text = (f"I think this is a {analysis.product_type}, but I couldn't find similar products in the catalog.")
            return WorkflowResult(WorkflowStatus.COMPLETED, text, blocks)
        remember(ctx, out.products)
        traits = ", ".join(filter(None, [analysis.product_type, *analysis.colors[:2], *analysis.materials[:1]]))
        text = (f"It looks like a {traits} (confidence {analysis.confidence:.0%}). These catalog items are the closest "
                f"matches by the extracted attributes:")
        blocks.append(ProductListBlock(title="Similar products", products=[card(p) for p in out.products],
                                       note=f"Matched on: {analysis.search_query}"))
        return WorkflowResult(WorkflowStatus.COMPLETED, text, blocks, suggestions=["Compare the first two"])


# ============================================================================ bundles / accessories
class BundleWorkflow(Workflow):
    name = "bundle"
    intents = ("bundle",)

    def run(self, ctx: WorkflowContext) -> WorkflowResult:
        try:
            product = resolve_target(ctx, purpose="find accessories for")
        except Unresolved as u:
            return u.result
        ctx.status("Finding compatible accessories…")
        acc = ctx.call("find_accessories", product_id=product.id, limit=6)
        assert isinstance(acc, AccessoriesOutput)
        ctx.status("Checking bundle availability…")
        bundles = ctx.call("get_product_bundles", product_id=product.id)
        assert isinstance(bundles, ProductBundlesOutput)
        remember(ctx, acc.accessories, focus=product)
        ctx.state.slots["last_bundles"] = [{"id": b.id, "name": b.name} for b in bundles.bundles if b.available]
        lines = []
        if bundles.bundles:
            b = max(bundles.bundles, key=lambda x: x.savings)
            lines.append(f"**{b.name}** bundles it with {len(b.products) - 1} item(s) for {money(b.bundle_price)} "
                         f"(save {money(b.savings)}).")
        if acc.accessories:
            lines.append("Compatible add-ons from the catalog: " + ", ".join(a.name for a in acc.accessories[:4]) + ".")
        if not lines:
            text = f"I couldn't find accessories or bundles for {product.name} in the catalog right now."
        else:
            text = f"Great pairings for **{product.name}**:\n" + "\n".join(lines)
        bundle_dicts = [{**b.model_dump(exclude={"products"}), "products": [card(p) for p in b.products]}
                        for b in bundles.bundles]
        suggestions = [f"Add the {bundles.bundles[0].name} to my cart"] if bundles.bundles else []
        return WorkflowResult(
            WorkflowStatus.COMPLETED, text,
            [BundleBlock(product=card(product), bundles=bundle_dicts, accessories=[card(a) for a in acc.accessories],
                         note="; ".join(f"{a.name}: {acc.compatibility[a.id]}" for a in acc.accessories if a.id in acc.compatibility)
                         or None)],
            suggestions=suggestions + ["Any discounts on this?"], facts=[text],
        )


# ============================================================================ offers
class OffersWorkflow(Workflow):
    name = "offers"
    intents = ("offers",)

    def run(self, ctx: WorkflowContext) -> WorkflowResult:
        try:
            product = resolve_target(ctx, purpose="check discounts for")
        except Unresolved as u:
            return u.result
        ctx.status("Checking available offers…")
        out = ctx.call("get_product_offers", product_id=product.id)
        assert isinstance(out, ProductOffersOutput)
        details = ctx.call("get_product_details", product_id=product.id)
        assert isinstance(details, ProductDetailsOutput)
        remember(ctx, [product], focus=product)
        base = product.sale_price if product.sale_price is not None else product.price
        suggestions: list[str] = []
        if not out.offers:
            text = f"There are no active offers on **{product.name}** right now. The current price is {money(product.final_price)}."
        else:
            best = out.offers[0]
            text = (f"**{product.name}** has {len(out.offers)} active offer{'s' if len(out.offers) > 1 else ''}. "
                    f"The best one, “{best.name}”, takes {money(best.discount_per_unit)} off ({money(base)} → "
                    f"{money(best.price_after_offer)}). Offers apply automatically in your cart — no code needed.")
            if not best.eligible_for_single_unit:
                text += f" Note: it requires buying at least {best.min_quantity}."
        if product.sale_price is not None and product.sale_price < product.price:
            text += f" It's also already on sale from {money(product.price)}."
        if details.negotiable:
            text += " The seller also accepts price offers."
            suggestions.append(f"Can I get it for {money(round(product.final_price * 0.95, 0))}?")
        return WorkflowResult(
            WorkflowStatus.COMPLETED, text,
            [OffersBlock(product=card(product), offers=[o.model_dump(mode="json") for o in out.offers],
                         note="Only offers currently active in the marketplace are shown.")],
            suggestions=suggestions + ["Add it to my cart"], facts=[text],
        )


# ============================================================================ negotiation
class NegotiateWorkflow(ConfirmableWorkflow):
    name = "negotiate"
    intents = ("negotiate",)

    def run(self, ctx: WorkflowContext) -> WorkflowResult:
        try:
            product = resolve_target(ctx, purpose="make an offer on")
        except Unresolved as u:
            return u.result
        remember(ctx, [product], focus=product)
        ctx.status("Checking the seller's negotiation rules…")
        policy = ctx.call("check_negotiation_policy", product_id=product.id)
        assert isinstance(policy, NegotiationPolicyOutput)
        if not policy.negotiable:
            return WorkflowResult(WorkflowStatus.COMPLETED,
                                  f"{policy.reason or 'This product is not open to offers'}. "
                                  f"The current price of **{product.name}** is {money(policy.current_price)}.",
                                  suggestions=["Any discounts on this?"])
        price = extract_offer_price(ctx.text)
        if price is None:
            return WorkflowResult.ask(ctx.state, self.name, "offer_price",
                                      f"The seller accepts offers on **{product.name}** (currently "
                                      f"{money(policy.current_price)}). What price would you like to offer?")
        offered = float(price)
        if offered >= policy.current_price:
            return WorkflowResult(WorkflowStatus.COMPLETED,
                                  f"{money(offered)} is at or above the current price of {money(policy.current_price)} — "
                                  "no need to negotiate, you can add it to your cart directly.",
                                  suggestions=["Add it to my cart"])
        pct = (1 - offered / policy.current_price) * 100
        action = PendingAction(
            tool="submit_negotiation", args={"product_id": product.id, "offered_price": round(offered, 2)},
            summary=f"Submit an offer of {money(offered)} for {product.name}", workflow=self.name,
            details=[f"Current price: {money(policy.current_price)} ({pct:.1f}% below)",
                     "The seller's automated pricing rules respond immediately",
                     "If accepted, the price is reserved for 1 unit and applied at checkout",
                     "No payment is taken until you check out"],
        )
        return WorkflowResult.confirm(ctx.state, action,
                                      f"I can submit an offer of **{money(offered)}** for **{product.name}** "
                                      f"(currently {money(policy.current_price)}). Shall I send it to the seller?")

    def on_confirmed(self, ctx: WorkflowContext, action: PendingAction, result: ToolResult) -> WorkflowResult:
        if not result.ok:
            return WorkflowResult.failed(f"The offer wasn't submitted: {result.error_message}", result.error_code or "FAILED")
        out = result.output
        assert isinstance(out, NegotiationResultOutput)
        block = NegotiationBlock(product={"id": action.args.get("product_id"), "name": out.product_name},
                                 outcome=out.model_dump(mode="json"))
        expires = f"{out.expires_at:%b %d, %H:%M} UTC" if out.expires_at else "the expiry time"
        if out.status == "accepted":
            return WorkflowResult(WorkflowStatus.COMPLETED,
                                  f"Good news — the seller accepted **{money(out.agreed_price)}** for {out.product_name}. "
                                  f"It's reserved for you until {expires} and applies automatically at checkout (1 unit).",
                                  [block], ["Add it to my cart"])
        if out.counter_price is not None:
            verb = "countered at" if out.status == "countered" else "can't accept that, but offers"
            counter = PendingAction(
                tool="accept_counter_offer", args={"negotiation_id": out.id},
                summary=f"Accept the counter-offer of {money(out.counter_price)} for {out.product_name}",
                workflow=self.name, details=[f"Valid until {expires}", "Reserved for 1 unit, applied at checkout"],
            )
            return WorkflowResult.confirm(ctx.state, counter,
                                          f"The seller {verb} **{money(out.counter_price)}** for {out.product_name} "
                                          f"(you offered {money(out.offered_price)}). Would you like to accept?", [block])
        return WorkflowResult(WorkflowStatus.COMPLETED, f"The seller declined the offer: {out.reason}.", [block])


# ============================================================================ reviews
class ReviewsWorkflow(Workflow):
    name = "reviews"
    intents = ("reviews",)

    def run(self, ctx: WorkflowContext) -> WorkflowResult:
        try:
            product = resolve_target(ctx, purpose="summarise reviews for")
        except Unresolved as u:
            return u.result
        ctx.status("Reading customer reviews…")
        out = ctx.call("get_review_insights", product_id=product.id)
        assert isinstance(out, ReviewInsightsOutput)
        remember(ctx, [product], focus=product)
        ins = out.insights
        text = f"**{product.name}** — {ins.get('summary', '')}"
        themes = ins.get("themes", [])
        if themes:
            quote = next((t["examples_positive"][0] for t in themes if t.get("examples_positive")), None)
            if quote:
                text += f" One reviewer wrote: “{quote}.”"
        return WorkflowResult(
            WorkflowStatus.COMPLETED, text,
            [ReviewSummaryBlock(product=card(product), insights=ins, disclaimer=out.disclaimer)],
            suggestions=["Compare it with similar products", "Any discounts on this?"], facts=[text, out.disclaimer],
        )


# ============================================================================ external prices
class ExternalPricesWorkflow(Workflow):
    name = "external_prices"
    intents = ("external_prices",)

    def run(self, ctx: WorkflowContext) -> WorkflowResult:
        try:
            product = resolve_target(ctx, purpose="compare prices for")
        except Unresolved as u:
            return u.result
        ctx.status("Checking external price sources…")
        out = ctx.call("get_external_prices", product_id=product.id)
        assert isinstance(out, ExternalPricesOutput)
        remember(ctx, [product], focus=product)
        if not out.providers_configured:
            note = ("External marketplace prices are unavailable: no licensed price-data provider is configured, "
                    "and GenOra does not scrape or estimate other stores' prices.")
            text = f"I can't compare prices with other marketplaces right now. {note} Our price for **{product.name}** is {money(out.our_price)}."
        elif not out.quotes:
            note = "The configured providers returned no data for this product."
            text = f"None of the configured price sources have data for **{product.name}**. Our price is {money(out.our_price)}."
        else:
            cheaper = [q for q in out.quotes if q.price < out.our_price]
            test = any(q.is_test_data for q in out.quotes)
            note = "Quotes marked TEST DATA come from a mock provider and are not real prices." if test else \
                "Prices come from configured external data providers at the time shown."
            text = (f"I found {len(out.quotes)} external quote(s) for **{product.name}** (our price {money(out.our_price)}). "
                    + (f"{len(cheaper)} source(s) list it for less." if cheaper else "Our price is the lowest among them."))
        return WorkflowResult(
            WorkflowStatus.COMPLETED, text,
            [ExternalPricesBlock(product=card(product), our_price=out.our_price,
                                 quotes=[q.model_dump(mode="json") for q in out.quotes],
                                 providers_configured=out.providers_configured, note=note)],
            facts=[text],
        )


# ============================================================================ add to cart
class AddToCartWorkflow(ConfirmableWorkflow):
    name = "add_to_cart"
    intents = ("add_to_cart",)

    def run(self, ctx: WorkflowContext) -> WorkflowResult:
        bundles = ctx.state.slots.get("last_bundles") or []
        if re.search(r"\b(bundle|kit|set)\b", ctx.text, re.I) and bundles:
            chosen = next((b for b in bundles if b["name"].lower() in ctx.text.lower()), bundles[0])
            action = PendingAction(tool="add_bundle_to_cart", args={"bundle_id": chosen["id"]},
                                   summary=f"Add the {chosen['name']} bundle to your cart", workflow=self.name,
                                   details=["All bundle items are added together", "The bundle discount applies at checkout"])
            return WorkflowResult.confirm(ctx.state, action, f"Add the **{chosen['name']}** bundle to your cart?")
        try:
            product = resolve_target(ctx, purpose="add to your cart")
        except Unresolved as u:
            return u.result
        qty = extract_quantity(ctx.text) or 1
        if not product.in_stock:
            return WorkflowResult(WorkflowStatus.COMPLETED, f"Sorry, **{product.name}** is out of stock right now.")
        if qty > product.stock:
            return WorkflowResult(WorkflowStatus.COMPLETED,
                                  f"Only {product.stock} unit(s) of **{product.name}** are available.")
        remember(ctx, [product], focus=product)
        action = PendingAction(
            tool="add_to_cart", args={"product_id": product.id, "quantity": qty},
            summary=f"Add {qty} × {product.name} to your cart", workflow=self.name,
            details=[f"Current price: {money(product.final_price)} each", "Final totals are calculated at checkout"],
        )
        return WorkflowResult.confirm(ctx.state, action,
                                      f"Add **{qty} × {product.name}** ({money(product.final_price)} each) to your cart?")

    def on_confirmed(self, ctx: WorkflowContext, action: PendingAction, result: ToolResult) -> WorkflowResult:
        if not result.ok:
            return WorkflowResult.failed(f"I couldn't add that to your cart: {result.error_message}",
                                         result.error_code or "FAILED")
        out = result.output
        assert isinstance(out, CartSummaryOutput)
        return WorkflowResult(WorkflowStatus.COMPLETED,
                              f"Added {out.added} to your cart. Your cart now has {out.item_count} item(s) — "
                              f"total {money(out.total)}.", suggestions=["Go to checkout", "What goes well with it?"])


# ============================================================================ details
class ProductDetailsWorkflow(Workflow):
    name = "product_details"
    intents = ("product_details",)

    def run(self, ctx: WorkflowContext) -> WorkflowResult:
        try:
            product = resolve_target(ctx, purpose="describe")
        except Unresolved as u:
            return u.result
        d = ctx.call("get_product_details", product_id=product.id)
        assert isinstance(d, ProductDetailsOutput)
        remember(ctx, [d.product], focus=d.product)
        specs = [f"{k.replace('_', ' ')}: {', '.join(map(str, v)) if isinstance(v, list) else v}"
                 for k, v in list(d.attributes.items())[:6]]
        first = d.description.split("\n")[0]
        text = (f"**{d.product.name}** by {d.product.brand or d.product.seller_name} — {money(d.product.final_price)}. "
                f"{first}" + (f"\nKey specs: {'; '.join(specs)}." if specs else ""))
        return WorkflowResult(WorkflowStatus.COMPLETED, text,
                              [ProductListBlock(title=d.product.name, products=[card(d.product)])],
                              suggestions=["What do reviews say?", "What goes well with it?", "Any discounts?"],
                              facts=[text])


# ============================================================================ recommendations
class RecommendationsWorkflow(Workflow):
    name = "recommendations"
    intents = ("recommendations",)

    def run(self, ctx: WorkflowContext) -> WorkflowResult:
        ctx.status("Personalising recommendations…")
        strategy = "popular" if re.search(r"\b(popular|trending|best ?sellers?)\b", ctx.text, re.I) else "for_you"
        out = ctx.call("get_recommendations", strategy=strategy, limit=6)
        assert isinstance(out, ProductListOutput)
        if not out.products:
            return WorkflowResult(WorkflowStatus.COMPLETED, "I don't have recommendations yet — try searching for something.")
        remember(ctx, out.products)
        title = "Popular right now" if strategy == "popular" else "Picked for you"
        return WorkflowResult(WorkflowStatus.COMPLETED, f"{title}:", [ProductListBlock(title=title, products=[card(p) for p in out.products])],
                              suggestions=["Compare the first two"])


# ============================================================================ greeting / help
NOVA_CAPABILITIES = [
    "Find products from a description of your needs and budget",
    "Search the catalog and compare products side by side",
    "Find similar products from a photo (when a vision model is configured)",
    "Suggest accessories and bundles that go with a product",
    "Check active discounts and make price offers to sellers who accept them",
    "Summarise what customers say in reviews",
    "Add items to your cart (always after your confirmation)",
]


class HelpWorkflow(Workflow):
    name = "help"
    intents = ("greeting", "help")

    def run(self, ctx: WorkflowContext) -> WorkflowResult:
        hello = "Hi! I'm Nova, your GenOra shopping assistant." if ctx.intent.intent == "greeting" else "Here's how I can help:"
        text = hello + "\n" + "\n".join(f"• {c}" for c in NOVA_CAPABILITIES)
        return WorkflowResult(WorkflowStatus.COMPLETED, text, suggestions=[
            "I need a laptop under $1000 for programming", "Find running shoes", "What's popular right now?"])


def budget_label(b: Budget) -> str:
    if b.min is not None and b.max is not None:
        return f"{money(float(b.min))}–{money(float(b.max))}"
    if b.max is not None:
        return f"under {money(float(b.max))}"
    if b.min is not None:
        return f"over {money(float(b.min))}"
    return "any budget"


__all__ = [
    "AddToCartWorkflow", "BundleWorkflow", "CompareWorkflow", "ExternalPricesWorkflow", "HelpWorkflow",
    "ImageSearchWorkflow", "NOVA_CAPABILITIES", "NegotiateWorkflow", "OffersWorkflow", "ProductDetailsWorkflow",
    "ProductDiscoveryWorkflow", "ProductSearchWorkflow", "RecommendationsWorkflow", "ReviewsWorkflow",
    "budget_label",
]
