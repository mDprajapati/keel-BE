"""Read-only model config page (v3 §11)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal, get_current_user, get_db
from app.schemas.common import ApiResponse, ok
from app.schemas.settings import ModelConfig
from app.services import settings_service

router = APIRouter(tags=["model"])


@router.get("/model", response_model=ApiResponse[ModelConfig])
async def get_model(
    principal: Principal = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return ok(await settings_service.get_model_config(db, workspace_id=principal.workspace_id))
