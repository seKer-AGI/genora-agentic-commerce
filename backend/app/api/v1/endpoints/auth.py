"""/api/v1/auth — registration, login, token refresh, logout, password reset, e-mail verification."""

from __future__ import annotations

from fastapi import APIRouter, Cookie, Request, Response, status

from app.api.deps import CurrentPrincipal, DbSession, client_ip
from app.core.config import get_settings
from app.core.errors import AuthenticationError
from app.core.rate_limit import rate_limiter
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MeResponse,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UpdateProfileRequest,
    VerifyEmailRequest,
)
from app.schemas.common import Message
from app.services.auth_service import AuthService, IssuedTokens, load_user, me_response

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_refresh_cookie(response: Response, tokens: IssuedTokens) -> None:
    s = get_settings()
    response.set_cookie(
        s.refresh_cookie_name, tokens.refresh_token, max_age=tokens.refresh_expires_in, httponly=True,
        secure=s.refresh_cookie_secure or s.is_production, samesite="lax", path=f"{s.api_prefix}/auth",
    )


def _limit(request: Request, bucket: str) -> None:
    rate_limiter.hit(f"{bucket}:{client_ip(request)}", get_settings().auth_rate_limit_per_minute)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, request: Request, response: Response, db: DbSession) -> TokenResponse:
    _limit(request, "register")
    svc = AuthService(db)
    user = svc.register(body, ip=client_ip(request))
    tokens = svc.issue_tokens(user, user_agent=request.headers.get("user-agent"), ip=client_ip(request))
    db.commit()
    _set_refresh_cookie(response, tokens)
    return TokenResponse(access_token=tokens.access_token, expires_in=tokens.expires_in, user=me_response(db, user))


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, response: Response, db: DbSession) -> TokenResponse:
    _limit(request, "login")
    user, tokens = AuthService(db).login(
        body.email, body.password, user_agent=request.headers.get("user-agent"), ip=client_ip(request)
    )
    _set_refresh_cookie(response, tokens)
    return TokenResponse(access_token=tokens.access_token, expires_in=tokens.expires_in, user=me_response(db, user))


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    request: Request,
    response: Response,
    db: DbSession,
    body: RefreshRequest | None = None,
    genora_refresh: str | None = Cookie(default=None),
) -> TokenResponse:
    raw = (body.refresh_token if body else None) or genora_refresh
    if not raw:
        raise AuthenticationError("Refresh token missing", code="REFRESH_MISSING")
    user, tokens = AuthService(db).refresh(raw, user_agent=request.headers.get("user-agent"), ip=client_ip(request))
    _set_refresh_cookie(response, tokens)
    return TokenResponse(access_token=tokens.access_token, expires_in=tokens.expires_in, user=me_response(db, user))


@router.post("/logout", response_model=Message)
def logout(
    response: Response, db: DbSession, body: RefreshRequest | None = None,
    genora_refresh: str | None = Cookie(default=None),
) -> Message:
    AuthService(db).logout((body.refresh_token if body else None) or genora_refresh)
    s = get_settings()
    response.delete_cookie(s.refresh_cookie_name, path=f"{s.api_prefix}/auth")
    return Message(message="Logged out")


@router.get("/me", response_model=MeResponse)
def me(principal: CurrentPrincipal, db: DbSession) -> MeResponse:
    user = load_user(db, principal.user_id)
    assert user is not None
    return me_response(db, user)


@router.patch("/me", response_model=MeResponse)
def update_me(body: UpdateProfileRequest, principal: CurrentPrincipal, db: DbSession) -> MeResponse:
    user = load_user(db, principal.user_id)
    assert user is not None
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.commit()
    return me_response(db, user)


@router.post("/change-password", response_model=Message)
def change_password(body: ChangePasswordRequest, principal: CurrentPrincipal, db: DbSession) -> Message:
    user = load_user(db, principal.user_id)
    assert user is not None
    AuthService(db).change_password(user, body.current_password, body.new_password)
    return Message(message="Password changed. Other sessions were signed out.")


@router.post("/forgot-password", response_model=Message, status_code=status.HTTP_202_ACCEPTED)
def forgot_password(body: ForgotPasswordRequest, request: Request, db: DbSession) -> Message:
    _limit(request, "forgot")
    AuthService(db).request_password_reset(body.email, ip=client_ip(request))
    return Message(message="If an account exists for that e-mail, a reset link has been sent.")


@router.post("/reset-password", response_model=Message)
def reset_password(body: ResetPasswordRequest, request: Request, db: DbSession) -> Message:
    _limit(request, "reset")
    AuthService(db).reset_password(body.token, body.new_password)
    return Message(message="Password updated. Please sign in again.")


@router.post("/verify-email", response_model=Message)
def verify_email(body: VerifyEmailRequest, db: DbSession) -> Message:
    AuthService(db).verify_email(body.token)
    return Message(message="E-mail verified")


@router.post("/resend-verification", response_model=Message, status_code=status.HTTP_202_ACCEPTED)
def resend_verification(principal: CurrentPrincipal, db: DbSession) -> Message:
    user = load_user(db, principal.user_id)
    assert user is not None
    AuthService(db).resend_verification(user)
    return Message(message="Verification e-mail queued")
