# Growth Model CLI Skill

Use `growth-model-cli` to run full analysis loops:

1. `growth-model-cli ingest ...` to send activity events.
2. `growth-model-cli compute ...` to recompute daily states and transitions.
3. `growth-model-cli metrics ...` to inspect DAU/WAU/MAU.
4. `growth-model-cli simulate ... --override current_users->at_risk_wau=0.1` to run scenarios.
