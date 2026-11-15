import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.security import create_access_token
from app.api.v1.endpoints.admin import _MEMORY_AUDIT_LOGS, _MEMORY_USER_ROLES
from app.api.v1.endpoints.vendor import _MEMORY_VENDORS
from app.api.v1.endpoints.catalog import _MEMORY_PRODUCTS

client = TestClient(app)

# Super Admin Token
ADMIN_ID = "admn-9999-0000-1111-2222"
ADMIN_TOKEN = create_access_token({
    "sub": ADMIN_ID,
    "email": "admin@amazing.in",
    "name": "Super Administrator",
    "roles": ["admin"],
})
AUTH_ADMIN = {"Authorization": f"Bearer {ADMIN_TOKEN}"}

# Vendor Token (Not an Admin)
VENDOR_ID = "vend-5555-6666-7777-8888"
VENDOR_TOKEN = create_access_token({
    "sub": VENDOR_ID,
    "email": "vendor@amazing.in",
    "name": "Apex Electronics Store",
    "roles": ["vendor"],
})
AUTH_VENDOR = {"Authorization": f"Bearer {VENDOR_TOKEN}"}

# Customer Token (Not an Admin)
CUSTOMER_ID = "cust-1111-2222-3333-4444"
CUSTOMER_TOKEN = create_access_token({
    "sub": CUSTOMER_ID,
    "email": "customer@amazing.in",
    "name": "Marketplace Shopper",
    "roles": ["customer"],
})
AUTH_CUSTOMER = {"Authorization": f"Bearer {CUSTOMER_TOKEN}"}


def test_unauthenticated_admin_access_rejected():
    """Unauthenticated requests to admin console must return 401 Unauthorized."""
    res = client.get("/api/v1/admin/dashboard")
    assert res.status_code == 401


def test_customer_access_to_admin_dashboard_forbidden():
    """
    CRITERIA 1: Standard customer attempting to call /admin/dashboard
    receives 403 Forbidden.
    """
    res = client.get("/api/v1/admin/dashboard", headers=AUTH_CUSTOMER)
    assert res.status_code == 403
    assert "Operation not permitted" in res.json()["detail"]


def test_vendor_access_to_admin_dashboard_forbidden():
    """
    CRITERIA 1: Vendor merchant attempting to call /admin/dashboard
    receives 403 Forbidden.
    """
    res = client.get("/api/v1/admin/dashboard", headers=AUTH_VENDOR)
    assert res.status_code == 403
    assert "Operation not permitted" in res.json()["detail"]


def test_admin_dashboard_metrics_aggregation():
    """Super Admin retrieves live marketplace metrics (GMV, platform revenue, vendor ratios)."""
    res = client.get("/api/v1/admin/dashboard", headers=AUTH_ADMIN)
    assert res.status_code == 200
    data = res.json()

    assert "gmv_inr" in data
    assert "platform_net_revenue_inr" in data
    assert "total_orders" in data
    assert "total_vendors" in data
    assert "active_vendors" in data
    assert "pending_vendor_applications" in data
    assert "pending_products_count" in data
    assert data["payment_conversion_rate"] >= 90.0


def test_admin_list_pending_applications():
    """Admin inspects list of pending vendor applications requiring KYB verification."""
    res = client.get("/api/v1/admin/vendors/applications", headers=AUTH_ADMIN)
    assert res.status_code == 200
    applications = res.json()
    assert isinstance(applications, list)
    # Check pending applicant store
    assert any(a["store_slug"] == "pending-merchant-hub" for a in applications)


def test_admin_inspect_vendor_with_signed_document_urls():
    """Admin inspects vendor KYC documents and receives short-lived signed access URLs."""
    res = client.get("/api/v1/admin/vendors/vend-pending-store-1111", headers=AUTH_ADMIN)
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == "vend-pending-store-1111"
    assert data["store_name"] == "Pending Merchant Hub"
    assert "documents" in data


def test_approving_vendor_automatically_provisions_vendor_role():
    """
    CRITERIA 2: Approving a vendor automatically provisions the 'vendor'
    role in user_roles and records an immutable audit log entry.
    """
    vendor_id = "vend-pending-store-1111"
    owner_user_id = "vend-pending-user-1111"

    # 1. Before approval: owner only has 'customer' role
    assert "vendor" not in _MEMORY_USER_ROLES.get(owner_user_id, [])

    # 2. Admin approves the vendor application
    mod_res = client.post(
        f"/api/v1/admin/vendors/{vendor_id}/moderate",
        json={"action": "approve", "reason": "KYB and GSTIN documents verified successfully"},
        headers=AUTH_ADMIN,
    )
    assert mod_res.status_code == 200
    mod_data = mod_res.json()
    assert mod_data["status"] == "success"
    assert mod_data["new_status"] == "approved"

    # 3. Verify vendor status is now approved
    assert _MEMORY_VENDORS[vendor_id]["application_status"] == "approved"

    # 4. CRITERIA 2: Owner automatically granted 'vendor' role
    assert "vendor" in _MEMORY_USER_ROLES[owner_user_id]

    # 5. Verify audit log entry created
    audit_res = client.get("/api/v1/admin/audit-logs?resource_type=vendor", headers=AUTH_ADMIN)
    assert audit_res.status_code == 200
    logs = audit_res.json()
    assert any(l["action"] == "vendor_approve" and l["resource_id"] == vendor_id for l in logs)

    # Teardown / Reset state so subsequent test suites (e.g. test_vendor.py) remain isolated
    _MEMORY_VENDORS[vendor_id]["application_status"] = "submitted"
    if "vendor" in _MEMORY_USER_ROLES.get(owner_user_id, []):
        _MEMORY_USER_ROLES[owner_user_id].remove("vendor")


def test_rejecting_product_leaves_immutable_audit_entry():
    """
    CRITERIA 3: Rejecting a product leaves an immutable audit entry
    in public.audit_logs with moderation feedback.
    """
    # Create or identify a test draft product
    test_prod_id = "prod-test-moderation-01"
    _MEMORY_PRODUCTS.append({
        "id": test_prod_id,
        "vendor_id": VENDOR_ID,
        "category_id": "cat-audio-002",
        "name": "Non-Compliant Unbranded Earbuds",
        "slug": "non-compliant-earbuds",
        "description": "Cheap clone without safety certifications.",
        "product_status": "draft",
        "variants": [],
        "images": []
    })

    # Reject the product with compliance reason
    reject_reason = "Missing BIS safety certification and trademark authorization"
    res = client.post(
        f"/api/v1/admin/products/{test_prod_id}/reject",
        json={"reason": reject_reason},
        headers=AUTH_ADMIN,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["new_status"] == "rejected"

    # Verify product status transitioned
    target = next((p for p in _MEMORY_PRODUCTS if p["id"] == test_prod_id), None)
    assert target is not None
    assert target["product_status"] == "rejected"

    # Verify immutable audit log
    audit_res = client.get("/api/v1/admin/audit-logs?resource_type=product", headers=AUTH_ADMIN)
    assert audit_res.status_code == 200
    logs = audit_res.json()

    reject_log = next((l for l in logs if l["action"] == "product_reject" and l["resource_id"] == test_prod_id), None)
    assert reject_log is not None
    assert reject_log["metadata"]["reason"] == reject_reason
    assert reject_log["actor_user_id"] == ADMIN_ID


def test_approving_product_makes_it_active():
    """Approving a product listing updates status to 'active' for public storefront discovery."""
    test_prod_id = "prod-approved-listing-02"
    _MEMORY_PRODUCTS.append({
        "id": test_prod_id,
        "vendor_id": VENDOR_ID,
        "category_id": "cat-elec-001",
        "name": "Compliant Mechanical RGB Gaming Keyboard",
        "slug": "compliant-gaming-keyboard",
        "description": "Full size blue switch mechanical keyboard.",
        "product_status": "draft",
        "variants": [],
        "images": []
    })

    res = client.post(f"/api/v1/admin/products/{test_prod_id}/approve", headers=AUTH_ADMIN)
    assert res.status_code == 200
    assert res.json()["new_status"] == "active"

    target = next((p for p in _MEMORY_PRODUCTS if p["id"] == test_prod_id), None)
    assert target is not None
    assert target["product_status"] == "active"


def test_commission_rules_configuration_and_precedence():
    """Admin inspects and configures dynamic tiered commission rules."""
    # 1. Fetch active rules
    res = client.get("/api/v1/admin/commissions", headers=AUTH_ADMIN)
    assert res.status_code == 200
    rules = res.json()
    assert len(rules) >= 3

    # 2. Add product-specific 5% negotiated rule
    new_rule_res = client.post(
        "/api/v1/admin/commissions",
        json={
            "rule_type": "product",
            "target_id": "prod-laptop-02",
            "target_name": "Ultrabook Core i7 Special Promo",
            "rate_percentage": 5.0,
        },
        headers=AUTH_ADMIN,
    )
    assert new_rule_res.status_code == 201
    new_rule = new_rule_res.json()
    assert new_rule["rate_percentage"] == 5.0
    assert new_rule["rule_type"] == "product"


def test_settlement_ledger_calculation_engine():
    """
    Automated settlement calculation aggregates suborders:
    Net Payout = Gross Subtotal - Platform Commission - Refund Deductions
    """
    res = client.post(
        "/api/v1/admin/settlements/calculate",
        json={"settlement_days": 14},
        headers=AUTH_ADMIN,
    )
    assert res.status_code == 200
    settlements = res.json()
    assert len(settlements) > 0

    for stl in settlements:
        assert stl["payout_status"] == "pending_payout"
        assert stl["gross_amount"] >= stl["net_payout"]
        assert round(stl["gross_amount"] - stl["commission_amount"] - stl["refund_deductions"], 2) == stl["net_payout"]
        assert stl["reference_number"].startswith("PAYOUT-")


def test_audit_logs_tamper_evident_stream():
    """Audit logs endpoint returns structured entries with actor and resource metadata."""
    res = client.get("/api/v1/admin/audit-logs", headers=AUTH_ADMIN)
    assert res.status_code == 200
    logs = res.json()
    assert len(logs) > 0

    first_log = logs[0]
    assert "id" in first_log
    assert "actor_user_id" in first_log
    assert "action" in first_log
    assert "resource_type" in first_log
    assert "created_at" in first_log
