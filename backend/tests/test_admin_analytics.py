"""Admin operations, RBAC boundaries and analytics endpoints."""

from __future__ import annotations

API = "/api/v1"


def test_admin_routes_forbidden_for_non_admins(client, buyer_headers, seller_headers):  # type: ignore[no-untyped-def]
    for path in ("/admin/users", "/admin/sellers", "/admin/orders", "/admin/settings", "/admin/roles",
                 "/admin/audit-logs", "/admin/agents/workflows", "/analytics/admin/overview"):
        for h in (buyer_headers, seller_headers):
            assert client.get(f"{API}{path}", headers=h).status_code == 403, path
        assert client.get(f"{API}{path}").status_code == 401


def test_seller_routes_require_seller_profile(client, buyer_headers):  # type: ignore[no-untyped-def]
    r = client.get(f"{API}/sellers/me/products", headers=buyer_headers)
    assert r.status_code == 403 and r.json()["error"]["code"] == "SELLER_REQUIRED"


def test_admin_user_management(client, admin_headers, buyer_headers):  # type: ignore[no-untyped-def]
    users = client.get(f"{API}/admin/users", params={"q": "buyer@genora"}, headers=admin_headers).json()
    buyer = users["items"][0]
    r = client.patch(f"{API}/admin/users/{buyer['id']}", json={"is_active": False}, headers=admin_headers)
    assert r.json()["is_active"] is False
    # the deactivated user's token stops working immediately
    assert client.get(f"{API}/auth/me", headers=buyer_headers).status_code == 401


def test_admin_cannot_lock_self_out(client, admin_headers):  # type: ignore[no-untyped-def]
    me = client.get(f"{API}/auth/me", headers=admin_headers).json()
    r = client.patch(f"{API}/admin/users/{me['id']}", json={"roles": ["BUYER"]}, headers=admin_headers)
    assert r.json()["error"]["code"] == "SELF_LOCKOUT"


def test_settings_validation(client, admin_headers):  # type: ignore[no-untyped-def]
    apex = client.put(f"{API}/admin/settings/agents.apex.enabled", json={"value": True}, headers=admin_headers)
    assert apex.json()["error"]["code"] == "APEX_NOT_IMPLEMENTED"
    wrong_type = client.put(f"{API}/admin/settings/agents.nova.enabled", json={"value": "yes"}, headers=admin_headers)
    assert wrong_type.status_code == 422
    ok = client.put(f"{API}/admin/settings/search.semantic_weight", json={"value": 0.7}, headers=admin_headers)
    assert ok.json()["value"] == 0.7
    logs = client.get(f"{API}/admin/audit-logs", params={"action": "admin.setting"}, headers=admin_headers).json()
    assert logs["items"][0]["action"] == "admin.setting.update"


def test_role_permission_management(client, admin_headers):  # type: ignore[no-untyped-def]
    roles = client.get(f"{API}/admin/roles", headers=admin_headers).json()
    admin_role = next(r for r in roles if r["name"] == "ADMIN")
    r = client.put(f"{API}/admin/roles/{admin_role['id']}/permissions", json={"permissions": ["users:manage"]},
                   headers=admin_headers)
    assert r.json()["error"]["code"] == "SELF_LOCKOUT"
    bad = client.put(f"{API}/admin/roles/{admin_role['id']}/permissions", json={"permissions": ["root:all"]},
                     headers=admin_headers)
    assert bad.json()["error"]["code"] == "UNKNOWN_PERMISSION"


def test_seller_analytics_matches_database(client, db, seller_headers):  # type: ignore[no-untyped-def]
    from datetime import timedelta

    from sqlalchemy import func, select

    from app.core.security import utcnow
    from app.models import Order, SellerProfile
    from app.models.enums import OrderStatus

    ov = client.get(f"{API}/analytics/seller/overview", params={"days": 30}, headers=seller_headers).json()
    seller = db.scalar(select(SellerProfile).where(SellerProfile.slug == "voltrix-official"))
    since = utcnow() - timedelta(days=30)
    expected = db.scalar(select(func.count()).select_from(Order).where(
        Order.seller_id == seller.id, Order.placed_at >= since,
        Order.status.not_in([OrderStatus.CANCELLED, OrderStatus.REFUNDED])))
    assert ov["orders"]["value"] == expected
    assert len(ov["series"]) >= 30
    assert sum(p["orders"] for p in ov["series"]) == expected


def test_admin_overview_and_search_analytics(client, admin_headers):  # type: ignore[no-untyped-def]
    ov = client.get(f"{API}/analytics/admin/overview", headers=admin_headers).json()
    assert ov["totals"]["products"] >= 80 and ov["top_categories"] and ov["seller_performance"]
    sa = client.get(f"{API}/analytics/admin/search", headers=admin_headers).json()
    assert sa["total_searches"] > 0 and sa["top_queries"]


def test_client_event_whitelist(client, product_by_slug):  # type: ignore[no-untyped-def]
    p = product_by_slug("voltrix-aerobook-14")
    ok = client.post(f"{API}/analytics/events", json={"event_type": "product_view", "product_id": p["id"],
                                                       "session_key": "abc123"})
    assert ok.status_code == 202
    bad = client.post(f"{API}/analytics/events", json={"event_type": "purchase", "product_id": p["id"]})
    assert bad.status_code == 422  # purchases can only be recorded server-side


def test_recommendations(client, buyer_headers, product_by_slug):  # type: ignore[no-untyped-def]
    cam = product_by_slug("aperture-lumix-lx-7-mirrorless-camera")
    sim = client.get(f"{API}/recommendations/similar/{cam['id']}").json()
    assert sim["items"] and all(i["id"] != cam["id"] for i in sim["items"])
    assert client.get(f"{API}/recommendations/popular").json()["items"]
    fy = client.get(f"{API}/recommendations/for-you", headers=buyer_headers).json()
    assert fy["items"] and fy["strategy"] in ("for_you", "popular_fallback")
    cat = client.get(f"{API}/recommendations/category/running-shoes").json()
    assert all(i["category"]["slug"] == "running-shoes" for i in cat["items"])


def test_media_upload_validation(client, seller_headers, buyer_headers):  # type: ignore[no-untyped-def]
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 100
    assert client.post(f"{API}/media/upload", files={"file": ("a.png", png, "image/png")},
                       headers=buyer_headers).status_code == 403
    r = client.post(f"{API}/media/upload", files={"file": ("a.png", png, "image/png")}, headers=seller_headers)
    assert r.status_code == 201
    assert client.get(r.json()["url"]).status_code == 200
    fake = client.post(f"{API}/media/upload", files={"file": ("a.png", b"<svg onload=alert(1)>", "image/png")},
                       headers=seller_headers)
    assert fake.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"
    svg = client.post(f"{API}/media/upload", files={"file": ("a.svg", b"<svg/>", "image/svg+xml")}, headers=seller_headers)
    assert svg.status_code == 422
    assert client.get(f"{API}/media/files/../../etc/passwd").status_code == 404
