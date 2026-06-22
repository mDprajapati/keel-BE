# Spec 013 — AI gateway & token usage

- **Status:** Not started
- **Spec source:** `Keel-MVP-Timeline 4-AI-changes` Phase 0 · v3 §9.4, §11
- **Success criteria covered:** underpins §21.5, §21.6, §21.8
- **Owner:** <unassigned>

## Context / intent

The single seam to OpenAI: `call_llm` + `embed`, with the **mandatory** `token_usage` logging on every call. Everything AI flows through here (tagging, NER, chat, embeddings).

## In scope

- `app/services/ai/llm_gateway.py`: the **only** OpenAI client (lazy singleton). `call_llm(messages, *, workspace_id, operation, model=None)`; `embed(texts, *, workspace_id, model=None)` — batches of 100 behind a token-bucket rate limiter (`EMBED_MAX_RPM`).
- `app/services/ai/usage.py`: write a `token_usage` row (`workspace_id, operation, model, prompt_tokens, completion_tokens, total_tokens, cost_usd, request_id, created_at`) on **every** call; cost from a per-model price table.
- `tagging.py` (first 2000 tokens → ≤20 lowercased tags) and `ner.py` use `call_llm`.
- `token_usage` model + migration.

## Out of scope / deferred

- Multi-provider gateway, runtime model switching beyond chat (Phase 3).

## Endpoints / modules touched

- `app/services/ai/{llm_gateway,usage,tagging,ner}.py`, `app/models/token_usage.py`.

## Acceptance criteria

1. No module outside `llm_gateway.py` constructs an OpenAI client or imports `openai` (enforced by a test that greps the tree).
2. Every `call_llm`/`embed` writes exactly one `token_usage` row with all mandatory fields; the row's `workspace_id`/`operation` are correct.
3. `embed` batches at 100 and respects the rate limiter; transient errors retry, permanent → `UpstreamAIError`.
4. The gateway is import-safe without `OPENAI_API_KEY` (client built on first call).

## Dependencies

- 000.

## Relevant rules

- `.claude/rules/ai-gateway.md`

## Traceability

| AC | Code path(s) | Test path(s) | Status |
|---|---|---|---|
| 1 | `app/services/ai/llm_gateway.py` | `tests/test_gateway_singleton.py` | ☐ |
| 2 | `app/services/ai/usage.py` | `tests/test_token_usage.py` | ☐ |
