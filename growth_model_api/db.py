from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, Float, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class ActivityEventRow(Base):
    __tablename__ = "activity_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[str] = mapped_column(String(100), index=True)
    product_id: Mapped[str] = mapped_column(String(100), index=True)
    user_id: Mapped[str] = mapped_column(String(256), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    event_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON)


class ApiKeyRow(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    api_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    company_id: Mapped[str] = mapped_column(String(100), index=True)
    product_id: Mapped[str] = mapped_column(String(100), index=True)
    product_version: Mapped[str] = mapped_column(String(64), default="v1")
    is_active: Mapped[int] = mapped_column(Integer, default=1)


class DailySnapshotRow(Base):
    __tablename__ = "daily_state_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[str] = mapped_column(String(100), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    segment: Mapped[str] = mapped_column(String(64), index=True)
    user_count: Mapped[int] = mapped_column(Integer)


class TransitionRateRow(Base):
    __tablename__ = "weekly_transition_rates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[str] = mapped_column(String(100), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    from_segment: Mapped[str] = mapped_column(String(64), index=True)
    to_segment: Mapped[str] = mapped_column(String(64), index=True)
    rate: Mapped[float] = mapped_column(Float)


def create_session_factory(database_url: str):
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
