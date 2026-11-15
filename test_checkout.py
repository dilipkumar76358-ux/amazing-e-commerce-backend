import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.security import create_access_token
from app.services.payment import generate_gateway_signature

client = TestClient(app)

CUSTOMER_USER_ID = "11111111-2222-3333-4444-555555555555"
CUSTOMER_TOKEN = create_access_token({
    "sub": CUSTOMER_USER_ID,
    "email": "customer@amazing.in",
    "roles": ["customer"],
    "name": "Dilip Kumar",
    "phone": "+919876543210",
})
AUTH_HEADERS = {"Authorization": f"Bearer {CUSTOMER_TOKEN}"}


def test_unauthenticated_checkout_rejected():
    """Checkout cannot be initiated without authentication credentials (401)."""
    res = client.post(
        "/api/v1/checkout/initiate",
        json={"address_id": "addr-demo-01"}
    )
    assert res.status_code == 401


def test_empty_cart_checkout_rejected():
    """Initiating checkout with an empty cart returns 400 Cart is empty."""
    client.delete("/api/v1/cart/clear", headers=AUTH_HEADERS)
    res = client.post(
        "/api/v1/checkout/initiate",
        json={"address_id": "addr-demo-01"},
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 400
    assert "Cart is empty" in res.json()["detail"]


def test_address_management_and_indian_pincode_validation():
    """
    Standard Indian address management:
    - 6-digit PIN code format enforced.
    - Default address toggle works.
    """
    # 1. Invalid PIN code rejected (e.g. 5 digits or letters)
    inv_res = client.post(
        "/api/v1/addresses",
        json={
            "recipient_name": "Rohan Sharma",
            "phone": "+919876543210",
            "address_line_1": "Flat 101, Palm Heights",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postal_code": "5600",  # Invalid
        },
        headers=AUTH_HEADERS,
    )
    assert inv_res.status_code == 422

    # 2. Valid Indian address created
    create_res = client.post(
        "/api/v1/addresses",
        json={
            "recipient_name": "Rohan Sharma",
            "phone": "+919876543210",
            "address_line_1": "Flat 101, Palm Heights, Indiranagar",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postal_code": "560038",
            "is_default": True,
        },
        headers=AUTH_HEADERS,
    )
    assert create_res.status_code == 201
    addr_data = create_res.json()
    assert addr_data["postal_code"] == "560038"
    assert addr_data["is_default"] is True

    # 3. List addresses
    list_res = client.get("/api/v1/addresses", headers=AUTH_HEADERS)
    assert list_res.status_code == 200
    assert any(a["id"] == addr_data["id"] for a in list_res.json())


def test_coupon_engine_minimum_spend_and_discount():
    """
    Server-side promo code validation:
    - Below minimum spend returns 400.
    - Meets spend returns verified discount.
    """
    # 1. Below threshold (WELCOME100 requires min 499)
    fail_res = client.post(
        "/api/v1/coupons/validate",
        json={"code": "WELCOME100", "cart_subtotal": 350.0},
        headers=AUTH_HEADERS,
    )
    assert fail_res.status_code == 400
    assert "requires a minimum order subtotal" in fail_res.json()["detail"]

    # 2. Meets threshold (subtotal 1999 gives 100 off)
    pass_res = client.post(
        "/api/v1/coupons/validate",
        json={"code": "WELCOME100", "cart_subtotal": 1999.0},
        headers=AUTH_HEADERS,
    )
    assert pass_res.status_code == 200
    c_data = pass_res.json()
    assert c_data["is_valid"] is True
    assert c_data["discount_amount"] == 100.0
    assert c_data["new_subtotal"] == 1899.0


def test_checkout_initiation_and_gateway_order_creation():
    """
    Initiating checkout calculates order amounts, creates Gateway Order,
    and returns razorpay details.
    """
    client.delete("/api/v1/cart/clear", headers=AUTH_HEADERS)

    # Add 1 headphone (₹1999)
    client.post(
        "/api/v1/cart/items",
        json={"variant_id": "var-hp-black", "quantity": 1},
        headers=AUTH_HEADERS,
    )

    init_res = client.post(
        "/api/v1/checkout/initiate",
        json={"address_id": "addr-demo-01", "coupon_code": "WELCOME100"},
        headers=AUTH_HEADERS,
    )
    assert init_res.status_code == 200
    data = init_res.json()

    assert data["order_number"].startswith("ORD-")
    assert data["item_subtotal"] == 1999.0
    assert data["discount_total"] == 100.0
    assert data["shipping_total"] == 0.0  # >= 499 free
    assert data["grand_total"] == 1899.0
    assert data["amount_paise"] == 189900
    assert data["currency"] == "INR"
    assert data["gateway_order_id"].startswith("order_")


def test_payment_tampered_signature_rejected():
    """
    Replay / tampering attack: passing spoofed or invalid signature fails with 400.
    """
    client.delete("/api/v1/cart/clear", headers=AUTH_HEADERS)
    client.post(
        "/api/v1/cart/items",
        json={"variant_id": "var-hp-black", "quantity": 1},
        headers=AUTH_HEADERS,
    )

    init_data = client.post(
        "/api/v1/checkout/initiate",
        json={"address_id": "addr-demo-01"},
        headers=AUTH_HEADERS,
    ).json()

    fraud_res = client.post(
        "/api/v1/payments/verify",
        json={
            "order_id": init_data["order_id"],
            "razorpay_order_id": init_data["gateway_order_id"],
            "razorpay_payment_id": "pay_test_9999",
            "razorpay_signature": "tampered_fake_signature_hash_0000",
        },
        headers=AUTH_HEADERS,
    )
    assert fraud_res.status_code == 400
    assert "Invalid payment signature" in fraud_res.json()["detail"]


def test_payment_verification_and_multi_vendor_suborder_splitting():
    """
    Valid payment signature verification:
    - Confirms master order.
    - Captures payment.
    - Generates separate vendor suborders for each merchant.
    - Atomically clears user's active cart.
    """
    client.delete("/api/v1/cart/clear", headers=AUTH_HEADERS)

    # 1. Add Headphone (Apex Electronics Store)
    client.post(
        "/api/v1/cart/items",
        json={"variant_id": "var-hp-black", "quantity": 1},
        headers=AUTH_HEADERS,
    )

    # 2. Add Running Shoes (StrideStyle Apparel)
    client.post(
        "/api/v1/cart/items",
        json={"variant_id": "var-shoe-red-9", "quantity": 1},
        headers=AUTH_HEADERS,
    )

    init_data = client.post(
        "/api/v1/checkout/initiate",
        json={"address_id": "addr-demo-01"},
        headers=AUTH_HEADERS,
    ).json()

    order_id = init_data["order_id"]
    gateway_order_id = init_data["gateway_order_id"]
    payment_id = "pay_live_test_777777"

    # Compute genuine cryptographic HMAC SHA-256 signature
    valid_sig = generate_gateway_signature(order_id=gateway_order_id, payment_id=payment_id)

    verify_res = client.post(
        "/api/v1/payments/verify",
        json={
            "order_id": order_id,
            "razorpay_order_id": gateway_order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": valid_sig,
        },
        headers=AUTH_HEADERS,
    )
    assert verify_res.status_code == 200
    v_data = verify_res.json()
    assert v_data["status"] == "success"

    # 3. Verify user's cart is now cleared
    cart_res = client.get("/api/v1/cart", headers=AUTH_HEADERS)
    assert cart_res.json()["total_items"] == 0

    # 4. Fetch confirmed master order and verify suborders
    detail_res = client.get(f"/api/v1/orders/{order_id}", headers=AUTH_HEADERS)
    assert detail_res.status_code == 200
    order_detail = detail_res.json()
    assert order_detail["order_status"] == "confirmed"
    assert order_detail["payment_status"] == "captured"

    # Verify Multi-Vendor Suborder Splitting: 2 separate suborders
    suborders = order_detail["vendor_suborders"]
    assert len(suborders) == 2
    store_names = [s["store_name"] for s in suborders]
    assert "Apex Electronics Store" in store_names
    assert "StrideStyle Apparel" in store_names


def test_concurrency_stock_protection():
    """
    Attempting to checkout when items in cart exceed available inventory
    fails with 400 Stock changed.
    """
    client.delete("/api/v1/cart/clear", headers=AUTH_HEADERS)

    # var-hp-silver has available_stock = 65
    # Force an impossible quantity directly into memory
    from app.api.v1.endpoints.cart import _MEMORY_CARTS
    _MEMORY_CARTS[CUSTOMER_USER_ID] = [
        {"item_id": "ci-overstock", "variant_id": "var-hp-silver", "quantity": 9999}
    ]

    res = client.post(
        "/api/v1/checkout/initiate",
        json={"address_id": "addr-demo-01"},
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 400
    assert "Stock changed" in res.json()["detail"]
