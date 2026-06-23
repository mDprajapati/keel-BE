"""Dashboard aggregation (v3 §7) — counters, feeds, connector sync, health."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import ApiCallLog
from app.models.base import ConnectorStatus, IngestionStatus
from app.models.chat import ChatMessage
from app.models.connector import Connector
from app.models.document import Document
from app.schemas.dashboard import (
    ConnectorSyncSummary,
    DashboardMetrics,
    DashboardResponse,
    IngestionActivityEvent,
    PipelineHealth,
)
from app.schemas.document import KeelDocumentOut

_IN_PROGRESS = {
    IngestionStatus.queued.value,
    IngestionStatus.processing.value,
    IngestionStatus.parsing.value,
    IngestionStatus.tagging.value,
    IngestionStatus.chunking.value,
    IngestionStatus.embedding.value,
    IngestionStatus.entity_extraction.value,
    IngestionStatus.graph_mapping.value,
    IngestionStatus.finalizing.value,
}


async def build_dashboard(db: AsyncSession, *, workspace_id: uuid.UUID) -> DashboardResponse:
    now = datetime.now(UTC)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    async def scalar(stmt) -> int:
        return (await db.execute(stmt)).scalar_one() or 0

    docs_filter = Document.workspace_id == workspace_id
    total_docs = await scalar(select(func.count()).select_from(Document).where(docs_filter))
    processed = await scalar(
        select(func.count())
        .select_from(Document)
        .where(docs_filter, Document.ingestion_status == "completed")
    )
    chunks = await scalar(
        select(func.coalesce(func.sum(Document.chunk_count), 0)).where(docs_filter)
    )
    tags_total = await scalar(
        select(
            func.coalesce(func.sum(func.coalesce(func.array_length(Document.tags, 1), 0)), 0)
        ).where(docs_filter)
    )
    sources_connected = await scalar(
        select(func.count())
        .select_from(Connector)
        .where(
            Connector.workspace_id == workspace_id,
            Connector.status == ConnectorStatus.connected.value,
        )
    )
    chat_queries = await scalar(
        select(func.count())
        .select_from(ChatMessage)
        .where(
            ChatMessage.workspace_id == workspace_id,
            ChatMessage.role == "user",
            ChatMessage.created_at >= month_start,
        )
    )
    api_calls = await scalar(
        select(func.count())
        .select_from(ApiCallLog)
        .where(ApiCallLog.workspace_id == workspace_id, ApiCallLog.created_at >= month_start)
    )

    recent = list(
        (
            await db.execute(
                select(Document).where(docs_filter).order_by(Document.updated_at.desc()).limit(20)
            )
        )
        .scalars()
        .all()
    )
    connectors = list(
        (await db.execute(select(Connector).where(Connector.workspace_id == workspace_id)))
        .scalars()
        .all()
    )

    ingestion_health = (
        "processing" if any(d.ingestion_status in _IN_PROGRESS for d in recent) else "idle"
    )

    return DashboardResponse(
        metrics=DashboardMetrics(
            documents_uploaded=total_docs,
            sources_connected=sources_connected,
            documents_processed=processed,
            chunks_generated=chunks,
            embeddings_created=chunks,
            ai_tags_generated=tags_total,
            chat_queries_this_month=chat_queries,
            api_calls_this_month=api_calls,
        ),
        recent_activity=[
            IngestionActivityEvent(
                id=f"act_{d.id}",
                document_name=d.name,
                status=d.ingestion_status,
                timestamp=d.updated_at,
            )
            for d in recent
        ],
        recent_documents=[KeelDocumentOut.from_orm_doc(d) for d in recent[:10]],
        connector_sync=[
            ConnectorSyncSummary(
                connector_id=str(c.id),
                connector_name=c.name,
                last_synced_at=c.last_synced_at,
                document_count=c.last_sync_document_count or 0,
            )
            for c in connectors
            if c.status == ConnectorStatus.connected.value
        ],
        pipeline_health=PipelineHealth(
            sources="active" if sources_connected or total_docs else "idle",
            ingestion=ingestion_health,
            storage="active",
            chat="active",
            rest_api="active",
        ),
    )
