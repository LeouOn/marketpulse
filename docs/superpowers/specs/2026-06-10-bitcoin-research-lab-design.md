# Bitcoin Long-Term Research Lab — Design Spec

**Date:** 2026-06-10
**Repo:** `nimble-otter` (branch: `opencode/nimble-otter`, currently tracking `main` at `a0ceeda`)
**Author:** Sisyphus (in collaboration with the user)

---

## 0. Purpose and Scope

This repo (MarketPulse) is a FastAPI + Next.js real-time trading dashboard with a strong LLM/agentic infrastructure and an existing backtester. It is *not* purpose-built for long-term Bitcoin research. The user wants to use it as a home for a **Bitcoin long-term evaluation, Monte Carlo, and buy/sell scaling** research lab, driven by the LLM-agent loop that already exists in the codebase. To make that work, this spec defines:

1. **Phase A — Repo cleanup**: pay down the actual current debt (which is different from the stale `ANALYSIS_REPORT.md`).
2. **Phase B — Bitcoin Research Lab**: add a long-term BTC research module and wire it into the existing LLM agent runtime.
3. **Phase C — Default LLM**: switch the app's default model to `MiniMax-M3` on the `minimax.io` international coding-plan endpoint.

The user has explicitly requested all of Phase A (full cleanup) and an LLM-agent-driven research UX. Earlier mid-flight decisions (multi-timeframe data, inline-in-FastAPI agent, MiniMax as default provider) are also captured here.

---

## 1. Ground Truth (what the repo actually is)

The repo was audited in detail on 2026-06-10. Key facts:

### Backend (`src/`)
- **~87 Python source files, ~17,500 LOC.**
- `src/api/main.py` is **2,039 lines** with ~50 inline endpoints that **duplicate** the properly-structured routers in `src/api/routers/`. This is the #1 cleanup target.
- Routers already exist: `market.py`, `llm.py`, `websocket.py`, `symbols.py`, `screeners.py`, `data_quality.py`, `deps.py`, `test.py`.
- Standalone endpoint modules (mounted from main): `ai_endpoints.py`, `backtest_endpoints.py`, `ict_endpoints.py`, `divergence_endpoints.py`, `risk_endpoints.py`, `visualization_endpoints.py`.
- Data clients: `yahoo_client.py` (primary, 591 lines), plus `alpaca_client.py` (123), `rithmic_client.py` (149), `coinbase_client.py` (162), `mock_market.py` (235). The non-Yahoo clients are configured but rarely the winning fallback.
- LLM: `llm_client.py` (LM Studio), `enhanced_llm_client.py`, `model_router.py` (DeepSeek primary), `deepseek_client.py`, `minimax_client.py` (127), `system_prompts.py`, RAG (`embedding_rag.py`, `trading_knowledge_rag.py`, `knowledge_graph.py`).
- Agents: 14 files in `src/llm/agents/`. `base.py` and `orchestrator.py` are real. **11 are 30–50 line stubs** (`technical_agent.py`, `strategy_agent.py`, `risk_agent.py`, `risk_quant_agent.py`, `macro_agent.py`, `ict_agent.py`, `options_agent.py`, `multi_tf_agent.py`, `hypothesis_agent.py`, `data_agent.py`, `critique_agent.py`, `alert_agent.py`).
- Tools: 7 modules in `src/llm/tools/` (registry, upstream, technical, data, knowledge, hypothesis, **backtest_tools.py**, alert_tools).
- Backtesting: `src/backtesting/backtest_engine.py` (510 lines, FVG+Divergence strategy, metrics).
- Analysis: `ohlc_analyzer.py` (714), `technical_indicators.py` (456), `ict_concepts.py` (494), `ict_signal_generator.py` (402), `divergence_detector.py` (437), `order_flow.py` (488), `risk_manager.py` (388), `position_scaler.py` (307), `options_pricing.py` (266), `options_analyzer.py` (294), `options_screener.py` (365), `strategy_builder.py` (398), `macro_context.py` (317).
- In-memory state: `state/position_manager.py` (349), `journal/trade_tracker.py` (481) — not persisted.
- Database layer: `core/database.py` (492 LOC) with SQLAlchemy 2.0 ORM models and `DatabaseManager`.
- Migrations: only `001_new_tables.py` exists; many tables (options, ICT, trading) are SQL-only.
- Config: `core/config.py` (336 LOC) with pydantic-settings + YAML. The `minimax` provider is already configured but pointing to a placeholder model name.

### Frontend (`marketpulse-client/src/`)
- **28 active components / 6 dead components (~1,600 dead LOC).**
- Dead: `UnifiedDashboard.tsx` (620), `ConnectedMarketDashboard.tsx` (403, hardcodes `http://localhost:8000`), `EnhancedMarketDashboard.tsx` (299), `DataTable.tsx` (182), `SymbolSearch.tsx` (132). Plus `useOHLCData.ts` (legacy hooks). Plus `SparklineArea`, `MarketDataSkeleton`, several unused `useMarketData` exports.
- Pages: `/`, `/trending`, `/symbol/[symbol]`, `/chart/[symbol]`. API proxy routes: `/api/llm/chat`, `/api/llm/model-status`.
- Active dashboard is `ThreeColumnDashboard.tsx` (636 lines, uses raw `apiFetch` with manual polling — inconsistent with the rest of the app which uses React Query).
- `lib/api.ts` is real (142 lines, `MarketPulseAPIClient` class + `apiFetch`). The old report's claim that it didn't exist is **wrong**.
- `StrategyTab.tsx` uses **mock data** with `setTimeout` (not wired to backend).
- 24 test files exist in `tests/`, but no test files exist in `src/`.

### Two critical real bugs
1. **Middleware filename**: `src/proxy.ts` exists but Next.js requires the file to be named `src/middleware.ts`. The `/api/*` proxy that forwards to FastAPI is **not running**, so the home page market data, breadth, macro all fail silently.
2. **Double `/api` prefix**: `apiFetch` in `lib/api.ts` already prepends `/api` to endpoints. Many callers (`ThreeColumnDashboard`, `llm-chat`, `RiskManagerTab`, `BacktestTab`, `OptionsFlowTab`) pass `/api/...` as the endpoint, producing `/api/api/...`. The `MarketPulseAPIClient` class methods pass correctly (e.g. `/market/dashboard`).

### What is NOT in the repo
- **No BTC historical OHLCV data pipeline.** No multi-year backtest dataset. No `data/btc/` folder.
- **No Monte Carlo engine.**
- **No scaling model library** (Kelly, vol-targeted, drawdown-scaled, etc.) for backtests. (`position_scaler.py` exists in `analysis/` but is auto-scaling, not a comparison library.)
- **No research tool registry** distinct from the existing LLM tool registry.
- **No research UI** in the frontend.

---

## 2. Design

### 2.1 Architecture Overview

```
┌────────────────────────────────────────────────────────────────────────┐
│                         Frontend (Next.js)                             │
│   ┌────────────┐ ┌──────────┐ ┌──────────────┐ ┌──────────────────┐    │
│   │ Dashboard  │ │ Backtest │ │ Research Chat│ │ Strategy compare │    │
│   │  (React Q) │ │   Tab    │ │  (new page)  │ │   (new page)     │    │
│   └─────┬──────┘ └────┬─────┘ └──────┬───────┘ └────────┬─────────┘    │
│         │              │              │                  │              │
│         └──────────────┴──────────────┴──────────────────┘              │
│                            │ /api/*                                    │
│                            ▼                                           │
│                  Next.js middleware.ts                                 │
│                  (proxy to FastAPI :8000)                              │
└─────────────────────────────┬──────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────────┐
│                       FastAPI Backend                                  │
│                                                                        │
│   ┌──────────────────── routers/ ─────────────────────────────────┐   │
│   │  market.py    llm.py    websocket.py                          │   │
│   │  symbols.py   screeners.py  data_quality.py  test.py          │   │
│   │  research.py  ◄── NEW: chat, backtest, monte carlo, compare   │   │
│   └──────────────────────┬─────────────────────────────────────────┘   │
│                          │                                             │
│   ┌──────────────────── services/ ────────────────────────────────┐   │
│   │  llm/        agents/        tools/         analysis/           │   │
│   │  backtesting/  ◄── wraps existing + adds MC, scaling lib      │   │
│   │  data/btc/    ◄── NEW: historical loaders, OHLCV cache        │   │
│   │  state/       alerts/       journal/                          │   │
│   └───────────────────────────────────────────────────────────────┘   │
│                                                                        │
│   ┌──────────────────── core/ ─────────────────────────────────────┐   │
│   │  config.py (LLM defaults → minimax-m3 on minimax.io)          │   │
│   │  database.py  cache.py  validators.py                          │   │
│   └────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
         PostgreSQL        Redis         LLM Providers
         (31 tables)    (cache layer)  ┌──────────────────┐
                                       │ DEFAULT: MiniMax │
                                       │  minimax.io      │
                                       │  model: M3       │
                                       │ Fallbacks:       │
                                       │  DeepSeek → LM   │
                                       │  Studio → OR     │
                                       └──────────────────┘
```

### 2.2 Phase A — Repo Cleanup (the actual current debt)

| # | Task | Detail |
|---|------|--------|
| A1 | **Dedupe `main.py`** | Identify the ~50 inline endpoints in `src/api/main.py` that already exist in `src/api/routers/`. Remove the inline duplicates. Keep only: `FastAPI()` construction, CORS, lifespan, router mounting, WebSocket mounting, root health endpoint. Target: `main.py` < 200 lines. |
| A2 | **Move `minimax` client to primary** | Re-wire `src/llm/model_router.py` so the default routing target is the MiniMax provider. Update `src/core/config.py` defaults: `llm.minimax.base_url = "https://minimax.io"` (international coding plan endpoint), `llm.minimax.model = "MiniMax-M3"`. Keep DeepSeek, LM Studio, OpenRouter as fallbacks. |
| A3 | **Fix middleware filename** | Rename `marketpulse-client/src/proxy.ts` → `marketpulse-client/src/middleware.ts`. Verify `next.config.js` matcher is preserved. |
| A4 | **Fix double `/api` prefix** | Update `lib/api.ts` `apiFetch` callers in `ThreeColumnDashboard.tsx`, `llm-chat.tsx`, `RiskManagerTab.tsx`, `BacktestTab.tsx`, `OptionsFlowTab.tsx` to drop the leading `/api/`. Verify with a smoke test of the home page. |
| A5 | **Delete dead frontend code** | Remove: `UnifiedDashboard.tsx`, `ConnectedMarketDashboard.tsx`, `EnhancedMarketDashboard.tsx`, `DataTable.tsx`, `SymbolSearch.tsx`, `useOHLCData.ts`. Remove dead exports: `SparklineArea`, `MarketDataSkeleton`, `useDashboardData`, `useMacroData`, `useAIAnalysis`, `useBreadthData`, `useRealTimeMarketData`. |
| A6 | **Migrate `ThreeColumnDashboard` to React Query** | Replace raw `apiFetch` + `useState` + `useEffect` polling with the existing `useDashboardData`, `useMacroData`, `useBreadthData` hooks. These currently exist but are only used by the dead `UnifiedDashboard`. |
| A7 | **Wire `StrategyTab` to real backend** | Replace mock-data `setTimeout` with a real call to a new `GET /api/strategy/scan` endpoint (or reuse an existing one if suitable). If no suitable endpoint exists, create a thin one in `routers/strategies.py` backed by the analysis modules. |
| A8 | **Add Alembic migrations for SQL-only tables** | Generate Alembic migrations for the options tables (`02-options-tables.sql`), ICT tables (`02b-ict-tables.sql`), indexes (`03-create-indexes.sql`), and trading/risk tables (`04-risk-journal-tables.sql`). These are currently applied manually. |
| A9 | **Auto-apply all SQL on container init** | Move `02-*.sql`, `03-*.sql`, `04-*.sql` into `database/docker-entrypoint-initdb.d/` with proper ordering (01, 02, 02b, 03, 04), so Docker Postgres init runs the whole schema automatically. |
| A10 | **Make `mock_market` opt-in** | Currently `mock_market.py` is the silent fallback. Make it require an explicit `MARKETPULSE_ALLOW_MOCK=1` env var. Fail loud otherwise with `RuntimeError("data source unreachable; set MARKETPULSE_ALLOW_MOCK=1 to allow fallback")`. |
| A11 | **Add `pytest` smoke to CI** | Add a minimal `.github/workflows/ci.yml` (or update existing) to run `pytest tests/` + `ruff check src/` + `cd marketpulse-client && npm run lint` on every PR. |
| A12 | **Update `ANALYSIS_REPORT.md`** | Mark it as historical; replace with a new `docs/superpowers/specs/2026-06-10-repo-state.md` reflecting the ground truth established in this spec. |

### 2.3 Phase B — Bitcoin Long-Term Research Lab

#### B1. Historical BTC OHLCV data pipeline
- **Daily BTC-USD from 2010-01-01 to present.** Free source: Kaggle "Bitcoin Historical Data" CSV (validated + cached), with Yahoo Finance `BTC-USD` as a live-update source. Loader is idempotent (upsert by date).
- **Hourly BTC-USD from 2018-01-01 to present.** Free source: CryptoCompare public API (no key required) or Binance public klines.
- Storage: two new Postgres tables in the `market_data` schema:
  - `btc_ohlcv_daily(ts DATE PRIMARY KEY, open NUMERIC, high NUMERIC, low NUMERIC, close NUMERIC, volume NUMERIC, source TEXT)`
  - `btc_ohlcv_hourly(ts TIMESTAMPTZ PRIMARY KEY, open NUMERIC, high NUMERIC, low NUMERIC, close NUMERIC, volume NUMERIC, source TEXT)`
- Loader script: `src/research/data/load_btc_history.py` (idempotent, resumable).
- Local Parquet cache: `data/btc/{daily,hourly}.parquet` for fast iteration.
- New module: `src/research/data/__init__.py` exposes `load_daily(start, end)`, `load_hourly(start, end)`, `update_latest()`.

#### B2. Strategy library
- New module: `src/research/strategies/`
- Each strategy is a class with `name`, `description`, `generate_signals(df) -> pd.Series[float]` returning the **target position fraction in `[0, 1]`** for each bar.
- Strategies (v1):
  - `DCAFixedAmount` — buy fixed $ amount every N bars
  - `DCAValueAveraging` — adjust buy amount to hit target portfolio value
  - `MomentumTrend` — long when close > SMA(N), flat otherwise
  - `MeanReversionBollinger` — long when close < lower band, exit at middle
  - `MeanReversionRSI` — long when RSI < threshold, exit on recovery
  - `BuyAndHold` — baseline
  - `NoTrade` — baseline (zero)
- Each strategy is unit-tested against synthetic price series with known signals.

#### B3. Position-scaling models
- New module: `src/research/scaling/`
- All take `(equity, position_value, price, recent_returns, params) -> buy_size_usd` (or zero).
- Models (v1):
  - `FixedFractional` (e.g. 1% of equity per buy)
  - `FixedDollar`
  - `KellyCriterion` (full and half-Kelly)
  - `VolatilityTargeted` (size ∝ 1 / recent_vol)
  - `RiskParity` (size to equal risk contribution)
  - `DrawdownScaled` (reduce size as equity drops below SMA)
  - `AntiMartingale` (scale up after wins)
  - `Martingale` (baseline that should lose)
- Each scaling model is unit-tested independently of strategies.

#### B4. Backtest engine
- New module: `src/research/backtest/`
- Event-driven, vectorized where possible.
- Inputs: `(df, strategy, scaling_model, fee_bps, slippage_bps, starting_equity)`.
- Outputs: `BacktestResult` with:
  - `equity_curve: pd.Series`
  - `trades: pd.DataFrame` (timestamp, side, size, price, fees, slippage, pnl)
  - `metrics`: CAGR, Sharpe, Sortino, Calmar, max DD, DD duration, hit rate, profit factor, time-in-market, final equity
  - `drawdown_curve: pd.Series`
- Reuse the existing `src/backtesting/backtest_engine.py` for the FVG+Divergence strategy but make the research backtester general-purpose.

#### B5. Monte Carlo engine
- New module: `src/research/montecarlo/`
- Three simulators, all runnable in parallel:
  - `GeometricBrownianMotion(mu, sigma, n_paths, n_steps, dt, s0)`
  - `BlockBootstrap(returns, block_size, n_paths, n_steps)`
  - `RegimeSwitching(returns, n_states, n_paths, n_steps)` — two-state HMM-style switcher
- For each simulation, output:
  - `paths: ndarray (n_paths, n_steps)` of equity curves
  - `terminal_wealth: ndarray` (n_paths,)
  - `max_drawdown: ndarray` (n_paths,)
  - Summary stats: median, 5th/95th percentile, ruin probability
- Optional: simulate a *strategy* (not just GBM) by running the backtester on each path's price series.

#### B6. Research tools for the LLM agent
- New module: `src/research/tools.py` (or extend `src/llm/tools/backtest_tools.py`)
- Tool registry additions (each becomes a function the LLM can call):
  - `list_strategies() -> [{name, description}]`
  - `describe_strategy(name) -> {name, params, defaults, example}`
  - `list_scaling_models() -> [{name, description}]`
  - `describe_scaling_model(name) -> {name, params, defaults, example}`
  - `run_backtest(strategy, scaling, start, end, params) -> {metrics, equity_curve_b64, drawdown_b64, report_id}`
  - `run_monte_carlo(method, params, n_paths) -> {summary_stats, paths_b64, report_id}`
  - `compare_strategies(strategies, scaling, start, end) -> {table, equity_curves_b64, report_id}`
  - `compare_scaling(strategy, scalings, start, end) -> {table, equity_curves_b64, report_id}`
  - `get_data_summary(start, end) -> {rows, start, end, source, summary_stats}`
  - `explain_metric(name) -> {name, definition, formula, good_range}`
  - `list_reports() -> [{id, kind, created_at, params}]`
  - `get_report(id) -> {metrics, equity_curve_b64, ...}`
- Each tool is a thin Python wrapper around the Phase B modules. They share a common `ToolResult` envelope: `{success, data, error, report_id, b64_artifacts}`.
- Reports are persisted as files under `reports/{backtest,montecarlo,compare}/<id>.json` (and `.png` for plots) and as rows in a new `analysis.research_reports` table.

#### B7. Research chat endpoint (in FastAPI)
- New router: `src/api/routers/research.py`
- Endpoints:
  - `POST /api/research/chat` — single-turn chat with full tool-calling loop. Body: `{messages: [{role, content}], model?: string, use_minimax_default?: bool}`. Streams NDJSON events: `{type: "token" | "tool_call" | "tool_result" | "final" | "error", ...}`.
  - `GET /api/research/strategies` — list strategies
  - `GET /api/research/strategies/{name}` — describe strategy
  - `GET /api/research/scaling` — list scaling models
  - `GET /api/research/scaling/{name}` — describe scaling model
  - `POST /api/research/backtest` — run backtest
  - `POST /api/research/montecarlo` — run Monte Carlo
  - `POST /api/research/compare` — compare strategies or scaling
  - `GET /api/research/reports` — list saved reports
  - `GET /api/research/reports/{id}` — fetch one report (JSON)
  - `GET /api/research/reports/{id}/image/{kind}` — fetch equity curve / drawdown PNG
- The chat endpoint **uses the existing LLM runtime** (`src/llm/llm_client.py`, `src/llm/model_router.py`). The default provider is **MiniMax** (see Phase C). If the model doesn't support function calling, fall back to a structured-JSON prompt parser.

#### B8. Frontend research UI
- New page: `marketpulse-client/src/app/research/page.tsx` — chat-style interface
  - Left pane: conversation history (saved in `localStorage` for v1)
  - Center: streaming response with rendered tool calls (mini-cards) and tool results (metrics table + chart)
  - Right pane: a "what can I ask?" sidebar with example queries
- New page: `marketpulse-client/src/app/research/reports/page.tsx` — saved reports list
- New page: `marketpulse-client/src/app/research/reports/[id]/page.tsx` — single report detail
- Add `/research` to the Sidebar's active nav.
- Use the existing React Query + `apiFetch` patterns. Reuse the existing chart/table primitives where possible.

### 2.4 Phase C — Default LLM: MiniMax-M3 on minimax.io

| Setting | Value | Where |
|---|---|---|
| Default model routing target | MiniMax | `src/llm/model_router.py` |
| Base URL | `https://minimax.io` (international coding plan) | `src/core/config.py` `llm.minimax.base_url` |
| Model | `MiniMax-M3` | `src/core/config.py` `llm.minimax.model` |
| Env var override | `LLM_PROVIDER=minimax` | runtime |
| Fallback chain | DeepSeek → LM Studio → OpenRouter | unchanged |
| .env.example | new `MINIMAX_API_KEY=...` and updated `LLM_PROVIDER` comment | `.env.example` |
| config/credentials.example.yaml | add `minimax: {base_url, api_key, model}` block | `config/credentials.example.yaml` |

Note: the existing `src/llm/minimax_client.py` is a thin wrapper. It needs to be updated to point to the new base URL and pass the new model name. The `LLMManager` / `EnhancedLLMManager` should default to MiniMax when `LLM_PROVIDER` is unset.

### 2.5 Data flow for a research query

```
User: "Compare DCA $100/week vs. momentum with Kelly sizing since 2018 on BTC"
  ↓
POST /api/research/chat
  ↓
FastAPI: load messages, prepend system prompt + tool definitions
  ↓
LLM (MiniMax) decides to call:
   1. get_data_summary(start=2018-01-01, end=today)
   2. run_backtest(strategy="DCAFixedAmount", scaling="FixedDollar", params={"amount":100,"freq":"1W"}, start=..., end=...)
   3. run_backtest(strategy="MomentumTrend", scaling="KellyCriterion", start=..., end=...)
   4. compare_strategies([result1, result2])
  ↓
Tools run, return JSON + base64 PNG equity curves
  ↓
LLM synthesizes a natural-language comparison, citing the metrics
  ↓
Response streamed to frontend, chat UI renders tool cards + final text
  ↓
Report persisted under reports/compare/<id>.{json,png} and Postgres row
```

### 2.6 Component map (new files)

```
src/research/
├── __init__.py
├── data/
│   ├── __init__.py
│   ├── load_btc_history.py     # B1: idempotent loader
│   └── ohlcv.py                # B1: typed accessors + Parquet cache
├── strategies/
│   ├── __init__.py
│   ├── base.py                 # B2: Strategy ABC
│   ├── dca.py                  # B2: DCAFixedAmount, DCAValueAveraging
│   ├── momentum.py             # B2: MomentumTrend
│   ├── mean_reversion.py       # B2: Bollinger, RSI
│   ├── baselines.py            # B2: BuyAndHold, NoTrade
│   └── registry.py             # B2: name → class lookup
├── scaling/
│   ├── __init__.py
│   ├── base.py                 # B3: ScalingModel ABC
│   ├── fixed.py                # B3: FixedFractional, FixedDollar
│   ├── kelly.py                # B3: KellyCriterion
│   ├── vol.py                  # B3: VolatilityTargeted
│   ├── risk_parity.py          # B3
│   ├── drawdown.py             # B3
│   ├── martingale.py           # B3: Anti + plain
│   └── registry.py             # B3
├── backtest/
│   ├── __init__.py
│   ├── engine.py               # B4: BacktestEngine
│   ├── metrics.py              # B4: CAGR, Sharpe, Sortino, Calmar, max DD, ...
│   └── report.py               # B4: equity curve PNG, drawdown PNG, trade log CSV
├── montecarlo/
│   ├── __init__.py
│   ├── gbm.py                  # B5: GeometricBrownianMotion
│   ├── bootstrap.py            # B5: BlockBootstrap
│   ├── regime.py               # B5: RegimeSwitching
│   └── summary.py              # B5: stats + fan chart
├── tools.py                    # B6: tool registry (OpenAI function-calling format)
└── persistence.py              # B6: report_id ↔ file/db

src/api/routers/
└── research.py                 # B7: chat + REST endpoints

marketpulse-client/src/app/research/
├── page.tsx                    # B8: chat
├── reports/
│   ├── page.tsx                # B8: list
│   └── [id]/page.tsx           # B8: detail
└── components/
    ├── ResearchChat.tsx
    ├── ToolCallCard.tsx
    ├── MetricsTable.tsx
    └── EquityCurveImage.tsx
```

### 2.7 Data model additions (Postgres)

```sql
-- 04-research-tables.sql (in market_data schema; or analysis)
CREATE TABLE IF NOT EXISTS analysis.research_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kind TEXT NOT NULL CHECK (kind IN ('backtest', 'montecarlo', 'compare')),
    params JSONB NOT NULL,
    metrics JSONB NOT NULL,
    artifacts_path TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by TEXT,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS ix_research_reports_kind_created
    ON analysis.research_reports (kind, created_at DESC);
```

```sql
-- BTC historical data (in market_data schema)
CREATE TABLE IF NOT EXISTS market_data.btc_ohlcv_daily (
    ts DATE PRIMARY KEY,
    open NUMERIC, high NUMERIC, low NUMERIC, close NUMERIC,
    volume NUMERIC, source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS market_data.btc_ohlcv_hourly (
    ts TIMESTAMPTZ PRIMARY KEY,
    open NUMERIC, high NUMERIC, low NUMERIC, close NUMERIC,
    volume NUMERIC, source TEXT NOT NULL
);
```

### 2.8 Testing strategy

- **Unit tests for every strategy** with a synthetic constant-price series (expect flat position), a trending series (expect momentum long), a mean-reverting series (expect mean-reversion long).
- **Unit tests for every scaling model** with known equity/price scenarios.
- **Property-based test for backtester**: starting equity - total withdrawals == final equity + total fees + sum(trade_pnl), invariant holds across random strategies and scalings.
- **Monte Carlo**: GBM closed-form sanity check (mean terminal wealth ≈ s0 * exp(mu*T) within tolerance over 10k paths).
- **API smoke**: `POST /api/research/backtest` returns 200 with metrics in <30s for default params.
- **Chat smoke**: `POST /api/research/chat` with a canned query "What strategies do you have?" returns a tool call to `list_strategies` within 10s.
- **Frontend**: render `/research` page, type a query, see a tool card appear.

### 2.9 Error handling

- **Data missing**: if `load_daily(start, end)` returns empty, return a structured `{success: false, error: "no_data", range: [start, end]}` — never crash.
- **Tool returns no result**: LLM gets a `{success: false, error: "..."}` payload and is told to inform the user or retry.
- **LLM provider down**: tool loop catches exception, falls back to next provider in chain (MiniMax → DeepSeek → LM Studio → OpenRouter), records the failure in the response.
- **Report persistence fails**: API still returns the in-memory result; logs error; includes a `report_id = null` field.
- **Sandboxing**: the chat endpoint is read-only by default. The agent cannot place trades, modify positions, or call admin endpoints.

### 2.10 Out of scope (deliberately)

- Live trading execution
- Tax/regulatory reporting
- Multi-asset portfolio optimization (BTC-only for v1)
- Options/derivatives strategies on BTC (covered separately by existing options code)
- Real-time streaming backtests (backtests are historical)
- RL/ML-based strategy generation
- GPU acceleration

---

## 3. Rollout

The work is decomposed into 5 ordered milestones. Each ends in a working, committable, demoable state.

| # | Milestone | Contents | Verifiable by |
|---|-----------|----------|---------------|
| M1 | Default LLM | Phase C only (C1, C2) | `curl /api/llm/model-status` shows MiniMax-M3; `MINIMAX_API_KEY` from `.env` actually calls `minimax.io` |
| M2 | Repo cleanup | Phase A (A1–A12) | Home page renders market data; `main.py` < 200 lines; dead components gone; CI green |
| M3 | BTC data + strategies + scaling + backtest | Phase B1, B2, B3, B4 | CLI: `python -m src.research.cli backtest --strategy DCA --start 2018-01-01 --end 2024-12-31` produces report |
| M4 | Monte Carlo | Phase B5 | CLI: `python -m src.research.cli montecarlo --method gbm --n-paths 10000` produces summary |
| M5 | Agent + UI | Phase B6, B7, B8 | Browser: `/research` page streams a tool-using chat; reports page lists saved runs |

Milestones M3–M5 are intentionally independent and could be parallelized as separate worktrees if speed matters.

---

## 4. Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| `main.py` deduplication breaks some endpoint currently in use | Run full test suite + a curl smoke against every router-mounted prefix before/after; keep both versions side-by-side behind a feature flag if needed |
| Removing dead components breaks a hidden import | Grep for the component name across `src/`, `marketpulse-client/`, `tests/` before deleting |
| BTC historical CSV source moves/breaks | Loader validates schema and falls back to Yahoo Finance `BTC-USD` with a clear warning |
| MiniMax function-calling API differs from OpenAI's | Wrap in a thin adapter; fall back to JSON-prompt mode if function calling unsupported |
| Frontend research chat is heavyweight | Page-level lazy load; chat history in `localStorage` only (no DB) for v1 |
| Monte Carlo is slow for large N | Vectorize with numpy; use `concurrent.futures.ProcessPoolExecutor` for the bootstrap variant; cap n_paths at 50k by default |

---

## 5. Open Questions (to resolve before M3)

1. **BTC data source preference**: Kaggle CSV (one-time bulk) vs. Yahoo Finance only (live) vs. CryptoCompare (free API, hourly)? Recommendation: Kaggle + Yahoo, with CryptoCompare hourly.
2. **Should the research backtester be the existing `src/backtesting/backtest_engine.py` generalized, or a new sibling?** Recommendation: new sibling, leave existing untouched (it has FVG+Divergence assumptions baked in).
3. **Should reports persist to DB, files, or both?** Recommendation: both — JSON in DB for query, PNGs in `reports/` directory for the UI.
4. **Should the agent be allowed to chain multiple tool calls in one turn?** Recommendation: yes, with a max of 5 tool calls per turn to bound cost.
5. **Should the LLM system prompt be hard-coded or loaded from a file?** Recommendation: file (`config/research_system_prompt.txt`) so the user can iterate on tone/guardrails without code changes.

---

## 6. Success Criteria

The work is done when:

- [ ] `python -m src.research.cli backtest --strategy DCAFixedAmount --scaling FixedDollar --start 2018-01-01 --end 2024-12-31` produces a saved report with realistic BTC metrics.
- [ ] `python -m src.research.cli montecarlo --method gbm --n-paths 10000 --start 2018-01-01 --end 2024-12-31` produces a Monte Carlo summary.
- [ ] `curl -X POST http://localhost:8000/api/research/chat -d '{"messages":[{"role":"user","content":"What strategies do you have?"}]}'` streams a tool call to `list_strategies` and returns a natural-language answer.
- [ ] `curl http://localhost:8000/api/llm/model-status` shows MiniMax-M3 as the active model with `minimax.io` as the base.
- [ ] The home page `/` loads without errors and shows live market data (proves the middleware + double-`/api` fixes work).
- [ ] `pytest tests/ -q` is green; `ruff check src/ marketpulse-client/` is clean.
- [ ] The user can open `/research` in the browser, type "Compare DCA vs. momentum since 2018 on BTC", and see a streamed agentic answer with two backtest tool cards and a comparison summary.
