"""REST retrieval (dual auth, v3 §13.1): /search, /context, /evidence."""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import log_api_call
from app.core.deps import Principal, get_db, get_principal
from app.core.errors import NotFoundError
from app.models.document import Document, DocumentChunk
from app.schemas.common import ApiResponse, ok
from app.schemas.search import (
    ContextEvidence,
    ContextPayload,
    ContextResponse,
    SearchPayload,
    SearchResponse,
    SearchResult,
)
from app.services import retrieval_service
from app.services.llm_gateway import embed
from app.stores import vector_store

router = APIRouter(tags=["retrieval"])


@router.post("/search", response_model=ApiResponse[SearchResponse])
async def search(
    payload: SearchPayload,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    ws = principal.workspace_id
    t0 = time.perf_counter()
    vector = (await embed([payload.query], workspace_id=ws))[0]
    t1 = time.perf_counter()
    hits = vector_store.search(
        ws,
        vector,
        top_k=payload.top_k,
        score_threshold=payload.min_score,
        source_types=[s.value for s in payload.filter_source_type]
        if payload.filter_source_type
        else None,
    )
    t2 = time.perf_counter()

    results = [
        SearchResult(
            chunk_id=h.chunk_id,
            document_id=str(h.payload.get("document_id", "")),
            document_name=str(h.payload.get("document_name", "")),
            source_type=h.payload.get("source_type", "manual_upload"),
            chunk_text=str(h.payload.get("chunk_text", "")),
            similarity_score=round(h.score, 4),
            section_ref=h.payload.get("section_ref"),
            metadata={k: v for k, v in h.payload.items() if k != "chunk_text"},
        )
        for h in hits
    ]
    await log_api_call(db, principal, "/api/search")
    return ok(
        SearchResponse(
            results=results,
            query_embedding_ms=int((t1 - t0) * 1000),
            search_ms=int((t2 - t1) * 1000),
        )
    )


@router.post("/context", response_model=ApiResponse[ContextResponse])
async def context(
    payload: ContextPayload,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    chunks = await retrieval_service.retrieve(
        workspace_id=principal.workspace_id, query=payload.query, top_k=payload.top_k
    )
    context_str, used, token_count, truncated = retrieval_service.assemble_context(
        chunks, max_tokens=payload.max_tokens
    )
    await log_api_call(db, principal, "/api/context")
    return ok(
        ContextResponse(
            context=context_str,
            evidence=[
                ContextEvidence(
                    chunk_id=c.chunk_id,
                    document_name=c.document_name,
                    similarity_score=round(c.score, 4),
                    section_ref=c.section_ref,
                )
                for c in used
            ],
            token_count=token_count,
            truncated=truncated,
        )
    )


@router.get("/evidence/{chunk_id}", response_model=ApiResponse[SearchResult])
async def evidence(
    chunk_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    chunk = await db.get(DocumentChunk, chunk_id)
    if chunk is None or chunk.workspace_id != principal.workspace_id:
        raise NotFoundError("Chunk not found")
    doc = await db.get(Document, chunk.document_id)
    await log_api_call(db, principal, "/api/evidence")
    return ok(
        SearchResult(
            chunk_id=str(chunk.id),
            document_id=str(chunk.document_id),
            document_name=doc.name if doc else "",
            source_type=chunk.source_type,
            chunk_text=chunk.chunk_text,
            similarity_score=1.0,
            section_ref=chunk.section_ref,
            metadata={**(chunk.chunk_metadata or {}), "token_count": chunk.token_count},
        )
    )
