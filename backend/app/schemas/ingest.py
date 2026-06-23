"""Ingestion schemas — match keel-UI IngestJobResponse, IngestStatus."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.base import IngestionStatus


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
