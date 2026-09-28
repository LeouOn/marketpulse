# T0 — One resolver for the FRED / EIA keys

**Prerequisite for:** T6. **Independent of:** everything else in wave A.

## Problem (verified 2026-09-28)
The owner put `FRED_API_KEY` and `EIA_API_KEY` in `.env`. Three code paths read them three different ways:

- `src/research/data/_fred_key.py` and `_eia_key.py` call `load_dotenv()` then `os.environ.get(...)` — works.
- `src/yield_curve/fetcher.py::_require_key` calls `os.getenv("FRED_API_KEY")` with **no** dotenv load. With the key only in `.env`
  it raises `RuntimeError: FRED_API_KEY not set`. This is a likely reason `/api/yield-curve/current` returns `data: null`.
- The README says the keys can instead live in `config/credentials.yaml` under `macro_data:` (`fred_api_key`, `eia_api_key`).
  **No code reads that section.** Check with `grep -rn macro_data src`.

`Settings` (pydantic) reads `.env` only into its own fields; it does not export to `os.environ`.

## Goal
A single function that finds a macro-data key with one documented precedence, used by every reader.

1. Add `src/core/keys.py` with `get_macro_key(name: str) -> str | None` and
   `require_macro_key(name: str, register_url: str) -> str` (raises `RuntimeError` with the existing "Register free at …" message).
2. Precedence: real process env var → `.env` (and `config/.env`) via `dotenv_values`, without mutating `os.environ` →
   `config/credentials.yaml` `macro_data.<name lower>` (`FRED_API_KEY` → `fred_api_key`). Ignore empty values and
   placeholder-looking values (`your_…`, `${…}`).
3. Migrate `_fred_key.py`, `_eia_key.py` and `yield_curve/fetcher.py::_require_key` to it. Keep their public names/signatures.
4. Leave `src/yield_curve/fetcher.py` otherwise alone (T6 owns the rest of that file and starts after you merge).

## Gotcha you must handle
Existing tests (`tests/test_research_data_fred.py::TestFredProviderMissingKey`, `tests/test_research_data_eia.py::test_missing_api_key_raises_runtime_error`,
and yield-curve tests) assert "missing key raises". After your change they would find the owner's real key in `.env`/`credentials.yaml`
and fail **only on this machine**. Make them hermetic: an env switch (for example `MARKETPULSE_KEYS_ENV_ONLY=1`, meaning "consult only
`os.environ`") set by an autouse fixture in the affected test modules — do not edit `tests/conftest.py` (T9 owns it).

## Acceptance
- New offline tests in `tests/test_macro_keys.py` cover: env wins over `.env` wins over yaml; empty/placeholder ignored; `.env`-only key found;
  missing key → clear `RuntimeError`; env switch works.
- Evidence: with `FRED_API_KEY` absent from the shell and present only in `.env`, `$PY -c "from src.yield_curve.fetcher import _require_key; print(bool(_require_key()))"`
  prints `True`. (Never print the key.)
- Live check (allowed): one FRED request (series `DGS10`, `limit=1`) and one EIA request (WTI spot `RWTC`, `length=1`) succeed through your resolver.
- Full suite: no new failures.
