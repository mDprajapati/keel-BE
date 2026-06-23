"""Provider-agnostic protocols + result types for LLM / embedding backends.

Only modules under ``services/providers/`` may import a vendor SDK (openai, ...).
The gateway (``services/llm_gateway.py``) programs against these protocols and
result types, so swapping providers never touches the gateway or its callers.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class ChatResult:
    """Result of a non-streaming chat completion."""

    content: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class StreamUsage:
    """Token usage surfaced on the final frame of a streaming completion."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class StreamEvent:
    """A single streamed frame: a content delta and/or end-of-stream usage."""

    text: str | None = None
    usage: StreamUsage | None = None


@dataclass
class EmbeddingResult:
    """Result of a single embedding batch."""

    vectors: list[list[float]]
    prompt_tokens: int
    total_tokens: int


@runtime_checkable
class LLMProvider(Protocol):
    """Interface every LLM/embedding backend must satisfy.

    Implementations stay stateless per call — retry, rate limiting, and
    token-usage logging live in the gateway, not here.
    """

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int | None = None,
        response_format: dict | None = None,
    ) -> ChatResult: ...

    def stream_chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
    ) -> AsyncIterator[StreamEvent]: ...

    async def embed(self, *, model: str, texts: list[str]) -> EmbeddingResult: ...
