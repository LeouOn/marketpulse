# RAG Pipeline Revival + Phase A1 main.py Dedupe — Design

Date: 2026-07-21
Status: Approved (user confirmed scope + LLM providers available: DeepSeek, GLM, MiniMax in env)

## Scope

Two workstreams, sequenced A1 first, RAG second:

1. **Phase A1**: Mount the existing FastAPI routers in `src/api/routers/` and delete the
   ~35 inline duplicate endpoints in `src/api/main.py` (2,339 lines).
2. **RAG revival**: Wire the dead `EnhancedLLMClient` into live endpoints, add embedding
   caching, hybrid retrieval, retrieval-quality tests, and clean up
   `src/llm/enhanced_llm_client.py`.

Explicitly out of scope: knowledge-base content authoring, cross-encoder rerankers,
vector databases, LLM agent stubs (`src/llm/agents/*`), frontend changes.

## Motivation

- `routers/llm.py` (1,318 lines, chat/models/feedback) is never mounted; `/api/llm/*`
  works only because `main.py` duplicates endpoints inline. Any new LLM endpoint added
  before A1 would need to be deduplicated again later.
- `EnhancedLLMClient` (ModelRouter-backed, RAG-integrated) is dead code; `main.py` uses
  plain `LLMManager`/`LMStudioClient`.
- `EmbeddingRAG` re-embeds the whole knowledge base on every process start (~30s, needs
  network on first run) and retrieval is semantic-OR-keyword fallback, not hybrid.

## Part 1 — Phase A1: main.py dedupe

### Safety net (written FIRST, before any refactor)

1. **Route-parity test** (`tests/test_route_parity.py`): snapshot the app's full route
   table (method, path, name) from the FastAPI app object via TestClient BEFORE the
   refactor; store as a checked-in JSON fixture; assert byte-identical parity AFTER.
   OpenAPI schema (`/openapi.json` paths) compared as a set, not byte-for-byte (router
   mounting may change operation IDs/order).
2. **Behavior tests** for the highest-traffic endpoints using TestClient with provider
   calls mocked: `/api/llm/chat`, `/api/llm/models`, `/api/llm/model-status`,
   `/api/market/*` (dashboard + internals), `/api/symbols/*`. Assert response shape and
   status codes match pre-refactor behavior.

### Refactor

- Mount routers: `llm`, `market`, `symbols`, `screeners`, `websocket`, `data_quality`,
  `yield_curve` (yield_curve already mounted — verify no double-mount).
- Delete inline duplicates from `main.py`; keep genuinely unique inline endpoints
  (identify during implementation; e.g. debug routes) and comment why they stay.
- Target: `main.py` reduced to app factory, lifespan, middleware, mounts (~400 lines).
- Shared state (e.g. `model_cache`, `_selected_model`, `collector`, `db_manager`)
  lives in `routers/deps.py` — verify no divergence between deps and inline versions
  before deletion; merge toward deps.

### Verification

- Route-parity test green; behavior tests green; full pytest suite green.
- Server boots; `/api/debug/routes` set identical; manual smoke: frontend chat works.

## Part 2 — RAG pipeline

### Endpoints (added to mounted `routers/llm.py`)

| Endpoint | Method | Backing |
|---|---|---|
| `/api/llm/enhanced-analysis` | POST | `EnhancedLLMClient.analyze_with_knowledge` |
| `/api/llm/test-hypothesis` | POST | `EnhancedLLMClient.test_hypothesis` (HypothesisTester, structured output) |
| `/api/llm/knowledge/{term}` | GET | `TradingKnowledgeRAG.get_glossary_term` + related terms |
| `/api/llm/retrieve-context` | POST | `TradingKnowledgeRAG.retrieve_context` (returns chunks + scores; debug/UX aid) |

All use a shared `EnhancedLLMClient` built on the shared `ModelRouter` (reuse the
existing `_get_router()` singleton pattern in `routers/llm.py`). All degrade gracefully:
no LLM provider → 503-style `MarketResponse(success=False)`, no 500s.

### Embedding cache

- Persist chunk embeddings to `data/rag_cache/embeddings.npz` + `manifest.json`
  (chunk id = sha256 of source file path + content).
- On boot: load cached vectors for unchanged files; embed only new/changed docs.
- Boot: ~30s → <1s steady-state; offline after first successful embed.
- `data/rag_cache/` added to `.gitignore`.

### Hybrid retrieval

- Replace semantic-or-keyword fallback in `TradingKnowledgeRAG.retrieve_context` with
  reciprocal rank fusion (RRF, k=60) over: (a) semantic ranking from `EmbeddingRAG`,
  (b) keyword/glossary ranking from the existing keyword path.
- Glossary exact-term matches get a small rank boost (they are curated ground truth).
- Behavior when embeddings unavailable (model missing, offline first run): pure keyword
  path, unchanged from today.

### Cleanup

- `enhanced_llm_client.py`: delete legacy `EnhancedLMStudioClient` (LMStudioClient
  subclass) and the `__main__` demo; keep `EnhancedLLMClient` + `EnhancedLLMManager`;
  reformat to normal spacing; no behavior change to kept classes.

### Retrieval quality harness

- `tests/rag/golden_queries.json`: ~15 query → expected-source-title pairs derived from
  existing knowledge base (FVG → market_structure, margin cascade → overnight hypothesis,
  glossary terms → glossary).
- `tests/rag/test_retrieval_quality.py`: asserts hit-rate@5 ≥ defined threshold for
  hybrid mode; runs with a mocked/cached embedder in CI (no model download).
- Embedding-cache tests: second load does not call `model.encode` for unchanged files.

## Testing strategy

- All new code: unit tests first (TDD), pytest, mocked network/LLM.
- Route parity + behavior tests gate A1 merge.
- Full suite (`pytest tests/ -q`, CI subset + new tests) green before done.
- Live smoke (manual, local): boot server, run one `enhanced-analysis` and one
  `test-hypothesis` call against DeepSeek/GLM/MiniMax from env; verify RAG chunks appear
  in prompt path via debug field in response.

## Risks

| Risk | Mitigation |
|---|---|
| A1 breaks a live endpoint silently | Route-parity + behavior tests written and green BEFORE refactor |
| deps.py state diverges from inline main.py state | Diff both before deletion; parity test catches endpoint loss; behavior tests catch state loss |
| Embedding model unavailable in CI | Quality harness uses stub embedder; cache tested with fake encode fn |
| RRF changes retrieval quality negatively | Golden-query harness compares hybrid vs keyword-only vs semantic-only; keep winner |

## Success criteria

1. `main.py` ≤ ~500 lines; all routers mounted; route set identical to pre-refactor.
2. Four new `/api/llm/*` endpoints live, tested, documented in `BACKEND_DOCUMENTATION.md`.
3. RAG boot < 1s warm; hybrid retrieval hit-rate ≥ keyword-only on golden set.
4. Full pytest suite green; live smoke test against real provider passes.
