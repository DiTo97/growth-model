"""Operator entrypoint: `growth-model-server {serve,create-key,daily,weekly}`.

`daily` / `weekly` are what your scheduler (cron, k8s CronJob, GitHub Actions,
Supabase pg_cron + HTTP) should run — see infra/crontab.
"""

from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy import select

from growth_model_core import Windows

from . import service
from .auth import Principal, generate_key, hash_key
from .db import ApiKey, TrackedUser, make_engine, make_sessionmaker
from .settings import Settings


def _tenants(db) -> list[Principal]:
    rows = db.execute(select(TrackedUser.company_id, TrackedUser.product_id).distinct()).all()
    return [Principal(c, p, "secret") for c, p in rows]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="growth-model-server")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="run the HTTP API")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    k = sub.add_parser("create-key", help="mint an API key directly in the database")
    k.add_argument("--company-id", required=True)
    k.add_argument("--product-id", required=True)
    k.add_argument("--kind", choices=["publishable", "secret"], default="secret")
    k.add_argument("--label", default="")
    sub.add_parser("daily", help="segment all tenants through yesterday (incremental)")
    w = sub.add_parser("weekly", help="refit rates for all tenants")
    w.add_argument("--window-days", type=int, default=None)
    args = ap.parse_args(argv)

    settings = Settings.from_env()
    if args.cmd == "serve":
        import uvicorn

        uvicorn.run("growth_model_api.main:app_factory", factory=True, host=args.host, port=args.port)
        return 0

    db = make_sessionmaker(make_engine(settings.database_url))()
    if args.cmd == "create-key":
        raw = generate_key(args.kind)
        db.add(
            ApiKey(
                key_hash=hash_key(raw),
                prefix=raw[:14],
                kind=args.kind,
                company_id=args.company_id,
                product_id=args.product_id,
                label=args.label,
            )
        )
        db.commit()
        print(raw)
        return 0

    windows = Windows(settings.week_days, settings.month_days)
    results = []
    for p in _tenants(db):
        try:
            if args.cmd == "daily":
                results.append(
                    {"tenant": f"{p.company_id}/{p.product_id}", **service.run_segments(db, p, None, None, windows)}
                )
            else:
                fit = service.run_fit(db, p, None, args.window_days or settings.fit_window_days)
                results.append({"tenant": f"{p.company_id}/{p.product_id}", **fit.to_dict()})
        except LookupError as e:
            results.append({"tenant": f"{p.company_id}/{p.product_id}", "skipped": str(e)})
    json.dump(results, sys.stdout, indent=2, default=str)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
