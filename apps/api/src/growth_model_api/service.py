"""Jobs and queries. Pure functions over a Session so they can run from the API, cron or tests."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import case, delete, func, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from growth_model_core import (
    ALLOWED_TRANSITIONS,
    RateFit,
    Rates,
    Segment,
    UserActivity,
    Windows,
    aggregates,
    estimate_rates,
    segment_users,
)

from .auth import Principal
from .db import ActivityDay, RateFitRow, SegmentCount, TrackedUser, TransitionCount


def _insert(db: Session, table):
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        return postgresql.insert(table)
    if dialect == "sqlite":
        return sqlite.insert(table)
    raise RuntimeError(f"unsupported database dialect: {dialect}")


def _tenant(model, p: Principal):
    return (model.company_id == p.company_id, model.product_id == p.product_id)


# --------------------------------------------------------------------- ingest
def ingest(db: Session, p: Principal, events: Iterable[dict[str, Any]]) -> int:
    """Idempotently record (user, UTC day) activity. Returns distinct user-days in the batch."""
    days: dict[tuple[str, date], dict[str, Any]] = {}
    for e in events:
        ts: datetime = e["timestamp"] or datetime.now(UTC)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        days.setdefault((e["user_id"], ts.astimezone(UTC).date()), e.get("metadata") or {})
    if not days:
        return 0
    first: dict[str, date] = {}
    for uid, d in days:
        first[uid] = min(d, first.get(uid, d))

    ins = _insert(db, TrackedUser)
    db.execute(
        ins.values(
            [
                {"company_id": p.company_id, "product_id": p.product_id, "user_id": u, "first_seen": d}
                for u, d in first.items()
            ]
        ).on_conflict_do_update(
            index_elements=["company_id", "product_id", "user_id"],
            set_={
                "first_seen": case(
                    (ins.excluded.first_seen < TrackedUser.first_seen, ins.excluded.first_seen),
                    else_=TrackedUser.first_seen,
                )
            },
        )
    )
    db.execute(
        _insert(db, ActivityDay)
        .values(
            [
                {"company_id": p.company_id, "product_id": p.product_id, "user_id": u, "day": d, "event_metadata": m}
                for (u, d), m in days.items()
            ]
        )
        .on_conflict_do_nothing()
    )
    db.commit()
    return len(days)


# ----------------------------------------------------------------------- jobs
def last_segmented_day(db: Session, p: Principal) -> date | None:
    return db.scalar(select(func.max(SegmentCount.day)).where(*_tenant(SegmentCount, p)))


def first_activity_day(db: Session, p: Principal) -> date | None:
    return db.scalar(select(func.min(TrackedUser.first_seen)).where(*_tenant(TrackedUser, p)))


def run_segments(db: Session, p: Principal, start: date | None, end: date | None, windows: Windows) -> dict[str, Any]:
    """(Re)materialise segment and transition counts for ``start..end`` (inclusive).

    Defaults: from the day after the last materialised day (or the first
    activity day) through yesterday UTC — i.e. the daily incremental job.
    """
    end = end or (datetime.now(UTC).date() - timedelta(days=1))
    if start is None:
        last = last_segmented_day(db, p)
        start = (last + timedelta(days=1)) if last else first_activity_day(db, p)
    if start is None or start > end:
        return {"start": None, "end": end.isoformat(), "days": 0}

    lookback = start - timedelta(days=windows.month + 1)
    first_seen = dict(
        db.execute(
            select(TrackedUser.user_id, TrackedUser.first_seen).where(
                *_tenant(TrackedUser, p), TrackedUser.first_seen <= end
            )
        ).all()
    )
    active: dict[str, list[date]] = defaultdict(list)
    for uid, d in db.execute(
        select(ActivityDay.user_id, ActivityDay.day).where(
            *_tenant(ActivityDay, p), ActivityDay.day >= lookback, ActivityDay.day <= end
        )
    ):
        active[uid].append(d)
    users = {
        uid: UserActivity(first_seen=fs, days=tuple(sorted(active.get(uid, ())))) for uid, fs in first_seen.items()
    }
    panel = segment_users(users, start, end, windows)

    for model in (SegmentCount, TransitionCount):
        db.execute(delete(model).where(*_tenant(model, p), model.day >= start, model.day <= end))
    db.add_all(
        SegmentCount(company_id=p.company_id, product_id=p.product_id, day=d, segment=s.value, users=n)
        for d, c in panel.counts.items()
        for s, n in c.items()
    )
    db.add_all(
        TransitionCount(
            company_id=p.company_id, product_id=p.product_id, day=d, from_segment=a.value, to_segment=b.value, users=n
        )
        for d, t in panel.transitions.items()
        for (a, b), n in t.items()
    )
    db.commit()
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "days": len(panel.counts),
        "users": len(users),
        "unexpected_transitions": panel.unexpected_transitions,
    }


def run_fit(db: Session, p: Principal, as_of: date | None, window_days: int) -> RateFit:
    """Fit rates over the trailing window ending at ``as_of`` (the weekly job)."""
    as_of = as_of or last_segmented_day(db, p)
    if as_of is None:
        raise LookupError("no segmented days yet; run the segments job first")
    lo = as_of - timedelta(days=window_days - 1)
    by_day: dict[date, Counter] = defaultdict(Counter)
    unexpected = 0
    for row in db.scalars(
        select(TransitionCount).where(
            *_tenant(TransitionCount, p), TransitionCount.day >= lo, TransitionCount.day <= as_of
        )
    ):
        edge = (Segment(row.from_segment), Segment(row.to_segment))
        by_day[row.day][edge] += row.users
        unexpected += 0 if edge in ALLOWED_TRANSITIONS else row.users
    new_users = db.scalars(
        select(SegmentCount.users).where(
            *_tenant(SegmentCount, p),
            SegmentCount.segment == Segment.NEW.value,
            SegmentCount.day >= lo,
            SegmentCount.day <= as_of,
        )
    ).all()
    prior = latest_fit(db, p)
    fit = estimate_rates(
        by_day.values(), new_users, as_of=as_of, window_days=window_days, prior=prior.rates if prior else None
    )
    db.add(
        RateFitRow(
            company_id=p.company_id,
            product_id=p.product_id,
            as_of=as_of,
            window_days=window_days,
            rates=fit.rates.to_dict(),
            exposure=fit.exposure,
            unexpected_transitions=unexpected,
        )
    )
    db.commit()
    return fit


# -------------------------------------------------------------------- queries
def latest_fit(db: Session, p: Principal) -> RateFit | None:
    row = db.scalars(
        select(RateFitRow).where(*_tenant(RateFitRow, p)).order_by(RateFitRow.as_of.desc(), RateFitRow.id.desc())
    ).first()
    if row is None:
        return None
    return RateFit(
        as_of=row.as_of, window_days=row.window_days, rates=Rates.from_dict(row.rates), exposure=row.exposure
    )


def fit_history(db: Session, p: Principal) -> list[dict[str, Any]]:
    rows = db.scalars(select(RateFitRow).where(*_tenant(RateFitRow, p)).order_by(RateFitRow.as_of, RateFitRow.id))
    return [{"as_of": r.as_of.isoformat(), "window_days": r.window_days, "rates": r.rates} for r in rows]


def segment_series(db: Session, p: Principal, start: date | None, end: date | None) -> dict[date, dict[Segment, int]]:
    q = select(SegmentCount).where(*_tenant(SegmentCount, p))
    if start:
        q = q.where(SegmentCount.day >= start)
    if end:
        q = q.where(SegmentCount.day <= end)
    out: dict[date, dict[Segment, int]] = defaultdict(lambda: {s: 0 for s in Segment})
    for row in db.scalars(q.order_by(SegmentCount.day)):
        out[row.day][Segment(row.segment)] = row.users
    return dict(out)


def metric_series(db: Session, p: Principal, start: date | None, end: date | None) -> list[dict[str, Any]]:
    return [{"day": d.isoformat(), **aggregates(c)} for d, c in segment_series(db, p, start, end).items()]


def latest_state(db: Session, p: Principal) -> tuple[date, dict[Segment, int]]:
    last = last_segmented_day(db, p)
    if last is None:
        raise LookupError("no segmented days yet; run the segments job first")
    return last, segment_series(db, p, last, last)[last]
