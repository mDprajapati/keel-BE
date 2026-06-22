# Keel MVP — Backend Scope (mirror of v3)

This is the backend-oriented source of truth. It mirrors **`Keel_MVP_Scope_Document_v3`** and the BE/AI delivery timelines, keeping the original section numbers (`v3 §N`) so every spec and code path is traceable. Where the frontend defers an item, the backend defers it too.

> Full product narrative lives in the v3 document. This file captures the decisions the **backend** must implement, plus the reconciliations needed against the real frontend at `../keel-UI` (contract authority; see `docs/api-contract.md`). `../keel-frontend` is an earlier prototype — ignore it.

## §2–§4 Product, roles, retrieval

- Org signs up → workspace created → upload/connect data → async ingestion → vector + graph storage → retrieval via Chat + REST.
- Connecting a source does **not** auto-ingest; the user manually selects files (v3 §2, §10.2).
- Roles: `admin`, `standard`. **Retrieval is not role-restricted** — all members retrieve all workspace data; roles gate admin actions only (v3 §4, §12.3).

## §6 Auth

- Signup fields: full name, work email, organization name, password (min 12, mixed case + digit/symbol), confirm.
- Atomic signup: `user` + `organization` + `workspace` + `organization_member(admin)`; bcrypt cost 12.
- JWT access token 15 min (response body); refresh token 30 days (HttpOnly cookie, stored server-side); `POST /auth/refresh` rotates.
- Login lockout: 10 fails / 15 min per email → 15-min lockout.
- **Deferred:** email verification (§6.2) — `is_verified` column only; MFA (§6.3) — `mfa_enabled` column only. Account is usable immediately after signup.

## §7 Dashboard (counters + feeds)

Counters: total documents, sources connected, documents processed (completed), chunks, embeddings, AI tags, chat queries (month), REST API calls (month). Feeds: last 20 ingestion events, last 10 uploaded docs, connector last-sync status. Served with a 60s stale-while-revalidate cache.

## §8 Data

- Upload types (MVP): PDF, DOCX, TXT, CSV, XLSX required; PPTX, PNG/JPG optional (OCR).
- Max 500 MB/file; >10 MB uses multipart 5 MB parts (assembled in object storage).
- Path: `workspaces/{workspace_id}/raw/{document_id}/{filename}`.
- MIME validated against content bytes → `INVALID_FILE_TYPE` on mismatch.
- `documents` row created immediately with `ingestion_status: queued`; frontend polls status.
- **Deferred:** SHA-256 content dedup (§9.2) — `content_hash` + `duplicate_of` stored, never enforced.
- Tags: LLM on first 2000 tokens; PG `text[]`; max 20 tags, 50 chars; lowercase normalized; editable via `PATCH /documents/{id}/tags` (no reprocess). Pre-defined metadata stored in **both** Qdrant and Neo4j (v3 §2.4, §8.2).
- `source_type` enum: `manual_upload`, `google_drive`, `onedrive`, `api_push`.
- Data table: server-side pagination (50/100/200), search on name, filter by source/status/type/tag, sort by date/name/chunk count.
- **Deferred:** Document Detail View (§8.5) — original document not stored.

## §9 Ingestion pipeline (Celery)

Resumable step chain on a dedicated `ingestion` queue. Concurrency 4 (`CELERY_INGESTION_CONCURRENCY`). Timeout 30 min (90 min for >100 MB). Retries 3, exponential backoff base 30s ×2 for transient errors; permanent errors (parse/unsupported) fail immediately. Dead-letter → `ingestion_errors` (`document_id`, `step_failed`, `error_type`, `error_message`, `retry_count`).

Steps (v3 §9.1): retrieve → parse (Docling, streaming >50 MB) → extract structure → tag (LLM, first 2000 tok) → write tags → chunk → **[7–9 SHA-256 dedup: skeleton, deferred]** → persist chunks → embed (batch 100) → upsert Qdrant → NER → upsert Neo4j → finalize metadata/source → `completed` + counters.

- Chunking (§9.3): target 512 / max 1024 / overlap 64 / min 50 tokens. PDF/DOCX/PPTX paragraph+sentence; XLSX/CSV row-based (header repeated, 50 rows/chunk, stream CSV >100K rows); TXT `\n\n` split. Chunk schema: `chunk_id, document_id, workspace_id, chunk_index, chunk_text, token_count, section_ref, source_type, metadata(JSONB), created_at`.
- Vector (§9.4): Qdrant HNSW `m=16, ef_construction=64, ef_search=40`, cosine, 1536 dims, point id = `chunk_id`, payload `{workspace_id, document_id, chunk_index, section_ref}`, **mandatory `workspace_id` filter**. Embedding model fixed at workspace init.
- Graph (§9.5): LLM-based NER (not spaCy). Entities: `PERSON, ORGANIZATION, PROJECT, DOCUMENT, PRODUCT, DATE, INDUSTRY`. Relationships: `MENTIONS, AUTHORED_BY, BELONGS_TO, REFERENCES`. Neo4j nodes dedup by `canonical_name + entity_type + workspace_id`; edges carry `document_id, chunk_id, confidence_score`. Constraints + indexes created on startup. Graph built on every ingest; multi-hop traversal deferred (1-hop best-effort only).

## §10 Connectors

Google Drive (primary, OAuth 2.0 auth-code), OneDrive (stretch / coming-soon stub). Out of scope: Slack, SharePoint, Notion, Confluence, local mount. Manual file selection after connect (§10.2). Manual sync only (scheduled deferred). Sync skips: same `external_document_id`+mtime, unsupported MIME, >500 MB. Encrypted refresh tokens in `connector_credentials`.

## §11 Model page (read-only)

No runtime model switching. Displays parser (Docling), embedding (`text-embedding-3-small`, 1536), chat (`gpt-4o-mini` default / `gpt-4o`), vector (Qdrant), graph (Neo4j). The chat model is the **one** runtime-configurable model (via workspace settings).

## §12 Chat

`POST /api/chat/query` (SSE, browser/JWT): embed question → Qdrant top-k=10 (cosine, min 0.65, mandatory `workspace_id` filter, configurable top-k ≤25) → optional 1-hop graph augmentation (≤5 extra chunks, best-effort) → assemble context ≤8000 tokens (drop lowest-ranked, no mid-sentence cut) → structured prompt → stream answer (SSE) → persist `chat_messages` with question, answer, chunk ids, confidence. Confidence = mean top-3 similarity (**not** trust score). Conversation history per user; loaded on demand; no shared conversations.

## §13 Public REST API (API-key auth)

Retrieval: `POST /api/search`, `POST /api/context`, `POST /api/chat` (non-streaming), `GET /api/documents`, `GET /api/evidence/{chunk_id}`. Ingestion: `POST /api/ingest/file`, `POST /api/ingest/text`, `POST /api/ingest/record`, `GET /api/ingest/status/{job_id}`. Auth: `Authorization: Bearer {api_key}`, workspace-scoped, `401` on invalid. Rate limit 100 req/min/key (sliding window) → `429` + `Retry-After`. Error envelope `{error_code, message, request_id}`. Targets: search/context p95 < 3s, chat < 10s, status < 300 ms. MCP is a placeholder only (§13.5).

## §14 Users & permissions

Roles admin / standard. Admin: invite (email + role), change role, remove (`organization_members` row), list (name, email, role, last active). Capability matrix v3 §14.2. **Deferred:** doc-level ACL, source ACL, role-based retrieval scoping, SSO/OIDC.

## §15 Settings

Workspace (display name, org name, default-upload behaviour, chat model `gpt-4o-mini`/`gpt-4o`, top-k 5–25, min similarity 0.5–0.9). API (enable REST, default rate limit). Connector (manual sync only, source tracking always on). UI: light only.

## §18 In-scope / §19 Out-of-scope

In: auth, dashboard, data upload + tags, source tracking, paginated data table, GD connector (OD stretch), Celery ingestion, Docling, chunking, batch embedding, Qdrant, LLM NER + Neo4j, read-only model page, chat (SSE) + confidence + evidence + history, REST retrieval + ingestion, API keys + rate limit, roles + user admin, settings, light theme.

Out (deferred): email verification, MFA, SHA-256 dedup, Document Detail View, dark mode, full MCP, Slack/SharePoint/Notion/Confluence connectors, runtime model switching, reranker, multi-hop GraphRAG, trust score, role/doc-level retrieval, source ACL sync, SSO/OIDC, scheduled sync, org hierarchy, advanced audit logs, k8s, multi-region, billing, workflow automation, virus scan, bulk reprocess queue.

## §21 Success criteria (the demo flow the backend must complete)

Signup→login (no email-verify)→dashboard counters→upload large PDF (progress, auto-ingest)→pipeline completes (parsed/chunked/embedded/graph)→tags visible+editable→GD connector OAuth+folder+file-select+manual sync→standard user chats (streamed answer + confidence + evidence)→same question via `POST /api/chat` with API key→third-party `POST /api/ingest/text` → `GET /api/ingest/status/{job_id}` returns `completed`→user admin (invite/role/remove)→API keys (generate/scope/revoke).
