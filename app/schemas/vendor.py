from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
import re


class VendorApplyRequest(BaseModel):
    store_name: str = Field(..., min_length=2, max_length=120)
    store_slug: str = Field(..., min_length=2, max_length=140)
    business_type: str = Field(default="proprietorship")
    legal_business_name: str = Field(..., min_length=2, max_length=200)
    contact_phone: str = Field(..., min_length=10, max_length=15)
    business_address: Dict[str, Any] = Field(default_factory=dict)
    gstin: Optional[str] = None
    pan_number: Optional[str] = None
    bank_account: Optional[Dict[str, Any]] = None
    documents: Optional[List[Dict[str, Any]]] = None

    @field_validator("gstin")
    @classmethod
    def validate_gstin(cls, v: Optional[str]) -> Optional[str]:
        if v:
            clean = v.strip().upper()
            if not re.match(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$", clean):
                raise ValueError("Invalid Indian GSTIN format (e.g. 27AABCU9603R1ZX)")
            return clean
        return v

    @field_validator("pan_number")
    @classmethod
    def validate_pan(cls, v: Optional[str]) -> Optional[str]:
        if v:
            clean = v.strip().upper()
            if not re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$", clean):
                raise ValueError("Invalid Indian PAN format (e.g. AABCU9603R)")
            return clean
        return v


class VendorProfileResponse(BaseModel):
    id: str
    owner_user_id: str
    store_name: str
    store_slug: str
    description: Optional[str] = None
    application_status: str
    account_status: str
    legal_business_name: Optional[str] = None
    business_type: Optional[str] = None
    gstin: Optional[str] = None
    pan_number: Optional[str] = None
    created_at: Optional[str] = None


class VendorDashboardResponse(BaseModel):
    total_products: int
    active_products: int
    low_stock_count: int
    pending_orders: int
    gross_sales: float
    total_commissions: float
    net_earnings: float


class FulfillSuborderRequest(BaseModel):
    carrier: str = Field(..., min_length=2, max_length=50)  # e.g., 'BlueDart', 'Delhivery', 'DTDC'
    tracking_number: str = Field(..., min_length=3, max_length=100)


class FulfillSuborderResponse(BaseModel):
    status: str = "success"
    message: str
    suborder_id: str
    carrier: str
    tracking_number: str
    fulfillment_status: str = "shipped"


class VendorInventoryItem(BaseModel):
    variant_id: str
    product_id: str
    product_name: str
    sku: str
    variant_attributes: Dict[str, Any] = Field(default_factory=dict)
    selling_price: float
    compare_at_price: Optional[float] = None
    available_stock: int
    low_stock_threshold: int = 10
    is_active: bool = True


class VendorInventoryUpdate(BaseModel):
    selling_price: Optional[float] = Field(default=None, ge=0)
    compare_at_price: Optional[float] = Field(default=None, ge=0)
    available_stock: Optional[int] = Field(default=None, ge=0)
    is_active: Optional[bool] = None


class VendorSuborderItem(BaseModel):
    product_name: str
    sku: str
    quantity: int
    unit_price: float
    line_total: float


class VendorSuborderResponse(BaseModel):
    id: str
    order_id: str
    order_number: str
    vendor_id: str
    store_name: str
    subtotal: float
    commission_total: float = 0.0
    fulfillment_status: str
    items: List[VendorSuborderItem]
    shipping_address: Optional[Dict[str, Any]] = None
    carrier: Optional[str] = None
    tracking_number: Optional[str] = None
    shipped_at: Optional[str] = None
    created_at: str
