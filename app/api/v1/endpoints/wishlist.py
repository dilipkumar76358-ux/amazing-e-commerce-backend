from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional, Dict, Any, List
from app.core.database import get_db
from app.core.security import get_current_user
from app.schemas.cart import (
    WishlistItemAddRequest,
    WishlistResponse,
    WishlistItemResponse,
)
from app.api.v1.endpoints.catalog import _MEMORY_PRODUCTS
from app.api.v1.endpoints.cart import _MEMORY_CARTS

router = APIRouter(tags=["Wishlist"])

# In-memory store: user_id -> List of product_ids
_MEMORY_WISHLISTS: Dict[str, List[str]] = {}


def _find_product_in_catalog(product_id: str) -> Optional[Dict[str, Any]]:
    for prod in _MEMORY_PRODUCTS:
        if prod["id"] == product_id:
            return prod
    return None


@router.get("/wishlist", response_model=WishlistResponse)
async def get_wishlist(
    current_user: dict = Depends(get_current_user),
    db: Optional[AsyncSession] = Depends(get_db),
):
    """
    Fetches the authenticated customer's saved Wishlist items.
    """
    user_id = str(current_user["id"])

    # Try DB
    if db is not None:
        try:
            query = text("""
                SELECT wi.id, wi.product_id, wi.created_at,
                       p.name, p.slug, p.average_rating, p.review_count,
                       b.name as brand_name,
                       MIN(pv.selling_price) as min_variant_price,
                       MAX(pv.compare_at_price) as max_compare_price,
                       (SELECT storage_path FROM public.product_images pi WHERE pi.product_id = p.id ORDER BY pi.sort_order ASC LIMIT 1) as primary_image
                FROM public.wishlist_items wi
                JOIN public.wishlists w ON w.id = wi.wishlist_id
                JOIN public.products p ON p.id = wi.product_id
                LEFT JOIN public.brands b ON b.id = p.brand_id
                LEFT JOIN public.product_variants pv ON pv.product_id = p.id AND pv.is_active = TRUE
                WHERE w.user_id = :user_id
                GROUP BY wi.id, p.id, b.name
                ORDER BY wi.created_at DESC;
            """)
            res = await db.execute(query, {"user_id": user_id})
            rows = [dict(r) for r in res.mappings().all()]
            if rows:
                items = [
                    WishlistItemResponse(
                        id=str(r["id"]),
                        product_id=str(r["product_id"]),
                        name=r["name"],
                        slug=r["slug"],
                        brand_name=r.get("brand_name"),
                        average_rating=float(r.get("average_rating") or 0.0),
                        review_count=int(r.get("review_count") or 0),
                        min_variant_price=float(r.get("min_variant_price") or 999.0),
                        max_compare_price=float(r["max_compare_price"]) if r.get("max_compare_price") else None,
                        primary_image=r.get("primary_image"),
                        in_stock=True,
                        created_at=str(r.get("created_at")),
                    )
                    for r in rows
                ]
                return WishlistResponse(
                    wishlist_id=f"wl-{user_id[:8]}",
                    total_items=len(items),
                    items=items,
                )
        except Exception:
            pass

    # In-memory fallback
    saved_ids = _MEMORY_WISHLISTS.get(user_id, [])
    items: List[WishlistItemResponse] = []
    for pid in saved_ids:
        prod = _find_product_in_catalog(pid)
        if prod:
            items.append(
                WishlistItemResponse(
                    id=f"wi-{pid}",
                    product_id=prod["id"],
                    name=prod["name"],
                    slug=prod["slug"],
                    brand_name=prod.get("brand_name"),
                    average_rating=float(prod.get("average_rating") or 4.5),
                    review_count=int(prod.get("review_count") or 100),
                    min_variant_price=float(prod.get("min_price") or 1499.0),
                    max_compare_price=None,
                    primary_image=prod.get("primary_image_url"),
                    in_stock=True,
                )
            )

    return WishlistResponse(
        wishlist_id=f"wl-{user_id[:8]}",
        total_items=len(items),
        items=items,
    )


@router.post("/wishlist/items", status_code=status.HTTP_201_CREATED)
async def add_to_wishlist(
    req: WishlistItemAddRequest,
    current_user: dict = Depends(get_current_user),
    db: Optional[AsyncSession] = Depends(get_db),
):
    """
    Saves a product to the user's wishlist.
    """
    user_id = str(current_user["id"])

    # DB Attempt
    if db is not None:
        try:
            upsert_query = text("""
                WITH user_wishlist AS (
                    INSERT INTO public.wishlists (user_id)
                    VALUES (:user_id)
                    ON CONFLICT (user_id) DO UPDATE SET user_id = EXCLUDED.user_id
                    RETURNING id
                )
                INSERT INTO public.wishlist_items (wishlist_id, product_id)
                SELECT id, :product_id FROM user_wishlist
                ON CONFLICT (wishlist_id, product_id) DO NOTHING;
            """)
            await db.execute(upsert_query, {"user_id": user_id, "product_id": req.product_id})
            await db.commit()
            return {"status": "success", "message": "Product saved to Wishlist"}
        except Exception:
            pass

    # In-Memory
    if user_id not in _MEMORY_WISHLISTS:
        _MEMORY_WISHLISTS[user_id] = []
    if req.product_id not in _MEMORY_WISHLISTS[user_id]:
        _MEMORY_WISHLISTS[user_id].append(req.product_id)

    return {"status": "success", "message": "Product saved to Wishlist"}


@router.delete("/wishlist/items/{product_id}")
async def remove_from_wishlist(
    product_id: str,
    current_user: dict = Depends(get_current_user),
    db: Optional[AsyncSession] = Depends(get_db),
):
    """
    Removes a product from the user's wishlist.
    """
    user_id = str(current_user["id"])

    if db is not None:
        try:
            del_query = text("""
                DELETE FROM public.wishlist_items wi
                USING public.wishlists w
                WHERE wi.wishlist_id = w.id AND w.user_id = :user_id AND wi.product_id = :product_id
            """)
            await db.execute(del_query, {"user_id": user_id, "product_id": product_id})
            await db.commit()
            return {"status": "success", "message": "Product removed from Wishlist"}
        except Exception:
            pass

    if user_id in _MEMORY_WISHLISTS:
        _MEMORY_WISHLISTS[user_id] = [p for p in _MEMORY_WISHLISTS[user_id] if p != product_id]

    return {"status": "success", "message": "Product removed from Wishlist"}


@router.post("/wishlist/items/{product_id}/move-to-cart")
async def move_wishlist_item_to_cart(
    product_id: str,
    current_user: dict = Depends(get_current_user),
    db: Optional[AsyncSession] = Depends(get_db),
):
    """
    Moves an item from Wishlist to Active Cart and removes it from the wishlist.
    """
    user_id = str(current_user["id"])

    # 1. DB Attempt
    if db is not None:
        try:
            var_query = text("""
                SELECT pv.id as variant_id, i.available_quantity
                FROM public.product_variants pv
                JOIN public.inventory i ON i.variant_id = pv.id
                WHERE pv.product_id = :product_id AND pv.is_active = TRUE AND i.available_quantity > 0
                ORDER BY pv.selling_price ASC
                LIMIT 1
            """)
            var_res = await db.execute(var_query, {"product_id": product_id})
            var_row = var_res.mappings().first()

            if var_row:
                variant_id = str(var_row["variant_id"])
                cart_upsert = text("""
                    WITH user_cart AS (
                        INSERT INTO public.carts (user_id, status) VALUES (:user_id, 'active')
                        ON CONFLICT (user_id) DO UPDATE SET updated_at = NOW()
                        RETURNING id
                    )
                    INSERT INTO public.cart_items (cart_id, variant_id, quantity)
                    SELECT id, :variant_id, 1 FROM user_cart
                    ON CONFLICT (cart_id, variant_id)
                    DO UPDATE SET quantity = cart_items.quantity + 1, updated_at = NOW();
                """)
                await db.execute(cart_upsert, {"user_id": user_id, "variant_id": variant_id})

                del_wl = text("""
                    DELETE FROM public.wishlist_items wi
                    USING public.wishlists w
                    WHERE wi.wishlist_id = w.id AND w.user_id = :user_id AND wi.product_id = :product_id
                """)
                await db.execute(del_wl, {"user_id": user_id, "product_id": product_id})
                await db.commit()
                return {"status": "success", "message": "Item moved to cart"}
        except Exception:
            pass

    # 2. In-Memory Fallback: Locate product & first active variant
    prod = _find_product_in_catalog(product_id)
    if not prod or not prod.get("variants"):
        raise HTTPException(status_code=404, detail="Product variant not found")

    variant = prod["variants"][0]
    variant_id = variant["id"]

    # Add to cart
    if user_id not in _MEMORY_CARTS:
        _MEMORY_CARTS[user_id] = []
    cart_items = _MEMORY_CARTS[user_id]
    existing = next((i for i in cart_items if i["variant_id"] == variant_id), None)
    if existing:
        existing["quantity"] += 1
    else:
        cart_items.append({
            "item_id": f"ci-{variant_id}-wl",
            "variant_id": variant_id,
            "quantity": 1,
        })

    # Remove from wishlist
    if user_id in _MEMORY_WISHLISTS:
        _MEMORY_WISHLISTS[user_id] = [p for p in _MEMORY_WISHLISTS[user_id] if p != product_id]

    return {"status": "success", "message": "Item moved to cart"}
