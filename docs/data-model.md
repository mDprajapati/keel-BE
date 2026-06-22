# Keel Backend — Data Model

PostgreSQL 16 via SQLAlchemy 2.0 (async). **Every table** has `id` (UUID pk), `created_at`, `updated_at`. **Every domain row** carries `workspace_id` (the tenant boundary). Vectors live in Qdrant, graph in Neo4j — never in PG.

## Tenancy

```
organizations 1──n workspaces 1──n (documents, document_chunks, conversations, connectors, api_keys, ...)
users n──n organizations  (via organization_members, carries role)
```

## Tables

### organizations
`id, name, slug (unique), created_at, updated_at`

### workspaces
`id, organization_id (fk), name, embedding_model='text-embedding-3-small', embedding_dims=1536, chat_model='gpt-4o-mini', top_k=10, min_similarity=0.65, default_auto_ingest=true, rest_api_enabled=true, default_rate_limit=100, created_at, updated_at`
> Embedding model/dims fixed at creation (no runtime switch). Chat model + top_k + min_similarity are the runtime-configurable settings (v3 §15.1).

### users
`id, email (unique, citext), full_name, password_hash, is_active=true, is_verified=false (SKELETON §6.2), mfa_enabled=false (SKELETON §6.3), last_active_at, failed_login_count=0, lockout_until (nullable), created_at, updated_at`

### organization_members
`id, organization_id (fk), user_id (fk), workspace_id (fk), role ENUM(admin, standard), invited_email (nullable), invite_accepted=false, created_at, updated_at` — unique (organization_id, user_id).

### documents
`id, workspace_id (fk), name (display name → `KeelDocument.name`), filename, file_type ENUM(pdf,docx,txt,csv,xlsx,pptx,png,jpg), mime_type, size_bytes, source_type ENUM(manual_upload, google_drive, onedrive, api_push), connector_id (nullable fk), external_document_id (nullable), storage_path, tags TEXT[] (≤20, lowercased), doc_metadata JSONB, ingestion_status ENUM (full set below), current_step, chunk_count (nullable int — null until chunked), embedding_status ENUM(pending, in_progress, completed, failed), content_hash (nullable, SKELETON §9.2), duplicate_of (nullable self-fk, SKELETON §9.2), uploaded_by_id (fk users), uploaded_by (display name → `KeelDocument.uploaded_by`), uploaded_at (= created_at, exposed as `uploaded_at`), created_at, updated_at`
> The `KeelDocument` API response = `{id, name, file_type, source_type, tags[], uploaded_by, uploaded_at, ingestion_status, chunk_count, embedding_status}`. `content_hash`/`duplicate_of` are stored but **never enforced** in MVP.

### document_chunks
`chunk_id (pk), document_id (fk), workspace_id (fk), chunk_index, chunk_text, token_count, section_ref (nullable), source_type, chunk_metadata JSONB (page, sheet, row range), created_at, updated_at` — index on (workspace_id, document_id).

### conversations
`id, workspace_id (fk), user_id (fk), title, last_message, created_at, updated_at`

### chat_messages
`id, conversation_id (fk), workspace_id (fk), role ENUM(user, assistant), content, confidence (nullable float), retrieved_chunk_ids UUID[] (nullable), created_at, updated_at`

### connectors
`id, workspace_id (fk), type ENUM(google_drive, onedrive), name, status ENUM(connected, disconnected, coming_soon), last_synced_at, last_sync_document_count (nullable), created_at, updated_at`

### connector_credentials
`id, connector_id (fk, unique), encrypted_refresh_token (SecretStr at rest), scopes, account_email, created_at, updated_at` — refresh tokens encrypted; never logged.

### api_keys
`id, workspace_id (fk), name, key_prefix, key_hash, scope ENUM(read_only, read_write), rate_limit_per_minute=100, last_used_at, request_count=0, revoked=false, created_by (fk), created_at, updated_at`
> The API response = `{id, name, scope, created_at, last_used_at, request_count, rate_limit_per_minute}`. `scope` is exactly `read_only`/`read_write` (keel-UI uses these values directly). The `secret` is returned **once** at creation (`POST /api/apikeys`); only `key_hash` persists. `read_only` = retrieval endpoints; `read_write` = retrieval + ingestion.

### ingestion_errors  (dead-letter)
`id, document_id (fk), workspace_id (fk), step_failed, error_type, error_message, retry_count, created_at, updated_at`

### token_usage  (MANDATORY per AI timeline)
`id, workspace_id (fk), operation (tagging|ner|embedding|chat|context), model, prompt_tokens, completion_tokens, total_tokens, cost_usd NUMERIC(12,6), request_id (nullable), created_at, updated_at`
> Written on **every** `call_llm()` / `embed()` — no exceptions.

### usage_counters / api_call_log (dashboard support)
Lightweight monthly counters for chat queries + REST calls (v3 §7). Implemented as an `api_call_log` row per REST call (workspace_id, endpoint, created_at) aggregated for the dashboard, plus derived counts for documents/chunks/embeddings/tags.

## Enums summary

- `ingestion_status`: queued, processing, parsing, tagging, chunking, embedding, entity_extraction, graph_mapping, finalizing, completed, failed, **duplicate** (forward-compat only)
- `embedding_status`: pending, in_progress, completed, failed
- `source_type`: manual_upload, google_drive, onedrive, api_push
- `role`: admin, standard
- `api_key_scope`: read_only, read_write
- `connector_type`: google_drive, onedrive
- `connector_status`: connected, disconnected, coming_soon

## Status vocabulary — no mapping

The frontend (`keel-UI`) consumes the **granular `ingestion_status` enum directly** (queued…finalizing…completed/failed). There is **no** app-vs-internal vocabulary translation — the API returns the raw enum value. `duplicate` is a valid value but is never produced in the MVP (dedup deferred, §9.2).

## Qdrant (per workspace collection)

Point id = `chunk_id`; vector = 1536-d embedding; payload = `{workspace_id, document_id, chunk_index, section_ref, source_type, tags}`. HNSW `m=16, ef_construction=64`, cosine. **Every query filters `workspace_id`.**

## Neo4j

Nodes: `(:Entity {entity_type, canonical_name, workspace_id})` deduped by `canonical_name+entity_type+workspace_id`. Edges: `MENTIONS|AUTHORED_BY|BELONGS_TO|REFERENCES {document_id, chunk_id, confidence_score}`. Constraints + indexes on `workspace_id, entity_type, canonical_name` (nodes) and `document_id` (edges), created on startup.
