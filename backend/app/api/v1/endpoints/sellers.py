"""/api/v1/sellers — public storefronts and the seller workspace (`/sellers/me/...`)."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import DbSession, SellerPrincipal
from app.core.errors import NotFoundError
from app.core.rbac import P
from app.models.enums import OrderStatus, SellerStatus
from app.models.identity import SellerProfile
from app.schemas.catalog import InventoryOut, InventoryUpdate, ProductCard
from app.schemas.commerce import OrderOut
from app.schemas.common import MoneyOut, Page
from app.schemas.promotions import BundleOut, NegotiationOut, NegotiationRuleIn, NegotiationRuleOut, OfferOut
from app.services.catalog_service import InventoryService, ProductService, product_card
from app.services.negotiation_service import NegotiationService
from app.services.order_service import OrderService
from app.services.pricing import PricingEngine
from app.services.promotion_service import PromotionService

router = APIRouter(prefix="/sellers", tags=["sellers"])


class SellerPublic(BaseModel):
    id: uuid.UUID
    store_name: str
    slug: str
    description: str | None
    logo_url: str | None
    rating_avg: MoneyOut
    country: str | None
    product_count: int = 0


class SellerProfileOut(SellerPublic):
    support_email: str | None
    status: str
    negotiation_enabled: bool


class SellerProfileUpdate(BaseModel):
    description: str | None = Field(default=None, max_length=2000)
    logo_url: str | None = Field(default=None, max_length=512)
    support_email: str | None = Field(default=None, max_length=255)
    country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")


def _public(db: DbSession, s: SellerProfile) -> dict[str, Any]:
    from sqlalchemy import func

    from app.models.catalog import Product
    from app.models.enums import ProductStatus

    count = db.scalar(select(func.count()).select_from(Product).where(
        Product.seller_id == s.id, Product.status == ProductStatus.ACTIVE, Product.deleted_at.is_(None))) or 0
    return dict(id=s.id, store_name=s.store_name, slug=s.slug, description=s.description, logo_url=s.logo_url,
                rating_avg=s.rating_avg, country=s.country, product_count=count)


@router.get("", response_model=list[SellerPublic])
def list_sellers(db: DbSession) -> list[SellerPublic]:
    rows = db.scalars(select(SellerProfile).where(SellerProfile.status == SellerStatus.ACTIVE,
                                                  SellerProfile.deleted_at.is_(None)).order_by(SellerProfile.store_name))
    return [SellerPublic(**_public(db, s)) for s in rows]


# ------------------------------------------------------------------ seller workspace
@router.get("/me", response_model=SellerProfileOut)
def my_profile(principal: SellerPrincipal, db: DbSession) -> SellerProfileOut:
    s = db.get(SellerProfile, principal.seller_id)
    assert s is not None
    return SellerProfileOut(**_public(db, s), support_email=s.support_email, status=s.status.value,
                            negotiation_enabled=s.negotiation_enabled)


@router.patch("/me", response_model=SellerProfileOut)
def update_profile(body: SellerProfileUpdate, principal: SellerPrincipal, db: DbSession) -> SellerProfileOut:
    s = db.get(SellerProfile, principal.seller_id)
    assert s is not None
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    db.commit()
    return my_profile(principal, db)


@router.get("/me/products", response_model=Page[ProductCard])
def my_products(
    principal: SellerPrincipal, db: DbSession, status: str | None = None, q: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1, page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[ProductCard]:
    principal.require(P.PRODUCTS_MANAGE_OWN)
    assert principal.seller_id
    items, total = ProductService(db).list_for_seller(principal.seller_id, status, q, (page - 1) * page_size, page_size)
    engine = PricingEngine(db)
    return Page(items=[product_card(p, engine) for p in items], total=total, page=page, page_size=page_size)


@router.get("/me/inventory", response_model=list[InventoryOut])
def my_inventory(principal: SellerPrincipal, db: DbSession, low_only: bool = False) -> list[InventoryOut]:
    principal.require(P.INVENTORY_MANAGE_OWN)
    assert principal.seller_id
    return InventoryService(db).list(principal.seller_id, low_only)


@router.patch("/me/inventory/{product_id}", response_model=InventoryOut)
def update_inventory(product_id: uuid.UUID, body: InventoryUpdate, principal: SellerPrincipal, db: DbSession
                     ) -> InventoryOut:
    return InventoryService(db).update(product_id, body, principal)


@router.get("/me/orders", response_model=Page[OrderOut])
def my_orders(
    principal: SellerPrincipal, db: DbSession, status: str | None = None, q: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1, page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[OrderOut]:
    principal.require(P.ORDERS_MANAGE_OWN)
    if status:
        OrderStatus(status)
    items, total = OrderService(db).list(seller_id=principal.seller_id, status=status, q=q,
                                         offset=(page - 1) * page_size, limit=page_size, principal=principal)
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/me/offers", response_model=list[OfferOut])
def my_offers(principal: SellerPrincipal, db: DbSession) -> list[OfferOut]:
    return PromotionService(db).list_offers(seller_id=principal.seller_id, active_only=False)


@router.get("/me/bundles", response_model=list[BundleOut])
def my_bundles(principal: SellerPrincipal, db: DbSession) -> list[BundleOut]:
    return PromotionService(db).list_bundles(seller_id=principal.seller_id, active_only=False)


@router.get("/me/negotiations", response_model=list[NegotiationOut])
def my_negotiations(principal: SellerPrincipal, db: DbSession) -> list[NegotiationOut]:
    assert principal.seller_id
    return NegotiationService(db).list_for_seller(principal.seller_id)


@router.get("/me/negotiation-rules", response_model=list[NegotiationRuleOut])
def my_rules(principal: SellerPrincipal, db: DbSession) -> list[NegotiationRuleOut]:
    assert principal.seller_id
    return NegotiationService(db).rules(principal.seller_id)


@router.put("/me/negotiation-rules", response_model=NegotiationRuleOut)
def upsert_rule(body: NegotiationRuleIn, principal: SellerPrincipal, db: DbSession) -> NegotiationRuleOut:
    return NegotiationService(db).upsert_rule(body, principal)


# ------------------------------------------------------------------ public storefront (declared last)
@router.get("/{slug}", response_model=SellerPublic)
def storefront(slug: str, db: DbSession) -> SellerPublic:
    s = db.scalar(select(SellerProfile).where(SellerProfile.slug == slug, SellerProfile.status == SellerStatus.ACTIVE,
                                              SellerProfile.deleted_at.is_(None)))
    if s is None:
        raise NotFoundError("Seller was not found", code="SELLER_NOT_FOUND")
    return SellerPublic(**_public(db, s))
