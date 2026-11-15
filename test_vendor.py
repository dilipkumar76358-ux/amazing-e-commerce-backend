import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.security import create_access_token
from app.services.payment import generate_gateway_signature
from app.api.v1.endpoints.vendor import _MEMORY_SUBORDERS_LIST, _MEMORY_VENDORS
from app.api.v1.endpoints.catalog import _MEMORY_PRODUCTS

client = TestClient(app)

# Vendor A (Apex Electronics Store - Approved)
VENDOR_A_ID = "vend-5555-6666-7777-8888"
VENDOR_A_TOKEN = create_access_token({
    "sub": VENDOR_A_ID,
    "email": "vendor_a@amazing.in",
    "name": "Apex Electronics Store",
    "roles": ["vendor"],
})
AUTH_VENDOR_A = {"Authorization": f"Bearer {VENDOR_A_TOKEN}"}

# Vendor B (StrideStyle Apparel / Other Merchant - Approved)
VENDOR_B_USER_ID = "vend-other-9999-0000"
VENDOR_B_TOKEN = create_access_token({
    "sub": VENDOR_B_USER_ID,
    "email": "vendor_b@amazing.in",
    "name": "Other Merchant Store",
    "roles": ["vendor"],
})
AUTH_VENDOR_B = {"Authorization": f"Bearer {VENDOR_B_TOKEN}"}

# Vendor Pending (Submitted Application - Not yet Approved)
VENDOR_PENDING_USER_ID = "vend-pending-user-1111"
VENDOR_PENDING_TOKEN = create_access_token({
    "sub": VENDOR_PENDING_USER_ID,
    "email": "pending_vendor@amazing.in",
    "name": "Pending Merchant Hub",
    "roles": ["vendor"],
})
AUTH_VENDOR_PENDING = {"Authorization": f"Bearer {VENDOR_PENDING_TOKEN}"}

# Standard Customer (Not a vendor)
CUSTOMER_USER_ID = "cust-1111-2222-3333-4444"
CUSTOMER_TOKEN = create_access_token({
    "sub": CUSTOMER_USER_ID,
    "email": "customer@amazing.in",
    "name": "Marketplace Shopper",
    "roles": ["customer"],
})
AUTH_CUSTOMER = {"Authorization": f"Bearer {CUSTOMER_TOKEN}"}


def test_unauthenticated_vendor_access_rejected():
    """Unauthenticated requests to vendor endpoints must return 401 Unauthorized."""
    res = client.get("/api/v1/vendor/dashboard")
    assert res.status_code == 401


def test_non_vendor_profile_rejected():
    """Users without an associated vendor store profile receive 403 Forbidden."""
    res = client.get("/api/v1/vendor/dashboard", headers=AUTH_CUSTOMER)
    assert res.status_code == 403
    assert "No vendor profile associated with this account" in res.json()["detail"]


def test_submitted_vendor_application_status_restricted():
    """
    CRITERIA 2: A vendor with application_status = 'submitted'
    receives 403 Access Restricted on the dashboard.
    """
    res = client.get("/api/v1/vendor/dashboard", headers=AUTH_VENDOR_PENDING)
    assert res.status_code == 403
    detail = res.json()["detail"]
    assert "Vendor application is currently submitted" in detail
    assert "Access restricted" in detail


def test_vendor_dashboard_metrics_calculation():
    """Approved vendor accesses dashboard and receives computed performance metrics."""
    res = client.get("/api/v1/vendor/dashboard", headers=AUTH_VENDOR_A)
    assert res.status_code == 200
    data = res.json()

    assert "total_products" in data
    assert "active_products" in data
    assert "low_stock_count" in data
    assert "pending_orders" in data
    assert "gross_sales" in data
    assert "total_commissions" in data
    assert "net_earnings" in data

    # Verify mathematical consistency: net_earnings = gross_sales - total_commissions
    assert round(data["gross_sales"] - data["total_commissions"], 2) == data["net_earnings"]


def test_tenant_isolation_suborders_listing():
    """
    Vendor A only sees their own assigned suborders.
    Vendor B's suborders are strictly filtered out.
    """
    res_a = client.get("/api/v1/vendor/suborders", headers=AUTH_VENDOR_A)
    assert res_a.status_code == 200
    suborders_a = res_a.json()
    assert len(suborders_a) > 0

    for sub in suborders_a:
        assert sub["vendor_id"] == VENDOR_A_ID
        assert sub["store_name"] == "Apex Electronics Store"

    # Vendor B listing
    res_b = client.get("/api/v1/vendor/suborders", headers=AUTH_VENDOR_B)
    assert res_b.status_code == 200
    suborders_b = res_b.json()
    for sub in suborders_b:
        assert sub["vendor_id"] == "vend-9999-8888-7777-6666"


def test_tenant_isolation_suborders_status_filtering():
    """Vendors can filter suborders by fulfillment status (e.g. unfulfilled vs shipped)."""
    # Filter for unfulfilled orders
    res_unf = client.get("/api/v1/vendor/suborders?status=unfulfilled", headers=AUTH_VENDOR_A)
    assert res_unf.status_code == 200
    for order in res_unf.json():
        assert order["fulfillment_status"] == "unfulfilled"

    # Filter for shipped orders
    res_shipped = client.get("/api/v1/vendor/suborders?status=shipped", headers=AUTH_VENDOR_A)
    assert res_shipped.status_code == 200
    for order in res_shipped.json():
        assert order["fulfillment_status"] == "shipped"


def test_tenant_isolation_suborder_detail_access():
    """Vendor B attempting to view Vendor A's suborder detail receives 404 Not Found."""
    suborder_a_id = "subord-apex-001"

    # Vendor A can view own suborder
    ok_res = client.get(f"/api/v1/vendor/suborders/{suborder_a_id}", headers=AUTH_VENDOR_A)
    assert ok_res.status_code == 200
    assert ok_res.json()["id"] == suborder_a_id

    # Vendor B attempting to view Vendor A's suborder -> 404 Not Found
    unauth_res = client.get(f"/api/v1/vendor/suborders/{suborder_a_id}", headers=AUTH_VENDOR_B)
    assert unauth_res.status_code == 404
    assert "Suborder not found or unauthorized" in unauth_res.json()["detail"]


def test_tenant_isolation_vendor_b_cannot_dispatch_vendor_a_suborder():
    """
    CRITERIA 1: Vendor B attempting to dispatch Vendor A's suborder receives 404 Not Found.
    """
    suborder_a_id = "subord-apex-001"
    dispatch_payload = {
        "carrier": "Delhivery",
        "tracking_number": "DLV123456789"
    }

    # Vendor B tries to dispatch Vendor A's order -> BLOCKED with 404
    blocked_res = client.post(
        f"/api/v1/vendor/suborders/{suborder_a_id}/dispatch",
        json=dispatch_payload,
        headers=AUTH_VENDOR_B,
    )
    assert blocked_res.status_code == 404
    assert "Suborder not found or unauthorized" in blocked_res.json()["detail"]


def test_vendor_a_can_dispatch_own_suborder():
    """Vendor A successfully dispatches their own unfulfilled suborder and attaches tracking."""
    # Reset suborder state if needed
    target = next((s for s in _MEMORY_SUBORDERS_LIST if s["id"] == "subord-apex-001"), None)
    if target:
        target["fulfillment_status"] = "unfulfilled"
        target["carrier"] = None
        target["tracking_number"] = None

    dispatch_payload = {
        "carrier": "BlueDart Express",
        "tracking_number": "BD9988776655IN"
    }

    res = client.post(
        "/api/v1/vendor/suborders/subord-apex-001/dispatch",
        json=dispatch_payload,
        headers=AUTH_VENDOR_A,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["fulfillment_status"] == "shipped"
    assert data["carrier"] == "BlueDart Express"
    assert data["tracking_number"] == "BD9988776655IN"

    # Verify state in suborder details
    detail_res = client.get("/api/v1/vendor/suborders/subord-apex-001", headers=AUTH_VENDOR_A)
    assert detail_res.status_code == 200
    assert detail_res.json()["fulfillment_status"] == "shipped"
    assert detail_res.json()["tracking_number"] == "BD9988776655IN"


def test_cannot_dispatch_already_shipped_suborder():
    """Dispatching a suborder that is already in 'shipped' state returns 400 Bad Request."""
    res = client.post(
        "/api/v1/vendor/suborders/subord-apex-001/dispatch",
        json={"carrier": "DTDC", "tracking_number": "DTDC112233"},
        headers=AUTH_VENDOR_A,
    )
    assert res.status_code == 400
    assert "Cannot dispatch suborder in shipped state" in res.json()["detail"]


def test_dispatch_invalid_payload_rejected():
    """Empty or missing tracking code and carrier fails schema validation with 422."""
    res = client.post(
        "/api/v1/vendor/suborders/subord-apex-001/dispatch",
        json={"carrier": "", "tracking_number": ""},
        headers=AUTH_VENDOR_A,
    )
    assert res.status_code == 422


def test_stock_updates_immediately_reflect_on_public_pdp():
    """
    CRITERIA 3: Stock updates immediately reflect on the public product detail page.
    """
    variant_id = "var-hp-black"
    product_id = "prod-headphones-01"

    # 1. Update available stock to 88 and selling price to 2050.00
    patch_res = client.patch(
        f"/api/v1/vendor/inventory/{variant_id}",
        json={"available_stock": 88, "selling_price": 2050.00},
        headers=AUTH_VENDOR_A,
    )
    assert patch_res.status_code == 200
    patched_data = patch_res.json()
    assert patched_data["available_stock"] == 88
    assert patched_data["selling_price"] == 2050.00

    # 2. Query public Product Detail Page (PDP)
    pdp_res = client.get(f"/api/v1/products/{product_id}")
    assert pdp_res.status_code == 200
    pdp_data = pdp_res.json()

    # Find the variant on the public PDP
    pdp_variant = next((v for v in pdp_data["variants"] if v["id"] == variant_id), None)
    assert pdp_variant is not None
    assert pdp_variant["available_stock"] == 88
    assert pdp_variant["selling_price"] == 2050.00


def test_cross_tenant_inventory_update_blocked():
    """Vendor B cannot modify stock or price of Vendor A's product variants (403 Forbidden)."""
    variant_id = "var-hp-silver"  # Owned by Vendor A (Apex)

    res = client.patch(
        f"/api/v1/vendor/inventory/{variant_id}",
        json={"available_stock": 999, "selling_price": 10.00},
        headers=AUTH_VENDOR_B,  # Vendor B tries to alter Vendor A's stock
    )
    assert res.status_code == 403
    assert "You do not have permission to manage this variant" in res.json()["detail"]


def test_inventory_negative_values_rejected():
    """Negative prices or stock quantities fail validation with 422 Unprocessable Entity."""
    variant_id = "var-hp-black"

    res = client.patch(
        f"/api/v1/vendor/inventory/{variant_id}",
        json={"selling_price": -100.0, "available_stock": -5},
        headers=AUTH_VENDOR_A,
    )
    assert res.status_code == 422


def test_vendor_check_slug_availability():
    """Slug availability endpoint correctly distinguishes registered vs available slugs."""
    # Already taken slug
    taken_res = client.get("/api/v1/vendor/check-slug?slug=apex-electronics-store")
    assert taken_res.status_code == 200
    assert taken_res.json()["is_available"] is False

    # Available new slug
    avail_res = client.get("/api/v1/vendor/check-slug?slug=brand-new-artisan-store-unique")
    assert avail_res.status_code == 200
    assert avail_res.json()["is_available"] is True


def test_vendor_onboarding_application_flow():
    """New vendor can submit an onboarding application with GSTIN and PAN validation."""
    new_user_id = "new-applicant-9876-5432"
    new_user_token = create_access_token({
        "sub": new_user_id,
        "email": "newvendor@amazing.in",
        "name": "Himalayan Handcrafts",
        "roles": ["customer"],
    })
    new_auth = {"Authorization": f"Bearer {new_user_token}"}

    payload = {
        "store_name": "Himalayan Handcrafts & Decor",
        "store_slug": "himalayan-handcrafts-decor",
        "business_type": "proprietorship",
        "legal_business_name": "Himalayan Handcrafts Enterprise",
        "contact_phone": "+919876501234",
        "business_address": {
            "address_line_1": "Mall Road, Near Clock Tower",
            "city": "Shimla",
            "state": "Himachal Pradesh",
            "postal_code": "171001",
            "country": "India"
        },
        "gstin": "02AABCH1234D1Z5",
        "pan_number": "AABCH1234D",
        "bank_account": {
            "account_holder_name": "Himalayan Handcrafts Enterprise",
            "account_number": "50100234567890",
            "ifsc_code": "SBIN0001234",
            "bank_name": "State Bank of India"
        },
        "documents": [
            {
                "document_type": "gst_certificate",
                "storage_path": "vendor-documents/new-applicant/gst.pdf"
            }
        ]
    }

    apply_res = client.post("/api/v1/vendor/apply", json=payload, headers=new_auth)
    assert apply_res.status_code == 201
    app_data = apply_res.json()
    assert app_data["store_name"] == "Himalayan Handcrafts & Decor"
    assert app_data["application_status"] == "submitted"
    assert app_data["gstin"] == "02AABCH1234D1Z5"

    # Profile lookup returns submitted status
    prof_res = client.get("/api/v1/vendor/profile", headers=new_auth)
    assert prof_res.status_code == 200
    assert prof_res.json()["application_status"] == "submitted"


def test_end_to_end_checkout_to_vendor_fulfillment_flow():
    """
    End-to-End Integration Flow:
    1. Customer adds Vendor A's product to cart and completes Razorpay checkout.
    2. Vendor A inspects /api/v1/vendor/suborders and finds the new suborder in unfulfilled state.
    3. Vendor A dispatches the order with carrier tracking.
    4. Verified suborder fulfillment transitions to 'shipped'.
    """
    # 1. Customer initiates checkout with Headphones (Vendor A: Apex)
    client.delete("/api/v1/cart/clear", headers=AUTH_CUSTOMER)
    client.post(
        "/api/v1/cart/items",
        json={"variant_id": "var-hp-black", "quantity": 1},
        headers=AUTH_CUSTOMER,
    )

    init_res = client.post(
        "/api/v1/checkout/initiate",
        json={"address_id": "addr-demo-01"},
        headers=AUTH_CUSTOMER,
    )
    assert init_res.status_code == 200
    init_data = init_res.json()
    order_id = init_data["order_id"]
    gateway_order_id = init_data["gateway_order_id"]
    payment_id = "pay_e2e_vendor_test_888"

    # Verify signature
    valid_sig = generate_gateway_signature(order_id=gateway_order_id, payment_id=payment_id)
    verify_res = client.post(
        "/api/v1/payments/verify",
        json={
            "order_id": order_id,
            "razorpay_order_id": gateway_order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": valid_sig,
        },
        headers=AUTH_CUSTOMER,
    )
    assert verify_res.status_code == 200

    # 2. Vendor A inspects suborders
    suborders_res = client.get("/api/v1/vendor/suborders?status=unfulfilled", headers=AUTH_VENDOR_A)
    assert suborders_res.status_code == 200
    vendor_orders = suborders_res.json()

    # Find the newly placed suborder
    target_suborder = next((o for o in vendor_orders if o["order_id"] == order_id), None)
    assert target_suborder is not None
    assert target_suborder["fulfillment_status"] == "unfulfilled"
    assert target_suborder["vendor_id"] == VENDOR_A_ID

    # 3. Vendor A dispatches the new suborder
    dispatch_res = client.post(
        f"/api/v1/vendor/suborders/{target_suborder['id']}/dispatch",
        json={
            "carrier": "Delhivery Logistics",
            "tracking_number": "DELHIVERY-E2E-9988",
        },
        headers=AUTH_VENDOR_A,
    )
    assert dispatch_res.status_code == 200
    assert dispatch_res.json()["fulfillment_status"] == "shipped"

    # 4. Confirm suborder is now marked as shipped
    sub_detail = client.get(f"/api/v1/vendor/suborders/{target_suborder['id']}", headers=AUTH_VENDOR_A)
    assert sub_detail.status_code == 200
    assert sub_detail.json()["fulfillment_status"] == "shipped"
    assert sub_detail.json()["tracking_number"] == "DELHIVERY-E2E-9988"
