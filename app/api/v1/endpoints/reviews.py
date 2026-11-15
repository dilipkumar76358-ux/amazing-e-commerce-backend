import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.database import get_db
from app.core.security import get_current_user
from app.schemas.reviews import (
    ReviewCreateRequest,
    ReviewResponse,
    ProductReviewsSummaryResponse,
)
from app.api.v1.endpoints.catalog import _MEMORY_PRODUCTS
from app.api.v1.endpoints.checkout import _MEMORY_ORDERS

router = APIRouter(tags=["Verified Customer Reviews"])

_MEMORY_REVIEWS: Dict[str, Dict[str, Any]] = {
    "rev-hp-01": {
        "id": "rev-hp-01",
        "product_id": "prod-headphones-01",
        "customer_user_id": "cust-seed-01",
        "customer_name": "Arjun Sharma",
        "order_id": "ord-seed-01",
        "rating": 5,
        "title": "Exceptional Sound & Top-notch ANC",
        "comment": "The active noise cancellation blocks out 95% of background chatter. Battery life easily exceeded 45 hours on single charge.",
        "images": ["https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=500&q=80"],
        "is_verified_purchase": True,
        "helpful_votes": 34,
        "review_status": "approved",
        "created_at": "2026-10-20T10:00:00Z"
    },
    "rev-hp-02": {
        "id": "rev-hp-02",
        "product_id": "prod-headphones-01",
        "customer_user_id": "cust-seed-02",
        "customer_name": "Priya Nair",
        "order_id": "ord-seed-02",
        "rating": 4,
        "title": "Super comfortable for long Zoom meetings",
        "comment": "Cushioning is very plush and doesn't squeeze my ears. Mic quality is crystal clear for office calls.",
        "images": [],
        "is_verified_purchase": True,
        "helpful_votes": 12,
        "review_status": "approved",
        "created_at": "2026-10-22T14:30:00Z"
    }
}


def _is_verified_buyer(user_id: str, product_id: str) -> bool:
    """
    CRITERIA 1: Checks whether the given user has a confirmed,
    shipped, or delivered order containing the target product_id.
    """
    for ord_data in _MEMORY_ORDERS.values():
        if ord_data.get("customer_user_id") == user_id:
            # Check status: Must be at least confirmed
            if ord_data.get("order_status") in ["confirmed", "shipped", "out_for_delivery", "delivered"]:
                for item in ord_data.get("items", []):
                    if item.get("product_id") == product_id:
                        return True
    return False


def _recalculate_product_ratings(product_id: str):
    """
    CRITERIA 2: Recalculates average_rating and review_count
    for the product based on all approved reviews.
    """
    reviews = [
        r for r in _MEMORY_REVIEWS.values()
        if r.get("product_id") == product_id and r.get("review_status", "approved") == "approved"
    ]

    total_count = len(reviews)
    if total_count > 0:
        avg_rating = round(sum(r["rating"] for r in reviews) / total_count, 2)
    else:
        avg_rating = 0.0

    # Update in _MEMORY_PRODUCTS
    for p in _MEMORY_PRODUCTS:
        if p.get("id") == product_id:
            p["average_rating"] = avg_rating
            p["review_count"] = total_count
            break

    return avg_rating, total_count


@router.post("/products/{product_id}/reviews", response_model=ReviewResponse, status_code=status.HTTP_201_CREATED)
async def submit_product_review(
    product_id: str,
    req: ReviewCreateRequest,
    current_user: dict = Depends(get_current_user),
    db: Optional[AsyncSession] = Depends(get_db)
):
    """
    Verified Customer Review Submission:
    1. CRITERIA 1: Verified Buyer Gate: Checks if current user has purchased the product.
       If not, rejects with 403 'Only verified buyers can submit reviews'.
    2. Inserts new verified review.
    3. CRITERIA 2: Recalculates and updates product average_rating & review_count immediately.
    """
    user_id = str(current_user["id"])

    # 1. Verified Buyer Verification
    if not _is_verified_buyer(user_id, product_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only verified buyers can submit reviews"
        )

    # 2. Check if product exists
    target_product = next((p for p in _MEMORY_PRODUCTS if p.get("id") == product_id), None)
    if not target_product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    # 3. Create Review
    review_id = f"rev-{uuid.uuid4().hex[:12]}"
    now_str = datetime.now(timezone.utc).isoformat()
    customer_name = current_user.get("name") or current_user.get("display_name") or "Verified Buyer"

    new_review = {
        "id": review_id,
        "product_id": product_id,
        "customer_user_id": user_id,
        "customer_name": customer_name,
        "order_id": None,
        "rating": req.rating,
        "title": req.title,
        "comment": req.comment,
        "images": req.images or [],
        "is_verified_purchase": True,
        "helpful_votes": 0,
        "review_status": "approved",
        "created_at": now_str,
    }

    _MEMORY_REVIEWS[review_id] = new_review

    # 4. Recalculate Ratings Immediately
    _recalculate_product_ratings(product_id)

    return ReviewResponse(**new_review)


@router.get("/products/{product_id}/reviews", response_model=ProductReviewsSummaryResponse)
async def get_product_reviews(
    product_id: str,
    db: Optional[AsyncSession] = Depends(get_db)
):
    """
    Retrieves approved reviews, average rating, review count,
    and 5-star distribution for a product.
    """
    reviews = [
        r for r in _MEMORY_REVIEWS.values()
        if r.get("product_id") == product_id and r.get("review_status", "approved") == "approved"
    ]
    # Sort newest first
    reviews.sort(key=lambda r: r.get("created_at", ""), reverse=True)

    total_count = len(reviews)
    avg_rating = round(sum(r["rating"] for r in reviews) / total_count, 2) if total_count > 0 else 0.0

    distribution = {"5": 0, "4": 0, "3": 0, "2": 0, "1": 0}
    for r in reviews:
        star_key = str(r["rating"])
        if star_key in distribution:
            distribution[star_key] += 1

    return ProductReviewsSummaryResponse(
        product_id=product_id,
        average_rating=avg_rating,
        review_count=total_count,
        rating_distribution=distribution,
        reviews=[ReviewResponse(**r) for r in reviews]
    )


@router.post("/reviews/{review_id}/helpful")
async def vote_review_helpful(
    review_id: str,
    current_user: dict = Depends(get_current_user),
    db: Optional[AsyncSession] = Depends(get_db)
):
    """Increments helpful count on a customer review."""
    rev = _MEMORY_REVIEWS.get(review_id)
    if not rev:
        raise HTTPException(status_code=404, detail="Review not found")

    rev["helpful_votes"] = rev.get("helpful_votes", 0) + 1
    return {"status": "success", "helpful_votes": rev["helpful_votes"]}

