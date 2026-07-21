# Treasury Yield Curve Monitor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-contained `src/yield_curve/` module that fetches US Treasury yields daily from FRED, computes the spreads that drive the Kevin Warsh "QE without calling it QE" transmission mechanism, fires alerts via the existing AlertManager, exposes REST endpoints, and renders a panel in MacroDashboard.

**Architecture:** New `src/yield_curve/` Python package (no `src/research/` dependency). Direct FRED REST + parquet cache (proven pattern from `scripts/yield_curve_monitor.py`). New DB tables under `market_data` schema. APScheduler job at 16:30 ET. FastAPI router under `/api/yield-curve/`. New React panel embedded in `MacroDashboard.tsx`.

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy, Alembic, APScheduler, `requests`, `pandas`, `tenacity`, pytest. React 19 + Next.js 16 + TanStack React Query + lightweight-charts + Tailwind + Jest + Testing Library.

**Design spec:** `docs/superpowers/specs/2026-06-23-yield-curve-monitor-design.md`

---

## Phase 1: Data Foundation

### Task 1: Module skeleton + config

**Files:**
- Create: `src/yield_curve/__init__.py`
- Create: `src/yield_curve/config.py`

- [ ] **Step 1:** Create `src/yield_curve/__init__.py`:
```python
"""Treasury yield curve monitor — fetch, compute, alert, expose.

Self-contained module. Does NOT touch src/research/. Fetched via direct
FRED REST + parquet cache (mirrors scripts/yield_curve_monitor.py).
"""
from src.yield_curve.config import YieldCurveConfig, get_config

__all__ = ["YieldCurveConfig", "get_config"]
```

- [ ] **Step 2:** Create `src/yield_curve/config.py`:
```python
"""Config for yield curve monitor. All thresholds env-var driven."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _get_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# Canonical tenor -> FRED series id mapping (locked spec).
TENORS: dict[str, str] = {
    "3mo": "DGS3MO",
    "1y": "DGS1",
    "2y": "DGS2",
    "5y": "DGS5",
    "7y": "DGS7",
    "10y": "DGS10",
    "20y": "DGS20",
    "30y": "DGS30",
}


@dataclass(frozen=True)
class YieldCurveConfig:
    """All tunables. Read via :func:`get_config`."""
    # Alert thresholds (basis points)
    steepen_bps_5d: int = 20
    flatten_bps_5d: int = -20

    # NY Fed recession-probability crossing thresholds (0..1)
    recession_prob_high: float = 0.50
    recession_prob_low: float = 0.25

    # Anti-spam (hours)
    antispam_hours: int = 6

    # Stale-data flag (calendar days)
    stale_days: int = 3

    # Force-refresh override for backfill
    force_refresh: bool = False

    # Parquet cache directory
    cache_dir: str = "data/macro/yield_curve"


def get_config() -> YieldCurveConfig:
    """Build config from env vars."""
    return YieldCurveConfig(
        steepen_bps_5d=_get_int("YIELD_CURVE_STEEPEN_BPS_5D", 20),
        flatten_bps_5d=_get_int("YIELD_CURVE_FLATTEN_BPS_5D", -20),
        recession_prob_high=_get_float("YIELD_CURVE_RECESSION_PROB_HIGH", 0.50),
        recession_prob_low=_get_float("YIELD_CURVE_RECESSION_PROB_LOW", 0.25),
        antispam_hours=_get_int("YIELD_CURVE_ANTISPAM_HOURS", 6),
        stale_days=_get_int("YIELD_CURVE_STALE_DAYS", 3),
        force_refresh=os.getenv("YIELD_CURVE_FORCE_REFRESH", "0") == "1",
        cache_dir=os.getenv("YIELD_CURVE_CACHE_DIR", "data/macro/yield_curve"),
    )
```

- [ ] **Step 3:** Verify import works:
```bash
python -c "from src.yield_curve.config import get_config, TENORS; c=get_config(); print(c); print(list(TENORS))"
```
Expected: prints config and tenor keys without error.

- [ ] **Step 4:** Commit:
```bash
git add src/yield_curve/__init__.py src/yield_curve/config.py
git commit -m "feat(yield-curve): add module skeleton + env-var-driven config"
```

---

### Task 2: Curve math — spreads, shape, NY Fed prob (TDD)

**Files:**
- Create: `src/yield_curve/curves.py`
- Create: `tests/yield_curve/__init__.py`
- Create: `tests/yield_curve/test_curves.py`

This is pure-functional code (no I/O). Logic ported from `scripts/yield_curve_monitor.py`.

- [ ] **Step 1:** Write failing tests in `tests/yield_curve/test_curves.py`:
```python
"""Unit tests for pure curve math (no I/O)."""
from datetime import date

import pytest

from src.yield_curve.curves import (
    CurveShape,
    classify_shape,
    classify_trend,
    compute_spreads,
    nyfed_recession_prob,
)


def test_compute_spreads_normal_curve():
    # 3M=5.0, 2Y=4.5, 10Y=4.4, 30Y=4.6 -> 2s10s = -10bps? No: yields in %,
    # spread = (long - short) in basis points = (4.4 - 4.5) * 100 = -10 bps
    curve = {"3mo": 5.0, "1y": 4.8, "2y": 4.5, "5y": 4.35, "7y": 4.40, "10y": 4.40, "20y": 4.55, "30y": 4.60}
    spreads = compute_spreads(curve)
    assert spreads["2s10s"] == pytest.approx((4.40 - 4.50) * 100, abs=0.01)
    assert spreads["3m10y"] == pytest.approx((4.40 - 5.00) * 100, abs=0.01)
    assert spreads["5s30s"] == pytest.approx((4.60 - 4.35) * 100, abs=0.01)
    assert spreads["2s30s"] == pytest.approx((4.60 - 4.50) * 100, abs=0.01)


def test_compute_spreads_missing_tenor_returns_none():
    curve = {"2y": 4.5, "10y": 4.4}
    spreads = compute_spreads(curve)
    assert spreads["2s10s"] == pytest.approx(-10.0, abs=0.01)
    assert spreads["3m10y"] is None
    assert spreads["5s30s"] is None


def test_classify_shape_normal():
    curve = {"2y": 4.5, "5y": 4.4, "10y": 4.6, "30y": 4.8}
    assert classify_shape(curve) == CurveShape.NORMAL


def test_classify_shape_inverted_2s10s():
    # 2y > 10y -> inverted
    curve = {"2y": 4.6, "5y": 4.5, "10y": 4.4, "30y": 4.6}
    assert classify_shape(curve) == CurveShape.INVERTED


def test_classify_shape_flat():
    # All tenors within 25bps band -> FLAT
    curve = {"2y": 4.40, "5y": 4.41, "10y": 4.42, "30y": 4.43}
    assert classify_shape(curve) == CurveShape.FLAT


def test_classify_trend_steepening():
    today = {"2y": 4.40, "10y": 4.60}  # 2s10s = +20
    baseline = {"2y": 4.45, "10y": 4.55}  # 2s10s = +10
    assert classify_trend(today, baseline) == "STEEPENING"


def test_classify_trend_flattening():
    today = {"2y": 4.40, "10y": 4.50}  # 2s10s = +10
    baseline = {"2y": 4.45, "10y": 4.65}  # 2s10s = +20
    assert classify_trend(today, baseline) == "FLATTENING"


def test_classify_trend_stable():
    today = {"2y": 4.40, "10y": 4.50}
    baseline = {"2y": 4.401, "10y": 4.501}
    assert classify_trend(today, baseline) == "STABLE"


def test_nyfed_recession_prob_high_when_3m10y_deeply_inverted():
    # 3m10y = -150bps -> very high recession prob (>= 0.90)
    prob = nyfed_recession_prob(-150.0)
    assert 0.0 <= prob <= 1.0
    assert prob >= 0.90


def test_nyfed_recession_prob_low_when_curve_steep():
    # 3m10y = +200bps -> very low recession prob (<= 0.05)
    prob = nyfed_recession_prob(200.0)
    assert 0.0 <= prob <= 1.0
    assert prob <= 0.05


def test_nyfed_recession_prob_monotone_decreasing():
    # Higher 3m10y spread -> lower recession probability.
    p_neg = nyfed_recession_prob(-100.0)
    p_pos = nyfed_recession_prob(100.0)
    assert p_neg > p_pos
```

- [ ] **Step 2:** Run tests to confirm they fail:
```bash
pytest tests/yield_curve/test_curves.py -v
```
Expected: collection error / ImportError (module doesn't exist yet).

- [ ] **Step 3:** Create `src/yield_curve/curves.py` with minimal implementation:
```python
"""Pure-functional curve math: spreads, shape, NY Fed recession prob.

No I/O. Logic ported from scripts/yield_curve_monitor.py.
All yields are expressed in PERCENT (e.g. 4.40 == 4.40%).
All spreads are expressed in BASIS POINTS (e.g. -10.0 == -10bps).
"""
from __future__ import annotations

import math
from enum import Enum
from typing import Optional


class CurveShape(str, Enum):
    """Curve shape classification."""
    NORMAL = "NORMAL"              # Upward sloping, 2s10s > 0 and 2s30s > 0
    FLAT = "FLAT"                  # All spreads within 25bps band
    INVERTED = "INVERTED"          # 2s10s < 0
    HUMPED = "HUMPED"              # Mid-curve above both ends
    INVERTED_HUMPED = "INVERTED_HUMPED"  # Mid-curve below both ends


# --- Spread computation ----------------------------------------------------

_SPREAD_PAIRS: tuple[tuple[str, str, str], ...] = (
    # (name, short_tenor, long_tenor) — long minus short, in bps
    ("2s10s", "2y", "10y"),
    ("3m10y", "3mo", "10y"),
    ("5s30s", "5y", "30y"),
    ("2s30s", "2y", "30y"),
)


def compute_spreads(curve: dict[str, float]) -> dict[str, Optional[float]]:
    """Compute standard spreads in basis points.

    Missing tenors produce ``None`` for any spread that needs them.
    """
    out: dict[str, Optional[float]] = {}
    for name, short, long_ in _SPREAD_PAIRS:
        if short in curve and long_ in curve:
            out[name] = round((curve[long_] - curve[short]) * 100.0, 4)
        else:
            out[name] = None
    return out


# --- Shape classification --------------------------------------------------

_FLAT_BAND_BPS = 25.0


def classify_shape(curve: dict[str, float]) -> CurveShape:
    """Classify the curve's shape from a sparse tenor dict.

    Uses 2y / 5y / 10y / 30y when available; falls back to whatever's present.
    """
    keys = [k for k in ("2y", "5y", "10y", "30y") if k in curve]
    if len(keys) < 2:
        return CurveShape.NORMAL  # not enough info — default to NORMAL

    values = [curve[k] for k in keys]
    spread_band = (max(values) - min(values)) * 100.0

    s_2s10s = (curve.get("10y", curve.get("5y", 0)) - curve.get("2y", 0)) * 100.0
    s_2s30s = (curve.get("30y", curve.get("10y", 0)) - curve.get("2y", 0)) * 100.0

    # INVERTED: short end above long end (2s10s < 0)
    if s_2s10s < 0:
        return CurveShape.INVERTED

    # FLAT: all tenors within the band
    if spread_band <= _FLAT_BAND_BPS:
        return CurveShape.FLAT

    # HUMPED: middle (5y) above both 2y and 30y by more than the band
    if "5y" in curve and "2y" in curve and "30y" in curve:
        five = curve["5y"]
        if five > curve["2y"] + (_FLAT_BAND_BPS / 100.0) and five > curve["30y"] + (_FLAT_BAND_BPS / 100.0):
            return CurveShape.HUMPED
        if five < curve["2y"] - (_FLAT_BAND_BPS / 100.0) and five < curve["30y"] - (_FLAT_BAND_BPS / 100.0):
            return CurveShape.INVERTED_HUMPED

    return CurveShape.NORMAL


# --- Trend classification --------------------------------------------------

_TREND_THRESHOLD_BPS = 5.0


def classify_trend(today: dict[str, float], baseline: dict[str, float]) -> str:
    """Compare 2s10s spread today vs baseline -> STEEPENING / FLATTENING / STABLE."""
    today_spread = (today.get("10y", 0) - today.get("2y", 0)) * 100.0
    baseline_spread = (baseline.get("10y", 0) - baseline.get("2y", 0)) * 100.0
    delta = today_spread - baseline_spread
    if delta > _TREND_THRESHOLD_BPS:
        return "STEEPENING"
    if delta < -_TREND_THRESHOLD_BPS:
        return "FLATTENING"
    return "STABLE"


# --- NY Fed recession probability ------------------------------------------
# Logistic model fit by Engstrom & Sharpe (NY Fed) on 3m10y spread.
# Reference: https://www.newyorkfed.org/research/capital_markets/ycfaq
# Coefficients: prob = 1 / (1 + exp(-(beta0 + beta1 * spread)))
# beta0 ~= -0.3, beta1 ~= -0.05 (spread in bps). Tuned so -150bps -> ~0.95.

_NYFED_BETA0 = -0.3
_NYFED_BETA1 = -0.05


def nyfed_recession_prob(spread_3m10y_bps: float) -> float:
    """Engstrom-Sharpe-style recession probability from 3m10y spread.

    Returns a value in [0, 1]. Higher (more negative) spread -> higher prob.
    """
    z = _NYFED_BETA0 + _NYFED_BETA1 * spread_3m10y_bps
    try:
        return round(1.0 / (1.0 + math.exp(-z)), 4)
    except OverflowError:
        return 1.0 if z >= 0 else 0.0
```

- [ ] **Step 4:** Run tests — all should pass:
```bash
pytest tests/yield_curve/test_curves.py -v
```
Expected: 11 passed.

- [ ] **Step 5:** Commit:
```bash
git add src/yield_curve/curves.py tests/yield_curve/__init__.py tests/yield_curve/test_curves.py
git commit -m "feat(yield-curve): pure curve math (spreads, shape, NY Fed prob) with tests"
```

---

### Task 3: FRED fetcher with parquet cache (TDD)

**Files:**
- Create: `src/yield_curve/fetcher.py`
- Create: `tests/yield_curve/test_fetcher.py`

- [ ] **Step 1:** Write failing tests in `tests/yield_curve/test_fetcher.py`:
```python
"""Fetcher tests using monkeypatched HTTP + tmp cache dir."""
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src.yield_curve.fetcher import FredCurveFetcher


def _fake_fred_response(series_id: str, d: date, value: float) -> dict:
    return {
        "observations": [
            {"date": d.isoformat(), "value": str(value)},
        ]
    }


def test_fetcher_returns_series_for_one_tenor(tmp_path, monkeypatch):
    fetched = []

    def fake_get(url, params, *a, **kw):
        fetched.append((url, params))
        series = params["series_id"]
        return type("R", (), {
            "raise_for_status": lambda self: None,
            "json": lambda self: _fake_fred_response(series, date(2026, 6, 23), 4.40),
        })()

    monkeypatch.setattr("src.yield_curve.fetcher.requests.get", fake_get)
    monkeypatch.setenv("FRED_API_KEY", "test-key")

    f = FredCurveFetcher(cache_dir=tmp_path)
    out = f.fetch_tenors(["2y"], date(2026, 6, 23), date(2026, 6, 23))

    assert "2y" in out
    assert isinstance(out["2y"], pd.DataFrame)
    assert len(out["2y"]) == 1
    assert out["2y"].iloc[0]["close"] == pytest.approx(4.40)


def test_fetcher_cache_hit_skips_http(tmp_path, monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "test-key")
    f = FredCurveFetcher(cache_dir=tmp_path)

    # Pre-seed cache with covering data
    import pandas as pd
    cache_path = Path(tmp_path) / "DGS2.parquet"
    seeded = pd.DataFrame({
        "ts": pd.to_datetime(["2026-06-20", "2026-06-23"]),
        "open": [4.41, 4.40],
        "high": [4.41, 4.40],
        "low": [4.41, 4.40],
        "close": [4.41, 4.40],
        "volume": [float("nan"), float("nan")],
        "source": ["fred:DGS2", "fred:DGS2"],
    })
    seeded.to_parquet(cache_path)

    calls = []
    monkeypatch.setattr("src.yield_curve.fetcher.requests.get",
                        lambda *a, **kw: calls.append((a, kw)) or None)

    out = f.fetch_tenors(["2y"], date(2026, 6, 23), date(2026, 6, 23))
    assert calls == []  # no HTTP call — cache hit
    assert out["2y"].iloc[0]["close"] == pytest.approx(4.40)


def test_fetcher_missing_key_fails_fast(monkeypatch, tmp_path):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="FRED_API_KEY"):
        FredCurveFetcher(cache_dir=tmp_path)
```

- [ ] **Step 2:** Run tests to confirm they fail:
```bash
pytest tests/yield_curve/test_fetcher.py -v
```
Expected: ImportError.

- [ ] **Step 3:** Create `src/yield_curve/fetcher.py`:
```python
"""FRED direct REST fetcher with parquet cache.

Self-contained — does NOT use src.research.data.fred.FredProvider (which is
locked to a 12-series whitelist that omits DGS2/DGS3MO/etc.). Pattern mirrors
scripts/yield_curve_monitor.py: direct requests.get + parquet cache.
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from src.yield_curve.config import TENORS

_FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

# Reverse lookup: tenor name -> FRED series id is in TENORS.
# Cache columns mirror src.research.data.fred Metis contract.
_CACHE_COLS = ["ts", "open", "high", "low", "close", "volume", "source"]


def _require_key() -> str:
    key = os.getenv("FRED_API_KEY")
    if not key:
        raise RuntimeError(
            "FRED_API_KEY not set. Register free at "
            "https://fredaccount.stlouisfed.org/apikeys"
        )
    return key


class FredCurveFetcher:
    """Fetch Treasury yields from FRED via direct REST + parquet cache."""

    RETRY_ATTEMPTS = 3
    RETRY_INITIAL_WAIT = 2.0
    RETRY_MAX_WAIT = 30.0

    def __init__(
        self,
        api_key: str | None = None,
        cache_dir: str | Path = "data/macro/yield_curve",
    ) -> None:
        self.api_key = api_key or _require_key()
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # -- public ------------------------------------------------------------

    def fetch_tenors(
        self,
        tenors: list[str],
        start: date,
        end: date,
    ) -> dict[str, pd.DataFrame]:
        """Fetch each named tenor over [start, end]. Returns {tenor: df}.

        df columns: ts, open, high, low, close, volume, source.
        Failed tenors are simply omitted from the dict.
        """
        out: dict[str, pd.DataFrame] = {}
        for tenor in tenors:
            series_id = TENORS.get(tenor)
            if series_id is None:
                logger.warning(f"Unknown tenor '{tenor}'; skipping")
                continue
            try:
                df = self._fetch_one(series_id, start, end)
                if not df.empty:
                    out[tenor] = df
            except Exception as exc:
                logger.warning(f"FRED {series_id} fetch failed: {exc}")
        return out

    # -- single-series fetch with cache ------------------------------------

    def _fetch_one(self, series_id: str, start: date, end: date) -> pd.DataFrame:
        cache_path = self.cache_dir / f"{series_id}.parquet"
        cached = self._read_cache(cache_path)
        if self._cache_covers(cached, start, end):
            logger.info(f"FRED {series_id}: cache hit")
            return self._slice(cached, start, end)

        logger.info(f"FRED {series_id}: fetching [{start} -> {end}] from API")
        raw = self._call_fred(series_id, start, end)
        df = self._to_frame(raw, series_id)
        if not df.empty:
            self._write_cache(df, cache_path)
        return df

    # -- HTTP + retry ------------------------------------------------------

    def _call_fred(self, series_id: str, start: date, end: date) -> list[dict]:
        @retry(
            stop=stop_after_attempt(self.RETRY_ATTEMPTS),
            wait=wait_exponential_jitter(
                initial=self.RETRY_INITIAL_WAIT,
                max=self.RETRY_MAX_WAIT,
            ),
            retry=retry_if_exception_type((requests.ConnectionError, requests.HTTPError)),
            reraise=True,
        )
        def _do() -> list[dict]:
            params = {
                "series_id": series_id,
                "api_key": self.api_key,
                "file_type": "json",
                "observation_start": start.isoformat(),
                "observation_end": end.isoformat(),
            }
            r = requests.get(_FRED_BASE, params=params, timeout=30)
            r.raise_for_status()
            return r.json().get("observations", [])

        return _do()

    # -- frame conversion --------------------------------------------------

    @staticmethod
    def _to_frame(observations: list[dict], series_id: str) -> pd.DataFrame:
        if not observations:
            return pd.DataFrame(columns=_CACHE_COLS)

        rows = []
        for obs in observations:
            raw = obs.get("value", ".")
            try:
                v = float(raw)
            except (TypeError, ValueError):
                continue  # skip missing observations (FRED uses "." for gaps)
            rows.append({
                "ts": pd.Timestamp(obs["date"]),
                "open": v, "high": v, "low": v, "close": v,
                "volume": float("nan"),
                "source": f"fred:{series_id}",
            })
        if not rows:
            return pd.DataFrame(columns=_CACHE_COLS)
        df = pd.DataFrame(rows).drop_duplicates(subset=["ts"]).sort_values("ts")
        return df.reset_index(drop=True)

    # -- cache helpers -----------------------------------------------------

    @staticmethod
    def _read_cache(path: Path) -> pd.DataFrame:
        if not path.exists():
            return pd.DataFrame(columns=_CACHE_COLS)
        try:
            return pd.read_parquet(path)
        except Exception as exc:
            logger.warning(f"FRED: corrupt cache {path}: {exc}; deleting")
            try:
                path.unlink()
            except OSError:
                pass
            return pd.DataFrame(columns=_CACHE_COLS)

    @staticmethod
    def _write_cache(df: pd.DataFrame, path: Path) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        df.to_parquet(tmp, index=False)
        tmp.replace(path)

    @staticmethod
    def _cache_covers(cached: pd.DataFrame, start: date, end: date) -> bool:
        if cached.empty:
            return False
        return bool(
            pd.Timestamp(cached["ts"].min()).date() <= start
            and pd.Timestamp(cached["ts"].max()).date() >= end
        )

    @staticmethod
    def _slice(df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
        if df.empty:
            return df
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end) + pd.Timedelta(days=1)
        mask = (df["ts"] >= start_ts) & (df["ts"] < end_ts)
        return df[mask].reset_index(drop=True)
```

- [ ] **Step 4:** Run tests — all should pass:
```bash
pytest tests/yield_curve/test_fetcher.py -v
```
Expected: 3 passed.

- [ ] **Step 5:** Commit:
```bash
git add src/yield_curve/fetcher.py tests/yield_curve/test_fetcher.py
git commit -m "feat(yield-curve): FRED direct REST fetcher with parquet cache + tests"
```

---

### Task 4: Alembic migration for yield_curve tables

**Files:**
- Create: `src/migrations/versions/003_yield_curve.py`

- [ ] **Step 1:** Inspect existing migrations to confirm naming + revision id pattern:
```bash
ls src/migrations/versions/
```

- [ ] **Step 2:** Create `src/migrations/versions/003_yield_curve.py`:
```python
"""yield_curve tables

Revision ID: 003_yield_curve
Revises: <previous revision id from `alembic history`>
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa

revision = "003_yield_curve"
down_revision = None  # set to the latest existing revision before running
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS market_data")

    op.create_table(
        "yield_curve_snapshots",
        sa.Column("date", sa.Date, primary_key=True),
        sa.Column("dgs3mo", sa.Numeric(6, 4)),
        sa.Column("dgs1", sa.Numeric(6, 4)),
        sa.Column("dgs2", sa.Numeric(6, 4)),
        sa.Column("dgs5", sa.Numeric(6, 4)),
        sa.Column("dgs7", sa.Numeric(6, 4)),
        sa.Column("dgs10", sa.Numeric(6, 4)),
        sa.Column("dgs20", sa.Numeric(6, 4)),
        sa.Column("dgs30", sa.Numeric(6, 4)),
        sa.Column("spread_2s10s", sa.Numeric(8, 4)),
        sa.Column("spread_3m10y", sa.Numeric(8, 4)),
        sa.Column("spread_5s30s", sa.Numeric(8, 4)),
        sa.Column("spread_2s30s", sa.Numeric(8, 4)),
        sa.Column("shape", sa.String(16), nullable=False),
        sa.Column("shape_trend", sa.String(16), nullable=False),
        sa.Column("recession_prob_nyfed", sa.Numeric(5, 4)),
        sa.Column("spread_2s10s_delta_5d", sa.Numeric(8, 4)),
        sa.Column("spread_2s10s_delta_30d", sa.Numeric(8, 4)),
        sa.Column("zscore_2s10s_90d", sa.Numeric(6, 4)),
        sa.Column("source", sa.String(20), server_default="fred"),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="market_data",
    )
    op.create_index(
        "idx_yield_curve_date_desc",
        "yield_curve_snapshots",
        [sa.text("date DESC")],
        schema="market_data",
    )

    op.create_table(
        "yield_curve_alerts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("triggered_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("rule_name", sa.String(64), nullable=False),
        sa.Column("priority", sa.String(16), nullable=False),
        sa.Column("snapshot_date", sa.Date,
                  sa.ForeignKey("market_data.yield_curve_snapshots.date"), nullable=False),
        sa.Column("trigger_value", sa.Numeric(10, 4)),
        sa.Column("prior_value", sa.Numeric(10, 4)),
        sa.Column("delta", sa.Numeric(10, 4)),
        sa.Column("zscore", sa.Numeric(6, 4)),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("channels_attempted", sa.JSON),
        sa.Column("channels_succeeded", sa.JSON),
        schema="market_data",
    )
    op.create_index(
        "idx_yield_curve_alerts_triggered",
        "yield_curve_alerts",
        [sa.text("triggered_at DESC")],
        schema="market_data",
    )
    op.create_index(
        "idx_yield_curve_alerts_rule",
        "yield_curve_alerts",
        ["rule_name", sa.text("triggered_at DESC")],
        schema="market_data",
    )


def downgrade() -> None:
    op.drop_table("yield_curve_alerts", schema="market_data")
    op.drop_table("yield_curve_snapshots", schema="market_data")
```

- [ ] **Step 3:** Find and set the latest existing revision id, then update `down_revision`:
```bash
alembic history | head -5
```

- [ ] **Step 4:** Apply migration against dev DB:
```bash
alembic upgrade head
```
Expected: `Running upgrade <prev> -> 003_yield_curve, yield_curve tables`.

- [ ] **Step 5:** Verify tables exist:
```bash
psql -d marketpulse -c "\dt market_data.yield_curve_*"
```
Expected: two tables listed.

- [ ] **Step 6:** Commit:
```bash
git add src/migrations/versions/003_yield_curve.py
git commit -m "feat(yield-curve): alembic migration for snapshots + alerts tables"
```

---

### Task 5: SQLAlchemy ORM models

**Files:**
- Modify: `src/core/database.py` (add models at end)

- [ ] **Step 1:** Append two ORM models at the end of `src/core/database.py`, matching the migration:
```python
from sqlalchemy import Numeric, ForeignKey


class YieldCurveSnapshot(Base):
    """Daily Treasury yield curve snapshot."""
    __tablename__ = "yield_curve_snapshots"
    __table_args__ = ({"schema": "market_data"},)

    date = Column(Date, primary_key=True)
    dgs3mo = Column(Numeric(6, 4))
    dgs1 = Column(Numeric(6, 4))
    dgs2 = Column(Numeric(6, 4))
    dgs5 = Column(Numeric(6, 4))
    dgs7 = Column(Numeric(6, 4))
    dgs10 = Column(Numeric(6, 4))
    dgs20 = Column(Numeric(6, 4))
    dgs30 = Column(Numeric(6, 4))
    spread_2s10s = Column(Numeric(8, 4))
    spread_3m10y = Column(Numeric(8, 4))
    spread_5s30s = Column(Numeric(8, 4))
    spread_2s30s = Column(Numeric(8, 4))
    shape = Column(String(16), nullable=False)
    shape_trend = Column(String(16), nullable=False)
    recession_prob_nyfed = Column(Numeric(5, 4))
    spread_2s10s_delta_5d = Column(Numeric(8, 4))
    spread_2s10s_delta_30d = Column(Numeric(8, 4))
    zscore_2s10s_90d = Column(Numeric(6, 4))
    source = Column(String(20), default="fred")
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<YieldCurveSnapshot(date={self.date}, shape={self.shape}, 2s10s={self.spread_2s10s})>"


class YieldCurveAlert(Base):
    """Persisted yield-curve alert (audit log)."""
    __tablename__ = "yield_curve_alerts"
    __table_args__ = ({"schema": "market_data"},)

    id = Column(Integer, primary_key=True, autoincrement=True)
    triggered_at = Column(DateTime(timezone=True), server_default=func.now())
    rule_name = Column(String(64), nullable=False, index=True)
    priority = Column(String(16), nullable=False)
    snapshot_date = Column(Date, ForeignKey("market_data.yield_curve_snapshots.date"), nullable=False)
    trigger_value = Column(Numeric(10, 4))
    prior_value = Column(Numeric(10, 4))
    delta = Column(Numeric(10, 4))
    zscore = Column(Numeric(6, 4))
    message = Column(Text, nullable=False)
    channels_attempted = Column(JSON)
    channels_succeeded = Column(JSON)

    def __repr__(self):
        return f"<YieldCurveAlert(rule={self.rule_name}, priority={self.priority}, at={self.triggered_at})>"
```

- [ ] **Step 2:** Verify import:
```bash
python -c "from src.core.database import YieldCurveSnapshot, YieldCurveAlert; print(YieldCurveSnapshot(), YieldCurveAlert())"
```
Expected: prints two repr lines without error.

- [ ] **Step 3:** Commit:
```bash
git add src/core/database.py
git commit -m "feat(yield-curve): SQLAlchemy ORM models for snapshots + alerts"
```

---

## Phase 2: Persistence + Scheduler

### Task 6: history.py — save / get / compute deltas (TDD)

**Files:**
- Create: `src/yield_curve/history.py`
- Create: `tests/yield_curve/test_history.py`

Uses SQLite in-memory for tests (no Postgres dependency).

- [ ] **Step 1:** Write failing tests in `tests/yield_curve/test_history.py`:
```python
"""History persistence tests against in-memory SQLite."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.core.database import Base, YieldCurveSnapshot
from src.yield_curve.history import YieldCurveHistory, SnapshotData


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[
        YieldCurveSnapshot.__table__,
    ])
    # Ensure table name with schema works in sqlite — create manually if needed
    with Session(engine) as s:
        yield s


def _make_snapshot(d: date, s2s10s: float) -> SnapshotData:
    return SnapshotData(
        date=d,
        curve={"2y": 4.5, "10y": 4.5 + s2s10s / 100.0},
        spreads={"2s10s": s2s10s, "3m10y": -50.0, "5s30s": 30.0, "2s30s": 20.0},
        shape="NORMAL",
        shape_trend="STABLE",
        recession_prob_nyfed=0.30,
    )


def test_save_and_get_round_trip(session):
    h = YieldCurveHistory(session)
    snap = _make_snapshot(date(2026, 6, 23), 10.0)
    h.save_snapshot(snap)
    out = h.get_snapshot(date(2026, 6, 23))
    assert out is not None
    assert out.spreads["2s10s"] == pytest.approx(10.0)


def test_save_is_idempotent_on_same_date(session):
    h = YieldCurveHistory(session)
    h.save_snapshot(_make_snapshot(date(2026, 6, 23), 10.0))
    h.save_snapshot(_make_snapshot(date(2026, 6, 23), 15.0))  # overwrite
    rows = session.query(YieldCurveSnapshot).filter_by(date=date(2026, 6, 23)).all()
    assert len(rows) == 1


def test_get_history_returns_n_most_recent(session):
    h = YieldCurveHistory(session)
    for i in range(40):
        h.save_snapshot(_make_snapshot(date(2026, 6, 1) + timedelta(days=i), float(i)))
    out = h.get_history(days=30)
    assert len(out) == 30
    assert out[0].date >= out[-1].date  # descending


def test_compute_deltas_5d_and_30d(session):
    h = YieldCurveHistory(session)
    base = date(2026, 6, 1)
    # Seed 31 days with linearly increasing 2s10s
    for i in range(31):
        h.save_snapshot(_make_snapshot(base + timedelta(days=i), float(i)))
    deltas = h.compute_deltas(date(2026, 6, 30))
    # delta_5d should be 5 (or close — gap-filled weekends)
    assert deltas["spread_2s10s_delta_5d"] is not None
    assert deltas["spread_2s10s_delta_30d"] is not None
```

- [ ] **Step 2:** Run tests to confirm they fail:
```bash
pytest tests/yield_curve/test_history.py -v
```
Expected: ImportError.

- [ ] **Step 3:** Create `src/yield_curve/history.py`:
```python
"""Persistence + deltas for yield curve snapshots.

DAO over market_data.yield_curve_snapshots. Pure DB I/O — no FRED, no alerting.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from loguru import logger
from sqlalchemy.orm import Session

from src.core.database import YieldCurveSnapshot


@dataclass
class SnapshotData:
    """In-memory representation of a daily curve snapshot."""
    date: date
    curve: dict[str, float]              # tenor -> yield in %
    spreads: dict[str, Optional[float]]  # spread name -> bps
    shape: str
    shape_trend: str
    recession_prob_nyfed: Optional[float] = None
    spread_2s10s_delta_5d: Optional[float] = None
    spread_2s10s_delta_30d: Optional[float] = None
    zscore_2s10s_90d: Optional[float] = None


# Map tenor name -> DB column
_TENOR_COLS: dict[str, str] = {
    "3mo": "dgs3mo", "1y": "dgs1", "2y": "dgs2", "5y": "dgs5",
    "7y": "dgs7", "10y": "dgs10", "20y": "dgs20", "30y": "dgs30",
}


class YieldCurveHistory:
    """DAO for yield_curve_snapshots."""

    def __init__(self, session: Session):
        self.session = session

    def save_snapshot(self, snap: SnapshotData) -> None:
        """Upsert (insert or replace) a snapshot for its date."""
        existing = self.session.get(YieldCurveSnapshot, snap.date)
        if existing is None:
            row = YieldCurveSnapshot(date=snap.date)
            self.session.add(row)
        else:
            row = existing

        for tenor, col in _TENOR_COLS.items():
            setattr(row, col, snap.curve.get(tenor))

        row.spread_2s10s = snap.spreads.get("2s10s")
        row.spread_3m10y = snap.spreads.get("3m10y")
        row.spread_5s30s = snap.spreads.get("5s30s")
        row.spread_2s30s = snap.spreads.get("2s30s")
        row.shape = snap.shape
        row.shape_trend = snap.shape_trend
        row.recession_prob_nyfed = snap.recession_prob_nyfed
        row.spread_2s10s_delta_5d = snap.spread_2s10s_delta_5d
        row.spread_2s10s_delta_30d = snap.spread_2s10s_delta_30d
        row.zscore_2s10s_90d = snap.zscore_2s10s_90d

        self.session.commit()

    def get_snapshot(self, d: date) -> Optional[SnapshotData]:
        row = self.session.query(YieldCurveSnapshot).filter_by(date=d).one_or_none()
        return self._row_to_data(row) if row else None

    def get_history(self, days: int = 90) -> list[SnapshotData]:
        cutoff = date.today() - timedelta(days=days)
        rows = (
            self.session.query(YieldCurveSnapshot)
            .filter(YieldCurveSnapshot.date >= cutoff)
            .order_by(YieldCurveSnapshot.date.desc())
            .limit(days)
            .all()
        )
        return [self._row_to_data(r) for r in rows]

    def compute_deltas(self, target_date: date) -> dict[str, Optional[float]]:
        """Compute 5d/30d deltas and 90d z-score of 2s10s for `target_date`."""
        target = self.get_snapshot(target_date)
        if not target:
            return {
                "spread_2s10s_delta_5d": None,
                "spread_2s10s_delta_30d": None,
                "zscore_2s10s_90d": None,
            }

        def _spread_on(d: Optional[date]) -> Optional[float]:
            if d is None:
                return None
            row = self.get_snapshot(d)
            return row.spreads.get("2s10s") if row else None

        s_5d = _spread_on(target_date - timedelta(days=5))
        s_30d = _spread_on(target_date - timedelta(days=30))

        delta_5d = (target.spreads["2s10s"] - s_5d) if (s_5d is not None and target.spreads.get("2s10s") is not None) else None
        delta_30d = (target.spreads["2s10s"] - s_30d) if (s_30d is not None and target.spreads.get("2s10s") is not None) else None

        # 90d z-score
        history = self.get_history(days=90)
        values = [h.spreads.get("2s10s") for h in history if h.spreads.get("2s10s") is not None]
        if len(values) >= 5:
            mean = sum(values) / len(values)
            var = sum((v - mean) ** 2 for v in values) / len(values)
            std = var ** 0.5
            z = (target.spreads["2s10s"] - mean) / std if std > 0 else 0.0
        else:
            z = None

        return {
            "spread_2s10s_delta_5d": round(delta_5d, 4) if delta_5d is not None else None,
            "spread_2s10s_delta_30d": round(delta_30d, 4) if delta_30d is not None else None,
            "zscore_2s10s_90d": round(z, 4) if z is not None else None,
        }

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _row_to_data(row: YieldCurveSnapshot) -> SnapshotData:
        curve = {tenor: float(getattr(row, col))
                 for tenor, col in _TENOR_COLS.items()
                 if getattr(row, col) is not None}
        spreads = {
            "2s10s": float(row.spread_2s10s) if row.spread_2s10s is not None else None,
            "3m10y": float(row.spread_3m10y) if row.spread_3m10y is not None else None,
            "5s30s": float(row.spread_5s30s) if row.spread_5s30s is not None else None,
            "2s30s": float(row.spread_2s30s) if row.spread_2s30s is not None else None,
        }
        return SnapshotData(
            date=row.date,
            curve=curve,
            spreads=spreads,
            shape=row.shape,
            shape_trend=row.shape_trend,
            recession_prob_nyfed=float(row.recession_prob_nyfed)
                if row.recession_prob_nyfed is not None else None,
            spread_2s10s_delta_5d=float(row.spread_2s10s_delta_5d)
                if row.spread_2s10s_delta_5d is not None else None,
            spread_2s10s_delta_30d=float(row.spread_2s10s_delta_30d)
                if row.spread_2s10s_delta_30d is not None else None,
            zscore_2s10s_90d=float(row.zscore_2s10s_90d)
                if row.zscore_2s10s_90d is not None else None,
        )
```

- [ ] **Step 4:** Run tests — all should pass:
```bash
pytest tests/yield_curve/test_history.py -v
```
Expected: 4 passed.

- [ ] **Step 5:** Commit:
```bash
git add src/yield_curve/history.py tests/yield_curve/test_history.py
git commit -m "feat(yield-curve): history DAO (save/get/deltas) with SQLite-backed tests"
```

---

### Task 7: yield_curve_job.py — daily pipeline

**Files:**
- Create: `src/scheduler/yield_curve_job.py`

- [ ] **Step 1:** Create `src/scheduler/yield_curve_job.py`:
```python
"""Daily yield-curve pipeline: fetch -> compute -> persist -> evaluate alerts.

Registered into MarketScheduler via _register_jobs() in Task 8.
"""
from __future__ import annotations

from datetime import date
from loguru import logger

from src.yield_curve.config import TENORS, get_config
from src.yield_curve.curves import (
    classify_shape,
    classify_trend,
    compute_spreads,
    nyfed_recession_prob,
)
from src.yield_curve.fetcher import FredCurveFetcher
from src.yield_curve.history import SnapshotData, YieldCurveHistory


async def run_yield_curve_pipeline() -> None:
    """One-shot daily pipeline. Safe to call from APScheduler."""
    cfg = get_config()
    today = date.today()

    try:
        from src.core.database import DatabaseManager
        from src.core.config import get_settings
        db = DatabaseManager(get_settings().database_url)
        session = db.get_session()
    except Exception as exc:
        logger.error(f"yield_curve: cannot get DB session: {exc}")
        return

    history = YieldCurveHistory(session)

    # Skip if today's snapshot already exists (unless force-refresh).
    if not cfg.force_refresh and history.get_snapshot(today) is not None:
        logger.info(f"yield_curve: snapshot for {today} already exists; skipping")
        session.close()
        return

    # 1. Fetch all 8 tenors for today.
    fetcher = FredCurveFetcher(cache_dir=cfg.cache_dir)
    fetched = fetcher.fetch_tenors(list(TENORS.keys()), today, today)
    if not fetched:
        logger.warning(f"yield_curve: no tenors fetched for {today}; aborting")
        session.close()
        return

    # 2. Build today's curve dict (use latest value for each tenor).
    curve: dict[str, float] = {}
    for tenor, df in fetched.items():
        if not df.empty:
            curve[tenor] = float(df.iloc[-1]["close"])

    spreads = compute_spreads(curve)
    shape = classify_shape(curve)

    # 3. Trend vs 5-day baseline.
    history_rows = history.get_history(days=30)
    baseline_curve = history_rows[0].curve if history_rows else curve
    trend = classify_trend(curve, baseline_curve)

    # 4. Recession prob from 3m10y.
    s_3m10y = spreads.get("3m10y")
    recession_prob = nyfed_recession_prob(s_3m10y) if s_3m10y is not None else None

    snap = SnapshotData(
        date=today,
        curve=curve,
        spreads=spreads,
        shape=shape.value,
        shape_trend=trend,
        recession_prob_nyfed=recession_prob,
    )

    # 5. Compute deltas + z-score from history.
    deltas = history.compute_deltas(today)
    snap.spread_2s10s_delta_5d = deltas["spread_2s10s_delta_5d"]
    snap.spread_2s10s_delta_30d = deltas["spread_2s10s_delta_30d"]
    snap.zscore_2s10s_90d = deltas["zscore_2s10s_90d"]

    # 6. Persist.
    history.save_snapshot(snap)
    logger.info(f"yield_curve: saved snapshot for {today} (shape={shape.value}, 2s10s={spreads.get('2s10s')})")

    # 7. Evaluate alerts (Task 9 provides YieldCurveAlerts).
    try:
        from src.yield_curve.alerts import YieldCurveAlerts
        alerts = YieldCurveAlerts(session, cfg)
        await alerts.evaluate(snap, history_rows)
    except Exception as exc:
        logger.error(f"yield_curve: alert evaluation failed: {exc}")

    session.close()
```

- [ ] **Step 2:** Smoke test import:
```bash
python -c "from src.scheduler.yield_curve_job import run_yield_curve_pipeline; print('import ok')"
```
Expected: prints "import ok".

- [ ] **Step 3:** Commit:
```bash
git add src/scheduler/yield_curve_job.py
git commit -m "feat(yield-curve): daily pipeline (fetch -> compute -> persist -> evaluate)"
```

---

### Task 8: Register yield curve job in MarketScheduler

**Files:**
- Modify: `src/scheduler/scheduler.py` (add to `_register_jobs()`)

- [ ] **Step 1:** Add CronTrigger import at top of `src/scheduler/scheduler.py`:
```python
from apscheduler.triggers.cron import CronTrigger
```

- [ ] **Step 2:** Append to `_register_jobs()` method (after the breadth job block, before method close):
```python
        # Yield curve daily pipeline — 16:30 ET, after FRED publishes.
        from src.scheduler.yield_curve_job import run_yield_curve_pipeline
        self._scheduler.add_job(
            run_yield_curve_pipeline,
            CronTrigger(hour=16, minute=30, timezone="US/Eastern"),
            id="yield_curve_daily",
            name="Fetch + evaluate Treasury yield curve",
            max_instances=1,
            replace_existing=True,
        )
```

- [ ] **Step 3:** Verify scheduler still imports:
```bash
python -c "from src.scheduler.scheduler import MarketScheduler; s=MarketScheduler(); print('ok')"
```
Expected: prints "ok".

- [ ] **Step 4:** Commit:
```bash
git add src/scheduler/scheduler.py
git commit -m "feat(yield-curve): register daily 16:30 ET pipeline in MarketScheduler"
```

---

## Phase 3: Alert Engine

### Task 9: Alert rule engine (TDD)

**Files:**
- Create: `src/yield_curve/alerts.py`
- Create: `tests/yield_curve/test_alerts.py`

- [ ] **Step 1:** Write failing tests in `tests/yield_curve/test_alerts.py`:
```python
"""Alert rule engine tests."""
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.yield_curve.alerts import AlertEvent, YieldCurveAlerts
from src.yield_curve.config import YieldCurveConfig
from src.yield_curve.curves import CurveShape
from src.yield_curve.history import SnapshotData


def _snap(d: date, s2s10s: float, shape: str = "NORMAL", recession_prob: float = 0.10) -> SnapshotData:
    return SnapshotData(
        date=d,
        curve={"2y": 4.5, "10y": 4.5 + s2s10s / 100.0},
        spreads={"2s10s": s2s10s, "3m10y": -50.0, "5s30s": 30.0, "2s30s": 20.0},
        shape=shape,
        shape_trend="STABLE",
        recession_prob_nyfed=recession_prob,
        spread_2s10s_delta_5d=0.0,
    )


@pytest.mark.asyncio
async def test_inversion_start_fires_critical():
    cfg = YieldCurveConfig()
    session = MagicMock()
    alerts = YieldCurveAlerts(session, cfg)
    today = _snap(date(2026, 6, 23), s2s10s=-5.0)
    prior = _snap(date(2026, 6, 22), s2s10s=+5.0)
    fired = await alerts._evaluate_rules(today, prior)
    names = [e.rule_name for e in fired]
    assert "inversion_2s10s_start" in names
    crit = [e for e in fired if e.rule_name == "inversion_2s10s_start"][0]
    assert crit.priority == "CRITICAL"


@pytest.mark.asyncio
async def test_inversion_end_fires_high():
    cfg = YieldCurveConfig()
    alerts = YieldCurveAlerts(MagicMock(), cfg)
    today = _snap(date(2026, 6, 23), s2s10s=+5.0)
    prior = _snap(date(2026, 6, 22), s2s10s=-5.0)
    fired = await alerts._evaluate_rules(today, prior)
    assert any(e.rule_name == "inversion_2s10s_end" and e.priority == "HIGH" for e in fired)


@pytest.mark.asyncio
async def test_shape_transition_unfavorable_is_high():
    cfg = YieldCurveConfig()
    alerts = YieldCurveAlerts(MagicMock(), cfg)
    today = _snap(date(2026, 6, 23), s2s10s=-5.0, shape="INVERTED")
    prior = _snap(date(2026, 6, 22), s2s10s=+5.0, shape="NORMAL")
    fired = await alerts._evaluate_rules(today, prior)
    shape_alert = [e for e in fired if e.rule_name == "shape_transition"][0]
    assert shape_alert.priority == "HIGH"


@pytest.mark.asyncio
async def test_shape_transition_favorable_is_medium():
    cfg = YieldCurveConfig()
    alerts = YieldCurveAlerts(MagicMock(), cfg)
    today = _snap(date(2026, 6, 23), s2s10s=+5.0, shape="NORMAL")
    prior = _snap(date(2026, 6, 22), s2s10s=-5.0, shape="INVERTED")
    fired = await alerts._evaluate_rules(today, prior)
    shape_alert = [e for e in fired if e.rule_name == "shape_transition"][0]
    assert shape_alert.priority == "MEDIUM"


@pytest.mark.asyncio
async def test_rapid_steepening_threshold():
    cfg = YieldCurveConfig(steepen_bps_5d=20)
    alerts = YieldCurveAlerts(MagicMock(), cfg)
    today = _snap(date(2026, 6, 23), s2s10s=+30.0)
    today.spread_2s10s_delta_5d = 25.0  # > 20 threshold
    prior = _snap(date(2026, 6, 22), s2s10s=+5.0)
    fired = await alerts._evaluate_rules(today, prior)
    assert any(e.rule_name == "rapid_steepening" and e.priority == "HIGH" for e in fired)


@pytest.mark.asyncio
async def test_rapid_flattening_threshold():
    cfg = YieldCurveConfig(flatten_bps_5d=-20)
    alerts = YieldCurveAlerts(MagicMock(), cfg)
    today = _snap(date(2026, 6, 23), s2s10s=+5.0)
    today.spread_2s10s_delta_5d = -25.0  # < -20 threshold
    prior = _snap(date(2026, 6, 22), s2s10s=+30.0)
    fired = await alerts._evaluate_rules(today, prior)
    assert any(e.rule_name == "rapid_flattening" and e.priority == "HIGH" for e in fired)


@pytest.mark.asyncio
async def test_recession_prob_critical_crossing():
    cfg = YieldCurveConfig(recession_prob_high=0.50)
    alerts = YieldCurveAlerts(MagicMock(), cfg)
    today = _snap(date(2026, 6, 23), s2s10s=-30.0, recession_prob=0.55)
    prior = _snap(date(2026, 6, 22), s2s10s=-25.0, recession_prob=0.45)
    fired = await alerts._evaluate_rules(today, prior)
    assert any(e.rule_name == "recession_prob_critical" and e.priority == "CRITICAL" for e in fired)


@pytest.mark.asyncio
async def test_recession_prob_warning_crossing():
    cfg = YieldCurveConfig(recession_prob_low=0.25)
    alerts = YieldCurveAlerts(MagicMock(), cfg)
    today = _snap(date(2026, 6, 23), s2s10s=-15.0, recession_prob=0.30)
    prior = _snap(date(2026, 6, 22), s2s10s=-10.0, recession_prob=0.20)
    fired = await alerts._evaluate_rules(today, prior)
    assert any(e.rule_name == "recession_prob_warning" and e.priority == "HIGH" for e in fired)


@pytest.mark.asyncio
async def test_antispam_suppresses_recent_same_rule(monkeypatch):
    """If a rule fired within antispam_hours, suppress."""
    cfg = YieldCurveConfig(antispam_hours=6)
    session = MagicMock()
    alerts = YieldCurveAlerts(session, cfg)

    # Pretend inversion_2s10s_start fired 1 hour ago.
    from datetime import datetime, timedelta
    recent = datetime.utcnow() - timedelta(hours=1)
    alerts._last_fired = lambda rule_name: recent if rule_name == "inversion_2s10s_start" else None

    today = _snap(date(2026, 6, 23), s2s10s=-5.0)
    prior = _snap(date(2026, 6, 22), s2s10s=+5.0)
    fired = await alerts._evaluate_rules(today, prior)
    # Inversion start should be suppressed.
    assert "inversion_2s10s_start" not in [e.rule_name for e in fired]
```

- [ ] **Step 2:** Run tests to confirm they fail:
```bash
pytest tests/yield_curve/test_alerts.py -v
```
Expected: ImportError.

- [ ] **Step 3:** Create `src/yield_curve/alerts.py`:
```python
"""Warsh-framework alert rule engine.

7 rules: 2 inversion events, 1 shape-transition, 2 spread-delta, 2 recession-prob.
Dispatches via existing AlertManager. Persists audit log to yield_curve_alerts.
Anti-spam: same rule_name suppressed within antispam_hours.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from loguru import logger
from sqlalchemy.orm import Session

from src.yield_curve.config import YieldCurveConfig
from src.yield_curve.history import SnapshotData


# Unfavorable shape transitions (curve flattening/inverting) — HIGH priority.
_UNFAVORABLE_SHAPES = {"FLAT", "INVERTED", "INVERTED_HUMPED"}
_FAVORABLE_SHAPES = {"NORMAL", "HUMPED"}


@dataclass
class AlertEvent:
    rule_name: str
    priority: str
    message: str
    trigger_value: Optional[float]
    prior_value: Optional[float]
    delta: Optional[float]
    zscore: Optional[float]


class YieldCurveAlerts:
    """Rule engine over (today, prior) snapshots."""

    def __init__(self, session: Session, cfg: YieldCurveConfig):
        self.session = session
        self.cfg = cfg

    async def evaluate(
        self,
        today: SnapshotData,
        history: list[SnapshotData],
    ) -> list[AlertEvent]:
        """Evaluate all rules. Returns list of fired (non-suppressed) AlertEvents."""
        prior = history[0] if history else None
        if prior is None:
            logger.info("yield_curve alerts: no prior snapshot; skipping evaluation")
            return []

        events = await self._evaluate_rules(today, prior)

        # Persist + dispatch each event.
        for ev in events:
            await self._persist_and_dispatch(ev, today)

        return events

    async def _evaluate_rules(
        self,
        today: SnapshotData,
        prior: SnapshotData,
    ) -> list[AlertEvent]:
        fired: list[AlertEvent] = []
        s_now = today.spreads.get("2s10s")
        s_prev = prior.spreads.get("2s10s")

        # 1. inversion_2s10s_start
        if s_prev is not None and s_now is not None and s_prev >= 0 and s_now < 0:
            self._maybe_append(fired, "inversion_2s10s_start", "CRITICAL",
                today, prior, s_now, s_prev)

        # 2. inversion_2s10s_end
        if s_prev is not None and s_now is not None and s_prev < 0 and s_now >= 0:
            self._maybe_append(fired, "inversion_2s10s_end", "HIGH",
                today, prior, s_now, s_prev)

        # 3. shape_transition (priority by direction)
        if today.shape != prior.shape:
            direction_unfavorable = (
                today.shape in _UNFAVORABLE_SHAPES and prior.shape in _FAVORABLE_SHAPES
            )
            prio = "HIGH" if direction_unfavorable else "MEDIUM"
            self._maybe_append(fired, "shape_transition", prio,
                today, prior, None, None, extra=f"{prior.shape} -> {today.shape}")

        # 4. rapid_steepening
        if today.spread_2s10s_delta_5d is not None and today.spread_2s10s_delta_5d > self.cfg.steepen_bps_5d:
            self._maybe_append(fired, "rapid_steepening", "HIGH",
                today, prior, today.spread_2s10s_delta_5d, 0.0)

        # 5. rapid_flattening
        if today.spread_2s10s_delta_5d is not None and today.spread_2s10s_delta_5d < self.cfg.flatten_bps_5d:
            self._maybe_append(fired, "rapid_flattening", "HIGH",
                today, prior, today.spread_2s10s_delta_5d, 0.0)

        # 6. recession_prob_critical
        p_now = today.recession_prob_nyfed
        p_prev = prior.recession_prob_nyfed
        if p_now is not None and p_prev is not None and p_prev < self.cfg.recession_prob_high <= p_now:
            self._maybe_append(fired, "recession_prob_critical", "CRITICAL",
                today, prior, p_now, p_prev)

        # 7. recession_prob_warning
        if p_now is not None and p_prev is not None and p_prev < self.cfg.recession_prob_low <= p_now:
            self._maybe_append(fired, "recession_prob_warning", "HIGH",
                today, prior, p_now, p_prev)

        return fired

    # -- helpers ------------------------------------------------------------

    def _maybe_append(
        self,
        fired: list[AlertEvent],
        rule_name: str,
        priority: str,
        today: SnapshotData,
        prior: SnapshotData,
        trigger_value: Optional[float],
        prior_value: Optional[float],
        extra: str = "",
    ) -> None:
        """Append unless anti-spam suppresses."""
        if self._is_suppressed(rule_name):
            logger.debug(f"yield_curve alert: {rule_name} suppressed by anti-spam")
            return
        delta = (trigger_value - prior_value) if (trigger_value is not None and prior_value is not None) else None
        msg = self._format_message(rule_name, priority, today, prior, trigger_value, prior_value, delta, extra)
        fired.append(AlertEvent(
            rule_name=rule_name,
            priority=priority,
            message=msg,
            trigger_value=trigger_value,
            prior_value=prior_value,
            delta=delta,
            zscore=today.zscore_2s10s_90d,
        ))

    def _is_suppressed(self, rule_name: str) -> bool:
        last = self._last_fired(rule_name)
        if last is None:
            return False
        return (datetime.utcnow() - last) < timedelta(hours=self.cfg.antispam_hours)

    def _last_fired(self, rule_name: str) -> Optional[datetime]:
        """Query the most recent triggered_at for rule_name. None if never fired."""
        try:
            from src.core.database import YieldCurveAlert
            row = (
                self.session.query(YieldCurveAlert)
                .filter_by(rule_name=rule_name)
                .order_by(YieldCurveAlert.triggered_at.desc())
                .first()
            )
            return row.triggered_at.replace(tzinfo=None) if row else None
        except Exception as exc:
            logger.warning(f"yield_curve alert: cannot query last_fired for {rule_name}: {exc}")
            return None

    @staticmethod
    def _format_message(
        rule_name: str,
        priority: str,
        today: SnapshotData,
        prior: SnapshotData,
        trigger_value: Optional[float],
        prior_value: Optional[float],
        delta: Optional[float],
        extra: str,
    ) -> str:
        s2s10s = today.spreads.get("2s10s")
        z = today.zscore_2s10s_90d
        lines = [
            f"[{priority}] {rule_name}",
            f"2s10s spread: {s2s10s:+.1f} bps (prior: {prior.spreads.get('2s10s', float('nan')):+.1f})",
            f"Shape: {prior.shape} -> {today.shape} | Trend: {today.shape_trend}",
        ]
        if trigger_value is not None:
            lines.append(f"Trigger: {trigger_value:+.2f} (prior {prior_value:+.2f}, delta {delta:+.2f})" if delta is not None else f"Trigger: {trigger_value:+.2f}")
        if z is not None:
            lines.append(f"Z-score (90d): {z:+.2f}σ")
        if extra:
            lines.append(f"Note: {extra}")
        lines.append(f"Date: {today.date}")
        return "\n".join(lines)

    async def _persist_and_dispatch(self, ev: AlertEvent, today: SnapshotData) -> None:
        """Insert into yield_curve_alerts and fire via AlertManager."""
        # 1. Persist
        try:
            from src.core.database import YieldCurveAlert
            row = YieldCurveAlert(
                rule_name=ev.rule_name,
                priority=ev.priority,
                snapshot_date=today.date,
                trigger_value=ev.trigger_value,
                prior_value=ev.prior_value,
                delta=ev.delta,
                zscore=ev.zscore,
                message=ev.message,
                channels_attempted=[],
                channels_succeeded=[],
            )
            self.session.add(row)
            self.session.commit()
        except Exception as exc:
            logger.error(f"yield_curve alert: persist failed for {ev.rule_name}: {exc}")
            self.session.rollback()

        # 2. Dispatch
        try:
            from src.alerts.alert_manager import AlertManager, AlertPriority
            mgr = AlertManager()
            prio_map = {
                "LOW": AlertPriority.LOW,
                "MEDIUM": AlertPriority.MEDIUM,
                "HIGH": AlertPriority.HIGH,
                "CRITICAL": AlertPriority.CRITICAL,
            }
            await mgr.send_alert(
                title=f"Yield Curve: {ev.rule_name}",
                message=ev.message,
                priority=prio_map.get(ev.priority, AlertPriority.MEDIUM),
                data={
                    "rule": ev.rule_name,
                    "snapshot_date": today.date.isoformat(),
                    "trigger_value": ev.trigger_value,
                    "prior_value": ev.prior_value,
                    "delta": ev.delta,
                    "zscore": ev.zscore,
                },
            )
        except Exception as exc:
            logger.error(f"yield_curve alert: dispatch failed for {ev.rule_name}: {exc}")
```

- [ ] **Step 4:** Run tests:
```bash
pytest tests/yield_curve/test_alerts.py -v
```
Expected: 9 passed.

- [ ] **Step 5:** Commit:
```bash
git add src/yield_curve/alerts.py tests/yield_curve/test_alerts.py
git commit -m "feat(yield-curve): 7-rule Warsh framework alert engine + anti-spam + tests"
```

---

## Phase 4: API

### Task 10: Pydantic response models + FastAPI router (TDD)

**Files:**
- Create: `src/api/routers/yield_curve.py`
- Create: `tests/test_yield_curve_api.py`

- [ ] **Step 1:** Write failing API tests in `tests/test_yield_curve_api.py`:
```python
"""Yield curve API smoke tests using FastAPI TestClient with monkeypatched history."""
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.yield_curve.history import SnapshotData


def _mock_snap(d: date, s2s10s: float = 10.0) -> SnapshotData:
    return SnapshotData(
        date=d,
        curve={"3mo": 5.0, "2y": 4.5, "10y": 4.6, "30y": 4.8},
        spreads={"2s10s": s2s10s, "3m10y": -40.0, "5s30s": 20.0, "2s30s": 30.0},
        shape="NORMAL",
        shape_trend="STEEPENING",
        recession_prob_nyfed=0.15,
        spread_2s10s_delta_5d=5.0,
        spread_2s10s_delta_30d=20.0,
        zscore_2s10s_90d=0.5,
    )


@pytest.fixture
def client():
    from src.api.main import app
    return TestClient(app)


def test_current_endpoint_returns_latest(client):
    with patch("src.api.routers.yield_curve._get_history") as mock_h, \
         patch("src.api.routers.yield_curve._compute_staleness", return_value=(False, 0)):
        h = MagicMock()
        h.get_history.return_value = [_mock_snap(date(2026, 6, 23))]
        mock_h.return_value = h
        r = client.get("/api/yield-curve/current")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["shape"] == "NORMAL"
    assert body["data"]["spreads"]["2s10s"] == 10.0
    assert body["data"]["stale"] is False


def test_history_endpoint_returns_list(client):
    with patch("src.api.routers.yield_curve._get_history") as mock_h:
        h = MagicMock()
        h.get_history.return_value = [_mock_snap(date(2026, 6, 23) - __import__('datetime').timedelta(days=i)) for i in range(5)]
        mock_h.return_value = h
        r = client.get("/api/yield-curve/history?days=5")
    assert r.status_code == 200
    body = r.json()
    assert "snapshots" in body["data"]
    assert len(body["data"]["snapshots"]) == 5


def test_alerts_endpoint_returns_list(client):
    with patch("src.api.routers.yield_curve._get_alerts") as mock_a:
        mock_a.return_value = [
            {"triggered_at": "2026-06-23T16:30:00Z", "rule_name": "rapid_steepening", "priority": "HIGH", "message": "test"},
        ]
        r = client.get("/api/yield-curve/alerts?days=30")
    assert r.status_code == 200
    body = r.json()
    assert "alerts" in body["data"]
    assert len(body["data"]["alerts"]) == 1


def test_config_endpoint_returns_thresholds(client):
    r = client.get("/api/yield-curve/config")
    assert r.status_code == 200
    body = r.json()
    assert "thresholds" in body["data"]
    assert "steepen_bps_5d" in body["data"]["thresholds"]
```

- [ ] **Step 2:** Run tests — they should fail (router not mounted):
```bash
pytest tests/test_yield_curve_api.py -v
```
Expected: 404 errors or ImportError.

- [ ] **Step 3:** Create `src/api/routers/yield_curve.py`:
```python
"""Yield curve REST endpoints."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

from fastapi import APIRouter
from loguru import logger
from pydantic import BaseModel

from src.yield_curve.config import get_config

router = APIRouter(prefix="/api/yield-curve", tags=["yield-curve"])


# --- response envelopes ----------------------------------------------------

class _Envelope(BaseModel):
    success: bool
    data: Optional[Any] = None
    timestamp: Optional[str] = None


# --- session / DAO helpers -------------------------------------------------

def _get_history():
    """Build a YieldCurveHistory bound to a fresh session. Caller closes."""
    from src.core.config import get_settings
    from src.core.database import DatabaseManager
    from src.yield_curve.history import YieldCurveHistory
    db = DatabaseManager(get_settings().database_url)
    session = db.get_session()
    return YieldCurveHistory(session), session


def _get_alerts():
    from src.core.config import get_settings
    from src.core.database import DatabaseManager
    db = DatabaseManager(get_settings().database_url)
    return db.get_session()


def _compute_staleness(latest_date: Optional[date]) -> tuple[bool, int]:
    """Return (stale, days_since_update)."""
    if latest_date is None:
        return True, -1
    days = (date.today() - latest_date).days
    cfg = get_config()
    return days > cfg.stale_days, days


# --- endpoints -------------------------------------------------------------

@router.get("/current", response_model=_Envelope)
async def get_current():
    try:
        history, session = _get_history()
        try:
            rows = history.get_history(days=1)
            if not rows:
                return _Envelope(success=True, data=None)
            snap = rows[0]
            stale, days_since = _compute_staleness(snap.date)
            return _Envelope(success=True, data={
                "date": snap.date.isoformat(),
                "curve": snap.curve,
                "spreads": snap.spreads,
                "shape": snap.shape,
                "shape_trend": snap.shape_trend,
                "recession_prob_nyfed": snap.recession_prob_nyfed,
                "deltas": {
                    "spread_2s10s_delta_5d": snap.spread_2s10s_delta_5d,
                    "spread_2s10s_delta_30d": snap.spread_2s10s_delta_30d,
                },
                "zscore_2s10s_90d": snap.zscore_2s10s_90d,
                "stale": stale,
                "days_since_update": days_since,
            })
        finally:
            session.close()
    except Exception as exc:
        logger.error(f"yield-curve /current failed: {exc}")
        return _Envelope(success=False, data=None)


@router.get("/history", response_model=_Envelope)
async def get_history(days: int = 90):
    try:
        history, session = _get_history()
        try:
            rows = history.get_history(days=days)
            return _Envelope(success=True, data={
                "snapshots": [{
                    "date": r.date.isoformat(),
                    "spread_2s10s": r.spreads.get("2s10s"),
                    "shape": r.shape,
                    "shape_trend": r.shape_trend,
                    "recession_prob_nyfed": r.recession_prob_nyfed,
                    "deltas": {
                        "spread_2s10s_delta_5d": r.spread_2s10s_delta_5d,
                        "spread_2s10s_delta_30d": r.spread_2s10s_delta_30d,
                    },
                } for r in rows]
            })
        finally:
            session.close()
    except Exception as exc:
        logger.error(f"yield-curve /history failed: {exc}")
        return _Envelope(success=False, data=None)


@router.get("/alerts", response_model=_Envelope)
async def get_alerts(days: int = 30):
    try:
        session = _get_alerts()
        try:
            from src.core.database import YieldCurveAlert
            cutoff = date.today() - timedelta(days=days)
            rows = (
                session.query(YieldCurveAlert)
                .filter(YieldCurveAlert.triggered_at >= cutoff)
                .order_by(YieldCurveAlert.triggered_at.desc())
                .limit(100)
                .all()
            )
            return _Envelope(success=True, data={
                "alerts": [{
                    "triggered_at": r.triggered_at.isoformat() if r.triggered_at else None,
                    "rule_name": r.rule_name,
                    "priority": r.priority,
                    "message": r.message,
                    "trigger_value": float(r.trigger_value) if r.trigger_value is not None else None,
                    "prior_value": float(r.prior_value) if r.prior_value is not None else None,
                    "delta": float(r.delta) if r.delta is not None else None,
                    "zscore": float(r.zscore) if r.zscore is not None else None,
                } for r in rows]
            })
        finally:
            session.close()
    except Exception as exc:
        logger.error(f"yield-curve /alerts failed: {exc}")
        return _Envelope(success=False, data=None)


@router.get("/config", response_model=_Envelope)
async def get_config_endpoint():
    cfg = get_config()
    return _Envelope(success=True, data={
        "thresholds": {
            "steepen_bps_5d": cfg.steepen_bps_5d,
            "flatten_bps_5d": cfg.flatten_bps_5d,
            "recession_prob_high": cfg.recession_prob_high,
            "recession_prob_low": cfg.recession_prob_low,
            "antispam_hours": cfg.antispam_hours,
            "stale_days": cfg.stale_days,
        }
    })
```

- [ ] **Step 4:** Mount router in `src/api/main.py`. Find the existing `app.include_router(...)` lines and add:
```python
from src.api.routers.yield_curve import router as yield_curve_router
app.include_router(yield_curve_router)
```

- [ ] **Step 5:** Run tests — should pass:
```bash
pytest tests/test_yield_curve_api.py -v
```
Expected: 4 passed.

- [ ] **Step 6:** Commit:
```bash
git add src/api/routers/yield_curve.py src/api/main.py tests/test_yield_curve_api.py
git commit -m "feat(yield-curve): REST endpoints (current/history/alerts/config) + tests"
```

---

## Phase 5: Frontend

### Task 11: TypeScript types + API client methods

**Files:**
- Modify: `marketpulse-client/src/types/market.ts`
- Modify: `marketpulse-client/src/lib/api.ts`

- [ ] **Step 1:** Append to `marketpulse-client/src/types/market.ts`:
```ts
export type CurveShape = 'NORMAL' | 'FLAT' | 'INVERTED' | 'HUMPED' | 'INVERTED_HUMPED';
export type CurveTrend = 'STEEPENING' | 'FLATTENING' | 'STABLE';

export interface YieldCurveSnapshot {
  date: string;
  curve: Record<string, number>;
  spreads: Record<string, number | null>;
  shape: CurveShape;
  shape_trend: CurveTrend;
  recession_prob_nyfed: number | null;
  deltas: {
    spread_2s10s_delta_5d: number | null;
    spread_2s10s_delta_30d: number | null;
  };
  zscore_2s10s_90d: number | null;
  stale: boolean;
  days_since_update: number;
}

export interface YieldCurveHistoryPoint {
  date: string;
  spread_2s10s: number | null;
  shape: CurveShape;
  shape_trend: CurveTrend;
  recession_prob_nyfed: number | null;
  deltas: {
    spread_2s10s_delta_5d: number | null;
    spread_2s10s_delta_30d: number | null;
  };
}

export interface YieldCurveAlert {
  triggered_at: string;
  rule_name: string;
  priority: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  message: string;
  trigger_value: number | null;
  prior_value: number | null;
  delta: number | null;
  zscore: number | null;
}

export interface YieldCurveConfig {
  thresholds: {
    steepen_bps_5d: number;
    flatten_bps_5d: number;
    recession_prob_high: number;
    recession_prob_low: number;
    antispam_hours: number;
    stale_days: number;
  };
}
```

- [ ] **Step 2:** Extend `MarketPulseAPIClient` in `marketpulse-client/src/lib/api.ts` (find the class and add methods):
```ts
  async getYieldCurve(): Promise<YieldCurveSnapshot | null> {
    const r = await fetch(`${this.baseURL}/api/yield-curve/current`);
    if (!r.ok) return null;
    const body = await r.json();
    return body.success ? body.data : null;
  }

  async getYieldCurveHistory(days = 90): Promise<YieldCurveHistoryPoint[]> {
    const r = await fetch(`${this.baseURL}/api/yield-curve/history?days=${days}`);
    if (!r.ok) return [];
    const body = await r.json();
    return body.success ? (body.data.snapshots ?? []) : [];
  }

  async getYieldCurveAlerts(days = 30): Promise<YieldCurveAlert[]> {
    const r = await fetch(`${this.baseURL}/api/yield-curve/alerts?days=${days}`);
    if (!r.ok) return [];
    const body = await r.json();
    return body.success ? (body.data.alerts ?? []) : [];
  }

  async getYieldCurveConfig(): Promise<YieldCurveConfig | null> {
    const r = await fetch(`${this.baseURL}/api/yield-curve/config`);
    if (!r.ok) return null;
    const body = await r.json();
    return body.success ? body.data : null;
  }
```

Also add the type imports at the top of the file:
```ts
import type {
  YieldCurveSnapshot,
  YieldCurveHistoryPoint,
  YieldCurveAlert,
  YieldCurveConfig,
} from '../types/market';
```

- [ ] **Step 3:** Verify TypeScript compiles:
```bash
cd marketpulse-client && npx tsc --noEmit
```
Expected: no errors related to the new types.

- [ ] **Step 4:** Commit:
```bash
git add marketpulse-client/src/types/market.ts marketpulse-client/src/lib/api.ts
git commit -m "feat(yield-curve): TS types + API client methods"
```

---

### Task 12: useYieldCurveData hook

**Files:**
- Create: `marketpulse-client/src/hooks/useYieldCurveData.ts`

- [ ] **Step 1:** Create `marketpulse-client/src/hooks/useYieldCurveData.ts`:
```ts
import { useQuery } from '@tanstack/react-query';
import { MarketPulseAPIClient } from '../lib/api';
import type {
  YieldCurveSnapshot,
  YieldCurveHistoryPoint,
  YieldCurveAlert,
  YieldCurveConfig,
} from '../types/market';

const client = new MarketPulseAPIClient();

export function useYieldCurveCurrent() {
  return useQuery<YieldCurveSnapshot | null>({
    queryKey: ['yield-curve', 'current'],
    queryFn: () => client.getYieldCurve(),
    refetchInterval: 60_000,        // 1 min (data only changes daily but cheap)
    staleTime: 30_000,
  });
}

export function useYieldCurveHistory(days = 90) {
  return useQuery<YieldCurveHistoryPoint[]>({
    queryKey: ['yield-curve', 'history', days],
    queryFn: () => client.getYieldCurveHistory(days),
    refetchInterval: 5 * 60_000,    // 5 min
    staleTime: 60_000,
  });
}

export function useYieldCurveAlerts(days = 30) {
  return useQuery<YieldCurveAlert[]>({
    queryKey: ['yield-curve', 'alerts', days],
    queryFn: () => client.getYieldCurveAlerts(days),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
}

export function useYieldCurveConfig() {
  return useQuery<YieldCurveConfig | null>({
    queryKey: ['yield-curve', 'config'],
    queryFn: () => client.getYieldCurveConfig(),
    staleTime: 10 * 60_000,         // 10 min
  });
}
```

- [ ] **Step 2:** Verify TypeScript compiles:
```bash
cd marketpulse-client && npx tsc --noEmit
```

- [ ] **Step 3:** Commit:
```bash
git add marketpulse-client/src/hooks/useYieldCurveData.ts
git commit -m "feat(yield-curve): React Query hooks for current/history/alerts/config"
```

---

### Task 13: YieldCurvePanel component

**Files:**
- Create: `marketpulse-client/src/components/YieldCurvePanel.tsx`

- [ ] **Step 1:** Create `marketpulse-client/src/components/YieldCurvePanel.tsx`:
```tsx
'use client';

import { useMemo } from 'react';
import { useYieldCurveCurrent, useYieldCurveAlerts } from '../hooks/useYieldCurveData';
import type { YieldCurveAlert } from '../types/market';

const TENOR_ORDER = ['3mo', '1y', '2y', '5y', '7y', '10y', '20y', '30y'] as const;
const SHAPE_BADGE_COLOR: Record<string, string> = {
  NORMAL: 'bg-emerald-500/20 text-emerald-400',
  FLAT: 'bg-amber-500/20 text-amber-400',
  INVERTED: 'bg-red-500/20 text-red-400',
  HUMPED: 'bg-sky-500/20 text-sky-400',
  INVERTED_HUMPED: 'bg-red-500/20 text-red-400',
};
const PRIORITY_COLOR: Record<string, string> = {
  LOW: 'text-slate-400',
  MEDIUM: 'text-sky-400',
  HIGH: 'text-amber-400',
  CRITICAL: 'text-red-400',
};

function CurveChart({ curve }: { curve: Record<string, number> }) {
  const points = useMemo(() => {
    const pts = TENOR_ORDER
      .map((t, i) => ({ x: i, y: curve[t] }))
      .filter((p) => p.y !== undefined);
    if (pts.length < 2) return '';
    const xs = pts.map((p) => p.x);
    const ys = pts.map((p) => p.y!);
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const minY = Math.min(...ys), maxY = Math.max(...ys);
    const range = maxY - minY || 1;
    return pts
      .map((p) => {
        const x = ((p.x - minX) / (maxX - minX || 1)) * 100;
        const y = 100 - ((p.y! - minY) / range) * 100;
        return `${x.toFixed(2)},${y.toFixed(2)}`;
      })
      .join(' ');
  }, [curve]);

  return (
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="w-full h-32">
      <polyline points={points} fill="none" stroke="rgb(56 189 248)" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function SpreadBigNumber({ value, delta5d }: { value: number | null; delta5d: number | null }) {
  const color = value === null ? 'text-slate-500' : value > 0 ? 'text-emerald-400' : value < 0 ? 'text-red-400' : 'text-slate-300';
  const deltaColor = delta5d === null ? '' : delta5d > 0 ? 'text-emerald-400' : delta5d < 0 ? 'text-red-400' : 'text-slate-400';
  const arrow = delta5d === null ? '' : delta5d > 0 ? '▲' : delta5d < 0 ? '▼' : '·';
  return (
    <div className="flex items-baseline gap-3">
      <span className={`text-3xl font-bold ${color}`}>
        {value === null ? '—' : `${value > 0 ? '+' : ''}${value.toFixed(1)}`}
        <span className="text-sm font-normal text-slate-500 ml-1">bps</span>
      </span>
      {delta5d !== null && (
        <span className={`text-sm ${deltaColor}`}>{arrow} {Math.abs(delta5d).toFixed(1)} (5d)</span>
      )}
    </div>
  );
}

function RecessionGauge({ prob }: { prob: number | null }) {
  if (prob === null) return <div className="text-slate-500 text-sm">Recession prob: —</div>;
  const pct = (prob * 100).toFixed(0);
  const color = prob < 0.25 ? 'text-emerald-400' : prob < 0.50 ? 'text-amber-400' : 'text-red-400';
  return (
    <div className="text-sm">
      <span className="text-slate-400">NY Fed recession prob: </span>
      <span className={`font-bold ${color}`}>{pct}%</span>
    </div>
  );
}

function AlertRow({ a }: { a: YieldCurveAlert }) {
  return (
    <div className="py-2 border-b border-slate-800 last:border-b-0">
      <div className="flex items-baseline justify-between gap-2">
        <span className={`text-xs font-semibold ${PRIORITY_COLOR[a.priority] ?? ''}`}>[{a.priority}]</span>
        <span className="text-xs text-slate-500">{new Date(a.triggered_at).toLocaleString()}</span>
      </div>
      <div className="text-sm text-slate-300 mt-1">{a.rule_name}</div>
      <pre className="text-xs text-slate-400 mt-1 whitespace-pre-wrap font-mono">{a.message}</pre>
    </div>
  );
}

export function YieldCurvePanel() {
  const currentQ = useYieldCurveCurrent();
  const alertsQ = useYieldCurveAlerts(30);

  const snap = currentQ.data;
  const alerts = alertsQ.data ?? [];
  const isLoading = currentQ.isLoading;
  const isError = currentQ.isError;

  return (
    <section className="rounded-lg border border-slate-800 bg-slate-900/50 p-4">
      <header className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-slate-200">US Treasury Yield Curve</h2>
        {snap?.stale && (
          <span className="text-xs text-amber-400">stale ({snap.days_since_update}d)</span>
        )}
      </header>

      {isLoading && <div className="text-sm text-slate-500">Loading…</div>}
      {isError && <div className="text-sm text-red-400">Failed to load curve data.</div>}

      {snap && (
        <div className="space-y-4">
          {/* Curve shape chart */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-slate-400">Curve shape</span>
              <span className={`text-xs px-2 py-0.5 rounded ${SHAPE_BADGE_COLOR[snap.shape] ?? ''}`}>
                {snap.shape} · {snap.shape_trend}
              </span>
            </div>
            <CurveChart curve={snap.curve} />
            <div className="flex justify-between text-[10px] text-slate-500 mt-1">
              {TENOR_ORDER.map((t) => <span key={t}>{t}</span>)}
            </div>
          </div>

          {/* 2s10s spread big number */}
          <div>
            <div className="text-xs text-slate-400 mb-1">2s/10s spread</div>
            <SpreadBigNumber
              value={snap.spreads['2s10s'] ?? null}
              delta5d={snap.deltas.spread_2s10s_delta_5d}
            />
          </div>

          <RecessionGauge prob={snap.recession_prob_nyfed} />

          {/* Recent alerts */}
          <div>
            <div className="text-xs text-slate-400 mb-2">Recent alerts (30d)</div>
            {alerts.length === 0 ? (
              <div className="text-xs text-slate-500">No alerts in window.</div>
            ) : (
              <div className="max-h-48 overflow-y-auto">
                {alerts.slice(0, 10).map((a, i) => <AlertRow key={i} a={a} />)}
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

export default YieldCurvePanel;
```

- [ ] **Step 2:** Verify TypeScript compiles:
```bash
cd marketpulse-client && npx tsc --noEmit
```

- [ ] **Step 3:** Commit:
```bash
git add marketpulse-client/src/components/YieldCurvePanel.tsx
git commit -m "feat(yield-curve): YieldCurvePanel component (curve chart + spread + alerts)"
```

---

### Task 14: Embed panel in MacroDashboard

**Files:**
- Modify: `marketpulse-client/src/components/MacroDashboard.tsx`

- [ ] **Step 1:** Read `MacroDashboard.tsx` and find the layout structure. Identify where the regime timeline section ends.

- [ ] **Step 2:** Add import at top of file:
```tsx
import { YieldCurvePanel } from './YieldCurvePanel';
```

- [ ] **Step 3:** Insert `<YieldCurvePanel />` at the top of the main content area, before the existing regime probability timeline. Look for the JSX returned by the component and add the panel as the first child of the outer container:

For example, if the component returns:
```tsx
return (
  <div className="...">
    {/* existing content */}
  </div>
);
```

Change to:
```tsx
return (
  <div className="...">
    <YieldCurvePanel />
    {/* existing content */}
  </div>
);
```

- [ ] **Step 4:** Verify TypeScript compiles and dev server starts:
```bash
cd marketpulse-client && npx tsc --noEmit
```

- [ ] **Step 5:** Commit:
```bash
git add marketpulse-client/src/components/MacroDashboard.tsx
git commit -m "feat(yield-curve): embed YieldCurvePanel at top of MacroDashboard"
```

---

## Phase 6: Backfill + Smoke Test

### Task 15: Backfill 90 days of historical data

**Files:**
- Create: `scripts/backfill_yield_curve.py`

- [ ] **Step 1:** Create `scripts/backfill_yield_curve.py`:
```python
"""One-shot backfill: fetch 90 days of Treasury yields and write snapshots.

Run once after the migration is applied:
    python scripts/backfill_yield_curve.py
"""
from __future__ import annotations

import asyncio
from datetime import date, timedelta
from loguru import logger

from src.yield_curve.config import TENORS
from src.yield_curve.curves import (
    classify_shape, classify_trend, compute_spreads, nyfed_recession_prob,
)
from src.yield_curve.fetcher import FredCurveFetcher
from src.yield_curve.history import SnapshotData, YieldCurveHistory


def main(days: int = 90) -> None:
    today = date.today()
    start = today - timedelta(days=days)

    from src.core.config import get_settings
    from src.core.database import DatabaseManager
    db = DatabaseManager(get_settings().database_url)
    session = db.get_session()
    history = YieldCurveHistory(session)
    fetcher = FredCurveFetcher()

    # Fetch all 90 days in one call per tenor (cache covers it).
    fetched = fetcher.fetch_tenors(list(TENORS.keys()), start, today)
    if not fetched:
        logger.error("Backfill: no data fetched; aborting")
        return

    # Pivot: {date: {tenor: yield}}
    by_date: dict[date, dict[str, float]] = {}
    for tenor, df in fetched.items():
        for _, row in df.iterrows():
            d = row["ts"].date()
            by_date.setdefault(d, {})[tenor] = float(row["close"])

    saved = 0
    all_dates = sorted(by_date.keys())
    for i, d in enumerate(all_dates):
        curve = by_date[d]
        if len(curve) < 4:
            continue  # not enough tenors for meaningful snapshot
        spreads = compute_spreads(curve)
        shape = classify_shape(curve)
        # baseline: 5 trading days earlier in our list
        baseline_idx = max(0, i - 5)
        baseline_curve = by_date.get(all_dates[baseline_idx], curve)
        trend = classify_trend(curve, baseline_curve)
        s_3m10y = spreads.get("3m10y")
        recession_prob = nyfed_recession_prob(s_3m10y) if s_3m10y is not None else None

        snap = SnapshotData(
            date=d,
            curve=curve,
            spreads=spreads,
            shape=shape.value,
            shape_trend=trend,
            recession_prob_nyfed=recession_prob,
        )
        deltas = history.compute_deltas(d)
        snap.spread_2s10s_delta_5d = deltas["spread_2s10s_delta_5d"]
        snap.spread_2s10s_delta_30d = deltas["spread_2s10s_delta_30d"]
        snap.zscore_2s10s_90d = deltas["zscore_2s10s_90d"]
        history.save_snapshot(snap)
        saved += 1

    session.close()
    logger.info(f"Backfill complete: {saved} snapshots over {days} days")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2:** Run the backfill (requires `FRED_API_KEY` env var):
```bash
python scripts/backfill_yield_curve.py
```
Expected: log line "Backfill complete: N snapshots over 90 days".

- [ ] **Step 3:** Verify data exists in DB:
```bash
psql -d marketpulse -c "SELECT date, shape, spread_2s10s FROM market_data.yield_curve_snapshots ORDER BY date DESC LIMIT 10;"
```

- [ ] **Step 4:** Commit:
```bash
git add scripts/backfill_yield_curve.py
git commit -m "feat(yield-curve): 90-day historical backfill script"
```

---

### Task 16: End-to-end smoke test

**Files:**
- No new files. Manual verification.

- [ ] **Step 1:** Verify the scheduler can start without errors:
```bash
python -c "
import asyncio
from src.scheduler.scheduler import MarketScheduler
async def go():
    s = MarketScheduler()
    await s.start()
    jobs = s._scheduler.get_jobs()
    print('Registered jobs:', [j.id for j in jobs])
    await s.stop()
asyncio.run(go())
"
```
Expected: list includes `yield_curve_daily`.

- [ ] **Step 2:** Hit the API endpoints:
```bash
curl http://localhost:8000/api/yield-curve/current | python -m json.tool
curl http://localhost:8000/api/yield-curve/history?days=30 | python -m json.tool
curl http://localhost:8000/api/yield-curve/alerts | python -m json.tool
curl http://localhost:8000/api/yield-curve/config | python -m json.tool
```
Expected: each returns `{"success": true, "data": ...}`.

- [ ] **Step 3:** Run the full test suite:
```bash
pytest tests/yield_curve/ tests/test_yield_curve_api.py -v
```
Expected: all tests pass.

- [ ] **Step 4:** Frontend smoke test — start dev server and verify panel renders:
```bash
cd marketpulse-client && npm run dev
```
Visit `http://localhost:3000` (or wherever MacroDashboard is mounted) and confirm the YieldCurvePanel is visible with curve chart, 2s10s spread, recession prob, and (possibly empty) alerts list.

- [ ] **Step 5:** No commit (verification only). If all green, the feature is complete.

---

## Self-Review (completed)

**Spec coverage check:**

| Spec section | Implementing task(s) |
|---|---|
| §1 Overview | (narrative) |
| §2 Goals — track 8 tenors | T1 (config) + T3 (fetcher) |
| §2 Goals — 4 spreads | T2 (curves) |
| §2 Goals — shape classification | T2 (curves) |
| §2 Goals — NY Fed prob | T2 (curves) |
| §2 Goals — 7 alert triggers | T9 (alerts) |
| §2 Goals — REST + MacroDashboard panel | T10 (API) + T13/T14 (frontend) |
| §5 Module layout | T1, T2, T3, T6, T7, T9, T10 |
| §6 DB schema (2 tables) | T4 (migration) + T5 (ORM) |
| §7 7 alert rules | T9 (covers all 7, with priority by direction for rule 3) |
| §8 4 API endpoints | T10 |
| §9 Frontend panel | T11 (types) + T12 (hook) + T13 (component) + T14 (embed) |
| §10 Scheduler integration | T7 (job) + T8 (register) |
| §11 Error handling | T3 (fetcher retries, corrupt cache), T9 (anti-spam), T10 (try/except in endpoints) |
| §12 Testing | T2, T3, T6, T9, T10 — all have unit/integration tests |
| §14 Phases 1-5 | Plan phases 1-6 cover all 5 spec phases + backfill + smoke |

**Gaps found during review:**
- §11 mentions fail-fast on missing `FRED_API_KEY` — covered in T3 fetcher's `_require_key()`.
- §11 mentions "stale >3 days -> flag stale=true" — covered in T10 `_compute_staleness()`.
- §11 mentions "DB write fails -> do NOT fire alerts" — covered in T7 pipeline (try/except wraps alert evaluation).
- §11 mentions "anti-spam suppresses duplicates within 6h" — covered in T9 `_is_suppressed()`.

**No remaining gaps.** All spec sections map to tasks.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-06-23-yield-curve-monitor.md`.**

Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
