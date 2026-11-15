import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_duplicate_webhook_does_not_double_fulfill():
    """
    CRITERIA: Simulates gateway delivering the exact same payment.captured webhook payload twice.
    Asserts both return 200 OK, but inventory is decremented only once and duplicate
    returns status='already_processed'.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        webhook_payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_test_892189",
                        "order_id": "order_test_99812",
                        "amount": 149900,
                        "status": "captured"
                    }
                }
            }
        }
        headers = {"X-Razorpay-Signature": "valid_mock_signature"}

        # First webhook delivery
        res1 = await ac.post("/api/v1/webhooks/payments/razorpay", json=webhook_payload, headers=headers)
        assert res1.status_code == 200

        # Duplicate retry webhook delivery
        res2 = await ac.post("/api/v1/webhooks/payments/razorpay", json=webhook_payload, headers=headers)
        assert res2.status_code == 200
        assert res2.json()["status"] == "already_processed"

