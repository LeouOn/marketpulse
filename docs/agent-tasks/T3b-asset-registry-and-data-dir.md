# T3b — Asset registry truth + stop the app from rewriting tracked data files

Two related problems in `src/research/data/`. You own that package (except `_fred_key.py` / `_eia_key.py`, which T0 owns).

## Part 1 — Registry tests vs code
Two tests fail in `tests/test_research_data_asset_registry.py`:

- `test_registry_entries_use_distinct_providers_where_expected`: expects a `FredProvider`, registry gives `YahooProvider` (ticker `GLD`, "Gold (GLD ETF proxy)").
- `test_oil_ticker_is_dcoilwtico_and_housing_is_case_shiller`: expects `AssetRegistry["GOLD"].ticker == "GOLDAMGBD228NLBM"`, code has `GLD`.

Decide which is right, with evidence: `git log -S"GLD" -- src/research/data/__init__.py`, the specs in `docs/superpowers/specs/`, and a **live FRED lookup**
of `GOLDAMGBD228NLBM` (the series may have been discontinued — hypothesis, verify). Then fix the test **or** the registry, and keep comments/docstrings consistent
(the module also documents "5 assets: BTC, SP500-equivalent, XAU, DCOILWTICO, Case-Shiller").

## Part 2 — Mutable data lives in tracked files
A single `GET /api/research/data/summary` rewrote the **tracked** `data/btc/daily.csv` (162 insertions / 61 deletions) and created untracked `data/btc/hourly.csv` and
`data/btc/mvrv.csv` (`DAILY_CSV = DATA_DIR / "daily.csv"` at `src/research/data/__init__.py:155`). Running the app dirties the repo, and a commit can sweep the changes in.

1. Keep the tracked CSV as a read-only **seed**; write refreshed data to an untracked cache directory (for example `data/cache/`, overridable by `MARKETPULSE_DATA_DIR`).
   On first use, copy or read the seed so a fresh checkout still works offline.
2. Update `.gitignore` (you own it) for the cache dir and for `reports/`. Find out who creates `reports/` (`grep -rn "reports" src`) and say so.
3. Check the other loaders in the package (hourly, MVRV, Fear & Greed, on-chain, Alpaca/Yahoo caches) follow the same rule.

## Acceptance
- Registry tests green with a documented decision; offline tests prove the cache location, seed fallback, and that the tracked seed is never modified.
- Evidence: start the API, hit `/api/research/data/summary` and the research endpoints, then `git status --porcelain` shows **no** changes.
- Full suite: no new failures.
