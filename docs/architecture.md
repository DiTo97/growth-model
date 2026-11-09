# Architecture

```
 your app ──SDK.active(user)──▶ POST /v1/events ──▶ tracked_users + activity_days   (1 row / user / UTC day)
                                                         │
                         cron: growth-model-server daily  ▼
                                               segment_counts + transition_counts  (growth_model_core.segment_users)
                                                         │
                         cron: growth-model-server weekly ▼
                                                     rate_fits                      (growth_model_core.estimate_rates)
                                                         │
     web console / CLI / agents ◀── GET metrics, rates · POST simulations, levers (growth_model_core.simulate)
```

Alternative path for teams that already have events in a warehouse or PostHog: skip the SDK and
either run `infra/sql/segments.sql` in the warehouse, or pull `(user_id, day)` rows with
`growth_model_core.read_posthog` / `read_csv` and use the CLI locally.

## Tenancy and auth

- Tenant = `(company_id, product_id)`, always resolved from the credential.
- `gm_pub_` publishable keys: ingest only (safe in client apps). `gm_sk_` secret keys: full read for one tenant.
- Console users authenticate with Supabase. The API verifies the JWT (JWKS via `SUPABASE_URL`, or a
  legacy HS256 secret) and maps `sub` to a tenant through `members`.
- Admin endpoints need `GROWTH_MODEL_ADMIN_TOKEN` and are disabled when it is unset.

## Jobs

- **Daily** (`/v1/jobs/segments`, `growth-model-server daily`): incremental from the last
  materialised day through yesterday (UTC); idempotent for explicit ranges. It loads tenant users and a
  31-day lookback of activity into memory.
- **Weekly** (`/v1/jobs/fit`, `growth-model-server weekly`): pooled fit over the trailing window
  from stored transition counts. Every fit is kept, which gives a rate history.
