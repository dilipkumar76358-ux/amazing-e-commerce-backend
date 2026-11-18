from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional, Dict, Any
from app.core.database import get_db
from app.core.security import get_customer_or_guest_user
from app.schemas.checkout import CouponValidateRequest, CouponValidateResponse

router = APIRouter(tags=["Coupons & Discounts"])

# Standard in-memory coupon definitions for testing and fallback
_MEMORY_COUPONS: Dict[str, Dict[str, Any]] = {
    "WELCOME100": {
        "code": "WELCOME100",
        "description": "Flat ₹100 off on your first order",
        "discount_type": "fixed",
        "discount_value": 100.0,
        "min_order_amount": 499.0,
        "max_discount_amount": None,
        "is_active": True,
    },
    "AMAZING50": {
        "code": "AMAZING50",
        "description": "Flat ₹50 off on orders above ₹299",
        "discount_type": "fixed",
        "discount_value": 50.0,
        "min_order_amount": 299.0,
        "max_discount_amount": None,
        "is_active": True,
    },
    "FESTIVE10": {
        "code": "FESTIVE10",
        "description": "10% instant discount up to ₹500",
        "discount_type": "percentage",
        "discount_value": 10.0,
        "min_order_amount": 999.0,
        "max_discount_amount": 500.0,
        "is_active": True,
    },
}


def calculate_coupon_discount(coupon: Dict[str, Any], subtotal: float) -> float:
    """Calculates deterministic discount based on rule type and threshold."""
    if subtotal < float(coupon.get("min_order_amount", 0)):
        return 0.0

    d_type = coupon.get("discount_type", "fixed")
    val = float(coupon.get("discount_value", 0))

    if d_type == "percentage":
        discount = (val / 100.0) * subtotal
        max_d = coupon.get("max_discount_amount")
        if max_d is not None and float(max_d) > 0:
            discount = min(discount, float(max_d))
    else:
        discount = val

    return round(min(discount, subtotal), 2)


@router.post("/coupons/validate", response_model=CouponValidateResponse)
async def validate_coupon(
    req: CouponValidateRequest,
    current_user: dict = Depends(get_customer_or_guest_user),
    db: Optional[AsyncSession] = Depends(get_db)
):
    """
    Validates promotional discount code against cart subtotal, minimum spend requirements,
    and returns verified discount amount.
    """
    code_upper = req.code.strip().upper()

    # 1. Try DB
    if db is not None:
        try:
            q = text("""
                SELECT code, description, discount_type, discount_value,
                       min_order_amount, max_discount_amount, is_active
                FROM public.coupons
                WHERE UPPER(code) = :code AND is_active = TRUE
            """)
            res = await db.execute(q, {"code": code_upper})
            row = res.mappings().first()
            if row:
                c_data = dict(row)
                min_spend = float(c_data.get("min_order_amount") or 0.0)
                if req.cart_subtotal < min_spend:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Coupon '{code_upper}' requires a minimum order subtotal of ₹{min_spend:.2f}."
                    )
                discount = calculate_coupon_discount(c_data, req.cart_subtotal)
                new_sub = max(0.0, round(req.cart_subtotal - discount, 2))
                return CouponValidateResponse(
                    code=code_upper,
                    is_valid=True,
                    discount_amount=discount,
                    new_subtotal=new_sub,
                    message=f"Coupon '{code_upper}' applied successfully! Saved ₹{discount:.2f}."
                )
        except HTTPException:
            raise
        except Exception:
            pass

    # 2. In-memory validation
    coupon = _MEMORY_COUPONS.get(code_upper)
    if not coupon or not coupon.get("is_active"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Coupon code '{code_upper}' is invalid or expired."
        )

    min_spend = float(coupon.get("min_order_amount", 0.0))
    if req.cart_subtotal < min_spend:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Coupon '{code_upper}' requires a minimum order subtotal of ₹{min_spend:.2f}."
        )

    discount = calculate_coupon_discount(coupon, req.cart_subtotal)
    new_sub = max(0.0, round(req.cart_subtotal - discount, 2))

    return CouponValidateResponse(
        code=code_upper,
        is_valid=True,
        discount_amount=discount,
        new_subtotal=new_sub,
        message=f"Coupon '{code_upper}' applied successfully! Saved ₹{discount:.2f}."
    )
