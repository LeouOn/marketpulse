# MarketPulse — Current Repo State

**Date:** 2026-06-10
**Audited as part of:** Bitcoin long-term research lab effort
**Replaces:** `ANALYSIS_REPORT.md` (now archived at
`docs/superpowers/historical/2026-05-05-original-analysis-report.md`)

The 2026-05-05 analysis report was a snapshot at commit `1d71b6d` and is now
substantially out of date. This file is the ground truth as of 2026-06-10.

## Backend (`src/`) — ~17,500 LOC across 87 source files

- `src/api/main.py` is **2,339 lines** with 35 inline endpoints that
  duplicate properly-structured routers in `src/api/routers/`. The routers
  are **never mounted** (`include_router` not called for them), so the
  inline endpoints are the actually-served routes. **Phase A1 follow-up:**
  mount the routers and remove the inline duplicates. Deferred.
- Routers exist at `src/api/routers/{market,llm,websocket,symbols,screeners,data_quality,deps,test}.py`
  but are not mounted.
- Mounted endpoint modules: `ict_endpoints.py`, `divergence_endpoints.py`,
  `risk_endpoints.py`, `visualization_endpoints.py`, `ai_endpoints.py`,
  `backtest_endpoints.py`, plus the new `research_router.py` (B7).
- LLM: default provider is now **MiniMax-M3 on minimax.io** (international
  coding plan). Fallbacks: DeepSeek → LM Studio → OpenRouter. See
  `src/llm/model_router.py`.
- LLM agents: 14 files in `src/llm/agents/`. Only `base.py` and
  `orchestrator.py` are real. The other 11 (`technical_agent.py`,
  `strategy_agent.py`, `risk_agent.py`, `risk_quant_agent.py`,
  `macro_agent.py`, `ict_agent.py`, `options_agent.py`, `multi_tf_agent.py`,
  `hypothesis_agent.py`, `data_agent.py`, `critique_agent.py`,
  `alert_agent.py`) are 30–50 line stubs.

## Frontend (`marketpulse-client/`) — 28 active components, 6 dead removed

- Active dashboard: `ThreeColumnDashboard.tsx` (still uses raw `apiFetch`
  with manual `useState` polling — migration to React Query deferred).
- LLM chat: `llm-chat.tsx`.
- Research: `app/research/page.tsx` (chat), `app/research/reports/page.tsx`
  (list), `app/research/reports/[id]/page.tsx` (detail).
- **Phase A4 done:** deleted 5 dead components
  (`UnifiedDashboard`, `ConnectedMarketDashboard`, `EnhancedMarketDashboard`,
  `DataTable`, `SymbolSearch`) + `hooks/useOHLCData.ts` + dead exports
  `SparklineArea`, `MarketDataSkeleton`, `useDashboardData`, `useMacroData`,
  `useAIAnalysis`, `useBreadthData`, `useRealTimeMarketData`.
- **Phase A3 done:** fixed double-`/api` prefix in 5 components
  (`ThreeColumnDashboard`, `llm-chat`, `OptionsFlowTab`, `BacktestTab`,
  `RiskManagerTab`).
- **Phase A2 done:** renamed `src/proxy.ts` → `src/middleware.ts` so
  Next.js actually picks it up.

## BTC Research Lab (`src/research/`) — added in this session

| Module | Purpose |
|--------|---------|
| `data/` | BTC-USD daily (Yahoo, 2010+) + hourly (CryptoCompare, 2018+) CSV cache |
| `strategies/` | 7 strategies: BuyAndHold, NoTrade, DCAFixedAmount, DCAValueAveraging, MomentumTrend, MeanReversionBollinger, MeanReversionRSI |
| `scaling/` | 8 scaling models: FixedFractional, FixedDollar, KellyCriterion, VolatilityTargeted, RiskParity, DrawdownScaled, AntiMartingale, Martingale |
| `backtest/` | Event-driven engine, 12 metrics (CAGR, Sharpe, Sortino, Calmar, max DD, profit factor, hit rate, ...) |
| `montecarlo/` | 3 simulators: GBM, block bootstrap, 2-state regime-switching |
| `tools.py` | 9 LLM-callable tools in OpenAI function-calling format |
| `cli.py` | 9-subcommand CLI: `update-cache`, `data-summary`, `backtest`, `compare`, `montecarlo`, `list-reports`, `list-strategies`, `list-scaling` |
| `api/research_router.py` | 13 HTTP endpoints under `/api/research/*` (mounted in `main.py`) |
| `migrations/versions/002_btc_research.py` | Alembic migration adding 3 tables: `market_data.btc_ohlcv_daily`, `market_data.btc_ohlcv_hourly`, `analysis.research_reports` |

**160 tests pass across the research lab + MiniMax wiring.**

## CI / dev hygiene

- `.github/workflows/ci.yml` — ruff + pytest + npm lint + tsc on every PR.
- `mock_market` is now opt-in via `MARKETPULSE_ALLOW_MOCK=1` (default off).
  `src/api/market_data_collector.py` errors loudly when all data sources
  fail and the env var is unset.

## Still on the list (deferred)

- **A1** — `main.py` dedupe (mount routers, remove inline dupes). High-risk
  mechanical refactor across 2,339 lines. Best done in a focused follow-up
  PR with the routers covered by full integration tests first.
