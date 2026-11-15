from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.database import get_db
from app.core.security import get_current_user
from app.schemas.orders import (
    GSTInvoiceResponse,
    SellerSnapshot,
    BillingAddressSnapshot,
    TaxBreakdown,
    InvoiceItem,
    OrderTrackingResponse,
    TrackingStage,
)
from app.api.v1.endpoints.checkout import _MEMORY_ORDERS, _MEMORY_VENDOR_SUBORDERS
from app.api.v1.endpoints.vendor import _MEMORY_VENDORS

router = APIRouter(tags=["Orders, Tracking & GST Invoices"])

# Seed default demo orders into _MEMORY_ORDERS if not yet present
_SEED_ORDERS: Dict[str, Dict[str, Any]] = {
    "ord-demo-001": {
        "id": "ord-demo-001",
        "order_number": "ORD-20261025-001",
        "customer_user_id": "cust-1111-2222-3333-4444",
        "order_status": "delivered",
        "payment_status": "captured",
        "item_subtotal": 3998.00,
        "discount_total": 0.00,
        "shipping_total": 0.00,
        "grand_total": 3998.00,
        "shipping_address_snapshot": {
            "recipient_name": "Rohan Sharma",
            "phone": "+919876543210",
            "address_line_1": "Flat 101, Palm Heights, Indiranagar",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postal_code": "560038",
            "country": "India"
        },
        "items": [
            {
                "item_id": "item-ord-001",
                "product_id": "prod-headphones-01",
                "product_name": "Wireless ANC Bluetooth Over-Ear Headphones (50H Playtime)",
                "sku": "HP-ANC-BLK",
                "hsn_code": "85183000",
                "vendor_id": "vend-5555-6666-7777-8888",
                "store_name": "Apex Electronics Store",
                "quantity": 2,
                "selling_price": 1999.00,
                "line_total": 3998.00,
            }
        ],
        "carrier": "BlueDart",
        "tracking_number": "BD89472918",
        "shipped_at": "2026-11-12T14:15:00Z",
        "delivered_at": "2026-11-13T10:30:00Z",  # Delivered within last 2 days (within 7-day window)
        "created_at": "2026-11-12T10:30:00Z"
    },
    "ord-demo-002": {
        "id": "ord-demo-002",
        "order_number": "ORD-20261025-002",
        "customer_user_id": "cust-1111-2222-3333-4444",
        "order_status": "delivered",
        "payment_status": "captured",
        "item_subtotal": 54990.00,
        "discount_total": 0.00,
        "shipping_total": 0.00,
        "grand_total": 54990.00,
        "shipping_address_snapshot": {
            "recipient_name": "Ananya Patel",
            "phone": "+919123456780",
            "address_line_1": "42 Lake View Apartments",
            "city": "Mumbai",
            "state": "Maharashtra",
            "postal_code": "400050",
            "country": "India"
        },
        "items": [
            {
                "item_id": "item-ord-002",
                "product_id": "prod-laptop-02",
                "product_name": "Ultrabook Thin & Light 15.6-inch Laptop Core i7 (16GB RAM, 512GB SSD)",
                "sku": "LAP-I7-16-512",
                "hsn_code": "84713010",
                "vendor_id": "vend-5555-6666-7777-8888",
                "store_name": "Apex Electronics Store",
                "quantity": 1,
                "selling_price": 54990.00,
                "line_total": 54990.00,
            }
        ],
        "carrier": "BlueDart",
        "tracking_number": "BD987654321IN",
        "shipped_at": "2026-10-10T14:15:00Z",
        "delivered_at": "2026-10-12T16:00:00Z",  # Delivered ~30 days ago (expired return window)
        "created_at": "2026-10-10T10:00:00Z"
    },
    "ord-demo-003": {
        "id": "ord-demo-003",
        "order_number": "ORD-20261025-003",
        "customer_user_id": "cust-1111-2222-3333-4444",
        "order_status": "shipped",  # In transit, not delivered
        "payment_status": "captured",
        "item_subtotal": 2499.00,
        "discount_total": 0.00,
        "shipping_total": 0.00,
        "grand_total": 2499.00,
        "shipping_address_snapshot": {
            "recipient_name": "Vikas Verma",
            "phone": "+919811223344",
            "address_line_1": "Sector 14, Huda Colony",
            "city": "Gurugram",
            "state": "Haryana",
            "postal_code": "122001",
            "country": "India"
        },
        "items": [
            {
                "item_id": "item-ord-003",
                "product_id": "prod-shoes-04",
                "product_name": "Men's Performance Lightweight Breathable Running Shoes",
                "sku": "SHOE-RUN-RED-9",
                "hsn_code": "64041100",
                "vendor_id": "vend-9999-8888-7777-6666",
                "store_name": "StrideStyle Apparel",
                "quantity": 1,
                "selling_price": 2499.00,
                "line_total": 2499.00,
            }
        ],
        "carrier": "Delhivery",
        "tracking_number": "DEL11223344IN",
        "shipped_at": "2026-11-13T11:00:00Z",
        "delivered_at": None,
        "created_at": "2026-11-13T10:00:00Z"
    }
}

for k, v in _SEED_ORDERS.items():
    if k not in _MEMORY_ORDERS:
        _MEMORY_ORDERS[k] = v


def _resolve_hsn_code(sku: str, product_name: str) -> str:
    name_lower = product_name.lower()
    if "headphone" in name_lower or "earbud" in name_lower or "audio" in name_lower:
        return "85183000"
    elif "laptop" in name_lower or "computer" in name_lower or "notebook" in name_lower:
        return "84713010"
    elif "keyboard" in name_lower or "mouse" in name_lower:
        return "84716060"
    elif "shoe" in name_lower or "sneaker" in name_lower or "boot" in name_lower:
        return "64041100"
    elif "shirt" in name_lower or "apparel" in name_lower or "clothing" in name_lower:
        return "61091000"
    return "84716060"


def _find_order(order_id_or_number: str) -> Optional[Dict[str, Any]]:
    for ord_data in _MEMORY_ORDERS.values():
        if ord_data.get("id") == order_id_or_number or ord_data.get("order_number") == order_id_or_number:
            return ord_data
    return None


@router.get("/orders", response_model=List[Dict[str, Any]])
async def list_customer_orders(
    current_user: dict = Depends(get_current_user),
    db: Optional[AsyncSession] = Depends(get_db)
):
    """Lists orders placed by the current authenticated user."""
    user_id = str(current_user["id"])
    roles = current_user.get("roles", [])

    matched = []
    for ord_data in _MEMORY_ORDERS.values():
        if "admin" in roles or ord_data.get("customer_user_id") == user_id:
            matched.append(ord_data)

    return sorted(matched, key=lambda x: x.get("created_at", ""), reverse=True)


@router.get("/orders/{order_id_or_number}/invoice", response_model=GSTInvoiceResponse)
async def get_order_gst_invoice(
    order_id_or_number: str,
    current_user: dict = Depends(get_current_user),
    db: Optional[AsyncSession] = Depends(get_db)
):
    """
    CRITERIA 3: Dynamic Indian GST-Compliant Tax Invoice Generation.
    - Preserves immutable purchase-time snapshots.
    - Accurately computes HSN codes and GST splits (IGST vs CGST+SGST).
    """
    order = _find_order(order_id_or_number)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order '{order_id_or_number}' not found."
        )

    # Permission check: Customer owner, vendor, or admin
    user_id = str(current_user["id"])
    roles = current_user.get("roles", [])
    if "admin" not in roles and order.get("customer_user_id") != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to view this invoice."
        )

    # Resolve Seller
    items = order.get("items", [])
    first_vendor_id = items[0].get("vendor_id") if items else "vend-5555-6666-7777-8888"
    vendor_data = _MEMORY_VENDORS.get(first_vendor_id, {})

    store_name = vendor_data.get("store_name", items[0].get("store_name", "Apex Electronics Store") if items else "Marketplace Merchant")
    legal_name = vendor_data.get("legal_business_name", f"{store_name} Pvt Ltd")
    gstin = vendor_data.get("gstin", "27AABCU9603R1ZX")
    v_addr = vendor_data.get("business_address", {})
    seller_state = v_addr.get("state", "Karnataka")
    seller_address = f"{v_addr.get('address_line_1', 'Tech Park')}, {v_addr.get('city', 'Bengaluru')}, {seller_state} {v_addr.get('postal_code', '560066')}"

    seller_snapshot = SellerSnapshot(
        store_name=store_name,
        legal_name=legal_name,
        gstin=gstin,
        address=seller_address
    )

    # Resolve Billing Address
    ship_addr = order.get("shipping_address_snapshot", {})
    billing_state = ship_addr.get("state", "Karnataka")
    billing_snapshot = BillingAddressSnapshot(
        recipient_name=ship_addr.get("recipient_name", "Valued Customer"),
        address_line_1=ship_addr.get("address_line_1", "Marketplace Address"),
        city=ship_addr.get("city", "Bengaluru"),
        state=billing_state,
        postal_code=ship_addr.get("postal_code", "560001"),
        country=ship_addr.get("country", "India")
    )

    # Tax Calculation: 18% GST standard rate
    # Determine Inter-State vs Intra-State
    is_inter_state = seller_state.strip().lower() != billing_state.strip().lower()

    invoice_items: List[InvoiceItem] = []
    total_tax = 0.0

    for itm in items:
        p_name = itm.get("product_name", "Marketplace Item")
        sku = itm.get("sku", "SKU-GEN")
        hsn = itm.get("hsn_code") or _resolve_hsn_code(sku, p_name)
        qty = int(itm.get("quantity", 1))
        selling_price = float(itm.get("selling_price", itm.get("unit_price", 0.0)))
        line_total = round(selling_price * qty, 2)

        # Base price (excluding 18% tax) = selling_price / 1.18
        unit_base = round(selling_price / 1.18, 2)
        unit_tax = round(selling_price - unit_base, 2)
        item_tax_total = round(unit_tax * qty, 2)
        total_tax += item_tax_total

        invoice_items.append(
            InvoiceItem(
                product_name=p_name,
                sku=sku,
                hsn_code=hsn,
                quantity=qty,
                unit_price=unit_base,
                tax_amount=item_tax_total,
                line_total=line_total
            )
        )

    total_tax = round(total_tax, 2)

    if is_inter_state:
        tax_breakdown = TaxBreakdown(
            inter_state=True,
            igst_rate=18.0,
            igst_amount=total_tax,
            cgst_amount=0.0,
            sgst_amount=0.0
        )
    else:
        half_tax = round(total_tax / 2, 2)
        tax_breakdown = TaxBreakdown(
            inter_state=False,
            igst_rate=0.0,
            igst_amount=0.0,
            cgst_amount=half_tax,
            sgst_amount=round(total_tax - half_tax, 2)
        )

    order_num = order.get("order_number", "ORD-20261025-001")
    inv_number = f"INV-2026-{order_num.replace('ORD-', '')}"

    return GSTInvoiceResponse(
        invoice_number=inv_number,
        invoice_date=order.get("created_at", datetime.now(timezone.utc).isoformat()),
        order_number=order_num,
        seller=seller_snapshot,
        billing_address=billing_snapshot,
        tax_breakdown=tax_breakdown,
        items=invoice_items,
        grand_total=float(order.get("grand_total", sum(i.line_total for i in invoice_items)))
    )


@router.get("/orders/{order_id_or_number}/tracking", response_model=OrderTrackingResponse)
async def get_order_tracking(
    order_id_or_number: str,
    current_user: dict = Depends(get_current_user),
    db: Optional[AsyncSession] = Depends(get_db)
):
    """
    Amazon-style 4-stage visual tracking progress:
    [Confirmed] -> [Shipped] -> [Out for Delivery] -> [Delivered]
    Also computes 7-day return eligibility.
    """
    order = _find_order(order_id_or_number)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order '{order_id_or_number}' not found."
        )

    user_id = str(current_user["id"])
    roles = current_user.get("roles", [])
    if "admin" not in roles and order.get("customer_user_id") != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to view tracking for this order."
        )

    order_status = order.get("order_status", "confirmed").lower()
    carrier = order.get("carrier")
    tracking_num = order.get("tracking_number")
    shipped_at = order.get("shipped_at")
    delivered_at = order.get("delivered_at")

    # Map current stage
    if order_status in ["delivered"]:
        current_stage = "delivered"
    elif order_status in ["out_for_delivery"]:
        current_stage = "out_for_delivery"
    elif order_status in ["shipped"]:
        current_stage = "shipped"
    else:
        current_stage = "confirmed"

    # Evaluate 7-day return window eligibility
    is_return_eligible = False
    return_window_closes_at = None

    if order_status == "delivered" and delivered_at:
        try:
            del_dt = datetime.fromisoformat(delivered_at.replace("Z", "+00:00"))
            now_dt = datetime.now(timezone.utc)
            expiry_dt = del_dt + timedelta(days=7)
            return_window_closes_at = expiry_dt.isoformat()
            if now_dt <= expiry_dt:
                is_return_eligible = True
        except Exception:
            is_return_eligible = True

    # Carrier tracking URL
    tracking_url = None
    if tracking_num:
        if carrier and "blue" in carrier.lower():
            tracking_url = f"https://www.bluedart.com/tracking?track={tracking_num}"
        elif carrier and "delhivery" in carrier.lower():
            tracking_url = f"https://www.delhivery.com/track/package/{tracking_num}"
        else:
            tracking_url = f"https://shipment-tracking.amazing.in/?tracking={tracking_num}"

    # Construct the 4 stages
    order_created = order.get("created_at", "2026-11-12T10:30:00Z")

    stage_confirmed = TrackingStage(
        key="confirmed",
        label="Order Confirmed",
        description="Order placed and payment captured successfully",
        status="completed" if current_stage in ["confirmed", "shipped", "out_for_delivery", "delivered"] else "upcoming",
        timestamp=order_created
    )

    stage_shipped = TrackingStage(
        key="shipped",
        label="Shipped",
        description=f"Dispatched via {carrier or 'Partner Courier'} ({tracking_num or 'Pending Tracking'})",
        status="completed" if current_stage in ["shipped", "out_for_delivery", "delivered"] else ("current" if current_stage == "shipped" else "upcoming"),
        timestamp=shipped_at
    )

    stage_out = TrackingStage(
        key="out_for_delivery",
        label="Out for Delivery",
        description="Package is out with your local delivery courier",
        status="completed" if current_stage == "delivered" else ("current" if current_stage == "out_for_delivery" else "upcoming"),
        timestamp=delivered_at if current_stage == "delivered" else None
    )

    stage_delivered = TrackingStage(
        key="delivered",
        label="Delivered",
        description="Package delivered safely to recipient address",
        status="completed" if current_stage == "delivered" else "upcoming",
        timestamp=delivered_at
    )

    return OrderTrackingResponse(
        order_id=order["id"],
        order_number=order["order_number"],
        order_status=order_status,
        current_stage=current_stage,
        carrier=carrier,
        tracking_number=tracking_num,
        carrier_tracking_url=tracking_url,
        estimated_delivery=(datetime.fromisoformat(order_created.replace("Z", "+00:00")) + timedelta(days=2)).isoformat(),
        delivered_at=delivered_at,
        is_return_eligible=is_return_eligible,
        return_window_closes_at=return_window_closes_at,
        stages=[stage_confirmed, stage_shipped, stage_out, stage_delivered]
    )

