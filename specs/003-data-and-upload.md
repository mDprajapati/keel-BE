# Spec 003 — Data & upload

- **Status:** Not started
- **Spec source:** v3 §8 · timeline: Phase 1 (object storage, upload & ingest API, document model)
- **Success criteria covered:** §21.4 (and §21.6 tag editing)
- **Owner:** <unassigned>

## Context / intent

Accept uploads (incl. multipart for >10 MB), store raw bytes in object storage, create the `documents` row, enqueue ingestion, and serve the paginated data table. Tag editing + delete + reprocess.

## In scope

- Storage adapter (`local` + `s3`), path `workspaces/{ws}/raw/{doc}/{filename}`.
- `POST /api/ingest/file` (multipart, MIME-vs-bytes check → `INVALID_FILE_TYPE`), `POST /api/ingest/file/part` (5 MB parts, assembled in storage). Returns `{document_id, job_id, status:"queued"}`.
- `GET /api/documents` — server-side pagination (`page`/`limit` ≤200), filters (`search`, `status`, `source_type`, `file_type`, `tag`), sort (`uploaded_at`|`name`|`chunk_count`). Returns `Paginated<KeelDocument>`.
- `PATCH /api/documents/{id}/tags` (metadata only, no reprocess), `DELETE /api/documents/{id}`, `POST /api/documents/{id}/reprocess` (re-enqueue).
- `documents` model with `content_hash`/`duplicate_of` skeleton columns.

## Out of scope / deferred

- SHA-256 dedup enforcement (§9.2). Document Detail View (§8.5). Virus scan (Phase 2).

## Endpoints / modules touched

- `app/api/{documents,ingest}.py`, `app/services/{storage,document_service}.py`, `app/models/document.py`, `app/schemas/document.py`.

## Acceptance criteria

1. **(§21.4)** Upload returns `202`-style job immediately with `ingestion_status:queued`; a `documents` row exists; large files use parts.
2. MIME mismatch (bytes vs declared) → `INVALID_FILE_TYPE`.
3. `GET /api/documents` paginates/filters/sorts server-side and returns exact `KeelDocument` shape; **only the caller's `workspace_id`** rows.
4. **(§21.6)** Tag edit persists (≤20, lowercased) without reprocessing; reprocess re-enqueues.

## Dependencies

- 001 (auth/workspace), 004 (pipeline consumes the queued doc).

## Relevant rules

- `.claude/rules/database.md`, `.claude/rules/api.md`

## Traceability

| AC | Code path(s) | Test path(s) | Status |
|---|---|---|---|
| 1,2 | `app/api/ingest.py`, `app/services/storage.py` | `tests/test_upload.py` | ☐ |
| 3 | `app/api/documents.py` | `tests/test_documents.py` | ☐ |
| 4 | `app/services/document_service.py` | `tests/test_documents.py::test_tags` | ☐ |
