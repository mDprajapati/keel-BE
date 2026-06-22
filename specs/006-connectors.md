# Spec 006 — Connectors

- **Status:** Not started
- **Spec source:** v3 §10 · timeline: Phase 3 (BaseConnector, Google Drive OAuth, folders, file-select, sync, OneDrive stub)
- **Success criteria covered:** §21.7
- **Owner:** <unassigned>

## Context / intent

Google Drive connector (OAuth 2.0 auth-code), manual file selection, manual sync through the **same** ingestion pipeline. OneDrive is a coming-soon stub.

## In scope

- `BaseConnector` interface + `connectors` + `connector_credentials` (encrypted refresh token) models.
- `GET /api/connectors` → `Connector[]`.
- `POST /api/connectors/{type}/oauth/start` → `{authorization_url?}` (real flow) or `{connected:true}`; backend token exchange + encrypted store.
- `GET /api/connectors/{id}/folders` → `ConnectorFolderNode[]` (browse tree).
- `POST /api/connectors/{id}/sync` `{file_ids}` → fetch selected bytes → storage → `documents(source_type=google_drive)` → enqueue. Skip logic: same `external_document_id`+mtime, unsupported MIME, >500 MB.
- `DELETE /api/connectors/{id}` → revoke creds, mark disconnected (synced docs remain).
- OneDrive: stub returning `coming_soon`.

## Out of scope / deferred

- Scheduled sync, Slack/SharePoint/Notion/Confluence, source ACL sync (Phase 2/3).

## Endpoints / modules touched

- `app/api/connectors.py`, `app/services/connectors/{base,google_drive,onedrive}.py`, `app/models/{connector,connector_credential}.py`.

## Acceptance criteria

1. **(§21.7)** Connect GD (OAuth), list folders, select files, trigger sync → ≥1 document fetched and ingested via the standard pipeline (`source_type=google_drive`).
2. Sync skips already-synced (id+mtime), unsupported MIME, and >500 MB files (logged).
3. Disconnect revokes credentials and marks `disconnected`; previously synced docs persist.
4. OneDrive shows `coming_soon`; mutations on it are inert.
5. Refresh tokens are encrypted at rest and never logged.

## Dependencies

- 003 (storage + pipeline), 001 (admin).

## Relevant rules

- `.claude/rules/security.md`, `.claude/rules/api.md`

## Traceability

| AC | Code path(s) | Test path(s) | Status |
|---|---|---|---|
| 1 | `app/services/connectors/google_drive.py` | `tests/test_connectors.py` | ☐ |
| 2 | `app/services/connectors/base.py` | `tests/test_connectors.py::test_skip` | ☐ |
