# MarketPulse Comprehensive Overhaul — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform MarketPulse from a single-page dashboard into a multi-page trading platform with robust data infrastructure, professional charting, screener data, 52W stats, and a DB schema designed for algorithmic trading.

**Architecture:** Layered bottom-up: DB schema + migrations → Background scheduler + data collection → New API endpoints → Frontend shell (layout, routing) → Enhanced dashboard → New pages (trending, charts, symbol detail).

**Tech Stack:** PostgreSQL + SQLAlchemy + Alembic (backend DB), APScheduler (jobs), FastAPI (API), Next.js 16 + React 19 + TanStack React Query (frontend), TradingView Lightweight Charts (charts), Tailwind CSS (styling).

**Design spec:** `docs/superpowers/specs/2026-05-21-marketpulse-overhaul-design.md`

---

## Phase 1: Data Foundation (DB + Background Jobs)

### Task 1: Fix existing bug — add missing REASONABLE_RANGES to validators

**Files:**
- Modify: `src/core/validators.py`

The `DatabaseManager._validate_symbol_price()` at `src/core/database.py:286` imports `REASONABLE_RANGES` from validators, but it's never defined there. This will cause a runtime ImportError.

- [ ] **Step 1:** Add `REASONABLE_RANGES` dict to `src/core/validators.py` after the threshold constants (around line 16):

```python
REASONABLE_RANGES: dict[str, tuple[float, float]] = {
    "SPY": (300.0, 700.0),
    "QQQ": (300.0, 600.0),
    "VIX": (8.0, 40.0),
    "IWM": (150.0, 300.0),
    "DIA": (300.0, 500.0),
}
```

- [ ] **Step 2:** Verify import works by running:
```bash
python -c "from src.core.validators import REASONABLE_RANGES; print(REASONABLE_RANGES)"
```
Expected: dict printed without error.

- [ ] **Step 3:** Commit:
```bash
git add src/core/validators.py && git commit -m "fix: add missing REASONABLE_RANGES to validators module"
```

---

### Task 2: Add APScheduler dependency + Initialize Alembic

**Files:**
- Modify: `requirements.txt` — add `apscheduler>=3.10.0`
- Create: `alembic.ini` (project root)
- Create: `src/migrations/env.py`
- Create: `src/migrations/script.py.mako`

- [ ] **Step 1:** Add `apscheduler>=3.10.0` to `requirements.txt` after the `schedule` line.

- [ ] **Step 2:** Install it:
```bash
pip install apscheduler>=3.10.0
```

- [ ] **Step 3:** Initialize Alembic from project root:
```bash
cd C:\Users\llama\OneDrive\proj\marketpulse
python -m alembic init -t async src/migrations
```

- [ ] **Step 4:** Edit `alembic.ini` to set `sqlalchemy.url` to empty (we'll use env.py to configure it dynamically):
```
sqlalchemy.url =
```

- [ ] **Step 5:** Edit `src/migrations/env.py` to:
  - Import `Settings` from `src.core.config`
  - Set `target_metadata = Base.metadata` from `src.core.database`
  - Configure `run_migrations_online()` to use `settings.database_url` with asyncpg
  - Set `config.set_main_option("sqlalchemy.url", settings.database_url.replace("postgresql://", "postgresql+asyncpg://"))`

- [ ] **Step 6:** Commit:
```bash
git add requirements.txt alembic.ini src/migrations/ && git commit -m "chore: add APScheduler dependency and initialize Alembic migrations"
```

---

### Task 3: Create new ORM models for all new tables

**Files:**
- Modify: `src/core/database.py` — add 6 new ORM model classes after existing ones (after line 113)

- [ ] **Step 1:** Add new ORM models to `src/core/database.py` after `MarketRegime` class:

**`Symbol`** — maps to `market_data.symbols`:
- id, symbol (VARCHAR 20, UNIQUE NOT NULL), name (VARCHAR 200), asset_type (VARCHAR 20, NOT NULL), exchange (VARCHAR 20), sector (VARCHAR 50), industry (VARCHAR 100), currency (VARCHAR 3, default 'USD'), lot_size (Float, default 1), tick_size (Float, default 0.01), is_active (Boolean, default True), yahoo_symbol (VARCHAR 20), alpaca_symbol (VARCHAR 20), data_source (VARCHAR 20, default 'yahoo'), created_at, updated_at

**`SymbolStats`** — maps to `market_data.symbol_stats`:
- id, symbol (VARCHAR 20, NOT NULL), date (Date, NOT NULL), high_52w, low_52w, pct_from_52w_high, pct_from_52w_low, avg_volume_20d (BigInteger), avg_volume_50d (BigInteger), sma_20, sma_50, sma_200, atr_14, beta, market_cap (BigInteger), pe_ratio, prev_close, day_range_pct, year_high_date (Date), year_low_date (Date), created_at
- UniqueConstraint: `(symbol, date)`
- `__table_args__` includes `schema="market_data"`

**`ScreenerSnapshot`** — maps to `market_data.screener_snapshots`:
- id, snapshot_date (Date, NOT NULL), screener_type (VARCHAR 20, NOT NULL), symbol (VARCHAR 20, NOT NULL), rank (Integer, NOT NULL), price, change_pct, volume (BigInteger), market_cap (BigInteger), avg_volume_3m (BigInteger), relative_volume, extra_data (JSON), created_at
- UniqueConstraint: `(snapshot_date, screener_type, symbol)`
- `__table_args__` includes `schema="market_data"`

**`BreadthSnapshot`** — maps to `market_data.breadth_snapshots`:
- id, date (Date, NOT NULL), nyse_advancing (Integer), nyse_declining (Integer), nyse_unchanged (Integer), nyse_ad_ratio, nasdaq_advancing (Integer), nasdaq_declining (Integer), nasdaq_unchanged (Integer), nasdaq_ad_ratio, new_highs_52w (Integer), new_lows_52w (Integer), tick_avg_30m, vold_nyse (BigInteger), mcclellan_osc, mcclellan_sum, trin, created_at
- UniqueConstraint: `(date,)`
- `__table_args__` includes `schema="market_data"`

**`DataFetchLog`** — maps to `market_data.data_fetch_log`:
- id, source (VARCHAR 20, NOT NULL), endpoint (VARCHAR 200, NOT NULL), symbols (Text), status (VARCHAR 10, NOT NULL), response_ms (Integer), bars_fetched (Integer, default 0), error_message (Text), created_at
- `__table_args__` includes `schema="market_data"`

**`Indicator`** — maps to `analysis.indicators`:
- id, symbol (VARCHAR 20, NOT NULL), timeframe (VARCHAR 10, NOT NULL), timestamp (DateTime TZ, NOT NULL), indicator_type (VARCHAR 30, NOT NULL), params (JSON, NOT NULL), value (Float), values (JSON), created_at
- UniqueConstraint: `(symbol, timeframe, timestamp, indicator_type, params)`
- `__table_args__` includes `schema="analysis"`

Also add columns to existing `PriceData` model:
- `adjusted_close = Column(Float)`
- `split_factor = Column(Float, default=1.0)`
- `dividend_amount = Column(Float, default=0.0)`
- `source = Column(String(20), default='yahoo')`

- [ ] **Step 2:** Verify models import:
```bash
python -c "from src.core.database import Symbol, SymbolStats, ScreenerSnapshot, BreadthSnapshot, DataFetchLog, Indicator; print('All models imported OK')"
```

- [ ] **Step 3:** Commit:
```bash
git add src/core/database.py && git commit -m "feat: add ORM models for symbols, symbol_stats, screener_snapshots, breadth_snapshots, data_fetch_log, indicators"
```

---

### Task 4: Create Alembic migration for new tables

**Files:**
- Create: `src/migrations/versions/001_new_tables.py` (auto-generated then reviewed)

- [ ] **Step 1:** Generate migration:
```bash
cd C:\Users\llama\OneDrive\proj\marketpulse
alembic -c alembic.ini revision --autogenerate -m "add new tables for symbols stats screeners breadth"
```

- [ ] **Step 2:** Review the generated migration. Ensure it creates all 6 new tables and adds 4 new columns to `prices`. If autogenerate misses anything, edit the migration to add the missing operations. Ensure all tables use correct schema (`market_data.*` or `analysis.*`).

- [ ] **Step 3:** Also update the Docker init SQL at `database/docker-entrypoint-initdb.d/01-init.sql` to add `CREATE TABLE IF NOT EXISTS` for all new tables (so fresh Docker builds work without running Alembic).

- [ ] **Step 4:** Test migration (if DB available):
```bash
alembic -c alembic.ini upgrade head
```
Expected: "Running upgrade ... done" with no errors.

- [ ] **Step 5:** Commit:
```bash
git add src/migrations/ database/docker-entrypoint-initdb.d/ && git commit -m "feat: add Alembic migration for new tables (symbols, stats, screeners, breadth, fetch_log, indicators)"
```

---

### Task 5: Seed the `symbols` table with currently tracked symbols

**Files:**
- Create: `src/scheduler/__init__.py`
- Create: `src/scheduler/seed_symbols.py`

- [ ] **Step 1:** Create `src/scheduler/__init__.py` (empty).

- [ ] **Step 2:** Create `src/scheduler/seed_symbols.py` with a function `seed_symbols()` that:
  - Uses `DatabaseManager` to get a session
  - Inserts `Symbol` rows for all currently tracked symbols from `YahooFinanceClient.market_symbols` and `YahooFinanceClient.macro_symbols`
  - Maps each to correct `asset_type` (stock, etf, crypto, forex, future, index) and `yahoo_symbol`
  - Uses `session.merge()` to be idempotent
  - Stock symbols: SPY(etf), QQQ(etf), IWM(etf), DIA(etf), VTI(etf), VOO(etf), AAPL(stock), TSLA(stock), NVDA(stock)
  - Index/futures: ^VIX(index), NQ=F(future), ES=F(future)
  - Crypto: BTC-USD, ETH-USD, SOL-USD, XRP-USD (asset_type=crypto)
  - Macro ETFs: UUP(etf), GLD(etf), CL=F(future), ^TNX(index)
  - International: ^N225, ^HSI, 000001.SS, ^AXJO, ^FTSE, ^GDAXI, ^FCHI, ^STOXX50E (asset_type=index)
  - Forex: EURUSD=X, GBPUSD=X, USDJPY=X, AUDUSD=X, USDCAD=X, USDCHF=X (asset_type=forex)

- [ ] **Step 3:** Run the seeder:
```bash
python -c "from src.scheduler.seed_symbols import seed_symbols; seed_symbols()"
```

- [ ] **Step 4:** Commit:
```bash
git add src/scheduler/ && git commit -m "feat: add symbol seeder with all currently tracked Yahoo Finance symbols"
```

---

### Task 6: Build background scheduler with APScheduler

**Files:**
- Create: `src/scheduler/scheduler.py`
- Create: `src/scheduler/jobs.py`

- [ ] **Step 1:** Create `src/scheduler/scheduler.py` with:

```python
class MarketScheduler:
    def __init__(self):
        self._scheduler = AsyncIOScheduler()
        self._db_manager: DatabaseManager | None = None
        self._yahoo_client: YahooFinanceClient | None = None
        self._cache: CacheService | None = None

    async def start(self):
        # Initialize db_manager, yahoo_client, cache
        # Register all jobs with schedules
        # Start scheduler

    async def stop(self):
        self._scheduler.shutdown(wait=False)

    def _is_market_hours(self) -> bool:
        # Return True if current time is 9:30-16:00 ET Mon-Fri
```

- [ ] **Step 2:** Create `src/scheduler/jobs.py` with individual job functions:

**`fetch_realtime_quotes(scheduler)`** — Every 30s during market hours:
  - Call `yahoo_client.get_market_internals()` for tracked symbols
  - Cache result in Redis (key: `market:realtime`, TTL: 30s)
  - Log fetch to `data_fetch_log`

**`fetch_daily_ohlcv(scheduler)`** — After market close (4:15 PM ET):
  - For each active symbol in `market_data.symbols`:
    - Call `yahoo_client.get_bars(symbol, period="2y", interval="1d")`
    - Validate each bar with `_validate_ohlc()`
    - Upsert into `market_data.prices`
  - Then call `compute_daily_stats()` for all symbols

**`fetch_intraday_ohlcv(scheduler)`** — Every 15 min during market hours:
  - For major symbols (SPY, QQQ, AAPL, NVDA, TSLA, BTC-USD, ETH-USD):
    - Call `yahoo_client.get_bars(symbol, period="5d", interval="5m")`
    - Validate and upsert into `market_data.prices`

**`compute_daily_stats(scheduler)`** — Called after `fetch_daily_ohlcv`:
  - For each active symbol:
    - Query `SELECT MAX(high_price), MIN(low_price) FROM market_data.prices WHERE symbol=:sym AND timeframe='1d' AND timestamp >= NOW() - INTERVAL '52 weeks'`
    - Calculate SMA(20), SMA(50), SMA(200) from daily close prices
    - Calculate ATR(14) from daily OHLC
    - Calculate 20d/50d avg volume
    - Upsert into `market_data.symbol_stats`
  - This job makes **zero external API calls** — pure computation from stored data

**`fetch_screener_data(scheduler)`** — Every 30 min during market hours:
  - Call `yf.download()` screeners for gainers, losers, most_active
  - For each result, lookup or create Symbol entry
  - Insert into `market_data.screener_snapshots`
  - Cache in Redis (key: `screener:gainers`, `screener:losers`, `screener:most_active`, TTL: 30min)

**`fetch_breadth_data(scheduler)`** — Every 5 min during market hours:
  - Use existing `MarketBreadthCollector.get_market_internals()`
  - Cache in Redis (key: `market:breadth`, TTL: 1min)

**`cleanup_old_data(scheduler)`** — Daily at midnight ET:
  - Delete `market_data.prices` rows where `timeframe IN ('1m','5m') AND timestamp < NOW() - INTERVAL '30 days'`
  - Delete `market_data.data_fetch_log` rows where `created_at < NOW() - INTERVAL '30 days'`

- [ ] **Step 3:** Register scheduler in FastAPI lifespan (`src/api/main.py`):
  - Import `MarketScheduler`
  - Create instance in `lifespan()` startup
  - Call `await scheduler.start()`
  - On shutdown, call `await scheduler.stop()`

- [ ] **Step 4:** Commit:
```bash
git add src/scheduler/ src/api/main.py && git commit -m "feat: add APScheduler background jobs for OHLCV, screeners, breadth, and stats"
```

---

### Task 7: Add screener methods to YahooFinanceClient

**Files:**
- Modify: `src/api/yahoo_client.py` — add methods after `get_bars()` (around line 456)

- [ ] **Step 1:** Add `get_screener_data(self, screener_type: str) -> list[dict]`:
  - Uses `yf.Screener` or scrapes Yahoo screener pages for gainers/losers/most_active
  - Returns list of dicts with: symbol, name, price, change_pct, volume, market_cap
  - Fallback: use `yf.download()` on predefined high-volume symbol lists if screener API unreliable
  - Note: `yfinance` has `yf.Screener` in newer versions; if unavailable, use `pd.read_html()` on Yahoo screener URLs as fallback

- [ ] **Step 2:** Add `get_symbol_info(self, symbol: str) -> dict`:
  - Uses `yf.Ticker(symbol).info` to get: name, sector, industry, exchange, market_cap, pe_ratio
  - Returns dict compatible with `Symbol` ORM model fields

- [ ] **Step 3:** Add `get_52w_range(self, symbol: str) -> dict`:
  - Uses `yf.Ticker(symbol).info` keys: `fiftyTwoWeekHigh`, `fiftyTwoWeekLow`
  - Returns: `{high_52w, low_52w, pct_from_high, pct_from_low}`
  - Used as fallback if DB doesn't have computed stats yet

- [ ] **Step 4:** Commit:
```bash
git add src/api/yahoo_client.py && git commit -m "feat: add screener, symbol info, and 52W range methods to YahooFinanceClient"
```

---

## Phase 2: API Endpoints

### Task 8: Create screener API router

**Files:**
- Create: `src/api/routers/screeners.py`

- [ ] **Step 1:** Create router with prefix `/api/market/screeners`:

**`GET /api/market/screeners/{type}`** — Get latest screener results:
  - `type` path param: `gainers`, `losers`, `most_active`
  - Read from Redis cache `screener:{type}` first
  - If miss, query `market_data.screener_snapshots` for latest `snapshot_date`
  - Enrich with `symbol_stats` data (52W high/low, pct_from_52w_high)
  - Return list sorted by rank

**`GET /api/market/screeners/{type}/history`** — Historical screener data:
  - Query `screener_snapshots` for last 5 trading days
  - Return `{dates: [...], data: {date: [symbols...]}}`

- [ ] **Step 2:** Register router in `src/api/main.py`:
```python
from src.api.routers import screeners
app.include_router(screeners.router)
```

- [ ] **Step 3:** Commit:
```bash
git add src/api/routers/screeners.py src/api/main.py && git commit -m "feat: add screener API endpoints for gainers, losers, most_active"
```

---

### Task 9: Create symbol detail API router

**Files:**
- Create: `src/api/routers/symbols.py`

- [ ] **Step 1:** Create router with prefix `/api/market/symbols`:

**`GET /api/market/symbols`** — List all tracked symbols:
  - Query `market_data.symbols WHERE is_active = TRUE`
  - Return list with: symbol, name, asset_type, exchange, sector

**`GET /api/market/symbols/{symbol}`** — Full symbol profile:
  - Query `market_data.symbols` for metadata
  - Query `market_data.symbol_stats` for latest stats (52W levels, SMAs, ATR, etc.)
  - Query `market_data.prices` for latest price (most recent daily bar)
  - Return combined profile

**`GET /api/market/symbols/{symbol}/stats`** — Symbol statistics:
  - Query `market_data.symbol_stats WHERE symbol = :symbol ORDER BY date DESC LIMIT 1`
  - Return all stats fields

**`GET /api/market/symbols/{symbol}/52w-range`** — 52-week range:
  - Query `market_data.symbol_stats` for high_52w, low_52w, pct_from_52w_high, pct_from_52w_low
  - If no stats, fallback to `yahoo_client.get_52w_range(symbol)`
  - Return: `{symbol, current_price, high_52w, low_52w, pct_from_high, pct_from_low, high_date, low_date}`

**`GET /api/market/symbols/search?q={query}`** — Symbol search:
  - Query `market_data.symbols WHERE symbol ILIKE :q OR name ILIKE :q LIMIT 10`
  - Used for frontend autocomplete

- [ ] **Step 2:** Register router in `src/api/main.py`

- [ ] **Step 3:** Commit:
```bash
git add src/api/routers/symbols.py src/api/main.py && git commit -m "feat: add symbol detail, stats, 52W range, and search API endpoints"
```

---

### Task 10: Create data quality API router

**Files:**
- Create: `src/api/routers/data_quality.py`

- [ ] **Step 1:** Create router with prefix `/api/market/data-quality`:

**`GET /api/market/data-quality`** — Overview:
  - For each active symbol, report: last bar timestamp, bar count by timeframe, any gaps detected
  - Return `{symbols: {symbol: {last_update, bar_counts, gaps}}}`

**`GET /api/market/data-quality/{symbol}`** — Per-symbol:
  - Detailed report: date range of available data, missing dates, stats availability

- [ ] **Step 2:** Register router in `src/api/main.py`

- [ ] **Step 3:** Commit:
```bash
git add src/api/routers/data_quality.py src/api/main.py && git commit -m "feat: add data quality API endpoints"
```

---

### Task 11: Enhance existing market endpoints

**Files:**
- Modify: `src/api/routers/market.py`

- [ ] **Step 1:** Enhance `/api/market/dashboard` response:
  - Add `screener_summary` field: top 3 gainers + top 3 losers (from Redis `screener:*` cache or DB)
  - Add `symbol_stats` field: for SPY, QQQ, VIX — include 52W high/low, SMA values from `symbol_stats` table

- [ ] **Step 2:** Enhance `/api/market/macro` response:
  - For each macro symbol, add `high_52w` and `low_52w` from `symbol_stats` table
  - Add `pct_from_52w_high` field

- [ ] **Step 3:** Enhance `/api/market/breadth`:
  - Outside market hours: read latest from `breadth_snapshots` table instead of live fetch
  - During market hours: use existing live fetch + cache in Redis

- [ ] **Step 4:** Add `/api/market/historical/{symbol}` endpoint (new path style):
  - Try reading from `market_data.prices` first
  - If no data in DB for requested timeframe, fall back to `yahoo_client.get_bars()`
  - Store fetched data in DB for future requests

- [ ] **Step 5:** Commit:
```bash
git add src/api/routers/market.py && git commit -m "feat: enhance dashboard, macro, breadth endpoints with 52W data and screener summary"
```

---

## Phase 3: Frontend Shell

### Task 12: Install lightweight-charts dependency

**Files:**
- Modify: `marketpulse-client/package.json`

- [ ] **Step 1:** Install:
```bash
cd marketpulse-client && npm install lightweight-charts
```

- [ ] **Step 2:** Commit:
```bash
git add marketpulse-client/package.json marketpulse-client/package-lock.json && git commit -m "chore: add lightweight-charts dependency for TradingView charts"
```

---

### Task 13: Create LayoutShell, Sidebar, TopBar components

**Files:**
- Create: `marketpulse-client/src/components/LayoutShell.tsx`
- Create: `marketpulse-client/src/components/Sidebar.tsx`
- Create: `marketpulse-client/src/components/TopBar.tsx`

- [ ] **Step 1:** Create `Sidebar.tsx`:
  - Props: `collapsed: boolean`, `onToggle: () => void`, `currentPage: string`
  - Navigation items: Dashboard (`/`), Trending (`/trending`), Charts (`/chart/SPY`), Alerts (`/alerts`), Settings (`/settings`)
  - Uses `lucide-react` icons: `LayoutDashboard`, `Flame`, `CandlestickChart` (or `BarChart3`), `Bell`, `Settings`
  - Uses `next/link` for navigation
  - Desktop: fixed left sidebar, 64px collapsed / 200px expanded, `transition-all duration-200`
  - Mobile: overlay sidebar triggered by hamburger button
  - Active page highlighted with blue left border + blue text
  - Dark theme: `bg-gray-900 border-r border-gray-800`

- [ ] **Step 2:** Create `TopBar.tsx`:
  - Contains: MarketPulse logo/text (left), SymbolSearch placeholder (center), connection status + clock (right)
  - Props: `onMenuToggle: () => void`, `isConnected: boolean`, `lastUpdate: Date | null`
  - Mobile: hamburger menu button on left
  - Desktop: no hamburger, sidebar auto-visible
  - Connection status: green dot + "Live" or red dot + "Offline"
  - Clock: current time with `session-timer` tabular-nums

- [ ] **Step 3:** Create `LayoutShell.tsx`:
  - Wraps `Sidebar` + `TopBar` + `{children}` content area
  - Manages sidebar collapsed state in `useState`
  - Layout: `flex h-screen` with sidebar on left, main area on right
  - Main area: `flex flex-col` with TopBar on top, scrollable content below
  - Content area: `flex-1 overflow-auto p-4 lg:p-6 bg-gray-950`
  - Footer bar at bottom: data source, refresh interval, version (similar to current footer)

- [ ] **Step 4:** Update `marketpulse-client/src/app/layout.tsx` to use `LayoutShell`:
  - Wrap `{children}` with `<LayoutShell>` instead of just `{children}`
  - Remove `<main>` wrapper from `page.tsx` (LayoutShell handles it)

- [ ] **Step 5:** Simplify `marketpulse-client/src/app/page.tsx`:
  - Remove `<main>` wrapper
  - Just render `<UnifiedDashboard />` directly

- [ ] **Step 6:** Commit:
```bash
git add marketpulse-client/src/components/ marketpulse-client/src/app/ && git commit -m "feat: add LayoutShell with Sidebar and TopBar for multi-page navigation"
```

---

### Task 14: Create FiftyTwoWeekBar component

**Files:**
- Create: `marketpulse-client/src/components/FiftyTwoWeekBar.tsx`

- [ ] **Step 1:** Create component with props:
```typescript
interface FiftyTwoWeekBarProps {
  currentPrice: number;
  high52w: number;
  low52w: number;
  width?: number;
  height?: number;
  showLabels?: boolean;
}
```

- [ ] **Step 2:** Implementation:
  - Calculate position: `pct = (currentPrice - low52w) / (high52w - low52w)` clamped to [0, 1]
  - Render a thin horizontal bar (`h-1.5 rounded-full`) with:
    - Background: `bg-gray-800` full width
    - Fill: gradient from red (left) to green (right), width = `pct * 100%`
    - Marker dot at current position
  - If `showLabels`: show low52w and high52w values at ends
  - Color intensity: near highs = greener, near lows = redder, middle = neutral blue

- [ ] **Step 3:** Commit:
```bash
git add marketpulse-client/src/components/FiftyTwoWeekBar.tsx && git commit -m "feat: add FiftyTwoWeekBar range indicator component"
```

---

### Task 15: Create DataTable and PriceCell components

**Files:**
- Create: `marketpulse-client/src/components/DataTable.tsx`
- Create: `marketpulse-client/src/components/PriceCell.tsx`

- [ ] **Step 1:** Create `PriceCell.tsx`:
  - Props: `price: number`, `change: number`, `changePct: number`, `animate?: boolean`
  - Renders price with 2 decimal places (or integer for crypto)
  - Change % with +/- sign and color (green positive, red negative)
  - If `animate`, uses CSS `transition-colors duration-300` for smooth color changes on updates

- [ ] **Step 2:** Create `DataTable.tsx`:
  - Generic sortable data table component
  - Props: `columns: ColumnDef[]`, `data: any[]`, `onRowClick?: (row) => void`, `sortBy?: string`, `sortDir?: 'asc' | 'desc'`
  - `ColumnDef`: `{ key: string, label: string, sortable?: boolean, render?: (value, row) => ReactNode, width?: string }`
  - Click column header to sort (toggle asc/desc)
  - Row hover effect: `hover:bg-gray-800/50`
  - If `onRowClick`, cursor pointer on rows
  - Styled consistently with existing `.data-table` CSS

- [ ] **Step 3:** Commit:
```bash
git add marketpulse-client/src/components/DataTable.tsx marketpulse-client/src/components/PriceCell.tsx && git commit -m "feat: add generic DataTable and PriceCell components"
```

---

### Task 16: Create SymbolSearch component

**Files:**
- Create: `marketpulse-client/src/components/SymbolSearch.tsx`

- [ ] **Step 1:** Create component:
  - Props: `onSelect: (symbol: string) => void`, `placeholder?: string`
  - Uses debounced search (300ms) via `useSymbolSearch` hook (defined in Task 17)
  - Input with search icon, dropdown results below
  - Results show: symbol, name, asset_type badge
  - Click result → calls `onSelect` (navigates to `/chart/[symbol]`)
  - Keyboard navigation: arrow keys + enter
  - Click outside to close dropdown
  - Styled: `bg-gray-900 border border-gray-700 rounded-lg`

- [ ] **Step 2:** Commit:
```bash
git add marketpulse-client/src/components/SymbolSearch.tsx && git commit -m "feat: add SymbolSearch autocomplete component"
```

---

### Task 17: Create new React Query hooks

**Files:**
- Modify: `marketpulse-client/src/hooks/useMarketData.ts` — add new hooks
- Create: `marketpulse-client/src/hooks/useScreenerData.ts`
- Create: `marketpulse-client/src/hooks/useSymbolDetail.ts`
- Modify: `marketpulse-client/src/lib/api.ts` — add new API methods
- Modify: `marketpulse-client/src/types/market.ts` — add new types

- [ ] **Step 1:** Add new types to `market.ts`:
  - `ScreenerResult`: rank, symbol, name, price, change_pct, volume, relative_volume, high_52w, low_52w, pct_from_52w_high, market_cap
  - `SymbolProfile`: symbol, name, asset_type, exchange, sector, industry, market_cap, pe_ratio
  - `SymbolStats`: date, high_52w, low_52w, pct_from_52w_high, pct_from_52w_low, sma_20, sma_50, sma_200, atr_14, avg_volume_20d, avg_volume_50d
  - `FiftyTwoWeekRange`: symbol, current_price, high_52w, low_52w, pct_from_high, pct_from_low, high_date, low_date
  - `OHLCVBar`: timestamp, open, high, low, close, volume

- [ ] **Step 2:** Add new methods to `MarketPulseAPIClient` in `api.ts`:
  - `getScreenerData(type: string): Promise<ScreenerResult[]>`
  - `getSymbols(): Promise<SymbolProfile[]>`
  - `getSymbolDetail(symbol: string): Promise<SymbolProfile & {stats: SymbolStats, price: OHLCVBar}>`
  - `getSymbolStats(symbol: string): Promise<SymbolStats>`
  - `get52WRange(symbol: string): Promise<FiftyTwoWeekRange>`
  - `searchSymbols(query: string): Promise<SymbolProfile[]>`
  - `getHistoricalFromDB(symbol: string, timeframe: string): Promise<OHLCVBar[]>`

- [ ] **Step 3:** Create `useScreenerData.ts`:
  - `useScreener(type: 'gainers' | 'losers' | 'most_active')` with 60s refetch interval
  - `useScreenerHistory(type: string)` with 5min stale time

- [ ] **Step 4:** Create `useSymbolDetail.ts`:
  - `useSymbolDetail(symbol: string)` — profile + stats
  - `useSymbolStats(symbol: string)` — stats only, 5min stale
  - `use52WRange(symbol: string)` — 52W data, 5min stale
  - `useSymbolSearch(query: string)` — debounced search, 300ms debounce

- [ ] **Step 5:** Update `useMarketData.ts` with new query keys:
  - Add `screener: (type) => [...marketKeys.all, 'screener', type]`
  - Add `symbol: (symbol) => [...marketKeys.all, 'symbol', symbol]`
  - Add `search: (query) => [...marketKeys.all, 'search', query]`

- [ ] **Step 6:** Commit:
```bash
git add marketpulse-client/src/ && git commit -m "feat: add React Query hooks for screeners, symbol detail, 52W range, and search"
```

---

## Phase 4: Enhanced Dashboard

### Task 18: Refactor UnifiedDashboard to use React Query hooks

**Files:**
- Modify: `marketpulse-client/src/components/UnifiedDashboard.tsx`

- [ ] **Step 1:** Replace raw `fetch` + `useState` data fetching with React Query hooks:
  - Replace `fetchData()` with `useDashboardData()`, `useMacroData()`, `useMarketBreadth()` hooks
  - Remove `loading`, `error`, `lastUpdate`, `retryCount` state — use `isLoading`, `isError` from hooks
  - Remove `setInterval` for auto-refresh — hooks handle this
  - Keep `sessionTime` and `sessionCountdown` as local state (timer logic)

- [ ] **Step 2:** Add 52W data to data tables:
  - For each symbol row in `renderDataTable()`, show `<FiftyTwoWeekBar>` using stats data
  - Pass `high52w` and `low52w` from the enhanced dashboard response (`symbol_stats` field)

- [ ] **Step 3:** Make symbol rows clickable:
  - Wrap each symbol row in a `Link` to `/chart/[symbol]`
  - Add `cursor-pointer` class to rows

- [ ] **Step 4:** Commit:
```bash
git add marketpulse-client/src/components/UnifiedDashboard.tsx && git commit -m "refactor: migrate UnifiedDashboard to React Query hooks with 52W range bars"
```

---

### Task 19: Add mini screener widget to dashboard

**Files:**
- Modify: `marketpulse-client/src/components/UnifiedDashboard.tsx`

- [ ] **Step 1:** Add a "Top Movers" card in the dashboard layout (add to column 3 or as new section):
  - Use `useScreener('gainers')` and `useScreener('losers')` hooks
  - Show top 3 gainers in green list and top 3 losers in red list
  - Each item: symbol, change_pct, mini sparkline
  - Click → navigate to `/chart/[symbol]`

- [ ] **Step 2:** Commit:
```bash
git add marketpulse-client/src/components/UnifiedDashboard.tsx && git commit -m "feat: add Top Movers screener widget to dashboard"
```

---

### Task 20: Improve dashboard styling and animations

**Files:**
- Modify: `marketpulse-client/src/components/UnifiedDashboard.tsx`
- Modify: `marketpulse-client/src/app/globals.css`

- [ ] **Step 1:** Add animated price flash CSS to `globals.css`:
```css
@keyframes flashGreen {
  0% { background-color: rgba(16, 185, 129, 0.3); }
  100% { background-color: transparent; }
}
@keyframes flashRed {
  0% { background-color: rgba(239, 68, 68, 0.3); }
  100% { background-color: transparent; }
}
.price-flash-positive { animation: flashGreen 0.3s ease-out; }
.price-flash-negative { animation: flashRed 0.3s ease-out; }
```

- [ ] **Step 2:** Add page transition wrapper using Framer Motion `AnimatePresence` + `motion.div` with `fadeIn` initial/exit

- [ ] **Step 3:** Standardize card styling:
  - All cards: `bg-gray-900 border border-gray-800 rounded-xl p-4 hover:border-gray-700 transition-colors`
  - Card titles: `text-sm font-medium text-gray-400 mb-3 flex items-center gap-2`
  - Consistent 16px padding and 16px gap

- [ ] **Step 4:** Commit:
```bash
git add marketpulse-client/src/ && git commit -m "style: add price flash animations, page transitions, and consistent card styling"
```

---

## Phase 5: New Pages

### Task 21: Create Trending page

**Files:**
- Create: `marketpulse-client/src/app/trending/page.tsx`

- [ ] **Step 1:** Create trending page with:
  - Client component (`'use client'`)
  - Tab bar: Gainers | Losers | Most Active (default: Gainers)
  - Uses `useScreener(activeTab)` hook
  - Renders `<ScreenerTable>` (new specialized DataTable) with columns:
    - Rank (#), Symbol + Name, Price, Change %, Volume, Rel Vol, 52W Range (FiftyTwoWeekBar), % from 52W High, Sparkline
  - Sort by clicking column headers
  - Auto-refresh every 60s
  - Row click → navigate to `/chart/[symbol]`
  - Loading state: skeleton rows
  - Empty state: "No screener data available — market may be closed"

- [ ] **Step 2:** Commit:
```bash
git add marketpulse-client/src/app/trending/ && git commit -m "feat: add Trending page with gainers, losers, most active screener tables"
```

---

### Task 22: Create ChartWidget component

**Files:**
- Create: `marketpulse-client/src/components/ChartWidget.tsx`

- [ ] **Step 1:** Create TradingView Lightweight Charts wrapper:
  - Props: `symbol: string`, `data: OHLCVBar[]`, `timeframe: string`, `overlays?: string[]`
  - Uses `useRef` for chart container div
  - Initializes `createChart()` from `lightweight-charts`
  - Adds candlestick series + volume histogram
  - Timeframe selector buttons: 5m, 15m, 1h, 4h, 1D, 1W
  - Overlay toggles: SMA(20), SMA(50), EMA(12), EMA(26)
  - Crosshair with price/date tooltip
  - Responsive: resizes with container using `ResizeObserver`
  - Cleanup on unmount: `chart.remove()`
  - Compute SMA/EMA from passed data (not from API)

- [ ] **Step 2:** Commit:
```bash
git add marketpulse-client/src/components/ChartWidget.tsx && git commit -m "feat: add ChartWidget with TradingView Lightweight Charts integration"
```

---

### Task 23: Create Chart page

**Files:**
- Create: `marketpulse-client/src/app/chart/[symbol]/page.tsx`

- [ ] **Step 1:** Create chart page:
  - Extract `symbol` from route params
  - Use `useHistoricalOHLC(symbol, timeframe)` for chart data
  - Use `useSymbolDetail(symbol)` for sidebar info
  - Layout: chart takes 70% width, info sidebar takes 30% on desktop
  - Mobile: full-width chart, info below

  **Chart area:**
  - `<ChartWidget>` with fetched OHLCV data
  - Timeframe selector above chart
  - Symbol name + price in header

  **Sidebar:**
  - Symbol info: name, exchange, sector, market cap, P/E
  - 52W range bar (`<FiftyTwoWeekBar>`)
  - Key statistics: avg volume, ATR, SMA values
  - Support/resistance levels (from OHLC analysis endpoint)
  - Link to `/symbol/[symbol]` for full detail

  **Below chart:**
  - AI analysis summary (from LLM chat context for this symbol)

- [ ] **Step 2:** Commit:
```bash
git add marketpulse-client/src/app/chart/ && git commit -m "feat: add Chart page with TradingView Lightweight Charts and symbol info sidebar"
```

---

### Task 24: Create Symbol Detail page

**Files:**
- Create: `marketpulse-client/src/app/symbol/[symbol]/page.tsx`

- [ ] **Step 1:** Create symbol detail page:
  - Extract `symbol` from route params
  - Use `useSymbolDetail(symbol)` for profile + stats

  **Header section:**
  - Symbol, name, current price, daily change
  - 52W range bar (large version)

  **Key Statistics grid (2x4):**
  - Market Cap, P/E Ratio, Volume, Avg Volume (20d)
  - 52W High, 52W Low, SMA(50), SMA(200)
  - ATR(14), Beta, Day Range %

  **52-Week Analysis section:**
  - Small area chart showing price over last year with horizontal lines at 52W high/low
  - Date labels for when high/low were set

  **Data Quality section:**
  - Last data fetch time
  - Number of bars available by timeframe
  - Any gaps detected

  **Actions:**
  - Button to open chart page: "Open Chart →" links to `/chart/[symbol]`

- [ ] **Step 2:** Commit:
```bash
git add marketpulse-client/src/app/symbol/ && git commit -m "feat: add Symbol Detail page with profile, stats, 52W analysis, and data quality"
```

---

### Task 25: Final integration testing and cleanup

**Files:**
- Various: lint fixes, import cleanup, type fixes

- [ ] **Step 1:** Run backend linting:
```bash
cd C:\Users\llama\OneDrive\proj\marketpulse
ruff check src/ --fix
```
Fix any issues.

- [ ] **Step 2:** Run frontend linting:
```bash
cd marketpulse-client
npm run lint
```
Fix any issues.

- [ ] **Step 3:** Run backend tests:
```bash
cd C:\Users\llama\OneDrive\proj\marketpulse
python -m pytest tests/ -v --tb=short
```
Fix any failures.

- [ ] **Step 4:** Verify frontend builds:
```bash
cd marketpulse-client
npm run build
```
Fix any type errors or build failures.

- [ ] **Step 5:** Test the full stack:
  - Start backend: `python -m uvicorn src.api.main:app --reload --port 8000`
  - Start frontend: `cd marketpulse-client && npm run dev`
  - Verify all pages load: `/`, `/trending`, `/chart/SPY`, `/symbol/SPY`
  - Verify sidebar navigation works
  - Verify screener data loads
  - Verify 52W range bars render
  - Verify chart renders with candlesticks

- [ ] **Step 6:** Final commit with any fixes:
```bash
git add -A && git commit -m "chore: lint fixes, type fixes, and integration testing cleanup"
```

---

## Self-Review Checklist

After writing this plan, I checked:

1. **Spec coverage:** Each section of the design spec maps to at least one task:
   - DB schema (1.2): Tasks 3, 4
   - Data collection (2.1-2.5): Tasks 6, 7
   - API endpoints (3.1-3.3): Tasks 8, 9, 10, 11
   - Frontend shell (4.1-4.2): Tasks 13, 16
   - Component library (4.4): Tasks 14, 15, 22
   - Page designs (4.3): Tasks 21, 23, 24
   - Styling (4.5): Task 20
   - Data fetching (4.6): Tasks 17, 18
   - Caching (5): Tasks 6 (Redis caching in jobs), 11 (DB-first reads)

2. **Placeholder scan:** No TBDs, TODOs, or "implement later" patterns. All tasks have concrete file paths and implementation descriptions.

3. **Type consistency:** Method names used in hooks (e.g., `marketPulseAPI.getScreenerData()`) match those defined in Task 17's API client additions. Component props (e.g., `FiftyTwoWeekBar` props) are consistent across usage in dashboard, trending, chart, and symbol pages.
