# Spec 000 — Foundation & infra

- **Status:** Not started
- **Spec source:** v3 §20 · timeline: Phase 0 (BE: dev env, core scaffolding, Celery skeleton; AI: gateway shell)
- **Success criteria covered:** enables all of §21
- **Owner:** <unassigned>

## Context / intent

Stand up the runnable skeleton: infra via docker-compose, config/logging/db scaffolding, the FastAPI app factory with the error envelope + `/health`, and the Celery skeleton. Everything imports and boots with no secrets/services (lazy clients).

## In scope

- `docker-compose.yml`: Postgres 16, Qdrant, Neo4j, Redis, MinIO + `api` and `worker` (profile `full`); healthchecks.
- `pyproject.toml` (deps + ruff/mypy/pytest config), `alembic.ini`, `.env.example`, `Dockerfile`, `docker/entrypoint.sh` (runs `alembic upgrade head` then uvicorn).
- `app/config.py` (pydantic-settings, `SecretStr`), `app/logging.py` (structlog, no PII, request id), `app/database.py` (async engine + `get_db`).
- `app/main.py` (app factory, RequestID + CORS middleware, exception handlers → envelope, `/health`, router mount).
- `app/celery_app.py` (`ingestion` queue, 3 retries base 30s×2, 30/90-min timeouts), `ingestion_errors` dead-letter helper.

## Out of scope / deferred

- pgvector / AGE extensions (vectors→Qdrant, graph→Neo4j).
- k8s (infra phase).

## Endpoints / modules touched

- `GET /health`; `app/{config,logging,database,main,celery_app}.py`; `docker-compose.yml`; `Dockerfile`.

## Acceptance criteria

1. `import app.main` succeeds with **no** env vars set (lazy external clients).
2. `GET /health` → `200 {"status":"ok"}`.
3. `docker compose --profile full up` brings up all services healthy; `api` runs migrations on start.
4. Any unhandled error returns `{error_code, message, request_id}` with a correlated `request_id`.
5. `print()` is blocked (ruff `T201`); structlog emits no PII.

## Dependencies

- External: Docker. No other spec.

## Relevant rules

- `.claude/rules/database.md`, `.claude/rules/security.md`, `.claude/rules/api.md`

## Traceability

| AC | Code path(s) | Test path(s) | Status |
|---|---|---|---|
| 1,2 | `app/main.py` | `tests/test_health.py` | ☐ |
| 4 | `app/core/errors.py`, `app/main.py` | `tests/test_errors.py` | ☐ |
