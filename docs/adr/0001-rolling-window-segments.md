# ADR 0001 — Rolling-window segment definitions

**Status:** accepted

**Context.** The Duolingo post defines at-risk WAU as "first 7 days of inactivity" and at-risk MAU as
"up to 22 days" (dormant at 30). Taken literally, WAU becomes an 8-day window, and a user inactive
for 7 days who returns would be "current" by the prose but come from at-risk MAU in the diagram, where
at-risk MAU only leads to reactivated. The prose and the diagram cannot both hold.

**Decision.** Use rolling windows: at-risk WAU for `1 ≤ d < 7`, at-risk MAU for `7 ≤ d < 30`, dormant for
`d ≥ 30`; on an active day, current if the gap is `≤ 7`, reactivated if `≤ 30`, else resurrected.
Window lengths are configurable (`Windows`, `GROWTH_MODEL_{WEEK,MONTH}_DAYS`).

**Consequences.** WAU/MAU equal standard 7/30-day actives, and only the diagram's transitions can
occur; the tests enforce both. Numbers may differ slightly from a literal reading of the prose.
