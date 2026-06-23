"""Auth schemas — match keel-UI AuthTokenResponse / SessionInfo / User / Workspace."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.base import Role


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    organization_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=12, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: uuid.UUID
    full_name: str
    email: EmailStr
    role: Role
    last_active_at: datetime | None = None


class WorkspaceOut(BaseModel):
    id: uuid.UUID
    name: str
    organization_name: str


class AuthTokenResponse(BaseModel):
    access_token: str
    user: UserOut
    workspace: WorkspaceOut


class SessionInfo(BaseModel):
    user: UserOut
    workspace: WorkspaceOut
