# Keel Backend — Ingestion Pipeline

A resumable Celery task chain on the dedicated `ingestion` queue. One task per document. Each step writes its output **and** updates `documents.ingestion_status` / `current_step` before the next, so a retry resumes from the last successful step (v3 §9).

## Entry points (all converge here)

- App upload (JWT) and third-party (API key) both hit `POST /api/ingest/file` (multipart; >10 MB via `POST /api/ingest/file/part`)
- Public REST also: `POST /api/ingest/text` · `/record`
- Connector sync: fetch selected files → storage → `documents(source_type=google_drive|onedrive)`

All create a `documents` row (`ingestion_status=queued`) and enqueue `tasks.ingestion.ingest_document(document_id)`, returning `202` + `job_id` immediately.

## Worker config

- `celery -A app.celery_app.celery worker -Q ingestion -c $CELERY_INGESTION_CONCURRENCY` (default 4).
- Timeout 30 min/doc; 90 min for files > 100 MB.
- Retry: 3×, exponential backoff base 30s ×2 — **transient only** (network, rate limit). Permanent (parse/unsupported) → fail immediately, no retry.
- Dead-letter: after final failure write `ingestion_errors(document_id, step_failed, error_type, error_message, retry_count)`.

## Steps (`services/ingestion/steps.py`, ordered by `worker_flow.run`)

| # | Step | Status written | Notes |
|---|---|---|---|
| 1 | Retrieve file from object storage | `processing` | via `storage.get_bytes` |
| 2 | Parse (Docling; streaming >50 MB, page-by-page >500p) | `parsing` | progress every 50 pages |
| 3 | Extract text/headings/tables/page-section metadata | `parsing` | feeds `section_ref` |
| 4 | LLM tag generation (first 2000 tokens) | `tagging` | `tagging.generate_tags` |
| 5 | Write tags → `documents.tags` | `tagging` | ≤20, lowercased |
| 6 | Chunk (format-specific) | `chunking` | see chunking below |
| 7 | Compute SHA-256 `content_hash` | `dedup_check` | **SKELETON** — stored, not blocking (§9.2) |
| 8 | Check hash in workspace | `dedup_check` | **SKELETON / deferred** |
| 9 | If dup → link + `duplicate` + stop | `duplicate` | **SKELETON / deferred** (never fires in MVP) |
| 10 | Persist chunks → `document_chunks` | `chunking` | `workspace_id` on every chunk |
| 11 | Embed in batches of 100 | `embedding` | `llm_gateway.embed` + token bucket |
| 12 | Upsert vectors → Qdrant (HNSW, cosine) | `embedding` | point id = `chunk_id`, payload incl. `workspace_id` |
| 13 | LLM NER on full text (7 entity types incl INDUSTRY) | `entity_extraction` | `ner.extract` |
| 14 | Upsert nodes + edges → Neo4j | `graph_mapping` | MERGE dedup; parameterized Cypher; best-effort, never blocks completion |
| 15 | Write document metadata + source mapping | `finalizing` | |
| 16 | `ingestion_status=completed` + bump workspace counters | `completed` | |

In the MVP, step 6 → step 10 directly (7–9 compute/store the hash but do not block).

## Chunking (`services/chunking.py`, v3 §9.3)

- Token-based: target 512, max 1024 (hard cap, split at sentence), overlap 64, min 50 (merge up). Tokens measured with the embedding model's tokenizer (`tiktoken` for `text-embedding-3-small`).
- PDF/DOCX/PPTX: paragraph + section boundaries first; oversized paragraph → sentence split.
- XLSX/CSV: row-based, header repeated per chunk, 50 rows/chunk; each XLSX sheet independent; CSV > 100K rows streamed from disk (no DataFrame).
- TXT: split on `\n\n`, then cap at 512 tokens.

Chunk record: `chunk_id, document_id, workspace_id, chunk_index, chunk_text, token_count, section_ref, source_type, metadata(JSONB), created_at`.

## Embedding (`vector_store` + `llm_gateway.embed`)

Batches of 100 to minimize round-trips; token-bucket rate limit (configurable max req/min). Failed batch retried 3× → else `embedding_status=embedding_failed`. Vectors upserted to the workspace Qdrant collection.

## Graph (`services/graph_store.py`, v3 §9.5)

LLM NER (not spaCy) → entities `PERSON, ORGANIZATION, PROJECT, DOCUMENT, PRODUCT, DATE, INDUSTRY`; relationships `MENTIONS, AUTHORED_BY, BELONGS_TO, REFERENCES`. MERGE nodes (dedup by `canonical_name+entity_type+workspace_id`), MERGE edges with `document_id, chunk_id, confidence_score`. Built on every ingest. Failures here are logged but do **not** fail the document (graph is best-effort).

## Testing the pipeline

Call `worker_flow.run(document_id, session)` directly (not `.delay()`). Mock `parsing`, `llm_gateway`, `vector_store`, `graph_store`, `storage`. Assert: status transitions in order; chunks carry `workspace_id`; a transient error retries and resumes; a permanent error dead-letters.
