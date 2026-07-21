# Treasury Yield Curve Monitor + Alerter — Design

**Date:** 2026-06-23
**Status:** Approved for planning
**Owner:** Trading desk
**Scope:** New self-contained `src/yield_curve/` module + scheduler hook + API surface + frontend panel + dedicated DB table.

---

## 1. Overview

Build a daily Treasury yield curve monitor that tracks the full 3M → 30Y curve, computes the spreads that drive the Kevin Warsh "QE without calling it QE" transmission mechanism, and fires alerts when curve regime conditions change.

The 2s/10s spread is the primary transmission variable: if Warsh delivers on balance-sheet shrinkage while cutting short-term rates, the resulting curve steepening is the profit signal that keeps banks absorbing long-end Treasury supply. If the curve flattens or inverts instead, the bank-arbitrage channel collapses and the Fed faces a binary choice (restart QE or watch a Treasury buyers' strike). We monitor the curve, classify its shape, and alert on the conditions that matter.

---

## 2. Goals

- Track the full US Treasury yield curve (3M, 1Y, 2Y, 5Y, 7Y, 10Y, 20Y, 30Y) daily.
- Compute the four spreads that anchor the Warsh framework: 2s10s, 3m10y, 5s30s, 2s30s.
- Classify curve shape (NORMAL / FLAT / INVERTED / HUMPED / INVERTED_HUMPED) and trend (STEEPENING / FLATTENING / STABLE).
- Compute a NY Fed-style recession probability from the 3m10y spread.
- Detect and alert on seven distinct Warsh-framework triggers (table in §7).
- Expose current state and history via REST API; embed a panel in the existing MacroDashboard.

## 3. Non-Goals

- No real-time intraday updates. FRED publishes Treasury yields once per trading day at end-of-day; we follow that cadence.
- No support for non-US sovereign curves (UST only).
- No automatic trade execution. The system surfaces conditions; humans decide.
- No extension of the existing `FredProvider` whitelist. New code in `src/yield_curve/` fetches FRED directly to avoid touching `src/research/`.
- No new external dependencies beyond what's already in `requirements.txt` and `marketpulse-client/package.json`.

---

## 4. Architecture

```
   FRED API                  AlertManager (console | Telegram)
       │                              ▲
       ▼                              │
   fetcher.py ──► parquet cache       │
       │          (data/macro/...)    │
       ▼                              │
   curves.py ──► DB snapshot          │
       │           │                  │
       ▼           ▼                  │
   alerts.py ──► evaluate rules ──────┘
                  │
                  ▼
            /api/yield-curve/*  ──►  MacroDashboard.tsx
```

Single new module (`src/yield_curve/`) is self-contained. Touches to existing code are minimal and listed in §13.

---

## 5. Module Layout

```
src/yield_curve/
  __init__.py
  fetcher.py        # FRED direct REST + parquet cache (mirrors scripts/yield_curve_monitor.py)
  curves.py         # Tenor fetch, spread math, shape classification, NY Fed prob
  alerts.py         # Warsh framework rule engine → AlertManager
  history.py        # Daily snapshot persistence + rolling deltas / z-scores
  config.py         # Thresholds (config-driven via env vars)
src/scheduler/
  yield_curve_job.py  # Daily scheduled: fetch → persist → evaluate alerts
src/api/routers/
  yield_curve.py    # FastAPI router
src/migrations/versions/
  003_yield_curve.py  # Alembic migration
```

### File responsibilities

- **`fetcher.py`** — `FredCurveFetcher` class. Method `fetch_tenors(tenors: list[str], start: date, end: date) -> dict[str, pd.Series]`. Uses `requests` directly (no `fredapi` dependency). Caches each tenor as parquet at `data/macro/yield_curve/{TENOR}.parquet`. Cache-hit semantics lifted from `src/research/data/fred.py:_cache_covers`. Retry via `tenacity` (already in `requirements.txt`).
- **`curves.py`** — Pure functions, no I/O. `compute_spreads(curve: dict[str, float]) -> dict[str, float]`, `classify_shape(curve: dict) -> str`, `classify_trend(today_curve, baseline_curve) -> str`, `nyfed_recession_prob(spread_3m10y: float) -> float`. Logic ported from `scripts/yield_curve_monitor.py`.
- **`alerts.py`** — `YieldCurveAlerts` class. Method `evaluate(snapshot: YieldCurveSnapshot, history: list[YieldCurveSnapshot]) -> list[AlertEvent]`. Encapsulates the seven rules. Calls `AlertManager.send_alert(...)` for each fired rule. Anti-spam: 6-hour suppression window per `rule_name` key (suppression state queried from `market_data.yield_curve_alerts` via `MAX(triggered_at) WHERE rule_name = :name`).
- **`history.py`** — SQLAlchemy queries and inserts against `market_data.yield_curve_snapshots`. Methods: `save_snapshot(snapshot)`, `get_snapshot(date)`, `get_history(days)`, `compute_deltas(snapshot, history_window)`.
- **`config.py`** — Reads thresholds from env vars with sensible defaults:
  - `YIELD_CURVE_STEEPEN_BPS_5D = 20`
  - `YIELD_CURVE_FLATTEN_BPS_5D = -20`
  - `YIELD_CURVE_RECESSION_PROB_HIGH = 0.50`
  - `YIELD_CURVE_RECESSION_PROB_LOW = 0.25`
  - `YIELD_CURVE_ANTISPAM_HOURS = 6`
  - `YIELD_CURVE_FETCH_TIME_ET = "16:30"`

---

## 6. Database Schema

### New table: `market_data.yield_curve_snapshots`

One row per trading day. Primary key on `date` so duplicate inserts fail-fast and we can upsert via `ON CONFLICT (date) DO UPDATE`.

```sql
CREATE TABLE market_data.yield_curve_snapshots (
    date DATE PRIMARY KEY,
    dgs3mo NUMERIC(6,4), dgs1 NUMERIC(6,4), dgs2 NUMERIC(6,4), dgs5 NUMERIC(6,4),
    dgs7 NUMERIC(6,4), dgs10 NUMERIC(6,4), dgs20 NUMERIC(6,4), dgs30 NUMERIC(6,4),
    spread_2s10s NUMERIC(8,4),
    spread_3m10y NUMERIC(8,4),
    spread_5s30s NUMERIC(8,4),
    spread_2s30s NUMERIC(8,4),
    shape VARCHAR(16) NOT NULL,
    shape_trend VARCHAR(16) NOT NULL,
    recession_prob_nyfed NUMERIC(5,4),
    spread_2s10s_delta_5d NUMERIC(8,4),
    spread_2s10s_delta_30d NUMERIC(8,4),
    zscore_2s10s_90d NUMERIC(6,4),
    source VARCHAR(20) DEFAULT 'fred',
    fetched_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_yield_curve_date_desc ON market_data.yield_curve_snapshots(date DESC);
```

### New table: `market_data.yield_curve_alerts`

Audit log of fired alerts. Distinct from `AlertManager` runtime state — persists for review and backtesting.

```sql
CREATE TABLE market_data.yield_curve_alerts (
    id SERIAL PRIMARY KEY,
    triggered_at TIMESTAMPTZ DEFAULT NOW(),
    rule_name VARCHAR(64) NOT NULL,
    priority VARCHAR(16) NOT NULL,
    snapshot_date DATE NOT NULL REFERENCES market_data.yield_curve_snapshots(date),
    trigger_value NUMERIC(10,4),
    prior_value NUMERIC(10,4),
    delta NUMERIC(10,4),
    zscore NUMERIC(6,4),
    message TEXT NOT NULL,
    channels_attempted JSONB,
    channels_succeeded JSONB
);

CREATE INDEX idx_yield_curve_alerts_triggered ON market_data.yield_curve_alerts(triggered_at DESC);
CREATE INDEX idx_yield_curve_alerts_rule ON market_data.yield_curve_alerts(rule_name, triggered_at DESC);
```

### Why a new table (vs. existing `macro_context`)

The existing `market_data.macro_context` table (from `database/02-options-tables.sql`) has `treasury_10y`, `treasury_2y`, `yield_curve_spread` columns but is conceptually tied to options trading context. Yield-curve monitoring has different shape, history, and update semantics (one row per day for years vs. transient per-options-context rows). Separate table keeps concerns clean and avoids retro-mutating the existing options schema.

---

## 7. Alert Rules — Full Warsh Framework

Each rule returns `(priority, message, data)` when fired.

| # | Rule Name | Condition | Priority |
|---|---|---|---|
| 1 | `inversion_2s10s_start` | `spread_2s10s_prev >= 0` AND `spread_2s10s_today < 0` | CRITICAL |
| 2 | `inversion_2s10s_end` | `spread_2s10s_prev < 0` AND `spread_2s10s_today >= 0` | HIGH |
| 3 | `shape_transition` | `shape != shape_prev`; priority HIGH for unfavorable (`NORMAL→FLAT`, `NORMAL→HUMPED`, `NORMAL→INVERTED`, `FLAT→INVERTED`, `HUMPED→INVERTED`), priority MEDIUM for favorable (the inverse set) | HIGH or MEDIUM |
| 4 | `rapid_steepening` | `spread_2s10s_delta_5d > YIELD_CURVE_STEEPEN_BPS_5D` | HIGH |
| 5 | `rapid_flattening` | `spread_2s10s_delta_5d < YIELD_CURVE_FLATTEN_BPS_5D` | HIGH |
| 6 | `recession_prob_critical` | `recession_prob_nyfed_prev < 0.50` AND `recession_prob_nyfed_today >= 0.50` | CRITICAL |
| 7 | `recession_prob_warning` | `recession_prob_nyfed_prev < 0.25` AND `recession_prob_nyfed_today >= 0.25` | HIGH |

**Message format** (one alert example):

```
🚨 CRITICAL: 2s10s curve inverted
2s10s spread: -8 bps (prev: +12 bps, Δ -20 bps)
Z-score: -1.8σ vs 90-day baseline
Date: 2026-06-23
Warsh note: curve flattening kills the bank absorption channel — Fed faces QT/buyers'-strike binary choice
```

**Anti-spam:** suppress duplicate `(rule_name)` within `YIELD_CURVE_ANTISPAM_HOURS` (default 6). Suppression state held in `market_data.yield_curve_alerts` (last_triggered_at per rule_name query).

---

## 8. API Endpoints

All under `/api/yield-curve/`. Mounted via existing `src/api/main.py` FastAPI app. Returns match `MarketResponse` envelope used elsewhere in the codebase.

### `GET /api/yield-curve/current`

Latest snapshot.

**Response:**
```json
{
  "success": true,
  "data": {
    "date": "2026-06-23",
    "curve": {"3mo": 5.32, "1y": 4.98, "2y": 4.45, "5y": 4.31, "7y": 4.42, "10y": 4.51, "20y": 4.78, "30y": 4.82},
    "spreads": {"2s10s": 6, "3m10y": -81, "5s30s": 51, "2s30s": 37},
    "shape": "NORMAL",
    "shape_trend": "STEEPENING",
    "recession_prob_nyfed": 0.38,
    "deltas": {"spread_2s10s_delta_5d": 14, "spread_2s10s_delta_30d": 38},
    "zscore_2s10s_90d": 0.42,
    "stale": false,
    "days_since_update": 0
  }
}
```

### `GET /api/yield-curve/history?days=90`

Daily snapshots for chart rendering.

**Response:** `{success, data: {snapshots: [{date, spread_2s10s, shape, recession_prob_nyfed, ...}]}}`.

### `GET /api/yield-curve/alerts?days=30`

Recent alerts fired. Returns up to N most recent rows from `market_data.yield_curve_alerts`.

**Response:** `{success, data: {alerts: [{triggered_at, rule_name, priority, message, ...}]}}`.

### `GET /api/yield-curve/config`

Current thresholds (env-var values) for UI display. No secrets.

**Response:** `{success, data: {thresholds: {steepen_bps_5d: 20, ...}}}`.

---

## 9. Frontend

### New component: `YieldCurvePanel.tsx`

Location: `marketpulse-client/src/components/YieldCurvePanel.tsx`. Size target: ≤200 LOC. Uses `lightweight-charts` (already in `package.json`) for the spread chart and a custom inline SVG for the curve-shape line.

**Renders:**
- **Curve snapshot** — line chart with x-axis = maturity (3M, 1Y, 2Y, 5Y, 7Y, 10Y, 20Y, 30Y), y-axis = yield in %. Shows shape classification badge ("NORMAL" / "FLAT" / etc.).
- **2s10s spread big number** — current value in bps with color (green if >0, red if <0), 5d delta arrow, 30d delta.
- **Recession probability gauge** — circular gauge 0-100% with color-coded bands (green <25%, yellow 25-50%, red >50%).
- **30-day 2s10s spread history chart** — line chart from `lightweight-charts`, with horizontal zero-line for inversion boundary.
- **Recent alerts list** — last 10 fired alerts with timestamps, rule names, priority badges.

### Integration

Embed `<YieldCurvePanel />` inside `marketpulse-client/src/components/MacroDashboard.tsx` as a new section, above the existing regime probability timeline. The component reads from new `useYieldCurveData()` hook that hits the four API endpoints via React Query (already configured in `package.json`).

### TypeScript additions

`marketpulse-client/src/types/market.ts` — extend with:

```ts
export interface YieldCurveSnapshot {
  date: string;
  curve: Record<string, number>;
  spreads: Record<string, number>;
  shape: 'NORMAL' | 'FLAT' | 'INVERTED' | 'HUMPED' | 'INVERTED_HUMPED';
  shape_trend: 'STEEPENING' | 'FLATTENING' | 'STABLE';
  recession_prob_nyfed: number | null;
  deltas: Record<string, number>;
  zscore_2s10s_90d: number;
  stale: boolean;
  days_since_update: number;
}
export interface YieldCurveAlert {
  triggered_at: string;
  rule_name: string;
  priority: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  message: string;
  trigger_value: number;
  prior_value: number;
  delta: number;
  zscore: number;
}
```

`marketpulse-client/src/lib/api.ts` — extend `MarketPulseAPIClient` with `getYieldCurve()`, `getYieldCurveHistory(days)`, `getYieldCurveAlerts(days)`, `getYieldCurveConfig()`.

---

## 10. Scheduler Integration

**New file:** `src/scheduler/yield_curve_job.py`. Function `run_yield_curve_pipeline()`:

1. Check if today's snapshot already exists (skip if same-day run, but allow force-refresh via env var for backfill).
2. Call `FredCurveFetcher.fetch_tenors()` for the 8 tenors covering `[today, today]`.
3. Call `compute_spreads()`, `classify_shape()`, `classify_trend()`, `nyfed_recession_prob()`.
4. Load 90-day history from DB. Compute `spread_2s10s_delta_5d`, `spread_2s10s_delta_30d`, `zscore_2s10s_90d`.
5. Persist via `history.save_snapshot()`.
6. Call `YieldCurveAlerts.evaluate(snapshot, prior_snapshots)`.
7. For each fired alert: insert into `market_data.yield_curve_alerts`, dispatch via `AlertManager.send_alert()`.

**Wire-in:** `src/scheduler/scheduler.py:_register_jobs()` adds one line:
```python
self.scheduler.add_job(
    _yield_curve_job.run_yield_curve_pipeline,
    CronTrigger(hour=16, minute=30, timezone="America/New_York"),
    id="yield_curve_daily",
    name="Fetch + evaluate Treasury yield curve",
    replace_existing=True,
)
```

Cron time: 16:30 ET (after FRED publishes Treasury yields, typically by 16:00 ET).

---

## 11. Error Handling

| Failure | Behavior |
|---|---|
| FRED API 4xx/5xx | Retry 3× via `tenacity` (exponential backoff, 2s→60s); then log + skip day, fire `AlertChannel.CONSOLE` warning "yield curve fetch failed for {date}" |
| FRED returns partial data | Use whatever tenors succeeded; mark `stale=true` in API response; log missing tenors |
| Cache corrupt | Delete cache file, re-fetch (mirror `src/research/data/fred.py` corrupt-cache handling) |
| DB write fails | Log with full traceback; do NOT fire alerts (we never alert on stale/missing data); surface in next successful run's response as `stale=true` |
| FRED data >3 calendar days old | Flag `stale=true` in API response; fire `LOW` priority console alert "yield curve data is {n} days stale" |
| Same-rule alert re-fires within 6h | Suppress (anti-spam); log "alert suppressed" at debug level |
| `FRED_API_KEY` missing | Fail-fast at startup with registration-URL message (mirror `src/research/data/_fred_key.py` pattern) |

---

## 12. Testing

Per the project's existing `tests/` directory layout and TDD practice:

- **Unit tests** (`tests/yield_curve/`)
  - `test_curves.py` — spread math, shape classification, NY Fed prob formula against known values
  - `test_alerts.py` — each of the 7 rules' boundary cases; anti-spam window logic
  - `test_history.py` — DB round-trip (insert, query, dedupe)
  - `test_fetcher.py` — mocked HTTP responses for FRED; cache-hit + cache-miss paths; corrupt-cache recovery
  - `test_config.py` — env-var defaults
- **Integration tests** (`tests/integration/`)
  - Scheduler job runs end-to-end with mocked FRED + real DB (SQLite test DB or existing Postgres test container)
  - API endpoints return expected shape (smoke tests, no FRED)
- **Frontend tests** (`marketpulse-client/__tests__/`)
  - `YieldCurvePanel.test.tsx` — renders with mock data; chart, gauge, alerts list visible
  - `useYieldCurveData` hook test — fetches and returns typed data

CI must pass all new tests before merge.

---

## 13. Files Touched

### New files

- `src/yield_curve/__init__.py`
- `src/yield_curve/fetcher.py`
- `src/yield_curve/curves.py`
- `src/yield_curve/alerts.py`
- `src/yield_curve/history.py`
- `src/yield_curve/config.py`
- `src/scheduler/yield_curve_job.py`
- `src/api/routers/yield_curve.py`
- `src/migrations/versions/003_yield_curve.py`
- `tests/yield_curve/__init__.py`
- `tests/yield_curve/test_curves.py`
- `tests/yield_curve/test_alerts.py`
- `tests/yield_curve/test_history.py`
- `tests/yield_curve/test_fetcher.py`
- `tests/yield_curve/test_config.py`
- `marketpulse-client/src/components/YieldCurvePanel.tsx`
- `marketpulse-client/src/hooks/useYieldCurveData.ts`
- `marketpulse-client/__tests__/YieldCurvePanel.test.tsx`
- `marketpulse-client/__tests__/useYieldCurveData.test.ts`

### Modified files

- `src/scheduler/scheduler.py` — register new job (1 line added in `_register_jobs()`)
- `src/api/main.py` — mount `yield_curve` router
- `src/core/database.py` — add `YieldCurveSnapshot` and `YieldCurveAlert` ORM models
- `marketpulse-client/src/components/MacroDashboard.tsx` — embed `<YieldCurvePanel />`
- `marketpulse-client/src/lib/api.ts` — add `getYieldCurve*` methods to client
- `marketpulse-client/src/types/market.ts` — extend with `YieldCurveSnapshot`, `YieldCurveAlert`

---

## 14. Implementation Phases

Suggested sequencing for the implementation plan. Each phase is independently shippable.

**Phase 1 — Data foundation**
- FRED fetcher with parquet cache
- Curve math (spreads, shape, NY Fed prob)
- Unit tests for above
- Alembic migration for `yield_curve_snapshots` and `yield_curve_alerts` tables
- Manual backfill of 90 days of historical data

**Phase 2 — Persistence + scheduler**
- SQLAlchemy models
- `history.py` save/get/query
- Scheduler job wired into `MarketScheduler`
- Integration test for end-to-end pipeline

**Phase 3 — Alert engine**
- `alerts.py` with all 7 rules
- Anti-spam window
- Alert dispatch via `AlertManager`
- Persist fired alerts to DB

**Phase 4 — API**
- FastAPI router with 4 endpoints
- Response models (Pydantic)
- API smoke tests

**Phase 5 — Frontend**
- `YieldCurvePanel.tsx`
- `useYieldCurveData` hook
- Extend `MacroDashboard.tsx`
- TypeScript types + API client methods
- Component tests

---

## 15. Technical Decisions

| Decision | Choice | Rationale |
|---|---|---|
| FRED access | Direct REST + parquet cache in new module | Existing `FredProvider` whitelist (Metis SC4 lockdown) doesn't include DGS2/DGS3MO/etc.; building a new self-contained client avoids touching `src/research/`. Pattern proven in `scripts/yield_curve_monitor.py`. |
| Storage location | New dedicated table `yield_curve_snapshots` | Existing `macro_context` table is options-context-bound; curve monitoring has different semantics. Clean separation. |
| Update frequency | Daily at 16:30 ET | FRED publishes daily end-of-day only; intraday adds nothing. |
| Alert channels | Console (default) + Telegram (env-var gated) | User will deploy Telegram later; works without setup today. |
| NY Fed prob formula | Standard logistic from 3m10y spread | Matches the published NY Fed formula and `scripts/yield_curve_monitor.py:recession_prob_nyfed`. |
| Curve shape thresholds | `2s30s > 0` + `2s10s > 0` + `2s10s > 3m10y` → NORMAL; etc. | Lifted directly from `scripts/yield_curve_monitor.py:curve_shape()`. |
| Anti-spam window | 6 hours per (rule_name) | Default; tunable via env var. |
| State library on frontend | TanStack React Query | Already in `package.json`, just needs to be used. |
| Chart library | `lightweight-charts` | Already in `package.json`. |

---

## 16. Future Work (Out of Scope)

- Real-time intraday monitoring via Treasury direct feeds (would require new vendor).
- Non-US sovereign curves.
- ML-based regime prediction (deferred — wait for >2y of curve + alert history).
- Slack/Discord alert channels.
- Mobile push notification integration.
- Backtesting of historical alert accuracy vs. realized market moves.

---

## 17. Open Questions

None blocking. All assumptions documented in §15. Tunable thresholds can be adjusted via env vars without code changes after Phase 1.

---

## 18. References

- `scripts/yield_curve_monitor.py` — primary reference implementation, all curve math ported from here.
- `src/alerts/alert_manager.py` — alert dispatch API.
- `src/scheduler/scheduler.py` — job registration hook.
- `src/research/data/fred.py` — pattern reference for cache + retry + staleness handling (we mirror, don't extend).
- `marketpulse-client/src/components/MacroDashboard.tsx` — embed location.
- `database/02-options-tables.sql` — existing schema conventions (schemas, types, naming).
- US Treasury Daily Treasury Par Yield Curve Rates: https://home.treasury.gov/resource-center/data-chart-center/interest-rates
- FRED DGS series: https://fred.stlouisfed.org/release?rid=46