from datetime import datetime, timezone
import os

from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///./test_growth_model.db"
os.environ["GROWTH_MODEL_API_KEY"] = "test-key"

from growth_model_api.main import app  # noqa: E402


def test_ingest_endpoint_accepts_valid_payload():
    client = TestClient(app)
    payload = {
        "company_id": "acme",
        "product_id": "mobile",
        "user_id": "u1",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "metadata": {"platform": "ios", "app_version": "1.0.0", "locale": "en"},
    }
    res = client.post("/v1/ingest/activity", json=payload, headers={"x-api-key": "test-key"})
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_scoped_api_key_enforces_company_and_product():
    client = TestClient(app)
    key_create = {
        "api_key": "scoped-key-123",
        "company_id": "acme",
        "product_id": "mobile",
        "product_version": "v2",
    }
    admin_res = client.post("/v1/admin/api-keys", json=key_create, headers={"x-admin-key": "dev-admin-key"})
    assert admin_res.status_code in (200, 409)

    bad_payload = {
        "company_id": "other",
        "product_id": "mobile",
        "user_id": "u2",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "metadata": {"platform": "ios", "app_version": "1.0.0"},
    }
    bad_res = client.post("/v1/ingest/activity", json=bad_payload, headers={"x-api-key": "scoped-key-123"})
    assert bad_res.status_code == 403
