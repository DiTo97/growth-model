"""Growth-model ingestion client.

Design goals (this runs inside *other people's* apps):

* one call: ``client.active(user_id)``
* never blocks the caller and never raises into it
* batches, retries transient failures, and drops politely on overload
* deduplicates (user, UTC day) in-process — the model only needs one event per user per day
"""

from __future__ import annotations

import atexit
import logging
import os
import queue
import random
import threading
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import httpx

__all__ = ["DEFAULT_BASE_URL", "GrowthModelClient"]

log = logging.getLogger("growth_model_sdk")
DEFAULT_BASE_URL = "http://localhost:8000"
_STOP = object()


class GrowthModelClient:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        flush_interval: float = 5.0,
        max_batch_size: int = 100,
        max_queue_size: int = 10_000,
        timeout: float = 5.0,
        max_retries: int = 3,
        enabled: bool = True,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("GROWTH_MODEL_API_KEY", "")
        self.base_url = (base_url or os.getenv("GROWTH_MODEL_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.enabled = enabled and bool(self.api_key)
        if enabled and not self.api_key:
            log.warning("growth-model SDK disabled: no api_key and GROWTH_MODEL_API_KEY is unset")
        self.flush_interval = flush_interval
        self.max_batch_size = max_batch_size
        self.max_retries = max_retries
        self._queue: queue.Queue[Any] = queue.Queue(maxsize=max_queue_size)
        self._seen: set[tuple[str, str]] = set()
        self._seen_day = ""
        self._lock = threading.Lock()
        self._http = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}", "User-Agent": "growth-model-sdk-python/0.1"},
            timeout=timeout,
            transport=transport,
        )
        self._idle = threading.Event()
        self._idle.set()
        self._thread: threading.Thread | None = None
        if self.enabled:
            self._thread = threading.Thread(target=self._run, name="growth-model-sdk", daemon=True)
            self._thread.start()
            atexit.register(self.close)

    # ------------------------------------------------------------------ public
    def active(
        self,
        user_id: str,
        *,
        metadata: Mapping[str, Any] | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        """Record that ``user_id`` was active. Safe to call on every request."""
        if not self.enabled or not user_id:
            return
        ts = (timestamp or datetime.now(UTC)).astimezone(UTC)
        day = ts.date().isoformat()
        with self._lock:
            if day != self._seen_day and day > self._seen_day:
                self._seen.clear()
                self._seen_day = day
            key = (str(user_id), day)
            if key in self._seen:
                return
            self._seen.add(key)
        event = {"user_id": str(user_id), "timestamp": ts.isoformat(), "metadata": dict(metadata or {})}
        try:
            self._idle.clear()
            self._queue.put_nowait(event)
        except queue.Full:
            log.warning("growth-model SDK queue full; dropping event")

    def flush(self, timeout: float = 10.0) -> bool:
        """Block until queued events are sent (or ``timeout``). Returns True if drained."""
        if not self.enabled:
            return True
        self._queue.put(None)  # wake the worker
        return self._idle.wait(timeout)

    def close(self, timeout: float = 10.0) -> None:
        if self._thread and self._thread.is_alive():
            self.flush(timeout)
            self._queue.put(_STOP)
            self._thread.join(timeout)
        self._http.close()

    def __enter__(self) -> GrowthModelClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---------------------------------------------------------------- internal
    def _run(self) -> None:
        batch: list[dict[str, Any]] = []
        deadline = time.monotonic() + self.flush_interval
        while True:
            try:
                item = self._queue.get(timeout=max(0.0, deadline - time.monotonic()))
            except queue.Empty:
                item = None
            if item is _STOP:
                self._send(batch)
                return
            if item is not None:
                batch.append(item)
            if item is None or len(batch) >= self.max_batch_size or time.monotonic() >= deadline:
                self._send(batch)
                batch = []
                deadline = time.monotonic() + self.flush_interval
                if self._queue.empty():
                    self._idle.set()

    def _send(self, batch: list[dict[str, Any]]) -> None:
        if not batch:
            return
        for attempt in range(self.max_retries + 1):
            try:
                res = self._http.post("/v1/events", json={"events": batch})
                if res.status_code < 300:
                    return
                if res.status_code < 500 and res.status_code != 429:
                    log.warning("growth-model SDK: events rejected (%s): %s", res.status_code, res.text[:200])
                    return
            except httpx.HTTPError as exc:
                log.debug("growth-model SDK send failed: %s", exc)
            time.sleep(min(30.0, (2**attempt) * 0.5 + random.random() * 0.25))  # noqa: S311
        log.warning("growth-model SDK: dropping %d events after %d retries", len(batch), self.max_retries)
