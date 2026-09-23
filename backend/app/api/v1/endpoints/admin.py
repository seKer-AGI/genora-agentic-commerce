"""/api/v1/admin — marketplace operations. Every route requires a specific admin permission."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from app.api.deps import DbSession, require_permission
from app.core.errors import ConflictError, NotFoundError, ValidationFailed
from app.core.principal import Principal
from app.core.rbac import P
from app.models.agents import AgentToolCall, AgentWorkflow
from app.models.enums import OrderStatus, ProductStatus, ReviewStatus, RoleName, SellerStatus
from app.models.identity import AuditLog, Permission, Role, SellerProfile, SystemSetting, User, UserRole
from app.schemas.catalog import ProductCard
from app.schemas.commerce import OrderOut
from app.schemas.common import Page
from app.schemas.reviews import ReviewModeration, ReviewOut
from app.services.ai_runtime import describe_ai_runtime
from app.services.audit import audit
from app.services.auth_service import AuthService
from app.services.catalog_service import ProductService, product_card
from app.services.order_service import OrderService
from app.services.pricing import PricingEngine
from app.services.review_service import ReviewService

router = APIRouter(prefix="/admin", tags=["admin"])


def perm(code: str) -> Any:
    return Annotated[Principal, Depends(require_permission(code))]


# ================================================================== users
class AdminUserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    roles: list[str]
    is_active: bool
    is_email_verified: bool
    created_at: datetime
    last_login_at: datetime | None
    store_name: str | None = None


class AdminUserUpdate(BaseModel):
    is_active: bool | None = None
    roles: list[Literal["BUYER", "SELLER", "ADMIN"]] | None = Field(default=None, min_length=1)
    full_name: str | None = Field(default=None, min_length=2, max_length=120)


def _user_out(db: DbSession, u: User) -> AdminUserOut:
    store = db.scalar(select(SellerProfile.store_name).where(SellerProfile.user_id == u.id))
    return AdminUserOut(id=u.id, email=u.email, full_name=u.full_name, roles=u.role_names, is_active=u.is_active,
                        is_email_verified=u.is_email_verified, created_at=u.created_at, last_login_at=u.last_login_at,
                        store_name=store)


@router.get("/users", response_model=Page[AdminUserOut])
def list_users(
    db: DbSession, _: perm(P.USERS_MANAGE), q: str | None = None, role: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1, page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[AdminUserOut]:
    stmt = select(User).where(User.deleted_at.is_(None))
    if q:
        stmt = stmt.where(or_(User.email.ilike(f"%{q}%"), User.full_name.ilike(f"%{q}%")))
    if role:
        stmt = stmt.where(User.id.in_(select(UserRole.user_id).join(Role).where(Role.name == role)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
    return Page(items=[_user_out(db, u) for u in rows], total=total, page=page, page_size=page_size)


@router.patch("/users/{user_id}", response_model=AdminUserOut)
def update_user(user_id: uuid.UUID, body: AdminUserUpdate, principal: perm(P.USERS_MANAGE), db: DbSession) -> AdminUserOut:
    u = db.get(User, user_id)
    if u is None or u.deleted_at is not None:
        raise NotFoundError("User was not found", code="USER_NOT_FOUND")
    if u.id == principal.user_id and (body.is_active is False or (body.roles and RoleName.ADMIN not in body.roles)):
        raise ValidationFailed("You cannot deactivate yourself or remove your own admin role", code="SELF_LOCKOUT")
    if body.roles is not None:
        if RoleName.ADMIN in body.roles and not principal.has(P.PERMISSIONS_MANAGE):
            raise ValidationFailed("Granting ADMIN requires permissions:manage", code="ROLE_ESCALATION")
        roles = {r.name: r for r in db.scalars(select(Role))}
        u.user_roles = [UserRole(role_id=roles[r].id) for r in sorted(set(body.roles))]
    if body.is_active is not None:
        u.is_active = body.is_active
        if not body.is_active:
            AuthService(db).revoke_all_sessions(u.id)
    if body.full_name:
        u.full_name = body.full_name
    audit(db, principal.user_id, "admin.user.update", "user", u.id, body.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(u)
    return _user_out(db, u)


# ================================================================== sellers
class AdminSellerOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    store_name: str
    slug: str
    status: str
    rating_avg: float
    owner_email: str
    product_count: int
    created_at: datetime


@router.get("/sellers", response_model=list[AdminSellerOut])
def list_sellers(db: DbSession, _: perm(P.SELLERS_MANAGE), status: str | None = None) -> list[AdminSellerOut]:
    from app.models.catalog import Product

    stmt = select(SellerProfile).where(SellerProfile.deleted_at.is_(None)).order_by(SellerProfile.created_at.desc())
    if status:
        stmt = stmt.where(SellerProfile.status == SellerStatus(status))
    out = []
    for s in db.scalars(stmt):
        count = db.scalar(select(func.count()).select_from(Product).where(Product.seller_id == s.id,
                                                                           Product.deleted_at.is_(None))) or 0
        out.append(AdminSellerOut(id=s.id, user_id=s.user_id, store_name=s.store_name, slug=s.slug, status=s.status.value,
                                  rating_avg=float(s.rating_avg), owner_email=s.user.email, product_count=count,
                                  created_at=s.created_at))
    return out


class SellerStatusIn(BaseModel):
    status: Literal["active", "suspended", "pending"]
    reason: str | None = Field(default=None, max_length=255)


@router.post("/sellers/{seller_id}/status", response_model=AdminSellerOut)
def set_seller_status(seller_id: uuid.UUID, body: SellerStatusIn, principal: perm(P.SELLERS_MANAGE), db: DbSession
                      ) -> AdminSellerOut:
    s = db.get(SellerProfile, seller_id)
    if s is None:
        raise NotFoundError("Seller was not found", code="SELLER_NOT_FOUND")
    s.status = SellerStatus(body.status)
    audit(db, principal.user_id, "admin.seller.status", "seller", s.id, body.model_dump())
    db.commit()
    return next(x for x in list_sellers(db, principal) if x.id == s.id)


# ================================================================== products
@router.get("/products", response_model=Page[ProductCard])
def list_products(
    db: DbSession, _: perm(P.PRODUCTS_MANAGE_ALL), status: str | None = None, q: str | None = None,
    seller_id: uuid.UUID | None = None,
    page: Annotated[int, Query(ge=1)] = 1, page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[ProductCard]:
    items, total = ProductService(db).list_all(status, q, seller_id, (page - 1) * page_size, page_size)
    engine = PricingEngine(db)
    return Page(items=[product_card(p, engine) for p in items], total=total, page=page, page_size=page_size)


class ProductModeration(BaseModel):
    status: Literal["active", "blocked", "archived", "draft"]
    reason: str | None = Field(default=None, max_length=255)


@router.post("/products/{product_id}/moderate", response_model=ProductCard)
def moderate_product(product_id: uuid.UUID, body: ProductModeration, principal: perm(P.PRODUCTS_MANAGE_ALL),
                     db: DbSession) -> ProductCard:
    p = ProductService(db).moderate(product_id, ProductStatus(body.status), principal, body.reason)
    return product_card(p, PricingEngine(db))


# ================================================================== orders
@router.get("/orders", response_model=Page[OrderOut])
def list_orders(
    db: DbSession, principal: perm(P.ORDERS_MANAGE_ALL), status: str | None = None, q: str | None = None,
    seller_id: uuid.UUID | None = None,
    page: Annotated[int, Query(ge=1)] = 1, page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[OrderOut]:
    if status:
        OrderStatus(status)
    items, total = OrderService(db).list(seller_id=seller_id, status=status, q=q, offset=(page - 1) * page_size,
                                         limit=page_size, principal=principal)
    return Page(items=items, total=total, page=page, page_size=page_size)


# ================================================================== reviews
@router.get("/reviews", response_model=Page[ReviewOut])
def review_queue(
    db: DbSession, _: perm(P.REVIEWS_MODERATE), status: Literal["pending", "approved", "rejected"] | None = "pending",
    page: Annotated[int, Query(ge=1)] = 1, page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[ReviewOut]:
    items, total = ReviewService(db).moderation_queue(status, (page - 1) * page_size, page_size)
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.post("/reviews/{review_id}/moderate", response_model=ReviewOut)
def moderate_review(review_id: uuid.UUID, body: ReviewModeration, principal: perm(P.REVIEWS_MODERATE), db: DbSession
                    ) -> ReviewOut:
    return ReviewService(db).moderate(review_id, ReviewStatus(body.status), body.reason, principal)


# ================================================================== settings / AI configuration
class SettingOut(BaseModel):
    key: str
    value: Any
    description: str | None
    updated_at: datetime


class SettingUpdate(BaseModel):
    value: Any


@router.get("/settings", response_model=list[SettingOut])
def list_settings(db: DbSession, _: perm(P.AI_CONFIGURE)) -> list[SettingOut]:
    return [SettingOut(key=s.key, value=s.value, description=s.description, updated_at=s.updated_at)
            for s in db.scalars(select(SystemSetting).order_by(SystemSetting.key))]


@router.put("/settings/{key}", response_model=SettingOut)
def update_setting(key: str, body: SettingUpdate, principal: perm(P.AI_CONFIGURE), db: DbSession) -> SettingOut:
    s = db.get(SystemSetting, key)
    if s is None:
        raise NotFoundError("Setting was not found", code="SETTING_NOT_FOUND")
    if type(body.value) is not type(s.value) and not (isinstance(s.value, int | float) and isinstance(body.value, int | float)):
        raise ValidationFailed(f"Setting '{key}' expects a {type(s.value).__name__}", code="INVALID_SETTING_TYPE")
    if key == "agents.apex.enabled" and body.value:
        raise ConflictError("GenOra Apex is planned and not implemented; it cannot be enabled", code="APEX_NOT_IMPLEMENTED")
    if key == "search.semantic_weight" and not 0 <= float(body.value) <= 1:
        raise ValidationFailed("semantic_weight must be between 0 and 1", code="INVALID_SETTING_VALUE")
    if key == "agents.max_tool_calls_per_turn" and not 1 <= int(body.value) <= 20:
        raise ValidationFailed("max_tool_calls_per_turn must be between 1 and 20", code="INVALID_SETTING_VALUE")
    old = s.value
    s.value, s.updated_by = body.value, principal.user_id
    audit(db, principal.user_id, "admin.setting.update", "setting", key, {"old": old, "new": body.value})
    db.commit()
    return SettingOut(key=s.key, value=s.value, description=s.description, updated_at=s.updated_at)


@router.get("/ai/runtime")
def ai_runtime(_: perm(P.AI_CONFIGURE)) -> dict[str, Any]:
    """Active (non-secret) AI provider configuration. Providers are configured via environment variables."""
    return describe_ai_runtime()


# ================================================================== roles & permissions
class RoleOut(BaseModel):
    id: int
    name: str
    description: str | None
    permissions: list[str]


class RolePermissionsUpdate(BaseModel):
    permissions: list[str] = Field(max_length=100)


@router.get("/roles", response_model=list[RoleOut])
def list_roles(db: DbSession, _: perm(P.PERMISSIONS_MANAGE)) -> list[RoleOut]:
    return [RoleOut(id=r.id, name=r.name, description=r.description, permissions=sorted(p.code for p in r.permissions))
            for r in db.scalars(select(Role).order_by(Role.id))]


@router.get("/permissions", response_model=list[dict[str, str | None]])
def list_permissions(db: DbSession, _: perm(P.PERMISSIONS_MANAGE)) -> list[dict[str, str | None]]:
    return [{"code": p.code, "description": p.description} for p in db.scalars(select(Permission).order_by(Permission.code))]


@router.put("/roles/{role_id}/permissions", response_model=RoleOut)
def set_role_permissions(role_id: int, body: RolePermissionsUpdate, principal: perm(P.PERMISSIONS_MANAGE),
                         db: DbSession) -> RoleOut:
    role = db.get(Role, role_id)
    if role is None:
        raise NotFoundError("Role was not found", code="ROLE_NOT_FOUND")
    perms = list(db.scalars(select(Permission).where(Permission.code.in_(body.permissions))))
    unknown = set(body.permissions) - {p.code for p in perms}
    if unknown:
        raise ValidationFailed("Unknown permissions", code="UNKNOWN_PERMISSION", details=sorted(unknown))
    if role.name == RoleName.ADMIN and P.PERMISSIONS_MANAGE not in body.permissions:
        raise ValidationFailed("ADMIN must keep permissions:manage", code="SELF_LOCKOUT")
    before = sorted(p.code for p in role.permissions)
    role.permissions = perms
    audit(db, principal.user_id, "admin.role.permissions", "role", role.id, {"before": before, "after": sorted(body.permissions)})
    db.commit()
    return RoleOut(id=role.id, name=role.name, description=role.description, permissions=sorted(p.code for p in role.permissions))


# ================================================================== audit logs
class AuditOut(BaseModel):
    id: uuid.UUID
    actor_email: str | None
    action: str
    entity_type: str
    entity_id: str | None
    data: dict[str, Any]
    ip_address: str | None
    created_at: datetime


@router.get("/audit-logs", response_model=Page[AuditOut])
def audit_logs(
    db: DbSession, _: perm(P.LOGS_READ), action: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1, page_size: Annotated[int, Query(ge=1, le=100)] = 30,
) -> Page[AuditOut]:
    stmt = select(AuditLog, User.email).outerjoin(User, User.id == AuditLog.actor_user_id)
    if action:
        stmt = stmt.where(AuditLog.action.ilike(f"{action}%"))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return Page(items=[AuditOut(id=a.id, actor_email=email, action=a.action, entity_type=a.entity_type,
                                entity_id=a.entity_id, data=a.data, ip_address=a.ip_address, created_at=a.created_at)
                       for a, email in rows], total=total, page=page, page_size=page_size)


# ================================================================== agent monitoring
class WorkflowOut(BaseModel):
    id: uuid.UUID
    agent: str
    intent: str
    workflow_name: str
    status: str
    nlu_mode: str
    confidence: float | None
    latency_ms: int | None
    error_code: str | None
    safety_flags: list[Any]
    steps: list[Any]
    user_email: str | None
    started_at: datetime
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)


@router.get("/agents/workflows", response_model=Page[WorkflowOut])
def agent_workflows(
    db: DbSession, _: perm(P.AGENTS_MONITOR), agent: str | None = None, status: str | None = None,
    intent: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1, page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page[WorkflowOut]:
    stmt = select(AgentWorkflow, User.email).outerjoin(User, User.id == AgentWorkflow.user_id)
    if agent:
        stmt = stmt.where(AgentWorkflow.agent == agent)
    if status:
        stmt = stmt.where(AgentWorkflow.status == status)
    if intent:
        stmt = stmt.where(AgentWorkflow.intent == intent)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(AgentWorkflow.started_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    items = []
    for w, email in rows:
        calls = db.scalars(select(AgentToolCall).where(AgentToolCall.workflow_id == w.id).order_by(AgentToolCall.created_at))
        items.append(WorkflowOut(
            id=w.id, agent=w.agent.value, intent=w.intent, workflow_name=w.workflow_name, status=w.status.value,
            nlu_mode=w.nlu_mode, confidence=w.confidence, latency_ms=w.latency_ms, error_code=w.error_code,
            safety_flags=w.safety_flags, steps=w.steps, user_email=email, started_at=w.started_at,
            tool_calls=[{"tool": c.tool_name, "status": c.status.value, "latency_ms": c.latency_ms,
                         "error_code": c.error_code, "input": c.input, "output": c.output_summary} for c in calls],
        ))
    return Page(items=items, total=total, page=page, page_size=page_size)
