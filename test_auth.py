import pytest
from datetime import timedelta
from fastapi.testclient import TestClient
from app.main import app
from app.core.security import create_access_token

client = TestClient(app)


@pytest.fixture
def customer_token():
    return create_access_token({
        "sub": "cust-1111-2222-3333-4444",
        "email": "customer@amazing.in",
        "name": "Priya Sharma",
        "roles": ["customer"]
    })


@pytest.fixture
def vendor_token():
    return create_access_token({
        "sub": "vend-5555-6666-7777-8888",
        "email": "vendor@amazing.in",
        "name": "Apex Electronics Store",
        "roles": ["customer", "vendor"]
    })


@pytest.fixture
def admin_token():
    return create_access_token({
        "sub": "admn-9999-0000-1111-2222",
        "email": "admin@amazing.in",
        "name": "Super Admin",
        "roles": ["admin"]
    })


def test_unauthenticated_request_rejected():
    """Unauthenticated request must return 401 Unauthorized."""
    response = client.get("/api/v1/me")
    assert response.status_code == 401
    assert "detail" in response.json()


def test_invalid_token_rejected():
    """Malformed or invalid JWT must return 401 Unauthorized."""
    response = client.get(
        "/api/v1/me",
        headers={"Authorization": "Bearer invalid_garbage_token"}
    )
    assert response.status_code == 401


def test_expired_token_rejected():
    """Expired JWT must return 401 Unauthorized."""
    expired_token = create_access_token(
        {"sub": "expired-user", "roles": ["customer"]},
        expires_delta=timedelta(seconds=-10)
    )
    response = client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {expired_token}"}
    )
    assert response.status_code == 401


def test_customer_token_access(customer_token):
    """Customer can query own profile but is blocked from admin dashboard with 403."""
    # 1. Successful query to /api/v1/me
    response = client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {customer_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "customer@amazing.in"
    assert "customer" in data["roles"]

    # 2. Successful query to /api/v1/me/roles
    role_res = client.get(
        "/api/v1/me/roles",
        headers={"Authorization": f"Bearer {customer_token}"}
    )
    assert role_res.status_code == 200
    assert role_res.json()["roles"] == ["customer"]

    # 3. Blocked from admin dashboard with 403 Forbidden
    admin_res = client.get(
        "/api/v1/admin/dashboard",
        headers={"Authorization": f"Bearer {customer_token}"}
    )
    assert admin_res.status_code == 403
    assert "Operation not permitted" in admin_res.json()["detail"]


def test_vendor_token_access(vendor_token):
    """Vendor can access vendor catalog but is blocked from admin dashboard."""
    # 1. Vendor can access vendor catalog
    response = client.get(
        "/api/v1/vendor/products",
        headers={"Authorization": f"Bearer {vendor_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"

    # 2. Blocked from admin dashboard
    admin_res = client.get(
        "/api/v1/admin/dashboard",
        headers={"Authorization": f"Bearer {vendor_token}"}
    )
    assert admin_res.status_code == 403


def test_admin_token_access(admin_token):
    """Admin has access to both admin dashboard and vendor management."""
    # 1. Admin accesses /api/v1/admin/dashboard
    response = client.get(
        "/api/v1/admin/dashboard",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["privilege_level"] == "super_admin"

    # 2. Admin also accesses vendor catalog
    vendor_res = client.get(
        "/api/v1/vendor/products",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert vendor_res.status_code == 200
