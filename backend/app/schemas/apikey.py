"""API key schemas (match keel-UI)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.base import ApiKeyScope


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
