"""Qdrant adapter (v3 §9.4, AI timeline).

Per-workspace collection, HNSW (m=16, ef_construction=64), cosine, 1536-d.
EVERY search passes a mandatory `workspace_id` payload filter — the hard tenant
boundary. Client built lazily (import-safe without Qdrant running).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_client: Any = None
_ensured: set[str] = set()


@dataclass
class VectorPoint:
    chunk_id: str
    vector: list[float]
    payload: dict = field(default_factory=dict)


@dataclass
class SearchHit:
    chunk_id: str
    score: float
    payload: dict


def collection_name(workspace_id: str | uuid.UUID) -> str:
    return f"ws_{workspace_id}"


def _get_client() -> Any:
    global _client
    if _client is None:
        from qdrant_client import QdrantClient  # lazy

        _client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None,
        )
    return _client


def ensure_collection(workspace_id: str | uuid.UUID) -> None:
    name = collection_name(workspace_id)
    if name in _ensured:
        return
    from qdrant_client import models  # lazy

    client = _get_client()
    if not client.collection_exists(name):
        client.create_collection(
            collection_name=name,
            vectors_config=models.VectorParams(
                size=settings.embedding_dims, distance=models.Distance.COSINE
            ),
            hnsw_config=models.HnswConfigDiff(m=16, ef_construct=64),
        )
        # Payload index on workspace_id for fast mandatory filtering.
        client.create_payload_index(name, "workspace_id", models.PayloadSchemaType.KEYWORD)
    _ensured.add(name)


def upsert(workspace_id: str | uuid.UUID, points: list[VectorPoint]) -> None:
    if not points:
        return
    from qdrant_client import models  # lazy

    ensure_collection(workspace_id)
    _get_client().upsert(
        collection_name=collection_name(workspace_id),
        points=[
            models.PointStruct(id=p.chunk_id, vector=p.vector, payload=p.payload) for p in points
        ],
    )


def search(
    workspace_id: str | uuid.UUID,
    query_vector: list[float],
    *,
    top_k: int = 10,
    score_threshold: float | None = None,
    source_types: list[str] | None = None,
    document_ids: list[str] | None = None,
) -> list[SearchHit]:
    """Vector search with the MANDATORY workspace_id filter (+ optional source/doc filters)."""
    from qdrant_client import models  # lazy

    must: list[Any] = [
        models.FieldCondition(key="workspace_id", match=models.MatchValue(value=str(workspace_id)))
    ]
    if source_types:
        must.append(
            models.FieldCondition(key="source_type", match=models.MatchAny(any=source_types))
        )
    if document_ids:
        must.append(
            models.FieldCondition(key="document_id", match=models.MatchAny(any=document_ids))
        )

    hits = _get_client().search(
        collection_name=collection_name(workspace_id),
        query_vector=query_vector,
        query_filter=models.Filter(must=must),
        limit=top_k,
        score_threshold=score_threshold,
        with_payload=True,
    )
    return [SearchHit(chunk_id=str(h.id), score=h.score, payload=h.payload or {}) for h in hits]
