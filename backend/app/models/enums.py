"""Domain enumerations shared by models, schemas and services."""

from __future__ import annotations

import enum


class RoleName(enum.StrEnum):
    BUYER = "BUYER"
    SELLER = "SELLER"
    ADMIN = "ADMIN"


class AuthTokenPurpose(enum.StrEnum):
    PASSWORD_RESET = "password_reset"
    EMAIL_VERIFICATION = "email_verification"


class SellerStatus(enum.StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"


class ProductStatus(enum.StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"
    BLOCKED = "blocked"


class OrderStatus(enum.StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class PaymentStatus(enum.StrEnum):
    PENDING = "pending"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    FAILED = "failed"
    REFUNDED = "refunded"


class DiscountType(enum.StrEnum):
    PERCENTAGE = "percentage"
    FIXED = "fixed"


class DiscountSource(enum.StrEnum):
    OFFER = "offer"
    BUNDLE = "bundle"
    COUPON = "coupon"
    NEGOTIATION = "negotiation"


class ReviewStatus(enum.StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class NegotiationStatus(enum.StrEnum):
    ACCEPTED = "accepted"
    COUNTERED = "countered"
    REJECTED = "rejected"
    EXPIRED = "expired"
    USED = "used"


class AgentName(enum.StrEnum):
    NOVA = "nova"
    ASTRA = "astra"
    APEX = "apex"


class MessageRole(enum.StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class WorkflowStatus(enum.StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_CLARIFICATION = "needs_clarification"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    BLOCKED = "blocked"


class ToolCallStatus(enum.StrEnum):
    SUCCESS = "success"
    ERROR = "error"
    DENIED = "denied"


class ForecastStatus(enum.StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
