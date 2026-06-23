"""User administration schemas (match keel-UI)."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr

from app.models.base import Role


class InviteRequest(BaseModel):
    email: EmailStr
    role: Role = Role.standard


class RoleUpdate(BaseModel):
    role: Role
