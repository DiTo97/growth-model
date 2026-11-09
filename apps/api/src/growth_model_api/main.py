from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from growth_model_core import Windows, lever_analysis, simulate

from . import service
from .auth import (
    Principal,
    generate_key,
    get_db,
    get_settings,
    hash_key,
    ingest_principal,
    read_principal,
    require_admin,
)
from .db import ApiKey, Member, make_engine, make_sessionmaker, utcnow
from .schemas import EventBatch, FitJob, KeyCreate, LeverRequest, MemberCreate, SegmentsJob, SimulationRequest
from .settings import Settings

__version__ = "0.1.0"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(title="Growth Model API", version=__version__)
    app.state.settings = settings
    app.state.sessionmaker = make_sessionmaker(make_engine(settings.database_url))
    windows = Windows(week=settings.week_days, month=settings.month_days)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["authorization", "content-type", "x-tenant"],
        )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    # ------------------------------------------------------------- ingest
    @app.post("/v1/events", status_code=202, tags=["ingest"])
    def ingest_events(batch: EventBatch, p: Principal = Depends(ingest_principal), db: Session = Depends(get_db)):
        return {"accepted": service.ingest(db, p, (e.model_dump() for e in batch.events))}

    # --------------------------------------------------------------- jobs
    @app.post("/v1/jobs/segments", tags=["jobs"])
    def job_segments(body: SegmentsJob, p: Principal = Depends(read_principal), db: Session = Depends(get_db)):
        """Daily job: materialise segment + transition counts (incremental by default)."""
        return service.run_segments(db, p, body.start, body.end, windows)

    @app.post("/v1/jobs/fit", tags=["jobs"])
    def job_fit(body: FitJob, p: Principal = Depends(read_principal), db: Session = Depends(get_db)):
        """Weekly job: refit transition rates over the trailing window."""
        try:
            return service.run_fit(db, p, body.as_of, body.window_days or settings.fit_window_days).to_dict()
        except LookupError as e:
            raise HTTPException(409, str(e)) from e

    # ------------------------------------------------------------ queries
    @app.get("/v1/segments", tags=["analytics"])
    def segments(
        start: date | None = None,
        end: date | None = None,
        p: Principal = Depends(read_principal),
        db: Session = Depends(get_db),
    ):
        return [
            {"day": d.isoformat(), **{s.value: n for s, n in c.items()}}
            for d, c in service.segment_series(db, p, start, end).items()
        ]

    @app.get("/v1/metrics", tags=["analytics"])
    def metrics(
        start: date | None = None,
        end: date | None = None,
        p: Principal = Depends(read_principal),
        db: Session = Depends(get_db),
    ):
        return service.metric_series(db, p, start, end)

    @app.get("/v1/rates", tags=["analytics"])
    def rates(p: Principal = Depends(read_principal), db: Session = Depends(get_db)):
        fit = service.latest_fit(db, p)
        if fit is None:
            raise HTTPException(404, "no fitted rates yet; run POST /v1/jobs/fit")
        return fit.to_dict()

    @app.get("/v1/rates/history", tags=["analytics"])
    def rates_history(p: Principal = Depends(read_principal), db: Session = Depends(get_db)):
        return service.fit_history(db, p)

    def _model(db: Session, p: Principal):
        fit = service.latest_fit(db, p)
        if fit is None:
            raise HTTPException(409, "no fitted rates yet; run POST /v1/jobs/fit")
        day, state = service.latest_state(db, p)
        return fit, day, state

    @app.post("/v1/simulations", tags=["simulation"])
    def simulations(body: SimulationRequest, p: Principal = Depends(read_principal), db: Session = Depends(get_db)):
        fit, day, state = _model(db, p)
        rates = fit.rates.with_overrides(body.overrides, body.new_users_per_day)
        traj = simulate(state, rates, body.horizon_days)
        out: list[dict[str, Any]] = [
            s.to_dict() if body.include_segments else {"day": s.day, **s.metrics} for s in traj
        ]
        return {"start_day": day.isoformat(), "rates": rates.to_dict(), "trajectory": out}

    @app.post("/v1/levers", tags=["simulation"])
    def levers(body: LeverRequest, p: Principal = Depends(read_principal), db: Session = Depends(get_db)):
        fit, day, state = _model(db, p)
        try:
            res = lever_analysis(
                state,
                fit.rates,
                horizon_days=body.horizon_days,
                monthly_growth=body.monthly_growth,
                levers=body.levers,
                ceiling=body.ceiling,
            )
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        return {"start_day": day.isoformat(), "results": [r.to_dict() for r in res]}

    # -------------------------------------------------------------- admin
    @app.post("/v1/admin/keys", dependencies=[Depends(require_admin)], tags=["admin"], status_code=201)
    def create_key(body: KeyCreate, db: Session = Depends(get_db)):
        raw = generate_key(body.kind)
        db.add(
            ApiKey(
                key_hash=hash_key(raw),
                prefix=raw[:14],
                kind=body.kind,
                company_id=body.company_id,
                product_id=body.product_id,
                label=body.label,
            )
        )
        db.commit()
        return {
            "api_key": raw,
            "prefix": raw[:14],
            "kind": body.kind,
            "note": "store this key now; it is not retrievable",
        }

    @app.get("/v1/admin/keys", dependencies=[Depends(require_admin)], tags=["admin"])
    def list_keys(db: Session = Depends(get_db)):
        return [
            {
                "prefix": k.prefix,
                "kind": k.kind,
                "company_id": k.company_id,
                "product_id": k.product_id,
                "label": k.label,
                "revoked": k.revoked_at is not None,
            }
            for k in db.scalars(select(ApiKey).order_by(ApiKey.id))
        ]

    @app.delete("/v1/admin/keys/{prefix}", dependencies=[Depends(require_admin)], tags=["admin"])
    def revoke_key(prefix: str, db: Session = Depends(get_db)):
        rows = db.scalars(select(ApiKey).where(ApiKey.prefix == prefix, ApiKey.revoked_at.is_(None))).all()
        for r in rows:
            r.revoked_at = utcnow()
        db.commit()
        return {"revoked": len(rows)}

    @app.post("/v1/admin/members", dependencies=[Depends(require_admin)], tags=["admin"], status_code=201)
    def add_member(body: MemberCreate, db: Session = Depends(get_db)):
        db.merge(Member(**body.model_dump()))
        db.commit()
        return body.model_dump()

    _ = get_settings  # re-exported for dependency overrides in tests
    return app


def app_factory() -> FastAPI:  # for `uvicorn --factory growth_model_api.main:app_factory`
    return create_app()
