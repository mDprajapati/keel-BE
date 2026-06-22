# Spec 011 — Dashboard

- **Status:** Not started
- **Spec source:** v3 §7 · timeline: Phase 3 (dashboard metrics endpoint, 60s SWR cache)
- **Success criteria covered:** §21.3
- **Owner:** <unassigned>

## Context / intent

One endpoint feeding the dashboard: counters, recent feeds, connector sync status, and pipeline health.

## In scope

- `GET /api/dashboard` → `DashboardResponse` (exact `keel-UI` shape): `metrics{documents_uploaded, sources_connected, documents_processed, chunks_generated, embeddings_created, ai_tags_generated, chat_queries_this_month, api_calls_this_month}`, `recent_activity[≤20]`, `recent_documents[≤10]`, `connector_sync[]`, `pipeline_health{sources,ingestion,storage,chat,rest_api}`.
- 60s stale-while-revalidate cache. Counters computed workspace-scoped.
- Lightweight `api_call_log` for monthly REST counts + chat-query counts.

## Out of scope / deferred

- Advanced audit logs (Phase 2).

## Endpoints / modules touched

- `app/api/dashboard.py`, `app/services/dashboard_service.py`.

## Acceptance criteria

1. **(§21.3)** `GET /api/dashboard` returns all counters + feeds for the caller's workspace within the latency budget (cached 60s).
2. `pipeline_health` reflects live state (e.g. `processing` when a doc is mid-ingest).
3. Shape matches `keel-UI` `DashboardResponse` exactly; counts are workspace-scoped.

## Dependencies

- 003, 004 (data to count).

## Relevant rules

- `.claude/rules/api.md`, `.claude/rules/database.md`

## Traceability

| AC | Code path(s) | Test path(s) | Status |
|---|---|---|---|
| 1,3 | `app/services/dashboard_service.py` | `tests/test_dashboard.py` | ☐ |
