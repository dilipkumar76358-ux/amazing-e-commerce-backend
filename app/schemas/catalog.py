from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime


class CategoryBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    slug: str = Field(..., min_length=2, max_length=120)
    description: Optional[str] = None
    image_url: Optional[str] = None
    sort_order: int = 0
    is_active: bool = True
    parent_id: Optional[str] = None


class CategoryResponse(CategoryBase):
    id: str
    created_at: Optional[datetime] = None


class CategoryTreeResponse(CategoryResponse):
    subcategories: List["CategoryTreeResponse"] = []


class ProductImageCreate(BaseModel):
    storage_path: str
    alt_text: Optional[str] = None
    variant_id: Optional[str] = None
    sort_order: int = 0


class ProductImageResponse(BaseModel):
    id: str
    product_id: str
    variant_id: Optional[str] = None
    storage_path: str
    url: Optional[str] = None
    alt_text: Optional[str] = None
    sort_order: int = 0


class ProductVariantCreate(BaseModel):
    sku: str = Field(..., min_length=3, max_length=100)
    variant_attributes: Dict[str, Any] = Field(default_factory=dict)
    selling_price: float = Field(..., ge=0, description="Selling price must be non-negative")
    compare_at_price: Optional[float] = None
    weight_grams: int = 0
    initial_stock: int = Field(default=0, ge=0)
    is_active: bool = True

    @field_validator("selling_price")
    @classmethod
    def validate_price(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Selling price cannot be negative")
        return v


class ProductVariantResponse(BaseModel):
    id: str
    product_id: str
    sku: str
    variant_attributes: Dict[str, Any]
    selling_price: float
    compare_at_price: Optional[float] = None
    weight_grams: int = 0
    available_stock: int = 0
    is_active: bool = True


class ProductCreateRequest(BaseModel):
    category_id: str
    brand_id: Optional[str] = None
    name: str = Field(..., min_length=3, max_length=255)
    slug: str = Field(..., min_length=3, max_length=280)
    description: Optional[str] = None
    images: List[ProductImageCreate] = Field(default_factory=list)
    initial_variant: Optional[ProductVariantCreate] = None


class ProductResponse(BaseModel):
    id: str
    vendor_id: str
    category_id: str
    brand_id: Optional[str] = None
    name: str
    slug: str
    description: Optional[str] = None
    product_status: str
    average_rating: float = 0.00
    review_count: int = 0
    min_price: Optional[float] = None
    primary_image_url: Optional[str] = None
    category_name: Optional[str] = None


class ProductDetailResponse(ProductResponse):
    variants: List[ProductVariantResponse] = []
    images: List[ProductImageResponse] = []
    vendor_store_name: Optional[str] = None


class PaginatedProductsResponse(BaseModel):
    items: List[ProductResponse]
    total: int
    page: int
    limit: int
    total_pages: int
