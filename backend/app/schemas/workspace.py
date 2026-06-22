"""Dashboard / model / settings schemas — match keel-UI exactly (v3 §7, §11, §15)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.base import IngestionStatus
from app.schemas.document import KeelDocumentOut

HealthState = Literal["active", "processing", "idle", "error"]
ChatModel = Literal["gpt-4o-mini", "gpt-4o"]


# ---- Dashboard ----
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


# ---- Model (read-only) ----
class ParserConfig(BaseModel):
    name: str
    version: str
    processing_mode: str
    supported_formats: list[str]


class EmbeddingConfig(BaseModel):
    provider: str
    model: str
    dimensions: int
    max_input_tokens: int
    chunk_target: int
    chunk_max: int


class ChatConfig(BaseModel):
    provider: str
    model: ChatModel
    max_context_tokens: int
    retrieval_context_tokens: int


class VectorStoreConfig(BaseModel):
    engine: str
    index_type: str
    similarity_metric: str


class GraphStoreConfig(BaseModel):
    engine: str


class ModelConfig(BaseModel):
    parser: ParserConfig
    embedding: EmbeddingConfig
    chat: ChatConfig
    vector_store: VectorStoreConfig
    graph_store: GraphStoreConfig


# ---- Settings ----
class ReadOnlySettings(BaseModel):
    parser: str
    embedding_model: str
    vector_store: str
    graph_store: str


class WorkspaceSettings(BaseModel):
    workspace_name: str
    organization_name: str
    auto_start_ingestion: bool
    chat_model: ChatModel
    chat_top_k: int
    min_similarity_threshold: float
    rest_api_enabled: bool
    default_rate_limit_per_minute: int
    sync_mode: Literal["manual"] = "manual"
    read_only: ReadOnlySettings


class WorkspaceSettingsUpdate(BaseModel):
    workspace_name: str | None = None
    organization_name: str | None = None
    auto_start_ingestion: bool | None = None
    chat_model: ChatModel | None = None
    chat_top_k: int | None = Field(default=None, ge=5, le=25)
    min_similarity_threshold: float | None = Field(default=None, ge=0.5, le=0.9)
    rest_api_enabled: bool | None = None
    default_rate_limit_per_minute: int | None = Field(default=None, ge=1)
