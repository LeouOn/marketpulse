# Draft: Long-Term Bitcoin Evaluation Repo

## User's Stated Goal
- Long-term evaluation
- Monte Carlo simulations
- Different techniques for buy/sell scaling of Bitcoin
- Want to know if THIS repo is the right home

## What This Repo Is
- **Name:** MarketPulse
- **Purpose:** Real-time market analysis dashboard with LLM insights
- **Stack:** Python 3.11 / FastAPI / SQLAlchemy (async) / Alembic / Next.js
- **Assets supported:** NQ (primary), BTC, ETH
- **Data sources:** Alpaca (unused), Rithmic (futures), Coinbase, Yahoo Finance (actually used)
- **LLM:** LM Studio (local) primary, OpenRouter fallback

## Architecture Findings (from ANALYSIS_REPORT.md)
- 🔴 Monolithic `src/api/main.py` (1,489 lines, 25+ endpoints, duplicate routes)
- 🔴 5 of 7 dashboard components dead — only `UnifiedDashboard.tsx` rendered
- 🔴 `@/lib/api` imported but doesn't exist
- 🟡 Silent mock-data fallback in `market_collector.py`
- 🟡 `yfinance` aliased as `AlpacaClient` (misleading)
- 🟡 Sparse RAG knowledge base (1 doc)
- 🟠 Alembic in deps but no `alembic/` directory
- 🟠 Hardcoded `http://localhost:8000` in frontend

## What Exists for BTC Specifically
- Coinbase client (used for "BTC perpetual contracts")
- LLM can produce insights, but no historical OHLCV research pipeline
- No backtesting engine
- No Monte Carlo simulator
- No position-sizing / scaling logic
- No strategy framework / signal library

## What Would Need To Be Added For User's Goal
1. Historical BTC OHLCV data pipeline (years of data, not just live)
2. Strategy framework (DCA, momentum, mean reversion, etc.)
3. Position scaling models (fixed-fractional, Kelly, martingale, anti-martingale, volatility-targeted)
4. Monte Carlo engine (geometric Brownian motion, bootstrap, regime-switching)
5. Backtest runner with realistic fees/slippage
6. Walk-forward analysis
7. Risk metrics (Sharpe, Sortino, max DD, CAGR, Calmar)
8. Visualization (equity curves, drawdown, Monte Carlo distribution)

## Verdict (Preliminary)
- This repo is a **live dashboard product**, not a research lab
- Architectural debt makes it a poor foundation for serious quant research
- Could host the research as a new module, but that's working around the wrong base
- A purpose-built research repo would be leaner, faster, and purpose-aligned

## Open Questions
- Does the user want to USE this repo or REPLACE it? → **DECIDED: Fix this repo, then add research.**
- What's the scale of historical data? Days? Years? Decades?
- Live data feed vs. static dataset?
- What "techniques" interest them? (DCA variants, momentum, ML, RL, options overlays, etc.)
- Position sizing models to compare? (Kelly, fixed %, vol-target, risk parity)
- Execution target — research notebook, CLI, web app, scheduled runs?

## Direction: Fix + Research (2-phase project)
### Phase A — Pay down critical debt
- Split monolithic `src/api/main.py` into routers (market, llm, test, websocket)
- Remove dead dashboard components
- Fix or create the missing `@/lib/api` module
- Remove silent mock-data fallback (or make it loud)
- Remove dead Alpaca clients / rename mislabeled Yahoo client
- Resolve duplicate deps (react-query v3 vs v5)
- Set up Alembic migrations

### Phase B — Bitcoin long-term research
- Historical BTC data pipeline
- Strategy library
- Position-scaling models
- Monte Carlo engine
- Backtest runner with risk metrics
- Visualization / reporting

### Questions Remaining
1. Phase A scope: fix EVERYTHING the report flagged, or just the critical (🔴) items? → **DECIDED: Everything**
2. Phase B depth: notebook + CLI only, or full web integration into the dashboard? → **DECIDED: LLM agentic flow** — research is driven by an LLM calling structured tools, not by human-driven notebooks/CLI/dashboard
3. Historical data range — how far back?
4. Data source — CSV download, free API (Coinbase/Kaggle), or paid (Kaiko/CoinMetrics)?
5. **NEW:** Which LLM/agent runtime? OpenAI function-calling, Anthropic tool use, LangGraph, CrewAI, custom? The repo already has LM Studio (local) + OpenRouter fallback, plus a generic OpenAI client.
6. **NEW:** Where does the agent live? Inside the FastAPI app (chat endpoint that calls research tools), or as a separate service/process that calls the FastAPI API?
