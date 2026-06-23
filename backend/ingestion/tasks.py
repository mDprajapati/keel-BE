"""Celery ingestion task — runs the resumable pipeline; retries transient failures.

Tests should call `worker_flow.run(...)` directly, not `.delay()` (AGENTS testing rule).
"""

from __future__ import annotations

import asyncio

from app.core.logging import get_logger

from ingestion import worker_flow
from ingestion.worker import celery

log = get_logger(__name__)

_loop: asyncio.AbstractEventLoop | None = None


def _run(coro):
    """Run a coroutine on a persistent per-worker event loop.

    Celery (prefork) runs tasks synchronously in a long-lived worker process. Using
    ``asyncio.run`` per task creates — and closes — a fresh loop each time, while the
    module-global async DB engine (app.database) stays bound to the FIRST loop. asyncpg
    connections are not portable across event loops, so the 2nd document in a worker
    would raise "Event loop is closed". Reusing one loop keeps the engine valid for the
    life of the worker process.
    """
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop.run_until_complete(coro)


@celery.task(bind=True, name="ingest_document", max_retries=3, default_retry_delay=30)
def ingest_document(self, document_id: str) -> None:
    try:
        _run(worker_flow.run(document_id))
    except worker_flow.PermanentIngestionError:
        return  # already dead-lettered + marked failed
    except worker_flow.TransientIngestionError as exc:
        try:
            raise self.retry(exc=exc, countdown=30 * (2**self.request.retries))
        except self.MaxRetriesExceededError:
            log.error("ingest_retries_exhausted", document_id=document_id, error=str(exc))
            _run(worker_flow.mark_failed(document_id, step="retry", error=str(exc)))
