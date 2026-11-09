"""Discrete-time forward simulation using the appendix equations of the blog post."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from .rates import Rate, Rates
from .segments import SEGMENTS, Segment, aggregates

S = Segment


@dataclass(frozen=True, slots=True)
class SimulationStep:
    day: int
    segments: dict[Segment, float]

    @property
    def metrics(self) -> dict[str, float]:
        return aggregates(self.segments)

    def to_dict(self) -> dict[str, object]:
        return {"day": self.day, **self.metrics, "segments": {s.value: v for s, v in self.segments.items()}}


def step(state: Mapping[Segment, float], r: Rates) -> dict[Segment, float]:
    """Advance one day.

    ``NEW`` is exogenous (the model does not measure acquisition), so it is set
    from ``r.new_users_per_day``.
    """
    nu, cu, ru, su = (state.get(s, 0.0) for s in (S.NEW, S.CURRENT, S.REACTIVATED, S.RESURRECTED))
    aw, am, du = (state.get(s, 0.0) for s in (S.AT_RISK_WAU, S.AT_RISK_MAU, S.DORMANT))
    v = r.values
    return {
        S.NEW: r.new_users_per_day,
        S.CURRENT: nu * v[Rate.NURR] + ru * v[Rate.RURR] + su * v[Rate.SURR] + cu * v[Rate.CURR] + aw * v[Rate.IWAURR],
        S.REACTIVATED: am * v[Rate.REACTIVATION],
        S.RESURRECTED: du * v[Rate.RESURRECTION],
        S.AT_RISK_WAU: aw * (1 - v[Rate.IWAURR] - v[Rate.WAU_LOSS])
        + cu * (1 - v[Rate.CURR])
        + ru * (1 - v[Rate.RURR])
        + nu * (1 - v[Rate.NURR])
        + su * (1 - v[Rate.SURR]),
        S.AT_RISK_MAU: am * (1 - v[Rate.REACTIVATION] - v[Rate.MAU_LOSS]) + aw * v[Rate.WAU_LOSS],
        S.DORMANT: du * (1 - v[Rate.RESURRECTION]) + am * v[Rate.MAU_LOSS],
    }


def simulate(
    initial: Mapping[Segment, float],
    rates: Rates | Callable[[int], Rates],
    horizon_days: int,
) -> list[SimulationStep]:
    """Project segment sizes ``horizon_days`` forward.

    ``rates`` may be a callable ``day -> Rates`` for time-varying scenarios
    (e.g. a lever that grows 2% month over month). Day 0 is the initial state.
    """
    if horizon_days < 0:
        raise ValueError("horizon_days must be >= 0")
    rate_fn = rates if callable(rates) else (lambda _day: rates)
    state = {s: float(initial.get(s, 0.0)) for s in SEGMENTS}
    out = [SimulationStep(0, dict(state))]
    for day in range(1, horizon_days + 1):
        state = step(state, rate_fn(day))
        out.append(SimulationStep(day, state))
    return out
