from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx


class GrowthModelSDK:
    def __init__(self, api_key: str, base_url: str):
        self._client = httpx.Client(base_url=base_url, headers={"x-api-key": api_key}, timeout=10.0)

    def log_active_user(
        self,
        company_id: str,
        product_id: str,
        user_id: str,
        *,
        platform: str,
        app_version: str,
        locale: str | None = None,
        product_version: str | None = None,
        occurred_at: datetime | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "company_id": company_id,
            "product_id": product_id,
            "user_id": user_id,
            "occurred_at": (occurred_at or datetime.now(timezone.utc)).isoformat(),
            "metadata": {
                "platform": platform,
                "app_version": app_version,
                "locale": locale,
                "product_version": product_version,
                **(extra_metadata or {}),
            },
        }
        res = self._client.post("/v1/ingest/activity", json=payload)
        res.raise_for_status()
