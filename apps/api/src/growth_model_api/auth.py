"""Authentication and tenant scoping.

Three kinds of credentials:

* ``gm_pub_*`` publishable keys — ingest-only, safe to ship in client apps.
* ``gm_sk_*`` secret keys — read, jobs and simulations for one tenant (servers, CLI, agents).
* Supabase JWTs — web console users, mapped to tenants via the ``members`` table.

The tenant is *always* derived from the credential, never from request params.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from functools import lru_cache

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import ApiKey, Member
from .settings import Settings

PUBLISHABLE, SECRET = "publishable", "secret"
_PREFIX = {PUBLISHABLE: "gm_pub_", SECRET: "gm_sk_"}


@dataclass(frozen=True)
class Principal:
    company_id: str
    product_id: str
    kind: str  # publishable | secret | member

    @property
    def can_read(self) -> bool:
        return self.kind in (SECRET, "member")


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_key(kind: str) -> str:
    return _PREFIX[kind] + secrets.token_urlsafe(24)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request):
    db: Session = request.app.state.sessionmaker()
    try:
        yield db
    finally:
        db.close()


@lru_cache(maxsize=4)
def _jwks_client(url: str):
    import jwt

    return jwt.PyJWKClient(f"{url.rstrip('/')}/auth/v1/.well-known/jwks.json")


def _verify_supabase_jwt(token: str, settings: Settings) -> str | None:
    import jwt

    try:
        if settings.supabase_url:
            key = _jwks_client(settings.supabase_url).get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=["ES256", "RS256"], audience="authenticated")
        elif settings.supabase_jwt_secret:
            claims = jwt.decode(token, settings.supabase_jwt_secret, algorithms=["HS256"], audience="authenticated")
        else:
            return None
    except jwt.PyJWTError:
        return None
    return claims.get("sub")


def _resolve(
    authorization: str,
    x_api_key: str,
    x_tenant: str,
    db: Session,
    settings: Settings,
) -> Principal:
    raw = x_api_key or (authorization[7:] if authorization.lower().startswith("bearer ") else "")
    if not raw:
        raise HTTPException(401, "missing credentials")
    if raw.startswith(("gm_pub_", "gm_sk_")):
        row = db.scalars(select(ApiKey).where(ApiKey.key_hash == hash_key(raw), ApiKey.revoked_at.is_(None))).first()
        if row is None:
            raise HTTPException(401, "invalid api key")
        return Principal(row.company_id, row.product_id, row.kind)

    subject = _verify_supabase_jwt(raw, settings)
    if subject is None:
        raise HTTPException(401, "invalid token")
    memberships = db.scalars(select(Member).where(Member.subject == subject)).all()
    if x_tenant:
        memberships = [m for m in memberships if f"{m.company_id}/{m.product_id}" == x_tenant]
    if len(memberships) != 1:
        raise HTTPException(403, "no tenant membership (or ambiguous: send X-Tenant: company/product)")
    m = memberships[0]
    return Principal(m.company_id, m.product_id, "member")


def ingest_principal(
    authorization: str = Header(default=""),
    x_api_key: str = Header(default=""),
    x_tenant: str = Header(default=""),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Principal:
    return _resolve(authorization, x_api_key, x_tenant, db, settings)


def read_principal(principal: Principal = Depends(ingest_principal)) -> Principal:
    if not principal.can_read:
        raise HTTPException(403, "publishable keys can only ingest events")
    return principal


def require_admin(authorization: str = Header(default=""), settings: Settings = Depends(get_settings)) -> None:
    if not settings.admin_token:
        raise HTTPException(404, "admin API disabled (set GROWTH_MODEL_ADMIN_TOKEN)")
    token = authorization[7:] if authorization.lower().startswith("bearer ") else ""
    if not hmac.compare_digest(token.encode(), settings.admin_token.encode()):
        raise HTTPException(401, "invalid admin token")
