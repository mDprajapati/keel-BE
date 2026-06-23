"""Token-usage cost math (spec 013 AC 2)."""

from __future__ import annotations

from app.services.usage import estimate_cost


def test_chat_cost():
    # gpt-4o-mini: $0.00015/1k in + $0.0006/1k out
    assert estimate_cost("gpt-4o-mini", 1000, 1000) == round(0.00015 + 0.0006, 6)


def test_embedding_cost_output_free():
    assert estimate_cost("text-embedding-3-small", 1000, 0) == round(0.00002, 6)


def test_unknown_model_is_zero():
    assert estimate_cost("mystery-model", 1000, 1000) == 0.0
