"""OpenAI implementation of LLMProvider — the ONLY module that imports ``openai``.

The client is built lazily on first use, so importing this module never requires
``OPENAI_API_KEY`` or a network connection. ``SecretStr`` is unwrapped only here.
Retry, rate limiting, and token-usage logging are the gateway's responsibility.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.core.config import settings
from app.core.errors import UpstreamAIError
from app.services.providers.base import (
    ChatResult,
    EmbeddingResult,
    StreamEvent,
    StreamUsage,
)

_client: Any = None


def _get_client() -> Any:
    """Lazily build the singleton AsyncOpenAI client."""
    global _client
    if _client is None:
        if not settings.openai_api_key:
            raise UpstreamAIError("OPENAI_API_KEY is not configured")
        import openai  # lazy: import-safe without the package/key

        _client = openai.AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())
    return _client


def reset_client() -> None:
    """Drop the cached client (used by tests)."""
    global _client
    _client = None


class OpenAIProvider:
    """OpenAI Chat Completions + Embeddings backend."""

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int | None = None,
        response_format: dict | None = None,
    ) -> ChatResult:
        client = _get_client()
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        if response_format:
            kwargs["response_format"] = response_format
        resp = await client.chat.completions.create(**kwargs)
        usage = getattr(resp, "usage", None)
        return ChatResult(
            content=resp.choices[0].message.content or "",
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            total_tokens=getattr(usage, "total_tokens", 0) or 0,
        )

    async def stream_chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
    ) -> AsyncIterator[StreamEvent]:
        client = _get_client()
        stream = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            stream=True,
            stream_options={"include_usage": True},
        )
        async for chunk in stream:
            usage = None
            if getattr(chunk, "usage", None):
                usage = StreamUsage(
                    prompt_tokens=chunk.usage.prompt_tokens or 0,
                    completion_tokens=chunk.usage.completion_tokens or 0,
                    total_tokens=chunk.usage.total_tokens or 0,
                )
            text = None
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                text = chunk.choices[0].delta.content
            if text is not None or usage is not None:
                yield StreamEvent(text=text, usage=usage)

    async def embed(self, *, model: str, texts: list[str]) -> EmbeddingResult:
        client = _get_client()
        resp = await client.embeddings.create(model=model, input=texts)
        usage = getattr(resp, "usage", None)
        return EmbeddingResult(
            vectors=[d.embedding for d in resp.data],
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            total_tokens=getattr(usage, "total_tokens", 0) or 0,
        )
