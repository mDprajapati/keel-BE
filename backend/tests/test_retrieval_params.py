"""G3: retrieval honors explicit top_k / min_score so the chat path can apply the
per-workspace settings (v3 §15.1) instead of the global defaults. Offline — adapters
mocked."""

from __future__ import annotations

from app.services import retrieval_service


async def test_retrieve_honors_explicit_top_k_and_min_score(monkeypatch):
    captured: dict = {}

    def fake_search(ws, vector, *, top_k, score_threshold, source_types=None, document_ids=None):
        captured["top_k"] = top_k
        captured["threshold"] = score_threshold
        return []

    async def fake_embed(texts, **kwargs):
        return [[0.0] * 1536]

    monkeypatch.setattr(retrieval_service.vector_store, "search", fake_search)
    monkeypatch.setattr(retrieval_service, "embed", fake_embed)

    await retrieval_service.retrieve(
        workspace_id="ws-1", query="q", top_k=3, min_score=0.9, augment=False
    )

    assert captured["top_k"] == 3
    assert captured["threshold"] == 0.9
