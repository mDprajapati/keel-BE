"""Connectors (v3 §10). View = any member; mutations = admin."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import Principal, get_current_user, get_db, require_admin
from app.models.base import ConnectorType
from app.schemas.common import ApiResponse, ok
from app.schemas.connector import (
    ConnectorFolderNode,
    ConnectorOut,
    OAuthStartResponse,
    SyncRequest,
    SyncResponse,
)
from app.services import connector_service

router = APIRouter(tags=["connectors"])


def _to_out(c) -> ConnectorOut:
    return ConnectorOut(
        id=c.id,
        type=ConnectorType(c.type),
        name=c.name,
        status=c.status,
        last_synced_at=c.last_synced_at,
        last_sync_document_count=c.last_sync_document_count,
    )


@router.get("/connectors", response_model=ApiResponse[list[ConnectorOut]])
async def list_connectors(
    principal: Principal = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    rows = await connector_service.list_connectors(db, workspace_id=principal.workspace_id)
    return ok([_to_out(c) for c in rows])


@router.post(
    "/connectors/{conn_type}/oauth/start", response_model=ApiResponse[OAuthStartResponse]
)
async def start_oauth(
    conn_type: ConnectorType,
    principal: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await connector_service.start_oauth(
        db, workspace_id=principal.workspace_id, conn_type=conn_type.value
    )
    return ok(OAuthStartResponse(**result))


@router.get(
    "/connectors/{connector_id}/folders",
    response_model=ApiResponse[list[ConnectorFolderNode]],
)
async def list_folders(
    connector_id: uuid.UUID,
    principal: Principal = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return ok(
        await connector_service.get_folders(
            db, workspace_id=principal.workspace_id, connector_id=connector_id
        )
    )


@router.post("/connectors/{connector_id}/sync", response_model=ApiResponse[SyncResponse])
async def sync_connector(
    connector_id: uuid.UUID,
    payload: SyncRequest,
    principal: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await connector_service.sync(
        db,
        workspace_id=principal.workspace_id,
        connector_id=connector_id,
        file_ids=payload.file_ids,
    )
    return ok(SyncResponse(**result))


@router.delete("/connectors/{connector_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_connector(
    connector_id: uuid.UUID,
    principal: Principal = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    await connector_service.disconnect(
        db, workspace_id=principal.workspace_id, connector_id=connector_id
    )


@router.get("/connectors/google_drive/oauth/callback")
async def oauth_callback(code: str, state: str, db: AsyncSession = Depends(get_db)):
    """Google redirects the browser here after consent (no app JWT — the HMAC-signed
    `state` binds the code to a connector). Stores credentials, then returns to the app."""
    await connector_service.complete_oauth(db, code=code, state=state)
    return RedirectResponse(settings.frontend_url)
