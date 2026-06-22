"""Documents — list (dual auth), tags/delete/reprocess (JWT)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import log_api_call
from app.core.deps import Principal, get_current_user, get_db, get_principal
from app.schemas.common import Paginated
from app.schemas.document import IngestJobResponse, KeelDocumentOut, TagsUpdate
from app.services import document_service

router = APIRouter(tags=["documents"])


@router.get("/documents", response_model=Paginated[KeelDocumentOut])
async def list_documents(
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    search: str | None = None,
    status_: str | None = Query(None, alias="status"),
    source_type: str | None = None,
    file_type: str | None = None,
    tag: str | None = None,
    sort: str = "uploaded_at",
    order: str = "desc",
):
    rows, total = await document_service.list_documents(
        db,
        workspace_id=principal.workspace_id,
        page=page,
        limit=limit,
        search=search,
        status=status_,
        source_type=source_type,
        file_type=file_type,
        tag=tag,
        sort=sort,
        order=order,
    )
    await log_api_call(db, principal, "/api/documents")
    return Paginated(
        data=[KeelDocumentOut.from_orm_doc(r) for r in rows], total=total, page=page, limit=limit
    )


@router.patch("/documents/{document_id}/tags", response_model=KeelDocumentOut)
async def update_tags(
    document_id: uuid.UUID,
    payload: TagsUpdate,
    principal: Principal = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    doc = await document_service.update_tags(db, principal.workspace_id, document_id, payload.tags)
    return KeelDocumentOut.from_orm_doc(doc)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    principal: Principal = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await document_service.delete_document(db, principal.workspace_id, document_id)


@router.post("/documents/{document_id}/reprocess", response_model=IngestJobResponse)
async def reprocess_document(
    document_id: uuid.UUID,
    principal: Principal = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    doc, job = await document_service.reprocess(db, principal.workspace_id, document_id)
    return IngestJobResponse(document_id=doc.id, job_id=job.id, status=doc.ingestion_status)
