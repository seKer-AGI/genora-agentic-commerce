"""Audit trail helper for security-relevant and administrative actions."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import redact
from app.models.identity import AuditLog


def audit(
    db: Session,
    actor_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: object | None = None,
    data: dict[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_user_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            data=redact(data or {}),
            ip_address=ip,
        )
    )


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()
