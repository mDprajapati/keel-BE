"""Ingestion endpoints (dual auth; write scope). Same pipeline for app + REST (v3 §13.2)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import log_api_call
from app.core.config import settings
from app.core.deps import Principal, ensure_write_scope, get_db, get_principal
from app.core.errors import BadRequestError
from app.models.base import SourceType
from app.models.user import User
from app.schemas.common import ApiResponse, ok
from app.schemas.ingest import IngestJobResponse, IngestStatusOut, RecordIngest, TextIngest
from app.services import document_service
from app.stores.storage import build_path, get_storage

router = APIRouter(tags=["ingest"])


async def _uploader_name(db: AsyncSession, principal: Principal) -> str:
    if principal.user_id:
        user = await db.get(User, principal.user_id)
        return user.full_name if user else "user"
    return "API"


def _source_type(principal: Principal) -> str:
    return SourceType.api_push.value if principal.api_key_id else SourceType.manual_upload.value


@router.post(
    "/ingest/file",
    response_model=ApiResponse[IngestJobResponse],
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_file(
    file: UploadFile = File(...),
    file_name: str | None = Form(None),
    source_label: str | None = Form(None),
    tags: str | None = Form(None),
    upload_id: str | None = Form(None),
    part_number: int | None = Form(None),
    total_parts: int | None = Form(None),
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    ensure_write_scope(principal)
    name = file_name or file.filename or "upload"
    doc_id = uuid.uuid4()
    storage = get_storage()
    path = build_path(str(principal.workspace_id), str(doc_id), name)

    if upload_id and total_parts:
        # Final part of a multipart upload (>10 MB, v3 §8.1): save it, then assemble
        # all previously-uploaded parts in object storage into the stored document.
        storage.save_part(upload_id, part_number or total_parts, await file.read())
        storage.complete_multipart(upload_id, path, total_parts)
        size_bytes = storage.size(path)
        file_type = document_service.detect_file_type(name)
    else:
        data = await file.read()
        file_type = document_service.detect_file_type(name, data)
        storage.save_bytes(path, data)
        size_bytes = len(data)

    if size_bytes > settings.max_upload_bytes:
        raise BadRequestError("File exceeds the 500 MB limit", error_code="FILE_TOO_LARGE")

    tag_list = [t.strip() for t in tags.split(",")] if tags else []
    doc, job = await document_service.create_queued_document(
        db,
        document_id=doc_id,
        workspace_id=principal.workspace_id,
        name=name,
        filename=name,
        file_type=file_type,
        source_type=_source_type(principal),
        size_bytes=size_bytes,
        storage_path=path,
        mime_type=file.content_type,
        tags=tag_list,
        uploaded_by=await _uploader_name(db, principal),
        uploaded_by_id=principal.user_id,
    )
    await log_api_call(db, principal, "/api/ingest/file")
    return ok(IngestJobResponse(document_id=doc.id, job_id=job.id, status=doc.ingestion_status))


@router.post("/ingest/file/part")
async def ingest_file_part(
    upload_id: str = Form(...),
    part_number: int = Form(...),
    file: UploadFile = File(...),
    principal: Principal = Depends(get_principal),
):
    ensure_write_scope(principal)
    get_storage().save_part(upload_id, part_number, await file.read())
    return ok({"part": part_number, "received": True})


@router.post(
    "/ingest/text",
    response_model=ApiResponse[IngestJobResponse],
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_text(
    payload: TextIngest,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    ensure_write_scope(principal)
    doc, job = await document_service.ingest_text(
        db,
        workspace_id=principal.workspace_id,
        content=payload.content,
        title=payload.title,
        tags=payload.tags,
        uploaded_by=await _uploader_name(db, principal),
    )
    await log_api_call(db, principal, "/api/ingest/text")
    return ok(IngestJobResponse(document_id=doc.id, job_id=job.id, status=doc.ingestion_status))


@router.post(
    "/ingest/record",
    response_model=ApiResponse[IngestJobResponse],
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_record(
    payload: RecordIngest,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    ensure_write_scope(principal)
    # Render the structured record to a readable text representation for ingestion.
    body = "\n".join(f"{k}: {v}" for k, v in payload.fields.items())
    content = f"{payload.record_type} {payload.record_id}\n{body}"
    title = f"{payload.record_type}:{payload.record_id}"
    doc, job = await document_service.ingest_text(
        db,
        workspace_id=principal.workspace_id,
        content=content,
        title=title,
        tags=payload.tags,
        uploaded_by=await _uploader_name(db, principal),
    )
    await log_api_call(db, principal, "/api/ingest/record")
    return ok(IngestJobResponse(document_id=doc.id, job_id=job.id, status=doc.ingestion_status))


@router.get("/ingest/status/{job_id}", response_model=ApiResponse[IngestStatusOut])
async def ingest_status(
    job_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    job = await document_service.get_job(db, workspace_id=principal.workspace_id, job_id=job_id)
    return ok(
        IngestStatusOut(
            job_id=job.id,
            document_id=job.document_id,
            status=job.status,
            current_step=job.current_step,
            steps_completed=job.steps_completed,
            steps_total=job.steps_total,
            error=job.error,
            completed_at=job.completed_at,
        )
    )
