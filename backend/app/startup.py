"""Idempotent startup init. Tolerates not-yet-ready dependencies (logged, not fatal).

Qdrant collections are created lazily per-workspace on first upsert/search, so the
only global init is Neo4j constraints/indexes.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.services import graph_store

log = get_logger(__name__)


async def on_startup() -> None:
    await graph_store.ensure_constraints()  # best-effort; tolerates an unready Neo4j
    log.info("startup_complete")
