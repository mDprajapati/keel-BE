"""Integration fixtures — exercise the pipeline/retrieval against the LIVE dev stack
(Postgres/Qdrant/Neo4j/MinIO on published localhost ports), mocking only the OpenAI
provider (AGENTS rule: 'mock at the adapter boundary'). Auto-skipped when the stores
are unreachable so the offline unit suite stays green (timeline: 'pytest green on a
clean checkout'). Each test isolates itself in a throwaway workspace and cleans up.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from app.core.config import settings
from app.core.database import dispose_engine, get_session_factory
from app.models.document import Document, DocumentChunk
from app.models.ingestion import IngestionError, IngestionJob
from app.models.organization import Organization, Workspace
from sqlalchemy import delete


def _db_reachable() -> bool:
    """True only if the DB is reachable AND usable (auth succeeds) — a real connect, so
    a local Postgres merely occupying the port can't make integration tests error
    instead of skip."""
    try:
        import psycopg

        with psycopg.connect(
            settings.sync_database_url.replace("+psycopg", ""), connect_timeout=2
        ) as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


_DB_OK = _db_reachable()


@pytest.fixture(autouse=True)
def _require_stores() -> None:
    if not _DB_OK:
        pytest.skip("live stores unreachable — integration tests skipped")


@pytest_asyncio.fixture
async def db():
    async with get_session_factory()() as session:
        yield session
    # Fresh engine per test: asyncpg connections are not portable across the
    # per-test event loop pytest-asyncio creates.
    await dispose_engine()


async def _cleanup_workspace(session, ws_id: uuid.UUID, org_id: uuid.UUID) -> None:
    for stmt in (
        delete(DocumentChunk).where(DocumentChunk.workspace_id == ws_id),
        delete(IngestionError).where(IngestionError.workspace_id == ws_id),
        delete(IngestionJob).where(IngestionJob.workspace_id == ws_id),
        delete(Document).where(Document.workspace_id == ws_id),
        delete(Workspace).where(Workspace.id == ws_id),
        delete(Organization).where(Organization.id == org_id),
    ):
        await session.execute(stmt)
    await session.commit()


@pytest_asyncio.fixture
async def workspace(db):
    org = Organization(name="itest-org", slug=f"itest-{uuid.uuid4().hex[:12]}")
    db.add(org)
    await db.flush()
    ws = Workspace(organization_id=org.id, name="itest-ws")
    db.add(ws)
    await db.commit()
    yield ws
    try:
        await _cleanup_workspace(db, ws.id, org.id)
    except Exception:
        await db.rollback()
