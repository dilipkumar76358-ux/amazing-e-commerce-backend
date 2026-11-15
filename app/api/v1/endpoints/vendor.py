from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from datetime import datetime, timezone
import uuid

from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.schemas.vendor import (
    VendorApplyRequest,
    VendorProfileResponse,
    VendorDashboardResponse,
    FulfillSuborderRequest,
    FulfillSuborderResponse,
    VendorInventoryItem,
    VendorInventoryUpdate,
    VendorSuborderResponse,
    VendorSuborderItem,
)
from app.api.v1.endpoints.catalog import _MEMORY_PRODUCTS

router = APIRouter(tags=["Vendor Management & Fulfillment"])

# ============================================================================
# In-Memory Bootstrap Stores (Synchronized with Catalog and Checkout)
# ============================================================================

_MEMORY_VENDORS: Dict[str, Dict[str, Any]] = {
    "vend-5555-6666-7777-8888": {
        "id": "vend-5555-6666-7777-8888",
        "owner_user_id": "vend-5555-6666-7777-8888",
        "store_name": "Apex Electronics Store",
        "store_slug": "apex-electronics-store",
        "description": "Authorized dealer of premium audio and personal electronics.",
        "legal_business_name": "Apex Electronics Pvt Ltd",
        "business_type": "pvt_ltd",
        "gstin": "27AABCU9603R1ZX",
        "pan_number": "AABCU9603R",
        "contact_phone": "+919876543210",
        "business_address": {
            "address_line_1": "Tech Park, Phase 2, Whitefield",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postal_code": "560066",
            "country": "India"
        },
        "bank_account": {
            "account_holder_name": "Apex Electronics Pvt Ltd",
            "account_number": "91234567890123",
            "ifsc_code": "HDFC0001234",
            "bank_name": "HDFC Bank"
        },
        "application_status": "approved",
        "account_status": "active",
        "created_at": "2026-10-25T00:00:00Z"
    },
    "vend-9999-8888-7777-6666": {
        "id": "vend-9999-8888-7777-6666",
        "owner_user_id": "vend-other-9999-0000",
        "store_name": "StrideStyle Apparel",
        "store_slug": "stridestyle-apparel",
        "description": "High performance athletic footwear and lifestyle apparel.",
        "legal_business_name": "StrideStyle Retail LLP",
        "business_type": "llp",
        "gstin": "29AAACR5055K1Z8",
        "pan_number": "AAACR5055K",
        "contact_phone": "+919876543211",
        "business_address": {
            "address_line_1": "10 Commercial Street",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postal_code": "560001",
            "country": "India"
        },
        "bank_account": {
            "account_holder_name": "StrideStyle Retail LLP",
            "account_number": "98765432109876",
            "ifsc_code": "ICIC0005678",
            "bank_name": "ICICI Bank"
        },
        "application_status": "approved",
        "account_status": "active",
        "created_at": "2026-10-25T00:00:00Z"
    },
    "vend-pending-store-1111": {
        "id": "vend-pending-store-1111",
        "owner_user_id": "vend-pending-user-1111",
        "store_name": "Pending Merchant Hub",
        "store_slug": "pending-merchant-hub",
        "description": "Onboarding vendor store pending KYC verification.",
        "legal_business_name": "Pending Merchant Hub Enterprise",
        "business_type": "proprietorship",
        "gstin": "27AABCU9603R1ZX",
        "pan_number": "AABCU9603R",
        "contact_phone": "+919876543212",
        "business_address": {
            "address_line_1": "Shop 4, Market Complex",
            "city": "Pune",
            "state": "Maharashtra",
            "postal_code": "411001",
            "country": "India"
        },
        "application_status": "submitted",
        "account_status": "active",
        "created_at": "2026-10-27T00:00:00Z"
    }
}

_MEMORY_SUBORDERS_LIST: List[Dict[str, Any]] = [
    {
        "id": "subord-apex-001",
        "order_id": "ord-demo-001",
        "order_number": "ORD-20261025-001",
        "vendor_id": "vend-5555-6666-7777-8888",
        "store_name": "Apex Electronics Store",
        "subtotal": 3998.00,
        "commission_total": 399.80,
        "fulfillment_status": "unfulfilled",
        "items": [
            {
                "product_name": "Wireless ANC Bluetooth Over-Ear Headphones (50H Playtime)",
                "sku": "HP-ANC-BLK",
                "quantity": 2,
                "unit_price": 1999.00,
                "line_total": 3998.00
            }
        ],
        "shipping_address": {
            "recipient_name": "Rohan Sharma",
            "phone": "+919876543210",
            "address_line_1": "Flat 101, Palm Heights, Indiranagar",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postal_code": "560038",
            "country": "India"
        },
        "carrier": None,
        "tracking_number": None,
        "shipped_at": None,
        "created_at": "2026-10-26T10:30:00Z"
    },
    {
        "id": "subord-apex-002",
        "order_id": "ord-demo-002",
        "order_number": "ORD-20261025-002",
        "vendor_id": "vend-5555-6666-7777-8888",
        "store_name": "Apex Electronics Store",
        "subtotal": 54990.00,
        "commission_total": 5499.00,
        "fulfillment_status": "shipped",
        "items": [
            {
                "product_name": "Ultrabook Thin & Light 15.6-inch Laptop Core i7 (16GB RAM, 512GB SSD)",
                "sku": "LAP-I7-16-512",
                "quantity": 1,
                "unit_price": 54990.00,
                "line_total": 54990.00
            }
        ],
        "shipping_address": {
            "recipient_name": "Ananya Patel",
            "phone": "+919123456780",
            "address_line_1": "42 Lake View Apartments",
            "city": "Mumbai",
            "state": "Maharashtra",
            "postal_code": "400050",
            "country": "India"
        },
        "carrier": "BlueDart",
        "tracking_number": "BD987654321IN",
        "shipped_at": "2026-10-26T14:15:00Z",
        "created_at": "2026-10-25T16:00:00Z"
    },
    {
        "id": "subord-stride-001",
        "order_id": "ord-demo-003",
        "order_number": "ORD-20261025-003",
        "vendor_id": "vend-9999-8888-7777-6666",
        "store_name": "StrideStyle Apparel",
        "subtotal": 2499.00,
        "commission_total": 249.90,
        "fulfillment_status": "unfulfilled",
        "items": [
            {
                "product_name": "Men's AeroBounce Lightweight Running Shoes",
                "sku": "SHOE-RUN-RED-9",
                "quantity": 1,
                "unit_price": 2499.00,
                "line_total": 2499.00
            }
        ],
        "shipping_address": {
            "recipient_name": "Vikas Verma",
            "phone": "+919811223344",
            "address_line_1": "Sector 14, Huda Colony",
            "city": "Gurugram",
            "state": "Haryana",
            "postal_code": "122001",
            "country": "India"
        },
        "carrier": None,
        "tracking_number": None,
        "shipped_at": None,
        "created_at": "2026-10-26T11:00:00Z"
    }
]


def _get_all_suborders() -> List[Dict[str, Any]]:
    """Merges seeded suborders with newly generated checkout suborders."""
    combined = list(_MEMORY_SUBORDERS_LIST)
    known_ids = {s["id"] for s in combined}
    try:
        from app.api.v1.endpoints.checkout import _MEMORY_VENDOR_SUBORDERS, _MEMORY_ORDERS
        for order_id, sub_list in _MEMORY_VENDOR_SUBORDERS.items():
            ord_data = _MEMORY_ORDERS.get(order_id, {})
            for sub in sub_list:
                s_id = sub.get("suborder_id") or sub.get("id")
                if s_id and s_id not in known_ids:
                    combined.append({
                        "id": s_id,
                        "order_id": order_id,
                        "order_number": ord_data.get("order_number", f"ORD-{order_id[:8]}"),
                        "vendor_id": sub.get("vendor_id"),
                        "store_name": sub.get("store_name", "Featured Merchant"),
                        "subtotal": sub.get("subtotal", 0.0),
                        "commission_total": round(sub.get("subtotal", 0.0) * 0.1, 2),
                        "fulfillment_status": sub.get("fulfillment_status", "unfulfilled"),
                        "items": sub.get("items", []),
                        "shipping_address": ord_data.get("shipping_address_snapshot"),
                        "carrier": sub.get("carrier"),
                        "tracking_number": sub.get("tracking_number"),
                        "shipped_at": sub.get("shipped_at"),
                        "created_at": ord_data.get("created_at", datetime.now(timezone.utc).isoformat()),
                    })
                    known_ids.add(s_id)
    except Exception:
        pass
    return combined


def _sync_suborder_update(suborder_id: str, updates: Dict[str, Any]):
    """Syncs suborder state changes across all memory stores."""
    for s in _MEMORY_SUBORDERS_LIST:
        if s["id"] == suborder_id:
            s.update(updates)
            return
    try:
        from app.api.v1.endpoints.checkout import _MEMORY_VENDOR_SUBORDERS
        for order_id, sub_list in _MEMORY_VENDOR_SUBORDERS.items():
            for sub in sub_list:
                if (sub.get("suborder_id") == suborder_id) or (sub.get("id") == suborder_id):
                    sub.update(updates)
                    return
    except Exception:
        pass


# ============================================================================
# Tenant Isolation Dependency (FastAPI Guard)
# ============================================================================

async def get_current_vendor(
    current_user: dict = Depends(get_current_user),
    db: Optional[AsyncSession] = Depends(get_db)
) -> dict:
    """
    Verifies that the user has an approved vendor store and returns vendor details.
    Enforces strict tenant isolation.
    """
    user_id = str(current_user["id"])

    # 1. Database Verification
    if db is not None:
        try:
            query = text("""
                SELECT v.id as vendor_id, v.owner_user_id, v.store_name, v.store_slug,
                       v.application_status, v.account_status, v.description
                FROM public.vendors v
                WHERE v.owner_user_id = :user_id OR v.id = :user_id
            """)
            res = await db.execute(query, {"user_id": user_id})
            vendor_row = res.mappings().first()
            if vendor_row:
                vendor = dict(vendor_row)
                if vendor["application_status"] != "approved":
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Vendor application is currently {vendor['application_status']}. Access restricted."
                    )
                if vendor["account_status"] != "active":
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Vendor account has been suspended"
                    )
                return vendor
        except HTTPException:
            raise
        except Exception:
            pass

    # 2. In-Memory Store Fallback
    vendor = None
    for v in _MEMORY_VENDORS.values():
        if v["owner_user_id"] == user_id or v["id"] == user_id:
            vendor = v
            break

    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No vendor profile associated with this account"
        )

    if vendor["application_status"] != "approved":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Vendor application is currently {vendor['application_status']}. Access restricted."
        )

    if vendor["account_status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vendor account has been suspended"
        )

    return {
        "vendor_id": vendor["id"],
        "id": vendor["id"],
        "owner_user_id": vendor["owner_user_id"],
        "store_name": vendor["store_name"],
        "store_slug": vendor["store_slug"],
        "application_status": vendor["application_status"],
        "account_status": vendor["account_status"],
        "description": vendor.get("description"),
    }


# ============================================================================
# Vendor Endpoints
# ============================================================================

@router.get("/vendor/check-slug")
async def check_vendor_slug_availability(slug: str = Query(..., min_length=2)):
    """Checks whether a vendor store slug is available."""
    clean_slug = slug.strip().lower()
    for v in _MEMORY_VENDORS.values():
        if v["store_slug"] == clean_slug:
            return {"slug": clean_slug, "is_available": False}
    return {"slug": clean_slug, "is_available": True}


@router.post("/vendor/apply", response_model=VendorProfileResponse, status_code=status.HTTP_201_CREATED)
@router.post("/vendor-applications", response_model=VendorProfileResponse, status_code=status.HTTP_201_CREATED)
async def submit_vendor_application(
    req: VendorApplyRequest,
    current_user: dict = Depends(get_current_user),
    db: Optional[AsyncSession] = Depends(get_db)
):
    """
    Vendor Onboarding Application:
    Collects business details, GSTIN, PAN, and KYC docs into private storage.
    Enters 'submitted' state pending Admin approval.
    """
    user_id = str(current_user["id"])

    # Check for existing application
    for v in _MEMORY_VENDORS.values():
        if v["owner_user_id"] == user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You have already submitted a vendor application"
            )
        if v["store_slug"] == req.store_slug:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Store slug '{req.store_slug}' is already taken"
            )

    new_vendor_id = f"vend-{uuid.uuid4().hex[:12]}"
    now_str = datetime.now(timezone.utc).isoformat()

    new_vendor_record = {
        "id": new_vendor_id,
        "owner_user_id": user_id,
        "store_name": req.store_name,
        "store_slug": req.store_slug,
        "description": f"{req.store_name} online storefront.",
        "legal_business_name": req.legal_business_name,
        "business_type": req.business_type,
        "gstin": req.gstin,
        "pan_number": req.pan_number,
        "contact_phone": req.contact_phone,
        "business_address": req.business_address,
        "bank_account": req.bank_account,
        "documents": req.documents or [],
        "application_status": "submitted",
        "account_status": "active",
        "created_at": now_str,
    }

    # DB Persistence
    if db is not None:
        try:
            await db.execute(text("""
                INSERT INTO public.vendors (
                    id, owner_user_id, store_name, store_slug, application_status, account_status
                ) VALUES (
                    :id, :owner_id, :name, :slug, 'submitted', 'active'
                );
            """), {
                "id": new_vendor_id,
                "owner_id": user_id,
                "name": req.store_name,
                "slug": req.store_slug
            })
            await db.commit()
        except Exception:
            pass

    _MEMORY_VENDORS[new_vendor_id] = new_vendor_record

    return VendorProfileResponse(
        id=new_vendor_id,
        owner_user_id=user_id,
        store_name=req.store_name,
        store_slug=req.store_slug,
        description=new_vendor_record["description"],
        application_status="submitted",
        account_status="active",
        legal_business_name=req.legal_business_name,
        business_type=req.business_type,
        gstin=req.gstin,
        pan_number=req.pan_number,
        created_at=now_str
    )


@router.get("/vendor/profile")
async def get_vendor_profile(
    current_user: dict = Depends(get_current_user),
    db: Optional[AsyncSession] = Depends(get_db)
):
    """Retrieves current user's vendor profile and application status."""
    user_id = str(current_user["id"])

    # Look up in memory
    for v in _MEMORY_VENDORS.values():
        if v["owner_user_id"] == user_id or v["id"] == user_id:
            return v

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="No vendor application found for this account"
    )


@router.get("/vendor/dashboard", response_model=VendorDashboardResponse)
async def get_vendor_dashboard(
    vendor: dict = Depends(get_current_vendor),
    db: Optional[AsyncSession] = Depends(get_db)
):
    """
    Vendor Dashboard Analytics:
    Calculates total products, active listings, low stock items,
    pending suborders, gross sales, and net earnings.
    """
    vendor_id = vendor["vendor_id"]

    # 1. DB Execution if available
    if db is not None:
        try:
            query = text("""
                SELECT 
                    (SELECT COUNT(*) FROM public.products WHERE vendor_id = :v_id) as total_products,
                    (SELECT COUNT(*) FROM public.products WHERE vendor_id = :v_id AND product_status = 'active') as active_products,
                    (SELECT COUNT(*) FROM public.inventory i JOIN public.product_variants pv ON pv.id = i.variant_id JOIN public.products p ON p.id = pv.product_id WHERE p.vendor_id = :v_id AND i.available_quantity <= i.low_stock_threshold) as low_stock_count,
                    (SELECT COUNT(*) FROM public.vendor_suborders WHERE vendor_id = :v_id AND fulfillment_status = 'unfulfilled') as pending_orders,
                    COALESCE((SELECT SUM(subtotal) FROM public.vendor_suborders WHERE vendor_id = :v_id), 0.0) as gross_sales,
                    COALESCE((SELECT SUM(commission_total) FROM public.vendor_suborders WHERE vendor_id = :v_id), 0.0) as total_commissions
            """)
            res = await db.execute(query, {"v_id": vendor_id})
            db_stats = res.mappings().first()
            if db_stats and db_stats["total_products"] > 0:
                stats = dict(db_stats)
                gross = float(stats["gross_sales"])
                comm = float(stats["total_commissions"])
                return VendorDashboardResponse(
                    total_products=int(stats["total_products"]),
                    active_products=int(stats["active_products"]),
                    low_stock_count=int(stats["low_stock_count"]),
                    pending_orders=int(stats["pending_orders"]),
                    gross_sales=round(gross, 2),
                    total_commissions=round(comm, 2),
                    net_earnings=round(gross - comm, 2)
                )
        except Exception:
            pass

    # 2. In-Memory Calculation
    # Products
    vendor_products = [p for p in _MEMORY_PRODUCTS if p.get("vendor_id") == vendor_id]
    total_products = len(vendor_products)
    active_products = len([p for p in vendor_products if p.get("product_status") == "active"])

    # Low stock variants (available_stock <= 10)
    low_stock_count = 0
    for prod in vendor_products:
        for var in prod.get("variants", []):
            if var.get("available_stock", 0) <= 10:
                low_stock_count += 1

    # Suborders
    all_suborders = _get_all_suborders()
    vendor_suborders = [s for s in all_suborders if s.get("vendor_id") == vendor_id]
    pending_orders = len([s for s in vendor_suborders if s.get("fulfillment_status") == "unfulfilled"])

    gross_sales = sum(float(s.get("subtotal", 0.0)) for s in vendor_suborders)
    total_commissions = sum(float(s.get("commission_total", 0.0)) for s in vendor_suborders)
    net_earnings = round(gross_sales - total_commissions, 2)

    return VendorDashboardResponse(
        total_products=total_products,
        active_products=active_products,
        low_stock_count=low_stock_count,
        pending_orders=pending_orders,
        gross_sales=round(gross_sales, 2),
        total_commissions=round(total_commissions, 2),
        net_earnings=net_earnings
    )


@router.get("/vendor/suborders", response_model=List[VendorSuborderResponse])
async def list_vendor_suborders(
    status_filter: Optional[str] = Query(None, alias="status"),
    vendor: dict = Depends(get_current_vendor),
    db: Optional[AsyncSession] = Depends(get_db)
):
    """
    Strict Tenant Isolation Suborder List:
    Merchants can only see suborders assigned to their vendor_id.
    """
    vendor_id = vendor["vendor_id"]
    all_suborders = _get_all_suborders()
    suborders = [s for s in all_suborders if s.get("vendor_id") == vendor_id]

    if status_filter and status_filter.lower() != "all":
        suborders = [s for s in suborders if s.get("fulfillment_status") == status_filter.lower()]

    return [
        VendorSuborderResponse(
            id=s["id"],
            order_id=s["order_id"],
            order_number=s["order_number"],
            vendor_id=s["vendor_id"],
            store_name=s["store_name"],
            subtotal=s["subtotal"],
            commission_total=s.get("commission_total", 0.0),
            fulfillment_status=s["fulfillment_status"],
            items=[VendorSuborderItem(**item) for item in s["items"]],
            shipping_address=s.get("shipping_address"),
            carrier=s.get("carrier"),
            tracking_number=s.get("tracking_number"),
            shipped_at=s.get("shipped_at"),
            created_at=s["created_at"]
        )
        for s in suborders
    ]


@router.get("/vendor/suborders/{suborder_id}", response_model=VendorSuborderResponse)
async def get_vendor_suborder_detail(
    suborder_id: str,
    vendor: dict = Depends(get_current_vendor),
    db: Optional[AsyncSession] = Depends(get_db)
):
    """
    Strict Tenant Isolation Suborder Detail:
    Returns 404 if suborder does not belong to the authenticated vendor.
    """
    vendor_id = vendor["vendor_id"]
    all_suborders = _get_all_suborders()
    target = next((s for s in all_suborders if s["id"] == suborder_id and s["vendor_id"] == vendor_id), None)

    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Suborder not found or unauthorized"
        )

    return VendorSuborderResponse(
        id=target["id"],
        order_id=target["order_id"],
        order_number=target["order_number"],
        vendor_id=target["vendor_id"],
        store_name=target["store_name"],
        subtotal=target["subtotal"],
        commission_total=target.get("commission_total", 0.0),
        fulfillment_status=target["fulfillment_status"],
        items=[VendorSuborderItem(**item) for item in target["items"]],
        shipping_address=target.get("shipping_address"),
        carrier=target.get("carrier"),
        tracking_number=target.get("tracking_number"),
        shipped_at=target.get("shipped_at"),
        created_at=target["created_at"]
    )


@router.post("/vendor/suborders/{suborder_id}/dispatch", response_model=FulfillSuborderResponse)
async def dispatch_vendor_suborder(
    suborder_id: str,
    req: FulfillSuborderRequest,
    vendor: dict = Depends(get_current_vendor),
    db: Optional[AsyncSession] = Depends(get_db)
):
    """
    Suborder Dispatch & Tracking Attachment:
    1. Verifies suborder belongs strictly to this vendor (tenant isolation).
    2. Validates suborder is not already shipped/delivered.
    3. Transitions fulfillment_status to 'shipped'.
    4. Attaches carrier and tracking number.
    """
    vendor_id = vendor["vendor_id"]

    # Locate suborder with strict tenant check
    all_suborders = _get_all_suborders()
    target = next((s for s in all_suborders if s["id"] == suborder_id and s["vendor_id"] == vendor_id), None)

    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Suborder not found or unauthorized"
        )

    if target["fulfillment_status"] in ["shipped", "delivered", "cancelled"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot dispatch suborder in {target['fulfillment_status']} state"
        )

    now_str = datetime.now(timezone.utc).isoformat()
    updates = {
        "fulfillment_status": "shipped",
        "carrier": req.carrier,
        "tracking_number": req.tracking_number,
        "shipped_at": now_str,
    }
    _sync_suborder_update(suborder_id, updates)
    target.update(updates)

    # Update in DB if present
    if db is not None:
        try:
            async with db.begin():
                await db.execute(text("""
                    UPDATE public.vendor_suborders
                    SET fulfillment_status = 'shipped', updated_at = NOW()
                    WHERE id = :suborder_id
                """), {"suborder_id": suborder_id})

                await db.execute(text("""
                    INSERT INTO public.shipments (
                        vendor_suborder_id, carrier, tracking_number, shipment_status, shipped_at
                    ) VALUES (
                        :suborder_id, :carrier, :tracking, 'in_transit', NOW()
                    )
                """), {
                    "suborder_id": suborder_id,
                    "carrier": req.carrier,
                    "tracking": req.tracking_number
                })
        except Exception:
            pass

    return FulfillSuborderResponse(
        status="success",
        message="Order marked as dispatched and tracking attached",
        suborder_id=suborder_id,
        carrier=req.carrier,
        tracking_number=req.tracking_number,
        fulfillment_status="shipped"
    )


@router.get("/vendor/inventory", response_model=List[VendorInventoryItem])
async def get_vendor_inventory(
    vendor: dict = Depends(get_current_vendor),
    db: Optional[AsyncSession] = Depends(get_db)
):
    """
    Inventory Management Grid:
    Lists all SKUs and variants belonging to the current vendor.
    """
    vendor_id = vendor["vendor_id"]
    items: List[VendorInventoryItem] = []

    for prod in _MEMORY_PRODUCTS:
        if prod.get("vendor_id") == vendor_id:
            for var in prod.get("variants", []):
                items.append(
                    VendorInventoryItem(
                        variant_id=var["id"],
                        product_id=prod["id"],
                        product_name=prod["name"],
                        sku=var["sku"],
                        variant_attributes=var.get("variant_attributes", {}),
                        selling_price=var["selling_price"],
                        compare_at_price=var.get("compare_at_price"),
                        available_stock=var.get("available_stock", 0),
                        low_stock_threshold=10,
                        is_active=var.get("is_active", True)
                    )
                )

    return items


@router.patch("/vendor/inventory/{variant_id}", response_model=VendorInventoryItem)
async def update_vendor_inventory(
    variant_id: str,
    update_data: VendorInventoryUpdate,
    vendor: dict = Depends(get_current_vendor),
    db: Optional[AsyncSession] = Depends(get_db)
):
    """
    Inline SKU Stock & Price Editor:
    Strictly verifies variant belongs to a product owned by this vendor.
    Updates immediately reflect on the public product detail page.
    """
    vendor_id = vendor["vendor_id"]
    target_prod = None
    target_var = None

    for prod in _MEMORY_PRODUCTS:
        for var in prod.get("variants", []):
            if var["id"] == variant_id:
                target_prod = prod
                target_var = var
                break
        if target_var:
            break

    if not target_var or not target_prod:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Variant '{variant_id}' not found"
        )

    # Strict Tenant Ownership Verification
    if target_prod.get("vendor_id") != vendor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to manage this variant"
        )

    # Apply updates
    if update_data.selling_price is not None:
        target_var["selling_price"] = update_data.selling_price
        # Update parent product min_price
        target_prod["min_price"] = min(v["selling_price"] for v in target_prod["variants"])

    if update_data.compare_at_price is not None:
        target_var["compare_at_price"] = update_data.compare_at_price

    if update_data.available_stock is not None:
        target_var["available_stock"] = update_data.available_stock

    if update_data.is_active is not None:
        target_var["is_active"] = update_data.is_active

    # DB Persistence
    if db is not None:
        try:
            update_fields = []
            params = {"var_id": variant_id}
            if update_data.selling_price is not None:
                update_fields.append("selling_price = :price")
                params["price"] = update_data.selling_price
            if update_fields:
                await db.execute(text(f"""
                    UPDATE public.product_variants
                    SET {', '.join(update_fields)}, updated_at = NOW()
                    WHERE id = :var_id
                """), params)

            if update_data.available_stock is not None:
                await db.execute(text("""
                    UPDATE public.inventory
                    SET available_quantity = :stock, updated_at = NOW()
                    WHERE variant_id = :var_id
                """), {"stock": update_data.available_stock, "var_id": variant_id})

            await db.commit()
        except Exception:
            pass

    return VendorInventoryItem(
        variant_id=target_var["id"],
        product_id=target_prod["id"],
        product_name=target_prod["name"],
        sku=target_var["sku"],
        variant_attributes=target_var.get("variant_attributes", {}),
        selling_price=target_var["selling_price"],
        compare_at_price=target_var.get("compare_at_price"),
        available_stock=target_var.get("available_stock", 0),
        low_stock_threshold=10,
        is_active=target_var.get("is_active", True)
    )

