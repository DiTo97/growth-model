# growth-model

Monorepo scaffold for a Duolingo-style growth model service.

## Components

- `growth_model_core`: segmentation, transition rates, aggregate metrics, simulation engine.
- `growth_model_api`: FastAPI service for ingestion, computation, analytics, and simulations.
- `growth_model_cli`: Typer CLI for ingest/compute/metrics/simulate loops.
- `growth_model_sdk`: lightweight SDK with `log_active_user(...)` integration endpoint.
- `apps/web`: web console shell with Supabase auth hookup + metrics fetch UI.
- `infra/sql/schema.sql`: Postgres-compatible schema.
- `skills/growth-model-cli/SKILL.md`: Agent skill instructions for CLI-first workflows.

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
uvicorn growth_model_api.main:app --reload
```

In another shell:

```bash
growth-model-cli ingest --company-id acme --product-id mobile --user-id u1 --occurred-at 2026-01-01T00:00:00Z
growth-model-cli compute --company-id acme --start-date 2026-01-01 --end-date 2026-01-08
growth-model-cli metrics --company-id acme
growth-model-cli simulate --company-id acme --horizon-days 30 --override 'current_users->at_risk_wau=0.1'
```

## API key management

- Runtime ingestion and analytics auth: `x-api-key` (`GROWTH_MODEL_API_KEY` fallback for local dev).
- Admin key provisioning endpoints: `x-admin-key` (`GROWTH_MODEL_ADMIN_KEY`).
- Admin routes:
  - `POST /v1/admin/api-keys`
  - `GET /v1/admin/api-keys`
