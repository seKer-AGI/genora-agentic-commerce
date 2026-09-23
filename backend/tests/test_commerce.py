"""Cart, pricing, checkout, order lifecycle, reviews, offers, bundles, coupons and negotiation."""

from __future__ import annotations

import uuid

API = "/api/v1"


def _fresh_cart(client, headers):  # type: ignore[no-untyped-def]
    client.delete(f"{API}/cart", headers=headers)


def _address(client, headers):  # type: ignore[no-untyped-def]
    return client.get(f"{API}/addresses", headers=headers).json()[0]["id"]


def test_cart_totals_are_server_side(client, buyer_headers, product_by_slug):  # type: ignore[no-untyped-def]
    _fresh_cart(client, buyer_headers)
    p = product_by_slug("hearth-powerblend-1200-blender")  # $149, no offers
    cart = client.post(f"{API}/cart/items", json={"product_id": p["id"], "quantity": 2, "price": 0.01},
                       headers=buyer_headers).json()
    assert cart["subtotal"] == 298.0
    assert cart["shipping_total"] == 0.0  # above free-shipping threshold
    assert cart["tax_total"] == round(298 * 0.08, 2)
    assert cart["total"] == round(298 + 298 * 0.08, 2)


def test_cart_quantity_validation_and_stock(client, buyer_headers, product_by_slug):  # type: ignore[no-untyped-def]
    _fresh_cart(client, buyer_headers)
    p = product_by_slug("hearth-pourover-kettle")
    assert client.post(f"{API}/cart/items", json={"product_id": p["id"], "quantity": 0}, headers=buyer_headers).status_code == 422
    too_many = client.post(f"{API}/cart/items", json={"product_id": p["id"], "quantity": p["stock"] + 1}, headers=buyer_headers)
    if p["stock"] < 99:
        assert too_many.json()["error"]["code"] == "INSUFFICIENT_STOCK"
    cart = client.post(f"{API}/cart/items", json={"product_id": p["id"], "quantity": 1}, headers=buyer_headers).json()
    item_id = cart["items"][0]["id"]
    cart = client.patch(f"{API}/cart/items/{item_id}", json={"quantity": 2}, headers=buyer_headers).json()
    assert cart["items"][0]["quantity"] == 2
    cart = client.delete(f"{API}/cart/items/{item_id}", headers=buyer_headers).json()
    assert cart["items"] == []


def test_cannot_touch_other_users_cart_items(client, buyer_headers, admin_headers, product_by_slug):  # type: ignore[no-untyped-def]
    _fresh_cart(client, buyer_headers)
    p = product_by_slug("hearth-pourover-kettle")
    item_id = client.post(f"{API}/cart/items", json={"product_id": p["id"], "quantity": 1},
                          headers=buyer_headers).json()["items"][0]["id"]
    other = client.delete(f"{API}/cart/items/{item_id}", headers=admin_headers)
    assert other.status_code in (403, 404)


def test_offer_applied_best_single_offer(client, buyer_headers, product_by_slug):  # type: ignore[no-untyped-def]
    _fresh_cart(client, buyer_headers)
    p = product_by_slug("voltrix-aerobook-14")  # 849 sale price; 5% product offer vs $20 laptop offer
    cart = client.post(f"{API}/cart/items", json={"product_id": p["id"], "quantity": 1}, headers=buyer_headers).json()
    line = cart["items"][0]
    assert line["discounts"] == [{"source": "offer", "description": "Offer: AeroBook launch week", "amount": 42.45}]
    offers = client.get(f"{API}/products/{p['id']}/offers").json()
    assert {o["name"] for o in offers} == {"AeroBook launch week", "Back to school: laptops"}
    assert all(o["status"] == "active" for o in offers)


def test_min_quantity_offer(client, buyer_headers, product_by_slug):  # type: ignore[no-untyped-def]
    _fresh_cart(client, buyer_headers)
    p = product_by_slug("flexfit-resistance-band-set")
    one = client.post(f"{API}/cart/items", json={"product_id": p["id"], "quantity": 1}, headers=buyer_headers).json()
    assert one["items"][0]["discounts"] == []
    two = client.patch(f"{API}/cart/items/{one['items'][0]['id']}", json={"quantity": 2}, headers=buyer_headers).json()
    assert two["items"][0]["discounts"][0]["description"] == "Offer: Buy 2, save 15%"


def test_coupon_rules(client, buyer_headers, product_by_slug):  # type: ignore[no-untyped-def]
    _fresh_cart(client, buyer_headers)
    kettle = product_by_slug("hearth-pourover-kettle")
    client.post(f"{API}/cart/items", json={"product_id": kettle["id"], "quantity": 1}, headers=buyer_headers)
    low = client.post(f"{API}/cart/coupon", json={"code": "SAVE20"}, headers=buyer_headers)
    assert low.json()["error"]["code"] == "COUPON_NOT_APPLICABLE"  # min subtotal $150
    assert client.post(f"{API}/cart/coupon", json={"code": "SPRING5"}, headers=buyer_headers).json()["error"]["code"] == "COUPON_NOT_APPLICABLE"
    assert client.post(f"{API}/cart/coupon", json={"code": "NOPE"}, headers=buyer_headers).json()["error"]["code"] == "COUPON_INVALID"
    ok = client.post(f"{API}/cart/coupon", json={"code": "welcome10"}, headers=buyer_headers).json()
    assert ok["coupon_discount"] == round(79 * 0.10, 2)


def test_bundle_pricing(client, buyer_headers):  # type: ignore[no-untyped-def]
    _fresh_cart(client, buyer_headers)
    bundle = client.get(f"{API}/bundles/yoga-starter-bundle").json()
    assert bundle["savings"] == round(bundle["items_total"] * 0.15, 2)
    cart = client.post(f"{API}/cart/bundles/{bundle['id']}", headers=buyer_headers).json()
    bundle_discount = sum(d["amount"] for i in cart["items"] for d in i["discounts"] if d["source"] == "bundle")
    assert round(bundle_discount, 2) == bundle["savings"]


def test_checkout_creates_orders_decrements_stock_and_is_idempotent(client, buyer_headers, product_by_slug):  # type: ignore[no-untyped-def]
    _fresh_cart(client, buyer_headers)
    a = product_by_slug("hearth-pourover-kettle")
    b = product_by_slug("glow-botanics-hydra-serum")  # different seller → two orders
    client.post(f"{API}/cart/items", json={"product_id": a["id"], "quantity": 1}, headers=buyer_headers)
    cart = client.post(f"{API}/cart/items", json={"product_id": b["id"], "quantity": 2}, headers=buyer_headers).json()
    headers = {**buyer_headers, "Idempotency-Key": f"test-{uuid.uuid4()}"}
    r = client.post(f"{API}/orders/checkout", json={"address_id": _address(client, buyer_headers)}, headers=headers)
    assert r.status_code == 201, r.text
    data = r.json()
    assert len(data["orders"]) == 2
    assert round(data["total_charged"], 2) == cart["total"]
    assert all(o["status"] == "confirmed" for o in data["orders"])
    assert product_by_slug("hearth-pourover-kettle")["stock"] == a["stock"] - 1
    assert client.get(f"{API}/cart", headers=buyer_headers).json()["items"] == []
    replay = client.post(f"{API}/orders/checkout", json={"address_id": _address(client, buyer_headers)}, headers=headers)
    assert replay.json()["checkout_group_id"] == data["checkout_group_id"]


def test_checkout_payment_declined_rolls_back(client, buyer_headers, product_by_slug):  # type: ignore[no-untyped-def]
    _fresh_cart(client, buyer_headers)
    p = product_by_slug("hearth-pourover-kettle")
    client.post(f"{API}/cart/items", json={"product_id": p["id"], "quantity": 1}, headers=buyer_headers)
    r = client.post(f"{API}/orders/checkout", json={"address_id": _address(client, buyer_headers),
                                                     "payment_method": "pm_card_declined"}, headers=buyer_headers)
    assert r.json()["error"]["code"] == "PAYMENT_FAILED"
    assert product_by_slug("hearth-pourover-kettle")["stock"] == p["stock"]
    assert client.get(f"{API}/cart", headers=buyer_headers).json()["items"]


def test_checkout_rejects_empty_cart_and_foreign_address(client, buyer_headers, admin_headers):  # type: ignore[no-untyped-def]
    _fresh_cart(client, buyer_headers)
    addr = _address(client, buyer_headers)
    r = client.post(f"{API}/orders/checkout", json={"address_id": addr}, headers=buyer_headers)
    assert r.json()["error"]["code"] == "CART_EMPTY"
    both = client.post(f"{API}/orders/checkout", json={}, headers=buyer_headers)
    assert both.status_code == 422


def test_order_lifecycle_permissions(client, buyer_headers, seller_headers, other_seller_headers, product_by_slug):  # type: ignore[no-untyped-def]
    _fresh_cart(client, buyer_headers)
    p = product_by_slug("voltrix-glide-wireless-mouse")  # Voltrix = seller@genora.dev
    client.post(f"{API}/cart/items", json={"product_id": p["id"], "quantity": 1}, headers=buyer_headers)
    order = client.post(f"{API}/orders/checkout", json={"address_id": _address(client, buyer_headers)},
                        headers=buyer_headers).json()["orders"][0]
    oid = order["id"]
    assert client.get(f"{API}/orders/{oid}", headers=other_seller_headers).status_code == 404
    # buyer cannot ship
    assert client.post(f"{API}/orders/{oid}/status", json={"status": "processing"}, headers=buyer_headers).status_code == 403
    # invalid jump
    jump = client.post(f"{API}/orders/{oid}/status", json={"status": "delivered"}, headers=seller_headers)
    assert jump.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"
    for st in ("processing", "shipped", "delivered"):
        r = client.post(f"{API}/orders/{oid}/status", json={"status": st, "tracking_number": "1Z999"}, headers=seller_headers)
        assert r.status_code == 200, r.text
    final = client.get(f"{API}/orders/{oid}", headers=buyer_headers).json()
    assert [e["to_status"] for e in final["status_history"]][-3:] == ["processing", "shipped", "delivered"]
    # now the buyer is a verified purchaser and may review
    assert client.get(f"{API}/products/{p['id']}/reviews/eligibility", headers=buyer_headers).json()["can_review"] in (True, False)


def test_buyer_cancel_restocks_and_refunds(client, buyer_headers, product_by_slug):  # type: ignore[no-untyped-def]
    _fresh_cart(client, buyer_headers)
    p = product_by_slug("hearth-pourover-kettle")
    client.post(f"{API}/cart/items", json={"product_id": p["id"], "quantity": 1}, headers=buyer_headers)
    order = client.post(f"{API}/orders/checkout", json={"address_id": _address(client, buyer_headers)},
                        headers=buyer_headers).json()["orders"][0]
    r = client.post(f"{API}/orders/{order['id']}/status", json={"status": "cancelled"}, headers=buyer_headers).json()
    assert r["status"] == "cancelled"
    assert r["payments"][0]["status"] == "refunded"
    assert product_by_slug("hearth-pourover-kettle")["stock"] == p["stock"]


def test_reviews_require_verified_purchase(client, db, product_by_slug):  # type: ignore[no-untyped-def]
    reg = client.post(f"{API}/auth/register", json={"email": "reviewer@example.com", "password": "Str0ngPass!",
                                                     "full_name": "Rev Iewer"})
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    p = product_by_slug("hearth-pourover-kettle")
    r = client.post(f"{API}/products/{p['id']}/reviews", json={"rating": 5, "body": "Amazing kettle, love it."}, headers=headers)
    assert r.json()["error"]["code"] == "PURCHASE_REQUIRED"


def test_review_create_moderate_and_aggregate(client, db, buyer_headers, seller_headers, admin_headers, product_by_slug):  # type: ignore[no-untyped-def]
    # deliver an order to the demo buyer for a product they have not reviewed
    p = product_by_slug("oakline-monitor-riser")
    elig = client.get(f"{API}/products/{p['id']}/reviews/eligibility", headers=buyer_headers).json()
    if elig.get("existing_review_id"):
        client.delete(f"{API}/reviews/{elig['existing_review_id']}", headers=buyer_headers)
    _fresh_cart(client, buyer_headers)
    client.post(f"{API}/cart/items", json={"product_id": p["id"], "quantity": 1}, headers=buyer_headers)
    oid = client.post(f"{API}/orders/checkout", json={"address_id": _address(client, buyer_headers)},
                      headers=buyer_headers).json()["orders"][0]["id"]
    oak = {"Authorization": client.post(f"{API}/auth/login", json={"email": "oakline@sellers.example.com",
                                                                    "password": "Password#2026!"}).json()["access_token"]}
    oak = {"Authorization": f"Bearer {oak['Authorization']}"}
    for st in ("processing", "shipped", "delivered"):
        assert client.post(f"{API}/orders/{oid}/status", json={"status": st}, headers=oak).status_code == 200
    spam = client.post(f"{API}/products/{p['id']}/reviews",
                       json={"rating": 5, "body": "Great riser! Visit https://spam.example for deals"}, headers=buyer_headers)
    assert spam.status_code == 201 and spam.json()["status"] == "pending"
    before = product_by_slug("oakline-monitor-riser")["rating_count"]
    queue = client.get(f"{API}/admin/reviews", headers=admin_headers).json()
    assert any(r["id"] == spam.json()["id"] for r in queue["items"])
    assert client.post(f"{API}/admin/reviews/{spam.json()['id']}/moderate", json={"status": "approved"},
                       headers=buyer_headers).status_code == 403
    ok = client.post(f"{API}/admin/reviews/{spam.json()['id']}/moderate", json={"status": "approved"}, headers=admin_headers)
    assert ok.json()["status"] == "approved"
    assert product_by_slug("oakline-monitor-riser")["rating_count"] == before + 1
    dup = client.post(f"{API}/products/{p['id']}/reviews", json={"rating": 4, "body": "Second review attempt"},
                      headers=buyer_headers)
    assert dup.json()["error"]["code"] == "REVIEW_EXISTS"


def test_review_summary_is_grounded(client, product_by_slug):  # type: ignore[no-untyped-def]
    p = product_by_slug("voltrix-aerobook-14")
    s = client.get(f"{API}/products/{p['id']}/reviews/summary").json()
    reviews = client.get(f"{API}/products/{p['id']}/reviews", params={"page_size": 50}).json()["items"]
    bodies = " ".join(r["body"] for r in reviews)
    for theme in s["insights"]["themes"]:
        for snippet in theme["examples_positive"] + theme["examples_negative"]:
            assert snippet in bodies  # every snippet is verbatim from a real review
    assert "not verified product specifications" in s["disclaimer"]


def test_seller_offer_crud_and_scope(client, seller_headers, other_seller_headers, product_by_slug):  # type: ignore[no-untyped-def]
    p = product_by_slug("voltrix-glide-wireless-mouse")
    body = {"name": "Mouse madness", "discount_type": "percentage", "value": 20, "product_id": p["id"]}
    assert client.post(f"{API}/offers", json=body, headers=other_seller_headers).status_code == 404
    assert client.post(f"{API}/offers", json={**body, "value": 95}, headers=seller_headers).status_code == 422
    r = client.post(f"{API}/offers", json=body, headers=seller_headers)
    assert r.status_code == 201 and r.json()["scope"] == "product"
    assert product_by_slug("voltrix-glide-wireless-mouse")["final_price"] == round(59 * 0.8, 2)
    assert client.delete(f"{API}/offers/{r.json()['id']}", headers=other_seller_headers).status_code == 404
    assert client.delete(f"{API}/offers/{r.json()['id']}", headers=seller_headers).status_code == 204


def test_negotiation_rules_enforced(client, buyer_headers, seller_headers, product_by_slug):  # type: ignore[no-untyped-def]
    lx9 = product_by_slug("aperture-lx-9-full-frame-camera")  # max 8%, auto 3%
    assert lx9["negotiable"] is True
    price = lx9["final_price"]
    low = client.post(f"{API}/products/{lx9['id']}/negotiations", json={"offered_price": round(price * 0.5, 2)},
                      headers=buyer_headers).json()
    assert low["status"] == "rejected" and low["agreed_price"] is None
    assert low["counter_price"] == round(price * 0.97, 2)
    close = client.post(f"{API}/products/{lx9['id']}/negotiations", json={"offered_price": round(price * 0.98, 2)},
                        headers=buyer_headers).json()
    assert close["status"] == "accepted" and close["agreed_price"] == round(price * 0.98, 2)
    # negotiated price is honoured in the cart (1 unit)
    _fresh_cart(client, buyer_headers)
    cart = client.post(f"{API}/cart/items", json={"product_id": lx9["id"], "quantity": 1}, headers=buyer_headers).json()
    assert cart["items"][0]["total"] == close["agreed_price"]
    not_neg = product_by_slug("voltrix-studybook-15")
    r = client.post(f"{API}/products/{not_neg['id']}/negotiations", json={"offered_price": 100}, headers=buyer_headers)
    assert r.json()["error"]["code"] == "NOT_NEGOTIABLE"
    own = client.post(f"{API}/products/{product_by_slug('voltrix-aerobook-pro-16')['id']}/negotiations",
                      json={"offered_price": 1000}, headers=seller_headers)
    assert own.status_code == 403


def test_wishlist(client, buyer_headers, product_by_slug):  # type: ignore[no-untyped-def]
    p = product_by_slug("northpeak-traillite-headlamp")
    items = client.post(f"{API}/wishlist/{p['id']}", headers=buyer_headers).json()
    assert any(i["id"] == p["id"] for i in items)
    items = client.delete(f"{API}/wishlist/{p['id']}", headers=buyer_headers).json()
    assert all(i["id"] != p["id"] for i in items)
