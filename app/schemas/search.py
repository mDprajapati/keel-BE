"""REST retrieval schemas — match keel-UI Search/Context types (v3 §13.1)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.models.base import SourceType


class SearchPayload(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=10, ge=1, le=25)
    min_score: float = Field(default=0.65, ge=0.0, le=1.0)
    filter_source_type: list[SourceType] | None = None


class SearchResult(BaseModel):
    chunk_id: str
    document_id: str
    document_name: str
    source_type: SourceType
    chunk_text: str
    similarity_score: float
    section_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    results: list[SearchResult]
    query_embedding_ms: int
    search_ms: int


class ContextPayload(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    max_tokens: int = Field(default=8000, ge=256, le=32000)
    top_k: int = Field(default=10, ge=1, le=25)


class ContextEvidence(BaseModel):
    chunk_id: str
    document_name: str
    similarity_score: float
    section_ref: str | None = None


class ContextResponse(BaseModel):
    context: str
    evidence: list[ContextEvidence]
    token_count: int
    truncated: bool
