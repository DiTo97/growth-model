import json
from datetime import UTC, datetime

import httpx

from growth_model_sdk import GrowthModelClient


def make(handler, **kw):
    return GrowthModelClient(
        "gm_pub_test", base_url="http://x", flush_interval=60, transport=httpx.MockTransport(handler), **kw
    )


def test_batches_and_dedupes_per_user_per_day():
    seen = []

    def handler(req: httpx.Request):
        assert req.headers["authorization"] == "Bearer gm_pub_test"
        seen.extend(json.loads(req.content)["events"])
        return httpx.Response(202, json={"accepted": 1})

    c = make(handler)
    for _ in range(5):
        c.active("u1", metadata={"platform": "ios"})
    c.active("u2")
    c.active("u1", timestamp=datetime(2030, 1, 2, tzinfo=UTC))
    assert c.flush(5)
    c.close()
    assert [e["user_id"] for e in seen] == ["u1", "u2", "u1"]
    assert seen[0]["metadata"] == {"platform": "ios"}


def test_never_raises_on_server_errors():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(500)

    c = make(handler, max_retries=1)
    c.active("u1")
    c.flush(10)
    c.close()
    assert calls["n"] == 2


def test_disabled_without_key(monkeypatch):
    monkeypatch.delenv("GROWTH_MODEL_API_KEY", raising=False)
    c = GrowthModelClient(None)
    assert not c.enabled
    c.active("u1")  # no-op, no error
    assert c.flush()
