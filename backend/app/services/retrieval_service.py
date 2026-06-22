"""Retrieval core (v3 §12.1, §17.3): embed → Qdrant search → best-effort 1-hop
graph augmentation → context assembly. Shared by chat and the REST endpoints.

Every search is workspace-scoped (mandatory filter in vector_store). Graph
augmentation never raises into the caller (best-effort)."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from app.core.config import settings
from app.core.logging import get_logger
from app.services import graph_store, vector_store
from app.services.ai.llm_gateway import embed
from app.services.chunking import count_tokens

log = get_logger(__name__)

_GRAPH_AUGMENT_LIMIT = 5


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    document_name: str
    source_type: str
    section_ref: str | None
    chunk_text: str
    score: float
    metadata: dict = field(default_factory=dict)


def _chunk_from_hit(hit) -> RetrievedChunk:
    p = hit.payload or {}
    return RetrievedChunk(
        chunk_id=hit.chunk_id,
        document_id=str(p.get("document_id", "")),
        document_name=str(p.get("document_name", "")),
        source_type=str(p.get("source_type", "manual_upload")),
        section_ref=p.get("section_ref"),
        chunk_text=str(p.get("chunk_text", "")),
        score=float(hit.score),
        metadata={k: v for k, v in p.items() if k not in {"chunk_text"}},
    )


def _candidate_entities(query: str) -> list[str]:
    """Cheap heuristic: capitalized multi-char tokens as entity candidates."""
    names = re.findall(r"\b[A-Z][A-Za-z0-9&.-]{2,}\b", query)
    seen: list[str] = []
    for n in names:
        if n not in seen:
            seen.append(n)
    return seen[:8]


async def retrieve(
    *,
    workspace_id: str | uuid.UUID,
    query: str,
    top_k: int | None = None,
    min_score: float | None = None,
    source_types: list[str] | None = None,
    augment: bool = True,
) -> list[RetrievedChunk]:
    k = top_k or settings.chat_top_k
    threshold = settings.chat_min_similarity if min_score is None else min_score

    vector = (await embed([query], workspace_id=workspace_id))[0]
    hits = vector_store.search(
        workspace_id, vector, top_k=k, score_threshold=threshold, source_types=source_types
    )
    chunks = [_chunk_from_hit(h) for h in hits]

    if augment:
        try:
            names = _candidate_entities(query)
            doc_ids = await graph_store.find_document_ids_for_entities(workspace_id, names)
            if doc_ids:
                seen = {c.chunk_id for c in chunks}
                extra = vector_store.search(
                    workspace_id,
                    vector,
                    top_k=_GRAPH_AUGMENT_LIMIT,
                    score_threshold=threshold,
                    document_ids=doc_ids,
                )
                for h in extra:
                    if h.chunk_id not in seen:
                        chunks.append(_chunk_from_hit(h))
        except Exception as exc:  # noqa: BLE001 — graph augmentation is best-effort
            log.warning("graph_augment_failed", error=str(exc))

    chunks.sort(key=lambda c: c.score, reverse=True)
    return chunks


def confidence_score(chunks: list[RetrievedChunk]) -> float:
    """Mean similarity of the top-3 chunks (v3 §12.2). NOT a trust score."""
    top = chunks[:3]
    return round(sum(c.score for c in top) / len(top), 4) if top else 0.0


def assemble_context(
    chunks: list[RetrievedChunk], *, max_tokens: int | None = None
) -> tuple[str, list[RetrievedChunk], int, bool]:
    """Rank-ordered context capped at max_tokens; whole low-ranked chunks dropped
    (never cut mid-sentence). Returns (context, used_chunks, token_count, truncated)."""
    cap = max_tokens or settings.context_max_tokens
    parts: list[str] = []
    used: list[RetrievedChunk] = []
    total = 0
    truncated = False
    for c in chunks:
        block = (
            f"[Source: {c.document_name}"
            + (f" — {c.section_ref}]" if c.section_ref else "]")
            + f"\n{c.chunk_text}"
        )
        tk = count_tokens(block)
        if total + tk > cap:
            truncated = True
            continue
        parts.append(block)
        used.append(c)
        total += tk
    return "\n\n".join(parts), used, total, truncated
