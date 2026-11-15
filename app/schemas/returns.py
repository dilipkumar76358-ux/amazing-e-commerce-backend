from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class ReturnInitiateRequest(BaseModel):
    order_item_id: str
    quantity: int = Field(default=1, ge=1)
    reason: str = Field(..., description="defective, wrong_item, not_as_described, size_issue, arrived_late, other")
    description: Optional[str] = ""
    evidence_urls: Optional[List[str]] = Field(default_factory=list)

class ReturnResponse(BaseModel):
    id: str
    order_id: str
    order_item_id: str
    customer_user_id: str
    vendor_id: str
    quantity: int
    reason: str
    description: Optional[str] = None
    evidence_urls: List[str] = Field(default_factory=list)
    return_status: str
    refund_amount: Optional[float] = 0.0
    refund_id: Optional[str] = None
    rejection_reason: Optional[str] = None
    created_at: str

class ReturnModerateRequest(BaseModel):
    action: str = Field(..., description="'approve' or 'reject'")
    rejection_reason: Optional[str] = None

class ReturnModerateResponse(BaseModel):
    status: str
    return_id: str
    new_status: str
    refund_id: Optional[str] = None
    refund_amount: Optional[float] = None
    message: str

