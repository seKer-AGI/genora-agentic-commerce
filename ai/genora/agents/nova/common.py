"""Helpers shared by Nova workflows: product reference resolution and presentation."""

from __future__ import annotations

import re
from typing import Any

from genora.contracts.commerce import ProductDetailsOutput, ProductSummary, ResolveProductOutput
from genora.core.memory import ProductRef
from genora.core.workflow import ToolFailed, WorkflowContext, WorkflowResult, WorkflowStatus
from genora.nlu.extractors import extract_ordinals, mentions_reference, product_phrase

_PRONOUN_WITH_NOUN = re.compile(r"\b(this|that|the same)\s+([a-z0-9\- ]{2,40}?)(?:\b|$)", re.I)
_GENERIC_NOUNS = {"product", "item", "one", "thing", "model", "listing", "deal"}


def money(v: float | None) -> str:
    return f"${v:,.2f}" if v is not None else "—"


def card(p: ProductSummary) -> dict[str, Any]:
    return {
        "id": p.id, "slug": p.slug, "name": p.name, "brand": p.brand, "price": p.price, "sale_price": p.sale_price,
        "final_price": p.final_price, "currency": p.currency, "rating_avg": p.rating_avg, "rating_count": p.rating_count,
        "image_url": p.image_url, "url": p.url, "seller_name": p.seller_name, "in_stock": p.in_stock, "stock": p.stock,
        "offer_name": p.offer_name, "category": p.category,
    }


def ref(p: ProductSummary) -> ProductRef:
    return ProductRef(id=p.id, name=p.name, price=p.final_price)


def remember(ctx: WorkflowContext, products: list[ProductSummary], focus: ProductSummary | None = None) -> None:
    ctx.state.remember_products([ref(p) for p in products])
    if focus is not None:
        ctx.state.set_focus(ref(focus))
    elif len(products) == 1:
        ctx.state.set_focus(ref(products[0]))


def product_by_id(ctx: WorkflowContext, product_id: str) -> ProductSummary:
    out = ctx.call("get_product_details", product_id=product_id)
    assert isinstance(out, ProductDetailsOutput)
    return out.product


def _focus_matches(focus: ProductRef, phrase: str | None) -> bool:
    if not phrase:
        return True
    words = {w for w in re.findall(r"[a-z0-9]+", phrase.lower()) if w not in _GENERIC_NOUNS}
    if not words:
        return True
    name = focus.name.lower()
    return any(w in name for w in words) or len(words) <= 2


class Unresolved(Exception):
    def __init__(self, result: WorkflowResult) -> None:
        super().__init__(result.text)
        self.result = result


def resolve_target(ctx: WorkflowContext, *, purpose: str) -> ProductSummary:
    """Resolve which product the user means. Raises Unresolved with a clarification result if unsure.

    Order: ordinal references to the last results → explicit product names → the product in focus.
    """
    text = ctx.text
    state = ctx.state
    ordinals = extract_ordinals(text)
    if ordinals and state.referenced_products:
        idx = ordinals[0]
        try:
            chosen = state.referenced_products[idx]
        except IndexError as exc:
            raise Unresolved(WorkflowResult(
                WorkflowStatus.NEEDS_CLARIFICATION,
                f"I only showed {len(state.referenced_products)} products — which one do you mean?",
                suggestions=[p.name for p in state.referenced_products[:4]])) from exc
        return product_by_id(ctx, chosen.id)

    phrase = product_phrase(text)
    answered_choice = ctx.intent.slots.get("answered") in ("product", "choice")
    if answered_choice:
        phrase = text.strip(" ?.!")
    pronoun = mentions_reference(text) or bool(_PRONOUN_WITH_NOUN.search(text))
    if state.focus_product and (not phrase or (pronoun and _focus_matches(state.focus_product, phrase))):
        return product_by_id(ctx, state.focus_product.id)

    if phrase:
        ctx.status("Looking up the product…")
        try:
            res = ctx.call("resolve_product", reference=phrase)
        except ToolFailed:
            res = None
        if isinstance(res, ResolveProductOutput) and res.candidates:
            if res.confident or len(res.candidates) == 1:
                return res.candidates[0]
            ctx.state.remember_products([ref(p) for p in res.candidates[:4]])
            raise Unresolved(WorkflowResult.ask(
                ctx.state, ctx.intent.intent, "product",
                f"I found several products matching “{phrase}”. Which one would you like me to {purpose}?",
                [p.name for p in res.candidates[:4]]))
    if state.referenced_products and len(state.referenced_products) == 1:
        return product_by_id(ctx, state.referenced_products[0].id)
    raise Unresolved(WorkflowResult.ask(
        ctx.state, ctx.intent.intent, "product",
        f"Which product would you like me to {purpose}? You can name it or pick one from a search.",
        [p.name for p in state.referenced_products[:4]]))
