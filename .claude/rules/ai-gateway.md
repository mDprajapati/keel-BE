# Rule: AI gateway & token usage

Source: `Keel-MVP-Timeline 4-AI-changes`, v3 §9.4–§9.5, §11.

## The single OpenAI client

- The OpenAI client is constructed **only** in `app/services/ai/llm_gateway.py`. No other module may `import openai` or instantiate a client. (Timeline: "Only place an openai client may be constructed.")
- All model access goes through two functions:
  - `call_llm(messages, *, workspace_id, operation, model=None, **kw) -> LLMResult`
  - `embed(texts: list[str], *, workspace_id, model=None) -> list[list[float]]` — batches of **100**, behind a configurable token-bucket rate limiter (max req/min from env).

## Mandatory logging (no exceptions)

Every `call_llm` / `embed` call writes a `token_usage` row **before returning**:
`workspace_id, operation, model, prompt_tokens, completion_tokens, total_tokens, cost_usd, request_id, created_at`.
If you add a new LLM use-case, it must pass `workspace_id` + `operation` — there is no un-logged path. (Timeline: "log workspace/op/model/tokens/cost on every call.")

## Models (fixed vs configurable)

- Embedding model = `text-embedding-3-small` (1536 dims), **fixed at workspace creation**. Changing it invalidates all vectors (no runtime switch).
- Chat model = workspace setting `chat_model ∈ {gpt-4o-mini (default), gpt-4o}` — the **one** runtime-configurable model.
- NER + tagging use the chat-completions model via `call_llm` (operations `ner`, `tagging`).

## Resilience

- `call_llm`/`embed` retry transient errors (rate limit, network) with backoff; raise `UpstreamAIError` (→ envelope `UPSTREAM_AI_ERROR`) on permanent failure.
- The client is built **lazily** on first call so the app imports without `OPENAI_API_KEY` set.
- NER/graph failures are **best-effort** in the pipeline — log and continue, never fail the document.
