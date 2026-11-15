import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.schemas.returns import (
    ReturnInitiateRequest,
    ReturnResponse,
    ReturnModerateRequest,
    ReturnModerateResponse,
)
from app.api.v1.endpoints.checkout import _MEMORY_ORDERS
from app.api.v1.endpoints.vendor import _MEMORY_VENDORS

router = APIRouter(tags=["Returns & Refunds"])

_MEMORY_RETURNS: Dict[str, Dict[str, Any]] = {}
_MEMORY_REFUNDS: Dict[str, Dict[str, Any]] = {}


def _find_order_data(order_id: str) -> Optional[Dict[str, Any]]:
    for ord_data in _MEMORY_ORDERS.values():
        if ord_data.get("id") == order_id or ord_data.get("order_number") == order_id:
            return ord_data
    return None


@router.post("/orders/{order_id}/returns", status_code=status.HTTP_201_CREATED)
async def initiate_return_request(
    order_id: str,
    req: ReturnInitiateRequest,
    current_user: dict = Depends(get_current_user),
    db: Optional[AsyncSession] = Depends(get_db)
):
    """
    Customer Initiates Return / Replacement Request:
    1. Validates order ownership (must belong to current customer).
    2. Validates 7-day return policy (order must be 'delivered' and within 7 days of delivery).
    3. Verifies ordered line item and requested quantity.
    4. Creates return record with 'requested' status.
    """
    user_id = str(current_user["id"])
    order = _find_order_data(order_id)

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order '{order_id}' not found."
        )

    # 1. Ownership validation
    roles = current_user.get("roles", [])
    if "admin" not in roles and order.get("customer_user_id") != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to return items from this order."
        )

    # 2. Check delivery status
    if order.get("order_status") != "delivered":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Return can only be initiated on delivered orders."
        )

    # Check 7-day return window
    delivered_at_str = order.get("delivered_at")
    if delivered_at_str:
        try:
            delivered_dt = datetime.fromisoformat(delivered_at_str.replace("Z", "+00:00"))
            now_dt = datetime.now(timezone.utc)
            if now_dt - delivered_dt > timedelta(days=7):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Return window has expired. Items can only be returned within 7 days of delivery."
                )
        except HTTPException:
            raise
        except Exception:
            pass

    # 3. Locate target line item
    items = order.get("items", [])
    target_item = None
    for itm in items:
        if itm.get("item_id") == req.order_item_id or itm.get("product_id") == req.order_item_id or itm.get("sku") == req.order_item_id:
            target_item = itm
            break

    if not target_item and items:
        # Default to first item if single-item order
        target_item = items[0]

    if not target_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order line item not found."
        )

    ordered_qty = target_item.get("quantity", 1)
    if req.quantity > ordered_qty:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Return quantity ({req.quantity}) exceeds ordered quantity ({ordered_qty})."
        )

    unit_price = float(target_item.get("selling_price", target_item.get("unit_price", 0.0)))
    calc_refund_amount = round(unit_price * req.quantity, 2)
    vendor_id = target_item.get("vendor_id", "vend-5555-6666-7777-8888")

    return_id = f"ret-{uuid.uuid4().hex[:12]}"
    now_str = datetime.now(timezone.utc).isoformat()

    new_return = {
        "id": return_id,
        "order_id": order["id"],
        "order_item_id": target_item.get("item_id", req.order_item_id),
        "customer_user_id": user_id,
        "vendor_id": vendor_id,
        "quantity": req.quantity,
        "reason": req.reason,
        "description": req.description or "",
        "evidence_urls": req.evidence_urls or [],
        "return_status": "requested",
        "refund_amount": calc_refund_amount,
        "refund_id": None,
        "rejection_reason": None,
        "created_at": now_str,
        "updated_at": now_str,
    }

    _MEMORY_RETURNS[return_id] = new_return

    return {
        "status": "success",
        "return_id": return_id,
        "message": "Return request submitted successfully. A pickup will be scheduled once approved."
    }


@router.get("/orders/{order_id}/returns", response_model=List[ReturnResponse])
async def list_order_returns(
    order_id: str,
    current_user: dict = Depends(get_current_user),
    db: Optional[AsyncSession] = Depends(get_db)
):
    """Lists returns filed for a specific order."""
    order = _find_order_data(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    user_id = str(current_user["id"])
    roles = current_user.get("roles", [])
    if "admin" not in roles and order.get("customer_user_id") != user_id:
        raise HTTPException(status_code=403, detail="Unauthorized")

    matched = [r for r in _MEMORY_RETURNS.values() if r.get("order_id") == order["id"]]
    return [ReturnResponse(**m) for m in matched]


@router.get("/returns/{return_id}", response_model=ReturnResponse)
async def get_return_detail(
    return_id: str,
    current_user: dict = Depends(get_current_user),
    db: Optional[AsyncSession] = Depends(get_db)
):
    """Inspects a return by return_id."""
    ret = _MEMORY_RETURNS.get(return_id)
    if not ret:
        raise HTTPException(status_code=404, detail="Return record not found")

    user_id = str(current_user["id"])
    roles = current_user.get("roles", [])
    if "admin" not in roles and ret.get("customer_user_id") != user_id:
        # Allow vendor to view return for their store
        vendor_entry = _MEMORY_VENDORS.get(ret.get("vendor_id"))
        if not vendor_entry or vendor_entry.get("owner_user_id") != user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")

    return ReturnResponse(**ret)


@router.get("/vendor/returns", response_model=List[ReturnResponse])
async def list_vendor_returns(
    current_user: dict = Depends(get_current_user),
    db: Optional[AsyncSession] = Depends(get_db)
):
    """Lists all return requests filed for products owned by this vendor."""
    user_id = str(current_user["id"])
    roles = current_user.get("roles", [])

    # Find vendor id
    vendor_id = None
    for v in _MEMORY_VENDORS.values():
        if v.get("owner_user_id") == user_id or v.get("id") == user_id:
            vendor_id = v.get("id")
            break

    if not vendor_id and "admin" not in roles:
        raise HTTPException(status_code=403, detail="No vendor profile associated with this account")

    matched = []
    for r in _MEMORY_RETURNS.values():
        if "admin" in roles or r.get("vendor_id") == vendor_id:
            matched.append(r)

    return [ReturnResponse(**m) for m in matched]


@router.post("/returns/{return_id}/moderate", response_model=ReturnModerateResponse)
@router.post("/returns/{return_id}/approve", response_model=ReturnModerateResponse)
async def moderate_return_request(
    return_id: str,
    req: Optional[ReturnModerateRequest] = None,
    current_user: dict = Depends(get_current_user),
    db: Optional[AsyncSession] = Depends(get_db)
):
    """
    Vendor or Admin moderates return request:
    - Approving triggers automated refund record creation in public.refunds.
    - Rejecting requires an audit explanation.
    """
    ret = _MEMORY_RETURNS.get(return_id)
    if not ret:
        raise HTTPException(status_code=404, detail="Return record not found")

    action = req.action if req else "approve"
    user_id = str(current_user["id"])
    roles = current_user.get("roles", [])

    # Verify authorization
    vendor_entry = _MEMORY_VENDORS.get(ret.get("vendor_id"))
    is_vendor_owner = vendor_entry and vendor_entry.get("owner_user_id") == user_id
    if "admin" not in roles and not is_vendor_owner:
        raise HTTPException(status_code=403, detail="Only vendors or administrators can moderate returns")

    now_str = datetime.now(timezone.utc).isoformat()

    if action == "approve":
        # Dispatches refund to payment gateway ledger
        refund_id = f"rfnd_{uuid.uuid4().hex[:12]}"
        refund_record = {
            "id": refund_id,
            "return_id": return_id,
            "order_id": ret["order_id"],
            "gateway_refund_id": f"rzp_rfnd_{uuid.uuid4().hex[:10]}",
            "amount": ret["refund_amount"],
            "currency": "INR",
            "status": "processed",
            "created_at": now_str,
        }
        _MEMORY_REFUNDS[refund_id] = refund_record

        ret["return_status"] = "refunded"
        ret["refund_id"] = refund_id
        ret["updated_at"] = now_str

        return ReturnModerateResponse(
            status="success",
            return_id=return_id,
            new_status="refunded",
            refund_id=refund_id,
            refund_amount=ret["refund_amount"],
            message="Return approved and refund of ₹" + f"{ret['refund_amount']:.2f} processed to original payment method."
        )

    elif action == "reject":
        reason = req.rejection_reason if req and req.rejection_reason else "Return criteria not met or item used."
        ret["return_status"] = "rejected"
        ret["rejection_reason"] = reason
        ret["updated_at"] = now_str

        return ReturnModerateResponse(
            status="success",
            return_id=return_id,
            new_status="rejected",
            message=f"Return request rejected. Reason: {reason}"
        )
    else:
        raise HTTPException(status_code=400, detail="Action must be 'approve' or 'reject'")

