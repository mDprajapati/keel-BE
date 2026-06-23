"""Regression tests for the production-readiness fixes (offline, no external services).

- The worker must reuse ONE event loop across documents — `asyncio.run` per task bound
  the async DB engine to a closed loop and crashed the 2nd document.
- Chat must feed prior conversation turns to the model — multi-turn was silently dropped.
"""

from __future__ import annotations

import asyncio


def test_worker_run_reuses_one_event_loop():
    """`_run` reuses a single loop so loop-bound resources (the async DB engine) stay
    valid across documents. The old `asyncio.run` per task created a fresh loop each
    time and crashed the 2nd document with 'Event loop is closed'."""
    from ingestion import tasks as ingestion

    state: dict = {}

    async def _make() -> int:
        state["lock"] = asyncio.Lock()  # binds to the running loop
        async with state["lock"]:
            return id(asyncio.get_running_loop())

    async def _reuse() -> int:
        # Re-acquiring a primitive created in a previous _run must not raise
        # "is bound to a different event loop".
        async with state["lock"]:
            return id(asyncio.get_running_loop())

    loop1 = ingestion._run(_make())
    loop2 = ingestion._run(_reuse())
    assert loop1 == loop2


def test_chat_messages_feed_history_to_model():
    """Prior turns must reach the LLM (multi-turn). The old code returned only
    [system, user] and dropped conversation history."""
    from app.services.chat_service import _messages

    history = [
        {"role": "user", "content": "What is Keel?"},
        {"role": "assistant", "content": "An enterprise context platform."},
    ]
    msgs = _messages("CONTEXT", "Tell me more", history)
    assert msgs[0]["role"] == "system"
    assert msgs[1:3] == history  # history sits between system and the new user turn
    assert msgs[-1]["role"] == "user"
    assert "Tell me more" in msgs[-1]["content"]
    # No history (new conversation) → just system + user.
    assert len(_messages("CONTEXT", "hi")) == 2
