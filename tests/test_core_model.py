from datetime import datetime, timezone, date

from growth_model_core.engine import ALL_SEGMENTS, aggregate_daily_states, compute_daily_states, simulate
from growth_model_core.models import ActivityEvent, Segment


def test_segmenting_and_aggregating():
    events = [
        ActivityEvent(company_id="c1", user_id="u1", occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc)),
        ActivityEvent(company_id="c1", user_id="u1", occurred_at=datetime(2026, 1, 3, tzinfo=timezone.utc)),
    ]
    states = compute_daily_states(events, date(2026, 1, 1), date(2026, 1, 4))
    out = aggregate_daily_states(states)

    assert out[("c1", date(2026, 1, 1))][Segment.NU] == 1
    assert out[("c1", date(2026, 1, 2))][Segment.AW] == 1
    assert out[("c1", date(2026, 1, 3))][Segment.CU] == 1


def test_simulate_preserves_population_when_no_transitions():
    initial = {segment: 0.0 for segment in ALL_SEGMENTS}
    initial[Segment.CU] = 100.0
    history = simulate(initial, {}, 5)
    assert all(day[Segment.CU.value] == 100.0 for day in history)
