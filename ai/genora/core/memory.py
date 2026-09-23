"""Conversational working memory (per session).

Stored as JSON in the host's session store. Contains only shopping/seller context needed to continue a
conversation (budget, category, referenced products, pending action) — never credentials, payment
details or other sensitive personal data.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from pydantic import BaseModel, Field

PENDING_ACTION_TTL = timedelta(minutes=15)
MAX_REFERENCED = 10


def _now() -> datetime:
    return datetime.now(UTC)


class ProductRef(BaseModel):
    id: str
    name: str
    price: float | None = None


class PendingAction(BaseModel):
    """A write action proposed by an agent that only runs after explicit user confirmation."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    tool: str
    args: dict[str, Any]
    summary: str
    details: list[str] = Field(default_factory=list)
    workflow: str
    created_at: datetime = Field(default_factory=_now)
    expires_at: datetime = Field(default_factory=lambda: _now() + PENDING_ACTION_TTL)

    @property
    def expired(self) -> bool:
        return _now() >= self.expires_at


class Clarification(BaseModel):
    """What the agent is waiting for (e.g. the budget for a product discovery)."""

    intent: str
    slot: str
    question: str
    options: list[str] = Field(default_factory=list)


class SessionState(BaseModel):
    slots: dict[str, Any] = Field(default_factory=dict)  # budget_max, budget_min, category, brand, use_case, …
    referenced_products: list[ProductRef] = Field(default_factory=list)  # last results shown, in order
    focus_product: ProductRef | None = None  # the product currently being discussed
    last_intent: str | None = None
    pending_action: PendingAction | None = None
    clarification: Clarification | None = None
    turns: int = 0

    def remember_products(self, products: list[ProductRef]) -> None:
        if products:
            self.referenced_products = products[:MAX_REFERENCED]

    def set_focus(self, product: ProductRef | None) -> None:
        self.focus_product = product

    def clear_task(self) -> None:
        self.clarification = None

    def public_view(self) -> dict[str, Any]:
        """What the UI may show about the agent's memory."""
        return {
            "slots": self.slots,
            "focus_product": self.focus_product.model_dump() if self.focus_product else None,
            "referenced_products": [p.model_dump() for p in self.referenced_products],
            "pending_action": self.pending_action.model_dump(mode="json") if self.pending_action else None,
            "awaiting": self.clarification.slot if self.clarification else None,
        }


class MemoryStore(Protocol):
    def load(self, session_id: uuid.UUID) -> SessionState: ...

    def save(self, session_id: uuid.UUID, state: SessionState) -> None: ...


class InMemoryStore:
    """Process-local store used by tests and tooling."""

    def __init__(self) -> None:
        self._data: dict[uuid.UUID, dict[str, Any]] = {}

    def load(self, session_id: uuid.UUID) -> SessionState:
        return SessionState.model_validate(self._data.get(session_id, {}))

    def save(self, session_id: uuid.UUID, state: SessionState) -> None:
        self._data[session_id] = state.model_dump(mode="json")
