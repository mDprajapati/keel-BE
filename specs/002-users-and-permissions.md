# Spec 002 — Users & permissions

- **Status:** Not started
- **Spec source:** v3 §14 · timeline: Phase 3 (Users & settings)
- **Success criteria covered:** §21.11
- **Owner:** <unassigned>

## Context / intent

Admin-only user management within a workspace. Roles gate **admin actions only** — never retrieval (v3 §4, §12.3).

## In scope

- `GET /api/admin/users` → `User[]`.
- `POST /api/admin/users/invite` `{email, role}` → `User` (creates an `organization_members` row; invite link pre-fills org — email delivery is out of MVP).
- `PATCH /api/admin/users/{id}/role` `{role}` → `User`.
- `DELETE /api/admin/users/{id}` → 204; **`422 LAST_ADMIN`** if it would remove the last admin (matches `keel-UI`). Removal deletes the membership, not the user account.
- `require_admin` dependency on all of the above.

## Out of scope / deferred

- Document/source-level ACL, role-based retrieval scoping, org hierarchy (all Phase 2/3).

## Endpoints / modules touched

- `app/api/admin_users.py`, `app/services/user_service.py`, `app/models/organization_member.py`, `app/schemas/user.py`.

## Acceptance criteria

1. **(§21.11)** Admin invites a user, changes role, removes a user; list reflects each change.
2. A `standard` user calling any admin endpoint → `403`.
3. Removing the last admin → `422 LAST_ADMIN`; removing a non-last admin/standard → `204`.
4. `role ∈ {admin, standard}`; response shape = `keel-UI` `User`.

## Dependencies

- 001.

## Relevant rules

- `.claude/rules/api.md`, `.claude/rules/security.md`

## Traceability

| AC | Code path(s) | Test path(s) | Status |
|---|---|---|---|
| 1 | `app/api/admin_users.py` | `tests/test_users.py` | ☐ |
| 2 | `app/core/deps.py` | `tests/test_users.py::test_admin_gate` | ☐ |
| 3 | `app/services/user_service.py` | `tests/test_users.py::test_last_admin` | ☐ |
