"""Workspace isolation — the hard tenant boundary (v3 §9.4 / AI timeline). A vector
search only ever returns the querying workspace's data, enforced by a per-workspace
collection AND a mandatory workspace_id payload filter. Live Qdrant; skips offline.
"""

from __future__ import annotations

import uuid

from app.stores import vector_store


def test_search_never_leaks_across_workspaces():
    ws_a, ws_b = str(uuid.uuid4()), str(uuid.uuid4())
    vec = [0.1] * 1536
    try:
        vector_store.upsert(
            ws_a,
            [vector_store.VectorPoint(str(uuid.uuid4()), vec, {"workspace_id": ws_a, "doc": "A"})],
        )
        vector_store.upsert(
            ws_b,
            [vector_store.VectorPoint(str(uuid.uuid4()), vec, {"workspace_id": ws_b, "doc": "B"})],
        )

        hits_a = vector_store.search(ws_a, vec, top_k=10)
        hits_b = vector_store.search(ws_b, vec, top_k=10)

        # Identical query vector, but each workspace sees only its own data.
        assert {h.payload.get("doc") for h in hits_a} == {"A"}
        assert {h.payload.get("doc") for h in hits_b} == {"B"}
    finally:
        client = vector_store._get_client()
        for ws in (ws_a, ws_b):
            try:
                client.delete_collection(vector_store.collection_name(ws))
            except Exception:
                pass
