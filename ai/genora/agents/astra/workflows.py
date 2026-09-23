"""GenOra Astra — seller workflows.

All analytics come from the seller's own data via tools. Price, stock, offer and catalog changes are
proposed as pending actions and only applied after the seller confirms.
"""

from __future__ import annotations

import re
from typing import Any

from genora.contracts.seller import (
    DiscountStrategyOutput,
    ForecastOutput,
    InventoryOutput,
    ListingDraftOutput,
    OfferCreatedOutput,
    PerfItem,
    ProductChangeOutput,
    ProductPerformanceOutput,
    ResolveSellerProductOutput,
    SalesSummaryOutput,
    SellerProductRef,
)
from genora.core.blocks import (
    ForecastBlock,
    KpiBlock,
    ListingDraftBlock,
    NoticeBlock,
    RecommendationBlock,
    TableBlock,
)
from genora.core.engine import ConfirmableWorkflow
from genora.core.memory import PendingAction, ProductRef
from genora.core.tools import ToolResult
from genora.core.workflow import Workflow, WorkflowContext, WorkflowResult, WorkflowStatus
from genora.nlu.catalog import CatalogMatcher
from genora.nlu.extractors import extract_attribute_constraints, extract_offer_price


def money(v: float | None) -> str:
    return f"${v:,.2f}" if v is not None else "—"


def pct(v: float | None) -> str:
    return "n/a" if v is None else f"{'+' if v >= 0 else ''}{v:.1f}%"


def period_days(text: str, default: int = 30) -> tuple[int, str]:
    low = text.lower()
    if m := re.search(r"(?:last|past|previous)\s+(\d{1,3})\s+days?", low):
        n = max(1, min(365, int(m.group(1))))
        return n, f"the last {n} days"
    for pattern, days, label in (
        (r"\b(today|yesterday)\b", 1, "the last day"), (r"\b(this|last|past) week\b", 7, "the last 7 days"),
        (r"\b(this|last|past) month\b|\bmonthly\b", 30, "the last 30 days"),
        (r"\b(this|last|past) quarter\b|\b90 days\b", 90, "the last 90 days"),
        (r"\b(this|last|past) year\b|\bannual", 365, "the last 365 days"),
    ):
        if re.search(pattern, low):
            return days, label
    return default, f"the last {default} days"


def perf_rows(items: list[PerfItem]) -> list[dict[str, Any]]:
    return [{"product_id": i.product_id, "name": i.name, "revenue": i.revenue, "units": i.units, "orders": i.orders,
             "views": i.views, "conversion_rate": i.conversion_rate, "rating": i.rating_avg, "stock": i.stock}
            for i in items]


PERF_COLUMNS = [
    {"key": "name", "label": "Product"}, {"key": "revenue", "label": "Revenue", "format": "money"},
    {"key": "units", "label": "Units"}, {"key": "views", "label": "Views"},
    {"key": "conversion_rate", "label": "Conversion", "format": "percent"}, {"key": "stock", "label": "Stock"},
]


class _Unresolved(Exception):
    def __init__(self, result: WorkflowResult) -> None:
        super().__init__(result.text)
        self.result = result


_TARGET = re.compile(
    r"(?:of|for|on|price of|stock of|restock|discount on|offer on|sale on)\s+(?:the\s+|my\s+)?(.+?)"
    r"(?:\s+(?:to|at|by|with|from|for)\s+\$?\d.*|\s+(?:for|over)\s+(?:\d+|a|one|two)\s+(?:days?|weeks?).*|\s*\d+\s*%.*|[?.!]|$)",
    re.I)


def resolve_own_product(ctx: WorkflowContext, *, purpose: str) -> SellerProductRef:
    m = _TARGET.search(ctx.text)
    phrase = m.group(1).strip() if m else None
    if ctx.intent.slots.get("answered") in ("product", "choice"):
        phrase = ctx.text.strip(" ?.!")
    if (not phrase or re.fullmatch(r"(it|this|that|this one|that one|them)", phrase, re.I)) and ctx.state.focus_product:
        phrase = ctx.state.focus_product.name
    if not phrase:
        raise _Unresolved(WorkflowResult.ask(ctx.state, ctx.intent.intent, "product",
                                             f"Which of your products would you like to {purpose}?",
                                             [p.name for p in ctx.state.referenced_products[:4]]))
    out = ctx.call("resolve_seller_product", reference=phrase)
    assert isinstance(out, ResolveSellerProductOutput)
    if not out.candidates:
        raise _Unresolved(WorkflowResult(WorkflowStatus.NEEDS_CLARIFICATION,
                                         f"I couldn't find “{phrase}” among your products. Which product do you mean?"))
    if not out.confident and len(out.candidates) > 1:
        ctx.state.remember_products([ProductRef(id=c.id, name=c.name, price=c.price) for c in out.candidates[:4]])
        raise _Unresolved(WorkflowResult.ask(ctx.state, ctx.intent.intent, "product",
                                             f"Several of your products match “{phrase}”. Which one?",
                                             [c.name for c in out.candidates[:4]]))
    chosen = out.candidates[0]
    ctx.state.set_focus(ProductRef(id=chosen.id, name=chosen.name, price=chosen.price))
    return chosen


# ============================================================================ listing
_LISTING_NAME = re.compile(
    r"(?:listing|product page|description|title)\s+(?:for|of)\s+(?:a|an|the|this|my|our)?\s*(.+?)(?:\s+(?:priced|at|for|with|,)\s|[.?!]|$)",
    re.I)
_SELL_NAME = re.compile(r"\b(?:sell|list)\s+(?:a|an|the|this|my|our)\s+(.+?)(?:\s+(?:priced|at|for|with|,)\s|[.?!]|$)", re.I)
_WITH = re.compile(r"\bwith\s+(.+?)(?:[.?!]|$)", re.I)
_SPEC = re.compile(r"(\d+(?:\.\d+)?)\s*(gb|tb|mah|mp|hz|w|kg|g|mm|inch|in|\")\b\s*([a-z]+)?", re.I)


def parse_listing_request(text: str) -> tuple[str | None, dict[str, Any], str | None, float | None]:
    m = _LISTING_NAME.search(text) or _SELL_NAME.search(text)
    name = m.group(1).strip(" ,") if m else None
    attrs: dict[str, Any] = {}
    for c in extract_attribute_constraints(text):
        if c["op"] == ">=":
            attrs[str(c["attribute"])] = int(c["value"]) if float(c["value"]).is_integer() else c["value"]  # type: ignore[arg-type]
        elif c["op"] == "==":
            attrs[str(c["attribute"])] = c["value"]
    for num, unit, noun in _SPEC.findall(text):
        unit = unit.lower().replace('"', "in")
        if unit == "gb" and (noun or "").lower() in ("ram", "memory"):
            attrs.setdefault("ram_gb", int(float(num)))
        elif unit in ("gb", "tb") and (noun or "").lower() in ("ssd", "storage", "hdd", ""):
            attrs.setdefault("storage_gb", int(float(num) * (1024 if unit == "tb" else 1)))
        elif unit in ("inch", "in"):
            attrs.setdefault("display_in", float(num))
        elif unit == "mah":
            attrs.setdefault("battery_mah", int(float(num)))
    w = _WITH.search(text)
    notes = w.group(1).strip() if w else None
    price = None
    if pm := re.search(r"(?:priced at|price(?: is|:)?|for|at|sell(?:s|ing)? for)\s*\$\s?(\d[\d,]*(?:\.\d{1,2})?)", text, re.I):
        price = float(pm.group(1).replace(",", ""))
    return name, attrs, notes, price


class CreateListingWorkflow(ConfirmableWorkflow):
    name = "create_listing"
    intents = ("create_listing",)

    def run(self, ctx: WorkflowContext) -> WorkflowResult:
        slots = ctx.state.slots
        answered = ctx.intent.slots.get("answered")
        if answered == "price" and slots.get("listing_draft"):
            price = extract_offer_price(ctx.text)
            if price is None:
                return WorkflowResult.ask(ctx.state, self.name, "price", "What price should the product be listed at?")
            draft = slots["listing_draft"]
            draft["price"] = float(price)
            return self._propose(ctx, draft)
        if answered == "product" and slots.get("listing_request"):
            req = slots["listing_request"]
            req["name"] = ctx.text.strip(" .!?")
        else:
            name, attrs, notes, price = parse_listing_request(ctx.text)
            brand = CatalogMatcher(ctx.hints).brand(ctx.text)
            req = {"name": name, "attributes": attrs, "notes": notes, "price": price, "brand": brand}
            slots["listing_request"] = req
        if not req.get("name"):
            return WorkflowResult.ask(ctx.state, self.name, "product",
                                      "What product would you like to list? Include key specs if you have them "
                                      "(e.g. “Voltrix AeroBook 15 with 16GB RAM and 1TB SSD, $1099”).")
        ctx.status("Drafting the listing…")
        out = ctx.call("draft_listing", product_name=req["name"], brand=req.get("brand"), notes=req.get("notes"),
                       attributes=req.get("attributes", {}), price=req.get("price"))
        assert isinstance(out, ListingDraftOutput)
        draft = out.model_dump()
        draft["category_id"] = out.category_suggestions[0].id if out.category_suggestions else None
        slots["listing_draft"] = draft
        block = ListingDraftBlock(draft=draft, generated_by=out.generated_by,
                                  note="Draft only — nothing is published until you confirm. You can edit every "
                                       "field later in Products.")
        if out.price is None:
            res = WorkflowResult.ask(ctx.state, self.name, "price",
                                     "Here's a draft listing. What price should I list it at?")
            res.blocks.insert(0, block)
            return res
        return self._propose(ctx, draft, block)

    def _propose(self, ctx: WorkflowContext, draft: dict[str, Any], block: ListingDraftBlock | None = None
                 ) -> WorkflowResult:
        cats = draft.get("category_suggestions") or []
        action = PendingAction(
            tool="create_product",
            args={"name": draft["title"], "description": draft["description"], "seo_description": draft["seo_description"],
                  "sku": draft["suggested_sku"], "brand": draft.get("brand"), "category_id": draft.get("category_id"),
                  "price": draft["price"], "stock": 0, "tags": draft["tags"], "attributes": draft["attributes"],
                  "status": "draft"},
            summary=f"Save “{draft['title']}” as a draft product at {money(draft['price'])}",
            workflow=self.name,
            details=[f"Category: {cats[0]['name'] if cats else 'uncategorised'}", f"SKU: {draft['suggested_sku']}",
                     "Status: draft (not visible to buyers until you publish)", "Stock starts at 0"],
        )
        blocks = [block] if block else []
        return WorkflowResult.confirm(ctx.state, action, "Here's the draft listing. Save it as a draft product?", blocks)

    def on_confirmed(self, ctx: WorkflowContext, action: PendingAction, result: ToolResult) -> WorkflowResult:
        ctx.state.slots.pop("listing_draft", None)
        ctx.state.slots.pop("listing_request", None)
        if not result.ok:
            return WorkflowResult.failed(f"The product wasn't created: {result.error_message}", result.error_code or "FAILED")
        out = result.output
        assert isinstance(out, ProductChangeOutput)
        ctx.state.set_focus(ProductRef(id=out.product_id, name=out.name, price=out.price))
        return WorkflowResult(WorkflowStatus.COMPLETED,
                              f"Saved **{out.name}** as a draft. Add photos and stock, then publish it from your Products page.",
                              [NoticeBlock(level="success", text=f"Draft created: {out.url}")],
                              ["Set its stock to 25", "Show my low-stock products"])


# ============================================================================ inventory
class LowInventoryWorkflow(Workflow):
    name = "low_inventory"
    intents = ("low_inventory",)

    def run(self, ctx: WorkflowContext) -> WorkflowResult:
        ctx.status("Checking inventory levels…")
        low_only = not re.search(r"\b(all|full|entire|every)\b", ctx.text, re.I)
        out = ctx.call("seller_inventory", low_only=low_only)
        assert isinstance(out, InventoryOutput)
        if not out.items:
            return WorkflowResult(WorkflowStatus.COMPLETED,
                                  f"Good news — none of your {out.total_products} products are at or below their "
                                  "low-stock threshold.")
        rows = [i.model_dump() for i in out.items]
        ctx.state.remember_products([ProductRef(id=i.product_id, name=i.name) for i in out.items[:10]])
        out_of_stock = [i for i in out.items if i.available == 0]
        text = (f"{len(out.items)} product{'s are' if len(out.items) != 1 else ' is'} running low"
                + (f", including {len(out_of_stock)} out of stock" if out_of_stock else "") + ".")
        urgent = sorted(out.items, key=lambda i: (i.days_of_cover if i.days_of_cover is not None else 999))[:3]
        if urgent:
            text += " Most urgent: " + ", ".join(
                f"{i.name} ({i.available} left" + (f", ~{i.days_of_cover:.0f} days of cover)" if i.days_of_cover is not None else ")")
                for i in urgent) + "."
        return WorkflowResult(
            WorkflowStatus.COMPLETED, text,
            [TableBlock(title="Low-stock products" if low_only else "Inventory", rows=rows, columns=[
                {"key": "name", "label": "Product"}, {"key": "sku", "label": "SKU"},
                {"key": "available", "label": "Available"}, {"key": "low_stock_threshold", "label": "Threshold"},
                {"key": "sold_last_30d", "label": "Sold (30d)"}, {"key": "days_of_cover", "label": "Days of cover",
                                                                  "format": "number"}],
                note="Days of cover = available units ÷ average daily units sold over the last 30 days.")],
            suggestions=[f"Restock {urgent[0].name} to 50 units"] if urgent else [], facts=[text],
        )


# ============================================================================ sales
class SalesPerformanceWorkflow(Workflow):
    name = "sales_performance"
    intents = ("sales_performance",)

    def run(self, ctx: WorkflowContext) -> WorkflowResult:
        days, label = period_days(ctx.text)
        ctx.status("Analysing your sales…")
        s = ctx.call("seller_sales_summary", days=days)
        assert isinstance(s, SalesSummaryOutput)
        if s.orders.value == 0:
            return WorkflowResult(WorkflowStatus.COMPLETED, f"You had no orders in {label}.")
        text = (f"In {label} you made **{money(s.revenue.value)}** in revenue ({pct(s.revenue.change_pct)} vs the "
                f"previous {days} days) from **{int(s.orders.value)} orders** and {int(s.units_sold.value)} units. "
                f"Average order value was {money(s.average_order_value.value)} and conversion was "
                f"{s.conversion_rate.value:.1f}% of product views.")
        if s.top_products:
            text += f" Top seller: **{s.top_products[0].name}** ({money(s.top_products[0].revenue)})."
        if s.low_performers:
            lp = s.low_performers[0]
            text += f" Weakest: {lp.name} ({lp.units} units, {lp.views} views)."
        kpis = [
            {"label": "Revenue", "value": s.revenue.value, "format": "money", "change_pct": s.revenue.change_pct},
            {"label": "Orders", "value": s.orders.value, "format": "number", "change_pct": s.orders.change_pct},
            {"label": "Units sold", "value": s.units_sold.value, "format": "number", "change_pct": s.units_sold.change_pct},
            {"label": "Avg order value", "value": s.average_order_value.value, "format": "money",
             "change_pct": s.average_order_value.change_pct},
            {"label": "Conversion", "value": s.conversion_rate.value, "format": "percent",
             "change_pct": s.conversion_rate.change_pct},
        ]
        return WorkflowResult(
            WorkflowStatus.COMPLETED, text,
            [KpiBlock(title=f"Sales — {label}", kpis=kpis, series=s.series),
             TableBlock(title="Top products", columns=PERF_COLUMNS, rows=perf_rows(s.top_products)),
             TableBlock(title="Low-performing products", columns=PERF_COLUMNS, rows=perf_rows(s.low_performers),
                        note=s.definitions.get("revenue"))],
            suggestions=["Which products are underperforming?", "Suggest a discount strategy", "Forecast next 14 days"],
            facts=[text],
        )


class ProductPerformanceWorkflow(Workflow):
    name = "product_performance"
    intents = ("product_performance",)

    def run(self, ctx: WorkflowContext) -> WorkflowResult:
        days, label = period_days(ctx.text)
        order = "best" if re.search(r"\b(best|top|best[- ]?sellers?|winning)\b", ctx.text, re.I) and not re.search(
            r"\b(worst|under|low|not selling|slow)\b", ctx.text, re.I) else "worst"
        ctx.status("Ranking your products…")
        out = ctx.call("seller_product_performance", days=days, order=order, limit=6)
        assert isinstance(out, ProductPerformanceOutput)
        if not out.items:
            return WorkflowResult(WorkflowStatus.COMPLETED, "You don't have any active products to analyse yet.")
        ctx.state.remember_products([ProductRef(id=i.product_id, name=i.name) for i in out.items])
        insights: list[str] = []
        for i in out.items[:4]:
            if order == "worst":
                if i.views >= 40 and (i.conversion_rate or 0) < 1:
                    insights.append(f"{i.name}: {i.views} views but only {i.orders} orders — price or listing may be the issue")
                elif i.views < 20:
                    insights.append(f"{i.name}: only {i.views} views — visibility is the main problem")
                elif i.stock == 0:
                    insights.append(f"{i.name}: out of stock, which blocks sales")
                else:
                    insights.append(f"{i.name}: {i.units} units from {i.views} views")
            else:
                insights.append(f"{i.name}: {money(i.revenue)} from {i.units} units")
        head = "underperforming" if order == "worst" else "best-performing"
        text = f"Your {head} products in {label}:\n" + "\n".join(f"• {s}" for s in insights)
        return WorkflowResult(
            WorkflowStatus.COMPLETED, text,
            [TableBlock(title=f"{head.capitalize()} products — {label}", columns=PERF_COLUMNS, rows=perf_rows(out.items))],
            suggestions=["Suggest a discount strategy for these", "Show my sales this month"], facts=[text],
        )


# ============================================================================ discount strategy
class DiscountStrategyWorkflow(Workflow):
    name = "discount_strategy"
    intents = ("discount_strategy",)

    def run(self, ctx: WorkflowContext) -> WorkflowResult:
        days, label = period_days(ctx.text)
        ids: list[str] = []
        if re.search(r"\b(these|those|them)\b", ctx.text, re.I):
            ids = [p.id for p in ctx.state.referenced_products[:10]]
        ctx.status("Analysing demand, conversion and stock…")
        out = ctx.call("discount_strategy", days=max(days, 7), product_ids=ids)
        assert isinstance(out, DiscountStrategyOutput)
        if not out.suggestions:
            return WorkflowResult(WorkflowStatus.COMPLETED, "I don't have enough sales data to suggest a strategy yet.")
        discounts = [s for s in out.suggestions if s.action == "discount"]
        text = (f"Based on {label} of your store data, here's what I'd suggest for {len(out.suggestions)} product(s). "
                "Nothing has been changed — each action needs your confirmation.")
        items = [{"title": s.headline, "product_id": s.product_id, "product_name": s.product_name, "action": s.action,
                  "rationale": s.rationale, "evidence": s.evidence, "proposed_percent_off": s.proposed_percent_off}
                 for s in out.suggestions]
        suggestions = [f"Create a {int(s.proposed_percent_off)}% offer on {s.product_name} for 14 days"
                       for s in discounts[:2] if s.proposed_percent_off]
        return WorkflowResult(WorkflowStatus.COMPLETED, text,
                              [RecommendationBlock(title="Discount & pricing strategy", items=items),
                               NoticeBlock(level="info", text=f"Method: {out.method}")],
                              suggestions=suggestions, facts=[text])


# ============================================================================ write actions
class UpdatePriceWorkflow(ConfirmableWorkflow):
    name = "update_price"
    intents = ("update_price",)

    def run(self, ctx: WorkflowContext) -> WorkflowResult:
        try:
            product = resolve_own_product(ctx, purpose="reprice")
        except _Unresolved as u:
            return u.result
        m = re.search(r"\bto\s*\$\s?(\d[\d,]*(?:\.\d{1,2})?)", ctx.text) or re.search(r"\$\s?(\d[\d,]*(?:\.\d{1,2})?)", ctx.text)
        pct_m = re.search(r"\bby\s*(\d{1,2}(?:\.\d+)?)\s*%", ctx.text)
        current = product.sale_price if product.sale_price is not None else product.price
        if m:
            new = float(m.group(1).replace(",", ""))
        elif pct_m:
            sign = 1 if re.search(r"\b(raise|increase)\b", ctx.text, re.I) else -1
            new = round(current * (1 + sign * float(pct_m.group(1)) / 100), 2)
        else:
            return WorkflowResult.ask(ctx.state, self.name, "price",
                                      f"What should the new price of **{product.name}** be? (currently {money(current)})")
        sale = bool(re.search(r"\bsale price\b", ctx.text, re.I))
        if sale and new > product.price:
            return WorkflowResult(WorkflowStatus.COMPLETED,
                                  f"A sale price can't exceed the list price ({money(product.price)}).")
        change = (new - current) / current * 100 if current else 0
        args: dict[str, Any] = {"product_id": product.id}
        if sale:
            args["sale_price"] = new
        else:
            args["price"] = new
            if product.sale_price is not None:
                args["clear_sale_price"] = True
        details = [f"Current {'sale ' if sale else ''}price: {money(current)}", f"New: {money(new)} ({pct(change)})"]
        if not sale and product.sale_price is not None:
            details.append(f"The existing sale price ({money(product.sale_price)}) will be removed")
        if abs(change) > 30:
            details.append("⚠ This is a large change (over 30%) — please double-check")
        action = PendingAction(tool="update_product_price", args=args, workflow=self.name, details=details,
                               summary=f"Change the {'sale ' if sale else ''}price of {product.name} to {money(new)}")
        return WorkflowResult.confirm(ctx.state, action,
                                      f"Change the {'sale ' if sale else ''}price of **{product.name}** from "
                                      f"{money(current)} to **{money(new)}**?")

    def on_confirmed(self, ctx: WorkflowContext, action: PendingAction, result: ToolResult) -> WorkflowResult:
        if not result.ok:
            return WorkflowResult.failed(f"The price wasn't changed: {result.error_message}", result.error_code or "FAILED")
        out = result.output
        assert isinstance(out, ProductChangeOutput)
        shown = out.sale_price if out.sale_price is not None else out.price
        return WorkflowResult(WorkflowStatus.COMPLETED, f"Updated — **{out.name}** now sells for {money(shown)}.")


class UpdateStockWorkflow(ConfirmableWorkflow):
    name = "update_stock"
    intents = ("update_stock",)

    def run(self, ctx: WorkflowContext) -> WorkflowResult:
        try:
            product = resolve_own_product(ctx, purpose="restock")
        except _Unresolved as u:
            return u.result
        nums = re.findall(r"\b(\d{1,6})\s*(?:units?|pcs|pieces|items)?\b", re.sub(r"\$\s?\d[\d,.]*", "", ctx.text))
        if not nums:
            return WorkflowResult.ask(ctx.state, self.name, "quantity", f"How many units of **{product.name}** do you have?")
        qty = int(nums[-1])
        additive = bool(re.search(r"\b(add|restock with|another|more)\b", ctx.text, re.I)) and not re.search(r"\bto\b", ctx.text)
        target = product.stock + qty if additive else qty
        action = PendingAction(tool="update_stock", args={"product_id": product.id, "quantity_on_hand": target},
                               workflow=self.name, summary=f"Set stock of {product.name} to {target} units",
                               details=[f"Current available stock: {product.stock}", f"New on-hand quantity: {target}"])
        return WorkflowResult.confirm(ctx.state, action, f"Set the stock of **{product.name}** to **{target} units**?")

    def on_confirmed(self, ctx: WorkflowContext, action: PendingAction, result: ToolResult) -> WorkflowResult:
        if not result.ok:
            return WorkflowResult.failed(f"Stock wasn't updated: {result.error_message}", result.error_code or "FAILED")
        out = result.output
        assert isinstance(out, ProductChangeOutput)
        return WorkflowResult(WorkflowStatus.COMPLETED, f"Stock updated — **{out.name}** now has {out.stock} units available.")


class CreateOfferWorkflow(ConfirmableWorkflow):
    name = "create_offer"
    intents = ("create_offer",)

    def run(self, ctx: WorkflowContext) -> WorkflowResult:
        try:
            product = resolve_own_product(ctx, purpose="discount")
        except _Unresolved as u:
            return u.result
        pm = re.search(r"(\d{1,2}(?:\.\d+)?)\s*%", ctx.text)
        if not pm:
            return WorkflowResult.ask(ctx.state, self.name, "percent", f"How big a discount on **{product.name}** (e.g. 10%)?")
        percent = float(pm.group(1))
        if not 0 < percent <= 50:
            return WorkflowResult(WorkflowStatus.COMPLETED, "Offers created by Astra must be between 1% and 50% off.")
        days = 14
        if dm := re.search(r"(\d{1,2})\s*days?", ctx.text):
            days = int(dm.group(1))
        elif re.search(r"\b(a|one) week\b", ctx.text, re.I):
            days = 7
        elif wm := re.search(r"(\d)\s*weeks?", ctx.text):
            days = int(wm.group(1)) * 7
        days = max(1, min(days, 90))
        base = product.sale_price if product.sale_price is not None else product.price
        new_price = round(base * (1 - percent / 100), 2)
        action = PendingAction(
            tool="create_offer", args={"product_id": product.id, "percent_off": percent, "days": days},
            summary=f"Create a {percent:g}% offer on {product.name} for {days} days", workflow=self.name,
            details=[f"Price during the offer: {money(base)} → {money(new_price)}", f"Runs for {days} days starting now",
                     "Applies automatically to buyers; the best single offer wins"])
        return WorkflowResult.confirm(ctx.state, action,
                                      f"Create a **{percent:g}% off** offer on **{product.name}** for {days} days?")

    def on_confirmed(self, ctx: WorkflowContext, action: PendingAction, result: ToolResult) -> WorkflowResult:
        if not result.ok:
            return WorkflowResult.failed(f"The offer wasn't created: {result.error_message}", result.error_code or "FAILED")
        out = result.output
        assert isinstance(out, OfferCreatedOutput)
        return WorkflowResult(WorkflowStatus.COMPLETED,
                              f"Offer “{out.name}” is live: {out.product_name} now shows {money(out.new_final_price)} "
                              f"until {out.ends_at[:10]}.")


# ============================================================================ forecast
class ForecastWorkflow(Workflow):
    name = "forecast"
    intents = ("forecast",)

    def run(self, ctx: WorkflowContext) -> WorkflowResult:
        low = ctx.text.lower()
        horizon = 14
        if m := re.search(r"next\s+(\d{1,2})\s+days?", low):
            horizon = int(m.group(1))
        elif "next month" in low:
            horizon = 30
        elif "next week" in low:
            horizon = 7
        horizon = max(1, min(horizon, 90))
        target, entity = "revenue", None
        if re.search(r"\b(orders|sales volume|number of sales)\b", low):
            target = "sales"
        if re.search(r"\b(demand|units)\b", low):
            target = "product_demand"
            try:
                product = resolve_own_product(ctx, purpose="forecast demand for")
                entity = product.id
            except _Unresolved as u:
                return u.result
        ctx.status("Running the forecasting model…")
        out = ctx.call("run_forecast", target=target, entity_id=entity, horizon_days=horizon)
        assert isinstance(out, ForecastOutput)
        if out.status != "completed":
            return WorkflowResult(WorkflowStatus.COMPLETED, f"I couldn't produce a forecast: {out.error}")
        total = sum(p["value"] for p in out.points)
        lo = sum(p["lower"] or 0 for p in out.points)
        hi = sum(p["upper"] or 0 for p in out.points)
        unit = {"revenue": "revenue", "sales": "orders", "product_demand": "units"}[target]
        fmt = money if target == "revenue" else (lambda v: f"{v:,.0f}")
        bt = out.metrics.get("backtest", {})
        acc = f" Backtest error (sMAPE) on the last {bt.get('holdout')} days: {bt.get('smape')}%." if bt.get("smape") is not None else ""
        text = (f"Forecast for the next {horizon} days: about **{fmt(total)}** in {unit} (80% range {fmt(lo)}–{fmt(hi)}), "
                f"using the {out.model_name} model on {len(out.history)} days of history.{acc} "
                "Treat this as a statistical estimate, not a guarantee.")
        return WorkflowResult(WorkflowStatus.COMPLETED, text, [ForecastBlock(forecast=out.model_dump(mode="json"))],
                              facts=[text])


ASTRA_CAPABILITIES = [
    "Draft product listings (title, description, SEO text, tags, category) — saved only after you confirm",
    "Find products that are running low on stock",
    "Summarise sales performance: revenue, orders, units, AOV, conversion",
    "Identify best- and worst-performing products",
    "Suggest data-driven discount strategies",
    "Change prices, stock and offers — always with your confirmation",
    "Forecast revenue, orders or product demand",
]


class AstraHelpWorkflow(Workflow):
    name = "help"
    intents = ("greeting", "help")

    def run(self, ctx: WorkflowContext) -> WorkflowResult:
        hello = "Hi! I'm Astra, your seller assistant." if ctx.intent.intent == "greeting" else "Here's what I can do:"
        return WorkflowResult(WorkflowStatus.COMPLETED, hello + "\n" + "\n".join(f"• {c}" for c in ASTRA_CAPABILITIES),
                              suggestions=["How did my sales perform this month?", "Which products are running low?",
                                           "Which products are underperforming?"])
