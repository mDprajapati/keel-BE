# Keel Backend — Architecture

## Services (docker-compose)

```
┌─────────────┐     ┌──────────────┐
│  FastAPI    │     │ Celery worker│   (queue: ingestion, concurrency 4)
│  (api)      │     │ (worker)     │
└──────┬──────┘     └──────┬───────┘
       │  shared code (app/)│
       ▼                    ▼
  PostgreSQL 16   Redis    Qdrant    Neo4j    MinIO (S3)
  (relational)   (broker/  (vectors, (graph,  (raw files)
                  result)   HNSW)     Cypher)
                                ▲
                                └── OpenAI (embeddings + chat + NER) via llm_gateway only
```

The **api** and **worker** containers run the same `app/` package. The API enqueues Celery tasks; the worker executes the ingestion pipeline. Both open their own DB sessions.

## Package layout

```
app/
  main.py            # app factory: middleware (RequestID, CORS), exception handlers, /health, router mount
  config.py          # pydantic-settings; all env; SecretStr for secrets
  logging.py         # structlog setup (no PII, request correlation)
  database.py        # async engine + session factory + get_db
  celery_app.py      # Celery app, 'ingestion' queue, retry/backoff/timeouts
  core/
    deps.py          # get_db, get_current_user (JWT), require_admin, get_api_principal (API key)
    security.py      # ONLY crypto: bcrypt, JWT create/decode, api-key hash
    errors.py        # AppError hierarchy + error_code constants
    rate_limit.py    # sliding-window limiter (Redis) for API keys
  models/            # SQLAlchemy ORM (one concern per file)
  schemas/           # Pydantic DTOs (request/response) — never expose ORM directly
  services/
    ai/
      llm_gateway.py # ONLY OpenAI client; call_llm(), embed() + token bucket
      usage.py       # token_usage logging helper (mandatory on every call)
      tagging.py     # LLM tag generation (first 2000 tokens)
      ner.py         # LLM NER + relationship extraction (7 entities)
    vector_store.py  # Qdrant adapter (collection init, upsert, search w/ workspace filter)
    graph_store.py   # Neo4j adapter (MERGE node/edge, constraints, 1-hop lookup)
    storage.py       # object storage adapter (local + S3), multipart assembly
    parsing.py       # Docling adapter (streaming >50MB)
    chunking.py      # token-based + format-specific chunkers
    retrieval_service.py  # embed query + Qdrant search + graph augment + context assembly
    chat_service.py       # prompt construction + call_llm + confidence + evidence
    dashboard_service.py  # counters + feeds
    ingestion/
      worker_flow.py # resumable step runner; updates ingestion_status per step
      steps.py       # the 16 pipeline steps
  tasks/
    ingestion.py     # Celery task -> worker_flow.run()
  api/             # ALL endpoints under one /api prefix (matches keel-UI)
    router.py      # aggregates the routers below
    auth.py        # register/login/refresh/logout/me (JWT + refresh cookie)
    documents.py   # list (dual auth), tags/reprocess/delete (JWT)
    ingest.py      # /ingest/file|part|text|record, /ingest/status (dual auth)
    conversations.py  # list + messages (JWT)
    chat.py        # /chat/query SSE (JWT) + /chat non-stream (dual auth)
    search.py      # /search, /context, /evidence (dual auth — v3 §13)
    apikeys.py connectors.py admin_users.py dashboard.py model.py settings.py mcp.py
  startup.py         # idempotent init: Qdrant collection + Neo4j constraints
migrations/          # Alembic (relational only)
scripts/seed_admin.py
tests/
```

## Request lifecycle

1. `RequestIDMiddleware` assigns/propagates `X-Request-ID`; bound into structlog context.
2. Router validates with a Pydantic schema.
3. Auth dependency resolves a `Principal {workspace_id, user_id?, api_key_id?, scope}`:
   - App-only routes → `get_current_user` (decode JWT, check active) / `require_admin`.
   - Dual-auth routes (v3 §13 surface) → `get_principal`: try JWT, else hash the incoming key and look up `api_keys` (check scope), then apply the per-key `rate_limit`.
4. Router calls a **service**. Services own transactions and call adapters.
5. Errors raise `AppError` → central handler returns `{error_code, message, request_id}` with the right status.

## Adapter boundary (why)

`vector_store` / `graph_store` / `storage` / `llm_gateway` are thin adapters so the engine can change without touching the pipeline (Qdrant→Pinecone, Neo4j→AuraDB, MinIO→S3) and so tests mock one seam. **All external SDK construction happens here and nowhere else.**

## Boot-time safety (error-free import)

External clients (OpenAI, Qdrant, Neo4j, S3) are constructed **lazily** on first use, not at import. The app therefore imports and `/health` responds even when secrets/services are absent. `startup.py` runs idempotent collection/constraint creation on API startup and tolerates a not-yet-ready dependency (logged, retried by the caller path). This is what makes `docker build` + a bare `import app.main` succeed without credentials.

## Configuration profiles

- `STORAGE_BACKEND=local|s3` switches the storage adapter.
- `CELERY_INGESTION_CONCURRENCY` (default 4), task timeouts 30/90 min.
- `CONTEXT_MAX_TOKENS` (default 8000), `CHAT_TOP_K` (default 10, max 25), `MIN_SIMILARITY` (default 0.65).
- Embedding model + dims are fixed per workspace at creation (no runtime switch).
