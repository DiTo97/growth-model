from __future__ import annotations

import os
from dataclasses import dataclass, field


def _list(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///./growth_model.db"
    # Admin endpoints are disabled unless this is set. There is no default admin secret.
    admin_token: str | None = None
    # Supabase auth for the web console: either a JWKS project URL (asymmetric keys) or a legacy HS256 secret.
    supabase_url: str | None = None
    supabase_jwt_secret: str | None = None
    cors_origins: list[str] = field(default_factory=list)
    week_days: int = 7
    month_days: int = 30
    fit_window_days: int = 28
    max_batch_events: int = 1000

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ
        return cls(
            database_url=env.get("DATABASE_URL", cls.database_url),
            admin_token=env.get("GROWTH_MODEL_ADMIN_TOKEN") or None,
            supabase_url=env.get("SUPABASE_URL") or None,
            supabase_jwt_secret=env.get("SUPABASE_JWT_SECRET") or None,
            cors_origins=_list(env.get("CORS_ORIGINS", "")),
            week_days=int(env.get("GROWTH_MODEL_WEEK_DAYS", cls.week_days)),
            month_days=int(env.get("GROWTH_MODEL_MONTH_DAYS", cls.month_days)),
            fit_window_days=int(env.get("GROWTH_MODEL_FIT_WINDOW_DAYS", cls.fit_window_days)),
        )
