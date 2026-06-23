"""G1: Google Drive sync fetches selected files → storage → google_drive documents →
enqueue, and is idempotent (skips already-synced files). Live DB; the Drive adapter and
the Celery enqueue are mocked (no Google creds / no broker needed). Skips offline.
"""

from __future__ import annotations

from app.connectors import google_drive
from app.models.base import SourceType
from app.models.connector import Connector, ConnectorCredential
from app.models.document import Document
from app.services import connector_service, document_service
from sqlalchemy import select


async def test_sync_fetches_creates_and_enqueues(db, workspace, monkeypatch):
    conn = Connector(
        workspace_id=workspace.id, type="google_drive", name="Google Drive", status="connected"
    )
    db.add(conn)
    await db.flush()
    db.add(ConnectorCredential(connector_id=conn.id, encrypted_refresh_token="enc"))
    await db.commit()

    enqueued: list[str] = []

    async def fake_access_token(_db, _connector):
        return "access-tok"

    async def fake_metadata(_token, fid):
        return {"id": fid, "name": f"{fid}.txt", "mimeType": "text/plain", "size": "5"}

    async def fake_download(_token, _fid):
        return b"hello"

    async def fake_enqueue(document_id):
        enqueued.append(str(document_id))

    monkeypatch.setattr(connector_service, "_access_token", fake_access_token)
    monkeypatch.setattr(google_drive, "get_metadata", fake_metadata)
    monkeypatch.setattr(google_drive, "download_file", fake_download)
    monkeypatch.setattr(document_service, "_enqueue", fake_enqueue)

    result = await connector_service.sync(
        db, workspace_id=workspace.id, connector_id=conn.id, file_ids=["A", "B"]
    )
    assert result["status"] == "completed"

    docs = (
        (await db.execute(select(Document).where(Document.workspace_id == workspace.id)))
        .scalars()
        .all()
    )
    assert len(docs) == 2
    assert all(d.source_type == SourceType.google_drive.value for d in docs)
    assert {d.external_document_id for d in docs} == {"A", "B"}
    assert len(enqueued) == 2  # each fetched file is queued for the ingestion pipeline

    # Re-syncing the same files is idempotent — no duplicates (v3 §10.3 skip logic).
    await connector_service.sync(
        db, workspace_id=workspace.id, connector_id=conn.id, file_ids=["A", "B"]
    )
    docs_after = (
        (await db.execute(select(Document).where(Document.workspace_id == workspace.id)))
        .scalars()
        .all()
    )
    assert len(docs_after) == 2
