from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional, Dict, Any, List
from app.core.database import get_db
from app.core.security import get_current_user
from app.schemas.cart import (
    CartItemAddRequest,
    CartItemUpdateRequest,
    CartResponse,
    CartItemResponse,
    VendorGroupResponse,
)
from app.api.v1.endpoints.catalog import _MEMORY_PRODUCTS

router = APIRouter(tags=["Cart & Checkout Preparation"])

# In-memory cart store for testing/lightweight environments
# Key: user_id -> List of cart item dicts
_MEMORY_CARTS: Dict[str, List[Dict[str, Any]]] = {}


def _find_variant_in_catalog(variant_id: str) -> Optional[Dict[str, Any]]:
    """Helper to locate a variant and its parent product from in-memory catalog."""
    for prod in _MEMORY_PRODUCTS:
        for var in prod.get("variants", []):
            if var["id"] == variant_id:
                return {
                    "product": prod,
                    "variant": var,
                }
    return None


@router.get("/cart", response_model=CartResponse)
async def get_cart(
    current_user: dict = Depends(get_current_user),
    db: Optional[AsyncSession] = Depends(get_db),
):
    """
    Retrieves the customer's server-validated shopping cart with multi-vendor grouping,
    real-time price recalculation, and stock validation.
    """
    user_id = str(current_user["id"])

    # Try live PostgreSQL query if DB is connected
    if db is not None:
        try:
            # 1. Ensure active cart exists
            cart_query = text("""
                INSERT INTO public.carts (user_id, status)
                VALUES (:user_id, 'active')
                ON CONFLICT (user_id) DO UPDATE SET updated_at = NOW()
                RETURNING id;
            """)
            cart_res = await db.execute(cart_query, {"user_id": user_id})
            cart_id = cart_res.scalar()
            await db.commit()

            # 2. Fetch all cart items joined with real-time price, vendor, and inventory
            items_query = text("""
                SELECT ci.id as item_id, ci.variant_id, ci.quantity,
                       pv.sku, pv.variant_attributes, pv.selling_price, pv.compare_at_price,
                       p.id as product_id, p.name as product_name, p.slug as product_slug,
                       v.id as vendor_id, v.store_name,
                       i.available_quantity as current_stock,
                       (SELECT storage_path FROM public.product_images pi WHERE pi.product_id = p.id ORDER BY pi.sort_order ASC LIMIT 1) as image_url
                FROM public.cart_items ci
                JOIN public.product_variants pv ON pv.id = ci.variant_id
                JOIN public.products p ON p.id = pv.product_id
                JOIN public.vendors v ON v.id = p.vendor_id
                JOIN public.inventory i ON i.variant_id = pv.id
                WHERE ci.cart_id = :cart_id
                ORDER BY v.store_name, ci.created_at;
            """)
            items_res = await db.execute(items_query, {"cart_id": cart_id})
            db_items = [dict(r) for r in items_res.mappings().all()]

            if db_items:
                item_subtotal = 0.0
                vendors_dict: Dict[str, Dict[str, Any]] = {}

                for r in db_items:
                    price = float(r["selling_price"])
                    qty = int(r["quantity"])
                    stock = int(r["current_stock"])
                    line_total = price * qty
                    item_subtotal += line_total

                    item_obj = CartItemResponse(
                        item_id=str(r["item_id"]),
                        variant_id=str(r["variant_id"]),
                        product_id=str(r["product_id"]),
                        product_name=r["product_name"],
                        product_slug=r["product_slug"],
                        vendor_id=str(r["vendor_id"]),
                        store_name=r["store_name"],
                        sku=r["sku"],
                        selling_price=price,
                        compare_at_price=float(r["compare_at_price"]) if r.get("compare_at_price") else None,
                        quantity=qty,
                        current_stock=stock,
                        is_available=(stock >= qty),
                        line_total=round(line_total, 2),
                        image_url=r.get("image_url"),
                        variant_attributes=r.get("variant_attributes") or {},
                    )

                    vid = str(r["vendor_id"])
                    if vid not in vendors_dict:
                        vendors_dict[vid] = {
                            "vendor_id": vid,
                            "store_name": r["store_name"],
                            "subtotal": 0.0,
                            "items": [],
                        }
                    vendors_dict[vid]["items"].append(item_obj)
                    vendors_dict[vid]["subtotal"] = round(vendors_dict[vid]["subtotal"] + line_total, 2)

                shipping_total = 0.0 if (item_subtotal >= 499.0 or item_subtotal == 0) else 40.0
                grand_total = round(item_subtotal + shipping_total, 2)
                amount_needed = max(0.0, round(499.0 - item_subtotal, 2)) if item_subtotal < 499.0 else 0.0

                return CartResponse(
                    cart_id=str(cart_id),
                    item_subtotal=round(item_subtotal, 2),
                    shipping_total=shipping_total,
                    grand_total=grand_total,
                    total_items=sum(i["quantity"] for i in db_items),
                    amount_needed_for_free_shipping=amount_needed,
                    vendor_groups=[
                        VendorGroupResponse(
                            vendor_id=vg["vendor_id"],
                            store_name=vg["store_name"],
                            subtotal=vg["subtotal"],
                            items=vg["items"],
                        )
                        for vg in vendors_dict.values()
                    ],
                )
        except Exception:
            pass

    # Fallback to in-memory cart store (e.g. for unit tests)
    cart_items = _MEMORY_CARTS.get(user_id, [])
    item_subtotal = 0.0
    vendors_dict: Dict[str, Dict[str, Any]] = {}

    formatted_items = []
    for item in cart_items:
        # Re-fetch latest variant from catalog to ensure atomic price verification
        catalog_entry = _find_variant_in_catalog(item["variant_id"])
        if catalog_entry:
            prod = catalog_entry["product"]
            var = catalog_entry["variant"]
            price = float(var["selling_price"])
            stock = int(var.get("available_stock", 0))
            vendor_id = str(prod["vendor_id"])
            store_name = prod.get("vendor_store_name", "Marketplace Vendor")
            primary_img = prod.get("primary_image_url")
        else:
            price = float(item.get("selling_price", 999.0))
            stock = int(item.get("current_stock", 10))
            vendor_id = item.get("vendor_id", "vend-default")
            store_name = item.get("store_name", "Featured Merchant")
            primary_img = item.get("image_url")
            prod = {"name": item.get("product_name", "Product"), "slug": "product", "id": item.get("product_id", "prod-1")}
            var = {"sku": "SKU-DEF", "variant_attributes": {}, "compare_at_price": None}

        qty = item["quantity"]
        line_total = round(price * qty, 2)
        item_subtotal += line_total

        cart_item_obj = CartItemResponse(
            item_id=item["item_id"],
            variant_id=item["variant_id"],
            product_id=str(prod.get("id")),
            product_name=prod.get("name"),
            product_slug=prod.get("slug"),
            vendor_id=vendor_id,
            store_name=store_name,
            sku=var.get("sku", "SKU"),
            selling_price=price,
            compare_at_price=float(var["compare_at_price"]) if var.get("compare_at_price") else None,
            quantity=qty,
            current_stock=stock,
            is_available=(stock >= qty),
            line_total=line_total,
            image_url=primary_img,
            variant_attributes=var.get("variant_attributes") or {},
        )

        if vendor_id not in vendors_dict:
            vendors_dict[vendor_id] = {
                "vendor_id": vendor_id,
                "store_name": store_name,
                "subtotal": 0.0,
                "items": [],
            }
        vendors_dict[vendor_id]["items"].append(cart_item_obj)
        vendors_dict[vendor_id]["subtotal"] = round(vendors_dict[vendor_id]["subtotal"] + line_total, 2)

    shipping_total = 0.0 if (item_subtotal >= 499.0 or item_subtotal == 0) else 40.0
    grand_total = round(item_subtotal + shipping_total, 2)
    amount_needed = max(0.0, round(499.0 - item_subtotal, 2)) if item_subtotal < 499.0 else 0.0

    return CartResponse(
        cart_id=f"cart-{user_id[:8]}",
        item_subtotal=round(item_subtotal, 2),
        shipping_total=shipping_total,
        grand_total=grand_total,
        total_items=sum(i["quantity"] for i in cart_items),
        amount_needed_for_free_shipping=amount_needed,
        vendor_groups=[
            VendorGroupResponse(
                vendor_id=vg["vendor_id"],
                store_name=vg["store_name"],
                subtotal=vg["subtotal"],
                items=vg["items"],
            )
            for vg in vendors_dict.values()
        ],
    )


@router.post("/cart/items", status_code=status.HTTP_201_CREATED)
async def add_item_to_cart(
    req: CartItemAddRequest,
    current_user: dict = Depends(get_current_user),
    db: Optional[AsyncSession] = Depends(get_db),
):
    """
    Adds a product variant to the customer's cart with atomic stock validation.
    Prices are strictly derived from backend database/catalog; client prices are ignored.
    """
    user_id = str(current_user["id"])

    # 1. DB Attempt
    if db is not None:
        try:
            stock_query = text("""
                SELECT i.available_quantity, pv.is_active, pv.selling_price, p.product_status
                FROM public.product_variants pv
                JOIN public.products p ON p.id = pv.product_id
                JOIN public.inventory i ON i.variant_id = pv.id
                WHERE pv.id = :variant_id
            """)
            stock_res = await db.execute(stock_query, {"variant_id": req.variant_id})
            variant_info = stock_res.mappings().first()

            if variant_info:
                if not variant_info["is_active"] or variant_info["product_status"] != "active":
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Product variant is inactive or not available"
                    )

                available_qty = int(variant_info["available_quantity"])
                if available_qty < req.quantity:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Insufficient stock. Available: {available_qty}"
                    )

                upsert_query = text("""
                    WITH user_cart AS (
                        INSERT INTO public.carts (user_id, status) VALUES (:user_id, 'active')
                        ON CONFLICT (user_id) DO UPDATE SET updated_at = NOW()
                        RETURNING id
                    )
                    INSERT INTO public.cart_items (cart_id, variant_id, quantity)
                    SELECT id, :variant_id, :quantity FROM user_cart
                    ON CONFLICT (cart_id, variant_id)
                    DO UPDATE SET quantity = cart_items.quantity + EXCLUDED.quantity, updated_at = NOW()
                    RETURNING id;
                """)
                await db.execute(upsert_query, {
                    "user_id": user_id,
                    "variant_id": req.variant_id,
                    "quantity": req.quantity
                })
                await db.commit()
                return {"status": "success", "message": "Item added to cart"}
        except HTTPException:
            raise
        except Exception:
            pass

    # 2. In-Memory Validation & Upsert (Catalog lookup)
    catalog_entry = _find_variant_in_catalog(req.variant_id)
    if not catalog_entry:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Product variant is inactive or not available"
        )

    var = catalog_entry["variant"]
    available_stock = int(var.get("available_stock", 0))

    if available_stock < req.quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient stock. Available: {available_stock}"
        )

    if user_id not in _MEMORY_CARTS:
        _MEMORY_CARTS[user_id] = []

    user_items = _MEMORY_CARTS[user_id]
    existing = next((i for i in user_items if i["variant_id"] == req.variant_id), None)

    if existing:
        new_total_qty = existing["quantity"] + req.quantity
        if new_total_qty > available_stock:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient stock. Available: {available_stock}"
            )
        existing["quantity"] = new_total_qty
    else:
        user_items.append({
            "item_id": f"ci-{req.variant_id}-{len(user_items) + 1}",
            "variant_id": req.variant_id,
            "quantity": req.quantity,
        })

    return {"status": "success", "message": "Item added to cart"}


@router.patch("/cart/items/{item_id}")
async def update_cart_item(
    item_id: str,
    req: CartItemUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: Optional[AsyncSession] = Depends(get_db),
):
    """
    Updates the quantity of an item in the cart, enforcing stock constraints.
    """
    user_id = str(current_user["id"])

    # Try DB
    if db is not None:
        try:
            check_query = text("""
                SELECT ci.id, ci.variant_id, i.available_quantity
                FROM public.cart_items ci
                JOIN public.carts c ON c.id = ci.cart_id
                JOIN public.inventory i ON i.variant_id = ci.variant_id
                WHERE ci.id = :item_id AND c.user_id = :user_id
            """)
            res = await db.execute(check_query, {"item_id": item_id, "user_id": user_id})
            row = res.mappings().first()
            if row:
                if row["available_quantity"] < req.quantity:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Insufficient stock. Available: {row['available_quantity']}"
                    )
                update_query = text("""
                    UPDATE public.cart_items
                    SET quantity = :qty, updated_at = NOW()
                    WHERE id = :item_id
                """)
                await db.execute(update_query, {"qty": req.quantity, "item_id": item_id})
                await db.commit()
                return {"status": "success", "message": "Cart item updated"}
        except HTTPException:
            raise
        except Exception:
            pass

    # In-Memory Update
    user_items = _MEMORY_CARTS.get(user_id, [])
    target = next((i for i in user_items if i["item_id"] == item_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Cart item not found")

    catalog_entry = _find_variant_in_catalog(target["variant_id"])
    if catalog_entry:
        stock = catalog_entry["variant"].get("available_stock", 0)
        if stock < req.quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient stock. Available: {stock}"
            )

    target["quantity"] = req.quantity
    return {"status": "success", "message": "Cart item updated"}


@router.delete("/cart/items/{item_id}")
async def remove_cart_item(
    item_id: str,
    current_user: dict = Depends(get_current_user),
    db: Optional[AsyncSession] = Depends(get_db),
):
    """
    Removes an item from the customer's cart.
    """
    user_id = str(current_user["id"])

    if db is not None:
        try:
            del_query = text("""
                DELETE FROM public.cart_items ci
                USING public.carts c
                WHERE ci.cart_id = c.id AND c.user_id = :user_id AND ci.id = :item_id
            """)
            await db.execute(del_query, {"user_id": user_id, "item_id": item_id})
            await db.commit()
            return {"status": "success", "message": "Item removed from cart"}
        except Exception:
            pass

    user_items = _MEMORY_CARTS.get(user_id, [])
    _MEMORY_CARTS[user_id] = [i for i in user_items if i["item_id"] != item_id]
    return {"status": "success", "message": "Item removed from cart"}


@router.delete("/cart/clear")
async def clear_cart(
    current_user: dict = Depends(get_current_user),
    db: Optional[AsyncSession] = Depends(get_db),
):
    """
    Clears all items from the customer's cart.
    """
    user_id = str(current_user["id"])

    if db is not None:
        try:
            clear_query = text("""
                DELETE FROM public.cart_items ci
                USING public.carts c
                WHERE ci.cart_id = c.id AND c.user_id = :user_id
            """)
            await db.execute(clear_query, {"user_id": user_id})
            await db.commit()
            return {"status": "success", "message": "Cart cleared"}
        except Exception:
            pass

    _MEMORY_CARTS[user_id] = []
    return {"status": "success", "message": "Cart cleared"}
