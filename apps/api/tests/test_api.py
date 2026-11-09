from datetime import UTC, date, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from growth_model_api.main import create_app
from growth_model_api.settings import Settings
from growth_model_core import synthetic_activity

ADMIN = {"Authorization": "Bearer admin-test"}
SECRET = "supabase-test-secret-with-enough-length"


@pytest.fixture
def client():
    app = create_app(Settings(database_url="sqlite://", admin_token="admin-test", supabase_jwt_secret=SECRET))
    return TestClient(app)


def mint(client, company="acme", product="app", kind="secret"):
    res = client.post(
        "/v1/admin/keys", json={"company_id": company, "product_id": product, "kind": kind}, headers=ADMIN
    )
    assert res.status_code == 201
    return {"Authorization": f"Bearer {res.json()['api_key']}"}


def ts(d: date) -> str:
    return datetime(d.year, d.month, d.day, 12, tzinfo=UTC).isoformat()


def load(client, headers, rows):
    for i in range(0, len(rows), 1000):
        chunk = [{"user_id": u, "timestamp": ts(d)} for u, d in rows[i : i + 1000]]
        assert client.post("/v1/events", json={"events": chunk}, headers=headers).status_code == 202


def test_admin_disabled_without_token():
    c = TestClient(create_app(Settings(database_url="sqlite://")))
    assert c.get("/v1/admin/keys", headers=ADMIN).status_code == 404


def test_publishable_key_is_ingest_only_and_tenant_comes_from_key(client):
    pub = mint(client, kind="publishable")
    res = client.post("/v1/events", json={"events": [{"user_id": "u1", "metadata": {"platform": "ios"}}]}, headers=pub)
    assert res.status_code == 202 and res.json() == {"accepted": 1}
    assert client.get("/v1/metrics", headers=pub).status_code == 403
    assert client.get("/v1/metrics").status_code == 401
    assert client.get("/v1/metrics", headers={"Authorization": "Bearer gm_sk_nope"}).status_code == 401


def test_tenants_are_isolated(client):
    a_pub, a_sk = mint(client, "a", kind="publishable"), mint(client, "a")
    b_sk = mint(client, "b")
    yesterday = datetime.now(UTC).date() - timedelta(days=1)
    load(client, a_pub, [("u1", yesterday), ("u2", yesterday)])
    client.post("/v1/jobs/segments", json={}, headers=a_sk)
    client.post("/v1/jobs/segments", json={}, headers=b_sk)
    assert client.get("/v1/metrics", headers=a_sk).json()[-1]["dau"] == 2
    assert client.get("/v1/metrics", headers=b_sk).json() == []


def test_end_to_end_segments_fit_simulate_levers(client):
    sk = mint(client)
    end = datetime.now(UTC).date() - timedelta(days=1)
    rows = synthetic_activity(days=75, new_users_per_day=15, end=end)
    load(client, sk, rows)
    load(client, sk, rows[:500])  # idempotent re-send

    job = client.post("/v1/jobs/segments", json={}, headers=sk).json()
    assert job["days"] == 75 and job["unexpected_transitions"] == 0
    assert client.post("/v1/jobs/segments", json={}, headers=sk).json()["days"] == 0  # incremental: nothing new

    fit = client.post("/v1/jobs/fit", json={"window_days": 28}, headers=sk)
    assert fit.status_code == 200, fit.text
    rates = client.get("/v1/rates", headers=sk).json()["rates"]
    assert 0 < rates["curr"] < 1

    metrics = client.get("/v1/metrics", headers=sk).json()
    by_day = {}
    for u, d in rows:
        by_day.setdefault(d, set()).add(u)
    assert metrics[-1]["dau"] == len(by_day[end])

    sim = client.post("/v1/simulations", json={"horizon_days": 90}, headers=sk).json()
    better = client.post(
        "/v1/simulations", json={"horizon_days": 90, "overrides": {"CURR": min(1, rates["curr"] + 0.05)}}, headers=sk
    ).json()
    assert better["trajectory"][-1]["dau"] > sim["trajectory"][-1]["dau"]
    assert client.post("/v1/simulations", json={"overrides": {"bogus": 1}}, headers=sk).status_code == 422

    levers = client.post("/v1/levers", json={"horizon_days": 365}, headers=sk).json()["results"]
    assert levers[0]["dau_impact"] >= levers[-1]["dau_impact"]


def test_supabase_member_can_read_its_tenant(client):
    sk = mint(client, "acme", "app")
    client.post(
        "/v1/admin/members", json={"subject": "user-1", "company_id": "acme", "product_id": "app"}, headers=ADMIN
    )
    token = jwt.encode({"sub": "user-1", "aud": "authenticated"}, SECRET, algorithm="HS256")
    assert client.get("/v1/metrics", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    stranger = jwt.encode({"sub": "user-2", "aud": "authenticated"}, SECRET, algorithm="HS256")
    assert client.get("/v1/metrics", headers={"Authorization": f"Bearer {stranger}"}).status_code == 403
    assert sk  # silence unused
