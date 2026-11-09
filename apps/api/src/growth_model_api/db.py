"""Persistence. Mirrors infra/sql/schema.sql (keep both in sync)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, Engine, Integer, String, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    prefix: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # "publishable" (ingest-only) | "secret"
    company_id: Mapped[str] = mapped_column(String(100))
    product_id: Mapped[str] = mapped_column(String(100))
    label: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Member(Base):
    """Maps an identity-provider subject (Supabase user id) to a tenant."""

    __tablename__ = "members"

    subject: Mapped[str] = mapped_column(String(100), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    product_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    role: Mapped[str] = mapped_column(String(32), default="analyst")


class TrackedUser(Base):
    __tablename__ = "tracked_users"

    company_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    product_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    first_seen: Mapped[date] = mapped_column(Date)


class ActivityDay(Base):
    """One row per (tenant, user, UTC day). This is all the model needs."""

    __tablename__ = "activity_days"

    company_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    product_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    event_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


class SegmentCount(Base):
    __tablename__ = "segment_counts"

    company_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    product_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    segment: Mapped[str] = mapped_column(String(32), primary_key=True)
    users: Mapped[int] = mapped_column(Integer)


class TransitionCount(Base):
    __tablename__ = "transition_counts"

    company_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    product_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    from_segment: Mapped[str] = mapped_column(String(32), primary_key=True)
    to_segment: Mapped[str] = mapped_column(String(32), primary_key=True)
    users: Mapped[int] = mapped_column(Integer)


class RateFitRow(Base):
    __tablename__ = "rate_fits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[str] = mapped_column(String(100), index=True)
    product_id: Mapped[str] = mapped_column(String(100), index=True)
    as_of: Mapped[date] = mapped_column(Date, index=True)
    window_days: Mapped[int] = mapped_column(Integer)
    rates: Mapped[dict[str, float]] = mapped_column(JSON)
    exposure: Mapped[dict[str, int]] = mapped_column(JSON)
    unexpected_transitions: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


def make_engine(url: str) -> Engine:
    kwargs: dict[str, Any] = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if url in ("sqlite://", "sqlite:///:memory:"):
            from sqlalchemy.pool import StaticPool

            kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _pragma(conn, _rec):  # pragma: no cover - trivial
            conn.execute("PRAGMA journal_mode=WAL")

    return engine


def make_sessionmaker(engine: Engine, create_tables: bool = True) -> sessionmaker:
    if create_tables:
        Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)
