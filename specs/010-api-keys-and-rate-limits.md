# Spec 010 — API keys & rate limits

- **Status:** Not started
- **Spec source:** v3 §13.3–§13.4 · timeline: Phase 3 (api_key model, generate/scope, list/revoke, rate-limit middleware)
- **Success criteria covered:** §21.12
- **Owner:** <unassigned>

## Context / intent

Workspace-scoped API keys that authorize the dual-auth surface, plus the sliding-window rate limiter.

## In scope

- `api_keys` model: `key_hash`, `key_prefix`, `scope ∈ {read_only, read_write}`, `rate_limit_per_minute`, `last_used_at`, `request_count`, `revoked`.
- `GET /api/apikeys` → `ApiKey[]`; `POST /api/apikeys` `{name, scope}` → `ApiKey & {secret}` (secret once); `DELETE /api/apikeys/{id}` → 204. Admin-gated.
- API-key authentication in `get_principal`: hash incoming → lookup → check `revoked`/scope → set `last_used_at`/`request_count`.
- Rate-limit (Redis sliding window) 100/min/key → `429` + `Retry-After`; configurable per key.

## Out of scope / deferred

- Granular scopes beyond read/write (§14.4).

## Endpoints / modules touched

- `app/api/apikeys.py`, `app/core/{security,rate_limit,deps}.py`, `app/models/api_key.py`, `app/schemas/api_key.py`.

## Acceptance criteria

1. **(§21.12)** Admin generates a key (secret shown once, never again), names + scopes it, lists keys (no secret), and revokes it (subsequent use → `401`).
2. Rate limit returns `429` + `Retry-After` after 100/min; under limit succeeds.
3. Only the `key_hash` + `key_prefix` persist; raw secret is never stored or logged.
4. `read_only` keys are rejected on ingestion endpoints.

## Dependencies

- 001 (admin), Redis.

## Relevant rules

- `.claude/rules/security.md`, `.claude/rules/api.md`

## Traceability

| AC | Code path(s) | Test path(s) | Status |
|---|---|---|---|
| 1,3 | `app/api/apikeys.py`, `app/core/security.py` | `tests/test_api_keys.py` | ☐ |
| 2 | `app/core/rate_limit.py` | `tests/test_rate_limit.py` | ☐ |
