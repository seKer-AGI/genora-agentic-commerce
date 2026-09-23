"""Reviews: verified-purchase creation, automated moderation filter, admin moderation, rating aggregates."""

from __future__ import annotations

import re
import uuid
from decimal import Decimal

from genora.analysis.reviews import ReviewInput, analyze_reviews
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, PermissionDenied
from app.core.principal import Principal
from app.core.rbac import P
from app.core.security import utcnow
from app.models.catalog import Product
from app.models.commerce import Order, OrderItem
from app.models.enums import OrderStatus, ProductStatus, ReviewStatus
from app.models.identity import SellerProfile, SystemSetting
from app.models.reviews import Rating, Review
from app.schemas.reviews import (
    RatingSummary,
    ReviewEligibility,
    ReviewIn,
    ReviewOut,
    ReviewSummaryOut,
    ReviewUpdate,
)
from app.services.audit import audit

_LINK = re.compile(r"(https?://|www\.)", re.IGNORECASE)
_BLOCKLIST = re.compile(r"\b(idiot|stupid|scam artist|f\*+k|shit)\b", re.IGNORECASE)
REVIEW_SORTS = {
    "newest": (Review.created_at.desc(),),
    "oldest": (Review.created_at.asc(),),
    "highest": (Review.rating.desc(), Review.created_at.desc()),
    "lowest": (Review.rating.asc(), Review.created_at.desc()),
    "helpful": (Review.helpful_count.desc(), Review.created_at.desc()),
}
REVIEWABLE_STATUSES = (OrderStatus.DELIVERED,)


def automated_moderation(body: str, title: str | None) -> str | None:
    """Returns a reason if the review needs human moderation."""
    text = f"{title or ''} {body}"
    if _LINK.search(text):
        return "Contains a link"
    if _BLOCKLIST.search(text):
        return "Possible abusive language"
    letters = [c for c in text if c.isalpha()]
    if len(letters) > 20 and sum(c.isupper() for c in letters) / len(letters) > 0.7:
        return "Excessive capitalisation"
    return None


class ReviewService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _to_out(self, r: Review, principal: Principal | None = None, include_product: bool = False) -> ReviewOut:
        name = r.author.full_name if r.author else "Customer"
        parts = name.split()
        display = f"{parts[0]} {parts[-1][0]}." if len(parts) > 1 else parts[0]
        product_name = self.db.scalar(select(Product.name).where(Product.id == r.product_id)) if include_product else None
        return ReviewOut(
            id=r.id, product_id=r.product_id, product_name=product_name, author_name=display, rating=r.rating,
            title=r.title, body=r.body, status=r.status.value, is_verified_purchase=r.is_verified_purchase,
            helpful_count=r.helpful_count, moderation_reason=r.moderation_reason if include_product else None,
            created_at=r.created_at, is_mine=bool(principal and principal.user_id == r.user_id),
        )

    def _product(self, product_id: uuid.UUID) -> Product:
        p = self.db.scalar(select(Product).where(Product.id == product_id, Product.deleted_at.is_(None)))
        if p is None or p.status != ProductStatus.ACTIVE:
            raise NotFoundError("Product was not found", code="PRODUCT_NOT_FOUND")
        return p

    def list_for_product(self, product_id: uuid.UUID, *, sort: str, rating: int | None, offset: int, limit: int,
                         principal: Principal | None = None) -> tuple[list[ReviewOut], int]:
        stmt = select(Review).where(Review.product_id == product_id, Review.status == ReviewStatus.APPROVED,
                                    Review.deleted_at.is_(None))
        if rating:
            stmt = stmt.where(Review.rating == rating)
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = self.db.scalars(stmt.order_by(*REVIEW_SORTS.get(sort, REVIEW_SORTS["newest"])).offset(offset).limit(limit))
        return [self._to_out(r, principal) for r in rows], total

    def eligibility(self, product_id: uuid.UUID, principal: Principal) -> ReviewEligibility:
        existing = self.db.scalar(select(Review).where(Review.product_id == product_id, Review.user_id == principal.user_id,
                                                       Review.deleted_at.is_(None)))
        if existing:
            return ReviewEligibility(can_review=False, reason="You have already reviewed this product",
                                     existing_review_id=existing.id)
        if not principal.has(P.REVIEWS_WRITE):
            return ReviewEligibility(can_review=False, reason="Your account cannot write reviews")
        if self._delivered_order(product_id, principal.user_id) is None:
            return ReviewEligibility(can_review=False, reason="Only customers who received this product can review it")
        return ReviewEligibility(can_review=True, reason=None)

    def _delivered_order(self, product_id: uuid.UUID, user_id: uuid.UUID) -> Order | None:
        return self.db.scalar(
            select(Order).join(OrderItem, OrderItem.order_id == Order.id)
            .where(Order.buyer_id == user_id, OrderItem.product_id == product_id, Order.status.in_(REVIEWABLE_STATUSES))
            .order_by(Order.placed_at.desc()).limit(1)
        )

    def create(self, product_id: uuid.UUID, data: ReviewIn, principal: Principal) -> ReviewOut:
        principal.require(P.REVIEWS_WRITE)
        product = self._product(product_id)
        if principal.seller_id and principal.seller_id == product.seller_id:
            raise PermissionDenied("Sellers cannot review their own products", code="OWN_PRODUCT_REVIEW")
        if self.db.scalar(select(Review.id).where(Review.product_id == product_id, Review.user_id == principal.user_id)):
            raise ConflictError("You have already reviewed this product", code="REVIEW_EXISTS")
        order = self._delivered_order(product_id, principal.user_id)
        if order is None:
            raise PermissionDenied("Only customers who received this product can review it", code="PURCHASE_REQUIRED")
        reason = automated_moderation(data.body, data.title)
        auto = self.db.get(SystemSetting, "reviews.auto_approve")
        status = ReviewStatus.APPROVED if reason is None and (auto is None or auto.value) else ReviewStatus.PENDING
        review = Review(product_id=product_id, user_id=principal.user_id, order_id=order.id, rating=data.rating,
                        title=data.title, body=data.body, status=status, is_verified_purchase=True,
                        moderation_reason=reason)
        self.db.add(review)
        self.db.flush()
        if status == ReviewStatus.APPROVED:
            self.recompute(product_id)
        self.db.commit()
        self.db.refresh(review)
        return self._to_out(review, principal)

    def _own(self, review_id: uuid.UUID, principal: Principal) -> Review:
        r = self.db.get(Review, review_id)
        if r is None or r.deleted_at is not None or r.user_id != principal.user_id:
            raise NotFoundError("Review was not found", code="REVIEW_NOT_FOUND")
        return r

    def update(self, review_id: uuid.UUID, data: ReviewUpdate, principal: Principal) -> ReviewOut:
        r = self._own(review_id, principal)
        for k, v in data.model_dump(exclude_unset=True).items():
            setattr(r, k, v)
        reason = automated_moderation(r.body, r.title)
        r.status = ReviewStatus.PENDING if reason else ReviewStatus.APPROVED
        r.moderation_reason = reason
        self.db.flush()
        self.recompute(r.product_id)
        self.db.commit()
        return self._to_out(r, principal)

    def delete(self, review_id: uuid.UUID, principal: Principal) -> None:
        r = self.db.get(Review, review_id)
        if r is None or r.deleted_at is not None:
            raise NotFoundError("Review was not found", code="REVIEW_NOT_FOUND")
        if r.user_id != principal.user_id and not principal.has(P.REVIEWS_MODERATE):
            raise NotFoundError("Review was not found", code="REVIEW_NOT_FOUND")
        r.deleted_at = utcnow()
        self.db.flush()
        self.recompute(r.product_id)
        audit(self.db, principal.user_id, "review.delete", "review", r.id)
        self.db.commit()

    def mark_helpful(self, review_id: uuid.UUID) -> ReviewOut:
        r = self.db.get(Review, review_id)
        if r is None or r.status != ReviewStatus.APPROVED or r.deleted_at is not None:
            raise NotFoundError("Review was not found", code="REVIEW_NOT_FOUND")
        r.helpful_count += 1
        self.db.commit()
        return self._to_out(r)

    # ------------------------------------------------------------ moderation
    def moderation_queue(self, status: str | None, offset: int, limit: int) -> tuple[list[ReviewOut], int]:
        stmt = select(Review).where(Review.deleted_at.is_(None))
        if status:
            stmt = stmt.where(Review.status == ReviewStatus(status))
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = self.db.scalars(stmt.order_by(Review.created_at.desc()).offset(offset).limit(limit))
        return [self._to_out(r, include_product=True) for r in rows], total

    def moderate(self, review_id: uuid.UUID, status: ReviewStatus, reason: str | None, principal: Principal) -> ReviewOut:
        principal.require(P.REVIEWS_MODERATE)
        r = self.db.get(Review, review_id)
        if r is None or r.deleted_at is not None:
            raise NotFoundError("Review was not found", code="REVIEW_NOT_FOUND")
        r.status, r.moderation_reason = status, reason
        r.moderated_by, r.moderated_at = principal.user_id, utcnow()
        self.db.flush()
        self.recompute(r.product_id)
        audit(self.db, principal.user_id, "review.moderate", "review", r.id, {"status": status.value, "reason": reason})
        self.db.commit()
        return self._to_out(r, include_product=True)

    def recompute(self, product_id: uuid.UUID) -> None:
        rows = self.db.execute(
            select(Review.rating, func.count()).where(
                Review.product_id == product_id, Review.status == ReviewStatus.APPROVED, Review.deleted_at.is_(None)
            ).group_by(Review.rating)
        ).all()
        dist = {str(i): 0 for i in range(1, 6)}
        for rating, n in rows:
            dist[str(rating)] = n
        count = sum(dist.values())
        avg = (Decimal(sum(int(k) * v for k, v in dist.items())) / count).quantize(Decimal("0.01")) if count else Decimal(0)
        agg = self.db.get(Rating, product_id) or Rating(product_id=product_id)
        agg.average, agg.count, agg.distribution = avg, count, dist
        self.db.add(agg)
        product = self.db.get(Product, product_id)
        if product:
            product.rating_avg, product.rating_count = avg, count
            seller = self.db.get(SellerProfile, product.seller_id)
            if seller:
                sa, sc = self.db.execute(
                    select(func.sum(Product.rating_avg * Product.rating_count), func.sum(Product.rating_count))
                    .where(Product.seller_id == seller.id, Product.rating_count > 0)
                ).one()
                seller.rating_avg = (Decimal(sa) / Decimal(sc)).quantize(Decimal("0.01")) if sc else Decimal(0)

    # ------------------------------------------------------------ insights
    def summary(self, product_id: uuid.UUID, limit: int = 300) -> ReviewSummaryOut:
        self._product(product_id)
        reviews = self.db.scalars(
            select(Review).where(Review.product_id == product_id, Review.status == ReviewStatus.APPROVED,
                                 Review.deleted_at.is_(None)).order_by(Review.created_at.desc()).limit(limit)
        ).all()
        insights = analyze_reviews([ReviewInput(r.rating, r.title, r.body, r.is_verified_purchase) for r in reviews])
        agg = self.db.get(Rating, product_id)
        return ReviewSummaryOut(
            product_id=product_id,
            rating=RatingSummary(average=float(agg.average) if agg else 0.0, count=agg.count if agg else 0,
                                 distribution=agg.distribution if agg else {}),
            insights=insights.as_dict(),
        )
