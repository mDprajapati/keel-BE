"""Sliding-window rate limiter for API keys (v3 §13.3): 100/min → 429 + Retry-After.

Redis-backed sorted set per key. Fails **open** on a Redis error (availability >
strictness for a transient infra blip) — logged, never silently strict. Lazy
client (import-safe without Redis).
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from app.core.config import settings
from app.core.errors import RateLimitError
from app.core.logging import get_logger

log = get_logger(__name__)

_redis: Any = None
_WINDOW_SEC = 60


def _get_redis() -> Any:
    global _redis
    if _redis is None:
        import redis.asyncio as aioredis  # lazy

        _redis = aioredis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    return _redis


async def enforce(api_key_id: str | uuid.UUID, limit_per_minute: int) -> None:
    """Raise RateLimitError if the key exceeded its per-minute limit."""
    limit = max(1, limit_per_minute)
    now = time.time()
    key = f"ratelimit:{api_key_id}"
    member = f"{now}:{uuid.uuid4().hex[:8]}"
    try:
        r = _get_redis()
        async with r.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(key, 0, now - _WINDOW_SEC)
            pipe.zadd(key, {member: now})
            pipe.zcard(key)
            pipe.expire(key, _WINDOW_SEC)
            _, _, count, _ = await pipe.execute()
        if count > limit:
            # A rejected request must not consume a slot in the window.
            await r.zrem(key, member)
            raise RateLimitError("Rate limit exceeded", retry_after=_WINDOW_SEC)
    except RateLimitError:
        raise
    except Exception as exc:  # noqa: BLE001 — fail open on infra error
        log.warning("rate_limit_unavailable", error=str(exc))
