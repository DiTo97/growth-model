"""`growth-model` CLI.

Local commands work on a CSV of activity with no server (great for analysts and
AI agents). `growth-model remote ...` talks to a running growth-model API.
Output is JSON by default; pass `--table` for a human-readable view.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Annotated, Any

import httpx
import typer

from growth_model_core import GrowthModel, parse_rate, read_csv, synthetic_activity, write_csv

app = typer.Typer(help=__doc__, no_args_is_help=True, add_completion=False)
remote = typer.Typer(
    help="Call a running growth-model API (uses GROWTH_MODEL_URL / GROWTH_MODEL_API_KEY).", no_args_is_help=True
)
app.add_typer(remote, name="remote")

CsvArg = Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="CSV with user_id and day|timestamp columns")]
TableOpt = Annotated[bool, typer.Option("--table", help="Human-readable output instead of JSON")]
FitWindow = Annotated[int, typer.Option(help="Days of history used to fit rates")]
SetOpt = Annotated[list[str], typer.Option("--set", help="Rate override, e.g. --set curr=0.85 (repeatable)")]


def _emit(data: Any, table: bool = False) -> None:
    if not table:
        typer.echo(json.dumps(data, indent=2, default=str))
        return
    rows = data if isinstance(data, list) else [data]
    if rows and isinstance(rows[0], dict):
        cols = list(rows[0].keys())
        fmt = lambda v: f"{v:.4f}" if isinstance(v, float) else str(v)  # noqa: E731
        widths = [max(len(c), *(len(fmt(r.get(c, ""))) for r in rows)) for c in cols]
        typer.echo("  ".join(c.ljust(w) for c, w in zip(cols, widths, strict=True)))
        for r in rows:
            typer.echo("  ".join(fmt(r.get(c, "")).ljust(w) for c, w in zip(cols, widths, strict=True)))
    else:
        typer.echo(str(data))


def _overrides(items: list[str]) -> dict[str, float]:
    out = {}
    for item in items:
        if "=" not in item:
            raise typer.BadParameter(f"expected rate=value, got {item!r}")
        k, v = item.split("=", 1)
        out[parse_rate(k).value] = float(v)
    return out


def _model(csv: Path, fit_window: int) -> GrowthModel:
    return GrowthModel.from_activity(read_csv(csv), fit_window_days=fit_window)


# --------------------------------------------------------------------- local
@app.command("demo-data")
def demo_data(
    out: Annotated[Path, typer.Argument(help="Where to write the CSV")],
    days: int = 120,
    new_users_per_day: int = 40,
    end: Annotated[str, typer.Option(help="Last day (YYYY-MM-DD)")] = "2026-01-31",
    seed: int = 7,
) -> None:
    """Write synthetic activity data to try the model."""
    n = write_csv(synthetic_activity(days, new_users_per_day, date.fromisoformat(end), seed), out)
    _emit({"rows": n, "path": str(out)})


@app.command()
def fit(csv: CsvArg, fit_window: FitWindow = 28, table: TableOpt = False) -> None:
    """Segment users and fit transition rates."""
    m = _model(csv, fit_window)
    data = {
        "as_of": m.fit.as_of.isoformat(),
        "window_days": m.fit.window_days,
        "rates": m.rates.to_dict(),
        "latest_state": {s.value: n for s, n in m.latest_state().items()},
        "unexpected_transitions": m.panel.unexpected_transitions,
    }
    _emit([{"rate": k, "value": v} for k, v in data["rates"].items()] if table else data, table)


@app.command()
def metrics(
    csv: CsvArg, last: Annotated[int, typer.Option(help="Only the last N days")] = 0, table: TableOpt = False
) -> None:
    """Daily DAU/WAU/MAU and segment sizes."""
    m = _model(csv, 28)
    rows = [
        {"day": d.isoformat(), **agg, **{s.value: m.panel.counts[d][s] for s in m.panel.counts[d]}}
        for d, agg in m.metrics().items()
    ]
    _emit(rows[-last:] if last else rows, table)


@app.command()
def simulate(
    csv: CsvArg,
    horizon: Annotated[int, typer.Option(help="Days to project")] = 365,
    set_: SetOpt = [],  # noqa: B006
    new_users: Annotated[float | None, typer.Option(help="Override new users per day")] = None,
    every: Annotated[int, typer.Option(help="Emit every Nth day")] = 30,
    fit_window: FitWindow = 28,
    table: TableOpt = False,
) -> None:
    """Project DAU/WAU/MAU forward, optionally with rate overrides."""
    m = _model(csv, fit_window)
    base = m.simulate(horizon)
    scen = m.simulate(horizon, _overrides(set_), new_users)
    rows = [
        {
            "day": s.day,
            **{k: round(v, 1) for k, v in s.metrics.items()},
            "dau_vs_baseline": s.metrics["dau"] / b.metrics["dau"] - 1 if b.metrics["dau"] else 0.0,
        }
        for b, s in zip(base, scen, strict=True)
        if s.day % every == 0 or s.day == horizon
    ]
    _emit(rows, table)


@app.command()
def levers(
    csv: CsvArg,
    horizon: Annotated[int, typer.Option(help="Days to project")] = 3 * 365,
    growth: Annotated[float, typer.Option(help="Month-over-month improvement per lever")] = 0.02,
    ceiling: Annotated[float, typer.Option(help="Max value a pulled rate may reach")] = 0.95,
    fit_window: FitWindow = 28,
    table: TableOpt = False,
) -> None:
    """Rank levers by DAU impact (the Duolingo "which metric matters" analysis)."""
    _emit([r.to_dict() for r in _model(csv, fit_window).levers(horizon, growth, ceiling=ceiling)], table)


# -------------------------------------------------------------------- remote
def _client() -> httpx.Client:
    key = os.getenv("GROWTH_MODEL_API_KEY")
    if not key:
        raise typer.BadParameter("set GROWTH_MODEL_API_KEY (a gm_sk_ secret key)")
    return httpx.Client(
        base_url=os.getenv("GROWTH_MODEL_URL", "http://localhost:8000"),
        headers={"Authorization": f"Bearer {key}"},
        timeout=120,
    )


def _call(method: str, path: str, **kw: Any) -> Any:
    with _client() as c:
        res = c.request(method, path, **kw)
    if res.status_code >= 400:
        typer.echo(json.dumps({"status": res.status_code, "error": res.text}), err=True)
        raise typer.Exit(1)
    return res.json()


@remote.command("ingest")
def r_ingest(csv: CsvArg) -> None:
    """Upload a CSV of activity in batches."""
    rows = [{"user_id": u, "timestamp": f"{d.isoformat()}T12:00:00Z"} for u, d in read_csv(csv)]
    total = 0
    for i in range(0, len(rows), 1000):
        total += _call("POST", "/v1/events", json={"events": rows[i : i + 1000]})["accepted"]
    _emit({"accepted_user_days": total})


@remote.command("segment")
def r_segment(start: str | None = None, end: str | None = None) -> None:
    """Run the (daily) segmentation job."""
    _emit(_call("POST", "/v1/jobs/segments", json={"start": start, "end": end}))


@remote.command("fit")
def r_fit(window_days: int = 28, as_of: str | None = None) -> None:
    """Run the (weekly) rate-fitting job."""
    _emit(_call("POST", "/v1/jobs/fit", json={"window_days": window_days, "as_of": as_of}))


@remote.command("metrics")
def r_metrics(start: str | None = None, end: str | None = None, table: TableOpt = False) -> None:
    _emit(_call("GET", "/v1/metrics", params={k: v for k, v in {"start": start, "end": end}.items() if v}), table)


@remote.command("rates")
def r_rates() -> None:
    _emit(_call("GET", "/v1/rates"))


@remote.command("simulate")
def r_simulate(horizon: int = 365, set_: SetOpt = [], new_users: float | None = None, table: TableOpt = False) -> None:  # noqa: B006
    data = _call(
        "POST",
        "/v1/simulations",
        json={"horizon_days": horizon, "overrides": _overrides(set_), "new_users_per_day": new_users},
    )
    _emit(data["trajectory"] if table else data, table)


@remote.command("levers")
def r_levers(horizon: int = 3 * 365, growth: float = 0.02, ceiling: float = 0.95, table: TableOpt = False) -> None:
    _emit(
        _call("POST", "/v1/levers", json={"horizon_days": horizon, "monthly_growth": growth, "ceiling": ceiling})[
            "results"
        ],
        table,
    )


if __name__ == "__main__":
    app()
