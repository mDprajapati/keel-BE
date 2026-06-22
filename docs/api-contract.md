# Keel Backend — API Contract

**Contract authority: `../keel-UI`** (the real frontend). Every path and shape below is taken verbatim from `keel-UI/src/lib/api/client.ts`, `src/lib/api/types.ts`, `src/lib/api/chat-stream.ts`, and `src/mocks/handlers.ts`. Do not drift from them. (`../keel-frontend` is an earlier prototype — **ignore it**.)

## Conventions

- **Single prefix `/api`** (no version segment). The frontend reads `VITE_API_BASE_URL` (empty in dev → same-origin, Vite proxies `/api` → `http://localhost:8000`).
- **Auth (app):** access token in the response body, kept **in memory** by the FE; refresh token in an **HttpOnly cookie** (`credentials: include`). On `401` the FE calls `POST /api/auth/refresh` once and retries.
- **Error envelope (every non-2xx):** `{ "error_code": "string", "message": "string", "request_id": "uuid" }`. `429` adds a `Retry-After` header (seconds).
- **`workspace_id` is never sent by the client** — derived server-side from the JWT (app) or the API key (REST).
- **Field casing is snake_case** end to end (no translation layer on the FE).

## Authentication model — one prefix, two principals

| Endpoint group | Accepted auth |
|---|---|
| `/api/auth/*` | special (login/register/refresh skip bearer; me/logout use JWT) |
| App-only: `/api/conversations*`, `/api/chat/query`, `/api/documents/{id}/tags\|reprocess`, `DELETE /api/documents/{id}`, `/api/apikeys*`, `/api/connectors*`, `/api/admin/users*`, `/api/dashboard`, `/api/model`, `/api/settings` | **User JWT** (admin gate where noted) |
| **Dual auth** (v3 §13 surface — app uses JWT, third parties use API key): `/api/search`, `/api/context`, `/api/chat`, `/api/documents` (GET list), `/api/evidence/{id}`, `/api/ingest/file`, `/api/ingest/file/part`, `/api/ingest/text`, `/api/ingest/record`, `/api/ingest/status/{job_id}` | **User JWT OR workspace API key** |

Rate limit (100/min, `429` + `Retry-After`) applies to **API-key-authenticated** calls (v3 §13.3). The auth dependency resolves a `Principal {workspace_id, user_id?, api_key_id?, scope}`; never sniff token type by content — try JWT, then API key.

---

## Endpoints (all under `/api`)

### Auth
| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/auth/register` | `{full_name, email, organization_name, password}` | `AuthTokenResponse` + Set-Cookie refresh |
| POST | `/auth/login` | `{email, password}` | `AuthTokenResponse` + Set-Cookie refresh |
| POST | `/auth/refresh` | — (refresh cookie) | `AuthTokenResponse` (`401 UNAUTHENTICATED` if no session) |
| POST | `/auth/logout` | — | `204` (clears cookie) |
| GET | `/auth/me` | — | `SessionInfo {user, workspace}` |

`AuthTokenResponse = {access_token, user, workspace}`.
`User = {id, full_name, email, role, last_active_at}`, `role ∈ {admin, standard}`.
`Workspace = {id, name, organization_name}`.

### Documents & ingestion
| Method | Path | Request | Response | Auth |
|---|---|---|---|---|
| GET | `/documents` | `?page=1&limit=50&search&status&source_type&file_type&tag&sort=uploaded_at&order=desc` | `Paginated<KeelDocument>` | dual |
| POST | `/ingest/file` | multipart `file`, `file_name?`, `source_label?`, `tags?` | `IngestJobResponse` | dual (write) |
| POST | `/ingest/file/part` | multipart part | `{part, received}` | dual (write) |
| POST | `/ingest/text` | `{content, title, source_label?, tags?[]}` | `IngestJobResponse` | dual (write) |
| POST | `/ingest/record` | `{record_type, record_id, fields, source_label?, tags?[]}` | `IngestJobResponse` | dual (write) |
| GET | `/ingest/status/{job_id}` | — | `IngestStatus` | dual |
| PATCH | `/documents/{id}/tags` | `{tags: string[]}` | `KeelDocument` | JWT |
| DELETE | `/documents/{id}` | — | `204` | JWT |
| POST | `/documents/{id}/reprocess` | — | `IngestJobResponse` | JWT |

```
KeelDocument = {id, name, file_type, source_type, tags[], uploaded_by, uploaded_at,
                ingestion_status, chunk_count: number|null, embedding_status}
Paginated<T>  = {data: T[], total, page, limit}
IngestJobResponse = {document_id, job_id, status}
IngestStatus  = {job_id, document_id, status, current_step, steps_completed, steps_total, error, completed_at}
file_type ∈ {pdf,docx,txt,csv,xlsx,pptx,png,jpg}
source_type ∈ {manual_upload, google_drive, onedrive, api_push}
ingestion_status ∈ {queued, processing, parsing, tagging, chunking, embedding,
                    entity_extraction, graph_mapping, finalizing, completed, failed, duplicate}
embedding_status ∈ {pending, in_progress, completed, failed}
```
> The FE consumes the **granular** `ingestion_status` enum directly — the API returns it raw (no app/internal vocabulary mapping). `duplicate` is valid but never produced in MVP.

### Conversations & chat
| Method | Path | Request | Response | Auth |
|---|---|---|---|---|
| GET | `/conversations` | `?cursor?` | `Paginated<Conversation>` | JWT |
| GET | `/conversations/{id}/messages` | `?cursor?` | `Paginated<ChatMessage>` | JWT |
| POST | `/chat/query` | `{question, conversation_id?}` | **SSE** `text/event-stream` | JWT |
| POST | `/chat` | `{question, conversation_id?}` | `{answer, confidence, evidence[], conversation_id}` (non-stream, v3 §13) | dual |

```
Conversation = {id, title, updated_at}
ChatMessage  = {id, conversation_id, role: 'user'|'assistant', content, confidence: number|null, evidence: EvidenceChunk[], created_at}
EvidenceChunk = {chunk_id, document_id, document_name, source_type, section_ref: string|null, excerpt, similarity_score}
```
**SSE frames** (`data: <json>\n\n`):
`{type:'token', text}` (repeated) → `{type:'done', confidence, evidence, conversation_id}`; `{type:'error', message}` on failure. `confidence` = mean similarity of the top-3 chunks. Persist user+assistant `chat_messages` after the stream closes.

### REST retrieval (dual auth)
**`POST /search`** `{query, top_k?=10≤25, min_score?=0.65, filter_source_type?[]}` ⇒
`{results:[{chunk_id, document_id, document_name, source_type, chunk_text, similarity_score, section_ref, metadata}], query_embedding_ms, search_ms}`

**`POST /context`** `{query, max_tokens?=8000≤32000, top_k?=10}` ⇒
`{context, evidence:[{chunk_id, document_name, similarity_score, section_ref}], token_count, truncated}`

**`GET /evidence/{chunk_id}`** ⇒ `{chunk_id, document_id, document_name, source_type, chunk_text, similarity_score, section_ref, metadata}`

### API keys (JWT, admin)
| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/apikeys` | — | `ApiKey[]` |
| POST | `/apikeys` | `{name, scope}` | `ApiKey & {secret}` (secret shown once) |
| DELETE | `/apikeys/{id}` | — | `204` |

`ApiKey = {id, name, scope, created_at, last_used_at, request_count, rate_limit_per_minute}`, `scope ∈ {read_only, read_write}`.

### Connectors (JWT; admin for mutations)
| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/connectors` | — | `Connector[]` |
| POST | `/connectors/{type}/oauth/start` | — | `{authorization_url?, connected?}` |
| GET | `/connectors/{id}/folders` | — | `ConnectorFolderNode[]` |
| POST | `/connectors/{id}/sync` | `{file_ids: string[]}` | `{status}` |
| DELETE | `/connectors/{id}` | — | `204` |

`Connector = {id, type, name, status, last_synced_at, last_sync_document_count}`, `type ∈ {google_drive, onedrive}`, `status ∈ {connected, disconnected, coming_soon}`.
`ConnectorFolderNode = {id, name, type:'folder'|'file', mime_type?, children?[]}`.

### Users (JWT, admin)
| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/admin/users` | — | `User[]` |
| POST | `/admin/users/invite` | `{email, role}` | `User` |
| PATCH | `/admin/users/{id}/role` | `{role}` | `User` |
| DELETE | `/admin/users/{id}` | — | `204` (`422 LAST_ADMIN` if removing the last admin) |

### Dashboard / model / settings (JWT)
| Method | Path | Response |
|---|---|---|
| GET | `/dashboard` | `DashboardResponse` |
| GET | `/model` | `ModelConfig` (read-only) |
| GET | `/settings` | `WorkspaceSettings` |
| PATCH | `/settings` | `WorkspaceSettings` |

```
DashboardResponse = {metrics:{documents_uploaded, sources_connected, documents_processed,
  chunks_generated, embeddings_created, ai_tags_generated, chat_queries_this_month, api_calls_this_month},
  recent_activity:[{id, document_name, status, timestamp}], recent_documents: KeelDocument[],
  connector_sync:[{connector_id, connector_name, last_synced_at, document_count}],
  pipeline_health:{sources, ingestion, storage, chat, rest_api}}   // each ∈ {active,processing,idle,error}

ModelConfig = {parser:{name,version,processing_mode,supported_formats[]},
  embedding:{provider,model,dimensions,max_input_tokens,chunk_target,chunk_max},
  chat:{provider,model,max_context_tokens,retrieval_context_tokens},
  vector_store:{engine,index_type,similarity_metric}, graph_store:{engine}}

WorkspaceSettings = {workspace_name, organization_name, auto_start_ingestion, chat_model,
  chat_top_k, min_similarity_threshold, rest_api_enabled, default_rate_limit_per_minute,
  sync_mode:'manual', read_only:{parser, embedding_model, vector_store, graph_store}}
chat_model ∈ {gpt-4o-mini, gpt-4o}
```

### Health & MCP
- `GET /health` ⇒ `{status:"ok", ...}` (no auth).
- `GET /api/mcp` ⇒ placeholder descriptor ("coming soon", v3 §13.5).

---

## Targets (v3 §13.3)

search/context p95 < 3 s · chat (non-stream) p95 < 10 s · ingest status p95 < 300 ms · pagination default 50 / max 200 · ingest body ≤ 50 MB · search/context body ≤ 64 KB.
