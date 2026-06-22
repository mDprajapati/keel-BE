---
description: Run all backend merge gates (format, lint, types, tests, import + boot smoke)
---

Run the backend quality gates in order and report a concise pass/fail summary. Stop at the first hard failure and show the actionable output.

1. **Format** — `ruff format --check .` → verify: no files would be reformatted.
2. **Lint** — `ruff check .` → verify: 0 errors (incl. `T201` no-print).
3. **Types** — `mypy app` → verify: 0 errors.
4. **Tests** — `pytest -q` → verify: all green (adapters mocked; no external services needed).
5. **Import smoke** — `python -c "import app.main"` → verify: app package imports with no env/secrets set (lazy clients).
6. **Boot smoke (optional, needs Docker)** — `docker compose --profile full up --build -d && curl -fsS localhost:8000/health` → verify: `{"status":"ok"}`; then `docker compose down`.

If Python is not installed locally, run steps 1–5 inside the API image: `docker compose run --rm api sh -lc "ruff format --check . && ruff check . && mypy app && pytest -q && python -c 'import app.main'"`.

Report: a table of gate → status, and for any failure the exact command + first lines of output.
