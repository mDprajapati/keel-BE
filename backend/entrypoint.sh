#!/usr/bin/env bash
# API container entrypoint: run migrations (best-effort, idempotent) then serve.
set -euo pipefail

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  echo "[entrypoint] alembic upgrade head"
  # Fail fast: with `set -e`, a failed migration aborts startup rather than booting a
  # schema-less app that would serve 500s. Compose gates this on Postgres being healthy.
  alembic upgrade head
fi

echo "[entrypoint] starting uvicorn"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers
