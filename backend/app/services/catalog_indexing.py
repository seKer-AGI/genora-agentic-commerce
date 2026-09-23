"""Keeps derived search fields (keywords, embeddings) of products in sync."""

from __future__ import annotations

from collections.abc import Sequence

from genora.providers.embeddings import EmbeddingProvider

from app.models.catalog import Product
from app.services.ai_runtime import get_embedding_provider


def build_keywords(product: Product, category_name: str | None = None) -> str:
    parts: list[str] = list(product.tags or [])
    for key, value in (product.attributes or {}).items():
        if isinstance(value, list):
            parts.extend(str(v) for v in value)
        elif isinstance(value, bool):
            if value:
                parts.append(key.replace("_", " "))
        else:
            parts.append(str(value))
    if category_name:
        parts.append(category_name)
    return " ".join(p for p in parts if p)[:4000]


def embedding_text(product: Product, category_name: str | None = None) -> str:
    """Text representation used for semantic indexing (name/brand/category weighted by repetition)."""
    return " ".join(
        filter(
            None,
            [
                product.name,
                product.name,
                product.brand or "",
                category_name or "",
                category_name or "",
                " ".join(product.tags or []),
                build_keywords(product),
                (product.description or "")[:600],
            ],
        )
    )


def index_products(
    products: Sequence[Product],
    category_names: dict[object, str] | None = None,
    provider: EmbeddingProvider | None = None,
) -> None:
    """Refresh keywords + embeddings in place (caller commits)."""
    if not products:
        return
    provider = provider or get_embedding_provider()
    names = category_names or {}
    texts = []
    for p in products:
        cname = names.get(p.category_id) or (p.category.name if p.category else None)
        p.keywords = build_keywords(p, cname)
        texts.append(embedding_text(p, cname))
    vectors = provider.embed(texts)
    for p, vec in zip(products, vectors, strict=True):
        p.embedding = vec
        p.embedding_model = f"{provider.name}:{provider.model}"
