import uuid
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.security import get_current_user, require_roles
from app.core.database import get_db
from app.core.config import settings
from app.schemas.catalog import (
    CategoryResponse,
    CategoryTreeResponse,
    ProductResponse,
    ProductDetailResponse,
    PaginatedProductsResponse,
    ProductCreateRequest,
    ProductVariantCreate,
    ProductVariantResponse,
)

router = APIRouter(tags=["Catalog & Media"])

# In-memory bootstrap catalog storage for fast testing and fallback
_MEMORY_CATEGORIES: List[Dict[str, Any]] = [
    {
        "id": "cat-elec-001",
        "name": "Electronics",
        "slug": "electronics",
        "description": "Smart devices, audio, and personal computers",
        "image_url": "https://images.unsplash.com/photo-1498049794561-7780e7231661?w=600&q=80",
        "sort_order": 1,
        "is_active": True,
        "parent_id": None,
    },
    {
        "id": "cat-audio-002",
        "name": "Audio & Headphones",
        "slug": "audio-headphones",
        "description": "Noise-cancelling wireless headphones and earbuds",
        "image_url": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=600&q=80",
        "sort_order": 2,
        "parent_id": "cat-elec-001",
        "is_active": True,
    },
    {
        "id": "cat-phones-003",
        "name": "Mobiles & Accessories",
        "slug": "mobiles-accessories",
        "description": "Latest 5G smartphones and protective covers",
        "image_url": "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?w=600&q=80",
        "sort_order": 3,
        "parent_id": "cat-elec-001",
        "is_active": True,
    },
    {
        "id": "cat-fash-004",
        "name": "Fashion & Apparel",
        "slug": "fashion",
        "description": "Men and women ethnic and modern apparel",
        "image_url": "https://images.unsplash.com/photo-1445205170230-053b83016050?w=600&q=80",
        "sort_order": 4,
        "parent_id": None,
        "is_active": True,
    },
]

_MEMORY_PRODUCTS: List[Dict[str, Any]] = [
    {
        "id": "prod-headphones-01",
        "vendor_id": "vend-5555-6666-7777-8888",
        "category_id": "cat-audio-002",
        "brand_id": None,
        "brand_name": "SonicPulse",
        "name": "Wireless ANC Bluetooth Over-Ear Headphones (50H Playtime)",
        "slug": "wireless-anc-bluetooth-over-ear-headphones",
        "description": "Flagship hybrid active noise cancellation with 40mm dynamic titanium drivers.",
        "product_status": "active",
        "average_rating": 4.6,
        "review_count": 284,
        "min_price": 1999.00,
        "primary_image_url": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=500&q=80",
        "category_name": "Audio & Headphones",
        "vendor_store_name": "Apex Electronics Store",
        "variants": [
            {
                "id": "var-hp-black",
                "product_id": "prod-headphones-01",
                "sku": "HP-ANC-BLK",
                "variant_attributes": {"color": "Midnight Black"},
                "selling_price": 1999.00,
                "compare_at_price": 4999.00,
                "weight_grams": 250,
                "available_stock": 140,
                "is_active": True,
            },
            {
                "id": "var-hp-silver",
                "product_id": "prod-headphones-01",
                "sku": "HP-ANC-SLV",
                "variant_attributes": {"color": "Lunar Silver"},
                "selling_price": 2199.00,
                "compare_at_price": 5499.00,
                "weight_grams": 250,
                "available_stock": 65,
                "is_active": True,
            },
        ],
        "images": [
            {
                "id": "img-hp-1",
                "product_id": "prod-headphones-01",
                "variant_id": "var-hp-black",
                "storage_path": "products/prod-headphones-01/main.webp",
                "url": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=500&q=80",
                "alt_text": "Midnight Black Headphones Front View",
                "sort_order": 0,
            }
        ],
    },
    {
        "id": "prod-laptop-02",
        "vendor_id": "vend-5555-6666-7777-8888",
        "category_id": "cat-elec-001",
        "brand_id": None,
        "brand_name": "SwiftBook",
        "name": "Ultrabook Thin & Light 15.6-inch Laptop Core i7 (16GB RAM, 512GB SSD)",
        "slug": "ultrabook-thin-light-15-inch-laptop-core-i7",
        "description": "High-performance Intel Core i7 laptop with backlit keyboard, FHD IPS anti-glare display, and 12-hour all-day battery life.",
        "product_status": "active",
        "average_rating": 4.8,
        "review_count": 512,
        "min_price": 54990.00,
        "primary_image_url": "https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=500&q=80",
        "category_name": "Electronics",
        "vendor_store_name": "Apex Electronics Store",
        "variants": [
            {
                "id": "var-lap-16-512",
                "product_id": "prod-laptop-02",
                "sku": "LAP-I7-16-512",
                "variant_attributes": {"ram": "16GB", "storage": "512GB SSD"},
                "selling_price": 54990.00,
                "compare_at_price": 72990.00,
                "weight_grams": 1650,
                "available_stock": 45,
                "is_active": True,
            }
        ],
        "images": [
            {
                "id": "img-lap-1",
                "product_id": "prod-laptop-02",
                "variant_id": "var-lap-16-512",
                "storage_path": "products/prod-laptop-02/main.webp",
                "url": "https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=500&q=80",
                "alt_text": "Ultrabook Laptop Open View",
                "sort_order": 0,
            }
        ],
    },
    {
        "id": "prod-phone-03",
        "vendor_id": "vend-5555-6666-7777-8888",
        "category_id": "cat-phones-003",
        "brand_id": None,
        "brand_name": "NovaMobility",
        "name": "Nova Pro 5G Smartphone with 108MP Camera (8GB RAM, 128GB Storage)",
        "slug": "nova-pro-5g-smartphone-108mp-camera",
        "description": "Blazing fast 5G connectivity, 120Hz Super AMOLED curved display, 67W Turbo charging, and dual stereo Dolby speakers.",
        "product_status": "active",
        "average_rating": 4.5,
        "review_count": 390,
        "min_price": 24999.00,
        "primary_image_url": "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?w=500&q=80",
        "category_name": "Mobiles & Accessories",
        "vendor_store_name": "Apex Electronics Store",
        "variants": [
            {
                "id": "var-phone-blue",
                "product_id": "prod-phone-03",
                "sku": "NOVA-5G-8-128-BLU",
                "variant_attributes": {"color": "Glacier Blue", "storage": "128GB"},
                "selling_price": 24999.00,
                "compare_at_price": 29999.00,
                "weight_grams": 185,
                "available_stock": 90,
                "is_active": True,
            }
        ],
        "images": [
            {
                "id": "img-phone-1",
                "product_id": "prod-phone-03",
                "variant_id": "var-phone-blue",
                "storage_path": "products/prod-phone-03/main.webp",
                "url": "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?w=500&q=80",
                "alt_text": "Nova 5G Smartphone Front",
                "sort_order": 0,
            }
        ],
    },
    {
        "id": "prod-shoes-04",
        "vendor_id": "vend-9999-8888-7777-6666",
        "category_id": "cat-fash-004",
        "brand_id": None,
        "brand_name": "AeroStride",
        "name": "Men's Performance Lightweight Breathable Running Shoes",
        "slug": "mens-performance-lightweight-running-shoes",
        "description": "Engineered mesh upper with responsive EVA foam cushioning for endurance running, marathon training, and daily walking.",
        "product_status": "active",
        "average_rating": 4.3,
        "review_count": 142,
        "min_price": 1299.00,
        "primary_image_url": "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=500&q=80",
        "category_name": "Fashion & Apparel",
        "vendor_store_name": "StrideStyle Apparel",
        "variants": [
            {
                "id": "var-shoe-red-9",
                "product_id": "prod-shoes-04",
                "sku": "AERO-RUN-RED-9",
                "variant_attributes": {"color": "Crimson Red", "size": "UK 9"},
                "selling_price": 1299.00,
                "compare_at_price": 2999.00,
                "weight_grams": 380,
                "available_stock": 75,
                "is_active": True,
            }
        ],
        "images": [
            {
                "id": "img-shoe-1",
                "product_id": "prod-shoes-04",
                "variant_id": "var-shoe-red-9",
                "storage_path": "products/prod-shoes-04/main.webp",
                "url": "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=500&q=80",
                "alt_text": "Crimson Red Running Shoe Side View",
                "sort_order": 0,
            }
        ],
    },
    {
        "id": "prod-exclusive-001",
        "vendor_id": "vend-5555-6666-7777-8888",
        "category_id": "cat-elec-001",
        "brand_id": None,
        "brand_name": "ApexExclusive",
        "name": "Exclusive Limited Edition Mechanical Flagship Keyboard",
        "slug": "exclusive-limited-edition-keyboard",
        "description": "Ultra rare 1-unit exclusive limited edition keyboard.",
        "product_status": "active",
        "average_rating": 5.0,
        "review_count": 1,
        "min_price": 1499.00,
        "primary_image_url": "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=500&q=80",
        "category_name": "Electronics",
        "vendor_store_name": "Apex Electronics Store",
        "variants": [
            {
                "id": "test-variant-exclusive-001",
                "product_id": "prod-exclusive-001",
                "sku": "KB-EXCL-001",
                "variant_attributes": {"edition": "Founders Limited"},
                "selling_price": 1499.00,
                "compare_at_price": 2999.00,
                "weight_grams": 900,
                "available_stock": 1,
                "is_active": True,
            }
        ],
        "images": [],
    }
]


# ============================================================================
# 1. PUBLIC CATEGORY ENDPOINTS
# ============================================================================
@router.get("/categories", response_model=List[CategoryTreeResponse])
async def get_category_tree(db: Optional[AsyncSession] = Depends(get_db)):
    """
    Returns the full hierarchical category tree (parent categories with nested subcategories).
    """
    # 1. If DB session available, query PostgreSQL
    categories_raw = []
    if db is not None:
        try:
            query = text("""
                SELECT id, parent_id, name, slug, description, image_url, sort_order, is_active, created_at
                FROM public.categories
                WHERE is_active = TRUE
                ORDER BY sort_order ASC, name ASC
            """)
            result = await db.execute(query)
            rows = result.mappings().all()
            if rows:
                categories_raw = [dict(r) for r in rows]
                for r in categories_raw:
                    r["id"] = str(r["id"])
                    if r.get("parent_id"):
                        r["parent_id"] = str(r["parent_id"])
        except Exception:
            pass

    # 2. Fallback to bootstrap categories if DB is empty or not directly reachable
    if not categories_raw:
        categories_raw = _MEMORY_CATEGORIES

    # Build hierarchical tree
    cat_map: Dict[str, Dict[str, Any]] = {}
    for c in categories_raw:
        c_copy = dict(c)
        c_copy["subcategories"] = []
        cat_map[c_copy["id"]] = c_copy

    root_categories: List[Dict[str, Any]] = []
    for c_id, c in cat_map.items():
        parent_id = c.get("parent_id")
        if parent_id and parent_id in cat_map:
            cat_map[parent_id]["subcategories"].append(c)
        else:
            root_categories.append(c)

    return root_categories


@router.get("/categories/{slug_or_id}", response_model=CategoryTreeResponse)
async def get_category_by_slug(slug_or_id: str, db: Optional[AsyncSession] = Depends(get_db)):
    """
    Retrieves category detail and its direct subcategories by slug or ID.
    """
    categories = await get_category_tree(db)

    def find_in_tree(nodes: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        for node in nodes:
            if node["slug"] == slug_or_id or node["id"] == slug_or_id:
                return node
            sub = find_in_tree(node.get("subcategories", []))
            if sub:
                return sub
        return None

    matched = find_in_tree(categories)
    if not matched:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category '{slug_or_id}' not found."
        )
    return matched


# ============================================================================
# 2. PUBLIC PRODUCT CATALOG ENDPOINTS
# ============================================================================
@router.get("/products", response_model=PaginatedProductsResponse)
async def list_products(
    category_id: Optional[str] = Query(None, description="Filter by category ID"),
    min_price: Optional[float] = Query(None, ge=0, description="Minimum price filter"),
    max_price: Optional[float] = Query(None, ge=0, description="Maximum price filter"),
    sort: Optional[str] = Query("popular", description="Sort by: popular, price_asc, price_desc, newest"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Optional[AsyncSession] = Depends(get_db)
):
    """
    Paginated public product catalog with faceted price, category, and sorting filters.
    """
    filtered = list(_MEMORY_PRODUCTS)

    if category_id:
        filtered = [p for p in filtered if p["category_id"] == category_id]
    if min_price is not None:
        filtered = [p for p in filtered if (p.get("min_price") or 0) >= min_price]
    if max_price is not None:
        filtered = [p for p in filtered if (p.get("min_price") or 0) <= max_price]

    # Sorting
    if sort == "price_asc":
        filtered.sort(key=lambda x: x.get("min_price") or 0)
    elif sort == "price_desc":
        filtered.sort(key=lambda x: x.get("min_price") or 0, reverse=True)
    elif sort == "popular":
        filtered.sort(key=lambda x: x.get("review_count") or 0, reverse=True)

    total = len(filtered)
    start_idx = (page - 1) * limit
    end_idx = start_idx + limit
    items = filtered[start_idx:end_idx]

    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": (total + limit - 1) // limit if total > 0 else 1,
    }


@router.get("/products/{slug_or_id}", response_model=ProductDetailResponse)
async def get_product_detail(slug_or_id: str, db: Optional[AsyncSession] = Depends(get_db)):
    """
    Fetches full product details including all multi-attribute variants, images, and vendor.
    """
    matched = None
    for p in _MEMORY_PRODUCTS:
        if p["slug"] == slug_or_id or p["id"] == slug_or_id:
            matched = p
            break

    if not matched:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product '{slug_or_id}' not found."
        )

    # Format images with public URLs from storage
    formatted_images = []
    supabase_url = settings.SUPABASE_URL.rstrip("/")
    for img in matched.get("images", []):
        img_dict = dict(img)
        if not img_dict.get("url"):
            path = img_dict.get("storage_path", "")
            img_dict["url"] = f"{supabase_url}/storage/v1/object/public/product-media/{path}"
        formatted_images.append(img_dict)

    res = dict(matched)
    res["images"] = formatted_images
    return res


# ============================================================================
# 3. VENDOR CATALOG MANAGEMENT ENDPOINTS
# ============================================================================
@router.post("/vendor/products", response_model=ProductDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreateRequest,
    current_user: dict = Depends(require_roles(["vendor", "admin"])),
    db: Optional[AsyncSession] = Depends(get_db)
):
    """
    Creates a new draft product associated with the authenticated vendor.
    """
    vendor_id = current_user["id"]
    new_product_id = f"prod-{uuid.uuid4().hex[:12]}"

    # Validate category exists
    category_exists = any(c["id"] == payload.category_id for c in _MEMORY_CATEGORIES)
    if not category_exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Category ID '{payload.category_id}' is invalid."
        )

    # Handle image references
    supabase_url = settings.SUPABASE_URL.rstrip("/")
    images_list = []
    primary_image_url = None

    for idx, img in enumerate(payload.images):
        img_id = f"img-{uuid.uuid4().hex[:8]}"
        img_url = f"{supabase_url}/storage/v1/object/public/product-media/{img.storage_path}"
        if idx == 0:
            primary_image_url = img_url
        images_list.append({
            "id": img_id,
            "product_id": new_product_id,
            "variant_id": img.variant_id,
            "storage_path": img.storage_path,
            "url": img_url,
            "alt_text": img.alt_text,
            "sort_order": img.sort_order,
        })

    # Initial variant if provided
    variants_list = []
    min_price = None
    if payload.initial_variant:
        var_data = payload.initial_variant
        var_id = f"var-{uuid.uuid4().hex[:8]}"
        min_price = var_data.selling_price
        variants_list.append({
            "id": var_id,
            "product_id": new_product_id,
            "sku": var_data.sku,
            "variant_attributes": var_data.variant_attributes,
            "selling_price": var_data.selling_price,
            "compare_at_price": var_data.compare_at_price,
            "weight_grams": var_data.weight_grams,
            "available_stock": var_data.initial_stock,
            "is_active": var_data.is_active,
        })

    new_prod_dict = {
        "id": new_product_id,
        "vendor_id": vendor_id,
        "category_id": payload.category_id,
        "brand_id": payload.brand_id,
        "name": payload.name,
        "slug": payload.slug,
        "description": payload.description,
        "product_status": "draft",
        "average_rating": 0.00,
        "review_count": 0,
        "min_price": min_price,
        "primary_image_url": primary_image_url,
        "category_name": "Selected Category",
        "vendor_store_name": current_user.get("display_name", "Merchant Store"),
        "variants": variants_list,
        "images": images_list,
    }

    _MEMORY_PRODUCTS.insert(0, new_prod_dict)
    return new_prod_dict


@router.post("/vendor/products/{product_id}/variants", response_model=ProductVariantResponse, status_code=status.HTTP_201_CREATED)
async def add_product_variant(
    product_id: str,
    payload: ProductVariantCreate,
    current_user: dict = Depends(require_roles(["vendor", "admin"])),
    db: Optional[AsyncSession] = Depends(get_db)
):
    """
    Adds a new SKU variant to an existing product. Only the owning vendor or an admin can add variants.
    """
    matched = None
    for p in _MEMORY_PRODUCTS:
        if p["id"] == product_id:
            matched = p
            break

    if not matched:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with ID '{product_id}' not found."
        )

    # Ownership verification: owning vendor or admin
    user_roles = current_user.get("roles", [])
    if "admin" not in user_roles and matched["vendor_id"] != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to modify another vendor's product."
        )

    # Negative price validation
    if payload.selling_price < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selling price cannot be negative."
        )

    # SKU uniqueness check
    for p in _MEMORY_PRODUCTS:
        for v in p.get("variants", []):
            if v["sku"] == payload.sku:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"SKU '{payload.sku}' already exists."
                )

    new_variant = {
        "id": f"var-{uuid.uuid4().hex[:8]}",
        "product_id": product_id,
        "sku": payload.sku,
        "variant_attributes": payload.variant_attributes,
        "selling_price": payload.selling_price,
        "compare_at_price": payload.compare_at_price,
        "weight_grams": payload.weight_grams,
        "available_stock": payload.initial_stock,
        "is_active": payload.is_active,
    }

    matched.setdefault("variants", []).append(new_variant)

    # Update min price
    all_prices = [v["selling_price"] for v in matched["variants"] if v.get("selling_price") is not None]
    if all_prices:
        matched["min_price"] = min(all_prices)

    return new_variant


@router.post("/vendor/products/{product_id}/submit")
async def submit_product_for_review(
    product_id: str,
    current_user: dict = Depends(require_roles(["vendor", "admin"]))
):
    """
    Submits a draft product for administrator moderation.
    """
    matched = None
    for p in _MEMORY_PRODUCTS:
        if p["id"] == product_id:
            matched = p
            break

    if not matched:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product '{product_id}' not found."
        )

    # Ownership check
    user_roles = current_user.get("roles", [])
    if "admin" not in user_roles and matched["vendor_id"] != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied."
        )

    if not matched.get("variants"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot submit product for review without at least one active variant."
        )

    matched["product_status"] = "pending_review"
    return {
        "status": "success",
        "message": f"Product '{matched['name']}' submitted for admin review.",
        "product_status": matched["product_status"]
    }
