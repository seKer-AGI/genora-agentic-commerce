"""External marketplace price lookups through configured, terms-compliant providers only."""

from __future__ import annotations

import logging
from functools import lru_cache

from genora.external_prices import (
    ExternalMarketplaceProvider,
    ExternalPrice,
    MockMarketplaceProviderA,
    MockMarketplaceProviderB,
    ProductIdentity,
    StaticFeedProvider,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import log_event
from app.models.catalog import Product

logger = logging.getLogger("app.external_prices")


def build_providers(db: Session) -> list[ExternalMarketplaceProvider]:
    s = get_settings()
    providers: list[ExternalMarketplaceProvider] = []
    for name in s.external_price_providers:
        if name == "static_feed" and s.external_price_feed_path:
            providers.append(StaticFeedProvider(s.external_price_feed_path))
        elif name in ("mock_a", "mock_b"):
            if s.is_production:
                log_event(logger, "mock_price_provider_refused_in_production", logging.WARNING, provider=name)
                continue
            ref = {sku: float(price) for sku, price in db.execute(select(Product.sku, Product.price)).all()}
            providers.append((MockMarketplaceProviderA if name == "mock_a" else MockMarketplaceProviderB)(ref))
    return providers


class ExternalPriceService:
    def __init__(self, db: Session, providers: list[ExternalMarketplaceProvider] | None = None) -> None:
        self.db = db
        self.providers = providers if providers is not None else build_providers(db)

    def configured(self) -> list[str]:
        return [p.name for p in self.providers]

    def lookup(self, product: Product) -> tuple[list[ExternalPrice], list[str]]:
        identity = ProductIdentity(name=product.name, brand=product.brand, sku=product.sku)
        quotes, errors = [], []
        for provider in self.providers:
            try:
                q = provider.lookup(identity)
                if q is not None:
                    quotes.append(q)
            except Exception as exc:  # noqa: BLE001 - one failing source must not break the others
                errors.append(f"{provider.name}: unavailable")
                log_event(logger, "external_price_provider_failed", logging.WARNING, provider=provider.name,
                          error=type(exc).__name__)
        return sorted(quotes, key=lambda q: q.price), errors


@lru_cache
def mock_providers_enabled() -> bool:
    return any(n.startswith("mock") for n in get_settings().external_price_providers)
