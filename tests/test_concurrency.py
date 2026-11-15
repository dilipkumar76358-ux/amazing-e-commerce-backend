import pytest
import asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.api.v1.endpoints.cart import _find_variant_in_catalog


@pytest.mark.asyncio
async def test_concurrent_inventory_purchase_no_overselling():
    """
    CRITERIA: Spawns 10 concurrent requests to purchase a variant with only 1 unit in stock.
    Asserts that exactly 1 request succeeds (200 OK) and 9 requests fail with 400 Insufficient Stock.
    """
    # 1. Setup: Variant with stock = 1
    variant_id = "test-variant-exclusive-001"
    catalog_entry = _find_variant_in_catalog(variant_id)
    assert catalog_entry is not None, f"Variant '{variant_id}' should exist in catalog"
    catalog_entry["variant"]["available_stock"] = 1

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        async def attempt_checkout(customer_id: str):
            headers = {"Authorization": f"Bearer mock-token-{customer_id}"}
            response = await ac.post(
                "/api/v1/checkout/initiate",
                json={"address_id": "test-addr-001", "variant_id": variant_id},
                headers=headers
            )
            return response.status_code

        # 2. Fire 10 simultaneous tasks
        tasks = [attempt_checkout(f"customer_{i}") for i in range(10)]
        results = await asyncio.gather(*tasks)

        # 3. Assertions
        success_count = results.count(200)
        failure_count = results.count(400)

        assert success_count == 1, f"Expected exactly 1 successful purchase, got {success_count}"
        assert failure_count == 9, f"Expected 9 failed requests due to out-of-stock, got {failure_count}"

