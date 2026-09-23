"""Seller insights used by Astra: stock cover and data-driven discount strategy.

Strategy rules (each suggestion lists the numbers behind it):
* out of stock and was selling            → restock (a discount cannot help)
* very few views                           → improve listing / visibility (discounting won't be seen)
* many views, low conversion, ample stock  → time-limited discount (10–15%)
* priced well above category median, weak sales → price review towards the median
* sales declining vs previous period       → bundle with complementary products
* selling well with limited stock          → hold price
"""

from __future__ import annotations

import statistics
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import utcnow
from app.models.analytics import AnalyticsEvent
from app.models.catalog import Product
from app.models.commerce import Order, OrderItem
from app.models.enums import OrderStatus, ProductStatus
from app.services.pricing import PricingEngine

EXCLUDED = (OrderStatus.CANCELLED, OrderStatus.REFUNDED)


@dataclass
class ProductStats:
    product: Product
    units: int
    prev_units: int
    views: int
    orders: int
    stock: int
    price: float
    category_median: float | None
    has_offer: bool

    @property
    def conversion(self) -> float | None:
        return self.orders / self.views * 100 if self.views else None


class SellerInsights:
    def __init__(self, db: Session) -> None:
        self.db = db

    def units_sold(self, product_ids: list[uuid.UUID], days: int, offset_days: int = 0) -> dict[uuid.UUID, int]:
        end = utcnow() - timedelta(days=offset_days)
        start = end - timedelta(days=days)
        rows = self.db.execute(
            select(OrderItem.product_id, func.sum(OrderItem.quantity), func.count(func.distinct(Order.id)))
            .join(Order, Order.id == OrderItem.order_id)
            .where(OrderItem.product_id.in_(product_ids), Order.placed_at >= start, Order.placed_at < end,
                   Order.status.not_in(EXCLUDED))
            .group_by(OrderItem.product_id)
        ).all()
        return {pid: int(u) for pid, u, _ in rows}

    def stats(self, seller_id: uuid.UUID, days: int, product_ids: list[uuid.UUID] | None = None) -> list[ProductStats]:
        stmt = select(Product).where(Product.seller_id == seller_id, Product.deleted_at.is_(None),
                                     Product.status == ProductStatus.ACTIVE)
        if product_ids:
            stmt = stmt.where(Product.id.in_(product_ids))
        products = list(self.db.scalars(stmt).unique())
        if not products:
            return []
        ids = [p.id for p in products]
        now = utcnow()
        units = self.units_sold(ids, days)
        prev = self.units_sold(ids, days, offset_days=days)
        orders = dict(self.db.execute(
            select(OrderItem.product_id, func.count(func.distinct(Order.id))).join(Order, Order.id == OrderItem.order_id)
            .where(OrderItem.product_id.in_(ids), Order.placed_at >= now - timedelta(days=days), Order.status.not_in(EXCLUDED))
            .group_by(OrderItem.product_id)).tuples().all())
        views = dict(self.db.execute(
            select(AnalyticsEvent.product_id, func.count()).where(
                AnalyticsEvent.product_id.in_(ids), AnalyticsEvent.event_type == "product_view",
                AnalyticsEvent.created_at >= now - timedelta(days=days)).group_by(AnalyticsEvent.product_id)).tuples().all())
        engine = PricingEngine(self.db)
        cat_ids = {p.category_id for p in products if p.category_id}
        medians: dict[uuid.UUID, float] = {}
        for cid in cat_ids:
            prices = [float(x) for x in self.db.scalars(
                select(func.coalesce(Product.sale_price, Product.price)).where(
                    Product.category_id == cid, Product.status == ProductStatus.ACTIVE, Product.deleted_at.is_(None)))]
            if len(prices) >= 3:
                medians[cid] = statistics.median(prices)
        return [
            ProductStats(p, units.get(p.id, 0), prev.get(p.id, 0), int(views.get(p.id, 0)), int(orders.get(p.id, 0)),
                         p.stock, float(p.effective_list_price), medians.get(p.category_id) if p.category_id else None,
                         engine.quote(p).offer is not None)
            for p in products
        ]

    def discount_strategy(self, seller_id: uuid.UUID, days: int = 30, product_ids: list[uuid.UUID] | None = None,
                          limit: int = 8) -> list[dict[str, object]]:
        out: list[tuple[float, dict[str, object]]] = []
        for s in self.stats(seller_id, days, product_ids):
            p = s.product
            ev = [f"{s.units} units sold in the last {days} days (previous {days} days: {s.prev_units})",
                  f"{s.views} product views, conversion {s.conversion:.1f}%" if s.conversion is not None else f"{s.views} product views",
                  f"{s.stock} units in stock"]
            if s.category_median:
                ev.append(f"Price ${s.price:,.2f} vs category median ${s.category_median:,.2f}")
            if s.has_offer:
                ev.append("Already has an active offer")
            base = {"product_id": str(p.id), "product_name": p.name, "evidence": ev}
            if s.stock == 0 and (s.units or s.prev_units):
                out.append((5, {**base, "action": "restock", "headline": f"Restock {p.name}",
                                "rationale": "It sells but is out of stock — a discount can't help until it's back.",
                                "proposed_percent_off": None}))
            elif s.views < 15:
                out.append((2, {**base, "action": "improve_listing", "headline": f"Improve visibility of {p.name}",
                                "rationale": "Very few shoppers see this product; better photos, title and tags will do "
                                             "more than a discount.", "proposed_percent_off": None}))
            elif (s.conversion is not None and s.conversion < 1.5 and s.stock >= 10 and not s.has_offer):
                pct = 15.0 if s.conversion < 0.75 else 10.0
                out.append((4, {**base, "action": "discount", "headline": f"Run a {pct:g}% time-limited offer on {p.name}",
                                "rationale": "Plenty of interest but few purchases and healthy stock — a short promotion "
                                             "is the most likely lever.", "proposed_percent_off": pct}))
            elif s.category_median and s.price > s.category_median * 1.25 and s.units <= s.prev_units:
                out.append((3, {**base, "action": "price_review", "headline": f"Review the price of {p.name}",
                                "rationale": f"It's priced {s.price / s.category_median * 100 - 100:.0f}% above the "
                                             "category median while sales are flat or falling.",
                                "proposed_percent_off": None}))
            elif s.prev_units >= 4 and s.units < s.prev_units * 0.6:
                out.append((3, {**base, "action": "bundle", "headline": f"Bundle {p.name} with a complementary item",
                                "rationale": "Sales dropped more than 40% vs the previous period; a bundle adds value "
                                             "without cutting the headline price.", "proposed_percent_off": None}))
            elif s.units >= 5 and s.stock < max(10, s.units):
                out.append((1, {**base, "action": "hold", "headline": f"Keep {p.name} at full price",
                                "rationale": "It's selling well and stock is limited — discounting would give away margin.",
                                "proposed_percent_off": None}))
        out.sort(key=lambda t: t[0], reverse=True)
        return [s for _, s in out[:limit]]
