from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class SellerSnapshot(BaseModel):
    store_name: str
    legal_name: str
    gstin: str
    address: str

class BillingAddressSnapshot(BaseModel):
    recipient_name: str
    address_line_1: str
    city: str
    state: str
    postal_code: str
    country: str = "India"

class TaxBreakdown(BaseModel):
    inter_state: bool
    igst_rate: float
    igst_amount: float
    cgst_amount: float
    sgst_amount: float

class InvoiceItem(BaseModel):
    product_name: str
    sku: str
    hsn_code: str
    quantity: int
    unit_price: float
    tax_amount: float
    line_total: float

class GSTInvoiceResponse(BaseModel):
    invoice_number: str
    invoice_date: str
    order_number: str
    seller: SellerSnapshot
    billing_address: BillingAddressSnapshot
    tax_breakdown: TaxBreakdown
    items: List[InvoiceItem]
    grand_total: float

class TrackingStage(BaseModel):
    key: str
    label: str
    description: str
    status: str  # 'completed', 'current', 'upcoming'
    timestamp: Optional[str] = None

class OrderTrackingResponse(BaseModel):
    order_id: str
    order_number: str
    order_status: str
    current_stage: str  # 'confirmed', 'shipped', 'out_for_delivery', 'delivered'
    carrier: Optional[str] = None
    tracking_number: Optional[str] = None
    carrier_tracking_url: Optional[str] = None
    estimated_delivery: Optional[str] = None
    delivered_at: Optional[str] = None
    is_return_eligible: bool
    return_window_closes_at: Optional[str] = None
    stages: List[TrackingStage]

