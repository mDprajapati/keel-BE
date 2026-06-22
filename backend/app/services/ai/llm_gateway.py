"""The ONE OpenAI seam (AI timeline: 'only place an openai client may be constructed').

All model access goes through `call_llm` / `stream_llm` / `embed`. Every call logs
a `token_usage` row. The client is built lazily on first use, so importing this
module never requires `OPENAI_API_KEY` or a network connection.

No other module may import `openai` or construct a client.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.core.errors import UpstreamAIError
from app.core.logging import get_logger
from app.services.ai.usage import record_usage

log = get_logger(__name__)

_client: Any = None
_MAX_RETRIES = 3
_TRANSIENT = ("RateLimitError", "APIConnectionError", "APITimeoutError", "InternalServerError")


@dataclass
class LLMResult:
    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


def _get_client() -> Any:
    """Lazily build the singleton AsyncOpenAI client."""
    global _client
    if _client is None:
        if not settings.openai_api_key:
            raise UpstreamAIError("OPENAI_API_KEY is not configured")
        import openai  # lazy: import-safe without the package/key

        _client = openai.AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())
    return _client


def _is_transient(exc: Exception) -> bool:
    return type(exc).__name__ in _TRANSIENT


async def _with_retry(coro_factory, *, what: str):
    last: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            return await coro_factory()
        except Exception as exc:  # noqa: BLE001
            last = exc
            if not _is_transient(exc) or attempt == _MAX_RETRIES:
                break
            await asyncio.sleep(min(2**attempt, 10))
    log.error("openai_call_failed", what=what, error=str(last))
    raise UpstreamAIError(f"AI provider error during {what}") from last


# ---------------------------------------------------------------------------
# Token bucket — limits embedding requests/minute (configurable EMBED_MAX_RPM).
# ---------------------------------------------------------------------------
class TokenBucket:
    def __init__(self, rate_per_minute: int) -> None:
        self.capacity = max(1, rate_per_minute)
        self.tokens = float(self.capacity)
        self.refill_per_sec = self.capacity / 60.0
        self._updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            self.tokens = min(
                self.capacity, self.tokens + (now - self._updated) * self.refill_per_sec
            )
            self._updated = now
            if self.tokens < 1:
                wait = (1 - self.tokens) / self.refill_per_sec
                await asyncio.sleep(wait)
                self.tokens = 0
            else:
                self.tokens -= 1


_embed_bucket: TokenBucket | None = None


def _bucket() -> TokenBucket:
    global _embed_bucket
    if _embed_bucket is None:
        _embed_bucket = TokenBucket(settings.embed_max_rpm)
    return _embed_bucket


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
async def call_llm(
    messages: list[dict[str, str]],
    *,
    workspace_id: str | uuid.UUID,
    operation: str,
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int | None = None,
    response_format: dict | None = None,
    session: Any = None,
    request_id: str | None = None,
) -> LLMResult:
    """Chat completion. Logs token_usage. `operation` ∈ {tagging,ner,chat,context}."""
    use_model = model or settings.chat_model
    client = _get_client()

    async def _do():
        kwargs: dict[str, Any] = {
            "model": use_model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        if response_format:
            kwargs["response_format"] = response_format
        return await client.chat.completions.create(**kwargs)

    resp = await _with_retry(_do, what=f"call_llm:{operation}")
    usage = getattr(resp, "usage", None)
    result = LLMResult(
        content=resp.choices[0].message.content or "",
        model=use_model,
        prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
        completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        total_tokens=getattr(usage, "total_tokens", 0) or 0,
    )
    await record_usage(
        workspace_id=workspace_id,
        operation=operation,
        model=use_model,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        total_tokens=result.total_tokens,
        request_id=request_id,
        session=session,
    )
    return result


async def stream_llm(
    messages: list[dict[str, str]],
    *,
    workspace_id: str | uuid.UUID,
    operation: str = "chat",
    model: str | None = None,
    temperature: float = 0.2,
    request_id: str | None = None,
) -> AsyncIterator[str]:
    """Yield content deltas; logs token_usage once the stream ends."""
    use_model = model or settings.chat_model
    client = _get_client()
    prompt_tokens = completion_tokens = total_tokens = 0
    try:
        stream = await client.chat.completions.create(
            model=use_model,
            messages=messages,
            temperature=temperature,
            stream=True,
            stream_options={"include_usage": True},
        )
        async for chunk in stream:
            if getattr(chunk, "usage", None):
                prompt_tokens = chunk.usage.prompt_tokens or 0
                completion_tokens = chunk.usage.completion_tokens or 0
                total_tokens = chunk.usage.total_tokens or 0
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    except Exception as exc:  # noqa: BLE001
        log.error("stream_llm_failed", error=str(exc))
        raise UpstreamAIError("AI provider error during chat stream") from exc
    finally:
        await record_usage(
            workspace_id=workspace_id,
            operation=operation,
            model=use_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            request_id=request_id,
        )


async def embed(
    texts: list[str],
    *,
    workspace_id: str | uuid.UUID,
    model: str | None = None,
    session: Any = None,
) -> list[list[float]]:
    """Embed texts in batches of `EMBED_BATCH_SIZE`, rate-limited. Logs token_usage per batch."""
    if not texts:
        return []
    use_model = model or settings.embedding_model
    client = _get_client()
    out: list[list[float]] = []
    batch = settings.embed_batch_size

    for start in range(0, len(texts), batch):
        chunk = texts[start : start + batch]
        await _bucket().acquire()

        async def _do(c=chunk):
            return await client.embeddings.create(model=use_model, input=c)

        resp = await _with_retry(_do, what="embed")
        out.extend([d.embedding for d in resp.data])
        usage = getattr(resp, "usage", None)
        await record_usage(
            workspace_id=workspace_id,
            operation="embedding",
            model=use_model,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=0,
            total_tokens=getattr(usage, "total_tokens", 0) or 0,
            session=session,
        )
    return out
