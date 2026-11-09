"""User-state segmentation.

Every known user is assigned exactly one of seven mutually exclusive states per
day. Definitions use rolling windows anchored on "days since last active":

* ``d = 0`` (active today): the state depends on the gap ``g`` to the previous
  active day — no previous day → NEW, ``g <= week`` → CURRENT,
  ``g <= month`` → REACTIVATED, otherwise RESURRECTED.
* ``1 <= d < week`` → AT_RISK_WAU, ``week <= d < month`` → AT_RISK_MAU,
  ``d >= month`` → DORMANT.

With ``week=7, month=30`` this makes WAU/MAU equal to the conventional 7-day and
30-day rolling-window counts, and it guarantees the only transitions that can
occur are the arrows of the Duolingo growth-model diagram (see docs/model.md).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import StrEnum


class Segment(StrEnum):
    NEW = "new"
    CURRENT = "current"
    REACTIVATED = "reactivated"
    RESURRECTED = "resurrected"
    AT_RISK_WAU = "at_risk_wau"
    AT_RISK_MAU = "at_risk_mau"
    DORMANT = "dormant"


SEGMENTS: tuple[Segment, ...] = tuple(Segment)
ACTIVE_SEGMENTS = frozenset({Segment.NEW, Segment.CURRENT, Segment.REACTIVATED, Segment.RESURRECTED})

# The arrows of the growth-model diagram. Anything else indicates a bug or bad data.
ALLOWED_TRANSITIONS: frozenset[tuple[Segment, Segment]] = frozenset(
    {
        *((s, Segment.CURRENT) for s in ACTIVE_SEGMENTS),
        *((s, Segment.AT_RISK_WAU) for s in ACTIVE_SEGMENTS),
        (Segment.AT_RISK_WAU, Segment.CURRENT),
        (Segment.AT_RISK_WAU, Segment.AT_RISK_WAU),
        (Segment.AT_RISK_WAU, Segment.AT_RISK_MAU),
        (Segment.AT_RISK_MAU, Segment.REACTIVATED),
        (Segment.AT_RISK_MAU, Segment.AT_RISK_MAU),
        (Segment.AT_RISK_MAU, Segment.DORMANT),
        (Segment.DORMANT, Segment.RESURRECTED),
        (Segment.DORMANT, Segment.DORMANT),
    }
)


@dataclass(frozen=True, slots=True)
class Windows:
    """Window lengths in days. ``week=7, month=30`` is the Duolingo convention."""

    week: int = 7
    month: int = 30

    def __post_init__(self) -> None:
        if not 1 < self.week < self.month:
            raise ValueError("expected 1 < week < month")


def classify(days_since_last: int | None, gap_to_previous: int | None, w: Windows = Windows()) -> Segment:
    """Classify one user on one day.

    ``days_since_last`` is 0 when active today. ``gap_to_previous`` is the gap
    between today and the previous active day (only meaningful when active
    today; ``None`` means there is no previous active day, i.e. a new user).
    ``days_since_last=None`` means "known user, last activity is older than any
    loaded history" and is treated as dormant.
    """
    if days_since_last is None:
        return Segment.DORMANT
    if days_since_last == 0:
        if gap_to_previous is None:
            return Segment.NEW
        if gap_to_previous <= w.week:
            return Segment.CURRENT
        if gap_to_previous <= w.month:
            return Segment.REACTIVATED
        return Segment.RESURRECTED
    if days_since_last < w.week:
        return Segment.AT_RISK_WAU
    if days_since_last < w.month:
        return Segment.AT_RISK_MAU
    return Segment.DORMANT


@dataclass(frozen=True, slots=True)
class UserActivity:
    """Activity history for one user.

    ``days`` must contain every active day from ``start - windows.month - 1``
    onwards (older days are allowed). ``first_seen`` is the first day the user
    was ever active; when it predates the earliest loaded day the user is
    treated as having a long-past last activity (a "known" user), not as new.
    """

    first_seen: date
    days: tuple[date, ...]


@dataclass(slots=True)
class SegmentPanel:
    """Daily aggregate output of :func:`segment_users`."""

    start: date
    end: date
    counts: dict[date, Counter[Segment]] = field(default_factory=dict)
    # transitions[t][(from, to)] = number of users in `from` on t-1 and `to` on t
    transitions: dict[date, Counter[tuple[Segment, Segment]]] = field(default_factory=dict)
    unexpected_transitions: int = 0

    def days(self) -> list[date]:
        return sorted(self.counts)

    def latest(self) -> dict[Segment, int]:
        last = max(self.counts)
        return {s: self.counts[last][s] for s in SEGMENTS}


def daterange(start: date, end: date) -> Iterable[date]:
    for i in range((end - start).days + 1):
        yield start + timedelta(days=i)


def _user_states(user: UserActivity, start: date, end: date, w: Windows) -> Iterable[tuple[date, Segment]]:
    """Yield (day, segment) for ``start - 1 .. end`` (only days the user exists)."""
    active = sorted(set(user.days))
    active_set = set(active)

    begin = max(user.first_seen, start - timedelta(days=1))
    # Last active day strictly before `begin`.
    last: date | None = None
    for d in active:
        if d < begin:
            last = d
        else:
            break

    for day in daterange(begin, end):
        if day in active_set:
            if last is not None:
                gap: int | None = (day - last).days
            elif day == user.first_seen:
                gap = None  # first activity ever
            else:
                gap = w.month + 1  # known user whose last activity predates loaded history
            yield day, classify(0, gap, w)
            last = day
        else:
            yield day, classify(None if last is None else (day - last).days, None, w)


def segment_users(
    users: Mapping[str, UserActivity],
    start: date,
    end: date,
    windows: Windows = Windows(),
) -> SegmentPanel:
    """Compute daily segment counts and day-over-day transition counts.

    Users only enter the population on their ``first_seen`` day. Transitions
    into ``start`` are included (they need the state on ``start - 1``).
    """
    if end < start:
        raise ValueError("end must be >= start")
    panel = SegmentPanel(start=start, end=end)
    for d in daterange(start, end):
        panel.counts[d] = Counter({s: 0 for s in SEGMENTS})
        panel.transitions[d] = Counter()

    for user in users.values():
        if user.first_seen > end:
            continue
        prev: Segment | None = None
        for day, seg in _user_states(user, start, end, windows):
            if day >= start:
                panel.counts[day][seg] += 1
                if prev is not None:
                    panel.transitions[day][(prev, seg)] += 1
                    if (prev, seg) not in ALLOWED_TRANSITIONS:
                        panel.unexpected_transitions += 1
            prev = seg
    return panel


def build_users(
    rows: Iterable[tuple[str, date]], first_seen: Mapping[str, date] | None = None
) -> dict[str, UserActivity]:
    """Group ``(user_id, day)`` rows into :class:`UserActivity` records.

    ``first_seen`` lets callers supply the true first-activity day for users
    whose early history was not loaded (e.g. from a ``users`` table).
    """
    by_user: dict[str, set[date]] = {}
    for user_id, day in rows:
        by_user.setdefault(user_id, set()).add(day)
    first_seen = dict(first_seen or {})
    out: dict[str, UserActivity] = {}
    for uid in by_user.keys() | first_seen.keys():
        days = tuple(sorted(by_user.get(uid, ())))
        fs = first_seen.get(uid) or days[0]
        if days and days[0] < fs:
            fs = days[0]
        out[uid] = UserActivity(first_seen=fs, days=days)
    return out


def aggregates(counts: Mapping[Segment, float]) -> dict[str, float]:
    """DAU/WAU/MAU from segment counts (appendix equations of the blog post)."""
    dau = sum(counts.get(s, 0) for s in ACTIVE_SEGMENTS)
    wau = dau + counts.get(Segment.AT_RISK_WAU, 0)
    mau = wau + counts.get(Segment.AT_RISK_MAU, 0)
    return {"dau": dau, "wau": wau, "mau": mau}
