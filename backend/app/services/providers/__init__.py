"""Provider factory: resolves the configured LLM/embedding backend.

The gateway calls :func:`get_provider` to obtain a cached provider instance.
Add a new backend by implementing :class:`~app.services.providers.base.LLMProvider`
in a new module here and adding a branch below.
"""

from __future__ import annotations

from app.services.providers.base import LLMProvider

_provider: LLMProvider | None = None


def get_provider() -> LLMProvider:
    """Return the cached LLM/embedding provider (OpenAI in the MVP)."""
    global _provider
    if _provider is None:
        from app.services.providers.openai import OpenAIProvider

        _provider = OpenAIProvider()
    return _provider


def reset_provider() -> None:
    """Drop the cached provider (used by tests)."""
    global _provider
    _provider = None
