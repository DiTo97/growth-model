from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class Segment(StrEnum):
    NU = "new_users"
    CU = "current_users"
    RU = "reactivated_users"
    SU = "resurrected_users"
    AW = "at_risk_wau"
    AM = "at_risk_mau"
    DU = "dormant_users"


@dataclass(frozen=True)
class ActivityEvent:
    company_id: str
    user_id: str
    occurred_at: datetime


@dataclass(frozen=True)
class DailyUserState:
    company_id: str
    user_id: str
    day: date
    segment: Segment
