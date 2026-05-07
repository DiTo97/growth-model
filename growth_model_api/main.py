from __future__ import annotations

import os
from collections import defaultdict
from datetime import date
from datetime import timedelta

from fastapi import Depends, FastAPI, Header, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from growth_model_api.db import (
    ActivityEventRow,
    ApiKeyRow,
    DailySnapshotRow,
    TransitionRateRow,
    create_session_factory,
)
from growth_model_api.schemas import ActivityIn, ApiKeyCreate, ComputationRequest, SimulationRequest
from growth_model_core.engine import (
    ALL_SEGMENTS,
    aggregate_daily_states,
    compute_aggregates,
    compute_daily_states,
    compute_transition_rates,
    simulate,
)
from growth_model_core.models import ActivityEvent, Segment

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///growth_model.db")
API_KEY = os.getenv("GROWTH_MODEL_API_KEY", "dev-api-key")
ADMIN_KEY = os.getenv("GROWTH_MODEL_ADMIN_KEY", "dev-admin-key")
SessionFactory = create_session_factory(DATABASE_URL)

def get_db():
    db = SessionFactory()
    try:
        yield db
    finally:
        db.close()


app = FastAPI(title="Growth Model Service", version="0.1.0")


def require_api_key(
    db: Session = Depends(get_db),
    x_api_key: str = Header(default=""),
) -> ApiKeyRow:
    if x_api_key == API_KEY:
        return ApiKeyRow(api_key=x_api_key, company_id="*", product_id="*", product_version="v1", is_active=1)
    key = db.scalars(select(ApiKeyRow).where(ApiKeyRow.api_key == x_api_key, ApiKeyRow.is_active == 1)).first()
    if not key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return key


def require_admin_key(x_admin_key: str = Header(default="")) -> None:
    if x_admin_key != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Invalid admin key")


@app.post("/v1/admin/api-keys", dependencies=[Depends(require_admin_key)])
def create_api_key(payload: ApiKeyCreate, db: Session = Depends(get_db)):
    existing = db.scalars(select(ApiKeyRow).where(ApiKeyRow.api_key == payload.api_key)).first()
    if existing:
        raise HTTPException(status_code=409, detail="API key already exists")
    db.add(
        ApiKeyRow(
            api_key=payload.api_key,
            company_id=payload.company_id,
            product_id=payload.product_id,
            product_version=payload.product_version,
            is_active=1,
        )
    )
    db.commit()
    return {"status": "ok"}


@app.get("/v1/admin/api-keys", dependencies=[Depends(require_admin_key)])
def list_api_keys(db: Session = Depends(get_db)):
    rows = db.scalars(select(ApiKeyRow).order_by(ApiKeyRow.id.asc())).all()
    return [
        {
            "company_id": row.company_id,
            "product_id": row.product_id,
            "product_version": row.product_version,
            "is_active": bool(row.is_active),
        }
        for row in rows
    ]


@app.post("/v1/ingest/activity")
def ingest_activity(payload: ActivityIn, key: ApiKeyRow = Depends(require_api_key), db: Session = Depends(get_db)):
    if key.company_id != "*" and (payload.company_id != key.company_id or payload.product_id != key.product_id):
        raise HTTPException(status_code=403, detail="API key scope mismatch")
    row = ActivityEventRow(
        company_id=payload.company_id,
        product_id=payload.product_id,
        user_id=payload.user_id,
        occurred_at=payload.occurred_at,
        event_metadata=payload.metadata.model_dump(),
    )
    db.add(row)
    db.commit()
    return {"status": "ok"}


@app.post("/v1/jobs/compute")
def compute_job(payload: ComputationRequest, _key: ApiKeyRow = Depends(require_api_key), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(ActivityEventRow).where(
            ActivityEventRow.company_id == payload.company_id,
            ActivityEventRow.occurred_at >= payload.start_date,
            ActivityEventRow.occurred_at < payload.end_date + timedelta(days=1),
        )
    ).all()
    events = [
        ActivityEvent(company_id=r.company_id, user_id=r.user_id, occurred_at=r.occurred_at)
        for r in rows
    ]
    states = compute_daily_states(events, payload.start_date, payload.end_date)
    aggregates = aggregate_daily_states(states)
    rates = compute_transition_rates(states)

    db.execute(delete(DailySnapshotRow).where(DailySnapshotRow.company_id == payload.company_id))
    db.execute(delete(TransitionRateRow).where(TransitionRateRow.company_id == payload.company_id))

    for (company_id, day), segment_map in aggregates.items():
        for segment, count in segment_map.items():
            db.add(
                DailySnapshotRow(
                    company_id=company_id,
                    day=day,
                    segment=segment.value,
                    user_count=count,
                )
            )

    for (company_id, day), transition_map in rates.items():
        for (from_s, to_s), rate in transition_map.items():
            db.add(
                TransitionRateRow(
                    company_id=company_id,
                    day=day,
                    from_segment=from_s.value,
                    to_segment=to_s.value,
                    rate=rate,
                )
            )

    db.commit()
    return {"status": "ok", "state_days": len(aggregates), "rate_days": len(rates)}


@app.get("/v1/states/distribution")
def states_distribution(company_id: str, _key: ApiKeyRow = Depends(require_api_key), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(DailySnapshotRow)
        .where(DailySnapshotRow.company_id == company_id)
        .order_by(DailySnapshotRow.day.asc())
    ).all()
    out: dict[str, dict[str, int]] = defaultdict(dict)
    for row in rows:
        out[row.day.isoformat()][row.segment] = row.user_count
    return out


@app.get("/v1/rates/current")
def current_rates(company_id: str, _key: ApiKeyRow = Depends(require_api_key), db: Session = Depends(get_db)):
    last_day = db.scalars(
        select(TransitionRateRow.day)
        .where(TransitionRateRow.company_id == company_id)
        .order_by(TransitionRateRow.day.desc())
    ).first()
    if not last_day:
        return {}
    rows = db.scalars(
        select(TransitionRateRow)
        .where(TransitionRateRow.company_id == company_id, TransitionRateRow.day == last_day)
    ).all()
    return {f"{r.from_segment}->{r.to_segment}": r.rate for r in rows}


@app.get("/v1/rates/history")
def rates_history(company_id: str, _key: ApiKeyRow = Depends(require_api_key), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(TransitionRateRow)
        .where(TransitionRateRow.company_id == company_id)
        .order_by(TransitionRateRow.day.asc())
    ).all()
    out: dict[str, dict[str, float]] = defaultdict(dict)
    for row in rows:
        out[row.day.isoformat()][f"{row.from_segment}->{row.to_segment}"] = row.rate
    return out


@app.get("/v1/metrics/distribution")
def metric_distribution(company_id: str, _key: ApiKeyRow = Depends(require_api_key), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(DailySnapshotRow)
        .where(DailySnapshotRow.company_id == company_id)
        .order_by(DailySnapshotRow.day.asc())
    ).all()
    by_day: dict[str, dict[Segment, int]] = defaultdict(lambda: {s: 0 for s in ALL_SEGMENTS})
    for row in rows:
        by_day[row.day.isoformat()][Segment(row.segment)] = row.user_count
    return {day: compute_aggregates(segment_map) for day, segment_map in by_day.items()}


@app.post("/v1/simulations/run")
def run_simulation(payload: SimulationRequest, _key: ApiKeyRow = Depends(require_api_key), db: Session = Depends(get_db)):
    latest_day = db.scalars(
        select(DailySnapshotRow.day)
        .where(DailySnapshotRow.company_id == payload.company_id)
        .order_by(DailySnapshotRow.day.desc())
    ).first()
    if not latest_day:
        raise HTTPException(status_code=400, detail="No state snapshots found")

    state_rows = db.scalars(
        select(DailySnapshotRow).where(
            DailySnapshotRow.company_id == payload.company_id,
            DailySnapshotRow.day == latest_day,
        )
    ).all()
    rate_rows = db.scalars(
        select(TransitionRateRow).where(
            TransitionRateRow.company_id == payload.company_id,
            TransitionRateRow.day == latest_day,
        )
    ).all()

    initial_state = {Segment(r.segment): float(r.user_count) for r in state_rows}
    for segment in ALL_SEGMENTS:
        initial_state.setdefault(segment, 0.0)

    transition_matrix = {(Segment(r.from_segment), Segment(r.to_segment)): r.rate for r in rate_rows}
    for key, value in payload.overrides.items():
        from_seg, to_seg = key.split("->", maxsplit=1)
        transition_matrix[(Segment(from_seg), Segment(to_seg))] = value

    history = simulate(initial_state, transition_matrix, payload.horizon_days)
    return {"start_day": latest_day.isoformat(), "history": history}
