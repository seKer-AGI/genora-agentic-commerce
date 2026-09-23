"""Shared plumbing for backend tool implementations."""

from __future__ import annotations

import functools
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from genora.contracts.commerce import ProductSummary
from genora.core.tools import ToolContext
from genora.errors import ProviderUnavailableError, ToolExecutionError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.principal import Principal
from app.models.catalog import Product
from app.services.pricing import PricingEngine

F = TypeVar("F", bound=Callable[..., Any])


@dataclass
class AgentServices:
    """Opaque service locator placed in ToolContext.services by the runtime (server-side only)."""

    db: Session
    principal: Principal


def services(ctx: ToolContext) -> AgentServices:
    svc = ctx.services
    if not isinstance(svc, AgentServices):
        raise ToolExecutionError("tool context is missing backend services", code="TOOL_MISCONFIGURED")
    return svc


def guarded(fn: F) -> F:
    """Convert application errors into structured tool errors (never leaking internals)."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except AppError as exc:
            raise ToolExecutionError(exc.message, code=exc.code) from exc
        except ProviderUnavailableError as exc:
            raise ToolExecutionError(exc.message, code="PROVIDER_UNAVAILABLE") from exc

    return wrapper  # type: ignore[return-value]


def summarize_product(ctx: ToolContext, p: Product, engine: PricingEngine, score: float | None = None) -> ProductSummary:
    """Product → tool contract. Registers the product and its price as grounded facts for this turn."""
    quote = engine.quote(p)
    ctx.seen_product_ids.add(str(p.id))
    for v in (quote.final_price, p.price, p.sale_price):
        if v is not None:
            ctx.seen_prices.add(f"{float(v):.2f}")
    return ProductSummary(
        id=str(p.id), slug=p.slug, name=p.name, brand=p.brand, price=float(p.price),
        sale_price=float(p.sale_price) if p.sale_price is not None else None, final_price=float(quote.final_price),
        currency=p.currency, rating_avg=float(p.rating_avg), rating_count=p.rating_count, in_stock=p.stock > 0,
        stock=p.stock, seller_id=str(p.seller_id), seller_name=p.seller.store_name,
        category=p.category.name if p.category else None, category_slug=p.category.slug if p.category else None,
        image_url=p.primary_image_url, url=f"/products/{p.slug}", tags=list(p.tags or []),
        attributes=dict(p.attributes or {}), offer_name=quote.offer.name if quote.offer else None, score=score,
    )


def note_price(ctx: ToolContext, *values: float | None) -> None:
    for v in values:
        if v is not None:
            ctx.seen_prices.add(f"{float(v):.2f}")
