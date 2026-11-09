# The growth model — specification

Source: Erin Gustafson, *Meaningful metrics: how data sharpened the focus of product teams*,
Duolingo blog, 2023-02-17 — <https://blog.duolingo.com/growth-model-duolingo/>.

## States

Every user who has ever been active is in exactly one state per (UTC) day. Let `d` be days since
the user's last active day (`0` = active today) and `g` the gap between today and the previous
active day when active today. Defaults: `week = 7`, `month = 30` (`Windows` in the core).

| State | Code | Rule |
| --- | --- | --- |
| New | `new` | active today, never active before |
| Current | `current` | active today, `g ≤ week` |
| Reactivated | `reactivated` | active today, `week < g ≤ month` |
| Resurrected | `resurrected` | active today, `g > month` |
| At-risk WAU | `at_risk_wau` | `1 ≤ d < week` |
| At-risk MAU | `at_risk_mau` | `week ≤ d < month` |
| Dormant | `dormant` | `d ≥ month` |

Users do not exist before their first active day. With these rules
`DAU = new + current + reactivated + resurrected`, `WAU = DAU + at_risk_wau` and
`MAU = WAU + at_risk_mau` equal the usual 7-day / 30-day rolling-window counts, and the only
possible day-over-day transitions are the arrows in the blog's diagram (tested).

## Rates

| Rate | Code | Edge |
| --- | --- | --- |
| NURR | `nurr` | new → current |
| CURR | `curr` | current → current |
| RURR | `rurr` | reactivated → current |
| SURR | `surr` | resurrected → current |
| iWAURR | `iwaurr` | at_risk_wau → current |
| WAU loss rate | `wau_loss` | at_risk_wau → at_risk_mau |
| Reactivation rate | `reactivation` | at_risk_mau → reactivated |
| MAU loss rate | `mau_loss` | at_risk_mau → dormant |
| Resurrection rate | `resurrection` | dormant → resurrected |

All other arrows are complements (`ARWAURR = 1 − iWAURR − WAU loss`, `ARMAURR = 1 − reactivation −
MAU loss`, `DormantRR = 1 − resurrection`, `X → at_risk_wau = 1 − XRR` for active states).
Rates are fitted as pooled ratios over a trailing window (default 28 days; MLE for a
time-homogeneous chain). `new_users_per_day` is the window mean of the `new` state.

## Simulation (blog appendix)

```
Reactivated_t = reactivation · AtRiskMAU_{t-1}
Resurrected_t = resurrection · Dormant_{t-1}
Current_t     = NURR·New_{t-1} + RURR·Reactivated_{t-1} + SURR·Resurrected_{t-1} + CURR·Current_{t-1} + iWAURR·AtRiskWAU_{t-1}
AtRiskWAU_t   = ARWAURR·AtRiskWAU_{t-1} + (1-CURR)·Current_{t-1} + (1-RURR)·Reactivated_{t-1} + (1-NURR)·New_{t-1} + (1-SURR)·Resurrected_{t-1}
AtRiskMAU_t   = ARMAURR·AtRiskMAU_{t-1} + WAUloss·AtRiskWAU_{t-1}
Dormant_t     = DormantRR·Dormant_{t-1} + MAUloss·AtRiskMAU_{t-1}
New_t         = new_users_per_day                         (exogenous; "unmeasured" in the blog)
```

## Lever analysis

Reproduces the blog's table ("impact on DAUs in 3 years" of 2% month-over-month growth in each
lever): each lever compounds by `(1 ± g)^(t/30)` (loss rates decrease), bounded so outgoing rates
from a state sum to ≤ 1 and the lever stays ≤ `ceiling` (default 0.95, configurable). Final DAU is
compared against the baseline projection.

## Deviations from / gaps in the source

1. **Window boundaries.** The prose says users stay at-risk WAU for "their first 7 days of
   inactivity" and at-risk MAU "up to 22 days", which implies an 8-day WAU and would allow
   at_risk_wau → reactivated, an arrow that is not in the diagram. We use rolling windows instead
   (ADR 0001). Both lengths are configurable.
2. **Lever mechanics.** The blog does not say how levers are bounded. Without a ceiling,
   compounding CURR reaches 1.0 (no churn) and DAU explodes; results depend strongly on `ceiling`.
3. **Aliasing.** Duolingo merges multiple accounts and devices into one learner before modelling.
   Here `user_id` is trusted as given.
4. **Aggregate only.** As the blog itself notes, one CURR averaged over a large, mixed population
   hides sub-segments. Cohort or segment splits (platform, country) are not modelled yet.
