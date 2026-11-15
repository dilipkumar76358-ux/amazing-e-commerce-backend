import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.security import create_access_token

client = TestClient(app)

CUSTOMER_USER_ID = "11111111-2222-3333-4444-555555555555"
CUSTOMER_TOKEN = create_access_token({
    "sub": CUSTOMER_USER_ID,
    "email": "customer@amazing.in",
    "roles": ["customer"],
})
AUTH_HEADERS = {"Authorization": f"Bearer {CUSTOMER_TOKEN}"}


def test_unauthenticated_cart_access_rejected():
    """Accessing cart without authentication credentials should return 401."""
    res = client.get("/api/v1/cart")
    assert res.status_code == 401


def test_empty_cart_returns_zero_totals():
    """New user starts with an empty cart and zero grand total."""
    client.delete("/api/v1/cart/clear", headers=AUTH_HEADERS)
    res = client.get("/api/v1/cart", headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["item_subtotal"] == 0.0
    assert data["grand_total"] == 0.0
    assert data["total_items"] == 0
    assert len(data["vendor_groups"]) == 0


def test_add_item_insufficient_stock_rejected():
    """Adding items exceeding available stock returns 400 Insufficient Stock."""
    res = client.post(
        "/api/v1/cart/items",
        json={"variant_id": "var-hp-silver", "quantity": 999999},
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 400
    assert "Insufficient stock" in res.json()["detail"]


def test_server_enforced_prices_client_price_ignored():
    """
    The server must strictly pull prices from the database/catalog.
    Even if client attempts to pass a custom price, server calculates authentic price (1999.00).
    """
    client.delete("/api/v1/cart/clear", headers=AUTH_HEADERS)
    res = client.post(
        "/api/v1/cart/items",
        json={
            "variant_id": "var-hp-black",
            "quantity": 1,
            "malicious_price": 1.00,  # Attacker attempt
        },
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 201

    cart_res = client.get("/api/v1/cart", headers=AUTH_HEADERS)
    assert cart_res.status_code == 200
    cart_data = cart_res.json()
    assert cart_data["item_subtotal"] == 1999.00
    assert cart_data["vendor_groups"][0]["items"][0]["selling_price"] == 1999.00


def test_multi_vendor_cart_grouping():
    """
    Adding items from two distinct vendors properly separates items into two vendor groups.
    var-hp-black: Apex Electronics Store (vend-5555-6666-7777-8888)
    var-shoe-red-9: StrideStyle Apparel (vend-9999-8888-7777-6666)
    """
    client.delete("/api/v1/cart/clear", headers=AUTH_HEADERS)

    # 1. Add Headphones (Apex Electronics Store)
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

    cart_res = client.get("/api/v1/cart", headers=AUTH_HEADERS)
    assert cart_res.status_code == 200
    cart = cart_res.json()

    assert cart["total_items"] == 2
    assert len(cart["vendor_groups"]) == 2

    stores = [vg["store_name"] for vg in cart["vendor_groups"]]
    assert "Apex Electronics Store" in stores
    assert "StrideStyle Apparel" in stores


def test_update_cart_quantity_and_delete_item():
    """Updating cart item quantity recalculates line total and grand total."""
    client.delete("/api/v1/cart/clear", headers=AUTH_HEADERS)

    # Add 1 headphone (₹1999)
    client.post(
        "/api/v1/cart/items",
        json={"variant_id": "var-hp-black", "quantity": 1},
        headers=AUTH_HEADERS,
    )

    cart = client.get("/api/v1/cart", headers=AUTH_HEADERS).json()
    item_id = cart["vendor_groups"][0]["items"][0]["item_id"]

    # Update to 2 headphones (₹3998)
    update_res = client.patch(
        f"/api/v1/cart/items/{item_id}",
        json={"quantity": 2},
        headers=AUTH_HEADERS,
    )
    assert update_res.status_code == 200

    updated_cart = client.get("/api/v1/cart", headers=AUTH_HEADERS).json()
    assert updated_cart["item_subtotal"] == 3998.00
    assert updated_cart["total_items"] == 2

    # Remove item
    del_res = client.delete(f"/api/v1/cart/items/{item_id}", headers=AUTH_HEADERS)
    assert del_res.status_code == 200

    empty_cart = client.get("/api/v1/cart", headers=AUTH_HEADERS).json()
    assert empty_cart["total_items"] == 0
    assert empty_cart["item_subtotal"] == 0.0


def test_wishlist_lifecycle_and_move_to_cart():
    """Test saving a product to wishlist and moving it into active cart."""
    # 1. Add laptop to wishlist
    add_wl = client.post(
        "/api/v1/wishlist/items",
        json={"product_id": "prod-laptop-02"},
        headers=AUTH_HEADERS,
    )
    assert add_wl.status_code == 201

    wl_res = client.get("/api/v1/wishlist", headers=AUTH_HEADERS)
    assert wl_res.status_code == 200
    wl_data = wl_res.json()
    assert any(i["product_id"] == "prod-laptop-02" for i in wl_data["items"])

    # 2. Clear cart and move from wishlist to cart
    client.delete("/api/v1/cart/clear", headers=AUTH_HEADERS)
    move_res = client.post(
        "/api/v1/wishlist/items/prod-laptop-02/move-to-cart",
        headers=AUTH_HEADERS,
    )
    assert move_res.status_code == 200

    # 3. Verify in cart
    cart_res = client.get("/api/v1/cart", headers=AUTH_HEADERS)
    assert cart_res.status_code == 200
    assert cart_res.json()["total_items"] == 1

    # 4. Verify removed from wishlist
    wl_after = client.get("/api/v1/wishlist", headers=AUTH_HEADERS).json()
    assert not any(i["product_id"] == "prod-laptop-02" for i in wl_after["items"])


def test_update_cart_quantity_exceeding_stock_rejected():
    """Updating cart item to a quantity exceeding available stock returns 400."""
    client.delete("/api/v1/cart/clear", headers=AUTH_HEADERS)

    # Add 1 headphone
    client.post(
        "/api/v1/cart/items",
        json={"variant_id": "var-hp-black", "quantity": 1},
        headers=AUTH_HEADERS,
    )

    cart = client.get("/api/v1/cart", headers=AUTH_HEADERS).json()
    item_id = cart["vendor_groups"][0]["items"][0]["item_id"]

    # Attempt to update to 999999
    update_res = client.patch(
        f"/api/v1/cart/items/{item_id}",
        json={"quantity": 999999},
        headers=AUTH_HEADERS,
    )
    assert update_res.status_code == 400
    assert "Insufficient stock" in update_res.json()["detail"]


def test_free_shipping_threshold_calculation():
    """Items above 499 qualify for free shipping (shipping_total = 0.0)."""
    client.delete("/api/v1/cart/clear", headers=AUTH_HEADERS)

    # var-hp-black is ₹1999 (above 499)
    client.post(
        "/api/v1/cart/items",
        json={"variant_id": "var-hp-black", "quantity": 1},
        headers=AUTH_HEADERS,
    )

    cart = client.get("/api/v1/cart", headers=AUTH_HEADERS).json()
    assert cart["item_subtotal"] == 1999.0
    assert cart["shipping_total"] == 0.0
    assert cart["amount_needed_for_free_shipping"] == 0.0
    assert cart["grand_total"] == 1999.0


def test_guest_session_token_shopping_flow():
    """Supports temporary anonymous/guest sessions with signed tokens."""
    guest_user_id = "guest-9999-aaaa-bbbb-cccc"
    guest_token = create_access_token({
        "sub": guest_user_id,
        "roles": ["customer"],
    })
    guest_headers = {"Authorization": f"Bearer {guest_token}"}

    client.delete("/api/v1/cart/clear", headers=guest_headers)

    add_res = client.post(
        "/api/v1/cart/items",
        json={"variant_id": "var-hp-black", "quantity": 1},
        headers=guest_headers,
    )
    assert add_res.status_code == 201

    cart_res = client.get("/api/v1/cart", headers=guest_headers)
    assert cart_res.status_code == 200
    assert cart_res.json()["total_items"] == 1
    assert cart_res.json()["item_subtotal"] == 1999.0

