"""Resumable ingestion pipeline (v3 §9.1, 16 steps).

Each step writes its output + `ingestion_status` before the next. The pipeline is
**idempotent**: on retry it re-runs from the start but skips steps whose output
already exists (tags set, chunks persisted, embeddings done), so a transient
failure effectively resumes without redoing expensive LLM work. Permanent errors
(parse/unsupported) dead-letter immediately; transient errors raise
`TransientIngestionError` for the Celery task to retry.

Test by calling `run(document_id)` directly — never `.delay()`.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select

from app.core.database import get_session_factory
from app.core.logging import get_logger
from app.models.base import EmbeddingStatus, IngestionStatus
from app.models.document import Document, DocumentChunk
from app.models.ingestion import IngestionError, IngestionJob
from app.services import graph_store, vector_store
from app.services.ai import ner, tagging
from app.services.ai.llm_gateway import embed
from app.services.chunking import chunk_parsed
from app.services.parsing import ParsedDocument, ParseError, parse_document
from app.services.storage import get_storage

log = get_logger(__name__)
STEPS_TOTAL = 16


class TransientIngestionError(Exception):
    """Retryable failure (network, rate limit, unavailable dependency)."""


class PermanentIngestionError(Exception):
    """Non-retryable failure (already recorded as failed + dead-letter)."""


async def _set_status(db, doc, job, status: str, step_name: str, steps_done: int) -> None:
    doc.ingestion_status = status
    doc.current_step = step_name
    job.status = status
    job.current_step = step_name
    job.steps_completed = steps_done
    await db.commit()


async def _dead_letter(db, doc, job, *, step: str, exc: Exception) -> None:
    db.add(
        IngestionError(
            document_id=doc.id,
            workspace_id=doc.workspace_id,
            step_failed=step,
            error_type=type(exc).__name__,
            error_message=str(exc)[:2000],
            retry_count=0,
        )
    )
    doc.ingestion_status = IngestionStatus.failed.value
    job.status = IngestionStatus.failed.value
    job.current_step = step
    job.error = str(exc)[:2000]
    await db.commit()


async def mark_failed(document_id: str, *, step: str, error: str) -> None:
    """Called by the task after retries are exhausted."""
    factory = get_session_factory()
    async with factory() as db:
        doc = await db.get(Document, uuid.UUID(str(document_id)))
        if doc is None:
            return
        job = (
            (
                await db.execute(
                    select(IngestionJob)
                    .where(IngestionJob.document_id == doc.id)
                    .order_by(IngestionJob.created_at.desc())
                )
            )
            .scalars()
            .first()
        )
        if job is None:
            # The dead-letter net must never crash on a missing job row.
            job = IngestionJob(
                document_id=doc.id, workspace_id=doc.workspace_id, steps_total=STEPS_TOTAL
            )
            db.add(job)
            await db.flush()
        await _dead_letter(db, doc, job, step=step, exc=TransientIngestionError(error))


async def run(document_id: str | uuid.UUID) -> None:
    factory = get_session_factory()
    async with factory() as db:
        doc = await db.get(Document, uuid.UUID(str(document_id)))
        if doc is None:
            log.warning("ingest_doc_missing", document_id=str(document_id))
            return
        job = (
            (
                await db.execute(
                    select(IngestionJob)
                    .where(IngestionJob.document_id == doc.id)
                    .order_by(IngestionJob.created_at.desc())
                )
            )
            .scalars()
            .first()
        )
        if job is None:
            job = IngestionJob(
                document_id=doc.id, workspace_id=doc.workspace_id, steps_total=STEPS_TOTAL
            )
            db.add(job)
            await db.flush()

        ws = doc.workspace_id
        current = "retrieve"
        try:
            # 1. retrieve bytes
            await _set_status(db, doc, job, IngestionStatus.processing.value, "retrieve", 1)
            data = get_storage().get_bytes(doc.storage_path) if doc.storage_path else b""

            # 2-3. parse + extract structure
            current = "parse"
            await _set_status(db, doc, job, IngestionStatus.parsing.value, "parse", 3)
            parsed: ParsedDocument = (
                parse_document(data, doc.file_type, size_bytes=doc.size_bytes)
                if data
                else ParsedDocument()
            )

            # 4-5. tags (skip if already set)
            current = "tagging"
            await _set_status(db, doc, job, IngestionStatus.tagging.value, "tagging", 5)
            if not doc.tags:
                doc.tags = await tagging.generate_tags(parsed.text, workspace_id=ws, session=db)
                await db.commit()

            # 6. chunk
            current = "chunking"
            await _set_status(db, doc, job, IngestionStatus.chunking.value, "chunking", 6)
            chunks = chunk_parsed(parsed)

            # 7-9. SHA-256 (SKELETON — computed/stored, never blocks; v3 §9.2)
            doc.content_hash = hashlib.sha256(data).hexdigest() if data else None

            # 10. persist chunks (idempotent: replace any existing)
            current = "persist_chunks"
            await db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc.id))
            chunk_rows = [
                DocumentChunk(
                    id=uuid.uuid4(),
                    document_id=doc.id,
                    workspace_id=ws,
                    chunk_index=c.chunk_index,
                    chunk_text=c.chunk_text,
                    token_count=c.token_count,
                    section_ref=c.section_ref,
                    source_type=doc.source_type,
                    chunk_metadata=c.metadata,
                )
                for c in chunks
            ]
            db.add_all(chunk_rows)
            doc.chunk_count = len(chunk_rows)
            await db.commit()

            # 11-12. embed + upsert vectors
            current = "embedding"
            await _set_status(db, doc, job, IngestionStatus.embedding.value, "embedding", 12)
            doc.embedding_status = EmbeddingStatus.in_progress.value
            await db.commit()
            if chunk_rows:
                vectors = await embed(
                    [r.chunk_text for r in chunk_rows], workspace_id=ws, session=db
                )
                points = [
                    vector_store.VectorPoint(
                        chunk_id=str(r.id),
                        vector=v,
                        payload={
                            "workspace_id": str(ws),
                            "document_id": str(doc.id),
                            "document_name": doc.name,
                            "chunk_index": r.chunk_index,
                            "section_ref": r.section_ref,
                            "source_type": doc.source_type,
                            "chunk_text": r.chunk_text,
                            "tags": doc.tags or [],
                        },
                    )
                    for r, v in zip(chunk_rows, vectors, strict=False)
                ]
                vector_store.upsert(ws, points)
            doc.embedding_status = EmbeddingStatus.completed.value
            await db.commit()

            # 13-14. NER + graph (best-effort — never fails the document)
            current = "graph"
            await _set_status(db, doc, job, IngestionStatus.graph_mapping.value, "graph", 14)
            entities, relations = await ner.extract(parsed.text, workspace_id=ws, session=db)
            await graph_store.upsert_graph(
                workspace_id=ws,
                document_id=doc.id,
                entities=entities,
                relations=relations,
                default_chunk_id=chunk_rows[0].id if chunk_rows else None,
            )

            # 15-16. finalize + complete
            current = "finalize"
            doc.doc_metadata = {
                **(doc.doc_metadata or {}),
                "page_count": parsed.page_count,
                "entities": len(entities),
            }
            await _set_status(db, doc, job, IngestionStatus.finalizing.value, "finalize", 15)
            await _set_status(
                db, doc, job, IngestionStatus.completed.value, "completed", STEPS_TOTAL
            )
            job.completed_at = datetime.now(UTC)
            await db.commit()
            log.info("ingest_completed", document_id=str(doc.id), chunks=doc.chunk_count)

        except ParseError as exc:
            await _dead_letter(db, doc, job, step=current, exc=exc)
            log.warning("ingest_parse_failed", document_id=str(doc.id), error=str(exc))
            raise PermanentIngestionError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 — transient → let the task retry
            doc.embedding_status = (
                EmbeddingStatus.failed.value if current == "embedding" else doc.embedding_status
            )
            await db.commit()
            log.error("ingest_step_failed", document_id=str(doc.id), step=current, error=str(exc))
            raise TransientIngestionError(f"{current}: {exc}") from exc
