"""Products, categories, search and inventory — including ownership/authorization rules."""

from __future__ import annotations

API = "/api/v1"

NEW_PRODUCT = {
    "name": "Voltrix Test Dock Pro",
    "sku": "VX-TEST-001",
    "description": "A USB-C dock used by the automated test-suite.",
    "price": "199.00",
    "sale_price": "179.00",
    "brand": "Voltrix",
    "tags": ["Dock", "usb c", "dock"],
    "attributes": {"ports": 9},
    "stock": 12,
    "status": "active",
}


def test_category_tree_has_counts(client):  # type: ignore[no-untyped-def]
    tree = client.get(f"{API}/categories").json()
    electronics = next(c for c in tree if c["slug"] == "electronics")
    assert electronics["product_count"] >= sum(ch["product_count"] for ch in electronics["children"])
    assert any(ch["slug"] == "laptops" for ch in electronics["children"])


def test_browse_filters_sort_and_paginate(client):  # type: ignore[no-untyped-def]
    r = client.get(f"{API}/products", params={"category": "laptops", "sort": "price_asc", "page_size": 3})
    data = r.json()
    prices = [i["price"] if i["sale_price"] is None else i["sale_price"] for i in data["items"]]
    assert prices == sorted(prices)
    assert data["total"] >= 8 and len(data["items"]) == 3
    page2 = client.get(f"{API}/products", params={"category": "laptops", "sort": "price_asc", "page_size": 3, "page": 2}).json()
    assert {i["id"] for i in page2["items"]}.isdisjoint({i["id"] for i in data["items"]})
    rated = client.get(f"{API}/products", params={"min_rating": 4.5}).json()
    assert all(i["rating_avg"] >= 4.5 for i in rated["items"])


def test_invalid_filters_rejected(client):  # type: ignore[no-untyped-def]
    r = client.get(f"{API}/search", params={"q": "laptop", "min_price": 500, "max_price": 100})
    assert r.status_code == 422
    assert client.get(f"{API}/search", params={"page_size": 1000}).status_code == 422


def test_search_modes_return_relevant_results(client):  # type: ignore[no-untyped-def]
    for mode in ("keyword", "semantic", "hybrid"):
        r = client.get(f"{API}/search", params={"q": "running shoes", "mode": mode}).json()
        assert r["items"], mode
        assert "Stridewell" in r["items"][0]["name"] or "FlexFit" in r["items"][0]["name"]
    tent = client.get(f"{API}/search", params={"q": "tent"}).json()
    assert tent["items"][0]["name"] == "Northpeak Basecamp 2P Tent"
    assert tent["engine"]["fusion"] == "rrf"


def test_search_price_filter_and_facets(client):  # type: ignore[no-untyped-def]
    r = client.get(f"{API}/search", params={"q": "laptop", "max_price": 1000, "category": "laptops"}).json()
    assert r["items"]
    for item in r["items"]:
        assert (item["sale_price"] or item["price"]) <= 1000
    assert r["facets"]["brands"]


def test_product_detail_by_slug_and_hidden_drafts(client, seller_headers):  # type: ignore[no-untyped-def]
    d = client.get(f"{API}/products/voltrix-aerobook-14").json()
    assert d["sku"] and d["images"] and d["rating_distribution"]
    assert d["final_price"] <= d["sale_price"]
    draft = client.post(f"{API}/products", json={**NEW_PRODUCT, "status": "draft", "sku": "VX-DRAFT"},
                        headers=seller_headers).json()
    assert client.get(f"{API}/products/{draft['id']}").status_code == 404  # public cannot see drafts
    assert client.get(f"{API}/products/{draft['id']}", headers=seller_headers).status_code == 200


def test_seller_product_crud(client, seller_headers):  # type: ignore[no-untyped-def]
    r = client.post(f"{API}/products", json=NEW_PRODUCT, headers=seller_headers)
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["tags"] == ["dock", "usb-c"]
    assert p["stock"] == 12 and p["images"]  # artwork generated when no images given
    upd = client.patch(f"{API}/products/{p['id']}", json={"price": "209.00", "clear_sale_price": True}, headers=seller_headers)
    assert upd.status_code == 200 and upd.json()["price"] == 209.0 and upd.json()["sale_price"] is None
    bad = client.patch(f"{API}/products/{p['id']}", json={"sale_price": "999.00"}, headers=seller_headers)
    assert bad.status_code == 422
    dup = client.post(f"{API}/products", json=NEW_PRODUCT, headers=seller_headers)
    assert dup.json()["error"]["code"] == "SKU_TAKEN"
    assert client.delete(f"{API}/products/{p['id']}", headers=seller_headers).status_code == 204
    assert client.get(f"{API}/products/{p['id']}").status_code == 404


def test_seller_cannot_modify_other_sellers_products(client, other_seller_headers, product_by_slug):  # type: ignore[no-untyped-def]
    voltrix = product_by_slug("voltrix-aerobook-14")
    for call in (
        lambda: client.patch(f"{API}/products/{voltrix['id']}", json={"price": "1.00"}, headers=other_seller_headers),
        lambda: client.delete(f"{API}/products/{voltrix['id']}", headers=other_seller_headers),
        lambda: client.patch(f"{API}/sellers/me/inventory/{voltrix['id']}", json={"quantity_on_hand": 0},
                             headers=other_seller_headers),
    ):
        r = call()
        assert r.status_code == 404, r.text  # existence not revealed
    assert product_by_slug("voltrix-aerobook-14")["price"] == voltrix["price"]


def test_buyer_cannot_create_products(client, buyer_headers):  # type: ignore[no-untyped-def]
    r = client.post(f"{API}/products", json=NEW_PRODUCT, headers=buyer_headers)
    assert r.status_code == 403


def test_inventory_management(client, seller_headers, product_by_slug):  # type: ignore[no-untyped-def]
    p = product_by_slug("voltrix-glide-wireless-mouse")
    r = client.patch(f"{API}/sellers/me/inventory/{p['id']}", json={"quantity_on_hand": 3, "low_stock_threshold": 5},
                     headers=seller_headers)
    assert r.status_code == 200 and r.json()["is_low"] is True
    low = client.get(f"{API}/sellers/me/inventory", params={"low_only": True}, headers=seller_headers).json()
    assert any(i["product_id"] == p["id"] for i in low)
    neg = client.patch(f"{API}/sellers/me/inventory/{p['id']}", json={"adjust_by": -10}, headers=seller_headers)
    assert neg.json()["error"]["code"] == "INVALID_STOCK"


def test_admin_category_management_and_rbac(client, admin_headers, buyer_headers):  # type: ignore[no-untyped-def]
    body = {"name": "Test Gadgets", "description": "test"}
    assert client.post(f"{API}/categories", json=body, headers=buyer_headers).status_code == 403
    r = client.post(f"{API}/categories", json=body, headers=admin_headers)
    assert r.status_code == 201 and r.json()["slug"] == "test-gadgets"
    used = client.get(f"{API}/categories/laptops").json()
    assert client.delete(f"{API}/categories/{used['id']}", headers=admin_headers).json()["error"]["code"] == "CATEGORY_IN_USE"


def test_admin_can_block_product(client, admin_headers, seller_headers, product_by_slug):  # type: ignore[no-untyped-def]
    p = product_by_slug("voltrix-studybook-15")
    r = client.post(f"{API}/admin/products/{p['id']}/moderate", json={"status": "blocked", "reason": "test"},
                    headers=admin_headers)
    assert r.status_code == 200 and r.json()["status"] == "blocked"
    assert client.get(f"{API}/products/{p['id']}").status_code == 404
    relist = client.patch(f"{API}/products/{p['id']}", json={"status": "active"}, headers=seller_headers)
    assert relist.json()["error"]["code"] == "PRODUCT_BLOCKED"


def test_error_shape_for_unknown_product(client):  # type: ignore[no-untyped-def]
    r = client.get(f"{API}/products/does-not-exist")
    assert r.status_code == 404
    assert r.json() == {"success": False, "error": {"code": "PRODUCT_NOT_FOUND", "message": "Product was not found"}}
