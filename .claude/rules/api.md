# Rule: API routers

Source: contract authority `../keel-UI`; v3 §13; `docs/api-contract.md`.

## Shape discipline

- One prefix: `/api`. Match `keel-UI` paths and JSON shapes **verbatim** (`docs/api-contract.md`). snake_case fields.
- Routers are thin: validate with a Pydantic schema → call a **service** → return a schema. No business logic, no DB queries, no SDK calls in a router.
- Errors: raise an `AppError` subclass from `app/core/errors.py`; the central handler emits `{error_code, message, request_id}`. Never return ad-hoc error dicts.

## Auth selection

- App-only routes depend on `get_current_user` (or `require_admin`).
- Dual-auth routes (v3 §13: `/search`, `/context`, `/chat`, `GET /documents`, `/evidence/{id}`, `/ingest/*`, `/ingest/status/{id}`) depend on `get_principal` (JWT **or** API key) + `rate_limit` (key only). Enforce `read_write` scope on ingestion.
- Unauthenticated: `/auth/login|register|refresh`, `/health`.

## Async & long work

- Ingestion endpoints return `202`-style `{document_id, job_id, status}` immediately and enqueue a Celery task — never parse/embed in the request.
- Chat streaming uses `StreamingResponse` with `media_type="text/event-stream"`, frames `data: <json>\n\n` (`token`* then `done`). Persist `chat_messages` after the stream closes.
- Pagination: `page`/`limit` (default 50, max 200); list responses that the FE types as `Paginated<T>` return `{data, total, page, limit}` (documents, conversations, messages). Plain arrays where the FE types an array (apikeys, connectors, admin/users).
