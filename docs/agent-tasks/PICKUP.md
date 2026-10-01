# Pickup note — 2026-10-01

**State:** everything is merged and **pushed**: `main` = `origin/main` = `4e398c6` (82 commits, fast-forward, first push; only `main` was pushed).
All agent tasks (T0–T12) are done and merged, no agents are running, and only the shared checkout (on `main`) remains.

- **CI on GitHub is green for the first time** (the Jul–Sep runs all failed): frontend lint + build, and Python 3.11 and 3.12 each running the full suite — **1113 passed, 35 skipped**, identical to the local clean-room result (no `.env`, no keys).
  Baseline at the start of the revival was 919 pass / 20 fail / 6 errors.
- **Before pushing,** all 82 commits were scanned for the real key values and key patterns (nothing found; only placeholders and model names matched).
- The macro regime model was repaired this session: `REAL_YIELD_SHOCK` scores matched-horizon *changes* (it was never dominant in 1990–2026 before), the API and dashboard expose raw stress `scores`,
  and the Sahm look-back now matches FRED's published `SAHMCURRENT` (0 mismatches in 440 months). Details: `docs/STATUS.md`, `docs/regime-recession-study.md`, `docs/agent-tasks/FOLLOWUPS.md`.

## Open items and things to check

### Check soon
1. **GitHub Actions deprecation:** the CI run warns that `actions/checkout@v4` and friends target Node 20 and are being forced onto Node 24. Bump the action versions in `.github/workflows/ci.yml` before it becomes an error.
   The frontend job also prints ~97 non-failing `any` lint warnings (`marketpulse-client`), which could be cleaned up.
2. **Live model tests are not in CI** (no keys; `@pytest.mark.live` is skipped). The macro regime acceptance episodes and the Sahm-vs-FRED check only run by hand:
   `RUN_LIVE_TESTS=1 pytest tests/test_research_macro_regimes.py tests/test_research_macro_factors.py -k "backrun or tape or sahm" -p no:cacheprovider`. Re-run after touching `regimes.py`/`factors.py`, or consider a manual/scheduled workflow with a FRED secret.
3. **Look at the dashboard in a browser.** The regime bars (now stress scores), the DXY/gold labels and the empty states for withheld data were verified by jest, typecheck and a production build, not by eye.
4. **`ds4` against the real local server.** The provider is tested only against a fake server. Start your DeepSeek V4 server on `:8001` (the API itself uses `:8000`) and run one real completion through the router.
5. **Factor cache:** `MacroFactorProvider` caches derived columns already computed. Bump `_FACTOR_SCHEMA` in `src/research/macro/factors.py` whenever a derived definition (`sahm_recession`, `cpi_yoy`, …) changes, or the old values keep being served.
6. **Regime label flipping.** The dominant regime flips between `RISK_ON` and `REAL_YIELD_SHOCK` on small moves (28–30 Sep vs 1 Oct) because the argmax ignores near-ties. The scores show it; the UI could flag a "contested" reading or the model could add hysteresis.

### Known bugs, not fixed
- `OIL` / `HOUSING` `GET /api/research/{asset}/data` returns 500 on a NaN. Fix: run the payload through `src/api/json_utils.to_builtin` in `research_router.py` (`docs/STATUS.md` item 2).
- `/api/ai/status` reports an unresolved `${…}` key as configured (item 3). `/api/llm/chat` leaks MiniMax's inline `<think>…</think>` reasoning to the user (item 4).
- The agent pipeline (`src/llm/agents/`) has no tool calling on MiniMax (item 5).

### Ideas and analysis not started
- **Better recession early-warning.** The `RECESSION` score falls back on the IPMAN industrial-production proxy for the ISM PMI (real ISM isn't on FRED): ~10% precision (274 false vs 31 true days). Evaluate a regional Fed survey (Philadelphia / Empire State, both on FRED)
  with the T12 method (NBER agreement + the 8 acceptance episodes, neighbourhood of thresholds, negative controls). Separately, `RECESSION` is a **lagging labor-market state**, 31–91 days after the NBER start; consider relabelling it in the UI/docs.
- **Rates and debt, deeper.** The 2026-09-29 analysis found the 10y move is real yield + term premium (breakevens flat), and that debt dynamics depend on nominal growth vs the market yield. Not yet pulled: foreign holdings of Treasuries (FRED `FDHBFIN`), the Fed's balance sheet / QT, and auction data (not in FRED).
  A "rates & debt" panel would make that arithmetic part of the platform instead of a one-off.
- **Thesis tracking.** The agent tool registry has a hypothesis tracker (`hypothesis_tools`, `src/llm/hypothesis_tester.py`) that hasn't been looked at. Candidate hypotheses with measurable indicators: consumer demand falls (retail sales, saving rate, sentiment),
  hyperscaler capex keeps rising (quarterly capex; +77–110% YoY last quarter), oil structurally higher (real WTI percentile), BTC bull after the midterms (halving-cycle analogue; peak-to-trough ~363–372 days in the last two cycles).
- **BTC and real yields.** Weekly BTC returns barely respond to real yields (t ≈ −1); after 13-week real-yield surges of ≥50bp the next 13 weeks were weaker (n small, overlapping), and we are in that bucket now while BTC is up. Revisit.

### Housekeeping
- The shared venv (`.venv`) is on pydantic-ai 1.x while `requirements.txt` says `>=2,<3` (works on both). Align: `uv pip install --python .venv/bin/python -r requirements.txt`.
- Merged local `task/*` and `fix/*` branch labels remain (history is in `main`): `git branch -d $(git branch --list 'task/*')` removes them safely (`-d` refuses anything unmerged). Other remote branches (`feat/rag-followups`, `feat/warsh-simulator`, `opencode/proud-engine`) were left alone.
- `docs/STATUS.md` quotes test counts; refresh them when they drift (currently 1113 passed / 35 skipped).
- Rotate the EIA key if you care: a failing test once printed most of it in a session transcript (tests no longer expose keys; it never reached a commit).
- On any other clone run `git config blame.ignoreRevsFile .git-blame-ignore-revs` (the mechanical format commit `49ac5b5` is listed there).

## Workflow that worked (keep it)
One git worktree per task (`docs/agent-tasks/new-worktree.sh <ID> [base]`), disjoint file ownership, dependencies gated, integrate on a scratch branch and verify (normal **and** clean-room suite, plus a live smoke) before moving `main`.
For model changes: build a baseline first, prototype on a saved frame against positives **and** negative controls, check a neighbourhood of thresholds, then verify through the real endpoint (a padding bug only showed up there).
Never work in the shared checkout; check `git branch --show-current` before merging. Never `git add -A`; never print key values; scan a range for real secrets before pushing.
In zsh don't use `path` as a loop variable (it is tied to `PATH`) and don't put multi-word commands in unquoted variables.
