"""Mandatory token-usage logging (AI timeline).

`record_usage` is called by `llm_gateway` after EVERY LLM/embedding call. It is
best-effort at the persistence layer (a transient DB error is logged, never
raised into the caller's request) but there is no code path that skips it.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session_factory
from app.core.logging import get_logger
from app.models.ingestion import TokenUsage

log = get_logger(__name__)

# USD per 1K tokens. Update as pricing changes (single source of truth for cost).
PRICES: dict[str, dict[str, float]] = {
    "text-embedding-3-small": {"input": 0.00002, "output": 0.0},
    "text-embedding-3-large": {"input": 0.00013, "output": 0.0},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4o": {"input": 0.0025, "output": 0.01},
}


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    price = PRICES.get(model, {"input": 0.0, "output": 0.0})
    return round(
        (prompt_tokens / 1000) * price["input"] + (completion_tokens / 1000) * price["output"], 6
    )


def _coerce_ws(workspace_id: str | uuid.UUID) -> uuid.UUID:
    return workspace_id if isinstance(workspace_id, uuid.UUID) else uuid.UUID(str(workspace_id))


async def record_usage(
    *,
    workspace_id: str | uuid.UUID,
    operation: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    request_id: str | None = None,
    session: AsyncSession | None = None,
) -> None:
    """Persist one `token_usage` row. Reuses `session` if given, else opens one."""
    row = TokenUsage(
        workspace_id=_coerce_ws(workspace_id),
        operation=operation,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost_usd=estimate_cost(model, prompt_tokens, completion_tokens),
        request_id=request_id,
    )
    try:
        if session is not None:
            session.add(row)
            await session.flush()
        else:
            factory = get_session_factory()
            async with factory() as s:
                s.add(row)
                await s.commit()
    except Exception as exc:  # noqa: BLE001 — usage logging must not break the call
        log.warning("token_usage_write_failed", operation=operation, model=model, error=str(exc))
