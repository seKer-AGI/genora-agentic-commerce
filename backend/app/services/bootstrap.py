"""Idempotent bootstrap of reference data required in every environment (roles, permissions, settings)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import DEFAULT_ROLE_PERMISSIONS, PERMISSION_DESCRIPTIONS, ROLE_DESCRIPTIONS
from app.models.identity import Permission, Role, SystemSetting

DEFAULT_SETTINGS: dict[str, tuple[Any, str]] = {
    "agents.nova.enabled": (True, "Enable GenOra Nova (buyer agent)"),
    "agents.astra.enabled": (True, "Enable GenOra Astra (seller agent)"),
    "agents.apex.enabled": (False, "GenOra Apex is planned / not implemented; cannot be enabled"),
    "agents.max_tool_calls_per_turn": (8, "Upper bound on tool calls in a single agent turn"),
    "agents.use_llm_when_available": (True, "Use the configured LLM for intent detection and phrasing"),
    "agents.negotiation.enabled": (True, "Allow Nova to submit negotiation proposals to sellers"),
    "search.hybrid_enabled": (True, "Fuse keyword and vector search results"),
    "search.semantic_weight": (0.5, "Relative weight of vector results in hybrid ranking (0-1)"),
    "reviews.auto_approve": (True, "Auto-approve reviews that pass the automated moderation filter"),
}


def ensure_reference_data(db: Session) -> None:
    perms = {p.code: p for p in db.scalars(select(Permission))}
    for code, desc in PERMISSION_DESCRIPTIONS.items():
        if code not in perms:
            perms[code] = Permission(code=code, description=desc)
            db.add(perms[code])
    db.flush()

    roles = {r.name: r for r in db.scalars(select(Role))}
    for name, codes in DEFAULT_ROLE_PERMISSIONS.items():
        role = roles.get(name)
        if role is None:
            role = Role(name=name, description=ROLE_DESCRIPTIONS[name])
            role.permissions = [perms[c] for c in sorted(codes)]
            db.add(role)
    db.flush()

    existing = set(db.scalars(select(SystemSetting.key)))
    for key, (value, desc) in DEFAULT_SETTINGS.items():
        if key not in existing:
            db.add(SystemSetting(key=key, value=value, description=desc))
    db.flush()
