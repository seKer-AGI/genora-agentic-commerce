"""Authentication request/response schemas."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

_PASSWORD_RULES = (
    (re.compile(r"[a-z]"), "a lowercase letter"),
    (re.compile(r"[A-Z]"), "an uppercase letter"),
    (re.compile(r"\d"), "a digit"),
)


def _validate_password(v: str) -> str:
    missing = [label for rx, label in _PASSWORD_RULES if not rx.search(v)]
    if missing:
        raise ValueError("password must contain " + ", ".join(missing))
    return v


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=120)
    account_type: Literal["buyer", "seller"] = "buyer"
    store_name: str | None = Field(default=None, min_length=2, max_length=120)

    _pw = field_validator("password")(_validate_password)

    @field_validator("full_name", "store_name")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        return v.strip() if v else v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: MeResponse


class RefreshRequest(BaseModel):
    """Refresh token may be sent in the body by non-browser clients; browsers use the httpOnly cookie."""

    refresh_token: str | None = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    new_password: str = Field(min_length=8, max_length=128)

    _pw = field_validator("new_password")(_validate_password)


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)

    _pw = field_validator("new_password")(_validate_password)


class SellerSummary(BaseModel):
    id: uuid.UUID
    store_name: str
    slug: str
    status: str


class MeResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    roles: list[str]
    permissions: list[str]
    is_email_verified: bool
    created_at: datetime
    seller: SellerSummary | None = None


class UpdateProfileRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    phone: str | None = Field(default=None, max_length=32, pattern=r"^[+0-9 ()\-]{6,32}$")


TokenResponse.model_rebuild()
