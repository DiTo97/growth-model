from __future__ import annotations

import json

import httpx
import typer

app = typer.Typer(help="Growth model CLI for ingestion, analysis, and simulation")


def _client(base_url: str, api_key: str):
    return httpx.Client(base_url=base_url, headers={"x-api-key": api_key}, timeout=30.0)


@app.command()
def ingest(
    base_url: str = typer.Option("http://localhost:8000"),
    api_key: str = typer.Option("dev-api-key"),
    company_id: str = typer.Option(...),
    product_id: str = typer.Option(...),
    user_id: str = typer.Option(...),
    occurred_at: str = typer.Option(...),
    platform: str = typer.Option("web"),
    app_version: str = typer.Option("dev"),
):
    payload = {
        "company_id": company_id,
        "product_id": product_id,
        "user_id": user_id,
        "occurred_at": occurred_at,
        "metadata": {"platform": platform, "app_version": app_version},
    }
    with _client(base_url, api_key) as client:
        res = client.post("/v1/ingest/activity", json=payload)
        res.raise_for_status()
    typer.echo("ingested")


@app.command()
def compute(
    base_url: str = typer.Option("http://localhost:8000"),
    api_key: str = typer.Option("dev-api-key"),
    company_id: str = typer.Option(...),
    start_date: str = typer.Option(...),
    end_date: str = typer.Option(...),
):
    payload = {"company_id": company_id, "start_date": start_date, "end_date": end_date}
    with _client(base_url, api_key) as client:
        res = client.post("/v1/jobs/compute", json=payload)
        res.raise_for_status()
        typer.echo(json.dumps(res.json(), indent=2))


@app.command()
def metrics(
    base_url: str = typer.Option("http://localhost:8000"),
    api_key: str = typer.Option("dev-api-key"),
    company_id: str = typer.Option(...),
):
    with _client(base_url, api_key) as client:
        res = client.get("/v1/metrics/distribution", params={"company_id": company_id})
        res.raise_for_status()
        typer.echo(json.dumps(res.json(), indent=2))


@app.command()
def simulate(
    base_url: str = typer.Option("http://localhost:8000"),
    api_key: str = typer.Option("dev-api-key"),
    company_id: str = typer.Option(...),
    horizon_days: int = typer.Option(30),
    override: list[str] = typer.Option([], help="transition overrides like current_users->at_risk_wau=0.2"),
):
    overrides = {}
    for item in override:
        key, value = item.split("=", maxsplit=1)
        overrides[key] = float(value)
    payload = {"company_id": company_id, "horizon_days": horizon_days, "overrides": overrides}
    with _client(base_url, api_key) as client:
        res = client.post("/v1/simulations/run", json=payload)
        res.raise_for_status()
        typer.echo(json.dumps(res.json(), indent=2))
