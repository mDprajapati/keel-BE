"""Connector schemas (match keel-UI)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.base import ConnectorStatus, ConnectorType


class ConnectorOut(BaseModel):
    id: uuid.UUID
    type: ConnectorType
    name: str
    status: ConnectorStatus
    last_synced_at: datetime | None = None
    last_sync_document_count: int | None = None


class ConnectorFolderNode(BaseModel):
    id: str
    name: str
    type: Literal["folder", "file"]
    mime_type: str | None = None
    children: list[ConnectorFolderNode] | None = None


ConnectorFolderNode.model_rebuild()  # resolve the recursive self-reference


class OAuthStartResponse(BaseModel):
    authorization_url: str | None = None
    connected: bool | None = None


class SyncRequest(BaseModel):
    file_ids: list[str] = Field(default_factory=list)


class SyncResponse(BaseModel):
    status: str
    requested: int = 0
    created: int = 0
    skipped: int = 0
    failed: int = 0
