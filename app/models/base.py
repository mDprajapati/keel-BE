"""Declarative base, common mixins, and string enums.

Every table gets a UUID pk + created_at + updated_at (timeline: 'always include
BOTH timestamps'). Enums are ``StrEnum`` so values serialize directly to the
exact strings the frontend expects; columns store them as VARCHAR.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# ---- Enums (string values match keel-UI types verbatim) ----
class Role(StrEnum):
    admin = "admin"
    standard = "standard"


class SourceType(StrEnum):
    manual_upload = "manual_upload"
    google_drive = "google_drive"
    onedrive = "onedrive"
    api_push = "api_push"


class IngestionStatus(StrEnum):
    queued = "queued"
    processing = "processing"
    parsing = "parsing"
    tagging = "tagging"
    chunking = "chunking"
    embedding = "embedding"
    entity_extraction = "entity_extraction"
    graph_mapping = "graph_mapping"
    finalizing = "finalizing"
    completed = "completed"
    failed = "failed"
    duplicate = "duplicate"  # forward-compat only; never produced in MVP


class EmbeddingStatus(StrEnum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"


class FileType(StrEnum):
    pdf = "pdf"
    docx = "docx"
    txt = "txt"
    csv = "csv"
    xlsx = "xlsx"
    pptx = "pptx"
    png = "png"
    jpg = "jpg"


class ApiKeyScope(StrEnum):
    read_only = "read_only"
    read_write = "read_write"


class ConnectorType(StrEnum):
    google_drive = "google_drive"
    onedrive = "onedrive"


class ConnectorStatus(StrEnum):
    connected = "connected"
    disconnected = "disconnected"
    coming_soon = "coming_soon"


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()
