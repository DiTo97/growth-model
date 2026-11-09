import itertools
from datetime import date, timedelta

import pytest

from growth_model_core import (
    ALLOWED_TRANSITIONS,
    SEGMENTS,
    GrowthModel,
    Rate,
    Rates,
    Segment,
    Windows,
    aggregates,
    build_users,
    classify,
    segment_users,
    simulate,
    synthetic_activity,
)

S = Segment
D0 = date(2026, 1, 1)


def d(n: int) -> date:
    return D0 + timedelta(days=n)


@pytest.mark.parametrize(
    ("since_last", "gap", "expected"),
    [
        (0, None, S.NEW),
        (0, 1, S.CURRENT),
        (0, 7, S.CURRENT),
        (0, 8, S.REACTIVATED),
        (0, 30, S.REACTIVATED),
        (0, 31, S.RESURRECTED),
        (1, None, S.AT_RISK_WAU),
        (6, None, S.AT_RISK_WAU),
        (7, None, S.AT_RISK_MAU),
        (29, None, S.AT_RISK_MAU),
        (30, None, S.DORMANT),
        (None, None, S.DORMANT),
    ],
)
def test_classify_boundaries(since_last, gap, expected):
    assert classify(since_last, gap) is expected


def test_windows_validation():
    with pytest.raises(ValueError):
        Windows(week=30, month=7)


def test_users_do_not_exist_before_first_activity():
    users = build_users([("a", d(5))])
    panel = segment_users(users, d(0), d(6))
    assert sum(panel.counts[d(4)].values()) == 0
    assert panel.counts[d(5)][S.NEW] == 1
    assert panel.counts[d(6)][S.AT_RISK_WAU] == 1


def test_single_user_lifecycle():
    # active day 0, 1, then 10 (gap 9 -> reactivated), then 50 (gap 40 -> resurrected)
    users = build_users([("a", d(0)), ("a", d(1)), ("a", d(10)), ("a", d(50))])
    panel = segment_users(users, d(0), d(52))
    seq = {n: next(s for s, c in panel.counts[d(n)].items() if c) for n in range(53)}
    assert seq[0] is S.NEW
    assert seq[1] is S.CURRENT
    assert seq[2] is S.AT_RISK_WAU
    assert seq[8] is S.AT_RISK_MAU  # 7 days since last active
    assert seq[10] is S.REACTIVATED
    assert seq[11] is S.AT_RISK_WAU
    assert seq[40] is S.DORMANT  # 30 days since day 10
    assert seq[50] is S.RESURRECTED
    assert panel.unexpected_transitions == 0


def test_known_user_with_no_recent_activity_is_dormant_not_missing():
    users = build_users([("a", d(40))], first_seen={"a": d(-200), "b": d(-100)})
    panel = segment_users(users, d(35), d(41))
    assert panel.counts[d(35)][S.DORMANT] == 2
    assert panel.counts[d(40)][S.RESURRECTED] == 1


def test_synthetic_data_only_produces_diagram_transitions():
    model = GrowthModel.from_activity(synthetic_activity(days=90, new_users_per_day=20))
    assert model.panel.unexpected_transitions == 0
    for t in model.panel.transitions.values():
        assert set(t) <= ALLOWED_TRANSITIONS


def test_wau_mau_match_rolling_windows():
    rows = synthetic_activity(days=80, new_users_per_day=15)
    model = GrowthModel.from_activity(rows)
    by_day: dict[date, set[str]] = {}
    for uid, day in rows:
        by_day.setdefault(day, set()).add(uid)
    for day, m in model.metrics().items():
        wau = set().union(*(by_day.get(day - timedelta(days=i), set()) for i in range(7)))
        mau = set().union(*(by_day.get(day - timedelta(days=i), set()) for i in range(30)))
        assert m["dau"] == len(by_day.get(day, set()))
        assert m["wau"] == len(wau)
        assert m["mau"] == len(mau)


def _rates(**kw: float) -> Rates:
    base = {r: 0.0 for r in Rate}
    base.update({Rate(k): v for k, v in kw.items()})
    return Rates(values=base)


def test_rates_validation():
    with pytest.raises(ValueError):
        _rates(iwaurr=0.7, wau_loss=0.5)
    with pytest.raises(ValueError):
        Rates(values={Rate.CURR: 0.5})


def test_simulation_conserves_population_plus_inflow():
    r = _rates(
        nurr=0.5,
        curr=0.8,
        rurr=0.4,
        surr=0.3,
        iwaurr=0.1,
        wau_loss=0.15,
        reactivation=0.05,
        mau_loss=0.04,
        resurrection=0.01,
    )
    r = r.with_overrides(new_users_per_day=10)
    init = {s: 100.0 for s in SEGMENTS}
    traj = simulate(init, r, 50)
    for prev, cur in itertools.pairwise(traj):
        # NEW is replaced each day, everyone else is carried over.
        carried = sum(prev.segments.values())
        assert sum(cur.segments.values()) == pytest.approx(carried + 10)


def test_fitted_model_reproduces_observed_one_step_transitions():
    model = GrowthModel.from_activity(synthetic_activity(days=100, new_users_per_day=30), fit_window_days=1)
    days = model.panel.days()
    prev = {s: float(model.panel.counts[days[-2]][s]) for s in SEGMENTS}
    nxt = simulate(prev, model.rates.with_overrides(new_users_per_day=model.panel.counts[days[-1]][S.NEW]), 1)[-1]
    for s in SEGMENTS:
        assert nxt.segments[s] == pytest.approx(model.panel.counts[days[-1]][s])


def test_overrides_and_levers():
    model = GrowthModel.from_activity(synthetic_activity(days=90, new_users_per_day=25))
    base = model.simulate(180)[-1].metrics["dau"]
    better = model.simulate(180, overrides={"CURR": min(1.0, model.rates[Rate.CURR] + 0.05)})[-1].metrics["dau"]
    assert better > base
    results = model.levers(horizon_days=365)
    assert len(results) == len(Rate) + 1
    assert results == sorted(results, key=lambda r: r.dau_impact, reverse=True)
    impacts = {r.lever: r.dau_impact for r in results}
    assert impacts["curr"] > 0
    assert impacts["wau_loss"] >= 0  # losses are pulled downwards


def test_aggregates():
    assert aggregates({S.NEW: 1, S.CURRENT: 2, S.AT_RISK_WAU: 3, S.AT_RISK_MAU: 4, S.DORMANT: 5}) == {
        "dau": 3,
        "wau": 6,
        "mau": 10,
    }
