from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Iterable

from .models import ActivityEvent, DailyUserState, Segment

ALL_SEGMENTS = [
    Segment.NU,
    Segment.CU,
    Segment.RU,
    Segment.SU,
    Segment.AW,
    Segment.AM,
    Segment.DU,
]


def daterange(start: date, end: date):
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def _classify_day(active_dates: list[date], today: date) -> Segment:
    if not active_dates:
        return Segment.DU

    is_active_today = today in active_dates
    prior_dates = [d for d in active_dates if d < today]
    last_seen = max((d for d in active_dates if d <= today), default=None)

    if last_seen is None:
        return Segment.DU

    if is_active_today:
        if not prior_dates:
            return Segment.NU
        prior_last = max(prior_dates)
        gap = (today - prior_last).days
        if gap <= 7:
            return Segment.CU
        if gap <= 30:
            return Segment.RU
        return Segment.SU

    gap = (today - last_seen).days
    if gap <= 7:
        return Segment.AW
    if gap <= 30:
        return Segment.AM
    return Segment.DU


def compute_daily_states(events: Iterable[ActivityEvent], start: date, end: date) -> list[DailyUserState]:
    by_company_user: dict[tuple[str, str], list[date]] = defaultdict(list)
    for event in events:
        by_company_user[(event.company_id, event.user_id)].append(event.occurred_at.date())

    states: list[DailyUserState] = []
    for (company_id, user_id), dates in by_company_user.items():
        unique_dates = sorted(set(dates))
        for day in daterange(start, end):
            states.append(
                DailyUserState(
                    company_id=company_id,
                    user_id=user_id,
                    day=day,
                    segment=_classify_day(unique_dates, day),
                )
            )
    return states


def aggregate_daily_states(states: Iterable[DailyUserState]) -> dict[tuple[str, date], dict[Segment, int]]:
    out: dict[tuple[str, date], dict[Segment, int]] = defaultdict(lambda: defaultdict(int))
    for state in states:
        out[(state.company_id, state.day)][state.segment] += 1
    for key in list(out.keys()):
        for segment in ALL_SEGMENTS:
            out[key].setdefault(segment, 0)
    return out


def compute_transition_rates(states: Iterable[DailyUserState]) -> dict[tuple[str, date], dict[tuple[Segment, Segment], float]]:
    grouped: dict[tuple[str, str], list[DailyUserState]] = defaultdict(list)
    for s in states:
        grouped[(s.company_id, s.user_id)].append(s)

    counts: dict[tuple[str, date], dict[tuple[Segment, Segment], int]] = defaultdict(lambda: defaultdict(int))
    totals: dict[tuple[str, date], dict[Segment, int]] = defaultdict(lambda: defaultdict(int))

    for (company_id, _user_id), user_states in grouped.items():
        user_states.sort(key=lambda x: x.day)
        for i in range(1, len(user_states)):
            prev_s = user_states[i - 1]
            cur_s = user_states[i]
            key = (company_id, cur_s.day)
            counts[key][(prev_s.segment, cur_s.segment)] += 1
            totals[key][prev_s.segment] += 1

    rates: dict[tuple[str, date], dict[tuple[Segment, Segment], float]] = defaultdict(dict)
    for key, transitions in counts.items():
        for transition, n in transitions.items():
            from_segment = transition[0]
            denom = totals[key][from_segment]
            if denom:
                rates[key][transition] = n / denom
    return rates


def compute_aggregates(state_counts: dict[Segment, int]) -> dict[str, int]:
    dau = state_counts[Segment.NU] + state_counts[Segment.CU] + state_counts[Segment.RU] + state_counts[Segment.SU]
    wau = dau + state_counts[Segment.AW]
    mau = wau + state_counts[Segment.AM]
    return {"dau": dau, "wau": wau, "mau": mau}


def simulate(
    initial_state: dict[Segment, float],
    transition_matrix: dict[tuple[Segment, Segment], float],
    days: int,
) -> list[dict[str, float]]:
    history: list[dict[str, float]] = []
    current = {segment: float(initial_state.get(segment, 0.0)) for segment in ALL_SEGMENTS}

    for _ in range(days):
        next_state = {segment: 0.0 for segment in ALL_SEGMENTS}
        for from_segment in ALL_SEGMENTS:
            row_sum = sum(
                transition_matrix.get((from_segment, to_segment), 0.0) for to_segment in ALL_SEGMENTS
            )
            stay_probability = max(0.0, 1.0 - row_sum)
            next_state[from_segment] += current[from_segment] * stay_probability
            for to_segment in ALL_SEGMENTS:
                p = transition_matrix.get((from_segment, to_segment), 0.0)
                if p > 0:
                    next_state[to_segment] += current[from_segment] * p
        current = next_state
        aggregates = compute_aggregates({k: int(v) for k, v in current.items()})
        history.append(
            {
                "dau": float(aggregates["dau"]),
                "wau": float(aggregates["wau"]),
                "mau": float(aggregates["mau"]),
                **{segment.value: current[segment] for segment in ALL_SEGMENTS},
            }
        )
    return history
