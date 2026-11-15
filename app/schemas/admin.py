from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any


class VendorModerationRequest(BaseModel):
    action: str = Field(..., description="'approve', 'reject', or 'suspend'")
    reason: Optional[str] = None

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        clean = v.strip().lower()
        if clean not in ["approve", "reject", "suspend"]:
            raise ValueError("Action must be 'approve', 'reject', or 'suspend'")
        return clean


class VendorModerationResponse(BaseModel):
    status: str = "success"
    message: str
    vendor_id: str
    new_status: str


class ProductModerationRequest(BaseModel):
    reason: Optional[str] = None


class ProductModerationResponse(BaseModel):
    status: str = "success"
    message: str
    product_id: str
    new_status: str


class CommissionRuleCreate(BaseModel):
    rule_type: str = Field(..., description="'platform_default', 'category', 'vendor', or 'product'")
    target_id: Optional[str] = None
    target_name: Optional[str] = None
    rate_percentage: float = Field(..., ge=0, le=100)

    @field_validator("rule_type")
    @classmethod
    def validate_rule_type(cls, v: str) -> str:
        clean = v.strip().lower()
        if clean not in ["platform_default", "category", "vendor", "product"]:
            raise ValueError("Rule type must be 'platform_default', 'category', 'vendor', or 'product'")
        return clean


class CommissionRuleResponse(BaseModel):
    id: str
    rule_type: str
    target_id: Optional[str] = None
    target_name: Optional[str] = None
    rate_percentage: float
    is_active: bool = True
    created_at: str


class SettlementCalculateRequest(BaseModel):
    settlement_days: int = Field(default=7, ge=1, le=90)


class SettlementRecordResponse(BaseModel):
    id: str
    vendor_id: str
    vendor_name: str
    period_start: str
    period_end: str
    gross_amount: float
    commission_amount: float
    refund_deductions: float = 0.0
    net_payout: float
    payout_status: str
    reference_number: Optional[str] = None
    created_at: str


class AuditLogResponse(BaseModel):
    id: str
    actor_user_id: Optional[str] = None
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str


class AdminDashboardMetricsResponse(BaseModel):
    status: str = "success"
    message: str = "Welcome to Admin Command Center"
    privilege_level: str = "super_admin"
    gmv_inr: float
    platform_net_revenue_inr: float
    total_orders: int
    total_vendors: int
    active_vendors: int
    pending_vendor_applications: int
    pending_products_count: int
    payment_conversion_rate: float
