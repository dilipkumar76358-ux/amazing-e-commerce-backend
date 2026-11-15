from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class SearchResultItem(BaseModel):
    id: str
    name: str
    slug: str
    description: Optional[str] = None
    category_id: str
    category_name: Optional[str] = None
    brand_name: Optional[str] = None
    average_rating: float = 0.0
    review_count: int = 0
    min_variant_price: float
    max_compare_price: Optional[float] = None
    total_stock: int = 0
    primary_image: Optional[str] = None


class SearchFacets(BaseModel):
    categories: List[Dict[str, Any]] = []
    brands: List[Dict[str, Any]] = []
    price_ranges: List[Dict[str, Any]] = []
    rating_counts: Dict[str, int] = {}


class SearchResponse(BaseModel):
    query: Optional[str] = None
    page: int = 1
    limit: int = 24
    count: int = 0
    total: int = 0
    results: List[SearchResultItem] = []
    facets: Optional[SearchFacets] = None
    message: Optional[str] = None


class AutoSuggestResponse(BaseModel):
    query: str
    suggestions: List[str] = []
    matched_categories: List[Dict[str, str]] = []
    featured_products: List[Dict[str, Any]] = []
