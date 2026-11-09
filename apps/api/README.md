# growth-model-api

```bash
export GROWTH_MODEL_ADMIN_TOKEN=change-me          # enables /v1/admin/*
growth-model-server create-key --company-id acme --product-id app --kind secret
growth-model-server serve --port 8000              # OpenAPI docs at /docs
growth-model-server daily                          # cron: segment all tenants through yesterday
growth-model-server weekly                         # cron: refit rates
```

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| POST | `/v1/events` | publishable or secret | ingest `{events: [{user_id, timestamp?, metadata?}]}` |
| POST | `/v1/jobs/segments` | secret / member | materialise daily segment + transition counts |
| POST | `/v1/jobs/fit` | secret / member | fit rates on a trailing window |
| GET | `/v1/segments`, `/v1/metrics` | secret / member | state and DAU/WAU/MAU time series |
| GET | `/v1/rates`, `/v1/rates/history` | secret / member | latest fit and fit history |
| POST | `/v1/simulations` | secret / member | `{horizon_days, overrides, new_users_per_day}` |
| POST | `/v1/levers` | secret / member | lever ranking |
| * | `/v1/admin/keys`, `/v1/admin/members` | admin token | key minting/revocation, Supabase membership |

Environment: `DATABASE_URL` (SQLite default; `postgresql+psycopg://…` with the `postgres` extra),
`GROWTH_MODEL_ADMIN_TOKEN`, `SUPABASE_URL` (JWKS) or `SUPABASE_JWT_SECRET` (legacy HS256),
`CORS_ORIGINS`, `GROWTH_MODEL_{WEEK,MONTH,FIT_WINDOW}_DAYS`.
