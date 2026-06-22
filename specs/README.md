# Keel Backend MVP — Feature Specs

Per-feature specs decomposing the authoritative scope ([`../docs/spec/SCOPE.md`](../docs/spec/SCOPE.md), mirroring `Keel_MVP_Scope_Document_v3`) and the **BE** + **AI** delivery timelines into implementable backend units. Each spec maps to v3 §18 in-scope items, cites the v3 §21 success-criteria step(s) it satisfies, and names the timeline rows it covers.

Contract authority for paths/shapes: **`../keel-UI`** (see [`../docs/api-contract.md`](../docs/api-contract.md)).

## Status legend

`Not started` · `In progress` · `Done` — set in each spec header and reflected in [`TRACEABILITY.md`](./TRACEABILITY.md).

## Spec index

| # | Spec | v3 § | Timeline phase | §21 | Depends on |
|---|---|---|---|---|---|
| 000 | [foundation-and-infra](./000-foundation-and-infra.md) | §20 | Phase 0 (BE+AI) | — | — |
| 001 | [auth-and-workspace](./001-auth-and-workspace.md) | §6, §17.1 | Phase 1 + 3 | 1, 2 | 000 |
| 002 | [users-and-permissions](./002-users-and-permissions.md) | §14 | Phase 3 | 11 | 001 |
| 003 | [data-and-upload](./003-data-and-upload.md) | §8 | Phase 1 | 4 | 001 |
| 004 | [ingestion-pipeline](./004-ingestion-pipeline.md) | §9.1–§9.3 | Phase 1–2 (AI) | 5 | 003, 013 |
| 005 | [vector-and-graph](./005-vector-and-graph.md) | §9.4–§9.5 | Phase 1–2 (AI) | 5 | 004, 013 |
| 006 | [connectors](./006-connectors.md) | §10 | Phase 3 | 7 | 003 |
| 007 | [chat-and-retrieval](./007-chat-and-retrieval.md) | §12, §17.3 | Phase 2 | 8 | 005 |
| 008 | [rest-retrieval](./008-rest-retrieval.md) | §13.1 | Phase 2 | 9 | 005, 010 |
| 009 | [rest-ingestion](./009-rest-ingestion.md) | §13.2 | Phase 1–3 | 10 | 004, 010 |
| 010 | [api-keys-and-rate-limits](./010-api-keys-and-rate-limits.md) | §13.3–§13.4 | Phase 3 | 12 | 001 |
| 011 | [dashboard](./011-dashboard.md) | §7 | Phase 3 | 3 | 003 |
| 012 | [model-and-settings](./012-model-and-settings.md) | §11, §15 | Phase 3 | — | 001 |
| 013 | [ai-gateway-and-usage](./013-ai-gateway-and-usage.md) | §9.4, §11 | Phase 0 (AI) | — | 000 |
| 014 | [deployment-and-testing](./014-deployment-and-testing.md) | §20–§21 | Phase 4 | all | all |

## Dependency order

```
000 (foundation) ─▶ 013 (AI gateway) ─▶ 004 (pipeline) ─▶ 005 (vector+graph) ─▶ 007 (chat) ─▶ 008 (REST retrieval)
   └─▶ 001 (auth) ─┬▶ 002 (users)  ├▶ 003 (data/upload) ─▶ 006 (connectors)
                   ├▶ 010 (api keys) ─▶ 009 (REST ingestion)
                   ├▶ 011 (dashboard)
                   └▶ 012 (model/settings)
014 (deploy/test) closes the §21 demo flow.
```

## Conventions

- One spec per area; `NNN-kebab-name.md` from [`_template.md`](./_template.md).
- Acceptance criteria are backend-assertable (HTTP behaviour, DB state, pipeline transitions) with pytest.
- Traceability paths use `app/...` and `tests/...`.
- Scope is fixed by v3; deferred items are listed explicitly so they are not built (email verify, MFA, SHA-256 dedup, Document Detail View, multi-hop GraphRAG, trust score, role/doc-level retrieval — all skeleton/deferred).
