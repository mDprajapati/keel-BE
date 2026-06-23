"""Billing-proof pipeline test (the AI timeline's "ingestion pipeline coroutine test").

With the OpenAI-backed steps mocked at the adapter boundary (embed / tagging / NER) and
the vector + graph stores stubbed, a real document runs parse → chunk → embed → graph →
finalize to ingestion_status=completed against a real Postgres. Parsing and chunking run
for real; only the external calls are mocked. This proves the pipeline is correct
end-to-end EXCEPT the actual OpenAI request — i.e. once OpenAI billing is enabled, the
embed/tag/NER calls return and ingestion completes automatically, with no code changes.

Live DB; skips offline. (token_usage logging is covered by tests/test_token_usage_cost.py;
embed/call_llm are the only OpenAI touchpoints, both routed through that logged gateway.)
"""

from __future__ import annotations

import uuid

from app.models.base import EmbeddingStatus, IngestionStatus
from app.models.document import Document, DocumentChunk
from app.models.ingestion import IngestionJob
from ingestion import worker_flow
from sqlalchemy import select


class _TextStorage:
    def get_bytes(self, path: str) -> bytes:
        return b"Acme Corp partnered with Globex on Project Atlas in 2024.\n\n" * 80


async def _seed_queued_doc(db, ws_id: uuid.UUID) -> uuid.UUID:
    doc = Document(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        name="deal-memo",
        filename="deal-memo.txt",
        file_type="txt",
        source_type="manual_upload",
        size_bytes=10,
        storage_path="workspaces/x/raw/x/deal-memo.txt",
        ingestion_status=IngestionStatus.queued.value,
        uploaded_by="itest",
    )
    db.add(doc)
    await db.flush()
    db.add(IngestionJob(document_id=doc.id, workspace_id=ws_id, steps_total=16))
    await db.commit()
    return doc.id


async def test_pipeline_completes_with_mocked_openai(db, workspace, monkeypatch):
    doc_id = await _seed_queued_doc(db, workspace.id)

    async def fake_embed(texts, **kwargs):
        return [[0.1] * 1536 for _ in texts]

    async def fake_tags(text, **kwargs):
        return ["finance", "deal"]

    async def fake_ner(text, **kwargs):
        return ([], [])

    async def fake_graph(**kwargs):
        return None

    monkeypatch.setattr(worker_flow, "get_storage", lambda: _TextStorage())
    monkeypatch.setattr(worker_flow, "embed", fake_embed)
    monkeypatch.setattr(worker_flow.tagging, "generate_tags", fake_tags)
    monkeypatch.setattr(worker_flow.ner, "extract", fake_ner)
    monkeypatch.setattr(worker_flow.vector_store, "upsert", lambda ws, points: None)
    monkeypatch.setattr(worker_flow.graph_store, "upsert_graph", fake_graph)

    await worker_flow.run(doc_id)

    db.expunge_all()
    doc = await db.get(Document, doc_id)
    assert doc.ingestion_status == IngestionStatus.completed.value
    assert doc.embedding_status == EmbeddingStatus.completed.value
    assert (doc.chunk_count or 0) > 0

    chunks = (
        (await db.execute(select(DocumentChunk).where(DocumentChunk.document_id == doc_id)))
        .scalars()
        .all()
    )
    assert chunks
    assert all(c.workspace_id == workspace.id for c in chunks)  # tenant tag on every chunk
