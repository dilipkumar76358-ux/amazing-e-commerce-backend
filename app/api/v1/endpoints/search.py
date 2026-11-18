from fastapi import APIRouter, Depends, Query
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.database import get_db
from app.core.config import settings
from app.schemas.search import SearchResponse, AutoSuggestResponse, SearchResultItem, SearchFacets
from app.api.v1.endpoints.catalog import _MEMORY_PRODUCTS, _MEMORY_CATEGORIES

router = APIRouter(tags=["Search & Discovery"])


@router.get("/search", response_model=SearchResponse)
async def search_products(
    q: Optional[str] = Query(None, description="Free-text search keyword"),
    category: Optional[str] = Query(None, description="Category slug or ID"),
    brand: Optional[str] = Query(None, description="Brand name or filter"),
    min_price: Optional[float] = Query(None, ge=0, description="Minimum price filter (₹)"),
    max_price: Optional[float] = Query(None, ge=0, description="Maximum price filter (₹)"),
    min_rating: Optional[float] = Query(None, ge=0, le=5, description="Minimum star rating filter"),
    in_stock_only: bool = Query(False, description="Filter for in-stock items only"),
    sort: str = Query("relevance", description="Sorting: relevance, price_asc, price_desc, rating_desc, newest"),
    page: int = Query(1, ge=1),
    limit: int = Query(24, ge=1, le=48),
    db: Optional[AsyncSession] = Depends(get_db)
):
    """
    Full-Text and faceted search engine for marketplace catalog.
    Supports keyword relevance ranking, price range slicing, star ratings, and category filters.
    """
    matched_items: List[Dict[str, Any]] = []

    # 1. Attempt PostgreSQL Full-Text search query if DB session is active
    if db is not None:
        try:
            sort_clause = "p.average_rating DESC, p.created_at DESC"
            if sort == "price_asc":
                sort_clause = "min_variant_price ASC"
            elif sort == "price_desc":
                sort_clause = "min_variant_price DESC"
            elif sort == "newest":
                sort_clause = "p.created_at DESC"
            elif sort == "rating_desc":
                sort_clause = "p.average_rating DESC"

            query_sql = f"""
                WITH matched_products AS (
                    SELECT p.id, p.name, p.slug, p.description, p.average_rating, p.review_count,
                           p.category_id, p.brand_id, p.created_at,
                           b.name as brand_name,
                           c.name as category_name,
                           MIN(pv.selling_price) as min_variant_price,
                           MAX(pv.compare_at_price) as max_compare_price,
                           COALESCE(SUM(i.available_quantity), 0) as total_stock,
                           (SELECT pi.storage_path FROM public.product_images pi WHERE pi.product_id = p.id ORDER BY pi.sort_order ASC LIMIT 1) as primary_image
                    FROM public.products p
                    JOIN public.categories c ON c.id = p.category_id
                    JOIN public.product_variants pv ON pv.product_id = p.id AND pv.is_active = TRUE
                    LEFT JOIN public.inventory i ON i.variant_id = pv.id
                    LEFT JOIN public.brands b ON b.id = p.brand_id
                    WHERE p.product_status = 'active'
                      AND (:q IS NULL OR p.search_vector @@ websearch_to_tsquery('english', :q) OR p.name ILIKE '%' || :q || '%')
                    GROUP BY p.id, b.name, c.name
                )
                SELECT * FROM matched_products
                WHERE (:min_price IS NULL OR min_variant_price >= :min_price)
                  AND (:max_price IS NULL OR min_variant_price <= :max_price)
                  AND (:min_rating IS NULL OR average_rating >= :min_rating)
                ORDER BY {sort_clause};
            """
            results = await db.execute(text(query_sql), {
                "q": q.strip() if q else None,
                "min_price": min_price,
                "max_price": max_price,
                "min_rating": min_rating,
            })
            rows = results.mappings().all()
            if rows:
                matched_items = [dict(r) for r in rows]
                for item in matched_items:
                    item["id"] = str(item["id"])
                    item["category_id"] = str(item["category_id"])
                    if item.get("primary_image"):
                        item["primary_image"] = f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/public/product-media/{item['primary_image']}"
        except Exception:
            pass

    # 2. In-memory fallback / bootstrap search algorithm
    if not matched_items:
        clean_q = q.lower().strip() if q else ""
        stopwords = {"a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "with", "by", "of", "from", "is", "it"}
        for p in _MEMORY_PRODUCTS:
            if p.get("product_status") != "active":
                continue

            # Text relevance check
            relevance_score = 0
            if clean_q:
                name_lower = p.get("name", "").lower()
                desc_lower = p.get("description", "").lower()
                cat_lower = p.get("category_name", "").lower()
                brand_lower = (p.get("brand_name") or "").lower()

                if clean_q in name_lower:
                    relevance_score += 10
                if clean_q in brand_lower:
                    relevance_score += 8
                if clean_q in cat_lower:
                    relevance_score += 6
                if clean_q in desc_lower:
                    relevance_score += 3

                # Check token overlap if full phrase didn't match
                if relevance_score == 0:
                    raw_tokens = clean_q.split()
                    filtered_tokens = [t for t in raw_tokens if t not in stopwords]
                    tokens_to_check = filtered_tokens if filtered_tokens else raw_tokens

                    token_matched = False
                    for t in tokens_to_check:
                        t_stem = t[:-1] if (len(t) > 3 and t.endswith("s")) else (t[:-2] if (len(t) > 4 and t.endswith("es")) else t)
                        if t in name_lower or (len(t_stem) > 2 and t_stem in name_lower):
                            relevance_score += 5
                            token_matched = True
                        elif t in brand_lower or (len(t_stem) > 2 and t_stem in brand_lower):
                            relevance_score += 4
                            token_matched = True
                        elif t in cat_lower or (len(t_stem) > 2 and t_stem in cat_lower):
                            relevance_score += 3
                            token_matched = True
                        elif t in desc_lower or (len(t_stem) > 2 and t_stem in desc_lower):
                            relevance_score += 1
                            token_matched = True

                    if not token_matched:
                        continue

            price = p.get("min_price") or 0.0

            # Price filters
            if min_price is not None and price < min_price:
                continue
            if max_price is not None and price > max_price:
                continue

            # Rating filter
            rating = p.get("average_rating") or 0.0
            if min_rating is not None and rating < min_rating:
                continue

            # Category filter (flexible slug, ID, and alias matching)
            if category:
                cat_req = category.lower().strip()
                cat_prod_name = p.get("category_name", "").lower()
                cat_prod_id = str(p.get("category_id", "")).lower()

                is_match = (
                    cat_prod_id == cat_req
                    or cat_prod_name == cat_req
                    or cat_req in cat_prod_name
                    or cat_prod_name in cat_req
                )
                if not is_match:
                    if any(k in cat_req for k in ["laptop", "computer", "pc", "notebook"]):
                        is_match = (
                            "laptop" in cat_prod_name
                            or "computer" in cat_prod_name
                            or any(k in p.get("name", "").lower() for k in ["laptop", "ultrabook", "notebook", "swiftbook", "keyboard"])
                        )
                    elif any(k in cat_req for k in ["audio", "headphone", "earphone"]):
                        is_match = "audio" in cat_prod_name or "headphone" in cat_prod_name
                    elif any(k in cat_req for k in ["mobile", "phone"]):
                        is_match = "mobile" in cat_prod_name or "phone" in cat_prod_name
                    elif any(k in cat_req for k in ["fashion", "apparel", "shoe"]):
                        is_match = "fashion" in cat_prod_name or "apparel" in cat_prod_name
                    elif "electronic" in cat_req:
                        is_match = True

                if not is_match:
                    continue

            # Brand filter
            if brand:
                if (p.get("brand_name") or "").lower() != brand.lower():
                    continue

            # Stock check
            total_stock = sum(v.get("available_stock", 0) for v in p.get("variants", []))
            if in_stock_only and total_stock <= 0:
                continue

            matched_items.append({
                "id": p["id"],
                "name": p["name"],
                "slug": p["slug"],
                "description": p.get("description"),
                "category_id": p.get("category_id", ""),
                "category_name": p.get("category_name"),
                "brand_name": p.get("brand_name", "Featured Brand"),
                "average_rating": rating,
                "review_count": p.get("review_count", 0),
                "min_variant_price": price,
                "max_compare_price": p["variants"][0].get("compare_at_price") if p.get("variants") else None,
                "total_stock": total_stock,
                "primary_image": p.get("primary_image_url"),
                "_relevance": relevance_score,
            })

        # Sorting
        if sort == "price_asc":
            matched_items.sort(key=lambda x: x["min_variant_price"])
        elif sort == "price_desc":
            matched_items.sort(key=lambda x: x["min_variant_price"], reverse=True)
        elif sort == "rating_desc":
            matched_items.sort(key=lambda x: x["average_rating"], reverse=True)
        elif sort == "relevance":
            matched_items.sort(key=lambda x: (x.get("_relevance", 0), x["average_rating"]), reverse=True)

    # Calculate facets from all matched results
    category_counts: Dict[str, int] = {}
    brand_counts: Dict[str, int] = {}
    rating_buckets = {"4_and_up": 0, "3_and_up": 0}

    for item in matched_items:
        cat_name = item.get("category_name") or "Other"
        category_counts[cat_name] = category_counts.get(cat_name, 0) + 1

        b_name = item.get("brand_name") or "Generic"
        brand_counts[b_name] = brand_counts.get(b_name, 0) + 1

        if item.get("average_rating", 0) >= 4.0:
            rating_buckets["4_and_up"] += 1
        if item.get("average_rating", 0) >= 3.0:
            rating_buckets["3_and_up"] += 1

    facets = SearchFacets(
        categories=[{"name": k, "count": v} for k, v in category_counts.items()],
        brands=[{"name": k, "count": v} for k, v in brand_counts.items()],
        price_ranges=[
            {"label": "Under ₹500", "min": 0, "max": 500},
            {"label": "₹500 - ₹1,000", "min": 500, "max": 1000},
            {"label": "₹1,000 - ₹5,000", "min": 1000, "max": 5000},
            {"label": "Over ₹5,000", "min": 5000, "max": None},
        ],
        rating_counts=rating_buckets,
    )

    total = len(matched_items)
    start_idx = (page - 1) * limit
    paged_results = matched_items[start_idx : start_idx + limit]

    message = None
    if total == 0 and q:
        message = "No results found. Try checking your spelling or use more general terms."

    return {
        "query": q,
        "page": page,
        "limit": limit,
        "count": len(paged_results),
        "total": total,
        "results": paged_results,
        "facets": facets,
        "message": message,
    }


@router.get("/search/suggestions", response_model=AutoSuggestResponse)
async def get_search_suggestions(
    q: str = Query(..., min_length=1, description="Partial search query keyword")
):
    """
    Live debounced auto-suggestions returning keyword completions, matching categories,
    and featured product previews.
    """
    clean_q = q.lower().strip()
    suggestions: List[str] = []
    matched_categories: List[Dict[str, str]] = []
    featured_products: List[Dict[str, Any]] = []

    # Dictionary of popular autocomplete queries
    popular_keywords = [
        "wireless headphones", "bluetooth earphones", "laptop core i7",
        "laptop 16gb ram", "5g smartphone", "running shoes",
        "smartwatch amoled", "audio speakers", "wireless mouse"
    ]

    for kw in popular_keywords:
        if clean_q in kw and kw not in suggestions:
            suggestions.append(kw)

    # Match categories
    for c in _MEMORY_CATEGORIES:
        if clean_q in c["name"].lower() or clean_q in c["slug"]:
            matched_categories.append({"id": c["id"], "name": c["name"], "slug": c["slug"]})

    # Match top products
    for p in _MEMORY_PRODUCTS:
        if clean_q in p["name"].lower():
            if len(featured_products) < 4:
                featured_products.append({
                    "id": p["id"],
                    "name": p["name"],
                    "slug": p["slug"],
                    "price": p.get("min_price"),
                    "image": p.get("primary_image_url"),
                    "category": p.get("category_name"),
                })
            suggestions.append(p["name"][:35])

    return {
        "query": q,
        "suggestions": list(dict.fromkeys(suggestions))[:8],
        "matched_categories": matched_categories[:3],
        "featured_products": featured_products,
    }
