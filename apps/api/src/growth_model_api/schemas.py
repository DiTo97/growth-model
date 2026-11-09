from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from growth_model_core import DEFAULT_LEVERS, parse_rate


class Event(BaseModel):
    user_id: str = Field(min_length=1, max_length=256)
    timestamp: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EventBatch(BaseModel):
    events: list[Event] = Field(min_length=1, max_length=1000)


class SegmentsJob(BaseModel):
    start: date | None = None
    end: date | None = None


class FitJob(BaseModel):
    as_of: date | None = None
    window_days: int | None = Field(default=None, ge=1, le=365)


class SimulationRequest(BaseModel):
    horizon_days: int = Field(default=365, ge=1, le=3650)
    overrides: dict[str, float] = Field(default_factory=dict, description="e.g. {'curr': 0.85}")
    new_users_per_day: float | None = Field(default=None, ge=0)
    include_segments: bool = False

    @field_validator("overrides")
    @classmethod
    def _known(cls, v: dict[str, float]) -> dict[str, float]:
        return {parse_rate(k).value: x for k, x in v.items()}


class LeverRequest(BaseModel):
    horizon_days: int = Field(default=3 * 365, ge=1, le=3650)
    monthly_growth: float = Field(default=0.02, gt=-1, le=1)
    levers: list[str] = Field(default_factory=lambda: list(DEFAULT_LEVERS))
    ceiling: float = Field(default=0.95, gt=0, le=1, description="Max value a pulled rate may reach")


class KeyCreate(BaseModel):
    company_id: str = Field(min_length=1, max_length=100)
    product_id: str = Field(min_length=1, max_length=100)
    kind: Literal["publishable", "secret"] = "publishable"
    label: str = ""


class MemberCreate(BaseModel):
    subject: str = Field(min_length=1, description="Supabase auth user id (JWT `sub`)")
    company_id: str
    product_id: str
    role: str = "analyst"
