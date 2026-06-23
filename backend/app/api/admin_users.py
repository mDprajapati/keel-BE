"""User & permissions (admin, v3 §14)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal, get_db, require_admin
from app.schemas.admin import InviteRequest, RoleUpdate
from app.schemas.auth import UserOut
from app.schemas.common import ApiResponse, ok
from app.services import user_service

router = APIRouter(prefix="/admin", tags=["users"])


@router.get("/users", response_model=ApiResponse[list[UserOut]])
async def list_users(
    principal: Principal = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    return ok(await user_service.list_users(db, workspace_id=principal.workspace_id))


@router.post(
    "/users/invite", response_model=ApiResponse[UserOut], status_code=status.HTTP_201_CREATED
)
async def invite_user(
    payload: InviteRequest,
    principal: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return ok(
        await user_service.invite(
            db, workspace_id=principal.workspace_id, email=payload.email, role=payload.role
        )
    )


@router.patch("/users/{user_id}/role", response_model=ApiResponse[UserOut])
async def change_role(
    user_id: uuid.UUID,
    payload: RoleUpdate,
    principal: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return ok(
        await user_service.change_role(
            db, workspace_id=principal.workspace_id, user_id=user_id, role=payload.role
        )
    )


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_user(
    user_id: uuid.UUID,
    principal: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    await user_service.remove_user(db, workspace_id=principal.workspace_id, user_id=user_id)
