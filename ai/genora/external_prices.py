"""External marketplace price comparison.

Only licensed, terms-compliant data sources may be plugged in (retailer APIs, affiliate feeds, price
data vendors). GenOra never scrapes websites and never estimates prices. When no provider is
configured, callers must say that external prices are unavailable.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class ProductIdentity:
    name: str
    brand: str | None
    sku: str
    gtin: str | None = None


@dataclass
class ExternalPrice:
    provider: str
    marketplace: str
    price: float
    currency: str
    url: str | None
    in_stock: bool | None
    retrieved_at: datetime
    is_test_data: bool = False


class ExternalMarketplaceProvider(ABC):
    name: str
    marketplace: str
    is_test_data: bool = False

    @abstractmethod
    def lookup(self, product: ProductIdentity) -> ExternalPrice | None: ...


class StaticFeedProvider(ExternalMarketplaceProvider):
    """Reads a licensed price feed (JSON list of {sku|name, marketplace, price, currency, url, in_stock})."""

    name = "static_feed"
    marketplace = "feed"

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self._rows: list[dict[str, object]] | None = None

    def _load(self) -> list[dict[str, object]]:
        if self._rows is None:
            self._rows = json.loads(self.path.read_text(encoding="utf-8")) if self.path.is_file() else []
        return self._rows

    def lookup(self, product: ProductIdentity) -> ExternalPrice | None:
        for row in self._load():
            if row.get("sku") == product.sku or str(row.get("name", "")).lower() == product.name.lower():
                return ExternalPrice(self.name, str(row.get("marketplace", "feed")), float(row["price"]),  # type: ignore[arg-type]
                                     str(row.get("currency", "USD")), row.get("url"), row.get("in_stock"),  # type: ignore[arg-type]
                                     datetime.now(UTC))
        return None


class _MockProvider(ExternalMarketplaceProvider):
    """Deterministic TEST-ONLY provider. Its prices are synthetic and always flagged `is_test_data`."""

    is_test_data = True
    spread: tuple[float, float] = (0.9, 1.1)

    def __init__(self, reference_prices: dict[str, float]) -> None:
        self.reference = reference_prices

    def lookup(self, product: ProductIdentity) -> ExternalPrice | None:
        base = self.reference.get(product.sku)
        if base is None:
            return None
        h = int(hashlib.sha256(f"{self.name}:{product.sku}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
        lo, hi = self.spread
        return ExternalPrice(self.name, self.marketplace, round(base * (lo + (hi - lo) * h), 2), "USD", None,
                             h > 0.2, datetime.now(UTC), is_test_data=True)


class MockMarketplaceProviderA(_MockProvider):
    name = "mock_a"
    marketplace = "Mock Marketplace A (test data)"


class MockMarketplaceProviderB(_MockProvider):
    name = "mock_b"
    marketplace = "Mock Marketplace B (test data)"
    spread = (0.95, 1.2)
