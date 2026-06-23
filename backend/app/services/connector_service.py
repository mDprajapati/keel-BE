"""Connector service (v3 §10). Google Drive is the primary connector; OneDrive is
a coming-soon stub. Real OAuth + Drive listing/fetch live behind the `connectors`
extra (timeline RISK item) — this module implements the keel-UI contract and the
DB/state machine, with clearly marked TODOs where the live Google API plugs in."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors import google_drive
from app.core.config import settings
from app.core.errors import BadRequestError, InvalidFileTypeError, NotFoundError
from app.core.logging import get_logger
from app.models.base import ConnectorStatus, ConnectorType, SourceType
from app.models.connector import Connector, ConnectorCredential
from app.models.document import Document
from app.schemas.connector import ConnectorFolderNode
from app.services import document_service
from app.stores.storage import build_path, get_storage

log = get_logger(__name__)


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
    """Begin OAuth. For Google Drive, return Google's consent URL when creds are
    configured (the browser completes the handshake at the callback). Without creds, or
    for the coming-soon OneDrive, report not-connected."""
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
    if (
        conn_type == ConnectorType.google_drive.value
        and connector.status != ConnectorStatus.coming_soon.value
        and google_drive.is_configured()
    ):
        return {"authorization_url": google_drive.build_auth_url(str(connector.id))}
    return {"connected": False}


async def complete_oauth(db: AsyncSession, *, code: str, state: str) -> uuid.UUID:
    """OAuth callback: verify the signed state, exchange the code, store the encrypted
    refresh token, mark the connector connected. Returns the connector id so the
    callback can redirect the browser back to that connector's card."""
    connector_id = google_drive.verify_state(state)
    if connector_id is None:
        raise BadRequestError("Invalid OAuth state", error_code="INVALID_OAUTH_STATE")
    connector = await db.get(Connector, uuid.UUID(connector_id))
    if connector is None:
        raise NotFoundError("Connector not found")
    tokens = await google_drive.exchange_code(code)
    cred = (
        await db.execute(
            select(ConnectorCredential).where(ConnectorCredential.connector_id == connector.id)
        )
    ).scalar_one_or_none()
    if cred is None:
        cred = ConnectorCredential(connector_id=connector.id)
        db.add(cred)
    refresh = tokens.get("refresh_token")
    if refresh:
        cred.encrypted_refresh_token = google_drive.encrypt_token(refresh)
    cred.scopes = " ".join(google_drive.SCOPES)
    connector.status = ConnectorStatus.connected.value
    connector.last_synced_at = connector.last_synced_at or datetime.now(UTC)
    await db.commit()
    return connector.id


async def _access_token(db: AsyncSession, connector: Connector) -> str | None:
    """A fresh Drive access token from the stored (encrypted) refresh token, or None if
    the connector has not completed OAuth yet."""
    cred = (
        await db.execute(
            select(ConnectorCredential).where(ConnectorCredential.connector_id == connector.id)
        )
    ).scalar_one_or_none()
    if cred is None or not cred.encrypted_refresh_token:
        return None
    return await google_drive.refresh_access_token(
        google_drive.decrypt_token(cred.encrypted_refresh_token)
    )


async def get_folders(
    db: AsyncSession, *, workspace_id: uuid.UUID, connector_id: uuid.UUID
) -> list[ConnectorFolderNode]:
    connector = await _get(db, workspace_id, connector_id)
    token = await _access_token(db, connector)
    if token is None:
        # The card only exposes "Browse" once connected, so reaching here means the
        # stored Drive credentials are missing/expired. Surface an actionable error
        # instead of an empty list, which the UI would render as "No files found"
        # and wrongly suggest the user's Drive is empty (v3 §10.2, §16.2).
        raise BadRequestError(
            "Google Drive is not authorized. Please reconnect the connector.",
            error_code="CONNECTOR_NOT_AUTHORIZED",
        )
    items = await google_drive.list_files(token)
    return [
        ConnectorFolderNode(
            id=item["id"],
            name=item.get("name", ""),
            type="folder" if item.get("mimeType") == google_drive.FOLDER_MIME else "file",
            mime_type=item.get("mimeType"),
        )
        for item in items
    ]


async def _already_synced(db: AsyncSession, workspace_id: uuid.UUID, external_id: str) -> bool:
    return (
        await db.execute(
            select(Document.id).where(
                Document.workspace_id == workspace_id,
                Document.external_document_id == external_id,
            )
        )
    ).first() is not None


async def sync(
    db: AsyncSession, *, workspace_id: uuid.UUID, connector_id: uuid.UUID, file_ids: list[str]
) -> dict:
    """Fetch the selected Drive files → object storage → google_drive documents → enqueue
    ingestion (same 16-step pipeline as upload). Skips files already synced, of an
    unsupported type, or over the 500 MB limit (v3 §10.3). Best-effort per file."""
    connector = await _get(db, workspace_id, connector_id)
    if connector.type != ConnectorType.google_drive.value:
        raise BadRequestError("Sync is only supported for Google Drive", error_code="UNSUPPORTED")
    token = await _access_token(db, connector)
    if token is None:
        raise BadRequestError("Connector is not authorized", error_code="CONNECTOR_NOT_AUTHORIZED")

    created = 0
    skipped = 0
    failed = 0
    for fid in file_ids:
        try:
            if await _already_synced(db, workspace_id, fid):
                skipped += 1  # skip same external_document_id (v3 §10.3)
                continue
            meta = await google_drive.get_metadata(token, fid)
            name = meta.get("name") or fid
            if int(meta.get("size") or 0) > settings.max_upload_bytes:
                log.info("connector_skip_oversize", file_id=fid)
                skipped += 1
                continue
            try:
                file_type = document_service.detect_file_type(name)
            except InvalidFileTypeError:
                # e.g. Google-native Docs/Sheets/Slides whose name has no usable
                # extension and can't be downloaded with alt=media (v3 §10.3).
                log.info("connector_skip_mime", file_id=fid, name=name)
                skipped += 1
                continue
            data = await google_drive.download_file(token, fid)
            doc_id = uuid.uuid4()
            path = build_path(str(workspace_id), str(doc_id), name)
            get_storage().save_bytes(path, data)
            await document_service.create_queued_document(
                db,
                document_id=doc_id,
                workspace_id=workspace_id,
                name=name,
                filename=name,
                file_type=file_type,
                source_type=SourceType.google_drive.value,
                size_bytes=len(data),
                storage_path=path,
                mime_type=meta.get("mimeType"),
                uploaded_by="Connector sync",
                connector_id=connector.id,
                external_document_id=fid,
            )
            created += 1
        except Exception as exc:  # noqa: BLE001 — per-file best-effort; keep syncing
            log.warning("connector_file_failed", file_id=fid, error=str(exc))
            failed += 1

    connector.last_synced_at = datetime.now(UTC)
    connector.last_sync_document_count = created
    await db.commit()
    log.info(
        "connector_sync",
        connector_id=str(connector_id),
        requested=len(file_ids),
        created=created,
        skipped=skipped,
        failed=failed,
    )
    # Report per-file outcomes so the UI can distinguish "1 file ingested" from a
    # request where everything was skipped/failed (which previously surfaced as a
    # bare "completed" with a confusing "0 documents fetched").
    return {
        "status": "completed",
        "requested": len(file_ids),
        "created": created,
        "skipped": skipped,
        "failed": failed,
    }


async def disconnect(db: AsyncSession, *, workspace_id: uuid.UUID, connector_id: uuid.UUID) -> None:
    connector = await _get(db, workspace_id, connector_id)
    if connector.status != ConnectorStatus.coming_soon.value:
        connector.status = ConnectorStatus.disconnected.value
        connector.last_synced_at = None
        connector.last_sync_document_count = None
    await db.commit()
