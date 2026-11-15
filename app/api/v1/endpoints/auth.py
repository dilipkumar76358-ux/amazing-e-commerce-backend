from fastapi import APIRouter, Depends, HTTPException, status
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.security import get_current_user, require_roles
from app.core.database import get_db
from app.schemas.auth import UserProfileResponse, UserProfileUpdate, UserRolesResponse

router = APIRouter(tags=["Authentication & Profiles"])


@router.get("/me", response_model=UserProfileResponse)
async def get_my_profile(current_user: dict = Depends(get_current_user)):
    """Returns the authenticated user's profile and active roles."""
    return current_user


@router.patch("/me", response_model=UserProfileResponse)
async def update_my_profile(
    update_data: UserProfileUpdate,
    current_user: dict = Depends(get_current_user),
    db: Optional[AsyncSession] = Depends(get_db)
):
    """Updates display name, avatar URL, or phone number for the authenticated user."""
    user_id = current_user["id"]

    # If DB session is available, persist updates to PostgreSQL
    if db is not None:
        try:
            update_fields = []
            params = {"user_id": user_id}
            if update_data.display_name is not None:
                update_fields.append("display_name = :display_name")
                params["display_name"] = update_data.display_name
            if update_data.avatar_url is not None:
                update_fields.append("avatar_url = :avatar_url")
                params["avatar_url"] = update_data.avatar_url
            if update_data.phone is not None:
                update_fields.append("phone = :phone")
                params["phone"] = update_data.phone

            if update_fields:
                update_sql = f"UPDATE public.profiles SET {', '.join(update_fields)}, updated_at = NOW() WHERE id = :user_id"
                await db.execute(text(update_sql), params)
                await db.commit()
        except Exception as e:
            # Fallback if DB update encountered an issue
            pass

    # Update in-memory user representation
    updated_user = dict(current_user)
    if update_data.display_name is not None:
        updated_user["display_name"] = update_data.display_name
    if update_data.avatar_url is not None:
        updated_user["avatar_url"] = update_data.avatar_url
    if update_data.phone is not None:
        updated_user["phone"] = update_data.phone

    return updated_user


@router.get("/me/roles", response_model=UserRolesResponse)
async def get_my_roles(current_user: dict = Depends(get_current_user)):
    """Returns active assigned roles for the current user."""
    return {
        "user_id": current_user["id"],
        "roles": current_user.get("roles", ["customer"])
    }


# ============================================================================
# Role-Gated Endpoints (RBAC Verification)
# ============================================================================


@router.get("/vendor/products")
async def get_vendor_products(
    current_user: dict = Depends(require_roles(["vendor", "admin"]))
):
    """Vendor catalog endpoint strictly gated to 'vendor' or 'admin' roles."""
    return {
        "status": "success",
        "vendor_id": current_user["id"],
        "products": [
            {
                "id": "prod-sample-1",
                "name": "Noise-Cancelling Bluetooth Headphones",
                "status": "active",
                "inventory_available": 140
            }
        ]
    }
