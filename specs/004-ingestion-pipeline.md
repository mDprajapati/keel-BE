# Spec 004 — Ingestion pipeline

- **Status:** Not started
- **Spec source:** v3 §9.1–§9.3 · timeline: Phase 1 (pipeline orchestration, chunking) + AI rows
- **Success criteria covered:** §21.5
- **Owner:** <unassigned>

## Context / intent

The resumable Celery step chain that turns a queued document into chunks (and feeds vector+graph in 005). Each step writes output + `ingestion_status` before the next, so retries resume.

## In scope

- `worker_flow.run(document_id)` resumable runner + `tasks/ingestion.py` Celery task on the `ingestion` queue.
- Steps 1–6, 10 (MVP path): retrieve → Docling parse (streaming >50 MB, page-by-page >500p, progress/50p) → extract structure/section_ref → LLM tags (first 2000 tok) → write tags → chunk → persist chunks.
- Steps 7–9 SHA-256 **skeleton** (compute/store `content_hash`, no blocking).
- Chunking (`chunking.py`): token 512/1024/overlap 64/min 50; PDF/DOCX/PPTX paragraph+sentence; XLSX/CSV row-based (header repeated, 50 rows, CSV stream >100K); TXT `\n\n`.
- Retry policy (3×, backoff, transient only), dead-letter → `ingestion_errors`.

## Out of scope / deferred

- Dedup enforcement (§9.2). Bulk reprocess queue (Phase 2). Vector/graph upsert → spec 005.

## Endpoints / modules touched

- `app/services/ingestion/{worker_flow,steps}.py`, `app/services/{parsing,chunking}.py`, `app/tasks/ingestion.py`, `app/models/ingestion_error.py`.

## Acceptance criteria

1. **(§21.5)** A queued document runs end-to-end to `completed` with chunks persisted; status transitions occur in order and each is observable mid-run.
2. Chunking respects token bounds and format rules; every chunk row carries `workspace_id` + `chunk_index` + `section_ref`.
3. A transient error retries and **resumes** from the last successful step; a permanent error fails immediately and writes an `ingestion_errors` row.
4. Large-file path is memory-safe (streaming), proven by the runner calling parse in streaming mode for >50 MB.
5. `content_hash` is computed/stored but never blocks (dedup deferred).

## Dependencies

- 003 (queued docs + storage), 013 (gateway for tags), 005 (downstream).

## Relevant rules

- `.claude/rules/ai-gateway.md`, `.claude/rules/database.md`, `.claude/rules/testing.md`

## Traceability

| AC | Code path(s) | Test path(s) | Status |
|---|---|---|---|
| 1,3 | `app/services/ingestion/worker_flow.py` | `tests/test_pipeline.py` | ☐ |
| 2 | `app/services/chunking.py` | `tests/test_chunking.py` | ☐ |
