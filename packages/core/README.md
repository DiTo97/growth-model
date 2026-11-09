# growth-model-core

Zero-dependency (stdlib-only) implementation of [Duolingo's growth model](../../docs/model.md).

```python
from growth_model_core import GrowthModel, read_csv

model = GrowthModel.from_activity(read_csv("activity.csv"))   # rows of (user_id, day)
model.rates.to_dict()                                         # {"curr": 0.81, "nurr": 0.47, ...}
model.simulate(365, overrides={"curr": 0.85})[-1].metrics     # {"dau": ..., "wau": ..., "mau": ...}
[r.to_dict() for r in model.levers()]                         # DAU impact ranking
```

Lower-level building blocks: `segment_users`, `estimate_rates`, `simulate`, `lever_analysis`,
`read_posthog`, `synthetic_activity`.
