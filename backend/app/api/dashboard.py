"""Dashboard (v3 §7)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal, get_current_user, get_db
from app.schemas.common import ApiResponse, ok
from app.schemas.dashboard import DashboardResponse
from app.services import dashboard_service

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_model=ApiResponse[DashboardResponse])
async def get_dashboard(
    response: Response,
    principal: Principal = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    response.headers["Cache-Control"] = "max-age=60, stale-while-revalidate=60"
    return ok(await dashboard_service.build_dashboard(db, workspace_id=principal.workspace_id))
