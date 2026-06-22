# Traceability — backend specs ⇄ v3 §21 success criteria

Updated as features are built (`/verify` + review). A spec is `Done` only when every acceptance criterion has a passing test.

| §21 step | Demo behaviour | Spec(s) | Status |
|---|---|---|---|
| 1 | Org signup, first user = Admin | 001 | ☐ |
| 2 | Login (no email-verify), JWT issued | 001 | ☐ |
| 3 | Dashboard counters within 5s | 011 | ☐ |
| 4 | Upload large PDF, progress, auto-ingest | 003, 009 | ☐ |
| 5 | Pipeline completes: parsed/chunked/embedded; entities in graph | 004, 005, 013 | ☐ |
| 6 | AI tags visible + editable | 003, 013 | ☐ |
| 7 | Google Drive connect → folder → file-select → manual sync | 006 | ☐ |
| 8 | Standard user chats: streamed answer + confidence + evidence | 007 | ☐ |
| 9 | Same question via `POST /api/chat` with API key | 008, 010 | ☐ |
| 10 | `POST /api/ingest/text` → status `completed` | 009 | ☐ |
| 11 | Admin user mgmt: invite / role / remove | 002 | ☐ |
| 12 | API keys generate / scope / revoke | 010 | ☐ |
| — | Infra up, migrations, seed, all gates green | 000, 014 | ☐ |

## Cross-cutting invariants (asserted across specs)

| Invariant | Source | Spec(s) |
|---|---|---|
| `workspace_id` filter on every Qdrant search | v3 §9.4 / AI timeline | 005, 007, 008 |
| `token_usage` row on every LLM/embed call | AI timeline | 013, 004, 007 |
| Confidence = mean top-3 similarity (not trust score) | v3 §12.4 | 007, 008 |
| Graph best-effort (never fails chat/ingest) | v3 §9.5 / AI timeline | 005, 007 |
| Dual auth + 100/min rate limit on §13 surface | v3 §13.3 | 008, 009, 010 |
| Skeleton-not-enforced: dedup, email-verify, MFA | v3 §6.2/§6.3/§9.2 | 001, 004 |
