# T2a — Triage `tests/test_marketpulse.py` (9 failures)

## Problem
`tests/test_marketpulse.py` is an early-project test file. 9 tests fail on `main`. CI ignores the whole file
(`--ignore=tests/test_marketpulse.py` in `.github/workflows/ci.yml`), so nobody noticed. Observed failures:

- `TestDatabaseManager::test_save_price_data`, `::test_save_market_internals` — `sqlite3.OperationalError: no such table: main.prices` / `main.internals`
  (fixture never creates the tables).
- `TestAlpacaClient::test_format_internals_for_display` — `AlpacaClient has no attribute format_internals_for_display` / `key_symbols`.
- `TestMarketPulseCollector::test_format_internals_display`, `::test_classify_volatility` (`'HIGH' == 'EXTREME'`),
  `TestMarketCollectorIntegration::test_full_collection_workflow` (`save_market_internals` never called).
- `TestLLMIntegration::test_lm_studio_client_initialization` (`LMStudioClient has no attribute models`), `::test_llm_manager_status` (`KeyError: 'models'`).

## Goal
Every test in the file is either **passing and meaningful**, **deleted with a reason**, or **skipped with a reason** — and any genuine regression
it reveals is fixed or reported. No test may be weakened just to go green.

## Method (apply per test)
1. Read the code under test and `git log -S<symbol>` to learn whether the API change was deliberate.
2. Deliberate change → update the test to the current contract (assert the *new* behavior, don't just loosen). Removed feature → delete the test and
   say so in the report. Behavior that regressed (for example the volatility classification thresholds, or the collector no longer persisting
   internals) → fix the code and add a regression test, or report it if the fix is not clearly yours.
3. DB tests must use a temp SQLite database (`tmp_path`) with `Base.metadata.create_all`, never the repo's `marketpulse.db`.
4. No network in this file; use fakes.

## Acceptance
- `$PY -m pytest tests/test_marketpulse.py -q` green (skips allowed with reasons).
- Report a table: test → decision (updated / deleted / skipped / code fixed) → one-line justification.
- Do **not** edit `.github/workflows/ci.yml` (T10 removes the ignore once you're merged).
