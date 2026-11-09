"""High-level, one-call API: activity rows in, fitted model out."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta

from .levers import DEFAULT_CEILING, DEFAULT_LEVERS, LeverResult, lever_analysis
from .rates import Rate, RateFit, Rates, fit_panel, observed_daily_rates
from .segments import Segment, SegmentPanel, Windows, aggregates, build_users, segment_users
from .simulation import SimulationStep, simulate


@dataclass(slots=True)
class GrowthModel:
    panel: SegmentPanel
    fit: RateFit
    windows: Windows

    @classmethod
    def from_activity(
        cls,
        rows: Iterable[tuple[str, date]],
        *,
        start: date | None = None,
        end: date | None = None,
        fit_window_days: int = 28,
        windows: Windows = Windows(),
        first_seen: Mapping[str, date] | None = None,
    ) -> GrowthModel:
        """Segment ``rows`` and fit rates on the trailing ``fit_window_days``.

        By default the panel starts once a full month of history exists, so
        early days are not distorted by the lack of lookback.
        """
        rows = list(rows)
        if not rows:
            raise ValueError("no activity rows")
        users = build_users(rows, first_seen)
        lo = min(d for _, d in rows)
        hi = max(d for _, d in rows)
        end = end or hi
        start = start or min(end, lo + timedelta(days=windows.month + 1))
        panel = segment_users(users, start, end, windows)
        return cls(panel=panel, fit=fit_panel(panel, fit_window_days), windows=windows)

    @property
    def rates(self) -> Rates:
        return self.fit.rates

    def latest_state(self) -> dict[Segment, int]:
        return self.panel.latest()

    def metrics(self) -> dict[date, dict[str, float]]:
        return {d: aggregates(self.panel.counts[d]) for d in self.panel.days()}

    def daily_rates(self) -> dict[date, dict[str, float | None]]:
        return observed_daily_rates(self.panel)

    def simulate(
        self,
        horizon_days: int,
        overrides: Mapping[Rate | str, float] | None = None,
        new_users_per_day: float | None = None,
    ) -> list[SimulationStep]:
        return simulate(self.latest_state(), self.rates.with_overrides(overrides, new_users_per_day), horizon_days)

    def levers(
        self,
        horizon_days: int = 3 * 365,
        monthly_growth: float = 0.02,
        levers: Iterable[str] = DEFAULT_LEVERS,
        ceiling: float = DEFAULT_CEILING,
    ) -> list[LeverResult]:
        return lever_analysis(
            self.latest_state(),
            self.rates,
            horizon_days=horizon_days,
            monthly_growth=monthly_growth,
            levers=levers,
            ceiling=ceiling,
        )
