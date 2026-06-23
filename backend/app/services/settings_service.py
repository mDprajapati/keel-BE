"""Workspace settings + read-only model config (v3 §11, §15)."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models.organization import Organization, Workspace
from app.schemas.settings import (
    ChatConfig,
    EmbeddingConfig,
    GraphStoreConfig,
    ModelConfig,
    ParserConfig,
    ReadOnlySettings,
    VectorStoreConfig,
    WorkspaceSettings,
    WorkspaceSettingsUpdate,
)


async def _load(db: AsyncSession, workspace_id: uuid.UUID) -> tuple[Workspace, Organization]:
    ws = await db.get(Workspace, workspace_id)
    if ws is None:
        raise NotFoundError("Workspace not found")
    org = await db.get(Organization, ws.organization_id)
    if org is None:
        raise NotFoundError("Organization not found")
    return ws, org


def _to_settings(ws: Workspace, org: Organization) -> WorkspaceSettings:
    return WorkspaceSettings(
        workspace_name=ws.name,
        organization_name=org.name,
        auto_start_ingestion=ws.auto_start_ingestion,
        chat_model=ws.chat_model,  # type: ignore[arg-type]
        chat_top_k=ws.chat_top_k,
        min_similarity_threshold=ws.min_similarity,
        rest_api_enabled=ws.rest_api_enabled,
        default_rate_limit_per_minute=ws.default_rate_limit_per_minute,
        sync_mode="manual",
        read_only=ReadOnlySettings(
            parser="Docling 2.x",
            embedding_model=ws.embedding_model,
            vector_store="Qdrant Community",
            graph_store="Neo4j Community",
        ),
    )


async def get_settings(db: AsyncSession, *, workspace_id: uuid.UUID) -> WorkspaceSettings:
    ws, org = await _load(db, workspace_id)
    return _to_settings(ws, org)


async def update_settings(
    db: AsyncSession, *, workspace_id: uuid.UUID, patch: WorkspaceSettingsUpdate
) -> WorkspaceSettings:
    ws, org = await _load(db, workspace_id)
    if patch.workspace_name is not None:
        ws.name = patch.workspace_name
    if patch.organization_name is not None:
        org.name = patch.organization_name
    if patch.auto_start_ingestion is not None:
        ws.auto_start_ingestion = patch.auto_start_ingestion
    if patch.chat_model is not None:
        ws.chat_model = patch.chat_model
    if patch.chat_top_k is not None:
        ws.chat_top_k = patch.chat_top_k
    if patch.min_similarity_threshold is not None:
        ws.min_similarity = patch.min_similarity_threshold
    if patch.rest_api_enabled is not None:
        ws.rest_api_enabled = patch.rest_api_enabled
    if patch.default_rate_limit_per_minute is not None:
        ws.default_rate_limit_per_minute = patch.default_rate_limit_per_minute
    await db.commit()
    return _to_settings(ws, org)


async def get_model_config(db: AsyncSession, *, workspace_id: uuid.UUID) -> ModelConfig:
    ws, _ = await _load(db, workspace_id)
    return ModelConfig(
        parser=ParserConfig(
            name="Docling",
            version="2.x",
            processing_mode="Streaming for files > 50 MB",
            supported_formats=["PDF", "DOCX", "TXT", "CSV", "XLSX", "PPTX"],
        ),
        embedding=EmbeddingConfig(
            provider="OpenAI",
            model=ws.embedding_model,
            dimensions=ws.embedding_dims,
            max_input_tokens=8191,
            chunk_target=512,
            chunk_max=1024,
        ),
        chat=ChatConfig(
            provider="OpenAI",
            model=ws.chat_model,  # type: ignore[arg-type]
            max_context_tokens=128_000,
            retrieval_context_tokens=8000,
        ),
        vector_store=VectorStoreConfig(
            engine="Qdrant Community",
            index_type="HNSW (m=16, ef_construction=64)",
            similarity_metric="Cosine",
        ),
        graph_store=GraphStoreConfig(engine="Neo4j Community"),
    )
