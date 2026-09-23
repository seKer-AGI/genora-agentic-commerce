"""FastAPI dependencies: DB session, authenticated principal and permission guards."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import AuthenticationError, PermissionDenied
from app.core.logging import user_id_ctx
from app.core.principal import Principal
from app.core.security import decode_access_token
from app.db.session import get_db
from app.services.auth_service import build_principal, load_user

_bearer = HTTPBearer(auto_error=False, description="JWT access token")

DbSession = Annotated[Session, Depends(get_db)]


def _resolve(db: Session, creds: HTTPAuthorizationCredentials | None) -> Principal | None:
    if creds is None or creds.scheme.lower() != "bearer":
        return None
    payload = decode_access_token(creds.credentials)
    try:
        user_id = uuid.UUID(payload["sub"])
    except ValueError as exc:
        raise AuthenticationError("Invalid access token", code="TOKEN_INVALID") from exc
    user = load_user(db, user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Account is not active", code="ACCOUNT_DISABLED")
    principal = build_principal(db, user)
    user_id_ctx.set(str(user.id))
    return principal


def get_optional_principal(
    db: DbSession, creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]
) -> Principal | None:
    return _resolve(db, creds)


def get_principal(
    db: DbSession, creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]
) -> Principal:
    principal = _resolve(db, creds)
    if principal is None:
        raise AuthenticationError()
    return principal


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]
OptionalPrincipal = Annotated[Principal | None, Depends(get_optional_principal)]


def require_permission(*permissions: str) -> Callable[..., Principal]:
    """Dependency factory: the caller must hold ANY of the given permissions."""

    def _dep(principal: CurrentPrincipal) -> Principal:
        if not any(principal.has(p) for p in permissions):
            raise PermissionDenied()
        return principal

    return _dep


def require_seller(principal: CurrentPrincipal) -> Principal:
    if principal.seller_id is None:
        raise PermissionDenied("An active seller profile is required", code="SELLER_REQUIRED")
    return principal


SellerPrincipal = Annotated[Principal, Depends(require_seller)]


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None
