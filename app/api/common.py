"""Shared router helpers."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal
from app.models.api_key import ApiCallLog


async def log_api_call(db: AsyncSession, principal: Principal, endpoint: str) -> None:
    """Record a REST call for dashboard monthly counts (API-key principals only).

    Adds the row to the request session and lets the `get_db` dependency own the commit,
    so logging never commits the caller's unit of work as a side effect."""
    if principal.api_key_id is not None:
        db.add(
            ApiCallLog(
                workspace_id=principal.workspace_id,
                endpoint=endpoint,
                api_key_id=principal.api_key_id,
            )
        )
