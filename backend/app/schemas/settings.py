"""Model config + workspace settings schemas — match keel-UI (v3 §11, §15)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ChatModel = Literal["gpt-4o-mini", "gpt-4o"]


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
