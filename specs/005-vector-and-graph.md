# Spec 005 — Vector & graph storage

- **Status:** Not started
- **Spec source:** v3 §9.4–§9.5 · timeline: AI (Qdrant adapter, Neo4j adapter, NER, graph mapping)
- **Success criteria covered:** §21.5
- **Owner:** <unassigned>

## Context / intent

Embed chunks → Qdrant; extract entities/relationships → Neo4j. Both behind thin adapters. Graph is best-effort.

## In scope

- `vector_store.py` (Qdrant): per-workspace collection init (HNSW `m=16, ef_construction=64`, cosine, 1536-d); `upsert(points)` (id=`chunk_id`, payload `{workspace_id, document_id, chunk_index, section_ref, source_type, tags}`); `search(query_vec, workspace_id, top_k, score_threshold)` with **mandatory `workspace_id` payload filter**.
- Pipeline steps 11–12: batch-embed (100) via `llm_gateway.embed`, retry 3× → `embedding_failed`, upsert vectors.
- `graph_store.py` (Neo4j): MERGE entity nodes (dedup `canonical_name+entity_type+workspace_id`), MERGE edges (`document_id, chunk_id, confidence_score`), constraints+indexes on startup; parameterized Cypher only; 1-hop `entity→chunks` lookup.
- `ner.py`: LLM NER for 7 entity types (incl. **INDUSTRY**) + 4 relationships (`MENTIONS, AUTHORED_BY, BELONGS_TO, REFERENCES`). Pipeline steps 13–14.
- `startup.py`: idempotent collection + constraint creation, tolerant of a not-ready service.

## Out of scope / deferred

- Multi-hop GraphRAG traversal (§9.5, Phase 3). Reranker (Phase 2).

## Endpoints / modules touched

- `app/services/{vector_store,graph_store}.py`, `app/services/ai/ner.py`, `app/startup.py`, `app/services/ingestion/steps.py`.

## Acceptance criteria

1. **(§21.5)** After ingest, chunks are searchable in Qdrant and entity nodes/edges exist in Neo4j.
2. **Every** `vector_store.search` includes the `workspace_id` filter — a search for workspace A never returns workspace B points (isolation test).
3. Entities dedup within a workspace (same name+type reuses the node, adds an edge); INDUSTRY is extracted.
4. Embedding batches of 100; failed batch retried 3× then `embedding_status=failed`.
5. Graph/NER errors are logged and do **not** fail the document.

## Dependencies

- 004 (chunks), 013 (embed/NER via gateway).

## Relevant rules

- `.claude/rules/ai-gateway.md`, `.claude/rules/database.md`, `.claude/rules/testing.md`

## Traceability

| AC | Code path(s) | Test path(s) | Status |
|---|---|---|---|
| 2 | `app/services/vector_store.py` | `tests/test_isolation.py` | ☐ |
| 3 | `app/services/graph_store.py`, `app/services/ai/ner.py` | `tests/test_graph.py` | ☐ |
