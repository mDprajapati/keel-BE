"""Admin schemas — API keys, user admin, connectors (match keel-UI)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.models.base import ApiKeyScope, ConnectorStatus, ConnectorType, Role


# ---- API keys ----
class ApiKeyOut(BaseModel):
    id: uuid.UUID
    name: str
    scope: ApiKeyScope
    created_at: datetime
    last_used_at: datetime | None = None
    request_count: int
    rate_limit_per_minute: int


class ApiKeyWithSecret(ApiKeyOut):
    secret: str


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scope: ApiKeyScope = ApiKeyScope.read_only


# ---- Users (admin) ----
class InviteRequest(BaseModel):
    email: EmailStr
    role: Role = Role.standard


class RoleUpdate(BaseModel):
    role: Role


# ---- Connectors ----
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
