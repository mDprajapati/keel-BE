"""Document + DocumentChunk. `name`/`uploaded_by`/`uploaded_at` map to KeelDocument."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    Base,
    EmbeddingStatus,
    IngestionStatus,
    TimestampMixin,
    UUIDMixin,
)


class Document(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "documents"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)  # -> KeelDocument.name
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    source_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    connector_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("connectors.id", ondelete="SET NULL"), nullable=True
    )
    external_document_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    external_modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    storage_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    doc_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    ingestion_status: Mapped[str] = mapped_column(
        String(30), default=IngestionStatus.queued.value, nullable=False, index=True
    )
    current_step: Mapped[str | None] = mapped_column(String(50), nullable=True)
    chunk_count: Mapped[int | None] = mapped_column(Integer, nullable=True)  # null until chunked
    embedding_status: Mapped[str] = mapped_column(
        String(20), default=EmbeddingStatus.pending.value, nullable=False
    )

    # SKELETON — SHA-256 dedup deferred (v3 §9.2): stored, never enforced.
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    duplicate_of: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )

    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_by: Mapped[str] = mapped_column(String(255), default="", nullable=False)  # display


class DocumentChunk(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "document_chunks"
    # Composite index for retrieval/eviction by (workspace_id, document_id) — data-model.md.
    __table_args__ = (Index("ix_chunks_ws_doc", "workspace_id", "document_id"),)

    # chunk_id is this row's `id` (UUID); referenced as the Qdrant point id.
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    section_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    chunk_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
