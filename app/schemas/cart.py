from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class CartItemAddRequest(BaseModel):
    variant_id: str
    quantity: int = Field(default=1, ge=1)


class CartItemUpdateRequest(BaseModel):
    quantity: int = Field(default=1, ge=1)


class CartItemResponse(BaseModel):
    item_id: str
    variant_id: str
    product_id: str
    product_name: str
    product_slug: str
    vendor_id: str
    store_name: str
    sku: str
    selling_price: float
    compare_at_price: Optional[float] = None
    quantity: int
    current_stock: int
    is_available: bool
    line_total: float
    image_url: Optional[str] = None
    variant_attributes: Optional[Dict[str, Any]] = None


class VendorGroupResponse(BaseModel):
    vendor_id: str
    store_name: str
    subtotal: float
    items: List[CartItemResponse]


class CartResponse(BaseModel):
    cart_id: str
    item_subtotal: float
    shipping_total: float
    grand_total: float
    total_items: int
    free_shipping_threshold: float = 499.0
    amount_needed_for_free_shipping: float = 0.0
    vendor_groups: List[VendorGroupResponse]


class WishlistItemAddRequest(BaseModel):
    product_id: str


class WishlistItemResponse(BaseModel):
    id: str
    product_id: str
    name: str
    slug: str
    brand_name: Optional[str] = None
    average_rating: float = 0.0
    review_count: int = 0
    min_variant_price: float
    max_compare_price: Optional[float] = None
    primary_image: Optional[str] = None
    in_stock: bool = True
    created_at: Optional[str] = None


class WishlistResponse(BaseModel):
    wishlist_id: str
    total_items: int
    items: List[WishlistItemResponse]
