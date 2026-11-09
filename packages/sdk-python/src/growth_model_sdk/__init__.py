"""Minimal growth-model SDK.

import growth_model_sdk as gm

gm.init(api_key="gm_pub_...", base_url="https://growth.example.com")
gm.active("user-123", metadata={"platform": "ios", "app_version": "2.4.1"})
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from .client import DEFAULT_BASE_URL, GrowthModelClient

__all__ = ["DEFAULT_BASE_URL", "GrowthModelClient", "active", "flush", "init"]

_default: GrowthModelClient | None = None


def init(api_key: str | None = None, **kwargs: Any) -> GrowthModelClient:
    """Configure the process-wide default client."""
    global _default
    if _default is not None:
        _default.close()
    _default = GrowthModelClient(api_key, **kwargs)
    return _default


def active(user_id: str, *, metadata: Mapping[str, Any] | None = None, timestamp: datetime | None = None) -> None:
    """Record activity on the default client (no-op until :func:`init` is called)."""
    if _default is not None:
        _default.active(user_id, metadata=metadata, timestamp=timestamp)


def flush(timeout: float = 10.0) -> bool:
    return _default.flush(timeout) if _default is not None else True
