"""Lever analysis: "pull each lever and see what happens to DAU".

Reproduces the analysis in the Duolingo post: improve one input at a time by a
compounding month-over-month rate (2% by default) over a long horizon
(3 years by default) and compare final DAU against the baseline.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from .rates import RATE_EDGES, RATE_GROUPS, Rate, Rates
from .segments import Segment
from .simulation import simulate

NEW_USERS = "new_users"
LOSS_RATES = frozenset({Rate.WAU_LOSS, Rate.MAU_LOSS})
DEFAULT_LEVERS: tuple[str, ...] = (*(r.value for r in Rate), NEW_USERS)


@dataclass(frozen=True, slots=True)
class LeverResult:
    lever: str
    direction: str  # "increase" or "decrease"
    baseline_dau: float
    final_dau: float

    @property
    def dau_impact(self) -> float:
        return (self.final_dau / self.baseline_dau - 1.0) if self.baseline_dau else 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "lever": self.lever,
            "direction": self.direction,
            "baseline_dau": self.baseline_dau,
            "final_dau": self.final_dau,
            "dau_impact": self.dau_impact,
        }


DEFAULT_CEILING = 0.95


def _cap(rates: Rates, lever: Rate, value: float, ceiling: float) -> float:
    """Keep the lever a valid probability and below ``ceiling``.

    Without a ceiling a compounding retention rate reaches 1.0 (nobody ever
    churns) and DAU explodes. The blog does not say how Duolingo bounded its
    levers, so the ceiling is explicit and user-tunable.
    """
    src = RATE_EDGES[lever][0]
    others = sum(rates[r] for r in RATE_GROUPS[src] if r is not lever)
    return max(0.0, min(value, 1.0 - others, max(ceiling, rates[lever])))


def scenario(rates: Rates, lever: str, monthly_growth: float, ceiling: float = DEFAULT_CEILING):
    """Return ``day -> Rates`` where ``lever`` compounds by ``monthly_growth`` per 30 days."""
    if lever == NEW_USERS:
        return lambda day: rates.with_overrides(
            new_users_per_day=rates.new_users_per_day * (1 + monthly_growth) ** (day / 30)
        )
    r = Rate(lever)
    sign = -1.0 if r in LOSS_RATES else 1.0
    return lambda day: rates.with_overrides(
        {r: _cap(rates, r, rates[r] * (1 + sign * monthly_growth) ** (day / 30), ceiling)}
    )


def lever_analysis(
    initial: Mapping[Segment, float],
    rates: Rates,
    *,
    horizon_days: int = 3 * 365,
    monthly_growth: float = 0.02,
    levers: Iterable[str] = DEFAULT_LEVERS,
    ceiling: float = DEFAULT_CEILING,
) -> list[LeverResult]:
    """Rank levers by their DAU impact at ``horizon_days``, largest first."""
    baseline = simulate(initial, rates, horizon_days)[-1].metrics["dau"]
    results = []
    for lever in levers:
        final = simulate(initial, scenario(rates, lever, monthly_growth, ceiling), horizon_days)[-1].metrics["dau"]
        direction = "decrease" if lever in {r.value for r in LOSS_RATES} else "increase"
        results.append(LeverResult(lever, direction, baseline, final))
    return sorted(results, key=lambda x: x.dau_impact, reverse=True)
