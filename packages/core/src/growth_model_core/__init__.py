"""growth-model-core: a dependency-free implementation of Duolingo's growth model.

Typical use::

    from growth_model_core import GrowthModel, read_csv

    model = GrowthModel.from_activity(read_csv("activity.csv"))
    model.rates.to_dict()                                  # fitted CURR, NURR, ...
    model.simulate(365, overrides={"curr": 0.85})[-1].metrics
    [r.to_dict() for r in model.levers()]                  # which lever moves DAU most
"""

from .levers import DEFAULT_LEVERS, NEW_USERS, LeverResult, lever_analysis
from .pipeline import GrowthModel
from .rates import RATE_EDGES, Rate, RateFit, Rates, estimate_rates, fit_panel, observed_daily_rates, parse_rate
from .segments import (
    ACTIVE_SEGMENTS,
    ALLOWED_TRANSITIONS,
    SEGMENTS,
    Segment,
    SegmentPanel,
    UserActivity,
    Windows,
    aggregates,
    build_users,
    classify,
    segment_users,
)
from .simulation import SimulationStep, simulate, step
from .sources import read_csv, read_posthog, synthetic_activity, write_csv

__all__ = [
    "ACTIVE_SEGMENTS",
    "ALLOWED_TRANSITIONS",
    "DEFAULT_LEVERS",
    "NEW_USERS",
    "RATE_EDGES",
    "SEGMENTS",
    "GrowthModel",
    "LeverResult",
    "Rate",
    "RateFit",
    "Rates",
    "Segment",
    "SegmentPanel",
    "SimulationStep",
    "UserActivity",
    "Windows",
    "aggregates",
    "build_users",
    "classify",
    "estimate_rates",
    "fit_panel",
    "lever_analysis",
    "observed_daily_rates",
    "parse_rate",
    "read_csv",
    "read_posthog",
    "segment_users",
    "simulate",
    "step",
    "synthetic_activity",
    "write_csv",
]
