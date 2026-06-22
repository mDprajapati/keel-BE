"""Document service — create+enqueue ingestion, list/filter, tags, delete, reprocess."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import InvalidFileTypeError, NotFoundError
from app.core.logging import get_logger
from app.models.base import FileType, IngestionStatus, SourceType
from app.models.document import Document
from app.models.ingestion import IngestionJob
from app.services.storage import build_path, get_storage

log = get_logger(__name__)

_ALLOWED = {ft.value for ft in FileType}
# Minimal magic-byte signatures (bytes-vs-extension check, v3 §8.1).
_SIGNATURES: dict[str, bytes] = {
    "pdf": b"%PDF",
    "png": b"\x89PNG",
    "jpg": b"\xff\xd8\xff",
    "docx": b"PK",  # OOXML = zip
    "xlsx": b"PK",
    "pptx": b"PK",
}


def detect_file_type(filename: str, data: bytes | None = None) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in _ALLOWED:
        raise InvalidFileTypeError(f"Unsupported file type: .{ext or '?'}")
    sig = _SIGNATURES.get(ext)
    if data is not None and sig is not None and not data[:8].startswith(sig):
        raise InvalidFileTypeError("File content does not match its extension")
    return ext


async def _enqueue(document_id: uuid.UUID) -> None:
    """Best-effort enqueue of the Celery ingestion task (broker may be down in dev)."""
    try:
        from app.tasks.ingestion import ingest_document

        ingest_document.delay(str(document_id))
    except Exception as exc:  # noqa: BLE001
        log.error("ingestion_enqueue_failed", document_id=str(document_id), error=str(exc))


async def create_queued_document(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    name: str,
    filename: str,
    file_type: str,
    source_type: str,
    size_bytes: int,
    storage_path: str | None,
    mime_type: str | None = None,
    tags: list[str] | None = None,
    uploaded_by: str = "",
    uploaded_by_id: uuid.UUID | None = None,
    document_id: uuid.UUID | None = None,
) -> tuple[Document, IngestionJob]:
    doc = Document(
        id=document_id or uuid.uuid4(),
        workspace_id=workspace_id,
        name=name,
        filename=filename,
        file_type=file_type,
        mime_type=mime_type,
        size_bytes=size_bytes,
        source_type=source_type,
        storage_path=storage_path,
        tags=[t.strip().lower() for t in (tags or []) if t.strip()][:20],
        ingestion_status=IngestionStatus.queued.value,
        uploaded_by=uploaded_by,
        uploaded_by_id=uploaded_by_id,
    )
    db.add(doc)
    await db.flush()
    job = IngestionJob(document_id=doc.id, workspace_id=workspace_id, steps_total=16)
    db.add(job)
    await db.flush()
    await db.commit()
    await _enqueue(doc.id)
    return doc, job


async def ingest_text(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    content: str,
    title: str,
    tags: list[str] | None = None,
    uploaded_by: str = "api",
) -> tuple[Document, IngestionJob]:
    doc_id = uuid.uuid4()
    path = build_path(str(workspace_id), str(doc_id), f"{title}.txt")
    get_storage().save_bytes(path, content.encode("utf-8"))
    return await _create_with_id(
        db,
        doc_id=doc_id,
        workspace_id=workspace_id,
        name=title,
        filename=f"{title}.txt",
        file_type="txt",
        source_type=SourceType.api_push.value,
        size_bytes=len(content.encode()),
        storage_path=path,
        tags=tags,
        uploaded_by=uploaded_by,
    )


async def _create_with_id(db, *, doc_id, **kw) -> tuple[Document, IngestionJob]:
    doc = Document(id=doc_id, ingestion_status=IngestionStatus.queued.value, **kw)
    doc.tags = [t.strip().lower() for t in (kw.get("tags") or []) if t.strip()][:20]
    db.add(doc)
    await db.flush()
    job = IngestionJob(document_id=doc.id, workspace_id=doc.workspace_id, steps_total=16)
    db.add(job)
    await db.flush()
    await db.commit()
    await _enqueue(doc.id)
    return doc, job


async def list_documents(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    page: int = 1,
    limit: int = 50,
    search: str | None = None,
    status: str | None = None,
    source_type: str | None = None,
    file_type: str | None = None,
    tag: str | None = None,
    sort: str = "uploaded_at",
    order: str = "desc",
) -> tuple[list[Document], int]:
    limit = max(1, min(limit, 200))
    stmt = select(Document).where(Document.workspace_id == workspace_id)
    if search:
        stmt = stmt.where(Document.name.ilike(f"%{search}%"))
    if status:
        stmt = stmt.where(Document.ingestion_status == status)
    if source_type:
        stmt = stmt.where(Document.source_type == source_type)
    if file_type:
        stmt = stmt.where(Document.file_type == file_type)
    if tag:
        stmt = stmt.where(Document.tags.contains([tag]))

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()

    sort_col = {"name": Document.name, "chunk_count": Document.chunk_count}.get(
        sort, Document.created_at
    )
    stmt = stmt.order_by(sort_col.asc() if order == "asc" else sort_col.desc())
    stmt = stmt.offset((page - 1) * limit).limit(limit)
    rows = list((await db.execute(stmt)).scalars().all())
    return rows, total


async def _get_owned(db: AsyncSession, workspace_id: uuid.UUID, doc_id: uuid.UUID) -> Document:
    doc = await db.get(Document, doc_id)
    if doc is None or doc.workspace_id != workspace_id:
        raise NotFoundError("Document not found")
    return doc


async def update_tags(db, workspace_id, doc_id, tags: list[str]) -> Document:
    doc = await _get_owned(db, workspace_id, doc_id)
    doc.tags = [t.strip().lower() for t in tags if t.strip()][:20]
    await db.commit()
    return doc


async def delete_document(db, workspace_id, doc_id) -> None:
    doc = await _get_owned(db, workspace_id, doc_id)
    await db.delete(doc)
    await db.commit()


async def reprocess(db, workspace_id, doc_id) -> tuple[Document, IngestionJob]:
    doc = await _get_owned(db, workspace_id, doc_id)
    doc.ingestion_status = IngestionStatus.queued.value
    job = IngestionJob(document_id=doc.id, workspace_id=workspace_id, steps_total=16)
    db.add(job)
    await db.commit()
    await _enqueue(doc.id)
    return doc, job


async def get_job(db: AsyncSession, *, workspace_id: uuid.UUID, job_id: uuid.UUID) -> IngestionJob:
    job = await db.get(IngestionJob, job_id)
    if job is None or job.workspace_id != workspace_id:
        raise NotFoundError("Unknown job")
    return job
