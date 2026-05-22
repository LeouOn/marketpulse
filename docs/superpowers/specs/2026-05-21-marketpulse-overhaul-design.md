# MarketPulse Comprehensive Overhaul Design

## Overview

Transform MarketPulse from a single-page dashboard into a multi-page trading platform with robust data infrastructure, professional charting, trending stock screeners, and a database schema designed for algorithmic trading.

**Approach:** Layered — DB schema → Data collection → API → Frontend shell → Pages.

---

## 1. Database Schema Redesign

### 1.1 Design Principles

- **OHLCV is the source of truth.** All indicators compute from price data. We never store pre-computed indicators in the same table as raw data.
- **Time-series optimized.** Partitioned by time range, indexed by `(symbol, timeframe, timestamp)`.
- **Snapshot tables for screener/breadth.** Daily snapshots of aggregate data (screeners, 52W levels, breadth) avoid re-fetching.
- **Schema-versioned via Alembic migrations.** No more manual SQL init scripts.

### 1.2 New Tables

All tables use the existing `market_data` and `analysis` schemas. Migrations are additive — existing tables are preserved.

#### `market_data.symbols` — Symbol Metadata Registry

Tracks every symbol the system knows about. Acts as the central reference for symbol normalization.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | SERIAL | PK | Auto-increment ID |
| symbol | VARCHAR(20) | UNIQUE NOT NULL | Normalized ticker (uppercase: SPY, BTC-USD) |
| name | VARCHAR(200) | | Company/asset full name |
| asset_type | VARCHAR(20) | NOT NULL | `stock`, `etf`, `crypto`, `forex`, `future`, `index` |
| exchange | VARCHAR(20) | | Exchange code (NYSE, NASDAQ, etc.) |
| sector | VARCHAR(50) | | GICS sector (stocks/ETFs only) |
| industry | VARCHAR(100) | | GICS industry group |
| currency | VARCHAR(3) | DEFAULT 'USD' | Trading currency |
| lot_size | DECIMAL(15,6) | DEFAULT 1 | Minimum trade unit |
| tick_size | DECIMAL(15,6) | DEFAULT 0.01 | Minimum price increment |
| is_active | BOOLEAN | DEFAULT TRUE | Soft-delete flag |
| yahoo_symbol | VARCHAR(20) | | Yahoo Finance ticker (differs for some: ^GSPC, BTC-USD) |
| alpaca_symbol | VARCHAR(20) | | Alpaca ticker if different |
| data_source | VARCHAR(20) | DEFAULT 'yahoo' | Primary data source |
| created_at | TIMESTAMPTZ | DEFAULT NOW() | |
| updated_at | TIMESTAMPTZ | DEFAULT NOW() | |

Indexes: `(symbol)`, `(asset_type)`, `(is_active)`, `(sector)`

#### `market_data.prices` — Enhanced OHLCV (migration of existing table)

Add columns for split/dividend adjustment tracking:

| New Column | Type | Default | Description |
|------------|------|---------|-------------|
| adjusted_close | DECIMAL(15,6) | NULL | Split+dividend adjusted close price |
| split_factor | DECIMAL(15,6) | DEFAULT 1.0 | Cumulative split factor |
| dividend_amount | DECIMAL(15,6) | DEFAULT 0.0 | Dividend paid on this date |
| source | VARCHAR(20) | DEFAULT 'yahoo' | Data provider that supplied this bar |

Existing columns preserved: `id, symbol, timeframe, timestamp, open_price, high_price, low_price, close_price, volume, trade_count, vwap, created_at`.

**Timeframes:** `1m, 5m, 15m, 1h, 4h, 1d, 1w, 1mo` (stored as VARCHAR(10)).

**Data retention policy:**
- 1m/5m: 30 days
- 15m/1h: 90 days
- 4h/1d: 2 years
- 1w/1mo: unlimited

#### `market_data.symbol_stats` — Daily Computed Statistics

Populated by a daily background job. Eliminates repeated computation of 52W levels, averages, etc.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | SERIAL | PK | |
| symbol | VARCHAR(20) | NOT NULL | |
| date | DATE | NOT NULL | Snapshot date |
| high_52w | DECIMAL(15,6) | | 52-week high |
| low_52w | DECIMAL(15,6) | | 52-week low |
| pct_from_52w_high | DECIMAL(8,4) | | % distance from 52W high |
| pct_from_52w_low | DECIMAL(8,4) | | % distance from 52W low |
| avg_volume_20d | BIGINT | | 20-day average volume |
| avg_volume_50d | BIGINT | | 50-day average volume |
| sma_20 | DECIMAL(15,6) | | 20-day SMA |
| sma_50 | DECIMAL(15,6) | | 50-day SMA |
| sma_200 | DECIMAL(15,6) | | 200-day SMA |
| atr_14 | DECIMAL(15,6) | | 14-day ATR |
| beta | DECIMAL(8,4) | | Beta vs SPY |
| market_cap | BIGINT | | Market capitalization |
| pe_ratio | DECIMAL(10,4) | | P/E ratio |
| prev_close | DECIMAL(15,6) | | Previous day close |
| day_range_pct | DECIMAL(8,4) | | (High-Low)/Close as % |
| year_high_date | DATE | | Date 52W high was set |
| year_low_date | DATE | | Date 52W low was set |
| created_at | TIMESTAMPTZ | DEFAULT NOW() | |

Unique: `(symbol, date)`. Indexes: `(symbol, date DESC)`, `(date DESC)`.

Updated once daily after market close. The 52W high/low, SMA, ATR, and volume stats are computed from the `prices` table — no external API calls needed after OHLCV data is stored.

#### `market_data.screener_snapshots` — Daily Screener Results

Stores Yahoo screener results (gainers, losers, most active) so we don't re-fetch during the day.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | SERIAL | PK | |
| snapshot_date | DATE | NOT NULL | |
| screener_type | VARCHAR(20) | NOT NULL | `gainers`, `losers`, `most_active`, `undervalued`, `small_cap_gainers` |
| symbol | VARCHAR(20) | NOT NULL | |
| rank | INTEGER | NOT NULL | Position in screener (1=top) |
| price | DECIMAL(15,6) | | |
| change_pct | DECIMAL(8,4) | | Daily % change |
| volume | BIGINT | | |
| market_cap | BIGINT | | |
| avg_volume_3m | BIGINT | | 3-month average volume |
| relative_volume | DECIMAL(8,4) | | Volume / avg_volume_3m |
| extra_data | JSONB | | Flexible field for screener-specific data |
| created_at | TIMESTAMPTZ | DEFAULT NOW() | |

Unique: `(snapshot_date, screener_type, symbol)`. Indexes: `(screener_type, snapshot_date DESC)`, `(snapshot_date DESC)`.

#### `market_data.breadth_snapshots` — Daily Market Breadth

Replaces the volatile in-memory breadth data with persisted daily snapshots.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | SERIAL | PK | |
| date | DATE | NOT NULL | |
| nyse_advancing | INTEGER | | NYSE stocks up on the day |
| nyse_declining | INTEGER | | NYSE stocks down on the day |
| nyse_unchanged | INTEGER | | NYSE stocks unchanged |
| nyse_ad_ratio | DECIMAL(8,4) | | Advancing / Declining |
| nasdaq_advancing | INTEGER | | |
| nasdaq_declining | INTEGER | | |
| nasdaq_unchanged | INTEGER | | |
| nasdaq_ad_ratio | DECIMAL(8,4) | | |
| new_highs_52w | INTEGER | | Stocks at 52-week highs |
| new_lows_52w | INTEGER | | Stocks at 52-week lows |
| tick_avg_30m | DECIMAL(8,2) | | $TICK 30-min average |
| vold_nyse | BIGINT | | NYSE up volume - down volume |
| mcclellan_osc | DECIMAL(8,4) | | McClellan Oscillator |
| mcclellan_sum | DECIMAL(8,4) | | McClellan Summation Index |
| trin | DECIMAL(8,4) | | Arms Index (TRIN) |
| created_at | TIMESTAMPTZ | DEFAULT NOW() | |

Unique: `(date)`. Index: `(date DESC)`.

#### `market_data.data_fetch_log` — API Call Audit Trail

Tracks every external API call for monitoring rate limits and debugging.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | SERIAL | PK | |
| source | VARCHAR(20) | NOT NULL | `yahoo`, `alpaca`, `coinbase`, `rithmic` |
| endpoint | VARCHAR(200) | NOT NULL | API path or method called |
| symbols | TEXT | | Comma-separated symbols requested |
| status | VARCHAR(10) | NOT NULL | `success`, `error`, `rate_limited` |
| response_ms | INTEGER | | Response time in milliseconds |
| bars_fetched | INTEGER | DEFAULT 0 | Number of bars/batches fetched |
| error_message | TEXT | | Error details if failed |
| created_at | TIMESTAMPTZ | DEFAULT NOW() | |

Index: `(source, created_at DESC)`, `(created_at DESC)`.

Auto-pruned: rows older than 30 days deleted by weekly cleanup job.

#### `analysis.indicators` — Future-Use Indicator Storage

Schema-ready for when we want to persist computed indicators. Empty initially, populated on demand.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | SERIAL | PK | |
| symbol | VARCHAR(20) | NOT NULL | |
| timeframe | VARCHAR(10) | NOT NULL | |
| timestamp | TIMESTAMPTZ | NOT NULL | Bar timestamp this indicator applies to |
| indicator_type | VARCHAR(30) | NOT NULL | `sma`, `ema`, `rsi`, `macd`, `bbands`, `atr`, `vwap` |
| params | JSONB | NOT NULL | Indicator parameters: `{"period": 14}` |
| value | DECIMAL(15,6) | | Single-value indicators (RSI, ATR) |
| values | JSONB | | Multi-value indicators (MACD: {"macd": x, "signal": y, "histogram": z}) |
| created_at | TIMESTAMPTZ | DEFAULT NOW() | |

Unique: `(symbol, timeframe, timestamp, indicator_type, params)`. Indexes: `(symbol, timeframe, timestamp DESC)`, `(indicator_type)`.

### 1.3 Alembic Migration Setup

- Initialize Alembic in `src/migrations/` with async support.
- First migration: create all new tables (additive — don't touch existing ones).
- Existing tables get migrated separately: add new columns to `prices`, create new tables.
- All migrations use `CREATE TABLE IF NOT EXISTS` for safety.

---

## 2. Data Collection Layer

### 2.1 Background Job Architecture

Replace the current `run_continuous_monitoring()` loop with a structured scheduler.

**Library:** `APScheduler` (AsyncIOScheduler) — lightweight, no external broker needed.

**Jobs:**

| Job | Schedule | What | API Calls |
|-----|----------|------|-----------|
| `fetch_realtime_quotes` | Every 30s during market hours | Current prices for tracked symbols | 1 Yahoo `download()` batch |
| `fetch_daily_ohlcv` | After market close (4:15 PM ET) | Daily bars for all active symbols | 1 batch per symbol group |
| `fetch_intraday_ohlcv` | Every 15 min during market hours | 5m bars for major symbols | 1 batch per symbol |
| `compute_daily_stats` | After `fetch_daily_ohlcv` completes | Calculate SMAs, ATR, 52W levels, volume stats from DB | 0 (pure computation) |
| `fetch_screener_data` | Every 30 min during market hours | Yahoo gainers/losers/most-active | 3 calls |
| `fetch_breadth_data` | Every 5 min during market hours | A/D, TICK, VOLD via ETF proxies | 1 batch |
| `persist_breadth_snapshot` | After market close | Save final breadth numbers to DB | 0 |
| `cleanup_old_data` | Daily at midnight ET | Prune intraday bars past retention, audit log > 30d | 0 |
| `validate_data_quality` | Hourly | Check for gaps, stale data, anomalies | 0 |

### 2.2 OHLCV Data Pipeline

**Fetch → Validate → Store → Emit**

1. **Fetch:** Call Yahoo `get_bars(symbol, timeframe)`. Returns DataFrame.
2. **Validate:** Check for:
   - Missing bars (gaps in time series)
   - Zero volume (suspicious for liquid symbols)
   - Price outside 3-sigma of recent range
   - `high < low` or `close > high * 1.1` (data corruption)
3. **Store:** Upsert into `market_data.prices` using `INSERT ... ON CONFLICT (symbol, timeframe, timestamp) DO UPDATE`.
4. **Emit:** Publish to Redis channel `ohlcv:{symbol}` for real-time subscribers (future WebSocket).

### 2.3 Screener Data Pipeline

1. **Fetch:** Call `yf.download()` screener endpoints for gainers/losers/most_active.
2. **Enrich:** For each screener result, look up `symbol_stats` for 52W levels, avg volume, relative volume.
3. **Store:** Insert into `screener_snapshots`. Overwrite same-day data.
4. **Cache:** Store in Redis with key `screener:{type}` TTL=30min for fast API reads.

### 2.4 52-Week High/Low Calculation

Computed purely from stored `market_data.prices` data:

```sql
SELECT MAX(high_price), MIN(low_price)
FROM market_data.prices
WHERE symbol = :symbol
  AND timeframe = '1d'
  AND timestamp >= NOW() - INTERVAL '52 weeks'
```

No API call needed. Updated daily in `symbol_stats` table. Also available on-demand via API for any symbol.

### 2.5 Symbol Auto-Registration

When a new symbol appears in any data fetch (screener result, manual lookup, etc.):
1. Check if it exists in `market_data.symbols`.
2. If not, fetch basic info from Yahoo (name, sector, exchange, market cap).
3. Insert into `market_data.symbols`.
4. Start collecting data for it based on its asset type.

---

## 3. API Layer Enhancements

### 3.1 New Endpoints

#### Screeners

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/market/screeners/{type}` | Get latest screener results. Types: `gainers`, `losers`, `most_active` |
| GET | `/api/market/screeners/{type}/history` | Historical screener snapshots (which stocks appeared repeatedly) |

Response includes: rank, symbol, name, price, change_pct, volume, relative_volume, 52W high/low, pct_from_52w_high.

#### Symbol Detail

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/market/symbols` | List all tracked symbols with metadata |
| GET | `/api/market/symbols/{symbol}` | Full symbol profile: metadata + stats + latest price |
| GET | `/api/market/symbols/{symbol}/stats` | Daily statistics (52W levels, SMAs, ATR, etc.) |
| GET | `/api/market/symbols/{symbol}/52w-range` | 52-week high/low with dates and % from current |

#### Enhanced Historical Data

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/market/historical/{symbol}` | Historical OHLCV from DB (falls back to Yahoo if not cached) |
| GET | `/api/market/historical/{symbol}/intraday` | Intraday bars (5m, 15m, 1h) from DB |

These replace the current `/api/market/historical` endpoint with symbol-in-path style.

#### Data Quality

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/market/data-quality` | Overview: which symbols have data, last update times, gaps detected |
| GET | `/api/market/data-quality/{symbol}` | Per-symbol data quality report |

### 3.2 Modified Endpoints

- **`/api/market/dashboard`** — Add `screener_summary` field (top 3 gainers/losers), `symbol_stats` for tracked symbols (52W levels, SMAs).
- **`/api/market/macro`** — Add 52W high/low for each macro symbol.
- **`/api/market/breadth`** — Read from `breadth_snapshots` table instead of live Yahoo calculation when outside market hours.

### 3.3 Response Optimization

- **Conditional caching headers:** `ETag` + `Cache-Control: max-age=30` for real-time data, `max-age=3600` for daily stats.
- **Field selection:** Support `?fields=price,change_pct,52w_high` to reduce payload size.
- **Batch symbol lookup:** `/api/market/symbols?symbols=SPY,QQQ,AAPL` for multi-symbol queries.

---

## 4. Frontend Architecture

### 4.1 Multi-Page Routing

```
/                     → Dashboard (enhanced current view)
/trending             → Screener page (gainers, losers, most active)
/chart/[symbol]       → Full chart page with TradingView Lightweight Charts
/symbol/[symbol]      → Symbol detail page (profile, stats, 52W range)
/alerts               → Alerts management (future)
/settings             → Data sources, tracked symbols (future)
```

### 4.2 Layout Shell

**Shared layout with:**

- **Top bar:** Logo, global search (symbol lookup with autocomplete), connection status indicator, last update time, settings gear.
- **Sidebar navigation:** Icon + label nav items. Collapsible on mobile.
- **Content area:** Renders the active page.

```
┌─────────────────────────────────────────────────────┐
│ [Logo] MarketPulse    [Search...]  ● Live  3:45 PM  │
├──────┬──────────────────────────────────────────────┤
│ 📊   │                                              │
│ Dash │           Page Content                       │
│      │                                              │
│ 🔥   │                                              │
│ Trend│                                              │
│      │                                              │
│ 📈   │                                              │
│Charts│                                              │
│      │                                              │
│ 🔔   │                                              │
│Alerts│                                              │
│      │                                              │
│ ⚙️   │                                              │
│ Set  │                                              │
└──────┴──────────────────────────────────────────────┤
│ Data: Yahoo Finance | Refresh: 30s | v0.3.0        │
└─────────────────────────────────────────────────────┘
```

**Sidebar behavior:**
- Desktop (`lg+`): Fixed sidebar, 64px wide (icons only) expanding to 200px on hover or click.
- Mobile: Hidden by default, hamburger menu toggle, overlay sidebar.

### 4.3 Page Designs

#### Dashboard Page (`/`)

Enhanced version of the current 3-column layout:

**Changes from current:**
- Sparklines use **real historical data** from DB (last 24 data points) instead of synthetic PRNG data.
- Each symbol row is **clickable** → navigates to `/chart/[symbol]`.
- Data tables show **52W range indicator** (small bar showing where current price sits between 52W low and high).
- Add **mini screener widget** in the dashboard showing top 3 gainers + top 3 losers.
- Market internals card reads from persisted breadth data when market is closed.
- Better card spacing: consistent 16px padding, 8px gap grid.
- Animated number transitions (price changes animate smoothly instead of jumping).

**52W Range Indicator:**

```
SPY  $591.42  ▓▓▓▓▓▓▓▓▓▓▓░░░░  +1.2%
                ↑           ↑
            52W Low    52W High
```

A small horizontal bar inside each table row showing current price position within the 52-week range. Green fill = near highs, red fill = near lows.

#### Trending Page (`/trending`)

Three tabbed views: **Gainers**, **Losers**, **Most Active**.

Each tab shows a responsive data table with columns:

| Column | Description |
|--------|-------------|
| Rank | Position (1-20) |
| Symbol | Ticker + company name |
| Price | Current price |
| Change % | Daily change with color coding |
| Volume | Current volume |
| Rel Vol | Volume vs 3-month average |
| 52W Range | Visual bar indicator |
| % from 52W High | How far from 52W high |
| Sparkline | 5-day mini chart |
| Actions | Click to open chart page |

**Features:**
- Sort by any column (click column header).
- Filter by market cap tier (Large, Mid, Small, Micro).
- Auto-refresh every 60s during market hours.
- Historical view: compare today's screener to yesterday's (new entries, drop-offs).

#### Chart Page (`/chart/[symbol]`)

Full TradingView Lightweight Charts integration.

**Chart features:**
- Candlestick/OHLC chart with volume bars below.
- Timeframe selector: 5m, 15m, 1h, 4h, 1D, 1W.
- Overlays: SMA(20), SMA(50), SMA(200), EMA(12), EMA(26), Bollinger Bands, VWAP.
- Studies pane: RSI, MACD, Volume Profile.
- Crosshair with price/date tooltip.
- Data loaded from DB (historical) with real-time price overlay.

**Sidebar panel:**
- Symbol info: name, exchange, sector, market cap, P/E.
- 52W range bar.
- Key statistics: avg volume, ATR, beta.
- Support/resistance levels (from OHLC analysis).
- Quick links: related symbols, sector peers.

**Below chart:**
- AI analysis summary (from existing LLM integration).
- Recent alerts for this symbol.

#### Symbol Detail Page (`/symbol/[symbol]`)

Profile + stats page for any tracked symbol.

**Sections:**
1. **Header:** Symbol, name, price, daily change, 52W range bar.
2. **Key Statistics:** Market cap, P/E, volume, avg volume, 52W high/low, SMA values, ATR, beta.
3. **52-Week Analysis:** Visual chart of price vs 52W high/low bands over time.
4. **Sector Comparison:** How this symbol ranks vs sector peers.
5. **Data Quality:** When data was last fetched, any gaps detected.

### 4.4 Component Library

Extract reusable components from the current monolithic `UnifiedDashboard.tsx`:

| Component | Purpose |
|-----------|---------|
| `LayoutShell` | Sidebar + top bar + content area |
| `Sidebar` | Navigation with icons, collapse/expand |
| `TopBar` | Logo, search, status, clock |
| `SymbolSearch` | Autocomplete search with symbol lookup |
| `DataTable` | Generic sortable, filterable data table |
| `PriceCell` | Price with color-coded change + animation |
| `Sparkline` | Real-data sparkline (enhanced current version) |
| `FiftyTwoWeekBar` | 52W range position indicator |
| `ScreenerTable` | Specialized DataTable for screener results |
| `ChartWidget` | TradingView Lightweight Charts wrapper |
| `SymbolCard` | Compact symbol overview card |
| `StatTile` | Single metric tile (used in market internals) |
| `SectorHeatmap` | Sector performance grid |
| `ConnectionStatus` | Live/mock data source indicator |
| `RefreshControl` | Manual/auto refresh with countdown |

### 4.5 Styling Enhancements

**Spacing system:** Use Tailwind's 4px scale consistently:
- Cards: `p-4` (16px), gap between cards: `gap-4` (16px)
- Section headings: `mb-3` (12px), `text-sm font-medium text-gray-400`
- Table rows: `py-2` (8px vertical), compact but not cramped
- Page margins: `p-6` (24px) desktop, `p-4` (16px) mobile

**Color enhancements:**
- Price flash: green pulse on positive tick, red pulse on negative tick (CSS animation, 300ms).
- 52W range: gradient from red (low) through neutral (mid) to green (high).
- Screener rank badges: gold (#1), silver (#2), bronze (#3).
- Card borders: subtle `border border-gray-800` with hover glow `hover:border-gray-700`.

**Animations:**
- Page transitions: fade-in (200ms) when navigating between pages.
- Number changes: `transition-colors duration-300` on price cells.
- Card entrance: `fadeInUp` with staggered delay (via Framer Motion `variants`).
- Sidebar expand/collapse: `transition-all duration-200`.

### 4.6 Data Fetching Strategy

**Migrate from raw `fetch` to TanStack React Query hooks** (already set up but unused by the dashboard):

- `useDashboard()` — replaces raw `fetchData()` in UnifiedDashboard.
- `useScreener(type)` — screener data with 60s refetch.
- `useSymbolDetail(symbol)` — symbol profile + stats.
- `useHistoricalOHLC(symbol, timeframe)` — chart data from DB.
- `useSymbolSearch(query)` — debounced search (300ms).

All hooks use the existing `MarketPulseAPIClient` from `lib/api.ts`.

---

## 5. Caching Strategy

### 5.1 Three-Tier Cache

```
Browser (React Query) → Redis (TTL) → PostgreSQL (persistent)
```

| Data | Browser TTL | Redis TTL | DB | Refresh Schedule |
|------|------------|-----------|-----|-----------------|
| Real-time quotes | 10s staleTime | 30s | prices (intraday) | 30s during market |
| Daily stats | 5min | 1hr | symbol_stats | After market close |
| Screener results | 60s | 30min | screener_snapshots | 30min during market |
| Breadth data | 30s | 1min | breadth_snapshots | 5min during market |
| Historical OHLCV | 5min | 5min | prices | On-demand, then cached |
| Symbol metadata | 1hr | 24hr | symbols | On registration |
| 52W high/low | 5min | 1hr | symbol_stats | Daily computation |

### 5.2 Cache Invalidation

- **Time-based:** All caches have TTL; no manual invalidation needed for most data.
- **Event-based:** When new OHLCV data is stored, invalidate `symbol_stats` Redis key so next read triggers recomputation.
- **On-demand:** Admin endpoint `POST /api/admin/cache/invalidate/{symbol}` to force refresh.

### 5.3 API Call Reduction

**Current state:** Every dashboard refresh (60s) makes 3 parallel API calls to backend, each of which may call Yahoo Finance.

**Target state:**
- Dashboard refresh reads from Redis cache (30s TTL).
- Background jobs populate Redis + DB independently.
- Yahoo Finance calls happen only via scheduled jobs, not on-demand API requests.
- Estimated reduction: **80% fewer Yahoo Finance calls** (from ~6/min to ~1/min during market hours).

---

## 6. Implementation Order

### Phase 1: Data Foundation (DB + Background Jobs)
1. Initialize Alembic migrations
2. Create `symbols`, `symbol_stats`, `screener_snapshots`, `breadth_snapshots`, `data_fetch_log`, `indicators` tables
3. Add new columns to `prices` table
4. Build background scheduler with APScheduler
5. Implement OHLCV fetch + validate + store pipeline
6. Implement daily stats computation (52W levels, SMAs, ATR)
7. Implement screener data collection
8. Seed `symbols` table with currently tracked symbols

### Phase 2: API Endpoints
1. New screener endpoints
2. New symbol detail endpoints
3. Enhanced dashboard/macro/breadth responses
4. Data quality endpoints
5. Update existing endpoints to read from DB first

### Phase 3: Frontend Shell
1. Create LayoutShell, Sidebar, TopBar components
2. Set up Next.js multi-page routing
3. Create SymbolSearch component with autocomplete
4. Migrate dashboard data fetching to React Query hooks
5. Extract reusable components from UnifiedDashboard

### Phase 4: Enhanced Dashboard
1. Real-data sparklines
2. 52W range bars in data tables
3. Mini screener widget
4. Improved spacing, animations, number transitions
5. Animated price cells

### Phase 5: New Pages
1. Trending page with screener tables
2. Chart page with TradingView Lightweight Charts
3. Symbol detail page

---

## 7. Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Migration tool | Alembic | Standard for SQLAlchemy, async support |
| Scheduler | APScheduler | Lightweight, in-process, async-native |
| Chart library | TradingView Lightweight Charts | Professional financial charts, 40KB, React wrapper available |
| State management | TanStack React Query | Already installed, just needs to be used |
| Symbol search | Server-side with debounce | Avoids downloading full symbol list to client |
| Data validation | Pydantic models in API layer | Consistent with existing FastAPI patterns |
| 52W calculation | SQL from stored prices | No API calls, deterministic, auditable |
| Screener source | Yahoo Finance screeners | Stable endpoints, portable to other providers later |

---

## 8. Files to Create/Modify

### New Files

**Migrations:**
- `src/migrations/alembic.ini`
- `src/migrations/env.py`
- `src/migrations/versions/001_initial_new_tables.py`

**Scheduler:**
- `src/scheduler/__init__.py`
- `src/scheduler/jobs.py` — All background job definitions
- `src/scheduler/scheduler.py` — APScheduler setup and lifecycle

**API:**
- `src/api/routers/symbols.py` — Symbol detail endpoints
- `src/api/routers/screeners.py` — Screener endpoints
- `src/api/routers/data_quality.py` — Data quality endpoints

**Frontend Components:**
- `marketpulse-client/src/components/LayoutShell.tsx`
- `marketpulse-client/src/components/Sidebar.tsx`
- `marketpulse-client/src/components/TopBar.tsx`
- `marketpulse-client/src/components/SymbolSearch.tsx`
- `marketpulse-client/src/components/FiftyTwoWeekBar.tsx`
- `marketpulse-client/src/components/ScreenerTable.tsx`
- `marketpulse-client/src/components/ChartWidget.tsx`
- `marketpulse-client/src/components/SymbolCard.tsx`
- `marketpulse-client/src/components/DataTable.tsx`

**Frontend Pages:**
- `marketpulse-client/src/app/trending/page.tsx`
- `marketpulse-client/src/app/chart/[symbol]/page.tsx`
- `marketpulse-client/src/app/symbol/[symbol]/page.tsx`

**Frontend Hooks:**
- `marketpulse-client/src/hooks/useScreenerData.ts`
- `marketpulse-client/src/hooks/useSymbolDetail.ts`

### Modified Files

- `src/core/database.py` — Add ORM models for new tables
- `src/api/yahoo_client.py` — Add screener methods, improve async handling
- `src/api/main.py` — Register new routers, start scheduler on lifespan
- `src/api/routers/market.py` — Enhanced responses, DB-first reads
- `marketpulse-client/src/app/layout.tsx` — Wrap with LayoutShell
- `marketpulse-client/src/app/page.tsx` — Simplified to dashboard content only
- `marketpulse-client/src/components/UnifiedDashboard.tsx` — Refactored to use hooks + smaller components
- `marketpulse-client/src/hooks/useMarketData.ts` — New hooks
- `marketpulse-client/src/lib/api.ts` — New API methods
- `marketpulse-client/src/types/market.ts` — New type definitions
- `marketpulse-client/package.json` — Add `lightweight-charts` dependency
