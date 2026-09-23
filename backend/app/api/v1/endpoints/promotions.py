"""/api/v1/offers, /api/v1/bundles, /api/v1/reviews."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentPrincipal, DbSession
from app.core.rbac import P
from app.schemas.promotions import (
    BundleIn,
    BundleOut,
    BundleUpdate,
    CouponIn,
    CouponOut,
    OfferIn,
    OfferOut,
    OfferUpdate,
)
from app.schemas.reviews import ReviewOut, ReviewUpdate
from app.services.promotion_service import PromotionService
from app.services.review_service import ReviewService

offers = APIRouter(prefix="/offers", tags=["offers"])
bundles = APIRouter(prefix="/bundles", tags=["bundles"])
reviews = APIRouter(prefix="/reviews", tags=["reviews"])


# ------------------------------------------------------------------ offers
@offers.get("", response_model=list[OfferOut])
def active_offers(db: DbSession, seller_id: uuid.UUID | None = None) -> list[OfferOut]:
    """Currently active, automatically applied offers."""
    return PromotionService(db).list_offers(seller_id=seller_id, active_only=True)


@offers.post("", response_model=OfferOut, status_code=status.HTTP_201_CREATED)
def create_offer(body: OfferIn, principal: CurrentPrincipal, db: DbSession) -> OfferOut:
    principal.require(P.OFFERS_MANAGE_OWN, P.OFFERS_MANAGE_ALL)
    return PromotionService(db).create_offer(body, principal)


@offers.patch("/{offer_id}", response_model=OfferOut)
def update_offer(offer_id: uuid.UUID, body: OfferUpdate, principal: CurrentPrincipal, db: DbSession) -> OfferOut:
    principal.require(P.OFFERS_MANAGE_OWN, P.OFFERS_MANAGE_ALL)
    return PromotionService(db).update_offer(offer_id, body, principal)


@offers.delete("/{offer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_offer(offer_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> Response:
    principal.require(P.OFFERS_MANAGE_OWN, P.OFFERS_MANAGE_ALL)
    PromotionService(db).delete_offer(offer_id, principal)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@offers.get("/coupons", response_model=list[CouponOut])
def list_coupons(principal: CurrentPrincipal, db: DbSession) -> list[CouponOut]:
    principal.require(P.OFFERS_MANAGE_OWN, P.OFFERS_MANAGE_ALL)
    scope = None if principal.has(P.OFFERS_MANAGE_ALL) else principal.require_seller()
    return PromotionService(db).list_coupons(scope)


@offers.post("/coupons", response_model=CouponOut, status_code=status.HTTP_201_CREATED)
def create_coupon(body: CouponIn, principal: CurrentPrincipal, db: DbSession) -> CouponOut:
    principal.require(P.OFFERS_MANAGE_OWN, P.OFFERS_MANAGE_ALL)
    return PromotionService(db).create_coupon(body, principal)


@offers.delete("/coupons/{coupon_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_coupon(coupon_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> Response:
    principal.require(P.OFFERS_MANAGE_OWN, P.OFFERS_MANAGE_ALL)
    PromotionService(db).delete_coupon(coupon_id, principal)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------ bundles
@bundles.get("", response_model=list[BundleOut])
def list_bundles(db: DbSession, seller_id: uuid.UUID | None = None, product_id: uuid.UUID | None = None) -> list[BundleOut]:
    return PromotionService(db).list_bundles(seller_id=seller_id, product_id=product_id)


@bundles.get("/{id_or_slug}", response_model=BundleOut)
def get_bundle(id_or_slug: str, db: DbSession) -> BundleOut:
    return PromotionService(db).get_bundle(id_or_slug)


@bundles.post("", response_model=BundleOut, status_code=status.HTTP_201_CREATED)
def create_bundle(body: BundleIn, principal: CurrentPrincipal, db: DbSession) -> BundleOut:
    principal.require(P.OFFERS_MANAGE_OWN, P.OFFERS_MANAGE_ALL)
    return PromotionService(db).create_bundle(body, principal)


@bundles.patch("/{bundle_id}", response_model=BundleOut)
def update_bundle(bundle_id: uuid.UUID, body: BundleUpdate, principal: CurrentPrincipal, db: DbSession) -> BundleOut:
    principal.require(P.OFFERS_MANAGE_OWN, P.OFFERS_MANAGE_ALL)
    return PromotionService(db).update_bundle(bundle_id, body, principal)


@bundles.delete("/{bundle_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bundle(bundle_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> Response:
    principal.require(P.OFFERS_MANAGE_OWN, P.OFFERS_MANAGE_ALL)
    PromotionService(db).delete_bundle(bundle_id, principal)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------ reviews
@reviews.get("/mine", response_model=list[ReviewOut])
def my_reviews(principal: CurrentPrincipal, db: DbSession) -> list[ReviewOut]:
    from sqlalchemy import select

    from app.models.reviews import Review

    svc = ReviewService(db)
    rows = db.scalars(select(Review).where(Review.user_id == principal.user_id, Review.deleted_at.is_(None))
                      .order_by(Review.created_at.desc()))
    return [svc._to_out(r, principal, include_product=True) for r in rows]


@reviews.patch("/{review_id}", response_model=ReviewOut)
def update_review(review_id: uuid.UUID, body: ReviewUpdate, principal: CurrentPrincipal, db: DbSession) -> ReviewOut:
    return ReviewService(db).update(review_id, body, principal)


@reviews.delete("/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_review(review_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> Response:
    ReviewService(db).delete(review_id, principal)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@reviews.post("/{review_id}/helpful", response_model=ReviewOut)
def helpful(review_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> ReviewOut:
    return ReviewService(db).mark_helpful(review_id)
