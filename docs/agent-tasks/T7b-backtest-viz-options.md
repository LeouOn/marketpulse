# T7b — Sweep the backtest / visualization / options / ICT / divergence / risk endpoints

## Problem (verified 2026-09-28)
A smoke pass over the **parameterless** GET routes found three failures; parameterised routes were not tested at all.

- `GET /api/backtest/regime` → 500 `'YahooFinanceClient' object has no attribute 'get_historical_data'`. Fix the caller to use the client's existing method (probably `get_bars`);
  **do not edit `src/api/yahoo_client.py`** — T7a owns it.
- `GET /api/viz/market-heatmap` → 500 `404: No data available for heatmap` (an `HTTPException(404)` wrapped into a 500 by a broad `except`, and the underlying "no data" needs its own explanation).
- `GET /api/options/macro-context` → 200 but `vix.current_level`, `percentile`, `historical_mean` are all `null` — investigate why VIX data isn't populated and fix it.

## Goal
Every GET (and safe POST) route in these modules either works with real data or fails with a truthful status code and message.

## Steps
1. Fix the three above, with root causes (not blanket try/except).
2. Enumerate the routes with `app.openapi()` (or `src/api/route_utils.iter_routes`). For every route in your modules that takes parameters, call it with sensible inputs
   (e.g. `symbol=SPY`, `/api/backtest/run/SPY`, `/api/divergence/scan/SPY`, `/api/ict/*`, options chains/expirations, risk calculators).
   Live Yahoo is fine; keep the sweep small and sequential.
3. Fix genuine bugs; for routes that legitimately need unavailable resources (paid keys, live brokers) make them return a clear 4xx/5xx with a reason.
4. Add `tests/test_api_smoke.py`: an offline suite (FastAPI `TestClient`, monkeypatched Yahoo layer) asserting status + response shape for each route you touched, plus a `@pytest.mark.live` variant of the sweep.

## Constraints
Own only: `src/api/backtest_endpoints.py`, `visualization_endpoints.py`, `divergence_endpoints.py`, `ict_endpoints.py`, `risk_endpoints.py`, `src/api/routers/options.py`, `tests/test_api_smoke.py`
(plus the analysis modules those endpoints call, for genuine bugs — list every change). Additive response changes only.

## Acceptance
Report a table of routes swept: route · inputs · result before · result after. All previously failing routes fixed or explained. Full suite: no new failures.
