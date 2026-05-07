from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class ActivityMetadata(BaseModel):
    platform: str = Field(min_length=1)
    app_version: str = Field(min_length=1)
    locale: str | None = None
    product_version: str | None = None


class ActivityIn(BaseModel):
    company_id: str = Field(min_length=1)
    product_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    occurred_at: datetime
    metadata: ActivityMetadata


class SimulationRequest(BaseModel):
    company_id: str
    horizon_days: int = Field(ge=1, le=365)
    overrides: dict[str, float] = Field(default_factory=dict)


class ComputationRequest(BaseModel):
    company_id: str
    start_date: date
    end_date: date


class ApiKeyCreate(BaseModel):
    api_key: str = Field(min_length=8)
    company_id: str = Field(min_length=1)
    product_id: str = Field(min_length=1)
    product_version: str = "v1"
