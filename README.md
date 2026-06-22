# Keel Backend — Enterprise Context & Trust Platform

Python 3.12 / FastAPI backend for **Keel**. Organizations upload or connect enterprise data, an async Celery pipeline parses → tags → chunks → embeds → maps a graph, results are stored in **Qdrant** (vectors) + **Neo4j** (graph), and users retrieve evidence-backed answers via **Chat (SSE)** and a **REST API**.

> **Contract authority:** the real frontend at [`../keel-UI`](../keel-UI). Endpoint paths and JSON shapes match it verbatim — see [`docs/api-contract.md`](docs/api-contract.md). (`../keel-frontend` is an earlier prototype; ignore it.)
>
> **Driven by:** `Keel_MVP_Scope_Document_v3` (scope), `Keel-MVP-Timeline-backend` (BE tasks), `Keel-MVP-Timeline 4-AI-changes` (AI tasks).

## Stack

FastAPI · Celery + Redis · PostgreSQL 16 (SQLAlchemy 2.0 async + Alembic) · Qdrant Community (HNSW) · Neo4j Community · MinIO/S3 · Docling · OpenAI (`text-embedding-3-small`, `gpt-4o-mini`/`gpt-4o`) · JWT + bcrypt.

## Quick start (Docker — the supported path)

```bash
cp .env.example .env          # set OPENAI_API_KEY + JWT_SECRET_KEY at minimum
docker compose --profile full up --build
curl http://localhost:8000/health        # {"status":"ok"}
# API docs: http://localhost:8000/docs
docker compose exec api python -m scripts.seed_admin   # demo admin + workspace
```

Infra only (run api/worker locally):

```bash
docker compose up -d postgres qdrant neo4j redis minio
uvicorn app.main:app --reload
celery -A app.celery_app.celery worker -Q ingestion -c 4
```

## Layout

| Path | What |
|---|---|
| `app/` | FastAPI app (`config`, `database`, `main`, `core/`, `models/`, `schemas/`, `services/`, `api/`, `tasks/`) |
| `migrations/` | Alembic (relational only) |
| `scripts/seed_admin.py` | demo seed |
| `tests/` | pytest (adapters mocked; no services needed) |
| `docs/` | architecture, API contract, data model, ingestion pipeline, runbook, scope |
| `specs/` | per-feature specs (000–014) ⇄ v3 §21 |
| `AGENTS.md` / `CLAUDE.md` / `.claude/` | conventions, hard rules, dev gates |

## The two things that keep this correct

1. **`workspace_id` is the hard tenant boundary** — on every row and every Qdrant search filter.
2. **One OpenAI client** (`app/services/ai/llm_gateway.py`) and a **`token_usage` row on every call**.

See [`AGENTS.md`](AGENTS.md) for the full rule set and [`docs/runbook.md`](docs/runbook.md) to verify locally.

## Status

Phased build per the timelines. Code is import-safe and boots without secrets/services (lazy external clients); fill in AI/parse internals per `specs/`. Run gates with `/verify` (or `docker compose run --rm api sh -lc "ruff check . && mypy app && pytest -q"`).
