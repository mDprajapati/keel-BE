"""API key lifecycle (v3 §13.4). Only the hash + prefix persist; secret shown once."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.security import generate_api_key
from app.models.api_key import ApiKey
from app.models.base import ApiKeyScope
from app.schemas.apikey import ApiKeyOut, ApiKeyWithSecret


def _to_out(k: ApiKey) -> ApiKeyOut:
    return ApiKeyOut(
        id=k.id,
        name=k.name,
        scope=ApiKeyScope(k.scope),
        created_at=k.created_at,
        last_used_at=k.last_used_at,
        request_count=k.request_count,
        rate_limit_per_minute=k.rate_limit_per_minute,
    )


async def list_keys(db: AsyncSession, *, workspace_id: uuid.UUID) -> list[ApiKeyOut]:
    rows = (
        (
            await db.execute(
                select(ApiKey)
                .where(ApiKey.workspace_id == workspace_id, ApiKey.revoked.is_(False))
                .order_by(ApiKey.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_to_out(k) for k in rows]


async def create_key(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    name: str,
    scope: ApiKeyScope,
    created_by: uuid.UUID | None,
    default_rate_limit: int = 100,
) -> ApiKeyWithSecret:
    raw, prefix, key_hash = generate_api_key()
    key = ApiKey(
        workspace_id=workspace_id,
        name=name,
        key_prefix=prefix,
        key_hash=key_hash,
        scope=scope.value,
        rate_limit_per_minute=default_rate_limit,
        created_by_id=created_by,
    )
    db.add(key)
    await db.commit()
    out = _to_out(key)
    return ApiKeyWithSecret(**out.model_dump(), secret=raw)


async def revoke_key(db: AsyncSession, *, workspace_id: uuid.UUID, key_id: uuid.UUID) -> None:
    key = await db.get(ApiKey, key_id)
    if key is None or key.workspace_id != workspace_id:
        raise NotFoundError("API key not found")
    key.revoked = True
    await db.commit()
