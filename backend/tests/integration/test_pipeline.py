"""Pipeline integration tests (live stores; OpenAI mocked).

Regression: the worker logged `sqlalchemy.orm.exc.StaleDataError: UPDATE on documents
expected 1 row, 0 matched` — a concurrent DELETE removed the documents row while the
429-slowed pipeline was mid-flight, and the next commit crashed the worker. The
pipeline must abort cleanly instead.
"""

from __future__ import annotations

import uuid

from app.core.database import get_session_factory
from app.models.base import IngestionStatus
from app.models.document import Document
from app.models.ingestion import IngestionJob
from app.services import parsing
from ingestion import worker_flow
from sqlalchemy import delete


class _BytesStorage:
    """Stand-in storage so `data` is truthy and `parse_document` is invoked."""

    def get_bytes(self, path: str) -> bytes:
        return b"midflight-doc-bytes"


async def _seed_queued_doc(db, ws_id: uuid.UUID) -> uuid.UUID:
    doc = Document(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        name="midflight",
        filename="midflight.txt",
        file_type="txt",
        source_type="api_push",
        size_bytes=3,
        storage_path="workspaces/x/raw/x/midflight.txt",
        ingestion_status=IngestionStatus.queued.value,
        uploaded_by="itest",
    )
    db.add(doc)
    await db.flush()
    db.add(IngestionJob(document_id=doc.id, workspace_id=ws_id, steps_total=16))
    await db.commit()
    return doc.id


async def test_run_aborts_when_document_deleted_midflight(db, workspace, monkeypatch):
    doc_id = await _seed_queued_doc(db, workspace.id)

    async def _delete_then_parse(*args, **kwargs):
        # Simulate a concurrent DELETE /documents/{id} in a separate committed txn.
        async with get_session_factory()() as other:
            await other.execute(delete(IngestionJob).where(IngestionJob.document_id == doc_id))
            await other.execute(delete(Document).where(Document.id == doc_id))
            await other.commit()
        return parsing.ParsedDocument()

    monkeypatch.setattr(worker_flow, "get_storage", lambda: _BytesStorage())
    monkeypatch.setattr(worker_flow, "parse_document", _delete_then_parse)

    # Before the fix this escaped as StaleDataError (worker crash); now it returns.
    await worker_flow.run(doc_id)

    db.expunge_all()
    assert await db.get(Document, doc_id) is None
