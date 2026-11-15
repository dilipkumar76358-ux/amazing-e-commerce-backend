from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
import re


class AddressCreateRequest(BaseModel):
    recipient_name: str = Field(..., min_length=2, max_length=100)
    phone: str = Field(..., min_length=10, max_length=15)
    address_line_1: str = Field(..., min_length=5, max_length=255)
    address_line_2: Optional[str] = None
    landmark: Optional[str] = None
    city: str = Field(..., min_length=2, max_length=100)
    state: str = Field(..., min_length=2, max_length=100)
    postal_code: str = Field(..., min_length=6, max_length=6)
    country: str = Field(default="India")
    address_type: str = Field(default="home")
    is_default: bool = False

    @field_validator("postal_code")
    @classmethod
    def validate_postal_code(cls, v: str) -> str:
        clean = v.strip()
        if not re.match(r"^\d{6}$", clean):
            raise ValueError("Indian PIN code must be exactly 6 numeric digits")
        return clean

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        clean = re.sub(r"[^\d+]", "", v)
        if len(clean) < 10:
            raise ValueError("Phone number must have at least 10 digits")
        return clean


class AddressResponse(BaseModel):
    id: str
    user_id: str
    recipient_name: str
    phone: str
    address_line_1: str
    address_line_2: Optional[str] = None
    landmark: Optional[str] = None
    city: str
    state: str
    postal_code: str
    country: str = "India"
    address_type: str = "home"
    is_default: bool = False
    created_at: Optional[str] = None


class CouponValidateRequest(BaseModel):
    code: str = Field(..., min_length=2, max_length=30)
    cart_subtotal: float = Field(..., ge=0)


class CouponValidateResponse(BaseModel):
    code: str
    is_valid: bool
    discount_amount: float
    new_subtotal: float
    message: str


class CheckoutInitiateRequest(BaseModel):
    address_id: str
    coupon_code: Optional[str] = None
    variant_id: Optional[str] = None
    quantity: Optional[int] = 1


class CheckoutInitiateResponse(BaseModel):
    order_id: str
    order_number: str
    amount_paise: int
    currency: str = "INR"
    gateway_order_id: str
    key_id: str
    item_subtotal: float
    discount_total: float = 0.0
    shipping_total: float = 0.0
    grand_total: float
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None


class PaymentVerifyRequest(BaseModel):
    order_id: str
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class PaymentVerifyResponse(BaseModel):
    status: str
    message: str
    order_id: str
    order_number: str
    grand_total: float


class OrderItemSnapshot(BaseModel):
    product_name: str
    sku: str
    quantity: int
    unit_price: float
    line_total: float


class VendorSuborderSnapshot(BaseModel):
    suborder_id: str
    vendor_id: str
    store_name: str
    subtotal: float
    fulfillment_status: str
    items: List[OrderItemSnapshot]


class OrderDetailResponse(BaseModel):
    id: str
    order_number: str
    order_status: str
    payment_status: str
    item_subtotal: float
    discount_total: float
    shipping_total: float
    grand_total: float
    shipping_address_snapshot: Dict[str, Any]
    vendor_suborders: List[VendorSuborderSnapshot]
    created_at: str
