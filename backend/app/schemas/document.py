"""Document schemas — match keel-UI KeelDocument."""

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


class TagsUpdate(BaseModel):
    tags: list[str] = Field(default_factory=list)
