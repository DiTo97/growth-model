# AGENTS.md

Guidance for AI coding agents (Claude Code, Codex, Copilot, Cursor, Gemini, …) working in this repo.
Humans: see [README.md](README.md) and [CONTRIBUTING.md](CONTRIBUTING.md). Nested `AGENTS.md` files in
sub-packages add package-specific rules; the closest one to the file you edit wins.

## What this is

An open-source implementation of [Duolingo's growth model](https://blog.duolingo.com/growth-model-duolingo/):
users are classified daily into 7 states, day-over-day transition rates are fitted, and a Markov
model projects DAU/WAU/MAU under "what if" rate changes. The canonical spec is [docs/model.md](docs/model.md).

## Layout (uv workspace + one npm package)

| Path | Distribution | Role |
| --- | --- | --- |
| `packages/core` | `growth-model-core` | **Zero-dependency** domain library: segmentation, rate fitting, simulation, levers, sources |
| `packages/sdk-python` | `growth-model-sdk` | One-call ingestion SDK (`active(user_id)`), depends only on httpx |
| `packages/sdk-js` | `@growth-model/sdk` | Same SDK for browsers / Node / RN, zero deps, TypeScript |
| `apps/api` | `growth-model-api` | FastAPI multi-tenant service + `growth-model-server` ops CLI (daily/weekly jobs) |
| `apps/cli` | `growth-model-cli` | `growth-model` analyst/agent CLI (local CSV mode + `remote` mode) |
| `apps/web` | — | Static console, Supabase magic-link auth |
| `infra/` | — | Postgres DDL, warehouse-native segmentation SQL, Dockerfile, compose, crontab |
| `skills/` | — | Agent Skills (also linked from `.claude/skills/`) |
| `docs/` | — | Model spec, architecture, ADRs |

Dependency direction is strictly `apps/* → packages/core`. The core must never import from apps,
and must stay stdlib-only.

## Commands

```bash
uv sync                                  # install the whole workspace (Python 3.11+)
uv run pytest                            # all Python tests
uv run ruff check . && uv run ruff format --check .
uv run pyright                           # type check
(cd packages/sdk-js && npm ci && npm test && npm run typecheck)
uv run growth-model --help               # analyst CLI
uv run growth-model-server serve         # API on :8000 (SQLite by default)
```

`just` wraps these (`just check` runs everything CI runs).

## Rules

- **Run `just check` (or the commands above) before claiming a change works.**
- Model semantics live in `packages/core`. Any change to segment definitions, rate names or the
  simulation equations must update `docs/model.md` and the invariant tests in
  `packages/core/tests/test_core.py` (diagram-only transitions, WAU/MAU = rolling windows,
  one-step replay reproduces observed counts, population conservation).
- `infra/sql/schema.sql` mirrors `apps/api/src/growth_model_api/db.py`; change both together.
  `infra/sql/segments.sql` must stay equivalent to `growth_model_core.segment_users`.
- The tenant (`company_id`, `product_id`) is always derived from the credential, never from
  request bodies or query params. Publishable keys (`gm_pub_`) may only ingest.
- SDKs must never throw into or block the host application.
- Rate identifiers are lowercase (`curr`, `nurr`, `iwaurr`, `wau_loss`, …); parsing is case-insensitive.
- Keep public APIs typed; prefer small pure functions; no new runtime deps in `packages/core`.
- Do not commit secrets, `.env`, `apps/web/config.js`, or `*.db` files.

## Useful context

- Duolingo's prose definitions are slightly inconsistent with its own diagram; we use rolling
  windows so the diagram holds exactly. See `docs/adr/0001-rolling-window-segments.md`.
- New users are exogenous in the model (`new_users_per_day`), as in the blog post.
