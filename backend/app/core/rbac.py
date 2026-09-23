"""Permission catalogue and default role → permission grants.

Roles are coarse (BUYER/SELLER/ADMIN); permissions are fine-grained and editable by admins at runtime
(`role_permissions` table). Endpoints depend on permissions, not on role names, wherever practical.
"""

from __future__ import annotations

from app.models.enums import RoleName


class P:
    # Buyer capabilities
    CART_MANAGE = "cart:manage"
    ORDERS_PLACE = "orders:place"
    ORDERS_READ_OWN = "orders:read_own"
    REVIEWS_WRITE = "reviews:write"
    WISHLIST_MANAGE = "wishlist:manage"
    NOVA_USE = "agents:nova"
    NEGOTIATE = "negotiations:create"
    # Seller capabilities
    PRODUCTS_MANAGE_OWN = "products:manage_own"
    INVENTORY_MANAGE_OWN = "inventory:manage_own"
    ORDERS_MANAGE_OWN = "orders:manage_own"
    OFFERS_MANAGE_OWN = "offers:manage_own"
    ANALYTICS_READ_OWN = "analytics:read_own"
    ASTRA_USE = "agents:astra"
    FORECAST_RUN_OWN = "forecasting:run_own"
    # Admin capabilities
    USERS_MANAGE = "users:manage"
    SELLERS_MANAGE = "sellers:manage"
    PRODUCTS_MANAGE_ALL = "products:manage_all"
    CATEGORIES_MANAGE = "categories:manage"
    ORDERS_MANAGE_ALL = "orders:manage_all"
    REVIEWS_MODERATE = "reviews:moderate"
    OFFERS_MANAGE_ALL = "offers:manage_all"
    ANALYTICS_READ_ALL = "analytics:read_all"
    AI_CONFIGURE = "ai:configure"
    AGENTS_MONITOR = "agents:monitor"
    LOGS_READ = "logs:read"
    PERMISSIONS_MANAGE = "permissions:manage"
    FORECAST_RUN_ALL = "forecasting:run_all"


PERMISSION_DESCRIPTIONS: dict[str, str] = {
    v: k.replace("_", " ").capitalize() for k, v in vars(P).items() if not k.startswith("_") and isinstance(v, str)
}

_BUYER = {P.CART_MANAGE, P.ORDERS_PLACE, P.ORDERS_READ_OWN, P.REVIEWS_WRITE, P.WISHLIST_MANAGE, P.NOVA_USE, P.NEGOTIATE}
_SELLER = {
    P.PRODUCTS_MANAGE_OWN, P.INVENTORY_MANAGE_OWN, P.ORDERS_MANAGE_OWN, P.OFFERS_MANAGE_OWN,
    P.ANALYTICS_READ_OWN, P.ASTRA_USE, P.FORECAST_RUN_OWN,
}
_ADMIN = set(PERMISSION_DESCRIPTIONS)

DEFAULT_ROLE_PERMISSIONS: dict[str, set[str]] = {
    RoleName.BUYER: _BUYER,
    RoleName.SELLER: _SELLER,
    RoleName.ADMIN: _ADMIN,
}

ROLE_DESCRIPTIONS = {
    RoleName.BUYER: "Shops on the marketplace",
    RoleName.SELLER: "Sells products on the marketplace",
    RoleName.ADMIN: "Operates the marketplace",
}
