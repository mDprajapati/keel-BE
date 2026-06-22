"""API key management (admin, JWT)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal, get_db, require_admin
from app.schemas.admin import ApiKeyCreate, ApiKeyOut, ApiKeyWithSecret
from app.services import apikey_service

router = APIRouter(tags=["api-keys"])


@router.get("/apikeys", response_model=list[ApiKeyOut])
async def list_api_keys(
    principal: Principal = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    return await apikey_service.list_keys(db, workspace_id=principal.workspace_id)


@router.post("/apikeys", response_model=ApiKeyWithSecret, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    payload: ApiKeyCreate,
    principal: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await apikey_service.create_key(
        db,
        workspace_id=principal.workspace_id,
        name=payload.name,
        scope=payload.scope,
        created_by=principal.user_id,
    )


@router.delete("/apikeys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: uuid.UUID,
    principal: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    await apikey_service.revoke_key(db, workspace_id=principal.workspace_id, key_id=key_id)
