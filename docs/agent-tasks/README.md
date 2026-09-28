# MarketPulse agent task pack

Sixteen self-contained tasks for parallel agents. Each task file is a complete prompt.
Baseline: `main` @ `35e5556` — `pytest tests -q` = **919 passed, 20 failed, 6 errors, 20 skipped**
(the failures are stale legacy tests, owned by T2a/T2b/T2c/T3a/T3b below).

## Running a task

```bash
docs/agent-tasks/new-worktree.sh T3a            # branches from HEAD
docs/agent-tasks/new-worktree.sh T6 main        # branch from a specific ref (use after T0 is merged)
```

That creates `../marketpulse-wt/<ID>` on branch `task/<ID>`, symlinks the (gitignored) `.env` and
`config/credentials.yaml`, and copies this README plus the task file into `.agent-task/`.
Start the agent inside that directory with:

> You are working on MarketPulse in this git worktree. Read `.agent-task/README.md` (shared rules), then
> `.agent-task/<task file>` and do the task. Report in the format the README specifies.

Merge finished branches into `main` yourself, in the order given under *Waves*.

## Shared rules (every agent)

1. **Secrets are read-only.** `.env` and `config/credentials.yaml` are symlinks to the owner's real files.
   Never edit, copy, print or commit them, and never echo a key value (print lengths or booleans only). A key goes
   only to its own provider (FRED key → stlouisfed.org, and so on).
2. **Interpreter.** Run from the worktree root using the shared venv:
   `PY=/home/yl/proj/marketpulse/.venv/bin/python` → `$PY -m pytest …`, `$PY -m uvicorn src.api.main:app --port <free port>`.
   Do not install or upgrade packages in the shared venv (T5 is the one exception: it builds its own `.venv`).
   Use a spare port (not 8000/3000) for anything you start, and stop it when done.
3. **Scope.** Edit only files your task owns (table below). If you need a change in another task's file, do not
   make it — list it under *Follow-ups* in your report.
4. **Git.** Commit on your branch only. Stage explicit paths (`git add path …`), never `git add -A`/`.`.
   Never stage `data/`, `reports/`, `*.db`, `.env`, `config/credentials.yaml`. The app and the test suite rewrite
   files under `data/` and `reports/`; restore/delete those before you finish so `git status` shows only your work.
   Small logical commits, conventional messages (`fix(scope): …`). Do not push, merge, or rebase onto other branches.
5. **Network.** Live calls to Yahoo, FRED, EIA and MiniMax are fine, sparingly (no loops, no hammering). Nothing else.
6. **Evidence over assertion.** For every behavior claim, run it and quote the output. Never write "should work".
7. **Tests.** Full suite (~75 s) before reporting: `$PY -m pytest tests -q -p no:cacheprovider`. You must not add
   failures elsewhere. New behavior needs tests that run offline (fakes/mocks); network tests get
   `@pytest.mark.live` (skipped unless `RUN_LIVE_TESTS=1`).
8. **Wrong premise?** If what the task says turns out to be false, stop and report what you found.
9. **Report** (your last message): *What changed* (files + why) · *Evidence* (commands + results) ·
   *Test results* before/after · *Commits* (SHAs) · *Open questions* · *Follow-ups* (for other tasks/owner).

Known gotchas: tests share a global settings singleton (`get_settings()`), so prefer `monkeypatch.setattr` over direct
assignment; `config/credentials.yaml` is read relative to the working directory.

## Tasks, ownership and prerequisites

| ID | Task | Owns (may edit) | Needs |
|----|------|-----------------|-------|
| T0 | [Shared FRED/EIA key resolver](T0-macro-key-resolver.md) | `src/core/keys.py` (new), `src/research/data/_fred_key.py`, `_eia_key.py`, `src/yield_curve/fetcher.py` (`_require_key` only), `src/core/config.py` (macro_data only) | — |
| T1 | [Undefined-name bugs](T1-undefined-names.md) | `src/analysis/order_flow.py`, `src/llm/minimax_client.py`, `src/llm/tools/technical_tools.py`, two `scripts/` files | — |
| T2a | [Stale `test_marketpulse.py`](T2a-stale-marketpulse-tests.md) | `tests/test_marketpulse.py` (+ genuine-bug fixes in `src/data/market_collector.py`, `src/api/alpaca_client.py`, `src/core/database.py`) | — |
| T2b | [Stale `test_llm_chat_cached_data.py`](T2b-stale-llm-chat-tests.md) | `tests/test_llm_chat_cached_data.py` (+ surgical fixes in `src/api/routers/llm.py`) | — |
| T2c | [`test_e2e_agentic.py` is a script](T2c-e2e-agentic-script.md) | `tests/test_e2e_agentic.py` (+ genuine-bug fixes in `src/llm/agents/`) | — |
| T3a | [Macro regimes endpoint](T3a-macro-regimes.md) | `src/research/macro/`, `src/api/research_router.py`, `tests/test_research_macro_*.py`, `tests/test_research_router.py` | — |
| T3b | [Asset registry + writable data dir](T3b-asset-registry-and-data-dir.md) | `src/research/data/` (except the key files), `tests/test_research_data*.py`, `.gitignore` | — |
| T4 | [`ds4` local LLM provider](T4-ds4-provider.md) | `src/core/config.py` (LLMSettings only), `src/llm/model_router.py`, `src/llm/llm_client.py`, `src/llm/ds4_client.py` (new), `src/api/routers/llm.py` (model-status only), `config/credentials.example.yaml`, `docs/local-llm-ds4.md`, new tests | — |
| T5 | [pydantic-ai 2.x port](T5-ai-analyst-pydantic-ai-2.md) | `src/ai/`, `src/api/ai_endpoints.py`, `requirements.txt`, new tests | — |
| T6 | [Yield-curve pipeline](T6-yield-curve-pipeline.md) | `src/yield_curve/`, `src/scheduler/`, `src/api/routers/yield_curve.py`, `tests/yield_curve/` | **T0** |
| T7a | [Market data provenance + macro symbols](T7a-market-macro-symbols.md) | `src/api/routers/market.py`, `src/api/mock_market.py`, `src/api/yahoo_client.py`, `docs/data-provenance.md` (new), new tests | — |
| T7b | [Backtest/viz/options endpoint sweep](T7b-backtest-viz-options.md) | `src/api/backtest_endpoints.py`, `visualization_endpoints.py`, `divergence_endpoints.py`, `ict_endpoints.py`, `risk_endpoints.py`, `src/api/routers/options.py`, `tests/test_api_smoke.py` (new) | — |
| T8 | [Frontend verification](T8-frontend-verify.md) | `marketpulse-client/**` | — |
| T9 | [Hermetic tests / CI parity](T9-hermetic-tests.md) | `tests/conftest.py`, other tests that dirty the tree or depend on local config | — |
| T10 | [CI green + format pass](T10-ci-green.md) | `.github/workflows/ci.yml`, `pyproject.toml`, whole-repo formatting | **T1, T2a, T2b, T2c, T3a, T3b, T5, T9** |
| T11 | [Docs + status map](T11-docs-accuracy.md) | `README.md`, `USAGE.md`, root `*.md`, `tasks`, `docs/STATUS.md` (new) | **T0, T3b, T4, T5, T6, T7a, T10** |

Shared-file hot spots (different hunks, so they merge cleanly if agents keep diffs surgical):
`src/core/config.py` (T0: macro_data · T4: LLMSettings) and `src/api/routers/llm.py` (T2b: chat context · T4: model-status).

## Waves and merge order

```
Wave A — start together (13 tasks, disjoint files)
  T0  T1  T2a  T2b  T2c  T3a  T3b  T4  T5  T7a  T7b  T8  T9
        │
        └─ T0 ──► Wave B: T6
                        │
Wave C (after every code branch above is merged) ──► T10 ──► T11
```

Suggested priority if you run fewer at once (they share CPU and the Yahoo/FRED rate limits): **T0, T3a, T7a, T4, T8, T1** first,
then T6 as soon as T0 is merged, then the rest.

Merge order: T0 → T1, T2*, T3*, T4, T5, T7*, T8, T9 (any order) → T6 → T10 → T11.
T10 reformats ~158 files, so it must run last and be merged immediately; every other branch conflicts with it.
