"""Vector store abstraction. `PgVectorProductStore` uses the HNSW index on products.embedding.

Another backend (Qdrant, Pinecone, Weaviate, …) can implement :class:`VectorStore` without touching
search or recommendation logic.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models.catalog import Product


@dataclass(frozen=True)
class VectorHit:
    id: uuid.UUID
    similarity: float  # cosine similarity in [-1, 1]


class VectorStore(ABC):
    @abstractmethod
    def nearest(
        self,
        vector: Sequence[float],
        k: int,
        *,
        base_query: Select[Any] | None = None,
        exclude: Sequence[uuid.UUID] = (),
    ) -> list[VectorHit]: ...


class PgVectorProductStore(VectorStore):
    def __init__(self, db: Session) -> None:
        self.db = db

    def nearest(
        self,
        vector: Sequence[float],
        k: int,
        *,
        base_query: Select[Any] | None = None,
        exclude: Sequence[uuid.UUID] = (),
    ) -> list[VectorHit]:
        distance = Product.embedding.cosine_distance(list(vector))
        stmt = base_query if base_query is not None else select(Product.id)
        stmt = (
            stmt.with_only_columns(Product.id, distance.label("distance"))
            .where(Product.embedding.is_not(None))
            .order_by(distance)
            .limit(k)
        )
        if exclude:
            stmt = stmt.where(Product.id.not_in(list(exclude)))
        return [VectorHit(pid, 1.0 - float(d)) for pid, d in self.db.execute(stmt).all()]
