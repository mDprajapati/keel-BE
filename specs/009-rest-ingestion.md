# Spec 009 — REST ingestion API

- **Status:** Not started
- **Spec source:** v3 §13.2 · timeline: Phase 1 (ingest file/part/text/record, status)
- **Success criteria covered:** §21.10
- **Owner:** <unassigned>

## Context / intent

External-system ingestion through the **same** pipeline as upload. Dual auth; ingestion requires `read_write` scope.

## In scope

- `POST /api/ingest/file` (multipart) + `POST /api/ingest/file/part` (chunked).
- `POST /api/ingest/text` `{content≤5MB, title, source_label?, tags?[]}`.
- `POST /api/ingest/record` `{record_type, record_id, fields, source_label?, tags?[]}` → rendered to text.
- `GET /api/ingest/status/{job_id}` → `{job_id, document_id, status, current_step, steps_completed, steps_total, error, completed_at}` (`duplicate` retained, never produced).
- All create `documents(source_type=api_push)` and enqueue; return `{document_id, job_id, status:"queued"}`.

## Out of scope / deferred

- Dedup `duplicate` outcome (§9.2).

## Endpoints / modules touched

- `app/api/ingest.py`, `app/services/document_service.py`, `app/schemas/ingest.py`.

## Acceptance criteria

1. **(§21.10)** `POST /api/ingest/text` with an API key returns a queued job; `GET /api/ingest/status/{job_id}` reaches `completed` after processing.
2. `read_only` key on any ingest endpoint → `403`; missing/invalid key → `401`.
3. `text`/`record`/`file` all converge on the same pipeline + response shape.
4. Status endpoint p95 < 300 ms (reads DB only).

## Dependencies

- 004 (pipeline), 010 (API keys/scope).

## Relevant rules

- `.claude/rules/api.md`, `.claude/rules/security.md`

## Traceability

| AC | Code path(s) | Test path(s) | Status |
|---|---|---|---|
| 1 | `app/api/ingest.py` | `tests/test_rest_ingest.py` | ☐ |
| 2 | `app/core/deps.py` | `tests/test_rest_ingest.py::test_scope` | ☐ |
