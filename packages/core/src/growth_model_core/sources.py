"""Activity sources: turn raw logs into ``(user_id, day)`` rows.

The core library has no runtime dependencies, so sources use the stdlib only.
For SQL warehouses, prefer running ``infra/sql/segments.sql`` in the warehouse
and only pulling aggregates.
"""

from __future__ import annotations

import csv
import json
import random
import urllib.request
from collections.abc import Iterable, Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

POSTHOG_ACTIVE_DAYS_HOGQL = """
SELECT person_id AS user_id, toDate(timestamp) AS day
FROM events
WHERE timestamp >= toDateTime({start}) AND timestamp < toDateTime({end}) EVENT_FILTER
GROUP BY user_id, day
""".strip()


def _to_day(value: str) -> date:
    value = value.strip()
    if len(value) == 10:
        return date.fromisoformat(value)
    ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if ts.tzinfo is not None:
        ts = ts.astimezone(UTC)
    return ts.date()


def read_csv(path: str | Path, user_col: str = "user_id", time_col: str | None = None) -> Iterator[tuple[str, date]]:
    """Read a CSV with a user column and a ``day`` or ``timestamp`` column (UTC)."""
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames or []
        col = time_col or next((c for c in ("day", "date", "timestamp", "occurred_at") if c in fields), None)
        if user_col not in fields or col is None:
            raise ValueError(f"CSV needs a {user_col!r} column and a day/timestamp column; got {fields}")
        for row in reader:
            yield row[user_col], _to_day(row[col])


def write_csv(rows: Iterable[tuple[str, date]], path: str | Path) -> int:
    n = 0
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["user_id", "day"])
        for uid, d in rows:
            w.writerow([uid, d.isoformat()])
            n += 1
    return n


def read_posthog(
    host: str,
    project_id: str,
    personal_api_key: str,
    start: date,
    end: date,
    event: str | None = None,
) -> list[tuple[str, date]]:
    """Pull distinct active (user, day) pairs via PostHog's HogQL query API.

    Note: the query API caps result rows; for large projects export to a
    warehouse and use ``infra/sql/segments.sql`` instead.
    """
    # Values are bound server-side via HogQL placeholders, never interpolated.
    query = POSTHOG_ACTIVE_DAYS_HOGQL.replace("EVENT_FILTER", "AND event = {event}" if event else "")
    values = {"start": start.isoformat(), "end": (end + timedelta(days=1)).isoformat()} | (
        {"event": event} if event else {}
    )
    if not host.startswith(("https://", "http://")):
        raise ValueError("PostHog host must be an http(s) URL")
    req = urllib.request.Request(  # noqa: S310 - scheme checked above
        f"{host.rstrip('/')}/api/projects/{project_id}/query/",
        data=json.dumps({"query": {"kind": "HogQLQuery", "query": query, "values": values}}).encode(),
        headers={"Authorization": f"Bearer {personal_api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as res:  # noqa: S310 - user-supplied PostHog host
        payload = json.load(res)
    return [(str(uid), _to_day(str(d))) for uid, d in payload.get("results", [])]


def synthetic_activity(
    days: int = 120,
    new_users_per_day: int = 40,
    end: date = date(2026, 1, 31),
    seed: int = 7,
) -> list[tuple[str, date]]:
    """Generate plausible activity for demos and tests.

    Each user has a latent engagement level; daily activity probability decays
    with time since last activity, with occasional comebacks.
    """
    rng = random.Random(seed)  # noqa: S311 - demo data, not crypto
    start = end - timedelta(days=days - 1)
    rows: list[tuple[str, date]] = []
    users: list[tuple[str, float, list[int]]] = []  # id, engagement, [last_active_offset]
    for offset in range(days):
        day = start + timedelta(days=offset)
        for _ in range(new_users_per_day + rng.randint(-5, 5)):
            uid = f"u{len(users):06d}"
            users.append((uid, rng.betavariate(2, 2), [offset]))
            rows.append((uid, day))
        for uid, engagement, last in users:
            if last[0] == offset:
                continue
            gap = offset - last[0]
            p = engagement * 0.9 if gap == 1 else engagement * 0.5 / gap if gap <= 30 else 0.002
            if rng.random() < p:
                last[0] = offset
                rows.append((uid, day))
    return rows
