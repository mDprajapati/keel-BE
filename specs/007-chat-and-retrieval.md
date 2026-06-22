# Spec 007 — Chat & retrieval

- **Status:** Not started
- **Spec source:** v3 §12, §17.3 · timeline: Phase 2 (retrieval service, graph augment, context assembly, chat service, SSE endpoint, conversation models)
- **Success criteria covered:** §21.8
- **Owner:** <unassigned>

## Context / intent

The RAG flow: embed question → Qdrant top-k → best-effort 1-hop graph augment → assemble context → stream the LLM answer (SSE) → persist with confidence + evidence.

## In scope

- `retrieval_service`: embed query (same model as ingest) → `vector_store.search(workspace_id, top_k=settings, min_score=0.65)` → optional ≤5 graph-augment chunks (best-effort) → context assembly ≤`CONTEXT_MAX_TOKENS` (rank, drop over-cap, no mid-sentence cut).
- `chat_service`: structured prompt + `call_llm` (workspace `chat_model`); confidence = mean top-3 similarity; evidence list.
- `POST /api/chat/query` (SSE): `token`* then `done {confidence, evidence, conversation_id}`; persist `chat_messages` (user+assistant) after stream.
- `GET /api/conversations` + `GET /api/conversations/{id}/messages` (`Paginated`).
- Models: `conversations`, `chat_messages`.

## Out of scope / deferred

- Trust score (§12.4). Multi-hop GraphRAG (§9.5). Shared conversations (§12.5).

## Endpoints / modules touched

- `app/api/{chat,conversations}.py`, `app/services/{retrieval_service,chat_service}.py`, `app/models/{conversation,chat_message}.py`, `app/schemas/chat.py`.

## Acceptance criteria

1. **(§21.8)** A question streams an answer via SSE; the final `done` frame carries `confidence` (mean top-3) + `evidence[]` (exact `EvidenceChunk` shape); the exchange is persisted and appears in history.
2. Retrieval filters by `workspace_id` and `min_score`; context never exceeds the cap and is not cut mid-sentence.
3. Graph augmentation failure does **not** fail the chat (best-effort).
4. No field named `trust_score` is ever emitted.
5. A `standard` user can chat over all workspace data (retrieval not role-restricted).

## Dependencies

- 005 (vector+graph), 013 (gateway).

## Relevant rules

- `.claude/rules/ai-gateway.md`, `.claude/rules/api.md`, `.claude/rules/testing.md`

## Traceability

| AC | Code path(s) | Test path(s) | Status |
|---|---|---|---|
| 1 | `app/api/chat.py`, `app/services/chat_service.py` | `tests/test_chat.py` | ☐ |
| 2,3 | `app/services/retrieval_service.py` | `tests/test_retrieval.py` | ☐ |
