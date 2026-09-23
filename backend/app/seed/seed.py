"""Seed the database with realistic *synthetic* marketplace data.

Usage::

    python -m app.seed.seed            # seed if the database has no users yet
    python -m app.seed.seed --reset    # wipe domain data and reseed

Deterministic (fixed RNG seed). Produces ~80 products, 12 sellers, 60 buyers, ~750 orders over
180 days, ~350 reviews, offers, coupons, bundles, negotiation rules and ~12k analytics events.
"""

from __future__ import annotations

import argparse
import logging
import random
import re
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, insert, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import session_scope
from app.integrations.storage import get_storage
from app.models import (
    Address,
    AnalyticsEvent,
    Bundle,
    BundleItem,
    BuyerProfile,
    Cart,
    Category,
    Coupon,
    Discount,
    Inventory,
    NegotiationRule,
    Offer,
    Order,
    OrderItem,
    OrderStatusEvent,
    Payment,
    Product,
    ProductImage,
    Rating,
    Review,
    Role,
    SearchHistory,
    SellerProfile,
    User,
    UserRole,
    Wishlist,
    WishlistItem,
)
from app.models.enums import (
    DiscountSource,
    DiscountType,
    OrderStatus,
    PaymentStatus,
    ProductStatus,
    ReviewStatus,
    RoleName,
    SellerStatus,
)
from app.seed.catalog_data import BUNDLES, CATEGORIES, PRODUCTS, REVIEW_ASPECTS, SELLERS
from app.services.bootstrap import ensure_reference_data
from app.services.catalog_indexing import index_products
from app.services.product_art import render_product_svg

log = logging.getLogger("seed")

DEMO_ACCOUNTS = {
    "admin": ("admin@genora.dev", "Admin#2026!", "Ava Admin"),
    "seller": ("seller@genora.dev", "Seller#2026!", None),  # owner of the first store
    "buyer": ("buyer@genora.dev", "Buyer#2026!", "Ben Buyer"),
}
DEFAULT_PASSWORD = "Password#2026!"
DAYS_OF_HISTORY = 180
CENT = Decimal("0.01")

FIRST = ["Olivia", "Liam", "Emma", "Noah", "Amelia", "Oliver", "Sophia", "Elijah", "Isabella", "James", "Mia",
         "Lucas", "Aria", "Mateo", "Zara", "Ethan", "Leila", "Kai", "Nina", "Ravi", "Sofia", "Yusuf", "Ines", "Theo"]
LAST = ["Garcia", "Nguyen", "Smith", "Kowalski", "Haddad", "Silva", "Johnson", "Tanaka", "Osei", "Müller",
        "Rossi", "Patel", "Andersen", "Dubois", "Kim", "Lopez", "Novak", "Ahmed", "Brown", "Costa"]
CITIES = [("Portland", "OR", "97205"), ("Austin", "TX", "73301"), ("Denver", "CO", "80202"),
          ("Chicago", "IL", "60601"), ("Seattle", "WA", "98101"), ("Boston", "MA", "02108"),
          ("Atlanta", "GA", "30303"), ("San Diego", "CA", "92101"), ("Madison", "WI", "53703")]
STREETS = ["Maple Ave", "Cedar St", "Harbor Rd", "Willow Ln", "Summit Dr", "Lakeview Blvd", "Orchard Way"]
SEARCH_QUERIES = [
    "laptop for programming", "gaming laptop", "noise cancelling headphones", "running shoes", "trail running shoes",
    "mirrorless camera", "camera lens", "standing desk", "espresso machine", "yoga mat", "rain jacket",
    "tent", "smartwatch gps", "budget phone", "wireless earbuds", "usb c hub", "moisturizer sensitive skin",
    "board game family", "4k monitor", "air fryer", "chromebook", "carbon running shoe", "hiking backpack",
]


def slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return value[:200]


def money(v: float | Decimal) -> Decimal:
    return Decimal(str(v)).quantize(CENT, rounding=ROUND_HALF_UP)


def _wipe(db: Session) -> None:
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    db.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


class Seeder:
    def __init__(self, db: Session, rng_seed: int = 42) -> None:
        self.db = db
        self.rng = random.Random(rng_seed)
        self.now = datetime.now(UTC).replace(microsecond=0)
        self.storage = get_storage()
        self.settings = get_settings()

    # ------------------------------------------------------------------ users
    def _role(self, name: str) -> Role:
        return self.db.scalars(select(Role).where(Role.name == name)).one()

    def _user(self, email: str, name: str, pw_hash: str, roles: list[Role], created: datetime) -> User:
        u = User(email=email, full_name=name, password_hash=pw_hash, is_email_verified=True, created_at=created)
        u.user_roles = [UserRole(role_id=r.id) for r in roles]
        self.db.add(u)
        return u

    def seed_users(self) -> None:
        buyer_r, seller_r, admin_r = self._role(RoleName.BUYER), self._role(RoleName.SELLER), self._role(RoleName.ADMIN)
        shared_hash = hash_password(DEFAULT_PASSWORD)
        start = self.now - timedelta(days=DAYS_OF_HISTORY + 30)

        email, pw, name = DEMO_ACCOUNTS["admin"]
        self.admin = self._user(email, name, hash_password(pw), [admin_r], start)

        self.sellers: list[SellerProfile] = []
        for i, (store, owner, local, desc, negotiable) in enumerate(SELLERS):
            if i == 0:
                email, pw_hash = DEMO_ACCOUNTS["seller"][0], hash_password(DEMO_ACCOUNTS["seller"][1])
            else:
                email, pw_hash = f"{local}@sellers.example.com", shared_hash
            user = self._user(email, owner, pw_hash, [seller_r, buyer_r], start + timedelta(days=i))
            profile = SellerProfile(
                user=user, store_name=store, slug=slugify(store), description=desc, status=SellerStatus.ACTIVE,
                support_email=email, country="US", negotiation_enabled=negotiable, created_at=user.created_at,
            )
            self.db.add(profile)
            self.sellers.append(profile)

        self.buyers: list[User] = []
        email, pw, name = DEMO_ACCOUNTS["buyer"]
        self.buyers.append(self._user(email, name, hash_password(pw), [buyer_r], start))
        for i in range(59):
            first, last = self.rng.choice(FIRST), self.rng.choice(LAST)
            created = start + timedelta(days=self.rng.randint(0, DAYS_OF_HISTORY))
            self.buyers.append(
                self._user(f"{first.lower()}.{last.lower()}{i}@example.com".replace("ü", "u"),
                           f"{first} {last}", shared_hash, [buyer_r], created)
            )
        self.db.flush()
        for b in self.buyers:
            city, state, zip_ = self.rng.choice(CITIES)
            self.db.add(BuyerProfile(user_id=b.id, display_name=b.full_name.split()[0]))
            self.db.add(Address(
                user_id=b.id, label="Home", recipient_name=b.full_name,
                line1=f"{self.rng.randint(10, 9999)} {self.rng.choice(STREETS)}",
                city=city, state=state, postal_code=zip_, country="US", is_default=True,
            ))
            self.db.add(Cart(user_id=b.id))
            self.db.add(Wishlist(user_id=b.id))
        self.db.flush()
        log.info("users seeded: %d buyers, %d sellers", len(self.buyers), len(self.sellers))

    # --------------------------------------------------------------- catalog
    def seed_catalog(self) -> None:
        self.categories: dict[str, Category] = {}
        for order, (slug, name, parent, icon, desc) in enumerate(CATEGORIES):
            c = Category(slug=slug, name=name, icon=icon, description=desc, sort_order=order,
                         parent=self.categories.get(parent) if parent else None)
            self.db.add(c)
            self.categories[slug] = c
        self.db.flush()
        root_of = {slug: (parent or slug) for slug, _, parent, _, _ in CATEGORIES}

        self.products: list[Product] = []
        self.popularity: dict[uuid.UUID, float] = {}
        self.quality: dict[uuid.UUID, float] = {}
        for i, spec in enumerate(PRODUCTS):
            seller = self.sellers[spec["s"]]
            cat = self.categories[spec["cat"]]
            sku = f"{seller.slug[:4].upper()}-{i + 1:04d}"
            desc = self._description(spec)
            p = Product(
                seller=seller, category=cat, name=spec["name"], slug=slugify(spec["name"]), sku=sku,
                brand=spec["brand"], price=money(spec["price"]),
                sale_price=money(spec["sale"]) if spec["sale"] else None, currency="USD",
                attributes=spec["attrs"], tags=spec["tags"], description=desc,
                seo_description=spec["blurb"][:300], status=ProductStatus.ACTIVE,
                created_at=self.now - timedelta(days=DAYS_OF_HISTORY + self.rng.randint(0, 20)),
            )
            p.published_at = p.created_at
            self.db.add(p)
            self.products.append(p)
        self.db.flush()

        for p, spec in zip(self.products, PRODUCTS, strict=True):
            self.popularity[p.id] = self.rng.uniform(0.3, 1.0) * (1.4 if spec["sale"] else 1.0)
            self.quality[p.id] = self.rng.uniform(3.3, 4.8)
            root = root_of[spec["cat"]]
            key = f"products/seed/{p.slug}.svg"
            url = self.storage.save(key, render_product_svg(p.name, p.brand, root), "image/svg+xml")
            alt = self.storage.save(f"products/seed/{p.slug}-2.svg", render_product_svg(p.name, p.brand, root, 1),
                                    "image/svg+xml")
            p.images = [ProductImage(url=url, alt_text=p.name, is_primary=True, sort_order=0),
                        ProductImage(url=alt, alt_text=f"{p.name} — alternate view", sort_order=1)]
            on_hand = self.rng.choice([0, 2, 3, 4]) if self.rng.random() < 0.15 else self.rng.randint(15, 180)
            p.inventory = [Inventory(quantity_on_hand=on_hand, low_stock_threshold=self.rng.choice([5, 8, 10]))]
        cat_names = {c.id: c.name for c in self.categories.values()}
        index_products(self.products, cat_names)
        self.db.flush()
        self.by_name = {p.name: p for p in self.products}
        log.info("catalog seeded: %d categories, %d products", len(self.categories), len(self.products))

    @staticmethod
    def _description(spec: dict[str, Any]) -> str:
        lines = [spec["blurb"], "", "Key specifications:"]
        for k, v in spec["attrs"].items():
            label = k.replace("_", " ").replace(" gb", " (GB)").replace(" kg", " (kg)").capitalize()
            if isinstance(v, bool):
                v = "Yes" if v else "No"
            elif isinstance(v, list):
                v = ", ".join(map(str, v))
            lines.append(f"• {label}: {v}")
        return "\n".join(lines)

    # ------------------------------------------------------------ promotions
    def seed_promotions(self) -> None:
        now, d = self.now, timedelta(days=1)
        P = self.by_name
        offers = [
            Offer(product_id=P["Voltrix AeroBook 14"].id, seller_id=self.sellers[0].id, name="AeroBook launch week",
                  description="5% off the AeroBook 14 during launch week", discount_type=DiscountType.PERCENTAGE,
                  value=5, starts_at=now - 3 * d, ends_at=now + 11 * d),
            Offer(product_id=P["SonicWave Quiet 900 Headphones"].id, seller_id=self.sellers[3].id,
                  name="Quiet 900 travel deal", discount_type=DiscountType.FIXED, value=25,
                  description="$25 off for the travel season", starts_at=now - 5 * d, ends_at=now + 20 * d),
            Offer(product_id=P["Aperture Lumix LX-7 Mirrorless Camera"].id, seller_id=self.sellers[4].id,
                  name="LX-7 creator promo", discount_type=DiscountType.PERCENTAGE, value=7,
                  description="7% off the LX-7 body", starts_at=now - 2 * d, ends_at=now + 14 * d),
            Offer(seller_id=self.sellers[6].id, name="Northpeak autumn sale", discount_type=DiscountType.PERCENTAGE,
                  value=10, description="10% off everything from Northpeak Outfitters",
                  starts_at=now - 7 * d, ends_at=now + 21 * d),
            Offer(category_id=self.categories["laptops"].id, name="Back to school: laptops",
                  description="Marketplace-wide $20 off any laptop", discount_type=DiscountType.FIXED, value=20,
                  starts_at=now - 10 * d, ends_at=now + 10 * d),
            Offer(product_id=P["FlexFit Resistance Band Set"].id, seller_id=self.sellers[9].id,
                  name="Buy 2, save 15%", discount_type=DiscountType.PERCENTAGE, value=15, min_quantity=2,
                  description="Save 15% when you buy two or more band sets", starts_at=now - 30 * d),
            Offer(product_id=P["Stridewell Carbon Race Elite"].id, seller_id=self.sellers[5].id,
                  name="Summer race sale", discount_type=DiscountType.PERCENTAGE, value=20,
                  description="Expired summer promotion", starts_at=now - 60 * d, ends_at=now - 30 * d),
            Offer(product_id=P["Hearth BrewMaster Espresso Machine"].id, seller_id=self.sellers[7].id,
                  name="Holiday coffee preview", discount_type=DiscountType.FIXED, value=50,
                  description="Starts next week", starts_at=now + 7 * d, ends_at=now + 30 * d),
            Offer(product_id=P["Glow Botanics Hydra Serum"].id, seller_id=self.sellers[10].id,
                  name="Hydration week", discount_type=DiscountType.PERCENTAGE, value=10,
                  description="10% off the Hydra Serum", starts_at=now - 1 * d, ends_at=now + 6 * d),
        ]
        self.db.add_all(offers)
        self.db.add_all([
            Coupon(code="WELCOME10", description="10% off your first order", discount_type=DiscountType.PERCENTAGE,
                   value=10, per_user_limit=1, starts_at=now - 365 * d),
            Coupon(code="SAVE20", description="$20 off orders over $150", discount_type=DiscountType.FIXED,
                   value=20, min_subtotal=150, per_user_limit=3, starts_at=now - 30 * d, ends_at=now + 60 * d),
            Coupon(code="NORTHPEAK15", seller_id=self.sellers[6].id, description="15% off Northpeak Outfitters",
                   discount_type=DiscountType.PERCENTAGE, value=15, per_user_limit=1, usage_limit=500),
            Coupon(code="SPRING5", description="Expired spring coupon", discount_type=DiscountType.FIXED, value=5,
                   starts_at=now - 200 * d, ends_at=now - 100 * d),
        ])
        for spec in BUNDLES:
            dtype, value = spec["discount"]
            b = Bundle(seller_id=self.sellers[spec["seller"]].id, name=spec["name"], slug=slugify(spec["name"]),
                       description=spec["description"], discount_type=DiscountType(dtype), value=value,
                       starts_at=now - 60 * d)
            b.items = [BundleItem(product_id=P[n].id, quantity=1) for n in spec["products"]]
            self.db.add(b)
        for s in self.sellers:
            if s.negotiation_enabled:
                self.db.add(NegotiationRule(seller_id=s.id, product_id=None, max_discount_percent=12,
                                            auto_accept_percent=5))
        self.db.add_all([
            NegotiationRule(seller_id=self.sellers[4].id, product_id=P["Aperture LX-9 Full-Frame Camera"].id,
                            max_discount_percent=8, auto_accept_percent=3),
            NegotiationRule(seller_id=self.sellers[0].id, product_id=P["Voltrix AeroBook Pro 16"].id,
                            max_discount_percent=10, auto_accept_percent=6),
            NegotiationRule(seller_id=self.sellers[0].id, product_id=P["Voltrix StudyBook 15"].id,
                            is_enabled=False, max_discount_percent=0, auto_accept_percent=0),
        ])
        self.db.flush()
        log.info("promotions seeded: %d offers, 4 coupons, %d bundles", len(offers), len(BUNDLES))

    # ---------------------------------------------------------------- orders
    def _status_for_age(self, age_days: float) -> OrderStatus:
        r = self.rng.random()
        if age_days > 14:
            return OrderStatus.DELIVERED if r < 0.88 else (OrderStatus.CANCELLED if r < 0.95 else OrderStatus.REFUNDED)
        if age_days > 7:
            return OrderStatus.DELIVERED if r < 0.6 else (OrderStatus.SHIPPED if r < 0.9 else OrderStatus.CANCELLED)
        if age_days > 3:
            return OrderStatus.SHIPPED if r < 0.5 else (OrderStatus.PROCESSING if r < 0.8 else OrderStatus.DELIVERED)
        return OrderStatus.PENDING if r < 0.3 else (OrderStatus.CONFIRMED if r < 0.7 else OrderStatus.PROCESSING)

    def seed_orders(self) -> None:
        by_seller: dict[uuid.UUID, list[Product]] = {}
        for p in self.products:
            by_seller.setdefault(p.seller_id, []).append(p)
        sellers = list(by_seller)
        seller_weights = [sum(self.popularity[p.id] for p in by_seller[s]) for s in sellers]
        tax_rate, ship_rate, free_ship = self.settings.tax_rate, self.settings.shipping_flat_rate, self.settings.free_shipping_threshold
        addresses = {a.user_id: a for a in self.db.scalars(select(Address))}

        self.delivered_items: list[tuple[User, Product, Order]] = []
        events: list[dict[str, Any]] = []
        seq = 0
        flow = [OrderStatus.PENDING, OrderStatus.CONFIRMED, OrderStatus.PROCESSING, OrderStatus.SHIPPED,
                OrderStatus.DELIVERED]
        for day in range(DAYS_OF_HISTORY, -1, -1):
            day_start = (self.now - timedelta(days=day)).replace(hour=0, minute=0, second=0)
            trend = 2.0 + (DAYS_OF_HISTORY - day) * 0.022
            weekday = day_start.weekday()
            season = {4: 1.2, 5: 1.45, 6: 1.35}.get(weekday, 1.0)
            n_orders = max(0, round(self.rng.gauss(trend * season, 1.1)))
            for _ in range(n_orders):
                placed = day_start + timedelta(minutes=self.rng.randint(6 * 60, 23 * 60))
                if placed > self.now:
                    placed = self.now - timedelta(minutes=self.rng.randint(5, 300))
                buyer = self.rng.choice(self.buyers)
                seller_id = self.rng.choices(sellers, weights=seller_weights)[0]
                pool = by_seller[seller_id]
                k = min(len(pool), self.rng.choices([1, 2, 3], weights=[70, 22, 8])[0])
                chosen = set()
                while len(chosen) < k:
                    chosen.add(self.rng.choices(pool, weights=[self.popularity[p.id] for p in pool])[0])
                status = self._status_for_age((self.now - placed).total_seconds() / 86400)
                seq += 1
                order = Order(
                    order_number=f"GO-{placed:%y%m%d}-{seq:05d}", checkout_group_id=uuid.uuid4(),
                    buyer_id=buyer.id, seller_id=seller_id, status=status, currency="USD",
                    placed_at=placed, created_at=placed,
                    shipping_address=self._address_snapshot(addresses[buyer.id]), subtotal=0, total=0,
                )
                subtotal = Decimal(0)
                for p in chosen:
                    qty = self.rng.choices([1, 2], weights=[88, 12])[0]
                    unit = p.effective_list_price
                    line = (unit * qty).quantize(CENT)
                    subtotal += line
                    order.items.append(OrderItem(product_id=p.id, product_name=p.name, sku=p.sku, unit_price=unit,
                                                 quantity=qty, line_total=line))
                    if status not in (OrderStatus.CANCELLED,):
                        p.sold_count += qty
                    events.append(dict(event_type="purchase", user_id=buyer.id, product_id=p.id, seller_id=seller_id,
                                       category_id=p.category_id, value=line, created_at=placed,
                                       properties={"quantity": qty}))
                discount = Decimal(0)
                if self.rng.random() < 0.12:
                    discount = (subtotal * Decimal("0.10")).quantize(CENT)
                    order.discounts.append(Discount(source=DiscountSource.COUPON, description="WELCOME10 coupon",
                                                    amount=discount))
                shipping = Decimal(0) if subtotal >= free_ship else ship_rate
                tax = ((subtotal - discount) * tax_rate).quantize(CENT)
                order.subtotal, order.discount_total, order.shipping_total, order.tax_total = subtotal, discount, shipping, tax
                order.total = subtotal - discount + shipping + tax
                # status history
                reached = flow[: flow.index(status) + 1] if status in flow else flow[: self.rng.randint(1, 3)]
                t = placed
                prev = None
                for st in reached:
                    order.status_events.append(OrderStatusEvent(from_status=prev, to_status=st.value, created_at=t))
                    if st == OrderStatus.CONFIRMED:
                        order.confirmed_at = t
                    elif st == OrderStatus.SHIPPED:
                        order.shipped_at = t
                        order.tracking_number = f"1Z{self.rng.randint(10**9, 10**10 - 1)}"
                    elif st == OrderStatus.DELIVERED:
                        order.delivered_at = t
                    prev = st.value
                    t = min(t + timedelta(hours=self.rng.randint(4, 60)), self.now)
                if status in (OrderStatus.CANCELLED, OrderStatus.REFUNDED):
                    order.status_events.append(OrderStatusEvent(from_status=prev, to_status=status.value, created_at=t))
                    if status == OrderStatus.CANCELLED:
                        order.cancelled_at = t
                pay_status = {
                    OrderStatus.PENDING: PaymentStatus.PENDING, OrderStatus.CANCELLED: PaymentStatus.REFUNDED,
                    OrderStatus.REFUNDED: PaymentStatus.REFUNDED,
                }.get(status, PaymentStatus.CAPTURED)
                order.payments.append(Payment(provider="sandbox", provider_reference=f"sbx_{uuid.uuid4().hex[:18]}",
                                              amount=order.total, currency="USD", status=pay_status,
                                              created_at=placed))
                self.db.add(order)
                if status == OrderStatus.DELIVERED:
                    for p in chosen:
                        self.delivered_items.append((buyer, p, order))
        self.db.flush()
        self._events = events
        log.info("orders seeded: %d", seq)

    @staticmethod
    def _address_snapshot(a: Address) -> dict[str, Any]:
        return {"recipient_name": a.recipient_name, "line1": a.line1, "line2": a.line2, "city": a.city,
                "state": a.state, "postal_code": a.postal_code, "country": a.country}

    # --------------------------------------------------------------- reviews
    def seed_reviews(self) -> None:
        root_of = {slug: (parent or slug) for slug, _, parent, _, _ in CATEGORIES}
        seen: set[tuple[uuid.UUID, uuid.UUID]] = set()
        count = 0
        for buyer, product, order in self.delivered_items:
            if (product.id, buyer.id) in seen or self.rng.random() > 0.45:
                continue
            seen.add((product.id, buyer.id))
            rating = max(1, min(5, round(self.rng.gauss(self.quality[product.id], 0.95))))
            pos, neg = REVIEW_ASPECTS[root_of[product.category.slug]]
            if rating >= 4:
                parts = self.rng.sample(pos, 2)
                body = f"{parts[0].capitalize()} and {parts[1]}."
                if rating == 4 and self.rng.random() < 0.6:
                    body += f" Only complaint: {self.rng.choice(neg)}."
                title = self.rng.choice(["Love it", "Highly recommend", "Great purchase", "Exceeded expectations"])
            elif rating == 3:
                body = f"{self.rng.choice(pos).capitalize()}, but {self.rng.choice(neg)}."
                title = self.rng.choice(["It's okay", "Mixed feelings", "Decent but not perfect"])
            else:
                parts = self.rng.sample(neg, 2)
                body = f"Disappointed: {parts[0]} and {parts[1]}."
                title = self.rng.choice(["Not worth it", "Disappointed", "Would not buy again"])
            created = (order.delivered_at or order.placed_at) + timedelta(days=self.rng.randint(1, 10))
            created = min(created, self.now)
            status = ReviewStatus.APPROVED if self.rng.random() > 0.05 else ReviewStatus.PENDING
            self.db.add(Review(product_id=product.id, user_id=buyer.id, order_id=order.id, rating=rating, title=title,
                               body=body, status=status, is_verified_purchase=True,
                               helpful_count=self.rng.randint(0, 25), created_at=created, updated_at=created))
            count += 1
        self.db.flush()
        rows = self.db.execute(
            select(Review.product_id, Review.rating, func.count())
            .where(Review.status == ReviewStatus.APPROVED)
            .group_by(Review.product_id, Review.rating)
        ).all()
        agg: dict[uuid.UUID, dict[str, int]] = {}
        for pid, rating, n in rows:
            agg.setdefault(pid, {str(i): 0 for i in range(1, 6)})[str(rating)] = n
        for p in self.products:
            dist = agg.get(p.id, {str(i): 0 for i in range(1, 6)})
            total = sum(dist.values())
            avg = (Decimal(sum(int(k) * v for k, v in dist.items())) / total).quantize(CENT) if total else Decimal(0)
            p.rating_avg, p.rating_count = avg, total
            self.db.add(Rating(product_id=p.id, average=avg, count=total, distribution=dist))
        for s in self.sellers:
            rated = [p for p in self.products if p.seller_id == s.id and p.rating_count]
            if rated:
                s.rating_avg = (sum(p.rating_avg * p.rating_count for p in rated) /
                                sum(p.rating_count for p in rated)).quantize(CENT)
        self.db.flush()
        log.info("reviews seeded: %d", count)

    # ------------------------------------------------------------- analytics
    def seed_analytics(self) -> None:
        events = self._events
        weights = [self.popularity[p.id] for p in self.products]
        for _ in range(9000):
            p = self.rng.choices(self.products, weights=weights)[0]
            age = self.rng.triangular(0, DAYS_OF_HISTORY, 0)
            ts = self.now - timedelta(days=age, minutes=self.rng.randint(0, 1439))
            user = self.rng.choice(self.buyers) if self.rng.random() < 0.6 else None
            events.append(dict(event_type="product_view", user_id=user.id if user else None, product_id=p.id,
                               seller_id=p.seller_id, category_id=p.category_id, value=None, created_at=ts,
                               properties={"source": self.rng.choice(["search", "home", "category", "nova"])}))
            if user and self.rng.random() < 0.22:
                events.append(dict(event_type="add_to_cart", user_id=user.id, product_id=p.id, seller_id=p.seller_id,
                                   category_id=p.category_id, value=p.effective_list_price,
                                   created_at=ts + timedelta(minutes=2), properties={"quantity": 1}))
        history = []
        for _ in range(1500):
            q = self.rng.choice(SEARCH_QUERIES)
            ts = self.now - timedelta(days=self.rng.triangular(0, DAYS_OF_HISTORY, 0))
            user = self.rng.choice(self.buyers) if self.rng.random() < 0.5 else None
            n = self.rng.randint(0, 14)
            history.append(dict(id=uuid.uuid4(), user_id=user.id if user else None, query=q, filters={},
                                mode="hybrid", source=self.rng.choice(["web", "web", "nova"]), result_count=n,
                                latency_ms=self.rng.randint(12, 90), created_at=ts))
            events.append(dict(event_type="search", user_id=user.id if user else None, product_id=None,
                               seller_id=None, category_id=None, value=None, created_at=ts,
                               properties={"query": q, "result_count": n}))
        for e in events:
            e.setdefault("id", uuid.uuid4())
        self._bulk_insert(AnalyticsEvent, events)
        self._bulk_insert(SearchHistory, history)
        # wishlist items for a few buyers
        wishlist_ids = dict(self.db.execute(select(Wishlist.user_id, Wishlist.id)).tuples().all())
        for b in self.buyers[:25]:
            for p in self.rng.sample(self.products, 3):
                self.db.add(WishlistItem(wishlist_id=wishlist_ids[b.id], product_id=p.id))
        self.db.flush()
        log.info("analytics seeded: %d events, %d searches", len(events), len(history))

    def _bulk_insert(self, model: type[Base], rows: list[dict[str, Any]], chunk: int = 1000) -> None:
        """Multi-row VALUES inserts (one round trip per chunk)."""
        table = model.__table__
        for i in range(0, len(rows), chunk):
            self.db.execute(insert(table).values(rows[i : i + chunk]))

    def run(self) -> dict[str, int]:
        self.seed_users()
        self.seed_catalog()
        self.seed_promotions()
        self.seed_orders()
        self.seed_reviews()
        self.seed_analytics()
        return {
            "users": self.db.scalar(select(func.count()).select_from(User)) or 0,
            "sellers": len(self.sellers),
            "products": len(self.products),
            "orders": self.db.scalar(select(func.count()).select_from(Order)) or 0,
            "reviews": self.db.scalar(select(func.count()).select_from(Review)) or 0,
            "offers": self.db.scalar(select(func.count()).select_from(Offer)) or 0,
            "bundles": self.db.scalar(select(func.count()).select_from(Bundle)) or 0,
            "analytics_events": self.db.scalar(select(func.count()).select_from(AnalyticsEvent)) or 0,
        }


def seed(reset: bool = False) -> dict[str, int] | None:
    with session_scope() as db:
        if reset:
            _wipe(db)
        ensure_reference_data(db)
        if db.scalar(select(func.count()).select_from(User)):
            log.info("database already contains users; skipping demo seed (use --reset to reseed)")
            return None
        return Seeder(db).run()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed synthetic marketplace data")
    parser.add_argument("--reset", action="store_true", help="truncate all tables before seeding")
    args = parser.parse_args()
    configure_logging("INFO", json_logs=False)
    started = date.today()
    result = seed(reset=args.reset)
    log.info("seed complete (%s): %s", started.isoformat(), result)


if __name__ == "__main__":
    main()
