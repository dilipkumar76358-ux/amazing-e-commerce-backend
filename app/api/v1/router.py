from fastapi import APIRouter
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.catalog import router as catalog_router
from app.api.v1.endpoints.search import router as search_router
from app.api.v1.endpoints.cart import router as cart_router
from app.api.v1.endpoints.wishlist import router as wishlist_router
from app.api.v1.endpoints.address import router as address_router
from app.api.v1.endpoints.coupons import router as coupons_router
from app.api.v1.endpoints.orders import router as orders_router
from app.api.v1.endpoints.returns import router as returns_router
from app.api.v1.endpoints.reviews import router as reviews_router
from app.api.v1.endpoints.checkout import router as checkout_router
from app.api.v1.endpoints.vendor import router as vendor_router
from app.api.v1.endpoints.admin import router as admin_router

api_v1_router = APIRouter()
api_v1_router.include_router(health_router)
api_v1_router.include_router(auth_router)
api_v1_router.include_router(catalog_router)
api_v1_router.include_router(search_router)
api_v1_router.include_router(cart_router)
api_v1_router.include_router(wishlist_router)
api_v1_router.include_router(address_router)
api_v1_router.include_router(coupons_router)
api_v1_router.include_router(orders_router)
api_v1_router.include_router(returns_router)
api_v1_router.include_router(reviews_router)
api_v1_router.include_router(checkout_router)
api_v1_router.include_router(vendor_router)
api_v1_router.include_router(admin_router)

