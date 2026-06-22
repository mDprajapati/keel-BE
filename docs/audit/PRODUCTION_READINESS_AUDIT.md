# Keel Backend — Production Readiness & Agentic-AI Architecture Audit

**Date:** 2026-06-21
**Auditor roles:** Lead Backend Engineer + Lead AI Engineer (combined audit)
**Subject:** `keel-BE` (FastAPI + Celery + Postgres + Qdrant + Neo4j + OpenAI)
**Reference standard:** [`jamwithai/production-agentic-rag-course`](https://github.com/jamwithai/production-agentic-rag-course)
**Mandate:** Production-system audit + uplift. **Preserve** existing APIs/workflows/FE integrations/AI features/business logic. **Improve** reliability, scalability, maintainability, observability, evaluation. No greenfield redesign; all recommendations backward-compatible unless explicitly flagged.

---

## 0. Method, scope & a load-bearing caveat

**What was read & verified.** Full `app/` tree (66 modules), `tests/` (9 files), `docs/` (architecture, data-model, api-contract, ingestion-pipeline, runbook), `specs/000–014` + `TRACEABILITY.md`, `.claude/rules/*`, `AGENTS.md`, `CLAUDE.md`, `docker-compose.yml`, `Dockerfile`, `pyproject.toml`, and the three timeline source documents (extracted from PDF). Four parallel deep reviews were run (backend foundation, API+services+data-model, AI/RAG subsystem, reference-repo pattern extraction); the two highest-stakes findings (the Celery event-loop crash and broken multi-turn memory) and the dead-letter `None`-deref were re-verified line-by-line against source by the lead.

**The caveat that reframes everything.** Two facts dominate the assessment:

1. **The code has, by its own documentation, never been executed.** `docs/runbook.md` states it was *"authored without a runnable local Python or a running Docker daemon… correct by construction… Nothing here has been executed for you — treat the first `docker compose up` as the real smoke test."*
2. **The project's own `specs/TRACEABILITY.md` shows every success criterion unchecked (`☐`)** — and its rule is *"a spec is Done only when every acceptance criterion has a passing test."*

So this is **not** "harden a running production system." It is **"validate a construction-correct, never-run, exceptionally-well-documented codebase, then harden it."** The single most valuable thing this audit can do is separate *what is genuinely good design* from *what will fail the moment it actually runs* — and there are a few of the latter.

> **Note on `ponytail/`:** the `ponytail/` directory in the repo root is a separate third-party project (its own `.git`, plugin manifests, CI, logo). It is **not** part of the Keel backend and is not wired into `app/`/pyproject/docker. Flagged for cleanup; **not** counted as Keel functionality (in particular it does not count as evaluation infrastructure).

---

## 1. Executive Summary

Keel-BE is a **well-architected, exceptionally well-documented, contract-faithful skeleton with a small number of genuine runtime show-stoppers and three structural AI gaps.** The bones are excellent; the system has simply never been switched on.

**What is genuinely strong (preserve it):**
- **Architecture & layering** — clean `api → services → adapters → models` separation, one OpenAI client (gateway), one crypto module, lazy/import-safe external clients, enums as a single source of truth matching the frontend verbatim.
- **Contract fidelity** — 39 endpoints match `keel-UI` paths/shapes/enums almost perfectly (snake_case, `Paginated{data,total,page,limit}` vs arrays correctly distinguished).
- **Security & tenancy fundamentals** — centralized bcrypt/JWT/API-key crypto, `SecretStr` everywhere, no secrets/PII in logs, HttpOnly rotated refresh tokens, and — verified across all 39 endpoints — `workspace_id` is **always** derived from the authenticated principal, never from input.
- **Mandatory cost discipline** — every `call_llm`/`embed` writes a `token_usage` row with cost. Keel is **stricter than the reference repo** here (the reference logs no cost and has no usage table).
- **Documentation** — among the best seen in any audit: target architecture, data model, API contract, pipeline spec, 15 feature specs, a traceability matrix, and machine-readable rules.

**What will break or underperform when it runs (the actionable core):**

| # | Finding | Severity | Evidence |
|---|---|---|---|
| 1 | **Celery worker crashes on the 2nd document per process** — `asyncio.run()` per task creates a new event loop, but the async DB engine is a module global bound to the first loop (asyncpg connections aren't loop-portable). | **Critical** | `app/tasks/ingestion.py:20`, `app/database.py:22-35` |
| 2 | **Multi-turn chat is broken** — conversation history is persisted but never fed to the LLM; every turn is answered statelessly. | **High** | `app/services/chat_service.py:48-54,178,218` |
| 3 | **Dead-letter safety net can itself crash** — `mark_failed` passes a possibly-`None` job into `_dead_letter`, which dereferences `job.status`. | **High** | `app/services/ingestion/worker_flow.py:72-90,54-69` |
| 4 | **Tokenizer is approximate** — chunk sizes and the 8000-token context cap use a word/char heuristic; `tiktoken` is optional and not installed on the worker. | **Med-High** | `app/services/chunking.py:33-70`, `pyproject.toml` |
| 5 | **No evaluation infrastructure** — zero golden sets / retrieval metrics / faithfulness checks / regression gates. RAG quality regressions are undetectable. | **High (pre-prod)** | absence; `tests/` |
| 6 | **Thin observability** — no metrics, no tracing, shallow `/health`, no latency on `token_usage`, despite documented p95 SLOs (search <3s, chat <10s). | **Medium** | `app/main.py:94`, `app/models/ingestion.py:52-68` |
| 7 | **Graph-augment chunks bypass the similarity threshold**; relationship `MERGE` omits `entity_type` (graph fragmentation); API-key `last_used_at`/`request_count` never updated. | **Medium** | `retrieval_service.py:84-86`, `graph_store.py:79-80`, `deps.py:82-89` |

**Overall posture:** **Strong skeleton, unproven runtime.** Backend ≈ **6.0/10**, AI ≈ **4.5/10** (weighted down by broken memory and absent evaluation). With the Immediate roadmap (≈1–2 focused weeks, all backward-compatible), both rise materially and the §21 demo flow becomes genuinely demonstrable.

**What the reference repo teaches — and what to ignore.** The reference is a single-tenant, Ollama/OpenSearch/Airflow **agentic** course. Keel should **not** adopt LangGraph, RRF hybrid search, Airflow, or word-based chunking — they conflict with Keel's fixed MVP and mandated stack. The genuinely portable ideas are narrow and high-value: **Pydantic structured outputs for LLM decisions, per-stage best-effort tracing, defensive per-step LLM fallbacks, section-aware chunking heuristics, and — above all — the eval harness the reference itself lacks.** Keel is already *more* production-grade than the reference on the two things that matter most (persistent cost logging, workspace tenancy).

---

## 2. Phase 1 — Current State Assessment

### 2.1 Backend architecture (as-built)

**Style:** Modular layered monolith with an async API process and a Celery worker process sharing one `app/` package; PostgreSQL (relational), Qdrant (vectors), Neo4j (graph), Redis (broker/result/rate-limit), MinIO/S3 (objects).

**Request lifecycle:** `RequestIDMiddleware` (`main.py:52-61`) binds `X-Request-ID` into structlog; routers validate via Pydantic, resolve a `Principal` (`core/deps.py`), call a service; services own transactions and call adapters; errors raise `AppError` → central handlers emit `{error_code,message,request_id}` (`main.py:63-90`). All four exception handlers route through one envelope helper; no stack leakage.

**Service boundaries:** Generally clean and thin. Exceptions: `/search` and `/evidence` call adapters/ORM directly in the router (`api/search.py:29-66,98-118`), `/ingest/file` orchestrates storage in the router (`api/ingest.py:44-52`), and `log_api_call` commits the caller's transaction from a helper (`api/common.py:11-21`).

**API design:** One `/api` prefix, two principals (JWT app-only; JWT-or-API-key dual-auth on the §13 surface). Rate limiting correctly applies to API-key calls only. 39 endpoints, contract-faithful.

**Database architecture:** SQLAlchemy 2.0 async; every table has `id`+`created_at`+`updated_at` (`models/base.py:22-32`); every domain row carries `workspace_id`. Enums match `data-model.md`. Skeleton columns present and unenforced (dedup, email-verify, MFA). Minor drift: `users.email` is `String(320)` not `citext`; chunk PK is `id` not `chunk_id`; missing composite `(workspace_id, document_id)` index; `conversations.last_message` in docs but not the model.

**Dependency flow / infra:** Lazy clients make `import app.main` succeed without secrets (`test_app_imports.py`). Celery is correctly configured for a pipeline: `acks_late=True`, `prefetch_multiplier=1`, dedicated `ingestion` queue, 30/90-min timeouts, exp-backoff retry (`celery_app.py`). Migrations run on API container start.

**Backend reliability hot-spots:** the `asyncio.run()`/engine-reuse crash (#1), the `mark_failed` `None`-deref (#3), no graceful shutdown / engine disposal (`main.py:32-38` has no teardown), entrypoint masks migration failure (`docker/entrypoint.sh` `|| echo … continuing` boots a schema-less app), rate-limiter off-by-one + fail-open (`core/rate_limit.py:33-51`), no DB pool sizing (`database.py:29-34`), uploads buffered fully in RAM before the size check (`api/ingest.py:44`).

### 2.2 AI architecture (as-built) — *honest naming: a linear RAG pipeline, not an agent*

There is **no agent loop, no tool-calling, no planner, no self-correction.** Control flow is fixed and one-directional. This is **correct for the fixed MVP** — but it must not be described as "agentic."

**Ingestion (Celery, one task/doc, resumable-by-restart):**
`retrieve bytes → Docling/native parse → LLM tag (first ~2000 tok) → chunk → SHA-256 (compute only) → persist chunks → embed (batch 100) + Qdrant upsert → LLM NER + Neo4j upsert (best-effort) → finalize → completed`. Status is written before each step (`worker_flow.py:45-51`); permanent errors dead-letter, transient errors raise for Celery retry.

**Query (shared by SSE chat, `/api/chat`, `/api/search`, `/api/context`, `/api/evidence`):**
`embed(query) → Qdrant top-k search with mandatory workspace_id filter + score_threshold → best-effort 1-hop graph augment → re-sort → assemble_context (≤8000 tok, whole-chunk drop) → confidence = mean top-3 similarity → call_llm/stream_llm → persist chat_messages`.

**AI hard-rule compliance (all PASS, verified):** single OpenAI client (`llm_gateway.py:46-48`, enforced by `test_gateway_singleton.py`); `token_usage` on every call (incl. cost, `usage.py:29-33`); mandatory `workspace_id` Qdrant filter (`vector_store.py:99-101`); confidence = mean top-3, **zero** `trust_score` in code; graph augmentation best-effort (try/except + continue); embedding batches of 100 + token-bucket + 3× retry; per-step status + transient/permanent split + dead-letter; lazy clients.

**AI structural gaps:** broken multi-turn memory (#2); approximate tokenizer (#4); graph-augment bypasses min-score (#7); naive regex entity extraction (`retrieval_service.py:50-57`); relationships written but unused in retrieval; prompts hardcoded across three files (no registry/versioning/tests); no semantic dedup of overlapping chunks; no embedding/query/prompt caching; no eval; latency not persisted; `request_id` not propagated from `embed`/chat call sites.

### 2.3 Production Readiness Scorecard

**Backend** (each /10):

| Area | Score | Justification |
|---|---|---|
| **Scalability** | **5** | Correct pipeline concurrency model (acks_late, prefetch=1, dedicated queue); but no DB pool sizing, single uvicorn process, full-file-in-RAM uploads, no body-size limits, serial dashboard queries. |
| **Reliability** | **4** | Good *design* (resumable pipeline, dead-letter, backoff) undercut by real runtime defects: #1 worker crash, #3 dead-letter crash, no graceful shutdown, migration-failure masking, rate-limit correctness. |
| **Security** | **8** | Centralized crypto, `SecretStr`, no PII/secret logs, error envelope, HttpOnly+rotated refresh, API-key hashing, no `workspace_id`-from-input. Deduct: CORS `*` methods/headers, rate-limit fail-open+off-by-one, root container, stale API-key usage fields. |
| **Maintainability** | **8** | Clean layering, mostly-thin routers, single config/crypto/gateway seams, enums match FE, lazy clients, thorough docstrings, ruff+mypy. Deduct: `/search`+`/evidence` layering leaks, `log_api_call` commits caller txn. |
| **Monitoring / Observability** | **4** | structlog JSON + request-id correlation is good; but zero metrics/tracing, shallow `/health`, no SLO instrumentation, no latency on `token_usage`. |
| **Testing** | **4** | 9 offline unit tests (import-safety, envelope, crypto, gateway singleton, cost, chunking, retrieval assembly). The riskiest code (end-to-end `worker_flow`, rate limiter, auth/refresh, multi-turn) is untested; nothing has run; traceability is entirely `☐`. |
| **Documentation** | **9** | Outstanding: target architecture, data model, API contract, pipeline spec, 15 specs + traceability, machine-readable rules. Deduct slightly for doc↔code drift (citext, `last_message`, chunk PK name). |

**AI Systems** (each /10):

| Area | Score | Justification |
|---|---|---|
| **Agent architecture** | **6** | Clean, correct *linear* RAG with proper adapter seams and best-effort branches. Not agentic — appropriate for the fixed MVP; scored as fit-for-purpose, not "advanced." |
| **Prompt management** | **4** | Functional inline prompts, decent chat system prompt; but hardcoded across three files, unversioned, untemplated, no prompt tests, soft/unverifiable citation grounding. |
| **RAG quality** | **6** | Sound core (workspace-filtered cosine, threshold, top-k, context cap); but graph-augment bypasses min-score, entity extraction is a toy regex, relationships unused in retrieval, no chunk dedup. |
| **Context engineering** | **7** | Correct whole-chunk truncation (no mid-sentence cut), source attribution, `truncated` flag. Deduct: no semantic dedup; token accounting approximate without tiktoken. |
| **Memory systems** | **2** | History is persisted but **never fed to the LLM** — multi-turn is effectively broken; only single-shot Q&A works. |
| **Evaluation systems** | **1** | None. No golden sets, retrieval metrics, faithfulness/groundedness judge, or regression gates. RAG regressions are undetectable. |
| **AI observability** | **4** | Mandatory cost/token logging is solid; but no latency persisted, no tracing/spans, `request_id` not propagated, no RAG health metrics despite explicit latency SLAs. |
| **Cost optimization** | **6** | Good batching (100), token-bucket RPM limiting, cheap defaults, bounded NER/tagging inputs; no embedding/query/prompt caching, so cost scales linearly with reprocessing and chat volume. |

---

## 3. Phase 2 — Gap Analysis vs. Production Agentic-RAG Standards

The reference repo is a **single-tenant, Ollama + OpenSearch (BM25+kNN+RRF) + Airflow + LangGraph** teaching system. Pattern-by-pattern verdict for Keel:

| Pattern (reference) | Keel today | Verdict |
|---|---|---|
| LangGraph 7-node corrective-RAG state machine | Linear pipeline | **Not now** — contradicts Keel's fixed non-agentic MVP. It is the blueprint *if/when* Keel goes agentic later. |
| `with_structured_output(PydanticModel)` for every LLM decision | Free-text parsing in tagging/NER | **Adopt (low-risk)** — use OpenAI structured outputs for tagging/NER via the existing gateway. Reliability win, no scope change. |
| Per-node try/except → conservative fallback (never crash) | Already the philosophy (graph best-effort) | **Already aligned** — extend the same discipline to tagging/NER parse failures. |
| Per-stage tracing (spans, durations, returns trace id) — Langfuse | structlog + request_id only | **Adopt the pattern, not the library** — add per-stage spans/durations via structlog (and an optional OTel seam); keep Keel's mandated structlog. |
| LLM relevance grader + bounded query-rewrite retry (CRAG) | None | **Later/optional** — adds LLM calls + latency, out of v3 scope. Consider only if eval shows recall problems. |
| Hybrid BM25+vector with native RRF | Qdrant vector + 1-hop graph | **Not aligned** — don't introduce OpenSearch; Keel's stack is fixed. |
| Word-based, section-aware chunking | Token-based, format-specific | **Keep Keel's token-based**, but **borrow the section-aware heuristics** (merge tiny sections, drop duplicate/metadata sections). |
| Context (deps) vs State (data) separation | Service-injected adapters | **Aligned in spirit** — a useful clarity pattern if multi-step flows are ever added. |
| Token usage in Langfuse, **no cost, no DB table** | **Persistent `token_usage` + cost on every call** | **Keel is stricter — keep it.** Do not regress to the reference's weaker model. |
| Workspace/tenant isolation | Mandatory `workspace_id` everywhere | **Keel is stronger — the reference has none.** |
| **Evaluation framework** | **None in either** | **Do MORE than the reference** — this is the #1 portable *gap*, not a portable *pattern*. Build the harness the reference lacks. |
| Mock-at-client-boundary + structured-output assertions in tests | Adapter-boundary mocking already required | **Aligned** — structured outputs make LLM-touching services trivially assertable. |
| Airflow ingestion DAGs | Celery resumable queue | **Not aligned** — Celery is the right tool here; ignore. |

**Net:** The reference validates Keel's core decisions (adapter seams, best-effort branches, tenancy, cost logging) and offers exactly five surgical, scope-compatible upgrades: **structured outputs, per-stage tracing, defensive LLM fallbacks, section-aware chunking heuristics, and an evaluation harness.** Everything else is either out of MVP scope or a stack conflict.

---

## 4. Phase 4 — Recommended Architecture (evolve, do **not** redesign)

The current architecture is sound; the target state is the **same architecture with surgical additions**. No new services, no new datastores, no API/shape changes.

### 4.1 Backend
- **Keep** the layered monolith, adapter seams, single config/crypto/gateway, lazy clients.
- **Worker execution model:** replace per-task `asyncio.run()` with a **persistent event loop per worker child** (or dispose+recreate the engine inside each task), so the async engine and the loop agree. This is the one change that turns the pipeline from "crashes on doc #2" to "works."
- **Connection management:** add `pool_size`/`max_overflow`/`pool_recycle`/`pool_timeout` env knobs; dispose the engine on shutdown.
- **Lifecycle:** add a shutdown branch to the lifespan (engine dispose, Redis/clients close); add `/health/ready` that pings Postgres/Redis/Qdrant/Neo4j (keep `/health` shallow for the FE contract).
- **Edge safety:** enforce documented body-size limits (ingest ≤50 MB, search/context ≤64 KB); stream large uploads; fail-fast on migration error.

### 4.2 AI layer
- **Prompt management:** introduce `app/services/ai/prompts.py` — a small registry holding the chat/NER/tagging prompts as named, versioned constants (e.g., `CHAT_SYSTEM_V1`), imported by the services. No engine, no scope creep — just one seam so prompts are reviewable, testable, and diffable.
- **Memory:** feed the last *N* turns of the conversation into `_messages()` (bounded by token budget) so multi-turn actually works. Shape-preserving; no contract change.
- **Retrieval correctness:** pass `score_threshold` to the graph-augment search; carry `entity_type` on relationship `MERGE`; (optionally) dedup overlapping chunks before context assembly.
- **Structured outputs:** have tagging/NER use OpenAI structured outputs through the gateway, with the existing best-effort fallback on parse failure.
- **Tokenizer:** make `tiktoken` a hard worker dependency and validate each chunk window against the encoder (not just the MAX cap).
- **Still not agentic** — keep the linear pipeline. The CRAG grader/rewrite loop stays a documented future option, gated on eval evidence.

### 4.3 Observability layer
- **Logging:** keep structlog + request_id (already good); propagate `request_id` through `embed` and chat call sites.
- **Tracing:** add a lightweight per-stage span helper (embed / search / graph-augment / assemble / generate) emitting durations — the reference's best-effort pattern, implemented in structlog now, with an **optional** OpenTelemetry seam behind an env flag.
- **Metrics:** add a Prometheus seam (request latency histograms, Celery task outcomes, DB-pool gauges, rate-limit rejections) so the documented p95 SLOs are measurable.
- **AI telemetry:** add `duration_ms` to `token_usage`; derive chat/search latency, abstention rate, retrieval-empty rate, graph-augment hit rate.

### 4.4 Evaluation layer (the biggest net-new value)
- **Golden set:** a small, versioned workspace fixture (docs + curated Q&A with expected evidence) under `tests/eval/`.
- **Retrieval metrics:** hit-rate@k / MRR against expected chunk/document ids.
- **Answer quality:** an LLM-as-judge faithfulness/groundedness check (through the gateway, logged to `token_usage`), plus a "does the answer cite retrieved evidence" check.
- **Regression gate:** an offline `pytest -m eval` job (mocked adapters or a seeded ephemeral stack) that fails CI on metric regression. This is precisely the capability the reference repo lacks — Keel should exceed it.

---

## 5. Phase 3 + Phase 5 — Prioritized Roadmap & Implementation Plan

Priority = Critical/High/Med/Low · Risk = Low/Med/High · Effort = S/M/L. All items are backward-compatible (no API path/shape change) unless noted.

### 5.1 Immediate (low-risk; correctness & "make it actually run"; no API/FE impact)

| # | Item | Pri | Business impact | Technical impact | Risk | Effort | Files |
|---|---|---|---|---|---|---|---|
| I1 | Fix Celery `asyncio.run()`/engine-loop reuse (persistent loop or per-task engine dispose) | **Critical** | Ingestion works past the 1st doc; the whole product depends on it | Worker no longer crashes on doc #2 | Med | S–M | `app/tasks/ingestion.py:20`, `app/database.py:22-44` |
| I2 | Guard `mark_failed` against a `None` job | **High** | Failures dead-letter instead of vanishing | Safety net stops crashing | Low | S | `app/services/ingestion/worker_flow.py:72-90` |
| I3 | Feed last-N conversation turns into the chat prompt | **High** | Multi-turn chat actually works (user-visible) | Stateful answers; no shape change | Low | S–M | `app/services/chat_service.py:48-54,168-234` |
| I4 | Make `tiktoken` a hard worker dep + validate windows against encoder | **High** | Correct chunk sizes & context budget; avoids silent API truncation | Accurate tokenization | Low | S | `pyproject.toml`, `app/services/chunking.py:33-70` |
| I5 | Pass `score_threshold` to graph-augment search | Med | Better evidence quality | No low-relevance chunks leak into context | Low | S | `app/services/retrieval_service.py:84-86` |
| I6 | Carry `entity_type` on relationship `MERGE` | Med | Coherent graph | Stops type-less duplicate nodes | Low | S | `app/services/graph_store.py:79-80` |
| I7 | Update API-key `last_used_at`/`request_count` | Med | Contract-exposed fields stop being permanently stale | Accurate key telemetry | Low | S | `app/core/deps.py:82-89` |
| I8 | Entrypoint: fail-fast on migration error | Med | No silent boot of a schema-less app | Clear startup failure | Low | S | `docker/entrypoint.sh` |
| I9 | Rate-limiter: fix off-by-one + drop rejected entry | Med | Honest "100/min" enforcement | Correct sliding window | Low | S | `app/core/rate_limit.py:33-51` |
| I10 | Cap/real-paginate `conversations`/`messages` | Med | Long conversations don't OOM the API | Bounded queries; honor `cursor` | Low | S–M | `app/api/conversations.py`, `app/services/chat_service.py:76-104` |
| I11 | `reprocess`: supersede prior `IngestionJob` | Med | Status polling returns the right job | No orphan jobs | Low | S | `app/services/document_service.py:190-197` |

### 5.2 Medium-term (internal refactor; backward-compatible)

| # | Item | Pri | Business / technical impact | Risk | Effort | Files |
|---|---|---|---|---|---|---|
| M1 | DB pool sizing + env knobs; dispose engine on shutdown; `/health/ready` | High | Stable under load; real readiness gating | Med | M | `app/database.py`, `app/main.py:32-38`, `app/config.py` |
| M2 | Prompt registry `app/services/ai/prompts.py` (named, versioned) | Med | Reviewable/testable prompts | Low | M | `chat_service.py`, `ner.py`, `tagging.py` (+new) |
| M3 | Structured outputs for tagging/NER via gateway (+fallback) | Med | Fewer malformed LLM parses | Low | M | `app/services/ai/{tagging,ner}.py`, `llm_gateway.py` |
| M4 | `duration_ms` on `token_usage` + propagate `request_id` | Med | Measurable AI latency SLOs; correlation | Low | M | `app/models/ingestion.py`, `app/services/ai/*`, migration |
| M5 | Move `/search` + `/evidence` logic into `retrieval_service`; stop committing in `log_api_call` | Med | Restores layering; safe transactions | Med | M | `app/api/search.py`, `app/api/common.py`, `retrieval_service.py` |
| M6 | Enforce body-size limits; stream uploads; finalize multipart assembly | Med | DoS/memory safety; complete large-upload path | Med | M | `app/api/ingest.py`, `app/services/storage.py` |
| M7 | Prometheus metrics seam (request/celery/db-pool/rate-limit) | Med | The p95 SLOs become measurable | Low | M | `app/main.py`, `app/celery_app.py` |
| M8 | Redis embedding/query-embedding cache; OpenAI prompt caching | Med | Lower cost & latency on reprocess/repeat queries | Low | M | `llm_gateway.py`, `retrieval_service.py` |
| M9 | Non-root container; prune refresh tokens; composite chunk index; `citext` email | Low | Hardening + correctness | Low | S–M | `Dockerfile`, `auth_service.py`, `models/{document,user}.py`, migration |

### 5.3 Long-term (production-grade evolution)

| # | Item | Pri | Impact | Risk | Effort |
|---|---|---|---|---|---|
| L1 | **Evaluation harness** (golden set, retrieval metrics, faithfulness judge, CI regression gate) | **High** | Detect RAG regressions; the #1 pre-prod confidence gap | Med | L |
| L2 | OpenTelemetry tracing across API+worker+LLM; SLO + cost dashboards | Med | End-to-end latency/cost visibility | Med | L |
| L3 | Horizontal-scale hardening (uvicorn workers/gunicorn, PgBouncer, Qdrant/Neo4j sizing, 500 MB/1000-page perf pass) | Med | Meets the v3 large-corpus scale targets | Med | L |
| L4 | *Optional* CRAG-style relevance-grade + bounded rewrite (only if eval shows recall gaps) | Low | Higher answer quality at extra cost/latency | Med | M |
| L5 | *If/when agentic:* in-house structured-output node graph (Context-vs-State separation); LangGraph optional, not required | Low | Future capability without violating the single-gateway rule | High | L |

> **Explicitly out of scope (do not build):** email verify, MFA, SHA-256 dedup enforcement, Document Detail View, multi-hop GraphRAG, trust score, reranker, runtime embedding-model switching, role/doc-level retrieval, OpenSearch/RRF, Airflow, LangGraph-now. These are deferred by v3 and must stay deferred.

---

## 6. Safe Refactoring Plan (improve without breaking)

**Guiding principle: verify before you refactor.** The codebase has never run and nothing is checked off in traceability — so *proving it works* outranks *making it prettier*. Order of operations:

1. **Make it run (correctness only).** Apply I1, I2, I4, I8. Then execute the real smoke test the runbook describes: `docker compose --profile full up`, seed admin, run the §21 demo flow end-to-end. Nothing else proceeds until ingestion completes for ≥2 documents on one worker (proves I1).
2. **Get the existing gates green.** Run the project's `/verify` (ruff format+check, mypy, pytest, import/boot smoke). Fix only what blocks green. This establishes the baseline the karpathy guidelines call for ("tests pass before and after").
3. **Add the test that would have caught the worst bug.** A `worker_flow.run()` end-to-end test (adapters mocked) exercised **twice in one process** — this both locks I1 and satisfies the AGENTS testing rule (call `run()` directly, not `.delay()`).
4. **Lock the contract before touching routers.** Add contract tests asserting response JSON matches `docs/api-contract.md` / `keel-UI` shapes. Only then perform the layering refactors (M5) — they are pure internal moves with identical response shapes.
5. **Each behavior fix lands behind a test.** I3 (multi-turn) gets a test that prior turns reach the model; I5/I6/I7/I9/I10/I11 each get a focused unit test. Memory and threshold changes are shape-preserving, so the FE is unaffected.
6. **Additive-only schema changes.** M4/M9 migrations add columns/indexes; never rename or drop in place (the chunk-PK and `last_message` mismatches are reconciled additively or left documented, not destructively migrated).

**Backward-compatibility guardrails (non-negotiable):**
- `keel-UI` is the contract authority — **no path, field, enum, or envelope changes.** Verified-clean items (tenancy, auth selection, pagination shapes) stay as-is.
- Enums are frozen to `data-model.md` / FE values.
- Any behavior change that *could* alter outputs (e.g., feeding history) is shape-preserving and additive; if ever risky, gate behind a workspace setting/flag.
- Mock at the adapter boundary so refactors are provable offline (`pytest` green on a clean checkout, no external services).

**Definition of done for this uplift:** §21 demo flow passes end-to-end on a fresh `docker compose up`; `/verify` is green; the `worker_flow` twice-in-one-process test passes; `TRACEABILITY.md` rows flip from `☐` to checked as their acceptance tests land; the eval harness (L1) reports a baseline retrieval metric.

---

## 7. Appendix — Verified critical defects (with fix sketches)

**A. Celery event-loop / engine reuse (Critical).**
`app/tasks/ingestion.py:20` runs `asyncio.run(worker_flow.run(...))` per task; `asyncio.run` creates and closes a fresh loop each call. `app/database.py:26-35` caches a module-global `AsyncEngine` on first use, binding asyncpg connections to that first loop. With default prefork (`-c 4`, no `max_tasks_per_child`), each worker child handles many tasks → 2nd task reuses a loop-dead engine → `RuntimeError: Event loop is closed` / `got Future attached to a different loop`. *Fix:* run one persistent loop per child (e.g., a module-level loop + `loop.run_until_complete`), **or** dispose+rebuild the engine inside each task. Add the twice-in-one-process test.

**B. Multi-turn memory not wired (High).**
`app/services/chat_service.py:48-54` `_messages(context, query)` returns `[system, user]` only; `stream_answer` (:178) and `answer_once` (:218) never load prior turns; `conversation_id` is used solely by `_persist`. *Fix:* load the last N messages for the conversation, append them between system and the new user turn, bounded by a token budget. Shape-preserving.

**C. Dead-letter `None`-deref (High).**
`worker_flow.mark_failed` (:72-90) selects the latest job with `.first()` (can be `None`) and passes it to `_dead_letter` (:54-69), which sets `job.status/current_step/error`. `run()` guards this (:111-116) but `mark_failed` does not. *Fix:* if `job is None`, create one (mirror `run()`), or set only document-level failure state.

**D. Tokenizer approximation (Med-High).**
`app/services/chunking.py:33-50` falls back to `len/4` when `tiktoken` is absent (it's an optional dep, not installed on the worker); window sizing uses `words/0.75` (`:53-70`). Chunk sizes, the 1024 cap, and the 8000-token context cap are all approximate → possible oversized embeds (silent API truncation) and wrong context budgeting. *Fix:* make `tiktoken` a hard worker dependency; validate each window against `count_tokens`.

**E. Graph-augment threshold bypass + relationship MERGE gap (Med).**
`retrieval_service.py:84-86` omits `score_threshold` (low-relevance chunks enter context/evidence). `graph_store.py:79-80` `MERGE`s relationship endpoints on `{workspace_id, canonical_name}` without `entity_type`, while the node constraint is `(workspace_id, entity_type, canonical_name)` → a second type-less node can be created (graph fragmentation). *Fix:* pass the threshold; carry `entity_type` on both endpoints.

---

*Prepared as a non-destructive audit. No application code was modified. Every recommendation traces to a product requirement (v3 / timelines), a reliability/scalability need, or a production-AI best practice validated against the reference repository — and every one preserves the existing Keel contract.*
