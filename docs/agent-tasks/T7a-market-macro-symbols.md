# T7a — What in the market dashboard is real? Fix mislabelled macro symbols and write the provenance table

## Problem (verified 2026-09-28)
`GET /api/market/macro` returns values labelled as macro indicators that are actually ETF proxies:

- `DXY` = **28.70** (this is the `UUP` ETF; the dollar index trades near 100). `GC` = **378** (this is `GLD`, not gold futures / spot).
  The symbol maps are in **two places that must agree**: `macro_map` in `src/api/mock_market.py` (~L64; despite the filename it downloads Yahoo data) and
  `YahooFinanceClient.macro_symbols` in `src/api/yahoo_client.py` (~L47), which `src/api/routers/market.py` uses for the 52-week range — so the highs/lows are also for the proxy.
- `GET /api/market/breadth` returned `nyse_advancing: 9, nyse_declining: 1` — apparently derived from a handful of symbols, not the NYSE. Verify what it is.
- `market_session`, `economic_sentiment`, `risk_appetite`, `sector_performance` in the macro response come from `mock_market.py`.
  The dashboard UI has recently been reworked to show "honest" P&L and live status, so users will read these as real.

## Goal
1. **Audit** every field returned by `/api/market/{dashboard,internals,breadth,macro,ohlc-dashboard,data-quality}`: is it *live*, a *proxy*, *derived*, or *mock*? Write it up in
   `docs/data-provenance.md` (table: endpoint · field · source symbol/function · classification · notes).
2. **Fix the mislabelled indicators.** Prefer the true instruments (verify each live with yfinance before adopting: e.g. dollar index `DX-Y.NYB`, gold futures `GC=F`, 10y yield `^TNX`, WTI `CL=F`).
   Where a proxy must remain, keep the key but add additive fields (`symbol`, `instrument`, `is_proxy`) so the UI can label it. Keep the 52-week range consistent with the chosen symbol.
3. **Make mock data un-missable**: anything still mock must be flagged in the response (`"source": "mock"` or equivalent) and, if `MARKETPULSE_ALLOW_MOCK` is not set, absent
   rather than silently fabricated (see `src/api/market_data_collector.py:~178` for the existing opt-in convention).

## Constraints
- Additive response changes only; do not rename/remove existing keys (the Next.js client consumes them). Do **not** edit `marketpulse-client/` — list the label changes the UI should adopt under Follow-ups (T8 or the owner will do it).
- `src/api/yahoo_client.py` is yours; T7b must not need changes there (it will call the existing methods).

## Acceptance
- Live evidence: `/api/market/macro` shows plausible DXY (~90–110 range) and gold values with the new fields; quote before/after.
- Offline tests with a fake yfinance layer cover symbol mapping, 52-week consistency and the mock flagging. `docs/data-provenance.md` covers every field. Full suite: no new failures.
