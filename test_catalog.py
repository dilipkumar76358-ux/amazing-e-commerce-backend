import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.security import create_access_token

client = TestClient(app)


@pytest.fixture
def vendor_token():
    return create_access_token({
        "sub": "vend-5555-6666-7777-8888",
        "email": "vendor@amazing.in",
        "name": "Apex Electronics Store",
        "roles": ["vendor"]
    })


@pytest.fixture
def other_vendor_token():
    return create_access_token({
        "sub": "vend-other-9999-0000",
        "email": "other_vendor@amazing.in",
        "name": "Other Merchant Store",
        "roles": ["vendor"]
    })


@pytest.fixture
def admin_token():
    return create_access_token({
        "sub": "admn-9999-0000-1111-2222",
        "email": "admin@amazing.in",
        "name": "Super Admin",
        "roles": ["admin"]
    })


def test_category_tree_hierarchy():
    """Verify that child categories are nested properly under their parent categories."""
    response = client.get("/api/v1/categories")
    assert response.status_code == 200
    categories = response.json()
    assert len(categories) > 0

    # Electronics category must nest Audio and Mobiles
    elec = next((c for c in categories if c["slug"] == "electronics"), None)
    assert elec is not None
    assert len(elec["subcategories"]) >= 2
    sub_slugs = [s["slug"] for s in elec["subcategories"]]
    assert "audio-headphones" in sub_slugs
    assert "mobiles-accessories" in sub_slugs


def test_category_detail_by_slug():
    """Retrieving a category by slug returns its detail and subcategory structure."""
    response = client.get("/api/v1/categories/audio-headphones")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Audio & Headphones"


def test_public_product_listing_and_detail():
    """Paginated product catalog returns products with active variants and images."""
    response = client.get("/api/v1/products")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert data["total"] >= 1

    prod_id = data["items"][0]["id"]
    detail_res = client.get(f"/api/v1/products/{prod_id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert len(detail["variants"]) > 0
    assert "vendor_store_name" in detail


def test_vendor_create_product(vendor_token):
    """Authenticated vendor can create a new draft product with images."""
    payload = {
        "category_id": "cat-audio-002",
        "name": "Studio Reference Monitor Speakers",
        "slug": "studio-reference-monitor-speakers",
        "description": "Nearfield professional bi-amplified studio monitor pair.",
        "images": [
            {
                "storage_path": "products/sample/studio_mon.webp",
                "alt_text": "Studio monitor pair front view",
                "sort_order": 0
            }
        ],
        "initial_variant": {
            "sku": "STUDIO-MON-01",
            "variant_attributes": {"size": "5-inch"},
            "selling_price": 8499.00,
            "compare_at_price": 11999.00,
            "initial_stock": 25,
            "is_active": True
        }
    }
    response = client.post(
        "/api/v1/vendor/products",
        json=payload,
        headers={"Authorization": f"Bearer {vendor_token}"}
    )
    assert response.status_code == 201
    created = response.json()
    assert created["product_status"] == "draft"
    assert created["min_price"] == 8499.00
    assert len(created["images"]) == 1


def test_cannot_add_negative_price_variant(vendor_token):
    """Products cannot be published with negative pricing."""
    prod_id = "prod-headphones-01"
    response = client.post(
        f"/api/v1/vendor/products/{prod_id}/variants",
        json={
            "sku": "INVALID-PRICE-SKU",
            "selling_price": -500.00,
            "initial_stock": 10
        },
        headers={"Authorization": f"Bearer {vendor_token}"}
    )
    assert response.status_code in [400, 422]


def test_variant_ownership_enforcement(vendor_token, other_vendor_token, admin_token):
    """Only the owning vendor or an administrator can add variants to a product."""
    prod_id = "prod-headphones-01"

    # 1. Other vendor attempts to add variant -> BLOCKED with 403 Forbidden
    other_res = client.post(
        f"/api/v1/vendor/products/{prod_id}/variants",
        json={
            "sku": "UNAUTHORIZED-VAR-SKU",
            "selling_price": 2500.00,
            "initial_stock": 5
        },
        headers={"Authorization": f"Bearer {other_vendor_token}"}
    )
    assert other_res.status_code == 403

    # 2. Owning vendor adds variant -> ALLOWED (201 Created)
    owner_res = client.post(
        f"/api/v1/vendor/products/{prod_id}/variants",
        json={
            "sku": "HP-ANC-BLUE-VND",
            "variant_attributes": {"color": "Ocean Blue"},
            "selling_price": 2299.00,
            "initial_stock": 30
        },
        headers={"Authorization": f"Bearer {vendor_token}"}
    )
    assert owner_res.status_code == 201

    # 3. Admin adds variant -> ALLOWED (201 Created)
    admin_res = client.post(
        f"/api/v1/vendor/products/{prod_id}/variants",
        json={
            "sku": "HP-ANC-GOLD-ADM",
            "variant_attributes": {"color": "Champagne Gold"},
            "selling_price": 2499.00,
            "initial_stock": 15
        },
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert admin_res.status_code == 201
