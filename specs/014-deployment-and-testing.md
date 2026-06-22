# Spec 014 — Deployment & testing

- **Status:** Not started
- **Spec source:** v3 §20–§21 · timeline: Phase 4 (integration, testing, hardening, deployment, seed)
- **Success criteria covered:** all of §21 (E2E)
- **Owner:** <unassigned>

## Context / intent

Wire the §21 demo flow end-to-end, harden security paths, and make the stack deployable + seedable.

## In scope

- `docker compose --profile full` deploy; `docker/entrypoint.sh` runs `alembic upgrade head` on API start.
- `scripts/seed_admin.py` (+ demo data) for the dress rehearsal.
- Tests: ingestion pipeline (call the runner directly), retrieval + chat + **workspace isolation**, auth + admin-permission, REST search/context/chat/ingest, gateway singleton + token_usage. Mock at adapter boundaries.
- Hardening: security review of auth/rate-limit/CORS; perf note for 500 MB / 1000-page / HNSW `ef` tuning.

## Out of scope / deferred

- k8s, multi-region, billing (later phases).

## Endpoints / modules touched

- `docker-compose.yml`, `docker/entrypoint.sh`, `scripts/seed_admin.py`, `tests/**`.

## Acceptance criteria

1. `/verify` passes: format, lint, mypy, pytest, `import app.main`.
2. `docker compose --profile full up` → migrations applied, `/health` ok, worker consuming the `ingestion` queue.
3. `seed_admin` creates an admin + workspace; the §21 flow runs end-to-end against the running stack.
4. Workspace-isolation tests prove no cross-workspace leakage on every retrieval path.

## Dependencies

- All specs.

## Relevant rules

- `.claude/rules/testing.md`, `.claude/rules/security.md`

## Traceability

| AC | Code path(s) | Test path(s) | Status |
|---|---|---|---|
| 1 | `.claude/commands/verify.md` | CI / local | ☐ |
| 3 | `scripts/seed_admin.py` | `tests/test_e2e_smoke.py` | ☐ |
| 4 | `app/services/vector_store.py` | `tests/test_isolation.py` | ☐ |
