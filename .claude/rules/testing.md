# Rule: Testing

Source: `Keel-MVP-Timeline-backend` + `Keel-MVP-Timeline 4-AI-changes` (Testing rows), v3 §21.

- **Ingestion pipeline:** test `worker_flow.run(...)` / the step coroutines **directly**, not `.delay()`. Assert status transitions in order, chunks carry `workspace_id`, transient errors retry+resume, permanent errors dead-letter.
- **Workspace isolation is the hard boundary:** every retrieval/search test asserts no cross-workspace leakage (data from workspace B never returned to a principal in workspace A).
- **Mock at the adapter boundary:** `llm_gateway`, `storage`, `vector_store`, `graph_store`. Unit tests never hit real OpenAI/Qdrant/Neo4j/S3.
- **Auth & permissions:** for each protected behaviour, one 4xx test (bad input) and one permission-denied test (standard user on an admin route; `read_only` key on an ingestion route).
- **Contract tests:** assert response JSON matches the `keel-UI` shapes in `docs/api-contract.md` (field names + enums).
- Tests must pass with **no external services running** (everything mocked). `pytest` is green on a clean checkout.
