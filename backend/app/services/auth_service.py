"""Registration, login, token rotation, logout, password reset and e-mail verification."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AuthenticationError, ConflictError, ValidationFailed
from app.core.principal import Principal
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    generate_opaque_token,
    hash_password,
    hash_token,
    password_needs_rehash,
    utcnow,
    verify_password,
)
from app.integrations.email import get_email_sender
from app.models.commerce import Cart, Wishlist
from app.models.enums import AuthTokenPurpose, RoleName, SellerStatus
from app.models.identity import AuthToken, BuyerProfile, RefreshToken, Role, SellerProfile, User, UserRole
from app.schemas.auth import MeResponse, RegisterRequest, SellerSummary
from app.services.audit import audit


@dataclass
class IssuedTokens:
    access_token: str
    expires_in: int
    refresh_token: str
    refresh_expires_in: int


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:120] or "store"


def load_user(db: Session, user_id: uuid.UUID) -> User | None:
    return db.scalar(select(User).where(User.id == user_id, User.deleted_at.is_(None)))


def build_principal(db: Session, user: User) -> Principal:
    roles = frozenset(user.role_names)
    perms: set[str] = set()
    for ur in user.user_roles:
        perms.update(p.code for p in ur.role.permissions)
    seller_id = None
    if RoleName.SELLER in roles:
        seller = db.scalar(
            select(SellerProfile).where(
                SellerProfile.user_id == user.id,
                SellerProfile.status == SellerStatus.ACTIVE,
                SellerProfile.deleted_at.is_(None),
            )
        )
        seller_id = seller.id if seller else None
    return Principal(
        user_id=user.id, email=user.email, full_name=user.full_name, roles=roles,
        permissions=frozenset(perms), seller_id=seller_id,
    )


def me_response(db: Session, user: User) -> MeResponse:
    principal = build_principal(db, user)
    seller = db.scalar(select(SellerProfile).where(SellerProfile.user_id == user.id))
    return MeResponse(
        id=user.id, email=user.email, full_name=user.full_name, roles=sorted(principal.roles),
        permissions=sorted(principal.permissions), is_email_verified=user.is_email_verified,
        created_at=user.created_at,
        seller=SellerSummary(id=seller.id, store_name=seller.store_name, slug=seller.slug, status=seller.status.value)
        if seller else None,
    )


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    # ----------------------------------------------------------- register
    def register(self, data: RegisterRequest, ip: str | None = None) -> User:
        if self.db.scalar(select(User.id).where(User.email == data.email)):
            raise ConflictError("An account with this e-mail already exists", code="EMAIL_TAKEN")
        roles = {r.name: r for r in self.db.scalars(select(Role))}
        user = User(email=data.email, password_hash=hash_password(data.password), full_name=data.full_name)
        wanted = [RoleName.BUYER] + ([RoleName.SELLER] if data.account_type == "seller" else [])
        user.user_roles = [UserRole(role_id=roles[r].id) for r in wanted]
        self.db.add(user)
        self.db.flush()
        self.db.add_all([BuyerProfile(user_id=user.id), Cart(user_id=user.id), Wishlist(user_id=user.id)])
        if data.account_type == "seller":
            if not data.store_name:
                raise ValidationFailed("store_name is required for seller accounts", code="STORE_NAME_REQUIRED")
            if self.db.scalar(select(SellerProfile.id).where(func.lower(SellerProfile.store_name) == data.store_name.lower())):
                raise ConflictError("Store name is already taken", code="STORE_NAME_TAKEN")
            slug = _slugify(data.store_name)
            if self.db.scalar(select(SellerProfile.id).where(SellerProfile.slug == slug)):
                slug = f"{slug}-{uuid.uuid4().hex[:6]}"
            self.db.add(SellerProfile(user_id=user.id, store_name=data.store_name, slug=slug,
                                      support_email=data.email, status=SellerStatus.ACTIVE))
        self._issue_email_verification(user)
        audit(self.db, user.id, "auth.register", "user", user.id, {"account_type": data.account_type}, ip)
        self.db.commit()
        return user

    # -------------------------------------------------------------- login
    def authenticate(self, email: str, password: str) -> User:
        user = self.db.scalar(select(User).where(User.email == email, User.deleted_at.is_(None)))
        if user is None:
            verify_password(password, DUMMY_PASSWORD_HASH)  # equalise timing
            raise AuthenticationError("Invalid e-mail or password", code="INVALID_CREDENTIALS")
        if not verify_password(password, user.password_hash):
            raise AuthenticationError("Invalid e-mail or password", code="INVALID_CREDENTIALS")
        if not user.is_active:
            raise AuthenticationError("This account has been disabled", code="ACCOUNT_DISABLED")
        if password_needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)
        user.last_login_at = utcnow()
        return user

    def issue_tokens(self, user: User, *, family_id: uuid.UUID | None = None, user_agent: str | None = None,
                     ip: str | None = None) -> IssuedTokens:
        principal = build_principal(self.db, user)
        access, ttl = create_access_token(user.id, sorted(principal.roles), principal.seller_id)
        raw = generate_opaque_token()
        refresh_ttl = timedelta(days=self.settings.refresh_token_ttl_days)
        rt = RefreshToken(
            user_id=user.id, token_hash=hash_token(raw), family_id=family_id or uuid.uuid4(),
            expires_at=utcnow() + refresh_ttl, user_agent=(user_agent or "")[:255], ip_address=ip,
        )
        self.db.add(rt)
        self.db.flush()
        return IssuedTokens(access, ttl, raw, int(refresh_ttl.total_seconds()))

    def login(self, email: str, password: str, *, user_agent: str | None, ip: str | None) -> tuple[User, IssuedTokens]:
        user = self.authenticate(email, password)
        tokens = self.issue_tokens(user, user_agent=user_agent, ip=ip)
        audit(self.db, user.id, "auth.login", "user", user.id, ip=ip)
        self.db.commit()
        return user, tokens

    # ------------------------------------------------------------ refresh
    def refresh(self, raw_token: str, *, user_agent: str | None, ip: str | None) -> tuple[User, IssuedTokens]:
        token = self.db.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token)).with_for_update()
        )
        if token is None:
            raise AuthenticationError("Invalid refresh token", code="REFRESH_INVALID")
        now = utcnow()
        if token.revoked_at is not None:
            # Reuse of a rotated token → likely theft: revoke the entire family.
            self._revoke_family(token.family_id)
            audit(self.db, token.user_id, "auth.refresh_reuse_detected", "refresh_token", token.id, ip=ip)
            self.db.commit()
            raise AuthenticationError("Refresh token has been revoked", code="REFRESH_REUSED")
        if token.expires_at <= now:
            raise AuthenticationError("Refresh token has expired", code="REFRESH_EXPIRED")
        user = load_user(self.db, token.user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("Account is not active", code="ACCOUNT_DISABLED")
        tokens = self.issue_tokens(user, family_id=token.family_id, user_agent=user_agent, ip=ip)
        token.revoked_at = now
        token.replaced_by_id = self.db.scalar(
            select(RefreshToken.id).where(RefreshToken.token_hash == hash_token(tokens.refresh_token))
        )
        self.db.commit()
        return user, tokens

    def logout(self, raw_token: str | None) -> None:
        if not raw_token:
            return
        token = self.db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token)))
        if token and token.revoked_at is None:
            self._revoke_family(token.family_id)
            audit(self.db, token.user_id, "auth.logout", "user", token.user_id)
        self.db.commit()

    def revoke_all_sessions(self, user_id: uuid.UUID) -> None:
        self.db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )

    def _revoke_family(self, family_id: uuid.UUID) -> None:
        self.db.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )

    # ------------------------------------------------ password reset / verify
    def _create_auth_token(self, user: User, purpose: AuthTokenPurpose, ttl: timedelta) -> str:
        raw = generate_opaque_token()
        self.db.add(AuthToken(user_id=user.id, purpose=purpose, token_hash=hash_token(raw), expires_at=utcnow() + ttl))
        return raw

    def _consume_auth_token(self, raw: str, purpose: AuthTokenPurpose) -> User:
        token = self.db.scalar(
            select(AuthToken).where(AuthToken.token_hash == hash_token(raw), AuthToken.purpose == purpose).with_for_update()
        )
        if token is None or token.used_at is not None or token.expires_at <= utcnow():
            raise ValidationFailed("The link is invalid or has expired", code="TOKEN_INVALID")
        user = load_user(self.db, token.user_id)
        if user is None:
            raise ValidationFailed("The link is invalid or has expired", code="TOKEN_INVALID")
        token.used_at = utcnow()
        return user

    def _issue_email_verification(self, user: User) -> None:
        raw = self._create_auth_token(
            user, AuthTokenPurpose.EMAIL_VERIFICATION, timedelta(hours=self.settings.email_verification_ttl_hours)
        )
        link = f"{self.settings.public_base_url}/verify-email?token={raw}"
        get_email_sender().send(self.db, to=user.email, subject="Verify your GenOra account",
                                body=f"Hi {user.full_name},\n\nConfirm your e-mail address: {link}\n",
                                template="email_verification")

    def request_password_reset(self, email: str, ip: str | None = None) -> None:
        """Always succeeds (no account enumeration)."""
        user = self.db.scalar(select(User).where(User.email == email, User.deleted_at.is_(None)))
        if user and user.is_active:
            raw = self._create_auth_token(
                user, AuthTokenPurpose.PASSWORD_RESET, timedelta(minutes=self.settings.password_reset_ttl_minutes)
            )
            link = f"{self.settings.public_base_url}/reset-password?token={raw}"
            get_email_sender().send(self.db, to=user.email, subject="Reset your GenOra password",
                                    body=f"Reset your password: {link}\nThis link expires in "
                                         f"{self.settings.password_reset_ttl_minutes} minutes.",
                                    template="password_reset")
            audit(self.db, user.id, "auth.password_reset_requested", "user", user.id, ip=ip)
        self.db.commit()

    def reset_password(self, raw: str, new_password: str) -> None:
        user = self._consume_auth_token(raw, AuthTokenPurpose.PASSWORD_RESET)
        user.password_hash = hash_password(new_password)
        self.revoke_all_sessions(user.id)
        audit(self.db, user.id, "auth.password_reset", "user", user.id)
        self.db.commit()

    def verify_email(self, raw: str) -> None:
        user = self._consume_auth_token(raw, AuthTokenPurpose.EMAIL_VERIFICATION)
        user.is_email_verified = True
        self.db.commit()

    def resend_verification(self, user: User) -> None:
        if not user.is_email_verified:
            self._issue_email_verification(user)
        self.db.commit()

    def change_password(self, user: User, current: str, new: str) -> None:
        if not verify_password(current, user.password_hash):
            raise AuthenticationError("Current password is incorrect", code="INVALID_CREDENTIALS")
        user.password_hash = hash_password(new)
        self.revoke_all_sessions(user.id)
        audit(self.db, user.id, "auth.password_changed", "user", user.id)
        self.db.commit()
