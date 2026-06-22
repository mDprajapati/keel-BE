"""Workspace settings (v3 §15). View = member; update = admin."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal, get_current_user, get_db, require_admin
from app.schemas.workspace import WorkspaceSettings, WorkspaceSettingsUpdate
from app.services import settings_service

router = APIRouter(tags=["settings"])


@router.get("/settings", response_model=WorkspaceSettings)
async def get_settings(
    principal: Principal = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await settings_service.get_settings(db, workspace_id=principal.workspace_id)


@router.patch("/settings", response_model=WorkspaceSettings)
async def update_settings(
    payload: WorkspaceSettingsUpdate,
    principal: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await settings_service.update_settings(
        db, workspace_id=principal.workspace_id, patch=payload
    )
