"""Document / ingestion schemas — match keel-UI KeelDocument, IngestJobResponse, IngestStatus."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.base import EmbeddingStatus, FileType, IngestionStatus, SourceType


class KeelDocumentOut(BaseModel):
    id: uuid.UUID
    name: str
    file_type: FileType
    source_type: SourceType
    tags: list[str]
    uploaded_by: str
    uploaded_at: datetime
    ingestion_status: IngestionStatus
    chunk_count: int | None = None
    embedding_status: EmbeddingStatus

    @classmethod
    def from_orm_doc(cls, doc: Any) -> KeelDocumentOut:
        return cls(
            id=doc.id,
            name=doc.name,
            file_type=doc.file_type,
            source_type=doc.source_type,
            tags=doc.tags or [],
            uploaded_by=doc.uploaded_by or "",
            uploaded_at=doc.created_at,
            ingestion_status=doc.ingestion_status,
            chunk_count=doc.chunk_count,
            embedding_status=doc.embedding_status,
        )


class IngestJobResponse(BaseModel):
    document_id: uuid.UUID
    job_id: uuid.UUID
    status: IngestionStatus


class IngestStatusOut(BaseModel):
    job_id: uuid.UUID
    document_id: uuid.UUID
    status: IngestionStatus
    current_step: str
    steps_completed: int
    steps_total: int
    error: str | None = None
    completed_at: datetime | None = None


class TagsUpdate(BaseModel):
    tags: list[str] = Field(default_factory=list)


class TextIngest(BaseModel):
    content: str = Field(min_length=1, max_length=5_000_000)  # ≤ 5 MB UTF-8
    title: str = Field(min_length=1, max_length=255)
    source_label: str | None = None
    tags: list[str] = Field(default_factory=list)


class RecordIngest(BaseModel):
    record_type: str = Field(min_length=1)
    record_id: str = Field(min_length=1)
    fields: dict[str, Any]
    source_label: str | None = None
    tags: list[str] = Field(default_factory=list)
