"""FastAPI dependencies: DB session + principal resolution.

- `get_current_user` — app-only routes: requires a valid user JWT.
- `require_admin` — admin-gated routes.
- `get_principal` — dual-auth routes (v3 §13): tries the JWT first, then a
  workspace API key (rate-limited). Resolves a `Principal {workspace_id, user_id?,
  api_key_id?, scope, role}`. `workspace_id` always comes from the principal,
  never from request input.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Depends, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rate_limit
from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.security import API_KEY_PREFIX, decode_access_token, sha256_hex
from app.database import get_db
from app.models.api_key import ApiKey
from app.models.base import ApiKeyScope, Role
from app.models.user import User

__all__ = [
    "get_db",
    "get_current_user",
    "require_admin",
    "get_principal",
    "Principal",
    "ensure_write_scope",
]


@dataclass
class Principal:
    workspace_id: uuid.UUID
    user_id: uuid.UUID | None = None
    role: str | None = None
    api_key_id: uuid.UUID | None = None
    scope: str | None = None

    @property
    def is_admin(self) -> bool:
        return self.role == Role.admin.value

    @property
    def can_write(self) -> bool:
        # JWT users can write; API keys need read_write scope.
        return self.api_key_id is None or self.scope == ApiKeyScope.read_write.value

    def require_user(self) -> uuid.UUID:
        """Narrow `user_id` for JWT-only routes (get_current_user always sets it)."""
        if self.user_id is None:
            raise UnauthorizedError("User authentication required")
        return self.user_id


def _bearer(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise UnauthorizedError("Missing bearer token")
    return auth.split(" ", 1)[1].strip()


async def _principal_from_jwt(token: str, db: AsyncSession) -> Principal:
    claims = decode_access_token(token)
    user_id = uuid.UUID(claims["sub"])
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive")
    return Principal(
        workspace_id=uuid.UUID(claims["workspace_id"]),
        user_id=user_id,
        role=claims.get("role"),
    )


async def _principal_from_api_key(token: str, db: AsyncSession) -> Principal:
    row = (
        await db.execute(select(ApiKey).where(ApiKey.key_hash == sha256_hex(token)))
    ).scalar_one_or_none()
    if row is None or row.revoked:
        raise UnauthorizedError("Invalid API key")
    await rate_limit.enforce(row.id, row.rate_limit_per_minute)
    # Track usage (contract-exposed `last_used_at` / `request_count`). Atomic increment
    # avoids lost updates under concurrent calls with the same key.
    await db.execute(
        update(ApiKey)
        .where(ApiKey.id == row.id)
        .values(last_used_at=datetime.now(UTC), request_count=ApiKey.request_count + 1)
    )
    await db.commit()
    return Principal(workspace_id=row.workspace_id, api_key_id=row.id, scope=row.scope)


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> Principal:
    """App-only: a valid user JWT is required (API keys rejected here)."""
    return await _principal_from_jwt(_bearer(request), db)


async def require_admin(principal: Principal = Depends(get_current_user)) -> Principal:
    if not principal.is_admin:
        raise ForbiddenError("Admin role required")
    return principal


async def get_principal(request: Request, db: AsyncSession = Depends(get_db)) -> Principal:
    """Dual auth (v3 §13): JWT first, else workspace API key."""
    token = _bearer(request)
    if token.startswith(API_KEY_PREFIX):
        return await _principal_from_api_key(token, db)
    try:
        return await _principal_from_jwt(token, db)
    except UnauthorizedError:
        # Fall back to API-key resolution for non-JWT tokens.
        return await _principal_from_api_key(token, db)


def ensure_write_scope(principal: Principal) -> None:
    """Ingestion requires write access (JWT users OK; API keys need read_write)."""
    if not principal.can_write:
        raise ForbiddenError("read_write scope required for ingestion")
