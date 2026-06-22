> **This is the Python backend for Keel.**
> Source of truth for MVP scope: `docs/spec/SCOPE.md` (mirrors `Keel_MVP_Scope_Document_v3`). Per-feature specs: `specs/`. Read this file before writing any model, service, router, or task.
>
> **Greenfield note:** `app/` is being built out in phases (see `docs/architecture.md`). The `docs/` describe the *target* architecture derived from the v3 spec and the BE/AI timelines. Read the current `app/` before assuming a file exists.

# Project: Keel Backend — Enterprise Context & Trust Platform

Python 3.12 / FastAPI backend for Keel — a platform that lets organizations upload and connect enterprise data, process it through an asynchronous ingestion pipeline (parse → tag → chunk → embed → graph), store it in Qdrant (vectors) and Neo4j (graph), and retrieve evidence-backed answers via Chat (SSE) and a public REST API. This repo owns: auth + workspace, data upload + ingestion, the Celery pipeline, vector/graph storage, retrieval + chat, connectors, dashboard, user/API-key admin, and settings.

The real frontend lives at **`../keel-UI`** and is the **contract authority** (see "API surface"). Its `src/lib/api/client.ts`, `src/lib/api/types.ts`, and `src/mocks/handlers.ts` define every path and shape — match them verbatim. Never change a path or response shape the frontend consumes without updating the frontend in the same change. (`../keel-frontend` is an earlier prototype — **ignore it**.)

## Stack (confirmed — v3 §20)

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| Web framework | FastAPI (async) |
| Async task queue | Celery |
| Broker + result backend | Redis |
| Relational DB | PostgreSQL 16 (SQLAlchemy 2.0 async + Alembic) |
| Vector store | Qdrant Community (`qdrant-client>=1.9`, HNSW, cosine) |
| Graph store | Neo4j Community (`neo4j>=5.20`, official driver, parameterized Cypher) |
| Object storage | MinIO (local) / any S3-compatible adapter |
| Parsing | Docling (PDF/DOCX/TXT/CSV/XLSX/PPTX) |
| Embeddings | OpenAI `text-embedding-3-small` (1536 dims) |
| Chat / NER / tagging | OpenAI `gpt-4o-mini` (default) / `gpt-4o` (configurable) |
| Config | pydantic-settings (`SecretStr` for all secrets) |
| Logging | structlog (no PII, request correlation) |
| Auth | JWT (access 15 min, refresh 30 days) + bcrypt (cost 12) |

> **Do not** introduce pgvector or Apache AGE. Vectors live in Qdrant, graph lives in Neo4j. Relational migrations are standard SQLAlchemy/Alembic only (no vector/graph DDL).

## Layer model

```
api/        — Routers. Thin. Validate (Pydantic), call a service, shape the response. No business logic, no direct driver/SDK calls.
  └─▶ services/   — Business logic. The only layer that talks to adapters (gateway, vector_store, graph_store, storage) and the DB.
        └─▶ adapters — llm_gateway (OpenAI), vector_store (Qdrant), graph_store (Neo4j), storage (S3/local). The only place external SDKs are constructed.
              └─▶ models/   — SQLAlchemy ORM. schemas/ — Pydantic DTOs (never expose ORM objects directly).
```

Routers never import `openai`, `qdrant_client`, `neo4j`, or storage SDKs directly. They call a service; the service calls an adapter.

## API surface — one prefix `/api`, two principals (READ THIS)

There is **one** path prefix: `/api` (no version segment — `keel-UI` calls same-origin `/api/...`). Endpoints differ by **who may call them**, not by path tree:

| Group | Accepted auth |
|---|---|
| App-only (`/api/auth/*` me+logout, `/api/conversations*`, `/api/chat/query` SSE, `/api/documents/{id}/tags\|reprocess`, `DELETE /api/documents/{id}`, `/api/apikeys*`, `/api/connectors*`, `/api/admin/users*`, `/api/dashboard`, `/api/model`, `/api/settings`) | **User JWT** (admin gate where noted) |
| **Dual auth** — the v3 §13 surface that both the app (JWT) and third parties (API key) call: `/api/search`, `/api/context`, `/api/chat`, `GET /api/documents`, `/api/evidence/{id}`, `/api/ingest/file\|file/part\|text\|record`, `/api/ingest/status/{job_id}` | **User JWT OR workspace API key** |
| Unauthenticated | `/api/auth/login\|register\|refresh`, `/health` |

The auth dependency resolves a `Principal {workspace_id, user_id?, api_key_id?, scope}` by trying the JWT first, then the API key — **never sniff token type by string content**. Rate limiting (100/min, `429` + `Retry-After`) applies only to **API-key**-authenticated calls (v3 §13.3).

SSE chat for the browser is `POST /api/chat/query` (JWT, `data: <json>\n\n` frames: `token`* then `done`). The public non-streaming equivalent is `POST /api/chat`. The full endpoint list + exact shapes live in `docs/api-contract.md` (taken verbatim from `keel-UI`).

## Hard rules (non-negotiable)

1. **One OpenAI client.** It is constructed **only** in `app/services/ai/llm_gateway.py`. Every LLM/embedding call goes through `call_llm()` / `embed()`. No other file may `import openai` or build a client. (AI timeline: "Only place an openai client may be constructed.")
2. **Mandatory token-usage logging.** Every `call_llm()` and `embed()` writes a `token_usage` row with: `workspace_id`, `operation` (e.g. `tagging`, `ner`, `chat`, `embedding`), `model`, `prompt_tokens`, `completion_tokens`, `total_tokens`, `cost_usd`, `created_at`. No LLM call may bypass this. (AI timeline: "log workspace/op/model/tokens/cost on every call.")
3. **`workspace_id` is the hard tenant boundary.** Every domain row carries `workspace_id`. Every Qdrant search MUST pass a mandatory `workspace_id` payload filter. Every chunk carries `workspace_id`. Derive `workspace_id` from the authenticated principal — never from request body or URL.
4. **All crypto lives in `app/core/security.py` only** — bcrypt hash/verify, JWT create/decode, API-key hashing. Security-critical; reviewed line-by-line.
5. **Config from env only.** Every value is read via `app/config.py` (pydantic-settings). Secrets are `SecretStr`. No hardcoded keys, URLs, hosts, or credentials anywhere.
6. **structlog only, no PII.** No `print()` (ruff `T201` blocks it). Never log tokens, passwords, API-key secrets, refresh tokens, or personal data. Attach `request_id` for correlation.
7. **Error envelope.** Every error response is `{ "error_code": "string", "message": "string", "request_id": "uuid" }`. Use the central exception handlers in `app/main.py`; raise `AppError` subclasses, do not return ad-hoc dicts.
8. **CORS whitelist, no wildcards.** Origins come from `CORS_ALLOW_ORIGINS` env.
9. **Both timestamps everywhere.** Every table has `created_at` AND `updated_at`.
10. **Parameterized Cypher only.** Never string-interpolate values into Cypher. Use driver parameters.
11. **Graph augmentation is best-effort.** Graph lookups in retrieval must never fail a chat request — catch and continue.
12. **Confidence ≠ trust score.** The chat confidence is the mean cosine similarity of the top-3 retrieved chunks (float 0–1). Never emit a field named `trust_score`; trust vetting is deferred (v3 §12.4).
13. **Idempotent enqueue.** Ingest endpoints return `202` + `job_id` immediately; processing is async. MIME is validated against content bytes (not extension) → `INVALID_FILE_TYPE` on mismatch.

## Skeleton-now / deferred (build the column/hook, do NOT enforce)

These exist in code for forward-compat but are **not enforced** in the MVP (v3 §6.2, §6.3, §9.2):

| Skeleton | What exists now | What is deferred |
|---|---|---|
| SHA-256 dedup | `documents.content_hash` + `documents.duplicate_of` computed/stored; pipeline step present | No blocking/skip on hash (v3 §9.2) |
| Email verification | `users.is_verified` column | No verify email flow / gate (v3 §6.2) |
| MFA | `users.mfa_enabled` column | No MFA challenge at login (v3 §6.3) |
| `duplicate` status | retained as a valid `ingestion_status` value | never produced in MVP |
| API-key scopes | `read_only` / `read_write` enum (app uses `read`/`ingest`/`full` labels — map in schema) | finer-grained scopes |

Graph build runs on **every** ingest (not flag-gated). Multi-hop GraphRAG is deferred; 1-hop entity→chunk augmentation is the MVP ceiling.

## Auth model (v3 §6)

- Signup is atomic: one transaction creates `user` + `organization` + `workspace` + `organization_member` (first user = Admin).
- Login/register return `{access_token, user, workspace}` with the JWT **access token (15 min) in the response body** and rotate a **refresh token (30 days, HttpOnly cookie)**. `POST /api/auth/refresh` reads the cookie and returns a fresh `{access_token, user, workspace}`.
- Lockout: 10 failed logins / 15 min per email → 15-minute lockout.
- Roles (`admin`, `standard`) gate **admin actions only**. Retrieval is workspace-scoped for all members (v3 §4, §12.3) — never filter retrieval by role.

## Commands

| Task | Command |
|---|---|
| Bring up infra + app | `docker compose --profile full up --build` |
| Bring up infra only | `docker compose up -d postgres qdrant neo4j redis minio` |
| Run migrations | `alembic upgrade head` (runs automatically on API container start) |
| New migration | `alembic revision --autogenerate -m "<msg>"` |
| Run API (local) | `uvicorn app.main:app --reload` |
| Run worker (local) | `celery -A app.celery_app.celery worker -Q ingestion -c 4` |
| Tests | `pytest` |
| Lint | `ruff check .` |
| Format | `ruff format .` |
| Type check | `mypy app` |
| Seed demo admin | `python -m scripts.seed_admin` |

See `docs/runbook.md` for the full local-dev and verify flow.

## Testing rules (v3 / timeline)

- Test the ingestion pipeline by calling the coroutine/step runner directly — **not** `.delay()`.
- Workspace isolation is the hard boundary: every retrieval/search test asserts no cross-workspace leakage.
- Mock at the adapter boundary (gateway / storage / vector_store / graph_store) — do not call real OpenAI/Qdrant/Neo4j in unit tests.
- Each protected behaviour gets one 4xx test and one permission-denied test.

## Anti-patterns

| Pattern | Wrong | Right |
|---|---|---|
| OpenAI client | `import openai` in a service/router | Call `llm_gateway.call_llm()` / `embed()` |
| Untracked LLM call | Calling the model without writing `token_usage` | Always log workspace/op/model/tokens/cost |
| Tenant leak | Qdrant search without `workspace_id` filter | Mandatory `workspace_id` payload filter every search |
| `workspace_id` from input | `body.workspace_id` / `path.workspace_id` | Derive from the authenticated principal |
| Crypto scattered | bcrypt/JWT in a router | All crypto in `core/security.py` |
| Hardcoded secret | `client = OpenAI(api_key="sk-...")` | `settings.openai_api_key.get_secret_value()` |
| Cypher injection | f-string values into Cypher | Parameterized Cypher `MERGE (n {id:$id})` |
| Ad-hoc errors | `return {"error": "..."}` | Raise `AppError`; central handler emits the envelope |
| Trust score | emit `trust_score` | `confidence` = mean top-3 similarity |
| Sync blocking ingest | parse/embed inside the request | Return `202`+`job_id`; Celery does the work |
| Print debugging | `print(x)` | `log.info("event", key=value)` (structlog) |

## References

- @docs/spec/SCOPE.md
- @docs/api-contract.md
- @docs/architecture.md
- @docs/data-model.md
- @docs/ingestion-pipeline.md
- @specs/README.md
