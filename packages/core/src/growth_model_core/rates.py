"""Transition-rate estimation (the "training" step of the Markov model).

The growth model has nine free transition probabilities; every other arrow is
the complement of one of them (e.g. ``AT_RISK_WAU -> AT_RISK_WAU`` is
``1 - iWAURR - WAU_LOSS``). Rates are estimated as pooled ratios over a fitting
window, which is the maximum-likelihood estimate for a time-homogeneous chain.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import date
from enum import StrEnum

from .segments import Segment, SegmentPanel

S = Segment


class Rate(StrEnum):
    NURR = "nurr"  # new -> current
    CURR = "curr"  # current -> current
    RURR = "rurr"  # reactivated -> current
    SURR = "surr"  # resurrected -> current
    IWAURR = "iwaurr"  # at-risk WAU -> current
    WAU_LOSS = "wau_loss"  # at-risk WAU -> at-risk MAU
    REACTIVATION = "reactivation"  # at-risk MAU -> reactivated
    MAU_LOSS = "mau_loss"  # at-risk MAU -> dormant
    RESURRECTION = "resurrection"  # dormant -> resurrected


# (from, to) for each free rate.
RATE_EDGES: dict[Rate, tuple[Segment, Segment]] = {
    Rate.NURR: (S.NEW, S.CURRENT),
    Rate.CURR: (S.CURRENT, S.CURRENT),
    Rate.RURR: (S.REACTIVATED, S.CURRENT),
    Rate.SURR: (S.RESURRECTED, S.CURRENT),
    Rate.IWAURR: (S.AT_RISK_WAU, S.CURRENT),
    Rate.WAU_LOSS: (S.AT_RISK_WAU, S.AT_RISK_MAU),
    Rate.REACTIVATION: (S.AT_RISK_MAU, S.REACTIVATED),
    Rate.MAU_LOSS: (S.AT_RISK_MAU, S.DORMANT),
    Rate.RESURRECTION: (S.DORMANT, S.RESURRECTED),
}

# Rates sharing a source state must sum to <= 1.
RATE_GROUPS: dict[Segment, tuple[Rate, ...]] = {}
for _rate, (_src, _) in RATE_EDGES.items():
    RATE_GROUPS.setdefault(_src, ())
    RATE_GROUPS[_src] = (*RATE_GROUPS[_src], _rate)

ALIASES: dict[str, Rate] = {r.value: r for r in Rate} | {r.name.lower(): r for r in Rate}


def parse_rate(name: str) -> Rate:
    try:
        return ALIASES[name.strip().lower().replace("-", "_")]
    except KeyError:
        raise ValueError(f"unknown rate {name!r}; expected one of {[r.value for r in Rate]}") from None


@dataclass(frozen=True, slots=True)
class Rates:
    """A full parameterisation of the growth model."""

    values: Mapping[Rate, float]
    new_users_per_day: float = 0.0

    def __post_init__(self) -> None:
        missing = set(Rate) - set(self.values)
        if missing:
            raise ValueError(f"missing rates: {sorted(m.value for m in missing)}")
        for r, v in self.values.items():
            if not 0.0 <= v <= 1.0:
                raise ValueError(f"{r.value}={v} is not a probability")
        for src, group in RATE_GROUPS.items():
            if sum(self.values[r] for r in group) > 1.0 + 1e-9:
                raise ValueError(f"outgoing rates from {src.value} sum to > 1: {[r.value for r in group]}")
        if self.new_users_per_day < 0:
            raise ValueError("new_users_per_day must be >= 0")

    def __getitem__(self, rate: Rate) -> float:
        return self.values[rate]

    def with_overrides(
        self, overrides: Mapping[Rate | str, float] | None = None, new_users_per_day: float | None = None
    ) -> Rates:
        vals = dict(self.values)
        for k, v in (overrides or {}).items():
            vals[parse_rate(k) if isinstance(k, str) else k] = float(v)
        return replace(
            self,
            values=vals,
            new_users_per_day=self.new_users_per_day if new_users_per_day is None else new_users_per_day,
        )

    def to_dict(self) -> dict[str, float]:
        return {r.value: self.values[r] for r in Rate} | {"new_users_per_day": self.new_users_per_day}

    @classmethod
    def from_dict(cls, data: Mapping[str, float]) -> Rates:
        d = dict(data)
        nupd = float(d.pop("new_users_per_day", 0.0))
        return cls(values={parse_rate(k): float(v) for k, v in d.items()}, new_users_per_day=nupd)


@dataclass(frozen=True, slots=True)
class RateFit:
    as_of: date
    window_days: int
    rates: Rates
    # Number of users observed in each source state (denominator) — use as a confidence signal.
    exposure: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "as_of": self.as_of.isoformat(),
            "window_days": self.window_days,
            "rates": self.rates.to_dict(),
            "exposure": self.exposure,
        }


def _ratio(num: int, den: int, default: float) -> float:
    return num / den if den else default


def estimate_rates(
    transitions: Iterable[Counter[tuple[Segment, Segment]]],
    new_user_counts: Iterable[int],
    *,
    as_of: date,
    window_days: int,
    prior: Rates | None = None,
) -> RateFit:
    """Pool transition counts over a window and return the fitted rates.

    States never observed in the window fall back to ``prior`` (or 0).
    """
    pooled: Counter[tuple[Segment, Segment]] = Counter()
    for t in transitions:
        pooled.update(t)
    totals: Counter[Segment] = Counter()
    for (src, _), n in pooled.items():
        totals[src] += n
    new_users = list(new_user_counts)
    values = {r: _ratio(pooled[edge], totals[edge[0]], prior[r] if prior else 0.0) for r, edge in RATE_EDGES.items()}
    rates = Rates(values=values, new_users_per_day=(sum(new_users) / len(new_users)) if new_users else 0.0)
    return RateFit(as_of=as_of, window_days=window_days, rates=rates, exposure={s.value: totals[s] for s in Segment})


def fit_panel(panel: SegmentPanel, window_days: int = 28, as_of: date | None = None) -> RateFit:
    """Fit rates on the trailing ``window_days`` of a :class:`SegmentPanel`."""
    days = [d for d in panel.days() if as_of is None or d <= as_of]
    if not days:
        raise ValueError("panel has no days at or before as_of")
    window = days[-window_days:]
    return estimate_rates(
        (panel.transitions[d] for d in window),
        (panel.counts[d][Segment.NEW] for d in window),
        as_of=window[-1],
        window_days=len(window),
    )


def observed_daily_rates(panel: SegmentPanel) -> dict[date, dict[str, float | None]]:
    """Per-day rate time series (``None`` when the source state was empty)."""
    out: dict[date, dict[str, float | None]] = {}
    for d in panel.days():
        t = panel.transitions[d]
        totals: Counter[Segment] = Counter()
        for (src, _), n in t.items():
            totals[src] += n
        out[d] = {r.value: (t[e] / totals[e[0]] if totals[e[0]] else None) for r, e in RATE_EDGES.items()}
    return out
