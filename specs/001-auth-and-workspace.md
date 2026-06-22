# Spec 001 — Auth & workspace

- **Status:** Not started
- **Spec source:** v3 §6, §17.1 · timeline: Phase 1 (org/ws/user models) + Phase 3 (auth endpoints, refresh rotation, deps)
- **Success criteria covered:** §21.1, §21.2
- **Owner:** <unassigned>

## Context / intent

Atomic org signup, JWT login with refresh rotation, and the session/auth dependencies the rest of the API builds on. Email verification and MFA are **skeleton columns only** (deferred).

## In scope

- Models: `organizations`, `workspaces`, `users`, `organization_members` (each row carries `workspace_id`).
- `POST /api/auth/register` — one transaction: user + org + workspace + admin member; bcrypt(12); returns `{access_token, user, workspace}` + refresh cookie.
- `POST /api/auth/login` — validate, lockout (10/15 min), issue access JWT (15 min) + rotate refresh (30 d HttpOnly cookie).
- `POST /api/auth/refresh` (cookie) → new `{access_token, user, workspace}`; `POST /api/auth/logout` → 204; `GET /api/auth/me` → `{user, workspace}`.
- `app/core/deps.py`: `get_current_user`, `require_admin`, `get_principal` (JWT or API key); `app/core/security.py` crypto.

## Out of scope / deferred

- Email verification (§6.2) — `users.is_verified` column, no flow.
- MFA (§6.3) — `users.mfa_enabled` column, no challenge.
- SSO/OIDC (§14.4).

## Endpoints / modules touched

- `app/api/auth.py`, `app/services/auth_service.py`, `app/core/{security,deps}.py`, `app/models/{organization,workspace,user,organization_member}.py`, `app/schemas/auth.py`.

## Acceptance criteria

1. **(§21.1)** Register creates user+org+workspace+admin member atomically; first user is Admin; password hashed (bcrypt 12). Rollback on any failure.
2. **(§21.2)** Login returns a 15-min access JWT in the body + sets the refresh cookie; `me` returns the session; no email-verify gate.
3. 10 failed logins / 15 min → `423/`lockout for that email for 15 min.
4. Refresh rotates the token; a reused/expired refresh → `401 UNAUTHENTICATED`.
5. `User.role ∈ {admin, standard}`; shapes match `keel-UI` (`full_name`, `last_active_at`, `Workspace{id,name,organization_name}`).

## Dependencies

- 000.

## Relevant rules

- `.claude/rules/security.md`, `.claude/rules/database.md`, `.claude/rules/api.md`

## Traceability

| AC | Code path(s) | Test path(s) | Status |
|---|---|---|---|
| 1 | `app/services/auth_service.py` | `tests/test_auth.py::test_register_atomic` | ☐ |
| 2,4 | `app/api/auth.py`, `app/core/security.py` | `tests/test_auth.py` | ☐ |
| 3 | `app/services/auth_service.py` | `tests/test_auth.py::test_lockout` | ☐ |
