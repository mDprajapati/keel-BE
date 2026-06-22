"""Connector service (v3 §10). Google Drive is the primary connector; OneDrive is
a coming-soon stub. Real OAuth + Drive listing/fetch live behind the `connectors`
extra (timeline RISK item) — this module implements the keel-UI contract and the
DB/state machine, with clearly marked TODOs where the live Google API plugs in."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.logging import get_logger
from app.models.base import ConnectorStatus, ConnectorType, IngestionStatus, SourceType
from app.models.connector import Connector
from app.models.document import Document
from app.schemas.admin import ConnectorFolderNode

log = get_logger(__name__)

# Sample tree returned until the live Drive folder listing is wired (TODO).
_SAMPLE_FOLDERS = [
    ConnectorFolderNode(
        id="f_root",
        name="Drive",
        type="folder",
        children=[
            ConnectorFolderNode(
                id="f_finance",
                name="Finance",
                type="folder",
                children=[
                    ConnectorFolderNode(
                        id="file_1",
                        name="Q4 Forecast.xlsx",
                        type="file",
                        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    ),
                    ConnectorFolderNode(
                        id="file_2",
                        name="Budget Memo.pdf",
                        type="file",
                        mime_type="application/pdf",
                    ),
                ],
            ),
            ConnectorFolderNode(
                id="file_5", name="README.txt", type="file", mime_type="text/plain"
            ),
        ],
    )
]


async def ensure_default_connectors(db: AsyncSession, workspace_id: uuid.UUID) -> None:
    """Seed the GD + OneDrive cards for a workspace if absent (matches keel-UI)."""
    existing = (
        (await db.execute(select(Connector).where(Connector.workspace_id == workspace_id)))
        .scalars()
        .all()
    )
    have = {c.type for c in existing}
    if ConnectorType.google_drive.value not in have:
        db.add(
            Connector(
                workspace_id=workspace_id,
                type=ConnectorType.google_drive.value,
                name="Google Drive",
                status=ConnectorStatus.disconnected.value,
            )
        )
    if ConnectorType.onedrive.value not in have:
        db.add(
            Connector(
                workspace_id=workspace_id,
                type=ConnectorType.onedrive.value,
                name="OneDrive",
                status=ConnectorStatus.coming_soon.value,
            )
        )
    await db.commit()


async def list_connectors(db: AsyncSession, *, workspace_id: uuid.UUID) -> list[Connector]:
    await ensure_default_connectors(db, workspace_id)
    return list(
        (await db.execute(select(Connector).where(Connector.workspace_id == workspace_id)))
        .scalars()
        .all()
    )


async def _get(db, workspace_id, connector_id) -> Connector:
    c = await db.get(Connector, connector_id)
    if c is None or c.workspace_id != workspace_id:
        raise NotFoundError("Connector not found")
    return c


async def start_oauth(db: AsyncSession, *, workspace_id: uuid.UUID, conn_type: str) -> dict:
    """Begin OAuth. TODO: return a real Google authorization_url when creds are set.
    Until then, demo flow marks Google Drive connected; OneDrive stays coming-soon."""
    await ensure_default_connectors(db, workspace_id)
    connector = (
        await db.execute(
            select(Connector).where(
                Connector.workspace_id == workspace_id, Connector.type == conn_type
            )
        )
    ).scalar_one_or_none()
    if connector is None:
        raise NotFoundError("Connector not found")
    if connector.status == ConnectorStatus.coming_soon.value:
        return {"connected": False}
    # TODO: real auth-code flow → store encrypted refresh token in connector_credentials.
    connector.status = ConnectorStatus.connected.value
    connector.last_synced_at = connector.last_synced_at or datetime.now(UTC)
    await db.commit()
    return {"connected": True}


async def get_folders(
    db: AsyncSession, *, workspace_id: uuid.UUID, connector_id: uuid.UUID
) -> list[ConnectorFolderNode]:
    await _get(db, workspace_id, connector_id)
    return _SAMPLE_FOLDERS  # TODO: live Drive folder listing


async def sync(
    db: AsyncSession, *, workspace_id: uuid.UUID, connector_id: uuid.UUID, file_ids: list[str]
) -> dict:
    """Create document records for the selected files and (when bytes are fetched)
    enqueue ingestion. TODO: fetch real bytes via the Drive API → storage → enqueue;
    skip already-synced (external_id+mtime), unsupported MIME, >500 MB (v3 §10.3)."""
    connector = await _get(db, workspace_id, connector_id)
    created = 0
    for fid in file_ids:
        exists = (
            await db.execute(
                select(Document).where(
                    Document.workspace_id == workspace_id, Document.external_document_id == fid
                )
            )
        ).scalar_one_or_none()
        if exists is not None:
            continue  # skip already-synced (external_document_id)
        db.add(
            Document(
                workspace_id=workspace_id,
                name=f"{fid}",
                filename=f"{fid}.pdf",
                file_type="pdf",
                source_type=SourceType.google_drive.value,
                connector_id=connector.id,
                external_document_id=fid,
                ingestion_status=IngestionStatus.queued.value,
                uploaded_by="Connector sync",
                tags=["synced"],
            )
        )
        created += 1
    connector.last_synced_at = datetime.now(UTC)
    connector.last_sync_document_count = created
    await db.commit()
    log.info("connector_sync", connector_id=str(connector_id), files=len(file_ids), created=created)
    # NOTE: ingestion enqueue happens once real bytes are fetched to storage.
    return {"status": "completed"}


async def disconnect(db: AsyncSession, *, workspace_id: uuid.UUID, connector_id: uuid.UUID) -> None:
    connector = await _get(db, workspace_id, connector_id)
    if connector.status != ConnectorStatus.coming_soon.value:
        connector.status = ConnectorStatus.disconnected.value
        connector.last_synced_at = None
        connector.last_sync_document_count = None
    await db.commit()
