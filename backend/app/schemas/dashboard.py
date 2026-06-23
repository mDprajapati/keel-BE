"""Dashboard schemas — match keel-UI DashboardResponse (v3 §7)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.models.base import IngestionStatus
from app.schemas.document import KeelDocumentOut

HealthState = Literal["active", "processing", "idle", "error"]


class DashboardMetrics(BaseModel):
    documents_uploaded: int
    sources_connected: int
    documents_processed: int
    chunks_generated: int
    embeddings_created: int
    ai_tags_generated: int
    chat_queries_this_month: int
    api_calls_this_month: int


class IngestionActivityEvent(BaseModel):
    id: str
    document_name: str
    status: IngestionStatus
    timestamp: datetime


class ConnectorSyncSummary(BaseModel):
    connector_id: str
    connector_name: str
    last_synced_at: datetime | None = None
    document_count: int


class PipelineHealth(BaseModel):
    sources: HealthState
    ingestion: HealthState
    storage: HealthState
    chat: HealthState
    rest_api: HealthState


class DashboardResponse(BaseModel):
    metrics: DashboardMetrics
    recent_activity: list[IngestionActivityEvent]
    recent_documents: list[KeelDocumentOut]
    connector_sync: list[ConnectorSyncSummary]
    pipeline_health: PipelineHealth
