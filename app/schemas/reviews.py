from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class ReviewCreateRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5, description="1 to 5 star rating")
    title: str = Field(..., min_length=2, max_length=255)
    comment: str = Field(..., min_length=5)
    images: Optional[List[str]] = Field(default_factory=list)

class ReviewResponse(BaseModel):
    id: str
    product_id: str
    customer_user_id: str
    customer_name: str
    order_id: Optional[str] = None
    rating: int
    title: Optional[str] = None
    comment: Optional[str] = None
    images: List[str] = Field(default_factory=list)
    is_verified_purchase: bool = True
    helpful_votes: int = 0
    created_at: str

class ProductReviewsSummaryResponse(BaseModel):
    product_id: str
    average_rating: float
    review_count: int
    rating_distribution: Dict[str, int]
    reviews: List[ReviewResponse]

