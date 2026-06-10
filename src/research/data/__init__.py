"""Bitcoin long-term OHLCV data pipeline.

Sources (in priority order, all free / no API key):
  1. Local CSV cache at ``data/btc/{daily,hourly}.csv`` (idempotent loader)
  2. Yahoo Finance via yfinance for daily (BTC-USD, 2010+)
  3. CryptoCompare public API for hourly (no key, paginated 2000 rows/call)

The loader is **idempotent**: running it again fills in only the missing rows
beyond what's already in the cache. CSVs are human-readable so a researcher can
inspect and edit them. (We chose CSV over Parquet because pyarrow is not in
requirements-lite.txt; CSV is plenty fast for these dataset sizes.)
"""

from __future__ import annotations

import csv
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from loguru import logger

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

DATA_DIR = Path("data/btc")
DAILY_CSV = DATA_DIR / "daily.csv"
HOURLY_CSV = DATA_DIR / "hourly.csv"

# Source-of-record labels stored in CSV ``source`` column.
SRC_LOCAL = "local"
SRC_YAHOO = "yahoo"
SRC_CRYPTOCOMPARE = "cryptocompare"

# CryptoCompare free hourly endpoint.
CRYPTOCOMPARE_URL = "https://min-api.cryptocompare.com/data/v2/histohour"


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BTCBar:
    ts: pd.Timestamp  # UTC
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str


# ---------------------------------------------------------------------------
# CSV cache helpers
# ---------------------------------------------------------------------------


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _read_cache(path: Path) -> pd.DataFrame:
    """Read a cached CSV. Empty DataFrame if file is missing."""
    if not path.exists():
        return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume", "source"])
    df = pd.read_csv(path, parse_dates=["ts"])
    df = df.drop_duplicates(subset=["ts"]).sort_values("ts").reset_index(drop=True)
    return df


def _write_cache(df: pd.DataFrame, path: Path) -> None:
    """Write the cache atomically (write to .tmp, then replace)."""
    _ensure_data_dir()
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp, index=False, quoting=csv.QUOTE_MINIMAL)
    tmp.replace(path)


def _merge(new: pd.DataFrame, existing: pd.DataFrame) -> pd.DataFrame:
    """Combine new bars with existing cache, dedupe by ts, sort."""
    if existing.empty:
        combined = new.copy()
    elif new.empty:
        combined = existing.copy()
    else:
        combined = pd.concat([existing, new], ignore_index=True)
    combined = combined.drop_duplicates(subset=["ts"], keep="last")
    combined = combined.sort_values("ts").reset_index(drop=True)
    return combined


# ---------------------------------------------------------------------------
# Source fetchers
# ---------------------------------------------------------------------------


def fetch_daily_yahoo(start: str = "2010-01-01", end: str | None = None) -> pd.DataFrame:
    """Fetch daily BTC-USD from Yahoo Finance."""
    import yfinance as yf

    logger.info(f"Fetching daily BTC-USD from Yahoo Finance ({start} -> {end or 'today'})")
    ticker = yf.Ticker("BTC-USD")
    df = ticker.history(start=start, end=end, interval="1d", auto_adjust=False)
    if df.empty:
        return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume", "source"])

    df = df.reset_index()
    # yfinance returns the date column as "Date" or "index" depending on version
    date_col = "Date" if "Date" in df.columns else df.columns[0]
    df = df.rename(
        columns={
            date_col: "ts",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    )
    df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(None)
    df["source"] = SRC_YAHOO
    df = df[["ts", "open", "high", "low", "close", "volume", "source"]]
    df = df.dropna(subset=["open", "high", "low", "close"])
    return df


def fetch_hourly_cryptocompare(start_ts: int | None = None, end_ts: int | None = None) -> pd.DataFrame:
    """Fetch hourly BTC-USD from CryptoCompare.

    The free endpoint paginates 2000 rows per call. We walk backwards from
    ``end_ts`` (defaults to ``now``) collecting 2000 rows at a time until we
    reach ``start_ts`` (defaults to 2018-01-01).
    """
    if end_ts is None:
        end_ts = int(time.time())
    if start_ts is None:
        start_ts = int(datetime(2018, 1, 1, tzinfo=timezone.utc).timestamp())

    rows: list[dict] = []
    cursor = end_ts
    pages = 0
    logger.info(
        f"Fetching hourly BTC-USD from CryptoCompare (>= {datetime.fromtimestamp(start_ts, tz=timezone.utc).date()})"
    )
    while cursor > start_ts and pages < 50:  # 50 pages * 2000 = 100k hours ~ 11 years
        params = {
            "fsym": "BTC",
            "tsym": "USD",
            "limit": 2000,
            "toTs": cursor,
        }
        try:
            r = requests.get(CRYPTOCOMPARE_URL, params=params, timeout=30)
            r.raise_for_status()
            payload = r.json()
        except Exception as e:
            logger.warning(f"CryptoCompare page {pages} failed: {e}")
            break

        if payload.get("Response") != "Success":
            logger.warning(
                f"CryptoCompare page {pages} returned non-Success: {payload.get('Message')}"
            )
            break

        data = payload.get("Data", {}).get("Data", [])
        if not data:
            break

        for d in data:
            ts = d.get("time")
            if ts is None or ts < start_ts:
                continue
            rows.append(
                {
                    "ts": pd.Timestamp(ts, unit="s", tz="UTC").tz_convert(None),
                    "open": float(d.get("open", 0.0)),
                    "high": float(d.get("high", 0.0)),
                    "low": float(d.get("low", 0.0)),
                    "close": float(d.get("close", 0.0)),
                    "volume": float(d.get("volumefrom", 0.0)),
                    "source": SRC_CRYPTOCOMPARE,
                }
            )

        cursor = int(data[0]["time"])  # earliest ts on this page
        pages += 1

    df = pd.DataFrame(rows).drop_duplicates(subset=["ts"]).sort_values("ts").reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Public loaders (cache-first, source-fill)
# ---------------------------------------------------------------------------


def load_daily(
    start: str | None = None, end: str | None = None, force_refresh: bool = False
) -> pd.DataFrame:
    """Return the daily BTC-USD DataFrame, fetching from Yahoo if cache is stale."""
    if force_refresh or not DAILY_CSV.exists():
        new = fetch_daily_yahoo()
        existing = pd.DataFrame() if force_refresh else _read_cache(DAILY_CSV)
        merged = _merge(new, existing)
        _write_cache(merged, DAILY_CSV)
    else:
        merged = _read_cache(DAILY_CSV)
        if merged.empty or (
            pd.Timestamp.now("UTC").tz_convert(None) - merged["ts"].max()
        ) > pd.Timedelta(days=1):
            try:
                fetch_start = (
                    str(merged["ts"].max().date()) if not merged.empty else "2010-01-01"
                )
                new = fetch_daily_yahoo(start=fetch_start)
                merged = _merge(new, merged)
                _write_cache(merged, DAILY_CSV)
            except Exception as e:
                logger.warning(f"Daily auto-refresh failed; using stale cache: {e}")

    if start is not None:
        merged = merged[merged["ts"] >= pd.Timestamp(start)]
    if end is not None:
        merged = merged[merged["ts"] <= pd.Timestamp(end)]
    return merged.reset_index(drop=True)


def load_hourly(
    start: str | None = None, end: str | None = None, force_refresh: bool = False
) -> pd.DataFrame:
    """Return the hourly BTC-USD DataFrame, fetching from CryptoCompare if needed."""
    if force_refresh or not HOURLY_CSV.exists():
        new = fetch_hourly_cryptocompare()
        existing = pd.DataFrame() if force_refresh else _read_cache(HOURLY_CSV)
        merged = _merge(new, existing)
        _write_cache(merged, HOURLY_CSV)
    else:
        merged = _read_cache(HOURLY_CSV)
        if merged.empty or (
            pd.Timestamp.now("UTC").tz_convert(None) - merged["ts"].max()
        ) > pd.Timedelta(hours=2):
            try:
                end_ts = int(time.time())
                start_ts = int(merged["ts"].max().timestamp()) if not merged.empty else None
                new = fetch_hourly_cryptocompare(end_ts=end_ts, start_ts=start_ts)
                merged = _merge(new, merged)
                _write_cache(merged, HOURLY_CSV)
            except Exception as e:
                logger.warning(f"Hourly auto-refresh failed; using stale cache: {e}")

    if start is not None:
        merged = merged[merged["ts"] >= pd.Timestamp(start)]
    if end is not None:
        merged = merged[merged["ts"] <= pd.Timestamp(end)]
    return merged.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Summary helpers (used by the LLM tools)
# ---------------------------------------------------------------------------


def _cagr(start: float, end: float, years: float) -> float:
    if years <= 0 or start <= 0:
        return 0.0
    return (end / start) ** (1.0 / years) - 1.0


def _max_drawdown(close: pd.Series) -> float:
    """Return the max drawdown as a *negative* fraction (e.g. -0.83 for 83%)."""
    if close.empty:
        return 0.0
    running_max = close.cummax()
    drawdown = close / running_max - 1.0
    return float(drawdown.min())


def data_summary(df: pd.DataFrame) -> dict:
    """Return a structured summary of a price dataframe (used by LLM tools)."""
    if df.empty:
        return {"rows": 0}
    close = df["close"].astype(float)
    rets = close.pct_change().dropna()
    return {
        "rows": int(len(df)),
        "start": str(df["ts"].min().date()),
        "end": str(df["ts"].max().date()),
        "first_close": float(close.iloc[0]),
        "last_close": float(close.iloc[-1]),
        "total_return_pct": float((close.iloc[-1] / close.iloc[0] - 1.0) * 100.0),
        "cagr_pct": float(
            _cagr(
                close.iloc[0],
                close.iloc[-1],
                (df["ts"].iloc[-1] - df["ts"].iloc[0]).days / 365.25,
            )
        ),
        "realized_vol_annual_pct": float(rets.std() * (365.25**0.5) * 100.0)
        if len(rets) > 1
        else 0.0,
        "max_drawdown_pct": float(_max_drawdown(close) * 100.0),
        "best_day_pct": float(rets.max() * 100.0) if len(rets) else 0.0,
        "worst_day_pct": float(rets.min() * 100.0) if len(rets) else 0.0,
    }


# ---------------------------------------------------------------------------
# Cache refresh helper (used by the research CLI)
# ---------------------------------------------------------------------------


def update_cache() -> dict:
    """Refresh both daily and hourly caches. Returns counts of new rows added."""
    existing_daily = _read_cache(DAILY_CSV)
    existing_hourly = _read_cache(HOURLY_CSV)
    new_daily = fetch_daily_yahoo()
    new_hourly = fetch_hourly_cryptocompare()
    daily_merged = _merge(new_daily, existing_daily)
    hourly_merged = _merge(new_hourly, existing_hourly)
    daily_added = len(daily_merged) - len(existing_daily)
    hourly_added = len(hourly_merged) - len(existing_hourly)
    _write_cache(daily_merged, DAILY_CSV)
    _write_cache(hourly_merged, HOURLY_CSV)
    return {
        "daily_total": len(daily_merged),
        "daily_added": daily_added,
        "hourly_total": len(hourly_merged),
        "hourly_added": hourly_added,
    }
