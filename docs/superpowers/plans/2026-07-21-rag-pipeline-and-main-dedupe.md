# RAG Pipeline Revival + Phase A1 main.py Dedupe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mount the unmounted FastAPI routers and dedupe `src/api/main.py` (Phase A1), then wire the dead EnhancedLLMClient/RAG pipeline into four live endpoints with embedding caching, hybrid retrieval, and a retrieval-quality harness.

**Architecture:** A1 first (safety-net tests → state unification → mount routers → delete inline dupes → extract options router), then RAG work on the mounted `routers/llm.py` (embedding disk cache → RRF hybrid retrieval → client cleanup → new endpoints → live smoke).

**Tech Stack:** Python 3.11, FastAPI, pytest + TestClient, sentence-transformers (already in requirements.txt line 24), numpy, loguru, pydantic v2.

**Spec:** `docs/superpowers/specs/2026-07-21-rag-pipeline-and-main-dedupe-design.md`

## Global Constraints

- Ruff line-length 120; run `ruff check` + `ruff format --check` on changed files before each commit.
- No new production dependencies. sentence-transformers, numpy, aiohttp, fastapi, pytest already present.
- pydantic v2 syntax (`dict[str, Any] | None`, no `Optional`/`Dict` in NEW code).
- All tests must pass with no network and no LLM provider (mock/stub). Live tests use `@pytest.mark.live` (gated by `RUN_LIVE_TESTS=1` per existing `tests/conftest.py`).
- Working dir is repo root. Run tests: `python -m pytest tests/<file> -q`.
- **File hazard:** `src/api/routers/llm.py`, `src/llm/enhanced_llm_client.py` (and possibly others) have a blank line between every code line on disk, and the grep tool reports line numbers counting only non-blank lines. Use the Read tool's line numbers for edits. If Edit fails on exact-match, rewrite the whole file with Write (normalizing to single-spaced — this is desirable).
- `src/api/routers/market.py` is not reliably grep-able; verify its contents with Read or python.
- Do not commit secrets. `.env` values are only used by the manual smoke script at the end.

## Known Facts (verified during planning — trust these)

- `src/api/main.py` (2,360 lines) has 35 inline endpoints. Inline `/api/test/data-source` and `/api/test/yahoo-finance` are registered TWICE (lines ~207/233 and ~272/328); in FastAPI the LAST registration wins.
- Unmounted routers in `src/api/routers/`: `llm.py` (prefix `/api/llm`), `market.py` (prefix `/api/market`), `symbols.py` (`/api/market/symbols`), `screeners.py` (`/api/market/screeners`), `websocket.py` (`/ws/*`), `data_quality.py` (`/api/market/data-quality`), `test.py` (`/api/test`). `yield_curve.py` IS already mounted (main.py line ~2352).
- Already-mounted routers live in `src/api/*.py`: `ict_endpoints`, `backtest_endpoints`, `risk_endpoints`, `ai_endpoints`, `divergence_endpoints`, `visualization_endpoints`, `research_router` (+ journal, alerts). Do not touch these.
- `routers/market.py` covers ALL inline `/api/market/*`: internals, dashboard, historical, `historical/{symbol}`, ai-analysis, macro, breadth, `ohlc-analysis/{symbol}`, ohlc-dashboard, `trends/{symbol}`.
- `routers/llm.py` covers ALL inline `/api/llm/*`: chat, models, select-model, model-status, comment, refine, analyze-chart, validation/sanity-check, `conversation-history/{id}` (+ feedback endpoints which have no inline twin).
- Inline endpoints with NO router twin: `/`, `/api/debug/routes`, and 8 `/api/options/*` endpoints (expirations, chain, analyze/single-leg, screen, strategy/covered-call, strategy/bull-call-spread, strategy/bear-put-spread, macro-context).
- `src/api/routers/deps.py` has module globals `collector`, `ohlc_analyzer`, `db_manager`, `model_cache`, `settings` and models `MarketResponse`, `UserComment`, `RefinedAnalysisRequest`, `ChartAnalysisRequest`, `ChatRequest`, `ModelSelectionRequest`. main.py has its OWN copies of all of these (lifespan sets main.py's globals; deps' globals stay `None`).
- `routers/llm.py` line ~45 does `from .deps import collector as _collector` — this binds `None` at import time forever. Must become dynamic access (`deps.collector`).
- main.py lifespan (lines ~66-99) creates module-level `collector = MarketPulseCollector()` (with `await collector.initialize()`) and `ohlc_analyzer = OHLCAnalyzer()`; `db_manager` created at line ~137.
- `EnhancedLLMClient(settings)` in `src/llm/enhanced_llm_client.py`: async context manager creates its own ModelRouter; methods: `analyze_with_knowledge(query, market_data=None, prompt_type="trading_analyst", max_tokens=400, temperature=0.3)`, `test_hypothesis(hypothesis_name, market_data=None)`, `analyze_market_with_context`, `analyze_market_internals`, `deep_market_analysis`, `get_glossary_term`, `get_related_knowledge`. `EnhancedLLMManager` wraps it (`analyze_market`, `test_hypothesis`).
- `HypothesisTester(llm_client, knowledge_rag)` in `src/llm/hypothesis_tester.py`: `async test_hypothesis(...) -> HypothesisTestResult` (dataclass with `to_dict()`); also `list_hypotheses()`.
- `ModelRouter.generate(messages=, capability=, max_tokens=, temperature=)` returns an OpenAI-style dict with `choices`.
- `TradingKnowledgeRAG.retrieve_context(query, max_results=5)` currently: semantic via `EmbeddingRAG` if available, else keyword. `EmbeddingRAG.retrieve_context(query, top_k=5)` returns `[{title, type, content, score}]`.
- LLM provider keys (DeepSeek/GLM/MiniMax) are in the user's environment; `src/core/config.py` reads them. Verify exact env names with `grep -n "env" src/core/config.py | head -30` before the smoke test.

---

## Task 1: Route-parity snapshot (BEFORE any refactor)

**Files:**
- Create: `scripts/snapshot_routes.py`
- Create: `tests/test_route_parity.py`
- Create: `tests/fixtures/route_snapshot.json` (generated)

**Interfaces:**
- Produces: fixture = JSON object `{"routes": ["METHOD /path", ...]}` sorted; consumed by `test_route_parity.py` in every later task.

- [ ] **Step 1: Write the snapshot script**

```python
# scripts/snapshot_routes.py
"""Snapshot the app's route table (method+path set) to tests/fixtures/route_snapshot.json."""
import json
from pathlib import Path

from src.api.main import app

def route_set() -> list[str]:
    entries = set()
    for route in app.routes:
        path = getattr(route, "path", None)
        if not path:
            continue
        methods = getattr(route, "methods", None)
        if methods:
            for m in sorted(methods - {"HEAD", "OPTIONS"}):
                entries.add(f"{m} {path}")
        else:  # websocket routes have no .methods
            entries.add(f"WS {path}")
    return sorted(entries)

if __name__ == "__main__":
    out = Path("tests/fixtures/route_snapshot.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    routes = route_set()
    out.write_text(json.dumps({"routes": routes}, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(routes)} routes to {out}")
```

- [ ] **Step 2: Write the parity test**

```python
# tests/test_route_parity.py
"""Route table must be identical before/after the Phase A1 refactor."""
import json
from pathlib import Path

from src.api.main import app
from scripts.snapshot_routes import route_set

FIXTURE = Path(__file__).parent / "fixtures" / "route_snapshot.json"


def test_route_table_matches_snapshot():
    expected = set(json.loads(FIXTURE.read_text(encoding="utf-8"))["routes"])
    actual = set(route_set())
    missing = expected - actual
    added = actual - expected
    assert not missing, f"Routes LOST in refactor: {sorted(missing)}"
    assert not added, f"Routes ADDED (update fixture if intentional): {sorted(added)}"
```

- [ ] **Step 3: Generate the fixture and run the test (must pass pre-refactor)**

Run: `python scripts/snapshot_routes.py && python -m pytest tests/test_route_parity.py -q`
Expected: `Wrote N routes...` then `1 passed`

- [ ] **Step 4: Commit**

```bash
git add scripts/snapshot_routes.py tests/test_route_parity.py tests/fixtures/route_snapshot.json
git commit -m "test: route-parity snapshot safety net for Phase A1"
```

---

## Task 2: Behavior baseline tests (BEFORE any refactor)

**Files:**
- Create: `tests/test_api_behavior_baseline.py`

**Interfaces:**
- Consumes: `src.api.main:app` via `fastapi.testclient.TestClient`.
- Produces: passing baseline that must stay green through Tasks 3-5.

These endpoints are network-free / degrade gracefully offline, so they are stable anchors:

- [ ] **Step 1: Write the baseline tests**

```python
# tests/test_api_behavior_baseline.py
"""Behavior anchors for Phase A1: must pass identically before and after refactor."""
import json

from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


def test_root():
    r = client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, dict)


def test_debug_routes_lists_routes():
    r = client.get("/api/debug/routes")
    assert r.status_code == 200
    body = r.json()
    text = json.dumps(body)
    assert "/api/llm/chat" in text
    assert "/api/market/dashboard" in text


def test_test_status():
    r = client.get("/api/test/status")
    assert r.status_code == 200


def test_llm_models_shape():
    r = client.get("/api/llm/models")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert isinstance(body["data"]["models"], list)


def test_llm_chat_graceful_offline():
    """With no LLM provider reachable, chat returns success=True with fallback text."""
    r = client.post("/api/llm/chat", json={"message": "hello market"})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert isinstance(body["data"]["response"], str)
    assert len(body["data"]["response"]) > 0


def test_market_dashboard_shape():
    r = client.get("/api/market/dashboard")
    assert r.status_code == 200
    body = r.json()
    assert "success" in body and "timestamp" in body


def test_symbols_list():
    r = client.get("/api/market/symbols")
    assert r.status_code == 200
    assert "success" in r.json()
```

NOTE: `test_symbols_list` exercises `routers/symbols.py`, which is NOT yet mounted — this test FAILS with 404 pre-refactor. That is intentional: it is the proof that mounting happened. Mark it accordingly:

```python
import pytest

@pytest.mark.xfail(reason="symbols router not mounted until Task 4", strict=True)
def test_symbols_list(): ...
```

(Put the `xfail` decorator on `test_symbols_list` only. In Task 4 Step 4, remove it.)

- [ ] **Step 2: Run baseline**

Run: `python -m pytest tests/test_api_behavior_baseline.py -q`
Expected: 6 passed, 1 xfailed. If `test_llm_models_shape` or `test_llm_chat_graceful_offline` fails pre-refactor, READ the failure — do not "fix" by weakening the test; if inline behavior is genuinely different (e.g. chat returns success=False offline), record the ACTUAL behavior in the test instead, because parity means "same as before", not "ideal".

- [ ] **Step 3: Commit**

```bash
git add tests/test_api_behavior_baseline.py
git commit -m "test: behavior baseline anchors for Phase A1"
```

---

## Task 3: Unify app state in deps.py

**Files:**
- Modify: `src/api/routers/deps.py`
- Modify: `src/api/main.py` (lifespan only, ~lines 66-99)
- Modify: `src/api/routers/llm.py` (dynamic collector access)
- Test: `tests/test_deps_state.py` (create)

**Interfaces:**
- Produces: `deps.init_state(collector=None, ohlc_analyzer=None, db_manager=None) -> None`; `deps.get_collector() -> Any | None`. All routers access shared state via `deps.<name>` attribute access (never `from .deps import collector`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_deps_state.py
from src.api.routers import deps


def test_init_state_sets_globals():
    sentinel = object()
    deps.init_state(collector=sentinel)
    assert deps.collector is sentinel
    assert deps.get_collector() is sentinel
    deps.init_state(collector=None)  # reset
    assert deps.collector is None
```

Run: `python -m pytest tests/test_deps_state.py -q` — Expected: FAIL (`AttributeError: module ... has no attribute 'init_state'`).

- [ ] **Step 2: Implement in deps.py**

Append to `src/api/routers/deps.py`:

```python
def init_state(*, collector=None, ohlc_analyzer=None, db_manager=None):
    """Called by app lifespan to publish runtime singletons to routers."""
    globals()["collector"] = collector
    globals()["ohlc_analyzer"] = ohlc_analyzer
    if db_manager is not None:
        globals()["db_manager"] = db_manager


def get_collector():
    return collector
```

- [ ] **Step 3: Wire lifespan in main.py**

In `src/api/main.py` lifespan, after `ohlc_analyzer` is set (just before `logger.info(f"Lifespan initialization complete...")`), add:

```python
    from src.api.routers import deps as router_deps
    router_deps.init_state(collector=collector, ohlc_analyzer=ohlc_analyzer, db_manager=db_manager)
    logger.info("Router deps state published")
```

- [ ] **Step 4: Fix static imports of collector in routers**

In `src/api/routers/llm.py`: replace the line `from .deps import collector as _collector` with `from . import deps as _deps`, and replace every use of `_collector` with `_deps.collector`, and every use of bare `collector` (e.g. in `run_sanity_check`: `from .deps import collector` then `if not collector:` / `await collector.collect_market_internals()`) with `_deps.collector`. Also check `routers/market.py`, `routers/symbols.py`, `routers/screeners.py`, `routers/data_quality.py`, `routers/websocket.py`, `routers/test.py` for `from .deps import collector` / `from .deps import db_manager` / `from .deps import ohlc_analyzer` patterns and convert each to `from . import deps` + `deps.<name>` at use sites. (Verify each file with Read; remember the blank-line hazard when editing — rewrite the file with Write if Edit matching fails.)

Grep to find them all: `grep -rn "from .deps import" src/api/routers/`

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_deps_state.py tests/test_api_behavior_baseline.py tests/test_route_parity.py -q`
Expected: all pass (1 xfail remains).

- [ ] **Step 6: Commit**

```bash
git add src/api/routers/deps.py src/api/routers/llm.py src/api/main.py tests/test_deps_state.py
git commit -m "refactor: publish lifespan state to routers via deps.init_state"
```

(If other routers were edited, add them too.)

---

## Task 4: Mount routers + delete inline duplicates

**Files:**
- Modify: `src/api/main.py` (the big one)
- Modify: `tests/test_api_behavior_baseline.py` (remove xfail)

**Interfaces:**
- Consumes: everything from Tasks 1-3.
- Produces: mounted routers `llm, market, symbols, screeners, websocket, data_quality, test`; main.py without inline `/api/llm/*`, `/api/market/*`, `/api/test/*`, `/ws/*` handlers.

- [ ] **Step 1: Add mounts in main.py**

Near the existing `include_router` block (~line 2279), add BEFORE them:

```python
from src.api.routers import data_quality as data_quality_router_module
from src.api.routers import llm as llm_router_module
from src.api.routers import market as market_router_module
from src.api.routers import screeners as screeners_router_module
from src.api.routers import symbols as symbols_router_module
from src.api.routers import test as test_router_module
from src.api.routers import websocket as websocket_router_module

app.include_router(llm_router_module.router)
app.include_router(market_router_module.router)
app.include_router(symbols_router_module.router)
app.include_router(screeners_router_module.router)
app.include_router(websocket_router_module.router)
app.include_router(data_quality_router_module.router)
app.include_router(test_router_module.router)
```

- [ ] **Step 2: Delete inline duplicates from main.py**

Delete these inline handlers AND their now-unused helpers/imports (verify each against the router twin before deleting — if an inline handler has logic the router lacks, PORT the difference into the router first, then delete):

- `/api/test/status`, BOTH copies of `/api/test/data-source`, BOTH copies of `/api/test/yahoo-finance`
- `/api/market/internals`, `/api/market/dashboard`, `/api/market/historical`, `/api/market/ai-analysis`, `/api/market/macro`, `/api/market/breadth`, `/api/market/ohlc-analysis/{symbol}`, `/api/market/ohlc-dashboard`, `/api/market/trends/{symbol}`
- `/api/llm/chat`, `/api/llm/models`, `/api/llm/select-model`, `/api/llm/model-status`, `/api/llm/comment`, `/api/llm/refine`, `/api/llm/analyze-chart`, `/api/llm/validation/sanity-check`, `/api/llm/conversation-history/{analysis_id}`
- `/ws/market`, `/ws/test`

KEEP inline: `/`, `/api/debug/routes`, all 8 `/api/options/*` (Task 5 moves them). Also delete main.py's duplicate pydantic models (`MarketResponse`, `UserComment`, `RefinedAnalysisRequest`, `ChartAnalysisRequest`) and `model_cache` if nothing inline uses them after deletion — the options endpoints' dependencies stay.

Behavior-parity gotchas to check while porting:
- Inline `/api/llm/chat` has a `_selected_model` global and offline fallback text; `routers/llm.py` has its own `_selected_model`. Keep the router version; do not try to preserve main.py's copy.
- main.py line ~1042 sets `LMStudioClient.default_model`; router keeps its own mechanism — fine.

- [ ] **Step 3: Remove the xfail**

In `tests/test_api_behavior_baseline.py`, delete the `@pytest.mark.xfail(...)` line above `test_symbols_list`.

- [ ] **Step 4: Verify**

Run: `python -m pytest tests/test_route_parity.py tests/test_api_behavior_baseline.py tests/test_deps_state.py -q`
Expected: ALL pass, zero xfail. If parity reports LOST routes, you deleted something without a twin — restore or port. If it reports ADDED routes (e.g. `/api/llm/feedback`, `/api/market/historical/{symbol}`, `/api/market/symbols*`, `/ws/stream-analysis`, `/api/market/data-quality*` — router twins with no inline original), regenerate the fixture with `python scripts/snapshot_routes.py`, eyeball the diff with `git diff tests/fixtures/route_snapshot.json` to confirm every addition is an intended router-only endpoint, then commit the updated fixture.

Then run the broader suite: `python -m pytest tests/ -q --ignore=tests/e2e -x --timeout=300` (mirror CI's ignore list from `.github/workflows/ci.yml` if different). Fix only breakage caused by YOUR changes.

- [ ] **Step 5: Boot smoke**

Run: `python -c "from src.api.main import app; print(len(app.routes))"` (imports cleanly) and `uvicorn src.api.main:app --port 8000` briefly; hit `curl http://localhost:8000/api/debug/routes` and `curl -X POST http://localhost:8000/api/llm/chat -H "Content-Type: application/json" -d '{"message":"ping"}'`; confirm JSON response. Kill the server.

- [ ] **Step 6: Commit**

```bash
git add src/api/main.py src/api/routers/ tests/test_api_behavior_baseline.py tests/fixtures/route_snapshot.json
git commit -m "refactor(A1): mount routers, delete inline duplicate endpoints from main.py"
```

---

## Task 5: Extract /api/options/* into routers/options.py

**Files:**
- Create: `src/api/routers/options.py`
- Modify: `src/api/main.py`

**Interfaces:**
- Produces: `options.router` (prefix `/api/options`), mounted in main.py. Route set unchanged.

- [ ] **Step 1: Move the code**

Create `src/api/routers/options.py` with:

```python
"""Options analysis endpoints (extracted from main.py during Phase A1)."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/options", tags=["options"])
```

Then MOVE (cut, not copy) the 8 options handlers from main.py (~lines 1671-2339: expirations, chain, analyze/single-leg, screen, strategy/covered-call, strategy/bull-call-spread, strategy/bear-put-spread, macro-context) into this file, changing `@app.` to `@router.` and dropping the `/api/options` prefix from each path. Move the imports they need (check the top of main.py for options-related imports: options_pricing/options_analyzer/options_screener from `src.analysis`, plus pydantic models used only by options endpoints). Keep `MarketResponse` imported from `.deps`.

- [ ] **Step 2: Mount**

In main.py, with the other mounts: `from src.api.routers import options as options_router_module` + `app.include_router(options_router_module.router)`.

- [ ] **Step 3: Verify**

Run: `python -m pytest tests/test_route_parity.py tests/test_api_behavior_baseline.py -q`
Expected: pass with NO fixture change (paths identical). Then `ruff check src/api/routers/options.py src/api/main.py`.

- [ ] **Step 4: Commit**

```bash
git add src/api/routers/options.py src/api/main.py
git commit -m "refactor(A1): extract options endpoints to routers/options.py"
```

---

## Task 6: Embedding disk cache

**Files:**
- Modify: `src/llm/embedding_rag.py`
- Modify: `.gitignore`
- Test: `tests/rag/test_embedding_cache.py` (create; also `tests/rag/__init__.py` empty)

**Interfaces:**
- Produces: `EmbeddingRAG(knowledge_dir="trading_knowledge", model_name=..., cache_dir="data/rag_cache")`. Cache files: `<cache_dir>/embeddings.npz` (keys = chunk ids) + `<cache_dir>/manifest.json` (`{chunk_id: {"sha256": ..., "title": ..., "type": ..., "content": ...}}`). Chunk id = sha256 of `title + "\x00" + content` (first 16 hex chars).

- [ ] **Step 1: Write the failing test**

```python
# tests/rag/test_embedding_cache.py
import sys
import types

import numpy as np
import pytest


class _FakeModel:
    def __init__(self, *a, **kw):
        self.encode_calls = 0

    def get_sentence_embedding_dimension(self):
        return 4

    def encode(self, texts, show_progress_bar=False):
        self.encode_calls += 1
        return np.array([[float(len(t)), 1.0, 0.0, 0.0] for t in texts])


@pytest.fixture()
def fake_st(monkeypatch):
    module = types.ModuleType("sentence_transformers")
    model = _FakeModel()
    module.SentenceTransformer = lambda *a, **kw: model
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    return model


def _make_kb(tmp_path):
    kb = tmp_path / "kb"
    (kb / "core_concepts").mkdir(parents=True)
    (kb / "core_concepts" / "alpha.md").write_text("alpha content about gaps", encoding="utf-8")
    (kb / "trading_glossary.json").write_text('{"FVG": "fair value gap"}', encoding="utf-8")
    return kb


def test_second_instance_uses_cache(tmp_path, fake_st):
    from src.llm.embedding_rag import EmbeddingRAG

    kb = _make_kb(tmp_path)
    cache = tmp_path / "cache"

    rag1 = EmbeddingRAG(str(kb), cache_dir=str(cache))
    chunks1 = rag1.retrieve_context("gaps", top_k=2)
    assert chunks1, "expected retrieval results"
    calls_after_first = fake_st.encode_calls
    assert calls_after_first >= 1

    rag2 = EmbeddingRAG(str(kb), cache_dir=str(cache))
    chunks2 = rag2.retrieve_context("gaps", top_k=2)
    assert fake_st.encode_calls == calls_after_first, "unchanged docs must not be re-embedded"
    assert [c["content"] for c in chunks1] == [c["content"] for c in chunks2]


def test_changed_file_reembeds_only_changed(tmp_path, fake_st):
    from src.llm.embedding_rag import EmbeddingRAG

    kb = _make_kb(tmp_path)
    cache = tmp_path / "cache"
    EmbeddingRAG(str(kb), cache_dir=str(cache)).retrieve_context("gaps")
    baseline = fake_st.encode_calls

    (kb / "trading_glossary.json").write_text('{"FVG": "CHANGED definition"}', encoding="utf-8")
    rag = EmbeddingRAG(str(kb), cache_dir=str(cache))
    rag.retrieve_context("FVG")
    assert fake_st.encode_calls > baseline, "changed doc must trigger re-embed"
```

Run: `python -m pytest tests/rag/test_embedding_cache.py -q` — Expected: FAIL (`TypeError: __init__() got an unexpected keyword argument 'cache_dir'`).

- [ ] **Step 2: Implement the cache in embedding_rag.py**

Changes to `EmbeddingRAG`:

```python
# new imports at top
import hashlib

# __init__ signature
def __init__(self, knowledge_dir="trading_knowledge", model_name="all-MiniLM-L6-v2", cache_dir="data/rag_cache"):
    ...existing fields...
    self.cache_dir = Path(cache_dir)

@staticmethod
def _chunk_id(chunk: dict) -> str:
    return hashlib.sha256((chunk["title"] + "\x00" + chunk["content"]).encode("utf-8")).hexdigest()[:16]
```

Replace the embed-everything block in `_ensure_initialized` with:

```python
        self._chunks = self._collect_documents()
        if not self._chunks:
            logger.warning("EmbeddingRAG: no documents found to embed")
            self._initialized = True
            return

        self._embeddings = self._load_or_build_embeddings()
        self._initialized = True

def _load_or_build_embeddings(self) -> "np.ndarray | None":
    """Return embedding matrix aligned with self._chunks, using the disk cache."""
    import json as _json

    self.cache_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = self.cache_dir / "manifest.json"
    vectors_path = self.cache_dir / "embeddings.npz"

    manifest: dict = {}
    vectors: dict[str, np.ndarray] = {}
    if manifest_path.exists() and vectors_path.exists():
        try:
            manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
            vectors = dict(np.load(vectors_path))
        except Exception as e:
            logger.warning(f"EmbeddingRAG cache unreadable, rebuilding: {e}")
            manifest, vectors = {}, {}

    dim = self._model.get_sentence_embedding_dimension()
    out = np.zeros((len(self._chunks), dim), dtype=np.float32)
    new_manifest: dict = {}
    to_embed: list[int] = []

    for i, chunk in enumerate(self._chunks):
        cid = self._chunk_id(chunk)
        new_manifest[cid] = {"title": chunk["title"], "type": chunk["type"], "content": chunk["content"]}
        if cid in vectors and cid in manifest:
            out[i] = vectors[cid]
        else:
            to_embed.append(i)

    if to_embed:
        texts = [self._chunks[i]["content"] for i in to_embed]
        logger.info(f"EmbeddingRAG: embedding {len(texts)} new/changed chunks (cache had {len(vectors)})")
        fresh = self._model.encode(texts, show_progress_bar=False)
        for pos, i in enumerate(to_embed):
            out[i] = fresh[pos]

    try:
        np.savez(vectors_path, **{cid: out[i] for i, cid in enumerate(new_manifest)})
        manifest_path.write_text(_json.dumps(new_manifest), encoding="utf-8")
    except Exception as e:
        logger.warning(f"EmbeddingRAG: could not persist cache: {e}")

    return out
```

Note: `np.savez` with a `Path` appends `.npz` correctly. Chunk order stability matters: `_collect_documents` uses `glob` — sort the globs (`sorted(concepts_dir.glob("*.md"))`, same for hypotheses) so chunk order is deterministic across runs.

- [ ] **Step 3: .gitignore**

Append to `.gitignore`: `data/rag_cache/`

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/rag/ -q` — Expected: 2 passed. Also run any existing embedding tests: `python -m pytest tests/ -q -k "embedding or rag"`.

- [ ] **Step 5: Commit**

```bash
git add src/llm/embedding_rag.py tests/rag/ .gitignore
git commit -m "feat(rag): disk cache for knowledge embeddings (hash-keyed, incremental)"
```

---

## Task 7: Hybrid retrieval (RRF) + golden-query harness

**Files:**
- Modify: `src/llm/trading_knowledge_rag.py`
- Create: `tests/rag/golden_queries.json`
- Create: `tests/rag/test_retrieval_quality.py`
- Create: `tests/rag/test_hybrid_rrf.py`

**Interfaces:**
- `TradingKnowledgeRAG.retrieve_context(query, max_results=5)` now returns fused results; each chunk gains `"retrieval": "semantic" | "keyword" | "hybrid"` and keeps `relevance_score` (fused RRF score normalized to 0-1 range-ish). Signature unchanged.

- [ ] **Step 1: Write the failing RRF test**

```python
# tests/rag/test_hybrid_rrf.py
"""Hybrid fusion: exact glossary term matches must surface even when the
semantic path returns unrelated chunks, and vice versa."""
import sys
import types

import numpy as np
import pytest


class _FakeModel:
    def get_sentence_embedding_dimension(self):
        return 4

    def encode(self, texts, show_progress_bar=False):
        # Everything orthogonal-ish: semantic scores ~uniform, so keyword signal must win
        # for exact-term queries.
        rng = np.random.default_rng(42)
        return rng.random((len(texts), 4))


@pytest.fixture()
def kb(tmp_path, monkeypatch):
    module = types.ModuleType("sentence_transformers")
    module.SentenceTransformer = lambda *a, **kw: _FakeModel()
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    d = tmp_path / "kb"
    (d / "core_concepts").mkdir(parents=True)
    (d / "core_concepts" / "structure.md").write_text(
        "Fair value gaps and order blocks explained in depth.", encoding="utf-8"
    )
    (d / "trading_glossary.json").write_text(
        '{"FVG": "Fair Value Gap - a three-candle imbalance"}', encoding="utf-8"
    )
    return d


def test_exact_glossary_term_boosted(tmp_path, kb, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from src.llm.trading_knowledge_rag import TradingKnowledgeRAG

    rag = TradingKnowledgeRAG(str(kb))
    results = rag.retrieve_context("what is FVG?", max_results=3)
    assert results, "expected results"
    top = results[0]
    assert top.get("type") == "glossary", f"exact glossary term should rank first, got {top}"
    assert "retrieval" in top


def test_semantic_results_still_integrated(tmp_path, kb, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from src.llm.trading_knowledge_rag import TradingKnowledgeRAG

    rag = TradingKnowledgeRAG(str(kb))
    results = rag.retrieve_context("order blocks", max_results=5)
    assert any(r.get("type") == "concept" for r in results)
```

Run: `python -m pytest tests/rag/test_hybrid_rrf.py -q` — Expected: FAIL (no `retrieval` key / ranking assertion fails).

- [ ] **Step 2: Implement RRF fusion**

In `TradingKnowledgeRAG`, refactor `retrieve_context`:

```python
    def retrieve_context(self, query: str, max_results: int = 5) -> list[dict[str, Any]]:
        """Hybrid retrieval: RRF fusion of semantic + keyword rankings."""
        semantic = self._semantic_ranked(query, max_results * 3)
        keyword = self._keyword_ranked(query, max_results * 3)

        if semantic and keyword:
            return self._rrf_fuse(semantic, keyword, query)[:max_results]
        if semantic:
            for r in semantic:
                r.setdefault("retrieval", "semantic")
            return semantic[:max_results]
        for r in keyword:
            r.setdefault("retrieval", "keyword")
        return keyword[:max_results]

    def _semantic_ranked(self, query: str, limit: int) -> list[dict[str, Any]]:
        emb = self._embedding
        if emb is None:
            return []
        try:
            results = emb.retrieve_context(query, top_k=limit) or []
        except Exception as e:
            logger.warning(f"EmbeddingRAG failed, keyword-only: {e}")
            return []
        for r in results:
            r["retrieval"] = "semantic"
            r["relevance_score"] = r.get("score", 0.0)
        return results

    def _keyword_ranked(self, query: str, limit: int) -> list[dict[str, Any]]:
        # existing keyword logic from the old retrieve_context body
        # (glossary term matches + concept/hypothesis doc matches, sorted desc),
        # each dict tagged r["retrieval"] = "keyword"
        ...  # move the existing code here verbatim, adding the tag

    @staticmethod
    def _rrf_fuse(semantic: list[dict], keyword: list[dict], query: str, k: int = 60) -> list[dict]:
        """Reciprocal rank fusion; exact glossary-term matches get a one-rank boost."""
        scores: dict[str, float] = {}
        best: dict[str, dict] = {}
        for rank, item in enumerate(semantic):
            key = item.get("content", "")[:200]
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
            best.setdefault(key, item)
        for rank, item in enumerate(keyword):
            key = item.get("content", "")[:200]
            boost = 0.0
            if item.get("type") == "glossary" and item.get("term", "").lower() in query.lower():
                boost = 1.0 / (k + 1)  # treat as one rank better than first
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1) + boost
            best.setdefault(key, item)
        fused = sorted(scores, key=lambda kk: scores[kk], reverse=True)
        out = []
        for key in fused:
            item = dict(best[key])
            item["relevance_score"] = scores[key]
            item["retrieval"] = "hybrid"
            out.append(item)
        return out
```

(Move, don't copy, the old keyword body into `_keyword_ranked`.)

- [ ] **Step 3: Golden-query harness**

```json
// tests/rag/golden_queries.json
[
  {"query": "fair value gap", "expect": ["market_structure", "FVG"]},
  {"query": "what is an order block", "expect": ["market_structure", "Order Block"]},
  {"query": "liquidity sweep", "expect": ["market_structure"]},
  {"query": "break of structure vs change of character", "expect": ["market_structure", "BOS"]},
  {"query": "london kill zone times", "expect": ["market_structure", "kill_zones"]},
  {"query": "cumulative volume delta", "expect": ["market_structure", "CVD"]},
  {"query": "overnight margin cascade in crypto", "expect": ["overnight_margin_cascade"]},
  {"query": "funding rate", "expect": ["funding_rate"]},
  {"query": "backwardation vs contango", "expect": ["backwardation", "contango"]},
  {"query": "open interest", "expect": ["open_interest"]},
  {"query": "what is VWAP", "expect": ["VWAP", "vwap"]},
  {"query": "position sizing rules", "expect": ["position_sizing"]},
  {"query": "liquidation cascade", "expect": ["liquidation_cascade", "overnight_margin_cascade"]},
  {"query": "basis trade", "expect": ["basis"]},
  {"query": "max drawdown", "expect": ["max_drawdown"]}
]
```

```python
# tests/rag/test_retrieval_quality.py
"""Retrieval quality gate. Runs with the real knowledge base.

Default (CI) run uses a stub embedder so no model download is needed; the
keyword path must still hit the threshold. With RUN_LIVE_TESTS=1 the real
embedding model is used and hybrid mode is measured.
"""
import json
import os
import sys
import types
from pathlib import Path

import numpy as np
import pytest

GOLDEN = Path(__file__).parent / "golden_queries.json"
KB_DIR = Path("trading_knowledge")

LIVE = os.environ.get("RUN_LIVE_TESTS") == "1"


def _hit(results, expect):
    haystack = " ".join(
        f"{r.get('title', '')} {r.get('term', '')} {r.get('file', '')}".lower() for r in results
    )
    return any(e.lower() in haystack for e in expect)


@pytest.fixture(scope="module")
def rag():
    if not LIVE:
        module = types.ModuleType("sentence_transformers")
        rng = np.random.default_rng(7)

        class _Stub:
            def get_sentence_embedding_dimension(self):
                return 8

            def encode(self, texts, show_progress_bar=False):
                return rng.random((len(texts), 8))

        module.SentenceTransformer = lambda *a, **kw: _Stub()
        sys.modules["sentence_transformers"] = module
    from src.llm.trading_knowledge_rag import TradingKnowledgeRAG

    return TradingKnowledgeRAG(str(KB_DIR))


def test_golden_hit_rate(rag, tmp_path, monkeypatch):
    monkeypatch.setattr("src.llm.embedding_rag.EmbeddingRAG.__init__", lambda self, *a, **kw: None, raising=False)
    queries = json.loads(GOLDEN.read_text(encoding="utf-8"))
    # Use an isolated cache so CI doesn't touch the real one
    hits = 0
    for q in queries:
        results = rag.retrieve_context(q["query"], max_results=5)
        hits += _hit(results, q["expect"])
    rate = hits / len(queries)
    threshold = 0.8
    assert rate >= threshold, f"hit-rate {rate:.0%} < {threshold:.0%} on golden set"
```

If the stub-embedder path proves flaky (random vectors occasionally outrank keyword), pin the stub to return near-zero vectors (`np.full((len(texts), 8), 1e-6)`) so keyword dominates in CI — do that proactively.

- [ ] **Step 4: Run**

Run: `python -m pytest tests/rag/ -q`
Expected: all pass. Then optionally `RUN_LIVE_TESTS=1 python -m pytest tests/rag/test_retrieval_quality.py -q` locally to measure real hybrid quality (downloads model on first run) — record the hit-rate in the commit message.

- [ ] **Step 5: Commit**

```bash
git add src/llm/trading_knowledge_rag.py tests/rag/
git commit -m "feat(rag): RRF hybrid retrieval + golden-query quality harness (live hit-rate XX%)"
```

---

## Task 8: Rewrite enhanced_llm_client.py (cleanup + router injection)

**Files:**
- Rewrite: `src/llm/enhanced_llm_client.py`
- Test: `tests/test_enhanced_llm_client.py` (create)

**Interfaces:**
- `EnhancedLLMClient(settings=None, router=None)`: if `router` given (an entered ModelRouter), use it and do NOT own/close it; else `async with` creates its own (existing behavior). Methods unchanged: `analyze_with_knowledge`, `test_hypothesis`, `analyze_market_with_context`, `analyze_market_internals`, `deep_market_analysis`, `get_glossary_term`, `get_related_knowledge`.
- `EnhancedLLMManager` unchanged externally.
- DELETED: `EnhancedLMStudioClient`, `demo_enhanced_client`, `__main__` block.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_enhanced_llm_client.py
import pytest


class _FakeRouter:
    def __init__(self):
        self._entered = True
        self.calls = []

    async def generate(self, *, messages, capability="standard", max_tokens=800, temperature=0.3):
        self.calls.append({"messages": messages, "capability": capability})
        return {"choices": [{"message": {"content": "fake analysis"}}]}


@pytest.mark.asyncio
async def test_analyze_with_knowledge_uses_injected_router():
    from src.llm.enhanced_llm_client import EnhancedLLMClient

    router = _FakeRouter()
    client = EnhancedLLMClient(router=router)
    result = await client.analyze_with_knowledge("what is an FVG?")
    assert result == "fake analysis"
    assert router.calls, "router.generate was not called"
    prompt_text = router.calls[0]["messages"][-1]["content"]
    assert "FVG" in prompt_text or "fair value gap" in prompt_text.lower()


@pytest.mark.asyncio
async def test_legacy_class_removed():
    import src.llm.enhanced_llm_client as m

    assert not hasattr(m, "EnhancedLMStudioClient")
```

(If `pytest-asyncio` isn't configured for auto mode, check `pyproject.toml` — it declares `pytest-asyncio`; use `@pytest.mark.asyncio` as above.)

Run: `python -m pytest tests/test_enhanced_llm_client.py -q` — Expected: FAIL (legacy class exists / no router kwarg).

- [ ] **Step 2: Rewrite the file**

Replace `src/llm/enhanced_llm_client.py` entirely (Write tool, single-spaced, ~250 lines). Content = the current `EnhancedLLMClient` + `EnhancedLLMManager` classes verbatim in behavior, with these changes:
- `__init__(self, settings=None, router=None)`: store `self._router = router`; `self._owns_router = router is None`.
- `__aenter__`: only create/enter a ModelRouter when `self._owns_router`.
- `__aexit__`: only close when `self._owns_router`; never null out an injected router.
- Delete `EnhancedLMStudioClient`, `demo_enhanced_client`, `if __name__ == "__main__":`.
- Normal formatting, ruff-clean, line-length 120.

- [ ] **Step 3: Verify no dangling references**

Run: `grep -rn "EnhancedLMStudioClient" src/ tests/ marketpulse-client/src 2>/dev/null`
Expected: only possibly `ENHANCED_LLM_DOCUMENTATION.md` (docs — leave). If code references exist, update them to `EnhancedLLMClient`.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_enhanced_llm_client.py tests/rag/ -q` — Expected: pass. Plus `python -m pytest tests/ -q -k "llm" ` for regressions.

- [ ] **Step 5: Commit**

```bash
git add src/llm/enhanced_llm_client.py tests/test_enhanced_llm_client.py
git commit -m "refactor(llm): consolidate enhanced client, injectable router, drop legacy class"
```

---

## Task 9: Four RAG endpoints on routers/llm.py

**Files:**
- Modify: `src/api/routers/llm.py` (append)
- Modify: `src/api/routers/deps.py` (request models)
- Test: `tests/test_llm_rag_endpoints.py` (create)

**Interfaces:**
- New deps models: `EnhancedAnalysisRequest(query: str, market_data: dict | None = None, prompt_type: str = "trading_analyst", max_tokens: int = 400)`, `TestHypothesisRequest(hypothesis_name: str, market_data: dict | None = None)`, `RetrieveContextRequest(query: str, max_results: int = 5)`.
- New in llm.py: `async def _get_enhanced_client() -> EnhancedLLMClient` — builds on `_get_router()` (shared ModelRouter), injects via `EnhancedLLMClient(settings=settings, router=router)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_llm_rag_endpoints.py
import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.routers import llm as llm_router

client = TestClient(app)


class _FakeEnhanced:
    async def analyze_with_knowledge(self, query, market_data=None, prompt_type="trading_analyst", max_tokens=400):
        return f"analysis of: {query}"

    async def test_hypothesis(self, hypothesis_name, market_data=None):
        return {"hypothesis": hypothesis_name, "verdict": "inconclusive", "confidence": 0.5}


@pytest.fixture(autouse=True)
def fake_enhanced(monkeypatch):
    async def _get():
        return _FakeEnhanced()

    monkeypatch.setattr(llm_router, "_get_enhanced_client", _get)


def test_enhanced_analysis():
    r = client.post("/api/llm/enhanced-analysis", json={"query": "is NQ extended?"})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert "analysis" in body["data"]


def test_test_hypothesis():
    r = client.post("/api/llm/test-hypothesis", json={"hypothesis_name": "overnight_margin_cascade"})
    assert r.status_code == 200
    assert r.json()["data"]["hypothesis"] == "overnight_margin_cascade"


def test_knowledge_term_found():
    r = client.get("/api/llm/knowledge/FVG")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["definition"]


def test_knowledge_term_missing():
    r = client.get("/api/llm/knowledge/nonexistent_term_xyz")
    assert r.status_code == 200
    assert r.json()["success"] is False


def test_retrieve_context():
    r = client.post("/api/llm/retrieve-context", json={"query": "fair value gap", "max_results": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["chunks"]
    assert "retrieval_mode" in body["data"]
```

(`test_knowledge_term_found` / `test_retrieve_context` hit the real `TradingKnowledgeRAG` — keyword path works offline.)

Run: `python -m pytest tests/test_llm_rag_endpoints.py -q` — Expected: FAIL (404s).

- [ ] **Step 2: Add models to deps.py**

```python
class EnhancedAnalysisRequest(BaseModel):
    query: str
    market_data: dict[str, Any] | None = None
    prompt_type: str = "trading_analyst"
    max_tokens: int = 400


class TestHypothesisRequest(BaseModel):
    hypothesis_name: str
    market_data: dict[str, Any] | None = None


class RetrieveContextRequest(BaseModel):
    query: str
    max_results: int = 5
```

- [ ] **Step 3: Add endpoints to routers/llm.py**

Append (imports at top: `from src.llm.enhanced_llm_client import EnhancedLLMClient`, `from src.llm.trading_knowledge_rag import get_trading_rag`, and the three new models from `.deps`):

```python
async def _get_enhanced_client() -> "EnhancedLLMClient":
    """Enhanced (RAG-backed) client on the shared ModelRouter."""
    router = await _get_router()
    return EnhancedLLMClient(settings=settings, router=router)


@router.post("/enhanced-analysis", response_model=MarketResponse)
async def enhanced_analysis(request: EnhancedAnalysisRequest):
    """Knowledge-enhanced analysis via RAG + routed LLM."""
    try:
        client = await _get_enhanced_client()
        analysis = await client.analyze_with_knowledge(
            query=request.query,
            market_data=request.market_data,
            prompt_type=request.prompt_type,
            max_tokens=request.max_tokens,
        )
        if analysis is None:
            return MarketResponse(success=False, error="LLM unavailable", timestamp=datetime.now().isoformat())
        chunks = client.get_related_knowledge(request.query, max_results=3)
        return MarketResponse(
            success=True,
            data={"analysis": analysis, "knowledge_used": [c.get("title") or c.get("term") for c in chunks]},
            timestamp=datetime.now().isoformat(),
        )
    except Exception as e:
        logger.error(f"enhanced-analysis error: {e}")
        return MarketResponse(success=False, error=str(e), timestamp=datetime.now().isoformat())


@router.post("/test-hypothesis", response_model=MarketResponse)
async def test_hypothesis_endpoint(request: TestHypothesisRequest):
    """Test a trading hypothesis from trading_knowledge/hypotheses/."""
    try:
        client = await _get_enhanced_client()
        result = await client.test_hypothesis(request.hypothesis_name, request.market_data)
        if result is None:
            return MarketResponse(
                success=False, error="Hypothesis not found or LLM unavailable",
                timestamp=datetime.now().isoformat(),
            )
        return MarketResponse(success=True, data=result, timestamp=datetime.now().isoformat())
    except Exception as e:
        logger.error(f"test-hypothesis error: {e}")
        return MarketResponse(success=False, error=str(e), timestamp=datetime.now().isoformat())


@router.get("/knowledge/{term}", response_model=MarketResponse)
async def knowledge_term(term: str):
    """Glossary definition + related terms."""
    rag = get_trading_rag()
    definition = rag.get_glossary_term(term)
    if definition is None:
        return MarketResponse(success=False, error=f"Unknown term: {term}", timestamp=datetime.now().isoformat())
    return MarketResponse(
        success=True,
        data={"term": term, "definition": definition, "related": rag.get_related_terms(term)},
        timestamp=datetime.now().isoformat(),
    )


@router.post("/retrieve-context", response_model=MarketResponse)
async def retrieve_context_endpoint(request: RetrieveContextRequest):
    """Raw RAG retrieval (debug/UX: shows what context the LLM would see)."""
    rag = get_trading_rag()
    chunks = rag.retrieve_context(request.query, request.max_results)
    mode = chunks[0].get("retrieval", "keyword") if chunks else "none"
    return MarketResponse(
        success=True,
        data={"query": request.query, "chunks": chunks, "retrieval_mode": mode},
        timestamp=datetime.now().isoformat(),
    )
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_llm_rag_endpoints.py tests/test_route_parity.py -q`
Expected: pass. Parity will report 4 ADDED routes — regenerate fixture (`python scripts/snapshot_routes.py`), confirm the diff is exactly these 4 endpoints, commit it.

- [ ] **Step 5: Commit**

```bash
git add src/api/routers/llm.py src/api/routers/deps.py tests/test_llm_rag_endpoints.py tests/fixtures/route_snapshot.json
git commit -m "feat(llm): enhanced-analysis, test-hypothesis, knowledge, retrieve-context endpoints"
```

---

## Task 10: Docs, full suite, live smoke

**Files:**
- Modify: `BACKEND_DOCUMENTATION.md` (endpoint list)
- Create: `scripts/smoke_llm_rag.py`

- [ ] **Step 1: Document the 4 endpoints** in `BACKEND_DOCUMENTATION.md` under the LLM section (method, path, request body, one-line description — match existing doc style).

- [ ] **Step 2: Write the smoke script**

```python
# scripts/smoke_llm_rag.py
"""Manual live smoke test: boots nothing, expects server on :8000 and real LLM keys in env.
Usage: RUN server first (uvicorn src.api.main:app --port 8000), then: python scripts/smoke_llm_rag.py
"""
import json
import urllib.request

BASE = "http://localhost:8000"


def post(path, payload):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read())


if __name__ == "__main__":
    print("1. retrieve-context (offline RAG)...")
    rc = post("/api/llm/retrieve-context", {"query": "fair value gap", "max_results": 3})
    assert rc["success"], rc
    print(f"   mode={rc['data']['retrieval_mode']} chunks={len(rc['data']['chunks'])}")

    print("2. knowledge term...")
    kt = get("/api/llm/knowledge/FVG")
    assert kt["success"], kt
    print(f"   FVG: {kt['data']['definition'][:80]}")

    print("3. enhanced-analysis (live LLM)...")
    ea = post("/api/llm/enhanced-analysis", {"query": "What is a fair value gap and how is it traded?"})
    assert ea["success"], ea
    print(f"   analysis: {ea['data']['analysis'][:200]}")
    print(f"   knowledge_used: {ea['data']['knowledge_used']}")

    print("4. test-hypothesis (live LLM)...")
    th = post("/api/llm/test-hypothesis", {"hypothesis_name": "overnight_margin_cascade"})
    print(f"   success={th['success']} keys={list((th.get('data') or {}).keys())}")

    print("SMOKE OK")
```

- [ ] **Step 3: Full suite**

Run: `python -m pytest tests/ -q --timeout=300` (plus CI's ignore list from `.github/workflows/ci.yml`), `ruff check src/ tests/ scripts/`, `ruff format --check` on changed files.
Expected: green. Pre-existing failures unrelated to your changes: note them in the final report, do not fix.

- [ ] **Step 4: Live smoke (with user env)**

Boot: `uvicorn src.api.main:app --port 8000` (background), wait for /docs, then `python scripts/smoke_llm_rag.py`. Expect `SMOKE OK` with real provider responses (DeepSeek/GLM/MiniMax via ModelRouter). If no provider is reachable, report exactly which provider failed and why — do not mark the task done on a skipped smoke.

- [ ] **Step 5: Commit**

```bash
git add BACKEND_DOCUMENTATION.md scripts/smoke_llm_rag.py
git commit -m "docs+test: document RAG endpoints, add live smoke script"
```

---

## Self-Review Notes (plan author)

- Spec coverage: A1 safety net (T1, T2) ✓, state divergence (T3) ✓, mount+delete (T4) ✓, main.py size (T4+T5; options extraction removes ~650 lines, LLM/market/test/ws deletions remove ~1,300 → main.py ≈ 350-450 lines) ✓, 4 endpoints (T9) ✓, embedding cache (T6) ✓, hybrid RRF (T7) ✓, client cleanup (T8) ✓, quality harness (T7) ✓, docs (T10) ✓, live smoke (T10) ✓. `.gitignore` (T6) ✓.
- Type consistency: `_get_enhanced_client` defined T9 used in T9 tests ✓; `init_state` signature identical T3 test/impl/main.py call ✓; `EnhancedLLMClient(settings=..., router=...)` matches T8 ✓.
- Known soft spot: T4 Step 2's "port differences" instruction requires judgment; the parity + behavior tests are the guardrail. If an inline handler diverges from its router twin in user-visible behavior, prefer the ROUTER version (it is newer) unless the behavior test pinned inline behavior — then reconcile deliberately.
