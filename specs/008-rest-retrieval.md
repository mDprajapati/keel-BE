# Spec 008 — REST retrieval API

- **Status:** Not started
- **Spec source:** v3 §13.1 · timeline: Phase 2 (Retrieval REST: search, context, evidence; non-stream chat)
- **Success criteria covered:** §21.9
- **Owner:** <unassigned>

## Context / intent

The public, dual-auth retrieval surface third-party tools call (and the app's REST explorer uses with the session). Same retrieval core as chat.

## In scope

- `POST /api/search` `{query, top_k?≤25, min_score?, filter_source_type?[]}` → `{results[], query_embedding_ms, search_ms}`.
- `POST /api/context` `{query, max_tokens?≤32000, top_k?}` → `{context, evidence[], token_count, truncated}`.
- `GET /api/evidence/{chunk_id}` → full chunk (`chunk_text` + `metadata`).
- `POST /api/chat` non-stream → `{answer, confidence, evidence[], conversation_id}`.
- Dual auth (`get_principal`) + rate limit on API-key calls; mandatory `workspace_id` filter.

## Out of scope / deferred

- MCP server (§13.5) — placeholder only. Role/doc-level result filtering (Phase 2).

## Endpoints / modules touched

- `app/api/{search,chat}.py`, `app/services/retrieval_service.py`, `app/schemas/search.py`.

## Acceptance criteria

1. **(§21.9)** Same question answered via `POST /api/chat` with a valid API key returns structured `{answer, confidence, evidence}`; via `POST /api/search` returns ranked chunks (name, excerpt, score, section_ref) — all workspace-scoped.
2. `context` returns assembled text + `token_count` + `truncated` flag.
3. A request with no JWT and no API key → `401`; an over-limit API key → `429` + `Retry-After`.
4. Results never cross workspaces (isolation).
5. p95 latency targets documented; response shapes match `keel-UI`.

## Dependencies

- 005 (retrieval core), 010 (API keys + rate limit).

## Relevant rules

- `.claude/rules/api.md`, `.claude/rules/ai-gateway.md`

## Traceability

| AC | Code path(s) | Test path(s) | Status |
|---|---|---|---|
| 1 | `app/api/search.py`, `app/api/chat.py` | `tests/test_rest_retrieval.py` | ☐ |
| 3 | `app/core/{deps,rate_limit}.py` | `tests/test_rate_limit.py` | ☐ |
