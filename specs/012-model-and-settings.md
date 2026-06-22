# Spec 012 — Model & settings

- **Status:** Not started
- **Spec source:** v3 §11, §15 · timeline: Phase 3 (workspace/API/connector settings endpoints)
- **Success criteria covered:** — (supporting)
- **Owner:** <unassigned>

## Context / intent

Read-only model info + editable workspace settings. The chat model is the **one** runtime-configurable model.

## In scope

- `GET /api/model` → `ModelConfig` (read-only): parser (Docling), embedding (`text-embedding-3-small`, 1536), chat (workspace `chat_model`), vector (Qdrant HNSW), graph (Neo4j).
- `GET /api/settings` → `WorkspaceSettings`; `PATCH /api/settings` (admin) updates: `workspace_name`, `organization_name`, `auto_start_ingestion`, `chat_model ∈ {gpt-4o-mini, gpt-4o}`, `chat_top_k (5–25)`, `min_similarity_threshold (0.5–0.9)`, `rest_api_enabled`, `default_rate_limit_per_minute`. `sync_mode` fixed `manual`; `read_only` block reflects fixed engines.

## Out of scope / deferred

- Runtime embedding/parser switching (§11.3, Phase 3). Reranker/GraphRAG config (Phase 2/3).

## Endpoints / modules touched

- `app/api/{model,settings}.py`, `app/services/settings_service.py`, `app/schemas/settings.py`.

## Acceptance criteria

1. `GET /api/model` returns the exact `ModelConfig` shape; no edit controls (read-only).
2. `PATCH /api/settings` validates ranges (`top_k` 5–25, `min_similarity` 0.5–0.9, `chat_model` enum) and persists; non-admin → `403`.
3. Changing `chat_model` takes effect on the next chat (no re-embedding); embedding model is immutable.

## Dependencies

- 001.

## Relevant rules

- `.claude/rules/api.md`, `.claude/rules/ai-gateway.md`

## Traceability

| AC | Code path(s) | Test path(s) | Status |
|---|---|---|---|
| 1 | `app/api/model.py` | `tests/test_model.py` | ☐ |
| 2 | `app/services/settings_service.py` | `tests/test_settings.py` | ☐ |
