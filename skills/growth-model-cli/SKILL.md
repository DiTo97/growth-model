---
name: growth-model-cli
description: Analyse user retention and growth with the Duolingo-style growth model via the `growth-model` CLI. Use when asked which metric moves DAU most, to fit retention/churn rates (CURR, NURR, iWAURR, WAU/MAU loss, reactivation, resurrection) from activity logs, to forecast DAU/WAU/MAU, or to run what-if simulations on rate changes.
---

# Growth model CLI

The `growth-model` CLI fits a 7-state Markov model of user activity (new, current, reactivated,
resurrected, at-risk WAU, at-risk MAU, dormant) and simulates DAU/WAU/MAU. Output is JSON by
default, so parse it directly. Add `--table` only when showing results to a human.

## Inputs

- **Local mode** (preferred for analysis): a CSV with `user_id` plus `day` (YYYY-MM-DD) or
  `timestamp` (ISO 8601, UTC) — one row per activity, duplicates are fine.
  No data? `growth-model demo-data demo.csv` writes a synthetic dataset.
- **Remote mode**: `growth-model remote …` with `GROWTH_MODEL_URL` and `GROWTH_MODEL_API_KEY`
  (a `gm_sk_` secret key) in the environment.

Need at least ~60 days of history: the first 31 days are a warm-up for lookback windows,
and rates are fitted on the trailing 28 days (`--fit-window`).

## Workflow

1. **Fit**: `growth-model fit activity.csv` → `rates`, `latest_state`, `unexpected_transitions`.
   `unexpected_transitions` must be 0. If not, the input is malformed (check timezones and duplicate IDs).
2. **Baseline**: `growth-model metrics activity.csv --last 30` → DAU/WAU/MAU and segment sizes.
3. **Rank levers**: `growth-model levers activity.csv` → each lever improved 2% month-over-month
   for 3 years (`--horizon`, `--growth`, `--ceiling`), sorted by DAU impact. This is the question
   "which metric should a team own?".
4. **What-if**: `growth-model simulate activity.csv --horizon 365 --set curr=0.82 --set nurr=0.5`
   → trajectory every `--every` days with `dau_vs_baseline`. `--new-users N` overrides acquisition.

Rate names (case-insensitive): `nurr curr rurr surr iwaurr wau_loss reactivation mau_loss resurrection`.
Rates leaving the same state must sum to ≤ 1 (e.g. `iwaurr + wau_loss`), otherwise the command errors.

## Remote equivalents

```bash
growth-model remote ingest activity.csv   # upload
growth-model remote segment               # daily job (incremental)
growth-model remote fit --window-days 28  # weekly job
growth-model remote metrics | rates | simulate --set curr=0.8 | levers
```

## Reporting results

- Quote rates as percentages and say which window they were fitted on (`as_of`, `window_days`).
- Lever impact depends on `--ceiling` and on the horizon. Say so when recommending a lever.
- This is a correlational model: recommend A/B tests to confirm a lever is movable and causal.
