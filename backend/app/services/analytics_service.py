"""Analytics: event ingestion and reusable metric queries for sellers, admins, agents and forecasting.

Definitions
-----------
* **Revenue** (net sales) = order subtotal − discounts, excluding tax and shipping.
* **GMV** = order totals including tax and shipping.
* Cancelled and refunded orders are excluded from revenue, GMV, units and order counts.
* **Conversion rate** = orders containing the product ÷ product views, in the period.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import Date, and_, case, cast, distinct, func, select
from sqlalchemy.orm import Session

from app.core.principal import Principal
from app.core.security import utcnow
from app.models.agents import AgentToolCall, AgentWorkflow
from app.models.analytics import AnalyticsEvent, SearchHistory
from app.models.catalog import Category, Inventory, Product
from app.models.commerce import Order, OrderItem
from app.models.enums import OrderStatus, ProductStatus, SellerStatus
from app.models.identity import SellerProfile, User
from app.schemas.analytics import (
    AdminOverview,
    AgentUsage,
    EventIn,
    Kpi,
    ProductPerf,
    SearchAnalytics,
    SellerOverview,
    SeriesPoint,
)
from app.services.ai_runtime import describe_ai_runtime

EXCLUDED = (OrderStatus.CANCELLED, OrderStatus.REFUNDED)
NET = Order.subtotal - Order.discount_total


def _kpi(cur: float, prev: float) -> Kpi:
    change = None if prev == 0 else round((cur - prev) / prev * 100, 1)
    return Kpi(value=round(cur, 2), previous=round(prev, 2), change_pct=change)


def _window(days: int, now: datetime | None = None) -> tuple[datetime, datetime, datetime]:
    now = now or utcnow()
    start = now - timedelta(days=days)
    return start - timedelta(days=days), start, now


class AnalyticsService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------ ingestion
    def record(self, event: EventIn, principal: Principal | None) -> None:
        seller_id = None
        category_id = event.category_id
        if event.product_id:
            row = self.db.execute(select(Product.seller_id, Product.category_id).where(Product.id == event.product_id)).first()
            if row is None:
                return
            seller_id, category_id = row[0], row[1] or category_id
        props = {k: v for k, v in list(event.properties.items())[:10] if isinstance(v, str | int | float | bool)}
        self.db.add(AnalyticsEvent(event_type=event.event_type, user_id=principal.user_id if principal else None,
                                   session_key=event.session_key, product_id=event.product_id, seller_id=seller_id,
                                   category_id=category_id, properties=props))
        self.db.commit()

    # ------------------------------------------------------------ primitives
    def _orders_agg(self, start: datetime, end: datetime, seller_id: uuid.UUID | None = None) -> dict[str, float]:
        conds = [Order.placed_at >= start, Order.placed_at < end, Order.status.not_in(EXCLUDED)]
        if seller_id:
            conds.append(Order.seller_id == seller_id)
        rev, gmv, n = self.db.execute(
            select(func.coalesce(func.sum(NET), 0), func.coalesce(func.sum(Order.total), 0), func.count()).where(*conds)
        ).one()
        units = self.db.scalar(
            select(func.coalesce(func.sum(OrderItem.quantity), 0)).join(Order, Order.id == OrderItem.order_id).where(*conds)
        )
        return {"revenue": float(rev), "gmv": float(gmv), "orders": int(n), "units": int(units or 0)}

    def _views(self, start: datetime, end: datetime, seller_id: uuid.UUID | None = None) -> int:
        conds = [AnalyticsEvent.event_type == "product_view", AnalyticsEvent.created_at >= start,
                 AnalyticsEvent.created_at < end]
        if seller_id:
            conds.append(AnalyticsEvent.seller_id == seller_id)
        return int(self.db.scalar(select(func.count()).select_from(AnalyticsEvent).where(*conds)) or 0)

    def daily_series(self, start: datetime, end: datetime, seller_id: uuid.UUID | None = None,
                     product_id: uuid.UUID | None = None, category_ids: list[uuid.UUID] | None = None) -> list[SeriesPoint]:
        day = cast(Order.placed_at, Date)
        conds = [Order.placed_at >= start, Order.placed_at < end, Order.status.not_in(EXCLUDED)]
        if seller_id:
            conds.append(Order.seller_id == seller_id)
        if product_id or category_ids:
            item_conds = [OrderItem.order_id == Order.id]
            if product_id:
                item_conds.append(OrderItem.product_id == product_id)
            if category_ids:
                item_conds.append(OrderItem.product_id.in_(select(Product.id).where(Product.category_id.in_(category_ids))))
            rows = self.db.execute(
                select(day, func.sum(OrderItem.line_total), func.count(distinct(Order.id)), func.sum(OrderItem.quantity))
                .join(OrderItem, and_(*item_conds)).where(*conds).group_by(day)
            ).all()
        else:
            units_sq = (select(OrderItem.order_id, func.sum(OrderItem.quantity).label("u"))
                        .group_by(OrderItem.order_id).subquery())
            rows = self.db.execute(
                select(day, func.sum(NET), func.count(), func.coalesce(func.sum(units_sq.c.u), 0))
                .outerjoin(units_sq, units_sq.c.order_id == Order.id).where(*conds).group_by(day)
            ).all()
        by_day = {r[0]: r for r in rows}
        out, d = [], start.date()
        while d < end.date() + timedelta(days=1) and d <= end.date():
            r = by_day.get(d)
            out.append(SeriesPoint(date=d, revenue=float(r[1]) if r else 0.0, orders=int(r[2]) if r else 0,
                                   units=int(r[3] or 0) if r else 0))
            d += timedelta(days=1)
        return out

    def product_performance(self, start: datetime, end: datetime, seller_id: uuid.UUID | None = None,
                            limit: int = 10, worst: bool = False) -> list[ProductPerf]:
        sold = (
            select(OrderItem.product_id.label("pid"), func.sum(OrderItem.line_total).label("rev"),
                   func.sum(OrderItem.quantity).label("units"), func.count(distinct(Order.id)).label("orders"))
            .join(Order, Order.id == OrderItem.order_id)
            .where(Order.placed_at >= start, Order.placed_at < end, Order.status.not_in(EXCLUDED))
            .group_by(OrderItem.product_id).subquery()
        )
        views = (
            select(AnalyticsEvent.product_id.label("pid"), func.count().label("views"))
            .where(AnalyticsEvent.event_type == "product_view", AnalyticsEvent.created_at >= start,
                   AnalyticsEvent.created_at < end)
            .group_by(AnalyticsEvent.product_id).subquery()
        )
        stock = (select(Inventory.product_id.label("pid"),
                        func.sum(Inventory.quantity_on_hand - Inventory.quantity_reserved).label("stock"))
                 .group_by(Inventory.product_id).subquery())
        rev = func.coalesce(sold.c.rev, 0)
        stmt = (
            select(Product, rev, func.coalesce(sold.c.units, 0), func.coalesce(sold.c.orders, 0),
                   func.coalesce(views.c.views, 0), func.coalesce(stock.c.stock, 0))
            .outerjoin(sold, sold.c.pid == Product.id).outerjoin(views, views.c.pid == Product.id)
            .outerjoin(stock, stock.c.pid == Product.id)
            .where(Product.deleted_at.is_(None))
        )
        if seller_id:
            stmt = stmt.where(Product.seller_id == seller_id)
        if worst:
            stmt = stmt.where(Product.status == ProductStatus.ACTIVE).order_by(rev.asc(), func.coalesce(views.c.views, 0).desc())
        else:
            stmt = stmt.order_by(rev.desc())
        out = []
        for p, r, u, o, v, s in self.db.execute(stmt.limit(limit)).unique().all():
            out.append(ProductPerf(product_id=p.id, name=p.name, slug=p.slug, image_url=p.primary_image_url,
                                   revenue=float(r), units=int(u), orders=int(o), views=int(v),
                                   conversion_rate=round(o / v * 100, 2) if v else None,
                                   rating_avg=float(p.rating_avg), stock=int(s)))
        return out

    def status_breakdown(self, start: datetime, end: datetime, seller_id: uuid.UUID | None = None) -> dict[str, int]:
        stmt = select(Order.status, func.count()).where(Order.placed_at >= start, Order.placed_at < end)
        if seller_id:
            stmt = stmt.where(Order.seller_id == seller_id)
        return {s.value: int(n) for s, n in self.db.execute(stmt.group_by(Order.status)).all()}

    # ------------------------------------------------------------ dashboards
    def seller_overview(self, seller_id: uuid.UUID, days: int = 30) -> SellerOverview:
        prev_start, start, end = _window(days)
        cur, prev = self._orders_agg(start, end, seller_id), self._orders_agg(prev_start, start, seller_id)
        v_cur, v_prev = self._views(start, end, seller_id), self._views(prev_start, start, seller_id)
        aov = lambda a: a["revenue"] / a["orders"] if a["orders"] else 0.0  # noqa: E731
        conv = lambda a, v: a["orders"] / v * 100 if v else 0.0  # noqa: E731
        low_stock = self.db.scalar(
            select(func.count()).select_from(Inventory).join(Product, Product.id == Inventory.product_id)
            .where(Product.seller_id == seller_id, Product.deleted_at.is_(None), Product.status == ProductStatus.ACTIVE,
                   Inventory.quantity_on_hand - Inventory.quantity_reserved <= Inventory.low_stock_threshold)
        ) or 0
        seller = self.db.get(SellerProfile, seller_id)
        return SellerOverview(
            period_days=days, revenue=_kpi(cur["revenue"], prev["revenue"]), orders=_kpi(cur["orders"], prev["orders"]),
            units_sold=_kpi(cur["units"], prev["units"]), average_order_value=_kpi(aov(cur), aov(prev)),
            views=_kpi(v_cur, v_prev), conversion_rate=_kpi(conv(cur, v_cur), conv(prev, v_prev)),
            series=self.daily_series(start, end, seller_id),
            top_products=self.product_performance(start, end, seller_id, limit=5),
            low_performers=self.product_performance(start, end, seller_id, limit=5, worst=True),
            status_breakdown=self.status_breakdown(start, end, seller_id), low_stock_count=int(low_stock),
            rating_avg=float(seller.rating_avg) if seller else 0.0,
            definitions={
                "revenue": "Net sales: subtotal minus discounts, excluding tax and shipping; cancelled/refunded excluded",
                "conversion_rate": "Orders ÷ product views in the period",
                "average_order_value": "Revenue ÷ orders",
            },
        )

    def admin_overview(self, days: int = 30) -> AdminOverview:
        prev_start, start, end = _window(days)
        cur, prev = self._orders_agg(start, end), self._orders_agg(prev_start, start)
        new_u = lambda a, b: self.db.scalar(select(func.count()).select_from(User).where(User.created_at >= a, User.created_at < b)) or 0  # noqa: E731
        totals = {
            "users": self.db.scalar(select(func.count()).select_from(User).where(User.deleted_at.is_(None))) or 0,
            "active_sellers": self.db.scalar(select(func.count()).select_from(SellerProfile)
                                             .where(SellerProfile.status == SellerStatus.ACTIVE)) or 0,
            "products": self.db.scalar(select(func.count()).select_from(Product).where(
                Product.deleted_at.is_(None), Product.status == ProductStatus.ACTIVE)) or 0,
            "orders": self.db.scalar(select(func.count()).select_from(Order)) or 0,
            "lifetime_gmv": float(self.db.scalar(select(func.coalesce(func.sum(Order.total), 0))
                                                 .where(Order.status.not_in(EXCLUDED))) or 0),
        }
        # revenue by root category
        cats = {c.id: c for c in self.db.scalars(select(Category))}

        def root(cid: uuid.UUID | None) -> Category | None:
            c = cats.get(cid) if cid else None
            while c is not None and c.parent_id is not None and c.parent_id in cats:
                c = cats[c.parent_id]
            return c

        rows = self.db.execute(
            select(Product.category_id, func.sum(OrderItem.line_total), func.sum(OrderItem.quantity))
            .join(OrderItem, OrderItem.product_id == Product.id).join(Order, Order.id == OrderItem.order_id)
            .where(Order.placed_at >= start, Order.placed_at < end, Order.status.not_in(EXCLUDED))
            .group_by(Product.category_id)
        ).all()
        by_root: dict[str, dict[str, Any]] = {}
        for cid, rev, units in rows:
            r = root(cid)
            key = r.slug if r else "uncategorised"
            e = by_root.setdefault(key, {"slug": key, "name": r.name if r else "Uncategorised", "revenue": 0.0, "units": 0})
            e["revenue"] += float(rev or 0)
            e["units"] += int(units or 0)
        seller_rows = self.db.execute(
            select(SellerProfile.id, SellerProfile.store_name, SellerProfile.rating_avg,
                   func.coalesce(func.sum(case((Order.status.not_in(EXCLUDED), NET), else_=0)), 0),
                   func.count(Order.id), func.count(case((Order.status == OrderStatus.CANCELLED, 1))))
            .outerjoin(Order, and_(Order.seller_id == SellerProfile.id, Order.placed_at >= start, Order.placed_at < end))
            .group_by(SellerProfile.id).order_by(func.coalesce(func.sum(case((Order.status.not_in(EXCLUDED), NET), else_=0)), 0).desc())
        ).all()
        return AdminOverview(
            period_days=days, totals=totals, gmv=_kpi(cur["gmv"], prev["gmv"]), revenue=_kpi(cur["revenue"], prev["revenue"]),
            orders=_kpi(cur["orders"], prev["orders"]), new_users=_kpi(new_u(start, end), new_u(prev_start, start)),
            series=self.daily_series(start, end), top_products=self.product_performance(start, end, limit=8),
            top_categories=sorted(({**v, "revenue": round(v["revenue"], 2)} for v in by_root.values()),
                                  key=lambda x: x["revenue"], reverse=True),
            seller_performance=[
                {"seller_id": str(sid), "store_name": name, "rating_avg": float(rating), "revenue": round(float(rev), 2),
                 "orders": int(n), "cancellation_rate": round(c / n * 100, 1) if n else 0.0}
                for sid, name, rating, rev, n, c in seller_rows
            ],
            status_breakdown=self.status_breakdown(start, end),
        )

    def agent_usage(self, days: int = 30) -> AgentUsage:
        start = utcnow() - timedelta(days=days)
        w = AgentWorkflow
        total, avg_latency, prompt, completion = self.db.execute(
            select(func.count(), func.avg(w.latency_ms), func.coalesce(func.sum(w.prompt_tokens), 0),
                   func.coalesce(func.sum(w.completion_tokens), 0)).where(w.started_at >= start)
        ).one()
        by_agent = [
            {"agent": a.value, "workflows": int(n), "avg_latency_ms": round(float(lat or 0)),
             "success_rate": round(float(ok) / n * 100, 1) if n else 0.0}
            for a, n, lat, ok in self.db.execute(
                select(w.agent, func.count(), func.avg(w.latency_ms), func.count(case((w.status == "completed", 1))))
                .where(w.started_at >= start).group_by(w.agent)
            ).all()
        ]
        by_intent = [
            {"agent": a.value, "intent": i, "count": int(n)}
            for a, i, n in self.db.execute(select(w.agent, w.intent, func.count()).where(w.started_at >= start)
                                           .group_by(w.agent, w.intent).order_by(func.count().desc()).limit(30)).all()
        ]
        by_status = {s.value: int(n) for s, n in self.db.execute(
            select(w.status, func.count()).where(w.started_at >= start).group_by(w.status)).all()}
        t = AgentToolCall
        tools = [
            {"tool": name, "calls": int(n), "errors": int(err), "denied": int(den), "avg_latency_ms": round(float(lat or 0))}
            for name, n, err, den, lat in self.db.execute(
                select(t.tool_name, func.count(), func.count(case((t.status == "error", 1))),
                       func.count(case((t.status == "denied", 1))), func.avg(t.latency_ms))
                .where(t.created_at >= start).group_by(t.tool_name).order_by(func.count().desc())
            ).all()
        ]
        day = cast(w.started_at, Date)
        series = [{"date": d.isoformat(), "workflows": int(n)} for d, n in self.db.execute(
            select(day, func.count()).where(w.started_at >= start).group_by(day).order_by(day)).all()]
        return AgentUsage(
            period_days=days,
            totals={"workflows": int(total), "avg_latency_ms": round(float(avg_latency or 0)),
                    "prompt_tokens": int(prompt), "completion_tokens": int(completion),
                    "tool_calls": sum(x["calls"] for x in tools)},
            by_agent=by_agent, by_intent=by_intent, by_status=by_status, tool_calls=tools, series=series,
            runtime=describe_ai_runtime(),
        )

    def search_analytics(self, days: int = 30) -> SearchAnalytics:
        start = utcnow() - timedelta(days=days)
        s = SearchHistory
        total = self.db.scalar(select(func.count()).select_from(s).where(s.created_at >= start)) or 0
        zero = self.db.scalar(select(func.count()).select_from(s).where(s.created_at >= start, s.result_count == 0)) or 0
        top = self.db.execute(select(func.lower(s.query), func.count(), func.avg(s.result_count))
                              .where(s.created_at >= start).group_by(func.lower(s.query))
                              .order_by(func.count().desc()).limit(15)).all()
        zeros = self.db.execute(select(func.lower(s.query), func.count()).where(s.created_at >= start, s.result_count == 0)
                                .group_by(func.lower(s.query)).order_by(func.count().desc()).limit(10)).all()
        by_source = dict(self.db.execute(select(s.source, func.count()).where(s.created_at >= start).group_by(s.source)).tuples().all())
        day = cast(s.created_at, Date)
        series = [{"date": d.isoformat(), "searches": int(n)} for d, n in self.db.execute(
            select(day, func.count()).where(s.created_at >= start).group_by(day).order_by(day)).all()]
        return SearchAnalytics(
            period_days=days, total_searches=int(total), zero_result_rate=round(zero / total * 100, 1) if total else 0.0,
            top_queries=[{"query": q, "count": int(n), "avg_results": round(float(a or 0), 1)} for q, n, a in top],
            zero_result_queries=[{"query": q, "count": int(n)} for q, n in zeros],
            by_source={k: int(v) for k, v in by_source.items()}, series=series,
        )

    # ------------------------------------------------------------ forecasting inputs
    def history(self, target: str, *, days: int = 180, seller_id: uuid.UUID | None = None,
                entity_id: uuid.UUID | None = None) -> list[tuple[date, float]]:
        """Daily historical series used by forecasting providers."""
        end = utcnow()
        start = end - timedelta(days=days)
        cat_ids = None
        if target == "category_demand" and entity_id:
            from app.services.catalog_service import CategoryService

            cat_ids = CategoryService(self.db).descendants(entity_id)
        series = self.daily_series(start, end, seller_id,
                                   product_id=entity_id if target == "product_demand" else None, category_ids=cat_ids)
        if target == "revenue":
            return [(p.date, p.revenue) for p in series]
        if target == "sales":
            return [(p.date, float(p.orders)) for p in series]
        return [(p.date, float(p.units)) for p in series]
