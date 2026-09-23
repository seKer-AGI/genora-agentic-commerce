"""/api/v1/categories, /api/v1/products and /api/v1/search."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import CurrentPrincipal, DbSession, OptionalPrincipal, require_permission
from app.core.principal import Principal
from app.core.rbac import P
from app.schemas.catalog import (
    CategoryCreate,
    CategoryOut,
    CategoryTree,
    CategoryUpdate,
    ProductCard,
    ProductCreate,
    ProductDetail,
    ProductUpdate,
)
from app.schemas.common import Page
from app.schemas.promotions import BundleOut, NegotiationOut, NegotiationRequest, ProductOfferOut
from app.schemas.reviews import ReviewEligibility, ReviewIn, ReviewOut, ReviewSummaryOut
from app.schemas.search import SearchQuery, SearchResponse, SuggestResponse
from app.services.catalog_service import CategoryService, ProductService, product_detail
from app.services.negotiation_service import NegotiationService
from app.services.pricing import PricingEngine
from app.services.promotion_service import PromotionService
from app.services.review_service import ReviewService
from app.services.search_service import SearchService

categories = APIRouter(prefix="/categories", tags=["categories"])
products = APIRouter(prefix="/products", tags=["products"])
search = APIRouter(prefix="/search", tags=["search"])

AdminCategories = Annotated[Principal, Depends(require_permission(P.CATEGORIES_MANAGE))]


# ------------------------------------------------------------------ categories
@categories.get("", response_model=list[CategoryTree])
def category_tree(db: DbSession, include_inactive: bool = False) -> list[CategoryTree]:
    return CategoryService(db).tree(include_inactive)


@categories.get("/{id_or_slug}", response_model=CategoryOut)
def get_category(id_or_slug: str, db: DbSession) -> CategoryOut:
    return CategoryOut.model_validate(CategoryService(db).get(id_or_slug))


@categories.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(body: CategoryCreate, principal: AdminCategories, db: DbSession) -> CategoryOut:
    return CategoryOut.model_validate(CategoryService(db).create(body, principal))


@categories.patch("/{category_id}", response_model=CategoryOut)
def update_category(category_id: str, body: CategoryUpdate, principal: AdminCategories, db: DbSession) -> CategoryOut:
    return CategoryOut.model_validate(CategoryService(db).update(category_id, body, principal))


@categories.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: str, principal: AdminCategories, db: DbSession) -> Response:
    CategoryService(db).delete(category_id, principal)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------ search
@search.get("", response_model=SearchResponse)
def search_products(
    db: DbSession,
    principal: OptionalPrincipal,
    params: Annotated[SearchQuery, Query()],
) -> SearchResponse:
    """Keyword, semantic or hybrid product search with filters, sorting, facets and pagination."""
    return SearchService(db).search(params, principal)


@search.get("/suggest", response_model=SuggestResponse)
def suggest(db: DbSession, q: Annotated[str, Query(min_length=1, max_length=100)]) -> SuggestResponse:
    return SearchService(db).suggest(q)


# ------------------------------------------------------------------ products
@products.get("", response_model=SearchResponse)
def list_products(db: DbSession, principal: OptionalPrincipal, params: Annotated[SearchQuery, Query()]) -> SearchResponse:
    """Browse the catalog (same filters/sorting as /search; `q` optional)."""
    if not params.q and params.sort == "relevance":
        params.sort = "popularity"
    return SearchService(db).search(params, principal, record=False)


@products.get("/{id_or_slug}", response_model=ProductDetail)
def get_product(id_or_slug: str, db: DbSession, principal: OptionalPrincipal) -> ProductDetail:
    p = ProductService(db).get_visible(id_or_slug, principal)
    return product_detail(db, p, PricingEngine(db))


@products.post("", response_model=ProductDetail, status_code=status.HTTP_201_CREATED)
def create_product(body: ProductCreate, principal: CurrentPrincipal, db: DbSession) -> ProductDetail:
    p = ProductService(db).create(body, principal)
    return product_detail(db, p, PricingEngine(db))


@products.patch("/{product_id}", response_model=ProductDetail)
def update_product(product_id: uuid.UUID, body: ProductUpdate, principal: CurrentPrincipal, db: DbSession) -> ProductDetail:
    p = ProductService(db).update(product_id, body, principal)
    return product_detail(db, p, PricingEngine(db))


@products.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> Response:
    ProductService(db).delete(product_id, principal)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@products.get("/{product_id}/offers", response_model=list[ProductOfferOut])
def product_offers(product_id: uuid.UUID, db: DbSession, principal: OptionalPrincipal) -> list[ProductOfferOut]:
    p = ProductService(db).get_visible(str(product_id), principal)
    return PromotionService(db).offers_for_product(p)


@products.get("/{product_id}/bundles", response_model=list[BundleOut])
def product_bundles(product_id: uuid.UUID, db: DbSession) -> list[BundleOut]:
    return PromotionService(db).list_bundles(product_id=product_id)


@products.get("/{product_id}/reviews", response_model=Page[ReviewOut])
def product_reviews(
    product_id: uuid.UUID, db: DbSession, principal: OptionalPrincipal,
    sort: Literal["newest", "oldest", "highest", "lowest", "helpful"] = "newest",
    rating: Annotated[int | None, Query(ge=1, le=5)] = None,
    page: Annotated[int, Query(ge=1)] = 1, page_size: Annotated[int, Query(ge=1, le=50)] = 10,
) -> Page[ReviewOut]:
    items, total = ReviewService(db).list_for_product(product_id, sort=sort, rating=rating,
                                                      offset=(page - 1) * page_size, limit=page_size, principal=principal)
    return Page(items=items, total=total, page=page, page_size=page_size)


@products.get("/{product_id}/reviews/summary", response_model=ReviewSummaryOut)
def product_review_summary(product_id: uuid.UUID, db: DbSession) -> ReviewSummaryOut:
    return ReviewService(db).summary(product_id)


@products.get("/{product_id}/reviews/eligibility", response_model=ReviewEligibility)
def review_eligibility(product_id: uuid.UUID, principal: CurrentPrincipal, db: DbSession) -> ReviewEligibility:
    return ReviewService(db).eligibility(product_id, principal)


@products.post("/{product_id}/reviews", response_model=ReviewOut, status_code=status.HTTP_201_CREATED)
def create_review(product_id: uuid.UUID, body: ReviewIn, principal: CurrentPrincipal, db: DbSession) -> ReviewOut:
    return ReviewService(db).create(product_id, body, principal)


@products.post("/{product_id}/negotiations", response_model=NegotiationOut, status_code=status.HTTP_201_CREATED)
def propose_price(product_id: uuid.UUID, body: NegotiationRequest, principal: CurrentPrincipal, db: DbSession
                  ) -> NegotiationOut:
    return NegotiationService(db).propose(product_id, body.offered_price, principal, body.message)


@products.get("/{product_id}/similar", response_model=list[ProductCard])
def similar_products(product_id: uuid.UUID, db: DbSession, limit: Annotated[int, Query(ge=1, le=20)] = 8
                     ) -> list[ProductCard]:
    from app.services.recommendation_service import RecommendationService

    return RecommendationService(db).similar(product_id, limit).items
