# T3a — Make the macro regime endpoints actually work with the FRED/EIA keys

## Problem (verified 2026-09-28, keys present)
`GET /api/research/regimes` → HTTP 503 `Macro factor data unavailable: 'MacroFactorProvider' object has no attribute 'load_frame'`.

- `src/api/research_router.py` L640 (`GET /api/research/regimes`) and L797 (`GET /api/research/{asset}/regime`) call `provider.load_frame(...)`.
- `src/research/macro/factors.py::MacroFactorProvider` only has `load_factors(start, end)` (L169) and `compute_zscores`.
- `tests/test_research_macro_factors.py::TestHappyPath::test_load_factors_uses_all_fred_series` fails: it expects `ISM_MANUFACTURING` among the FRED series
  requested, but the implementation requests others (`IPMAN`, `DTWEXBGS`, `DFII10`, …). The module docstring still lists `ism_pmi ← ISM_MANUFACTURING`.
  Hypothesis to verify against the live FRED API: FRED no longer hosts the ISM PMI, and the code deliberately substitutes another series.

## Goal
`/api/research/regimes` (and `GET /api/research/{asset}/regime`, e.g. `/api/research/BTC/regime`) return real data, computed from live FRED + EIA + Yahoo, and the tests describe the truth.

## Steps
1. Find the intended design: module docstrings, `docs/superpowers/specs/`, `git log -S load_frame` and `-S load_factors`. Decide whether the router or the provider is wrong;
   fix the side that's wrong (keep a thin alias only if both names are genuinely wanted).
2. Resolve the ISM question with evidence (query FRED `series?series_id=ISM_MANUFACTURING`-style lookups for the candidates the code names). Update either the
   implementation or the test, and update the factor table docstring so docs, code and tests agree.
3. Run the two endpoints against the real backend (spare port) and quote the response shape plus today's regime output. Check the failure paths too (no key → clear 503 message).
4. Run the live macro tests: `RUN_LIVE_TESTS=1 $PY -m pytest tests -q -k "macro or factor" -p no:cacheprovider`.

## Constraints
- Do **not** touch the key-reading files (`src/research/data/_fred_key.py`, `_eia_key.py`) — T0 owns them; the keys already resolve via `.env` today.
- Do not touch `src/research/data/` (T3b).

## Acceptance
- Endpoints return HTTP 200 with real values (evidence in report), offline tests cover both endpoints with a fake provider,
  `tests/test_research_macro_factors.py` fully green, full suite has no new failures.
