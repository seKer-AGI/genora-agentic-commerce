"""The authenticated caller, resolved server-side from the access token + database."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from app.core.errors import PermissionDenied
from app.models.enums import RoleName


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    email: str
    full_name: str
    roles: frozenset[str]
    permissions: frozenset[str] = field(default_factory=frozenset)
    seller_id: uuid.UUID | None = None

    @property
    def is_admin(self) -> bool:
        return RoleName.ADMIN in self.roles

    @property
    def is_seller(self) -> bool:
        return RoleName.SELLER in self.roles and self.seller_id is not None

    def has(self, permission: str) -> bool:
        return permission in self.permissions

    def require(self, *permissions: str) -> None:
        """Require ANY of the given permissions."""
        if not any(p in self.permissions for p in permissions):
            raise PermissionDenied()

    def require_seller(self) -> uuid.UUID:
        if self.seller_id is None:
            raise PermissionDenied("A seller profile is required for this action", code="SELLER_REQUIRED")
        return self.seller_id
