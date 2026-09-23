"""Aggregates all v1 routers."""

from fastapi import APIRouter

from app.api.v1.endpoints import admin, analytics, auth, catalog, commerce, media, promotions, recommendations, sellers

api_router = APIRouter()
for r in (
    auth.router,
    catalog.categories,
    catalog.products,
    catalog.search,
    commerce.cart,
    commerce.wishlist,
    commerce.addresses,
    commerce.orders,
    commerce.negotiations,
    promotions.offers,
    promotions.bundles,
    promotions.reviews,
    sellers.router,
    admin.router,
    analytics.router,
    recommendations.router,
    media.router,
):
    api_router.include_router(r)


@api_router.get("/health", tags=["health"])
def api_health() -> dict[str, str]:
    return {"status": "ok"}
