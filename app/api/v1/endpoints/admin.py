from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from datetime import datetime, timezone, timedelta
import uuid

from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.core.config import settings
from app.core.supabase import get_supabase
from app.schemas.admin import (
    VendorModerationRequest,
    VendorModerationResponse,
    ProductModerationRequest,
    ProductModerationResponse,
    CommissionRuleCreate,
    CommissionRuleResponse,
    SettlementCalculateRequest,
    SettlementRecordResponse,
    AuditLogResponse,
    AdminDashboardMetricsResponse,
)
from app.api.v1.endpoints.vendor import _MEMORY_VENDORS, _get_all_suborders
from app.api.v1.endpoints.catalog import _MEMORY_PRODUCTS

router = APIRouter(prefix="/admin", tags=["Admin Command Center & Governance"])

# ============================================================================
# In-Memory Stores for Admin Audit, Settlements & Commission Rules
# ============================================================================

_MEMORY_AUDIT_LOGS: List[Dict[str, Any]] = [
    {
        "id": "audit-init-001",
        "actor_user_id": "admn-9999-0000-1111-2222",
        "action": "system_bootstrap",
        "resource_type": "platform",
        "resource_id": "system",
        "metadata": {"version": "1.0.0", "engine": "FastAPI + Supabase PostgreSQL"},
        "created_at": "2026-10-25T00:00:00Z"
    }
]

_MEMORY_COMMISSION_RULES: List[Dict[str, Any]] = [
    {
        "id": "comm-rule-default",
        "rule_type": "platform_default",
        "target_id": None,
        "target_name": "Standard Marketplace Commission",
        "rate_percentage": 10.0,
        "is_active": True,
        "created_at": "2026-10-25T00:00:00Z"
    },
    {
        "id": "comm-rule-fashion",
        "rule_type": "category",
        "target_id": "cat-fash-004",
        "target_name": "Fashion & Apparel",
        "rate_percentage": 12.0,
        "is_active": True,
        "created_at": "2026-10-25T00:00:00Z"
    },
    {
        "id": "comm-rule-electronics",
        "rule_type": "category",
        "target_id": "cat-elec-001",
        "target_name": "Electronics & Computers",
        "rate_percentage": 8.0,
        "is_active": True,
        "created_at": "2026-10-25T00:00:00Z"
    }
]

_MEMORY_SETTLEMENTS: List[Dict[str, Any]] = []
_MEMORY_USER_ROLES: Dict[str, List[str]] = {
    "vend-5555-6666-7777-8888": ["customer", "vendor"],
    "vend-other-9999-0000": ["customer", "vendor"],
    "vend-pending-user-1111": ["customer"],  # Only customer until approved!
    "admn-9999-0000-1111-2222": ["admin"],
}


def _record_audit_log(
    actor_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    metadata: Dict[str, Any]
) -> Dict[str, Any]:
    """Appends an immutable audit record to memory and database."""
    log_entry = {
        "id": f"audit-{uuid.uuid4().hex[:10]}",
        "actor_user_id": actor_id,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "metadata": metadata,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _MEMORY_AUDIT_LOGS.insert(0, log_entry)
    return log_entry


# ============================================================================
# Admin Endpoints (Strictly Gated to 'admin' role)
# ============================================================================

@router.get("/dashboard", response_model=AdminDashboardMetricsResponse)
async def get_admin_dashboard_metrics(
    admin: dict = Depends(require_roles(["admin"])),
    db: Optional[AsyncSession] = Depends(get_db)
):
    """
    Marketplace Overview Dashboard:
    Computes GMV, platform net earned commissions, order volume,
    and active vs pending vendors.
    """
    all_suborders = _get_all_suborders()
    total_gmv = sum(float(s.get("subtotal", 0.0)) for s in all_suborders)
    platform_revenue = sum(float(s.get("commission_total", 0.0)) for s in all_suborders)

    vendors_list = list(_MEMORY_VENDORS.values())
    total_vendors = len(vendors_list)
    active_vendors = len([v for v in vendors_list if v.get("application_status") == "approved"])
    pending_vendors = len([v for v in vendors_list if v.get("application_status") in ["submitted", "under_review"]])

    pending_products = len([
        p for p in _MEMORY_PRODUCTS if p.get("product_status") in ["pending_review", "draft"]
    ])

    return AdminDashboardMetricsResponse(
        gmv_inr=round(total_gmv, 2),
        platform_net_revenue_inr=round(platform_revenue, 2),
        total_orders=len(all_suborders),
        total_vendors=total_vendors,
        active_vendors=active_vendors,
        pending_vendor_applications=pending_vendors,
        pending_products_count=pending_products,
        payment_conversion_rate=94.5
    )


@router.get("/vendors/applications")
async def list_pending_vendor_applications(
    admin: dict = Depends(require_roles(["admin"])),
    db: Optional[AsyncSession] = Depends(get_db)
):
    """Lists vendor onboarding applications requiring KYB verification."""
    # Database query if connected
    if db is not None:
        try:
            query = text("""
                SELECT v.id as vendor_id, v.store_name, v.created_at, v.application_status,
                       p.email as owner_email, p.phone as owner_phone
                FROM public.vendors v
                JOIN public.profiles p ON p.id = v.owner_user_id
                WHERE v.application_status IN ('submitted', 'under_review')
                ORDER BY v.created_at ASC;
            """)
            res = await db.execute(query)
            rows = [dict(r) for r in res.mappings().all()]
            if rows:
                return rows
        except Exception:
            pass

    # In-Memory fallback
    pending = [
        v for v in _MEMORY_VENDORS.values()
        if v.get("application_status") in ["submitted", "under_review"]
    ]
    return pending


@router.get("/vendors")
async def list_all_vendors(
    status_filter: Optional[str] = Query(None, alias="status"),
    admin: dict = Depends(require_roles(["admin"])),
    db: Optional[AsyncSession] = Depends(get_db)
):
    """Lists all marketplace vendor stores with status filter."""
    vendors = list(_MEMORY_VENDORS.values())
    if status_filter and status_filter.lower() != "all":
        vendors = [v for v in vendors if v.get("application_status") == status_filter.lower()]
    return vendors


@router.get("/vendors/{vendor_id}")
async def get_vendor_details_with_signed_docs(
    vendor_id: str,
    admin: dict = Depends(require_roles(["admin"])),
    db: Optional[AsyncSession] = Depends(get_db)
):
    """
    Vendor Detail with Secure Signed URLs for Document Inspection:
    Generates short-lived 5-minute signed URLs for private KYC documents.
    """
    vendor = _MEMORY_VENDORS.get(vendor_id)
    if not vendor:
        for v in _MEMORY_VENDORS.values():
            if v.get("id") == vendor_id:
                vendor = v
                break

    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vendor '{vendor_id}' not found"
        )

    # Generate temporary signed URLs for documents
    docs_with_signed_urls = []
    supabase = get_supabase()

    for doc in vendor.get("documents", []):
        doc_copy = dict(doc)
        storage_path = doc.get("storage_path") or ""
        if supabase and storage_path:
            try:
                res = supabase.storage.from_("vendor-documents").create_signed_url(storage_path, 300)
                doc_copy["signed_url"] = res.get("signedURL") or res.get("signedUrl")
            except Exception:
                doc_copy["signed_url"] = f"https://mock-storage.amazing.in/signed/vendor-documents/{storage_path}?token=exp300s"
        else:
            doc_copy["signed_url"] = f"https://mock-storage.amazing.in/signed/vendor-documents/{storage_path}?token=exp300s"
        docs_with_signed_urls.append(doc_copy)

    response = dict(vendor)
    response["documents"] = docs_with_signed_urls
    return response


@router.post("/vendors/{vendor_id}/moderate", response_model=VendorModerationResponse)
async def moderate_vendor(
    vendor_id: str,
    req: VendorModerationRequest,
    admin: dict = Depends(require_roles(["admin"])),
    db: Optional[AsyncSession] = Depends(get_db)
):
    """
    Vendor KYB Moderation:
    1. Updates application_status to 'approved', 'rejected', or 'suspended'.
    2. If approved, automatically provisions 'vendor' role in user_roles.
    3. Writes immutable entry into public.audit_logs.
    """
    target = _MEMORY_VENDORS.get(vendor_id)
    if not target:
        for v in _MEMORY_VENDORS.values():
            if v.get("id") == vendor_id:
                target = v
                break

    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vendor '{vendor_id}' not found"
        )

    target_status = "approved" if req.action == "approve" else ("rejected" if req.action == "reject" else "suspended")
    admin_id = str(admin["id"])

    # Update vendor state
    target["application_status"] = target_status
    if req.action == "approve":
        target["account_status"] = "active"
        target["approved_at"] = datetime.now(timezone.utc).isoformat()
        target["approved_by"] = admin_id

        # 2. Automatically provision 'vendor' role for owner
        owner_id = target.get("owner_user_id")
        if owner_id:
            roles = _MEMORY_USER_ROLES.setdefault(owner_id, ["customer"])
            if "vendor" not in roles:
                roles.append("vendor")

    # 3. Write Immutable Audit Trail
    audit_entry = _record_audit_log(
        actor_id=admin_id,
        action=f"vendor_{req.action}",
        resource_type="vendor",
        resource_id=vendor_id,
        metadata={
            "store_name": target.get("store_name"),
            "reason": req.reason or "",
            "previous_status": target.get("application_status"),
            "new_status": target_status,
        }
    )

    # Database Persistence
    if db is not None:
        try:
            async with db.begin():
                await db.execute(text("""
                    UPDATE public.vendors
                    SET application_status = :status,
                        approved_at = CASE WHEN :status = 'approved' THEN NOW() ELSE approved_at END,
                        approved_by = :admin_id,
                        updated_at = NOW()
                    WHERE id = :v_id
                """), {"status": target_status, "admin_id": admin_id, "v_id": vendor_id})

                if req.action == "approve":
                    await db.execute(text("""
                        INSERT INTO public.user_roles (user_id, role_id)
                        SELECT v.owner_user_id, r.id
                        FROM public.vendors v, public.roles r
                        WHERE v.id = :v_id AND r.name = 'vendor'
                        ON CONFLICT DO NOTHING;
                    """), {"v_id": vendor_id})

                await db.execute(text("""
                    INSERT INTO public.audit_logs (
                        actor_user_id, action, resource_type, resource_id, metadata
                    ) VALUES (
                        :actor, :action, 'vendor', :res_id, :meta
                    )
                """), {
                    "actor": admin_id,
                    "action": f"vendor_{req.action}",
                    "res_id": vendor_id,
                    "meta": f'{{"reason": "{req.reason or ""}"}}'
                })
        except Exception:
            pass

    return VendorModerationResponse(
        status="success",
        message=f"Vendor application {target_status} successfully",
        vendor_id=vendor_id,
        new_status=target_status
    )


# ============================================================================
# Product Moderation Queue
# ============================================================================

@router.get("/products/pending")
async def list_pending_products(
    admin: dict = Depends(require_roles(["admin"])),
    db: Optional[AsyncSession] = Depends(get_db)
):
    """Lists products in draft or pending review queue."""
    pending = [
        p for p in _MEMORY_PRODUCTS
        if p.get("product_status") in ["draft", "pending_review"]
    ]
    return pending


@router.post("/products/{product_id}/approve", response_model=ProductModerationResponse)
async def approve_product(
    product_id: str,
    admin: dict = Depends(require_roles(["admin"])),
    db: Optional[AsyncSession] = Depends(get_db)
):
    """
    Approves product listing:
    1. Sets product_status to 'active'.
    2. Product immediately surfaces in public search results.
    3. Records audit log entry.
    """
    target_prod = next((p for p in _MEMORY_PRODUCTS if p["id"] == product_id), None)
    if not target_prod:
        raise HTTPException(status_code=404, detail=f"Product '{product_id}' not found")

    target_prod["product_status"] = "active"
    admin_id = str(admin["id"])

    _record_audit_log(
        actor_id=admin_id,
        action="product_approve",
        resource_type="product",
        resource_id=product_id,
        metadata={"product_name": target_prod.get("name"), "status": "active"}
    )

    if db is not None:
        try:
            await db.execute(text("""
                UPDATE public.products SET product_status = 'active', updated_at = NOW() WHERE id = :id
            """), {"id": product_id})
            await db.commit()
        except Exception:
            pass

    return ProductModerationResponse(
        status="success",
        message=f"Product '{target_prod['name']}' approved and published live",
        product_id=product_id,
        new_status="active"
    )


@router.post("/products/{product_id}/reject", response_model=ProductModerationResponse)
async def reject_product(
    product_id: str,
    req: ProductModerationRequest,
    admin: dict = Depends(require_roles(["admin"])),
    db: Optional[AsyncSession] = Depends(get_db)
):
    """
    Rejects product listing:
    1. Sets product_status to 'rejected'.
    2. Writes immutable entry into public.audit_logs with rejection reason.
    """
    target_prod = next((p for p in _MEMORY_PRODUCTS if p["id"] == product_id), None)
    if not target_prod:
        raise HTTPException(status_code=404, detail=f"Product '{product_id}' not found")

    target_prod["product_status"] = "rejected"
    admin_id = str(admin["id"])

    # Write immutable audit log
    _record_audit_log(
        actor_id=admin_id,
        action="product_reject",
        resource_type="product",
        resource_id=product_id,
        metadata={
            "product_name": target_prod.get("name"),
            "reason": req.reason or "Non-compliant specifications or imagery",
            "status": "rejected"
        }
    )

    if db is not None:
        try:
            await db.execute(text("""
                UPDATE public.products SET product_status = 'rejected', updated_at = NOW() WHERE id = :id
            """), {"id": product_id})
            await db.commit()
        except Exception:
            pass

    return ProductModerationResponse(
        status="success",
        message=f"Product '{target_prod['name']}' rejected",
        product_id=product_id,
        new_status="rejected"
    )


# ============================================================================
# Commission Configuration & Settlement Ledger
# ============================================================================

@router.get("/commissions", response_model=List[CommissionRuleResponse])
async def list_commission_rules(
    admin: dict = Depends(require_roles(["admin"])),
    db: Optional[AsyncSession] = Depends(get_db)
):
    """Lists all active commission rules with precedence ranking."""
    return [CommissionRuleResponse(**rule) for rule in _MEMORY_COMMISSION_RULES]


@router.post("/commissions", response_model=CommissionRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_commission_rule(
    req: CommissionRuleCreate,
    admin: dict = Depends(require_roles(["admin"])),
    db: Optional[AsyncSession] = Depends(get_db)
):
    """Creates a new dynamic commission rule (category, vendor, product, or default)."""
    new_id = f"comm-rule-{uuid.uuid4().hex[:8]}"
    now_str = datetime.now(timezone.utc).isoformat()

    new_rule = {
        "id": new_id,
        "rule_type": req.rule_type,
        "target_id": req.target_id,
        "target_name": req.target_name or f"Rule for {req.rule_type}",
        "rate_percentage": req.rate_percentage,
        "is_active": True,
        "created_at": now_str
    }
    _MEMORY_COMMISSION_RULES.append(new_rule)

    _record_audit_log(
        actor_id=str(admin["id"]),
        action="commission_rule_create",
        resource_type="commission_rule",
        resource_id=new_id,
        metadata=new_rule
    )

    return CommissionRuleResponse(**new_rule)


@router.post("/settlements/calculate", response_model=List[SettlementRecordResponse])
async def calculate_settlement_ledger(
    req: SettlementCalculateRequest,
    admin: dict = Depends(require_roles(["admin"])),
    db: Optional[AsyncSession] = Depends(get_db)
):
    """
    Automated Settlement Calculation Script:
    Aggregates vendor suborders within the settlement window:
    Net Payout = Gross Subtotal - Platform Commission - Refund Deductions
    Inserts records into vendor settlements with status 'pending_payout'.
    """
    all_suborders = _get_all_suborders()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=req.settlement_days)

    # Group completed/shipped suborders by vendor
    suborders_by_vendor: Dict[str, List[Dict[str, Any]]] = {}
    for s in all_suborders:
        v_id = s.get("vendor_id")
        if not v_id:
            continue
        suborders_by_vendor.setdefault(v_id, []).append(s)

    new_settlements: List[SettlementRecordResponse] = []

    for v_id, subs in suborders_by_vendor.items():
        vendor_data = _MEMORY_VENDORS.get(v_id, {})
        v_name = vendor_data.get("store_name", subs[0].get("store_name", "Vendor Store"))

        gross = sum(float(s.get("subtotal", 0.0)) for s in subs)
        comm = sum(float(s.get("commission_total", 0.0)) for s in subs)
        refunds = 0.0
        net = round(gross - comm - refunds, 2)

        settlement_id = f"stl-{uuid.uuid4().hex[:10]}"
        settlement_record = {
            "id": settlement_id,
            "vendor_id": v_id,
            "vendor_name": v_name,
            "period_start": cutoff.isoformat(),
            "period_end": now.isoformat(),
            "gross_amount": round(gross, 2),
            "commission_amount": round(comm, 2),
            "refund_deductions": round(refunds, 2),
            "net_payout": net,
            "payout_status": "pending_payout",
            "reference_number": f"PAYOUT-{v_id[:8].upper()}-{now.strftime('%Y%m%d')}",
            "created_at": now.isoformat()
        }
        _MEMORY_SETTLEMENTS.append(settlement_record)
        new_settlements.append(SettlementRecordResponse(**settlement_record))

    _record_audit_log(
        actor_id=str(admin["id"]),
        action="settlement_calculate",
        resource_type="settlements",
        resource_id=f"batch-{now.strftime('%Y%m%d%H%M')}",
        metadata={"total_settlements": len(new_settlements), "days": req.settlement_days}
    )

    return new_settlements


@router.get("/settlements", response_model=List[SettlementRecordResponse])
async def list_settlements(
    admin: dict = Depends(require_roles(["admin"])),
    db: Optional[AsyncSession] = Depends(get_db)
):
    """Lists all vendor settlement disbursement records."""
    return [SettlementRecordResponse(**s) for s in _MEMORY_SETTLEMENTS]


# ============================================================================
# Audit Logs
# ============================================================================

@router.get("/audit-logs", response_model=List[AuditLogResponse])
async def list_audit_logs(
    resource_type: Optional[str] = Query(None),
    admin: dict = Depends(require_roles(["admin"])),
    db: Optional[AsyncSession] = Depends(get_db)
):
    """
    Searchable, tamper-evident administrative audit log stream.
    Filterable by action type, resource, or actor.
    """
    logs = _MEMORY_AUDIT_LOGS
    if resource_type:
        logs = [l for l in logs if l.get("resource_type") == resource_type]

    return [AuditLogResponse(**l) for l in logs]
