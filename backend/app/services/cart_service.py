"""Shopping cart and wishlist. Totals are always recomputed server-side by the PricingEngine."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationFailed
from app.models.analytics import AnalyticsEvent
from app.models.catalog import Product, ProductVariant
from app.models.commerce import Cart, CartItem, Discount, Order, Wishlist, WishlistItem
from app.models.enums import DiscountSource, OrderStatus, ProductStatus, SellerStatus
from app.models.promotions import Bundle, Coupon
from app.schemas.catalog import ProductCard
from app.schemas.commerce import CartLineOut, CartOut, DiscountOut, SellerGroupOut
from app.services.catalog_service import product_card
from app.services.pricing import LineInput, PricedCart, PricingEngine
from app.services.promotion_service import is_bundle_live

MAX_LINES = 50


def coupon_uses_by(db: Session, coupon: Coupon, user_id: uuid.UUID) -> int:
    return db.scalar(
        select(func.count(func.distinct(Order.checkout_group_id)))
        .join(Discount, Discount.order_id == Order.id)
        .where(Order.buyer_id == user_id, Discount.source == DiscountSource.COUPON, Discount.source_id == coupon.id,
               Order.status != OrderStatus.CANCELLED)
    ) or 0


class CartService:
    def __init__(self, db: Session, user_id: uuid.UUID) -> None:
        self.db = db
        self.user_id = user_id

    def cart(self, lock: bool = False) -> Cart:
        stmt = select(Cart).where(Cart.user_id == self.user_id)
        if lock:
            stmt = stmt.with_for_update()
        cart = self.db.scalar(stmt)
        if cart is None:
            cart = Cart(user_id=self.user_id)
            self.db.add(cart)
            self.db.flush()
        return cart

    # ------------------------------------------------------------ pricing
    def price(self, cart: Cart | None = None, shipping_address: dict | None = None) -> tuple[Cart, PricedCart]:
        cart = cart or self.cart()
        variants = {v.id: v for v in self.db.scalars(
            select(ProductVariant).where(ProductVariant.id.in_([i.variant_id for i in cart.items if i.variant_id]))
        )} if any(i.variant_id for i in cart.items) else {}
        lines = [LineInput(i.product, i.quantity, variants.get(i.variant_id), i.bundle_id, i.id) for i in cart.items]
        coupon, uses = None, 0
        if cart.coupon_code:
            coupon = self.db.scalar(select(Coupon).where(Coupon.code == cart.coupon_code))
            if coupon:
                uses = coupon_uses_by(self.db, coupon, self.user_id)
        priced = PricingEngine(self.db).price_lines(
            lines, buyer_id=self.user_id, coupon=coupon, coupon_uses_by_buyer=uses, shipping_address=shipping_address
        )
        if cart.coupon_code and coupon is None:
            priced.coupon_message = "Coupon code not recognised"
        return cart, priced

    def view(self) -> CartOut:
        cart, priced = self.price()
        return to_cart_out(cart, priced)

    # ------------------------------------------------------------ mutations
    def _product_for_cart(self, product_id: uuid.UUID) -> Product:
        p = self.db.scalar(select(Product).where(Product.id == product_id, Product.deleted_at.is_(None)))
        if p is None or p.status != ProductStatus.ACTIVE or p.seller.status != SellerStatus.ACTIVE:
            raise NotFoundError("Product was not found", code="PRODUCT_NOT_FOUND")
        return p

    def add(self, product_id: uuid.UUID, quantity: int, variant_id: uuid.UUID | None = None,
            bundle_id: uuid.UUID | None = None, source: str = "web") -> CartOut:
        p = self._product_for_cart(product_id)
        if variant_id and not any(v.id == variant_id and v.is_active for v in p.variants):
            raise ValidationFailed("Unknown variant for this product", code="VARIANT_NOT_FOUND")
        cart = self.cart(lock=True)
        line = next((i for i in cart.items
                     if i.product_id == product_id and i.variant_id == variant_id and i.bundle_id == bundle_id), None)
        new_qty = (line.quantity if line else 0) + quantity
        self._check_stock(p, new_qty)
        if line:
            line.quantity = new_qty
        else:
            if len(cart.items) >= MAX_LINES:
                raise ValidationFailed("Your cart is full", code="CART_FULL")
            cart.items.append(CartItem(product_id=p.id, variant_id=variant_id, bundle_id=bundle_id, quantity=quantity,
                                       product=p))
        self.db.add(AnalyticsEvent(event_type="add_to_cart", user_id=self.user_id, product_id=p.id,
                                   seller_id=p.seller_id, category_id=p.category_id, value=p.effective_list_price,
                                   properties={"quantity": quantity, "source": source}))
        self.db.commit()
        return self.view()

    def add_bundle(self, bundle_id: uuid.UUID, source: str = "web") -> CartOut:
        bundle = self.db.scalar(select(Bundle).where(Bundle.id == bundle_id, Bundle.deleted_at.is_(None)))
        if bundle is None or not is_bundle_live(bundle):
            raise NotFoundError("Bundle was not found or is not active", code="BUNDLE_NOT_FOUND")
        for item in bundle.items:
            p = self._product_for_cart(item.product_id)
            self._check_stock(p, item.quantity)
        cart = self.cart(lock=True)
        for item in bundle.items:
            line = next((i for i in cart.items if i.product_id == item.product_id and i.bundle_id == bundle.id
                         and i.variant_id is None), None)
            if line:
                line.quantity += item.quantity
            else:
                cart.items.append(CartItem(product_id=item.product_id, bundle_id=bundle.id, quantity=item.quantity,
                                           product=item.product))
        self.db.add(AnalyticsEvent(event_type="add_bundle_to_cart", user_id=self.user_id,
                                   properties={"bundle_id": str(bundle.id), "source": source}))
        self.db.commit()
        return self.view()

    def _line(self, item_id: uuid.UUID) -> CartItem:
        cart = self.cart()
        line = next((i for i in cart.items if i.id == item_id), None)
        if line is None:  # also prevents touching other users' cart lines
            raise NotFoundError("Cart item was not found", code="CART_ITEM_NOT_FOUND")
        return line

    def update(self, item_id: uuid.UUID, quantity: int) -> CartOut:
        line = self._line(item_id)
        self._check_stock(line.product, quantity)
        line.quantity = quantity
        self.db.commit()
        return self.view()

    def remove(self, item_id: uuid.UUID) -> CartOut:
        line = self._line(item_id)
        cart = self.cart()
        cart.items.remove(line)
        self.db.commit()
        return self.view()

    def clear(self) -> CartOut:
        cart = self.cart()
        cart.items.clear()
        cart.coupon_code = None
        self.db.commit()
        return self.view()

    def apply_coupon(self, code: str) -> CartOut:
        coupon = self.db.scalar(select(Coupon).where(Coupon.code == code, Coupon.deleted_at.is_(None)))
        if coupon is None:
            raise ValidationFailed("Coupon code not recognised", code="COUPON_INVALID")
        cart = self.cart()
        cart.coupon_code = coupon.code
        _, priced = self.price(cart)
        if priced.coupon is None:
            cart.coupon_code = None
            self.db.rollback()
            raise ValidationFailed(priced.coupon_message or "Coupon cannot be applied", code="COUPON_NOT_APPLICABLE")
        self.db.commit()
        return self.view()

    def remove_coupon(self) -> CartOut:
        self.cart().coupon_code = None
        self.db.commit()
        return self.view()

    @staticmethod
    def _check_stock(p: Product, quantity: int) -> None:
        if quantity > p.stock:
            raise ValidationFailed(
                f"Only {p.stock} unit(s) of '{p.name}' are available", code="INSUFFICIENT_STOCK",
                details={"available": p.stock},
            )


def to_cart_out(cart: Cart, priced: PricedCart) -> CartOut:
    items = []
    for pl in priced.lines:
        p = pl.input.product
        items.append(CartLineOut(
            id=pl.input.line_id or uuid.uuid4(), product_id=p.id, product_slug=p.slug, product_name=p.name,
            image_url=p.primary_image_url, seller_id=p.seller_id, seller_name=p.seller.store_name,
            variant_id=pl.input.variant.id if pl.input.variant else None, bundle_id=pl.input.bundle_id,
            quantity=pl.quantity, unit_price=pl.unit_price, list_price=pl.list_price, subtotal=pl.subtotal,
            discounts=[DiscountOut(source=d.source, description=d.description, amount=d.amount) for d in pl.discounts],
            total=pl.total, available=pl.available, issues=pl.issues,
        ))
    return CartOut(
        id=cart.id, items=items,
        sellers=[SellerGroupOut(seller_id=s.seller_id, store_name=s.store_name, subtotal=s.subtotal,
                                discount_total=s.discount_total, shipping=s.shipping, tax=s.tax, total=s.total)
                 for s in priced.sellers.values()],
        coupon_code=cart.coupon_code, coupon_message=priced.coupon_message, coupon_discount=priced.coupon_discount,
        subtotal=priced.subtotal, discount_total=priced.discount_total, shipping_total=priced.shipping_total,
        tax_total=priced.tax_total, total=priced.total, currency=priced.currency,
        item_count=sum(pl.quantity for pl in priced.lines), issues=priced.issues,
    )


class WishlistService:
    def __init__(self, db: Session, user_id: uuid.UUID) -> None:
        self.db = db
        self.user_id = user_id

    def _wishlist(self) -> Wishlist:
        wl = self.db.scalar(select(Wishlist).where(Wishlist.user_id == self.user_id))
        if wl is None:
            wl = Wishlist(user_id=self.user_id)
            self.db.add(wl)
            self.db.flush()
        return wl

    def view(self) -> list[ProductCard]:
        engine = PricingEngine(self.db)
        return [product_card(i.product, engine) for i in self._wishlist().items
                if i.product.deleted_at is None and i.product.status == ProductStatus.ACTIVE]

    def add(self, product_id: uuid.UUID) -> list[ProductCard]:
        CartService(self.db, self.user_id)._product_for_cart(product_id)
        wl = self._wishlist()
        if not any(i.product_id == product_id for i in wl.items):
            wl.items.append(WishlistItem(product_id=product_id))
            self.db.add(AnalyticsEvent(event_type="add_to_wishlist", user_id=self.user_id, product_id=product_id))
        self.db.commit()
        self.db.expire_all()
        return self.view()

    def remove(self, product_id: uuid.UUID) -> list[ProductCard]:
        wl = self._wishlist()
        for i in list(wl.items):
            if i.product_id == product_id:
                wl.items.remove(i)
        self.db.commit()
        return self.view()
