"""Chat schemas — match keel-UI Conversation, ChatMessage, EvidenceChunk."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.base import SourceType


class EvidenceChunk(BaseModel):
    chunk_id: str
    document_id: str
    document_name: str
    source_type: SourceType
    section_ref: str | None = None
    excerpt: str
    similarity_score: float


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str
    updated_at: datetime


class ChatMessageOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: Literal["user", "assistant"]
    content: str
    confidence: float | None = None
    evidence: list[EvidenceChunk] = Field(default_factory=list)
    created_at: datetime


class ChatQuery(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    conversation_id: uuid.UUID | None = None


class ChatNonStreamResponse(BaseModel):
    answer: str
    confidence: float
    evidence: list[EvidenceChunk]
    conversation_id: str
