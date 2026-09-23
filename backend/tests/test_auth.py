"""Authentication: registration, login, refresh rotation, logout, password reset, token validation."""

from __future__ import annotations

import time

import jwt
from sqlalchemy import select

from app.core.config import get_settings
from app.models import EmailOutbox, RefreshToken, User

API = "/api/v1/auth"


def _register(client, email="new.user@example.com", **kw):  # type: ignore[no-untyped-def]
    body = {"email": email, "password": "Str0ngPass!", "full_name": "New User", **kw}
    return client.post(f"{API}/register", json=body)


def test_register_buyer_hashes_password_and_queues_verification(client, db):  # type: ignore[no-untyped-def]
    r = _register(client)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["user"]["roles"] == ["BUYER"]
    assert "genora_refresh" in r.cookies
    user = db.scalar(select(User).where(User.email == "new.user@example.com"))
    assert user.password_hash.startswith("$argon2")
    assert "Str0ngPass!" not in user.password_hash
    assert db.scalar(select(EmailOutbox).where(EmailOutbox.to_email == "new.user@example.com")) is not None


def test_register_seller_creates_store(client):  # type: ignore[no-untyped-def]
    r = _register(client, "shop.owner@example.com", account_type="seller", store_name="Test Emporium")
    assert r.status_code == 201, r.text
    user = r.json()["user"]
    assert set(user["roles"]) == {"BUYER", "SELLER"}
    assert user["seller"]["store_name"] == "Test Emporium"


def test_register_seller_requires_store_name(client):  # type: ignore[no-untyped-def]
    r = _register(client, "nostore@example.com", account_type="seller")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "STORE_NAME_REQUIRED"


def test_register_rejects_duplicate_and_weak_password(client):  # type: ignore[no-untyped-def]
    assert _register(client, "buyer@genora.dev").json()["error"]["code"] == "EMAIL_TAKEN"
    r = client.post(f"{API}/register", json={"email": "weak@example.com", "password": "password", "full_name": "Weak"})
    assert r.status_code == 422
    assert r.json()["success"] is False
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_register_cannot_self_assign_admin(client):  # type: ignore[no-untyped-def]
    r = _register(client, "sneaky@example.com", account_type="admin")
    assert r.status_code == 422


def test_login_success_and_failure_shapes(client):  # type: ignore[no-untyped-def]
    ok = client.post(f"{API}/login", json={"email": "buyer@genora.dev", "password": "Buyer#2026!"})
    assert ok.status_code == 200
    assert ok.json()["token_type"] == "bearer"
    bad = client.post(f"{API}/login", json={"email": "buyer@genora.dev", "password": "wrong"})
    assert bad.status_code == 401
    assert bad.json() == {"success": False, "error": {"code": "INVALID_CREDENTIALS", "message": "Invalid e-mail or password"}}
    unknown = client.post(f"{API}/login", json={"email": "nobody@example.com", "password": "whatever1A"})
    assert unknown.json()["error"]["code"] == "INVALID_CREDENTIALS"  # no account enumeration


def test_me_requires_valid_token(client, buyer_headers):  # type: ignore[no-untyped-def]
    assert client.get(f"{API}/me").status_code == 401
    assert client.get(f"{API}/me", headers={"Authorization": "Bearer not-a-jwt"}).json()["error"]["code"] == "TOKEN_INVALID"
    me = client.get(f"{API}/me", headers=buyer_headers)
    assert me.status_code == 200
    assert "cart:manage" in me.json()["permissions"]


def test_expired_and_forged_tokens_rejected(client, db):  # type: ignore[no-untyped-def]
    s = get_settings()
    user = db.scalar(select(User).where(User.email == "buyer@genora.dev"))
    now = int(time.time())
    base = {"sub": str(user.id), "roles": ["ADMIN"], "type": "access", "iss": s.jwt_issuer, "iat": now - 100}
    expired = jwt.encode({**base, "exp": now - 10}, s.jwt_secret.get_secret_value(), algorithm="HS256")
    r = client.get(f"{API}/me", headers={"Authorization": f"Bearer {expired}"})
    assert r.json()["error"]["code"] == "TOKEN_EXPIRED"
    forged = jwt.encode({**base, "exp": now + 600}, "attacker-secret-attacker-secret-1234", algorithm="HS256")
    assert client.get(f"{API}/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
    none_alg = jwt.encode({**base, "exp": now + 600}, key=None, algorithm="none")  # type: ignore[arg-type]
    assert client.get(f"{API}/me", headers={"Authorization": f"Bearer {none_alg}"}).status_code == 401


def test_role_claim_in_token_is_not_trusted(client, db):  # type: ignore[no-untyped-def]
    """Even a validly signed token claiming ADMIN gets only the DB-backed permissions of the user."""
    s = get_settings()
    user = db.scalar(select(User).where(User.email == "buyer@genora.dev"))
    now = int(time.time())
    token = jwt.encode({"sub": str(user.id), "roles": ["ADMIN"], "type": "access", "iss": s.jwt_issuer,
                        "iat": now, "exp": now + 600}, s.jwt_secret.get_secret_value(), algorithm="HS256")
    r = client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_refresh_rotation_and_reuse_detection(client, db):  # type: ignore[no-untyped-def]
    login = client.post(f"{API}/login", json={"email": "buyer@genora.dev", "password": "Buyer#2026!"})
    first = login.cookies["genora_refresh"]
    r1 = client.post(f"{API}/refresh", json={"refresh_token": first})
    assert r1.status_code == 200
    second = r1.cookies["genora_refresh"]
    assert second != first
    # reusing the rotated token revokes the whole family
    reuse = client.post(f"{API}/refresh", json={"refresh_token": first})
    assert reuse.json()["error"]["code"] == "REFRESH_REUSED"
    after = client.post(f"{API}/refresh", json={"refresh_token": second})
    assert after.status_code == 401
    # tokens are stored hashed only
    assert db.scalar(select(RefreshToken).where(RefreshToken.token_hash == first)) is None


def test_logout_revokes_refresh_token(client):  # type: ignore[no-untyped-def]
    login = client.post(f"{API}/login", json={"email": "buyer@genora.dev", "password": "Buyer#2026!"})
    token = login.cookies["genora_refresh"]
    assert client.post(f"{API}/logout", json={"refresh_token": token}).status_code == 200
    assert client.post(f"{API}/refresh", json={"refresh_token": token}).status_code == 401


def test_password_reset_flow(client, db):  # type: ignore[no-untyped-def]
    from app.core.security import generate_opaque_token, hash_token, utcnow
    from app.models import AuthToken
    from app.models.enums import AuthTokenPurpose

    r = client.post(f"{API}/forgot-password", json={"email": "nobody@example.com"})
    assert r.status_code == 202  # same response whether or not the account exists
    user = db.scalar(select(User).where(User.email == "buyer@genora.dev"))
    raw = generate_opaque_token()
    from datetime import timedelta

    db.add(AuthToken(user_id=user.id, purpose=AuthTokenPurpose.PASSWORD_RESET, token_hash=hash_token(raw),
                     expires_at=utcnow() + timedelta(minutes=10)))
    db.flush()
    ok = client.post(f"{API}/reset-password", json={"token": raw, "new_password": "NewPassw0rd!"})
    assert ok.status_code == 200, ok.text
    again = client.post(f"{API}/reset-password", json={"token": raw, "new_password": "NewPassw0rd!"})
    assert again.json()["error"]["code"] == "TOKEN_INVALID"  # single use
    assert client.post(f"{API}/login", json={"email": "buyer@genora.dev", "password": "NewPassw0rd!"}).status_code == 200


def test_login_rate_limited(client):  # type: ignore[no-untyped-def]
    codes = [client.post(f"{API}/login", json={"email": "x@example.com", "password": "Nope12345"}).status_code
             for _ in range(get_settings().auth_rate_limit_per_minute + 1)]
    assert codes[-1] == 429
