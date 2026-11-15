import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.security import create_access_token
from app.api.v1.endpoints.catalog import _MEMORY_PRODUCTS
from app.api.v1.endpoints.checkout import _MEMORY_ORDERS
from app.api.v1.endpoints.returns import _MEMORY_RETURNS, _MEMORY_REFUNDS
from app.api.v1.endpoints.reviews import _MEMORY_REVIEWS

client = TestClient(app)

# Customer 1: Verified Buyer (has purchased prod-headphones-01 and prod-laptop-02)
BUYER_ID = "cust-1111-2222-3333-4444"
BUYER_TOKEN = create_access_token({
    "sub": BUYER_ID,
    "email": "customer@amazing.in",
    "name": "Marketplace Shopper",
    "roles": ["customer"],
})
AUTH_BUYER = {"Authorization": f"Bearer {BUYER_TOKEN}"}

# Customer 2: Non-Buyer (has never purchased prod-headphones-01)
NON_BUYER_ID = "cust-nonbuyer-8888-9999"
NON_BUYER_TOKEN = create_access_token({
    "sub": NON_BUYER_ID,
    "email": "nonbuyer@amazing.in",
    "name": "Browsing Visitor",
    "roles": ["customer"],
})
AUTH_NON_BUYER = {"Authorization": f"Bearer {NON_BUYER_TOKEN}"}

# Admin
ADMIN_ID = "admn-9999-0000-1111-2222"
ADMIN_TOKEN = create_access_token({
    "sub": ADMIN_ID,
    "email": "admin@amazing.in",
    "name": "Platform Administrator",
    "roles": ["admin"],
})
AUTH_ADMIN = {"Authorization": f"Bearer {ADMIN_TOKEN}"}

# Vendor
VENDOR_OWNER_ID = "vend-5555-6666-7777-8888"
VENDOR_TOKEN = create_access_token({
    "sub": VENDOR_OWNER_ID,
    "email": "vendor_a@amazing.in",
    "name": "Apex Electronics Store",
    "roles": ["vendor"],
})
AUTH_VENDOR = {"Authorization": f"Bearer {VENDOR_TOKEN}"}


# ============================================================================
# CRITERIA 1 & 2: VERIFIED REVIEWS TESTS
# ============================================================================

def test_unverified_buyer_review_submission_forbidden():
    """
    CRITERIA 1: Customers who did not purchase a product receive
    403 Only verified buyers can submit reviews.
    """
    target_product_id = "prod-headphones-01"

    # Non-buyer attempts to submit review
    res = client.post(
        f"/api/v1/products/{target_product_id}/reviews",
        json={
            "rating": 5,
            "title": "Looks good from pictures",
            "comment": "I didn't buy this but looks like high quality headphones.",
        },
        headers=AUTH_NON_BUYER,
    )
    assert res.status_code == 403
    assert "Only verified buyers can submit reviews" in res.json()["detail"]


def test_verified_buyer_rating_submission_and_instant_recalculation():
    """
    CRITERIA 2: Verified purchase customer submits rating.
    The endpoint immediately recalculates and updates products.average_rating
    and review_count.
    """
    target_product_id = "prod-headphones-01"

    # Product state before new review
    target_prod = next(p for p in _MEMORY_PRODUCTS if p["id"] == target_product_id)
    initial_count = len([r for r in _MEMORY_REVIEWS.values() if r.get("product_id") == target_product_id])

    # Buyer has purchased prod-headphones-01 in ord-demo-001
    res = client.post(
        f"/api/v1/products/{target_product_id}/reviews",
        json={
            "rating": 5,
            "title": "Outstanding Clarity and Noise Cancellation",
            "comment": "Used these for 2 weeks. Battery life is amazing and ANC blocks all subway noise.",
            "images": ["https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=500&q=80"]
        },
        headers=AUTH_BUYER,
    )
    assert res.status_code == 201
    rev_data = res.json()
    assert rev_data["rating"] == 5
    assert rev_data["is_verified_purchase"] is True
    assert rev_data["customer_name"] == "Marketplace Shopper"

    # CRITERIA 2: Verify immediate recalculation of product average_rating
    updated_prod = next(p for p in _MEMORY_PRODUCTS if p["id"] == target_product_id)
    assert updated_prod["review_count"] >= initial_count + 1
    assert 1.0 <= updated_prod["average_rating"] <= 5.0

    # Also verify GET /products/{id}/reviews returns updated summary and 5-star distribution
    summary_res = client.get(f"/api/v1/products/{target_product_id}/reviews")
    assert summary_res.status_code == 200
    summary = summary_res.json()
    assert summary["product_id"] == target_product_id
    assert summary["review_count"] == updated_prod["review_count"]
    assert summary["average_rating"] == updated_prod["average_rating"]
    assert summary["rating_distribution"]["5"] >= 1


def test_review_helpful_upvoting():
    """Customers can upvote helpful reviews."""
    res = client.post("/api/v1/reviews/rev-hp-01/helpful", headers=AUTH_BUYER)
    assert res.status_code == 200
    assert res.json()["status"] == "success"
    assert res.json()["helpful_votes"] >= 35


# ============================================================================
# CRITERIA 3: GST-COMPLIANT TAX INVOICE TESTS
# ============================================================================

def test_gst_invoice_intra_state_calculation_accuracy():
    """
    CRITERIA 3: Invoices accurately display HSN code and GST tax splits
    without calculation errors.
    Test Intra-State: Karnataka Vendor to Karnataka Customer (CGST 9% + SGST 9%).
    """
    res = client.get("/api/v1/orders/ord-demo-001/invoice", headers=AUTH_BUYER)
    assert res.status_code == 200
    inv = res.json()

    assert inv["invoice_number"].startswith("INV-2026-")
    assert inv["order_number"] == "ORD-20261025-001"
    assert inv["seller"]["gstin"] == "27AABCU9603R1ZX"
    assert "Karnataka" in inv["seller"]["address"]
    assert inv["billing_address"]["state"] == "Karnataka"

    # Intra-state validation
    tax = inv["tax_breakdown"]
    assert tax["inter_state"] is False
    assert tax["igst_amount"] == 0.0
    assert tax["cgst_amount"] > 0.0
    assert tax["sgst_amount"] > 0.0
    assert round(tax["cgst_amount"] + tax["sgst_amount"], 2) == round(
        sum(item["tax_amount"] for item in inv["items"]), 2
    )

    # Item validation with HSN code
    assert len(inv["items"]) >= 1
    item = inv["items"][0]
    assert item["hsn_code"] == "85183000"
    assert item["quantity"] == 2
    assert item["unit_price"] > 0.0
    assert item["line_total"] == 3998.00
    assert inv["grand_total"] == 3998.00


def test_gst_invoice_inter_state_calculation_accuracy():
    """
    CRITERIA 3: Invoices accurately display HSN code and GST tax splits
    without calculation errors.
    Test Inter-State: Karnataka Vendor to Maharashtra Customer (IGST 18%).
    """
    res = client.get("/api/v1/orders/ord-demo-002/invoice", headers=AUTH_BUYER)
    assert res.status_code == 200
    inv = res.json()

    assert inv["order_number"] == "ORD-20261025-002"
    assert inv["billing_address"]["state"] == "Maharashtra"

    # Inter-state validation (Karnataka seller -> Maharashtra buyer)
    tax = inv["tax_breakdown"]
    assert tax["inter_state"] is True
    assert tax["igst_rate"] == 18.0
    assert tax["igst_amount"] > 0.0
    assert tax["cgst_amount"] == 0.0
    assert tax["sgst_amount"] == 0.0

    # HSN code for laptop
    item = inv["items"][0]
    assert item["hsn_code"] == "84713010"
    assert item["line_total"] == 54990.00
    assert inv["grand_total"] == 54990.00


# ============================================================================
# 4-STAGE VISUAL SHIPMENT TRACKING TESTS
# ============================================================================

def test_visual_shipment_tracking_timeline():
    """
    Amazon-style 4-stage tracking timeline:
    Confirmed -> Shipped -> Out for Delivery -> Delivered.
    """
    # 1. Delivered order (ord-demo-001)
    res_del = client.get("/api/v1/orders/ord-demo-001/tracking", headers=AUTH_BUYER)
    assert res_del.status_code == 200
    data_del = res_del.json()

    assert data_del["current_stage"] == "delivered"
    assert data_del["carrier"] == "BlueDart"
    assert data_del["tracking_number"] == "BD89472918"
    assert "bluedart.com" in data_del["carrier_tracking_url"]
    assert data_del["is_return_eligible"] is True
    assert len(data_del["stages"]) == 4

    # All 4 stages completed
    assert all(st["status"] == "completed" for st in data_del["stages"])

    # 2. In-transit shipped order (ord-demo-003)
    res_ship = client.get("/api/v1/orders/ord-demo-003/tracking", headers=AUTH_BUYER)
    assert res_ship.status_code == 200
    data_ship = res_ship.json()
    assert data_ship["current_stage"] == "shipped"
    assert data_ship["carrier"] == "Delhivery"
    assert data_ship["is_return_eligible"] is False


# ============================================================================
# 7-DAY RETURN POLICY & REFUND DISPATCH TESTS
# ============================================================================

def test_return_eligible_within_7_days_success():
    """Delivered order within 7 days is accepted for return."""
    res = client.post(
        "/api/v1/orders/ord-demo-001/returns",
        json={
            "order_item_id": "item-ord-001",
            "quantity": 1,
            "reason": "defective",
            "description": "Right earbud crackling intermittently during call audio.",
        },
        headers=AUTH_BUYER,
    )
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "success"
    assert data["return_id"].startswith("ret-")
    return_id = data["return_id"]

    # Verify return record inspection
    ret_res = client.get(f"/api/v1/returns/{return_id}", headers=AUTH_BUYER)
    assert ret_res.status_code == 200
    ret_data = ret_res.json()
    assert ret_data["return_status"] == "requested"
    assert ret_data["quantity"] == 1
    assert ret_data["refund_amount"] == 1999.00


def test_return_rejected_past_7_day_window():
    """Order delivered more than 7 days ago is rejected for return."""
    res = client.post(
        "/api/v1/orders/ord-demo-002/returns",
        json={
            "order_item_id": "item-ord-002",
            "quantity": 1,
            "reason": "size_issue",
            "description": "Want to exchange.",
        },
        headers=AUTH_BUYER,
    )
    assert res.status_code == 400
    assert "Return window has expired" in res.json()["detail"]


def test_return_rejected_for_undelivered_order():
    """In-transit order that has not been delivered cannot be returned."""
    res = client.post(
        "/api/v1/orders/ord-demo-003/returns",
        json={
            "order_item_id": "item-ord-003",
            "quantity": 1,
            "reason": "wrong_item",
            "description": "Accidentally ordered wrong color.",
        },
        headers=AUTH_BUYER,
    )
    assert res.status_code == 400
    assert "Return can only be initiated on delivered orders" in res.json()["detail"]


def test_vendor_approves_return_and_dispatches_gateway_refund():
    """
    Vendor approves return request:
    Status transitions to 'refunded' and automated refund ledger entry is created.
    """
    # 1. Customer initiates return
    init_res = client.post(
        "/api/v1/orders/ord-demo-001/returns",
        json={
            "order_item_id": "item-ord-001",
            "quantity": 1,
            "reason": "defective",
            "description": "ANC buzzing defect.",
        },
        headers=AUTH_BUYER,
    )
    return_id = init_res.json()["return_id"]

    # 2. Vendor approves return
    appr_res = client.post(
        f"/api/v1/returns/{return_id}/moderate",
        json={"action": "approve"},
        headers=AUTH_VENDOR,
    )
    assert appr_res.status_code == 200
    appr_data = appr_res.json()
    assert appr_data["status"] == "success"
    assert appr_data["new_status"] == "refunded"
    assert appr_data["refund_id"].startswith("rfnd_")
    assert appr_data["refund_amount"] == 1999.00

    # 3. Check return record
    ret_res = client.get(f"/api/v1/returns/{return_id}", headers=AUTH_BUYER)
    assert ret_res.json()["return_status"] == "refunded"
    assert ret_res.json()["refund_id"] == appr_data["refund_id"]
