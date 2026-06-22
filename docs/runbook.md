# Keel Backend — Runbook (local dev + verify)

## Prerequisites

- Docker + Docker Compose (the supported path on this machine — Python is not installed locally).
- An OpenAI API key for the AI features (the app boots without it; AI calls fail clearly until set).

> **Verification status:** This backend was authored without a runnable local Python or a running Docker daemon in the authoring session. It is correct **by construction** (import-safe, lazy external clients). Run the steps below to verify on your machine. Nothing here has been executed for you — treat the first `docker compose up` as the real smoke test.

## 1. Configure env

```bash
cp .env.example .env
# edit .env: set OPENAI_API_KEY, JWT_SECRET_KEY, POSTGRES_* etc. (.env.example documents every var)
```

## 2. Bring up infrastructure

```bash
# infra only (Postgres, Qdrant, Neo4j, Redis, MinIO)
docker compose up -d postgres qdrant neo4j redis minio
docker compose ps          # all healthy?
```

## 3. Run the full stack (api + worker + infra)

```bash
docker compose --profile full up --build
```

The `api` container runs `alembic upgrade head` on start (entrypoint), then `uvicorn`. The `worker` container runs the Celery ingestion worker.

## 4. Smoke checks

```bash
curl http://localhost:8000/health
# -> {"status":"ok", ...}

# Seed a demo admin + workspace
docker compose exec api python -m scripts.seed_admin
```

Open API docs: http://localhost:8000/docs

## 5. Run the §21 demo flow

1. `POST /api/auth/register` → returns `{access_token, user, workspace}` (+ refresh cookie).
2. `GET /api/dashboard` with the access token.
3. `POST /api/ingest/file` (multipart PDF) → `{document_id, job_id, status:"queued"}`; poll `GET /api/ingest/status/{job_id}`.
4. After `completed`: `GET /api/documents`, edit tags via `PATCH /api/documents/{id}/tags`.
5. `POST /api/chat/query` (SSE) — streamed answer + confidence + evidence.
6. Create an API key (`POST /api/apikeys`), then `POST /api/chat` with `Authorization: Bearer <key>`.
7. `POST /api/ingest/text` → `GET /api/ingest/status/{job_id}` → `completed`.

## 6. Local (non-Docker) quality gates — once Python 3.12 is installed

```bash
python -m venv .venv && source .venv/bin/activate   # (Windows: .venv\Scripts\activate)
pip install -e ".[dev]"
ruff check . && ruff format --check .
mypy app
pytest                       # unit tests mock all adapters; no external services needed
uvicorn app.main:app --reload
celery -A app.celery_app.celery worker -Q ingestion -c 4
```

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `docker info` fails | Docker Desktop daemon not running — start it. |
| AI endpoints 502/`UPSTREAM_AI_ERROR` | `OPENAI_API_KEY` unset/invalid in `.env`. |
| Qdrant/Neo4j connection refused | Dependency not up yet; `docker compose up -d` them first; `startup.py` retries collection/constraint creation. |
| 401 on an app route | Missing/expired access JWT — call `POST /api/auth/refresh` (refresh cookie). |
| 401 on a dual-auth route | Missing/invalid JWT **and** no valid API key. |
| 429 on `/api/*` | Rate limit (100/min/key) — honor `Retry-After`. |
| Migration drift | `alembic revision --autogenerate -m "..."` then review before commit. |

## Ports

| Service | Port |
|---|---|
| API | 8000 |
| PostgreSQL | 5432 |
| Qdrant | 6333 (http) / 6334 (grpc) |
| Neo4j | 7474 (http) / 7687 (bolt) |
| Redis | 6379 |
| MinIO | 9000 (api) / 9001 (console) |
