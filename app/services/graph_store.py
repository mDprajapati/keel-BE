"""Neo4j adapter (v3 §9.5, AI timeline).

Parameterized Cypher only. Entity nodes deduped by canonical_name+entity_type+
workspace_id; edges carry document_id, chunk_id, confidence_score. All operations
are best-effort — callers log and continue on failure (graph never blocks chat/
ingest). Async driver built lazily (import-safe without Neo4j).
"""

from __future__ import annotations

import uuid
from typing import Any

from app.config import settings
from app.logging import get_logger
from app.services.ai.ner import Entity, Relation

log = get_logger(__name__)

_driver: Any = None


def _get_driver() -> Any:
    global _driver
    if _driver is None:
        from neo4j import AsyncGraphDatabase  # lazy

        _driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
        )
    return _driver


async def ensure_constraints() -> None:
    """Idempotent constraints + indexes on startup. Tolerates an unready server."""
    cyphers = [
        "CREATE CONSTRAINT entity_unique IF NOT EXISTS "
        "FOR (e:Entity) REQUIRE (e.workspace_id, e.entity_type, e.canonical_name) IS UNIQUE",
        "CREATE INDEX entity_ws IF NOT EXISTS FOR (e:Entity) ON (e.workspace_id)",
        "CREATE INDEX entity_type_idx IF NOT EXISTS FOR (e:Entity) ON (e.entity_type)",
    ]
    try:
        async with _get_driver().session() as session:
            for cy in cyphers:
                await session.run(cy)
    except Exception as exc:  # noqa: BLE001
        log.warning("neo4j_constraints_skipped", error=str(exc))


async def upsert_graph(
    *,
    workspace_id: str | uuid.UUID,
    document_id: str | uuid.UUID,
    entities: list[Entity],
    relations: list[Relation],
    default_chunk_id: str | uuid.UUID | None = None,
) -> None:
    """MERGE entity nodes + MENTIONS/relationship edges. Best-effort."""
    if not entities and not relations:
        return
    ws, doc = str(workspace_id), str(document_id)
    try:
        async with _get_driver().session() as session:
            for e in entities:
                await session.run(
                    "MERGE (e:Entity {workspace_id:$ws, entity_type:$t, canonical_name:$n}) "
                    "MERGE (d:Document {workspace_id:$ws, document_id:$doc}) "
                    "MERGE (d)-[r:MENTIONS]->(e) "
                    "SET r.chunk_id=$chunk, r.confidence_score=coalesce(r.confidence_score,1.0)",
                    ws=ws,
                    t=e.entity_type,
                    n=e.canonical_name,
                    doc=doc,
                    chunk=str(default_chunk_id) if default_chunk_id else None,
                )
            # Map extracted entity names -> their type so relationship endpoints carry
            # entity_type and satisfy the (workspace_id, entity_type, canonical_name)
            # uniqueness constraint — otherwise a second, type-less node is created.
            type_by_name = {e.canonical_name: e.entity_type for e in entities}
            for rel in relations:
                src_type = type_by_name.get(rel.source)
                tgt_type = type_by_name.get(rel.target)
                if src_type is None or tgt_type is None:
                    # Best-effort: only link entities we actually extracted (with a type).
                    continue
                await session.run(
                    "MERGE (a:Entity {workspace_id:$ws, entity_type:$st, canonical_name:$src}) "
                    "MERGE (b:Entity {workspace_id:$ws, entity_type:$tt, canonical_name:$tgt}) "
                    "MERGE (a)-[r:REL {rel_type:$rt}]->(b) "
                    "SET r.document_id=$doc, r.confidence_score=$conf",
                    ws=ws,
                    st=src_type,
                    tt=tgt_type,
                    src=rel.source,
                    tgt=rel.target,
                    rt=rel.rel_type,
                    doc=doc,
                    conf=rel.confidence,
                )
    except Exception as exc:  # noqa: BLE001 — graph is best-effort
        log.warning("graph_upsert_failed", document_id=doc, error=str(exc))


async def find_document_ids_for_entities(
    workspace_id: str | uuid.UUID, names: list[str]
) -> list[str]:
    """1-hop lookup: documents that mention any of the named entities. Best-effort."""
    if not names:
        return []
    try:
        async with _get_driver().session() as session:
            result = await session.run(
                "MATCH (d:Document {workspace_id:$ws})-[:MENTIONS]->(e:Entity) "
                "WHERE e.canonical_name IN $names RETURN DISTINCT d.document_id AS doc LIMIT 25",
                ws=str(workspace_id),
                names=names,
            )
            return [record["doc"] async for record in result if record["doc"]]
    except Exception as exc:  # noqa: BLE001
        log.warning("graph_lookup_failed", error=str(exc))
        return []
