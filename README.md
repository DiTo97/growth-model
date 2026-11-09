# growth-model

An open-source take on **[Duolingo's growth model](https://blog.duolingo.com/growth-model-duolingo/)**:
classify every user into one of 7 activity states each day, fit the transition rates between
states (CURR, NURR, iWAURR, …), and simulate how DAU/WAU/MAU respond when you move a rate. That
tells you *which retention metric a team should own*.

```bash
uv run growth-model demo-data demo.csv
uv run growth-model levers demo.csv --table
```
```
lever         direction  dau_impact
curr          increase   4.2270      ← improving current-user retention dominates
resurrection  increase   0.6007
new_users     increase   0.5957
iwaurr        increase   0.4198
...
```

## What's inside

| | |
| --- | --- |
| [`packages/core`](packages/core) | Zero-dependency Python library: segmentation, rate fitting, simulation, lever analysis |
| [`packages/sdk-python`](packages/sdk-python) · [`packages/sdk-js`](packages/sdk-js) | One-call SDKs: `active(user_id)`. Non-blocking, batched, never throws |
| [`apps/api`](apps/api) | Multi-tenant FastAPI service with daily/weekly jobs, simulations and levers |
| [`apps/cli`](apps/cli) | `growth-model` CLI. Works offline on a CSV or against the API, JSON-first for agents |
| [`apps/web`](apps/web) | Build-free console with Supabase auth |
| [`infra`](infra) | Postgres DDL, warehouse-native segmentation SQL, Docker, compose, crontab |
| [`skills`](skills) | Agent Skill for driving the CLI |

Spec: [docs/model.md](docs/model.md) · Architecture: [docs/architecture.md](docs/architecture.md) ·
Agents: [AGENTS.md](AGENTS.md)

## Quickstart

```bash
uv sync
export GROWTH_MODEL_ADMIN_TOKEN=change-me
KEY=$(uv run growth-model-server create-key --company-id acme --product-id app --kind secret)
uv run growth-model-server serve &

export GROWTH_MODEL_API_KEY=$KEY
uv run growth-model demo-data demo.csv --end $(date -u -d yesterday +%F)
uv run growth-model remote ingest demo.csv
uv run growth-model remote segment && uv run growth-model remote fit
uv run growth-model remote simulate --horizon 365 --set curr=0.75 --table
```

In your product:

```python
import growth_model_sdk as gm
gm.init(api_key="gm_pub_...", base_url="https://growth.example.com")
gm.active(user.id, metadata={"platform": "ios"})
```

```ts
import { createClient } from "@growth-model/sdk";
const gm = createClient({ apiKey: "gm_pub_...", baseUrl: "https://growth.example.com" });
gm.active(user.id);
```

## Development

`just setup && just check` (or see [CONTRIBUTING.md](CONTRIBUTING.md)).
