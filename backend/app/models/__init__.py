"""Import every model so SQLAlchemy metadata (and Alembic autogenerate) sees all tables."""

from app.models.agents import AgentSession, AgentToolCall, AgentWorkflow, Conversation, Message
from app.models.analytics import AnalyticsEvent, ForecastResult, Recommendation, SearchHistory
from app.models.catalog import (
    Category,
    Inventory,
    Negotiation,
    NegotiationRule,
    Product,
    ProductImage,
    ProductVariant,
)
from app.models.commerce import (
    Cart,
    CartItem,
    Discount,
    Order,
    OrderItem,
    OrderStatusEvent,
    Payment,
    Wishlist,
    WishlistItem,
)
from app.models.identity import (
    Address,
    AuditLog,
    AuthToken,
    BuyerProfile,
    EmailOutbox,
    Notification,
    Permission,
    RefreshToken,
    Role,
    SellerProfile,
    SystemSetting,
    User,
    UserRole,
    role_permissions,
)
from app.models.promotions import Bundle, BundleItem, Coupon, Offer
from app.models.reviews import Rating, Review

__all__ = [
    "Address", "AgentSession", "AgentToolCall", "AgentWorkflow", "AnalyticsEvent", "AuditLog", "AuthToken",
    "Bundle", "BundleItem", "BuyerProfile", "Cart", "CartItem", "Category", "Conversation", "Coupon",
    "Discount", "EmailOutbox", "ForecastResult", "Inventory", "Message", "Negotiation", "NegotiationRule",
    "Notification", "Offer", "Order", "OrderItem", "OrderStatusEvent", "Payment", "Permission", "Product",
    "ProductImage", "ProductVariant", "Rating", "Recommendation", "RefreshToken", "Review", "Role",
    "SearchHistory", "SellerProfile", "SystemSetting", "User", "UserRole", "Wishlist", "WishlistItem",
    "role_permissions",
]
