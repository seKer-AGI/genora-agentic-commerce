"""GenOra Astra workflow tests + forecasting API."""

from __future__ import annotations

from sqlalchemy import select

from app.models import Product
from tests.test_agents_nova import Chat, blocks, status


def test_low_inventory(client, seller_headers, product_by_slug):  # type: ignore[no-untyped-def]
    mouse = product_by_slug("voltrix-glide-wireless-mouse")
    client.patch(f"/api/v1/sellers/me/inventory/{mouse['id']}", json={"quantity_on_hand": 2}, headers=seller_headers)
    t = Chat(client, seller_headers, "astra").say("Which products are running low?")
    table = blocks(t, "table")[0]
    assert any(r["name"] == "Voltrix Glide Wireless Mouse" and r["available"] == 2 for r in table["rows"])


def test_sales_performance_matches_analytics(client, seller_headers):  # type: ignore[no-untyped-def]
    t = Chat(client, seller_headers, "astra").say("How did my sales perform this month?")
    kpis = {k["label"]: k["value"] for k in blocks(t, "kpis")[0]["kpis"]}
    overview = client.get("/api/v1/analytics/seller/overview", params={"days": 30}, headers=seller_headers).json()
    assert kpis["Revenue"] == overview["revenue"]["value"]
    assert kpis["Orders"] == overview["orders"]["value"]
    assert "last 30 days" in t["message"]["content"]


def test_underperforming_products(client, seller_headers):  # type: ignore[no-untyped-def]
    t = Chat(client, seller_headers, "astra").say("Which products are underperforming?")
    rows = blocks(t, "table")[0]["rows"]
    assert rows and all("views" in r for r in rows)


def test_listing_assistant_drafts_then_creates_draft_only_after_confirmation(client, db, seller_headers):  # type: ignore[no-untyped-def]
    chat = Chat(client, seller_headers, "astra")
    t = chat.say("Create a product listing for a Voltrix AeroBook 15 with 16GB RAM and 1TB SSD priced at $1099")
    draft = blocks(t, "listing_draft")[0]["draft"]
    assert "AeroBook 15" in draft["title"]
    assert draft["attributes"]["ram_gb"] == 16 and draft["attributes"]["storage_gb"] == 1024
    assert draft["category_suggestions"][0]["slug"] == "laptops"
    assert status(t) == "awaiting_confirmation"
    assert db.scalar(select(Product).where(Product.name == draft["title"])) is None
    action = blocks(t, "confirmation")[0]
    done = chat.decide(action["action_id"], approve=True)
    assert "draft" in done["message"]["content"].lower()
    created = db.scalar(select(Product).where(Product.name == draft["title"]))
    assert created is not None and created.status.value == "draft" and float(created.price) == 1099.0


def test_listing_asks_for_price_when_missing(client, seller_headers):  # type: ignore[no-untyped-def]
    chat = Chat(client, seller_headers, "astra")
    t = chat.say("Write a listing for a Voltrix Pocket Charger 20000mAh")
    assert status(t) == "needs_clarification" and blocks(t, "listing_draft")
    t2 = chat.say("$39.99")
    assert status(t2) == "awaiting_confirmation"


def test_price_change_requires_confirmation(client, seller_headers, product_by_slug):  # type: ignore[no-untyped-def]
    chat = Chat(client, seller_headers, "astra")
    t = chat.say("Change the price of Voltrix Glide Wireless Mouse to $49")
    assert status(t) == "awaiting_confirmation"
    assert product_by_slug("voltrix-glide-wireless-mouse")["price"] == 59.0
    chat.decide(blocks(t, "confirmation")[0]["action_id"], approve=True)
    assert product_by_slug("voltrix-glide-wireless-mouse")["price"] == 49.0


def test_astra_cannot_touch_other_sellers_products(client, seller_headers, product_by_slug):  # type: ignore[no-untyped-def]
    t = Chat(client, seller_headers, "astra").say("Change the price of Kestrel Forge 15 Gaming Laptop to $1")
    assert status(t) != "awaiting_confirmation"
    assert "couldn't find" in t["message"]["content"].lower()
    assert product_by_slug("kestrel-forge-15-gaming-laptop")["price"] == 1299.0


def test_discount_strategy_is_evidence_based_and_changes_nothing(client, seller_headers):  # type: ignore[no-untyped-def]
    t = Chat(client, seller_headers, "astra").say("Suggest a discount strategy for my products")
    items = blocks(t, "recommendations")[0]["items"]
    assert items and all(i["evidence"] for i in items)
    assert "Nothing has been changed" in t["message"]["content"]


def test_create_offer_via_astra(client, seller_headers, product_by_slug):  # type: ignore[no-untyped-def]
    chat = Chat(client, seller_headers, "astra")
    t = chat.say("Create a 10% offer on Voltrix TypeFlow Mechanical Keyboard for 7 days")
    done = chat.decide(blocks(t, "confirmation")[0]["action_id"], approve=True)
    assert "is live" in done["message"]["content"]
    kb = product_by_slug("voltrix-typeflow-mechanical-keyboard")
    assert kb["final_price"] == round(109 * 0.9, 2)


def test_forecast_via_astra(client, seller_headers):  # type: ignore[no-untyped-def]
    t = Chat(client, seller_headers, "astra").say("Forecast my revenue for the next 14 days")
    fc = blocks(t, "forecast")[0]["forecast"]
    assert fc["status"] == "completed" and len(fc["points"]) == 14
    assert all(p["lower"] <= p["value"] <= p["upper"] for p in fc["points"])
    assert "not a guarantee" in t["message"]["content"]


def test_forecasting_api(client, seller_headers, admin_headers, buyer_headers, product_by_slug):  # type: ignore[no-untyped-def]
    providers = {p["name"]: p for p in client.get("/api/v1/forecasting/providers", headers=seller_headers).json()}
    assert providers["baseline"]["available"] is True
    assert providers["timesfm"]["available"] is False and providers["timesfm"]["unavailable_reason"]
    r = client.post("/api/v1/forecasting/run", json={"target": "sales", "horizon": 7}, headers=seller_headers).json()
    assert r["status"] == "completed" and r["metrics"]["backtest"]["holdout"] > 0
    tfm = client.post("/api/v1/forecasting/run", json={"target": "sales", "horizon": 7, "provider": "timesfm"},
                      headers=seller_headers).json()
    assert tfm["status"] == "failed" and tfm["points"] == [] and "timesfm" in tfm["error"]
    other = product_by_slug("kestrel-forge-15-gaming-laptop")
    forbidden = client.post("/api/v1/forecasting/run", json={"target": "product_demand", "entity_id": other["id"]},
                            headers=seller_headers)
    assert forbidden.status_code == 404
    market = client.post("/api/v1/forecasting/run", json={"target": "revenue", "scope": "marketplace", "horizon": 30},
                         headers=admin_headers).json()
    assert market["status"] == "completed" and len(market["points"]) == 30
    assert client.post("/api/v1/forecasting/run", json={"target": "revenue"}, headers=buyer_headers).status_code == 403
    listed = client.get("/api/v1/forecasting/results", headers=seller_headers).json()
    assert all(x["id"] != market["id"] for x in listed)  # sellers only see their own forecasts
