"""Bitcoin long-term OHLCV data pipeline (multi-tranche, multi-source).

Sources (in priority order, all free / no API key):

  - **Tranche 1 (daily, 2010-07-16 -> present)**: Yahoo Finance via yfinance.
    Single request returns the full daily history (~5,800+ bars).
  - **Tranche 2 (hourly, 2010-07-17 -> 2017-08-16)**: CryptoCompare histohour.
    Paginated, 2,000 rows per call. ~31 calls.
  - **Tranche 3 (hourly, 2017-08-17 -> present)**: Binance klines.
    Paginated, 1,000 rows per call. Exchange-verified, includes trade count.

The loader is **idempotent**: each run only fetches bars newer than the
last cached bar (or fills gaps). All network calls are wrapped in a
``tenacity`` retry with exponential backoff + jitter.

Output: local CSV at ``data/btc/{daily,hourly}.csv``.
"""

from __future__ import annotations

import csv
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd
import requests
import yfinance as yf
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

if TYPE_CHECKING:
    # Forward reference only -- avoids an import cycle at runtime.
    # Strategies (T16-T18) reference AssetConfig.cycle_strategy.
    from src.research.strategies import Strategy


# ---------------------------------------------------------------------------
# Multi-asset foundation: DataProvider ABC + AssetConfig + AssetRegistry (T2)
#
# Asset-class-agnostic public API. Concrete providers land in T6-T10
# (BTC, equities, gold, oil, housing). T10 populates ``AssetRegistry``.
# Spec: .omo/plans/multi-asset-macro-research-lab.md L290-362.
#
# IMPORTANT: do NOT move the existing BTC fetcher functions below into a
# ``btc`` submodule here -- T6 does that. This section is purely additive.
# ---------------------------------------------------------------------------


class DataProvider(ABC):
    """Asset-class-agnostic OHLCV data provider.

    DataFrame column contract (consumed by ``src.research.backtest``)::

        ts (datetime64[ns, UTC]), open, high, low, close,
        volume (NaN if unavailable), source (str)

    Subclasses MUST implement :meth:`load_daily` and
    :attr:`trading_days_per_year`. :meth:`load_monthly` and
    :meth:`load_intraday` have working defaults.
    """

    @abstractmethod
    def load_daily(self, start: date, end: date) -> pd.DataFrame:
        """Return daily OHLCV rows for ``[start, end]`` inclusive."""
        ...

    def load_monthly(self, start: date, end: date) -> pd.DataFrame:
        """Default: resample daily to month-end.

        Override for native monthly sources (e.g. Case-Shiller). Uses the
        pandas ``"ME"`` (month-end) anchor with standard OHLCV aggregation;
        months with no close row are dropped.
        """
        daily = self.load_daily(start, end)
        if daily.empty:
            return daily
        monthly = (
            daily.resample("ME", on="ts")
            .agg(
                {
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum",
                }
            )
            .dropna(subset=["close"])
        )
        return monthly.reset_index()

    def load_intraday(self, start: date, end: date) -> pd.DataFrame | None:
        """Optional. Return ``None`` if the asset has no intraday source."""
        return None

    @property
    @abstractmethod
    def trading_days_per_year(self) -> float:
        """Annualisation factor (365.25 crypto / 252 NYSE / 12 monthly)."""
        ...


@dataclass(frozen=True)
class AssetConfig:
    """Static configuration for one tradeable asset (Metis spec, T2).

    Frozen so registry entries are immutable at runtime. T10 populates
    the 5 assets (BTC, SP500-equivalent, XAU, DCOILWTICO, Case-Shiller).

    Field names are part of the public API -- downstream tasks read them
    directly (e.g. ``cfg.indicator_whitelist`` in T5, ``cfg.publication_lag_days``
    in T18, ``cfg.cycle_strategy`` in T16-T18, ``cfg.tradeable`` in T21).
    """

    ticker: str
    display_name: str
    asset_class: str  # "commodity" | "equity" | "realestate" | "crypto"
    calendar: str  # "247" | "NYSE" | "MONTHLY"
    trading_days_per_year: float  # 365.25 | 252 | 12
    data_provider: type  # DataProvider subclass
    cycle_strategy: type | None = None  # Strategy subclass; wired by T16-T18
    indicator_whitelist: tuple[str, ...] = ()
    default_regime_multipliers: dict = field(default_factory=dict)  # T10/T12
    publication_lag_days: int = 0
    tradeable: bool = True
    research_notes: str = ""


# AssetRegistry is populated at the BOTTOM of this module (T10) -- after the
# BTC fetchers (``load_daily`` / ``load_hourly``) are defined. The deferral is
# required because ``src.research.data.btc.BtcProvider`` imports those names
# from us, so building the registry at module-load time would otherwise hit an
# import cycle. See ``_build_asset_registry`` at end of file.
#
# Keys are the asset aliases used across the codebase: BTC, GOLD, OIL,
# EQUITIES, HOUSING.


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class DataPipelineError(RuntimeError):
    """Raised when a data fetch fails and no usable cache exists."""


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
SRC_BINANCE = "binance"
SRC_RECONCILED = "reconciled"

# Earliest BTC-USD date on Yahoo Finance (empirically: 2014-09-17).
# The earlier "2010-07-16" figure from yahoofinancials was wrong for
# BTC-USD specifically; yfinance returns 0 rows before 2014-09-17.
YAHOO_BTC_EARLIEST = "2014-09-17"
# Binance BTCUSDT trading started ~2017-08-17.
BINANCE_BTC_START = pd.Timestamp("2017-08-17", tz="UTC").tz_convert(None)

# CryptoCompare free hourly endpoint (requires free API key for >100 calls/day).
CRYPTOCOMPARE_URL = "https://min-api.cryptocompare.com/data/v2/histohour"
# Kraken public OHLC endpoint (used for T3 hourly). Kraken is preferred
# over Binance because api.binance.com is geo-blocked in many regions
# and api.binance.us only has BTCUSDT from 2020 onward. Kraken returns
# 1000 hourly bars per call, paginated via the ``since`` parameter.
KRAKEN_OHLC_URL = "https://api.kraken.com/0/public/OHLC"

# Optional CryptoCompare API key. When unset, T2 (CryptoCompare) will fail
# with a 401; T1 (Yahoo) and T3 (Kraken) still work. Set via env var:
#   export CRYPTOCOMPARE_API_KEY=your_key_here
import os as _os  # noqa: E402

CRYPTOCOMPARE_API_KEY: str = _os.getenv("CRYPTOCOMPARE_API_KEY", "")

# Network defaults.
REQ_TIMEOUT = 30
RETRY_ATTEMPTS = 4
RETRY_MIN_WAIT = 2
RETRY_MAX_WAIT = 60


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
# Retry-wrapped HTTP
# ---------------------------------------------------------------------------


def _is_retryable(exc: BaseException) -> bool:
    """Return True for transient errors we should retry."""
    if isinstance(exc, requests.HTTPError):
        return exc.response is not None and exc.response.status_code in (408, 429, 500, 502, 503, 504)
    if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
        return True
    return False


@retry(
    stop=stop_after_attempt(RETRY_ATTEMPTS),
    wait=wait_exponential_jitter(initial=RETRY_MIN_WAIT, max=RETRY_MAX_WAIT),
    retry=retry_if_exception_type((requests.HTTPError, requests.Timeout, requests.ConnectionError)),
    reraise=True,
)
def _http_get_json(url: str, params: dict | None = None, timeout: int = REQ_TIMEOUT) -> dict:
    """GET a URL and return JSON. Retries on transient errors."""
    r = requests.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()


@retry(
    stop=stop_after_attempt(RETRY_ATTEMPTS),
    wait=wait_exponential_jitter(initial=RETRY_MIN_WAIT, max=RETRY_MAX_WAIT),
    retry=retry_if_exception_type((requests.HTTPError, requests.Timeout, requests.ConnectionError)),
    reraise=True,
)
def _http_get_data_list(
    url: str,
    params: dict | None = None,
    headers: dict | None = None,
    timeout: int = REQ_TIMEOUT,
) -> list | None:
    """GET a URL; on success return the data list, on non-Success return None.

    Handles both shapes:
      - {"Data": [list of bars]}            (flat)
      - {"Data": {"Data": [list of bars]}}  (CryptoCompare nested)

    CryptoCompare's "silent 200 with non-Success body" failure mode is
    turned into a rate-limit HTTPError so tenacity retries.
    """
    r = requests.get(url, params=params, headers=headers, timeout=timeout)
    r.raise_for_status()
    payload = r.json()
    if not isinstance(payload, dict):
        return None
    if payload.get("Response") not in (None, "Success"):
        msg = (payload.get("Message") or "").lower()
        if "rate limit" in msg:
            raise requests.HTTPError(f"Rate limit: {payload.get('Message')}")
        return None
    data = payload.get("Data")
    if isinstance(data, dict):
        # CryptoCompare nests: Data.Data = [list]
        data = data.get("Data")
    return data


# ---------------------------------------------------------------------------
# CSV cache helpers
# ---------------------------------------------------------------------------


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _read_cache(path: Path) -> pd.DataFrame:
    """Read a cached CSV. Empty DataFrame if file is missing or corrupt."""
    if not path.exists():
        return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume", "source"])
    try:
        df = pd.read_csv(path, parse_dates=["ts"])
    except Exception as exc:
        logger.warning(f"Corrupt CSV cache {path}: {exc}; returning empty DataFrame")
        return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume", "source"])
    df = df.drop_duplicates(subset=["ts"]).sort_values("ts").reset_index(drop=True)
    return df


def _write_cache(df: pd.DataFrame, path: Path) -> None:
    """Write the cache atomically (write to .tmp, then replace)."""
    _ensure_data_dir()
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp, index=False, quoting=csv.QUOTE_MINIMAL)
    tmp.replace(path)


def _merge(new: pd.DataFrame, existing: pd.DataFrame) -> pd.DataFrame:
    """Combine new bars with existing cache, dedupe by ts, sort.

    On conflict (same ts in both), the new row wins.
    """
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


def fetch_daily_yahoo(
    start: str = YAHOO_BTC_EARLIEST,
    end: str | None = None,
) -> pd.DataFrame:
    """Fetch daily BTC-USD from Yahoo Finance. Single request, no pagination.

    Note: Yahoo Finance's BTC-USD data starts on 2010-07-16 (the earliest
    trade date for BTC-USD on Yahoo). For dates before that, the response
    is empty. We default to that start so callers don't request 2010-01-01
    and get a 5,800+ row history that "looks" complete but is actually
    missing the first half-year of BTC's existence on Yahoo.
    """
    logger.info(f"[T1] Fetching daily BTC-USD from Yahoo ({start} -> {end or 'today'})")
    ticker = yf.Ticker("BTC-USD")
    df = ticker.history(start=start, end=end, interval="1d", auto_adjust=False)
    if df.empty:
        return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume", "source"])

    df = df.reset_index()
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
    logger.info(f"[T1] Yahoo returned {len(df)} daily bars ({df['ts'].min().date()} -> {df['ts'].max().date()})")
    return df


def fetch_hourly_cryptocompare(
    start_ts: int | None = None,
    end_ts: int | None = None,
    symbol: str = "BTC",
    tsym: str = "USD",
) -> pd.DataFrame:
    """Fetch hourly BTC-USD from CryptoCompare (paginated 2000 rows/call).

    Used for **Tranche 2**: hourly history from 2010-07-17 to 2017-08-16,
    the only era where Binance doesn't have data.
    """
    if end_ts is None:
        end_ts = int(time.time())
    if start_ts is None:
        start_ts = int(datetime(2010, 7, 17, tzinfo=timezone.utc).timestamp())

    rows: list[dict] = []
    cursor = end_ts
    pages = 0
    logger.info(
        f"[T2] Fetching hourly BTC-USD from CryptoCompare (>= {datetime.fromtimestamp(start_ts, tz=timezone.utc).date()})"
    )
    headers = {}
    if CRYPTOCOMPARE_API_KEY:
        headers["authorization"] = f"Bearer {CRYPTOCOMPARE_API_KEY}"
    while cursor > start_ts and pages < 50:  # 50 * 2000 = 100k hours ~ 11 years
        data = _http_get_data_list(
            CRYPTOCOMPARE_URL,
            params={"fsym": symbol, "tsym": tsym, "limit": 2000, "toTs": cursor},
            headers=headers or None,
        )
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
                    "volume": float(d.get("volumeto", 0.0)),  # USD volume for consistency
                    "source": SRC_CRYPTOCOMPARE,
                }
            )

        cursor = int(data[0]["time"])
        pages += 1

    if not rows:
        logger.info(f"[T2] CryptoCompare returned 0 hourly bars (no data or auth required)")
        return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume", "source"])
    df = pd.DataFrame(rows).drop_duplicates(subset=["ts"]).sort_values("ts").reset_index(drop=True)
    logger.info(f"[T2] CryptoCompare returned {len(df)} hourly bars across {pages} pages")
    return df


def fetch_hourly_kraken(
    start_ts: int | None = None,
    end_ts: int | None = None,
    pair: str = "XBTUSD",
) -> pd.DataFrame:
    """Fetch hourly XBT-USD from Kraken's public OHLC API.

    Used for **Tranche 3**: hourly history. Kraken is preferred over
    Binance because (a) Binance.com is geo-blocked in many regions
    and (b) Binance.us only has BTCUSDT from 2020+.

    **Caveat**: Kraken's free OHLC endpoint returns at most the most
    recent 720 hourly bars (~30 days) per call. Going further back
    requires a paid tier or another source. We respect that limit:
    if the start_ts requested is older than what's available, we just
    return whatever Kraken gives us (the most recent 720 hours).

    Returns volume in USD (XBT volume * close as a proxy).
    """
    if end_ts is None:
        end_ts = int(time.time())
    if start_ts is None:
        start_ts = int(BINANCE_BTC_START.tz_localize("UTC").timestamp())

    logger.info(
        f"[T3] Fetching hourly XBT-USD from Kraken (requesting >= {datetime.fromtimestamp(start_ts, tz=timezone.utc).date()})"
    )
    try:
        payload = _http_get_json(
            KRAKEN_OHLC_URL, params={"pair": pair, "interval": 60, "since": start_ts}
        )
    except Exception as e:
        logger.warning(f"[T3] Kraken fetch failed: {e}")
        return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume", "source"])

    if not payload or payload.get("error"):
        if payload and payload.get("error"):
            logger.warning(f"[T3] Kraken error: {payload['error']}")
        return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume", "source"])

    result = payload.get("result", {})
    bars = result.get("XXBTZUSD") or result.get(pair) or []
    if not bars:
        return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume", "source"])

    rows: list[dict] = []
    for d in bars:
        # d = [time, open, high, low, close, vwap, volume, count]
        rows.append(
            {
                "ts": pd.Timestamp(int(d[0]), unit="s", tz="UTC").tz_convert(None),
                "open": float(d[1]),
                "high": float(d[2]),
                "low": float(d[3]),
                "close": float(d[4]),
                "volume": float(d[6]) * float(d[4]),  # XBT volume * close ~= USD volume
                "source": SRC_BINANCE,  # legacy name; means "exchange-sourced"
            }
        )

    df = pd.DataFrame(rows).drop_duplicates(subset=["ts"]).sort_values("ts").reset_index(drop=True)
    logger.info(
        f"[T3] Kraken returned {len(df)} hourly bars "
        f"({df['ts'].min().date()} -> {df['ts'].max().date()})"
    )
    return df


# Legacy alias for back-compat with tests; the name "binance" is kept
# in the source column for provenance continuity.
fetch_hourly_binance = fetch_hourly_kraken


# ---------------------------------------------------------------------------
# Tranche orchestration
# ---------------------------------------------------------------------------


@dataclass
class TrancheResult:
    """Outcome of a single data tranche fetch."""

    name: str
    source: str
    rows_fetched: int
    rows_added: int
    start: str | None
    end: str | None
    error: str | None = None


def _run_tranche(
    name: str,
    source: str,
    fetcher,
    existing: pd.DataFrame,
    cache_path: Path,
) -> TrancheResult:
    """Run a single tranche, merge with existing cache, persist."""
    try:
        new = fetcher()
    except Exception as e:
        logger.error(f"[{name}] Failed: {e}")
        return TrancheResult(
            name=name, source=source, rows_fetched=0, rows_added=0, start=None, end=None, error=str(e)
        )

    if new.empty:
        return TrancheResult(
            name=name, source=source, rows_fetched=0, rows_added=0, start=None, end=None
        )

    # Incremental: only keep new rows whose ts is strictly newer than existing
    if not existing.empty and not new.empty:
        last_existing_ts = existing["ts"].max()
        new_only = new[new["ts"] > last_existing_ts]
        if len(new_only) < len(new):
            logger.info(
                f"[{name}] Filtered to {len(new_only)} new bars (older ones already cached)"
            )
            new = new_only

    merged = _merge(new, existing)
    added = len(merged) - len(existing)
    _write_cache(merged, cache_path)

    return TrancheResult(
        name=name,
        source=source,
        rows_fetched=int(len(new)),
        rows_added=int(added),
        start=str(new["ts"].min().date()) if not new.empty else None,
        end=str(new["ts"].max().date()) if not new.empty else None,
    )


def update_cache(
    tranches: list[str] | None = None,
    daily: bool = True,
    hourly: bool = True,
) -> dict:
    """Run the multi-tranche BTC data acquisition pipeline.

    Args:
        tranches: optional list of tranche names to run. Default is
            all of ``["t1_daily_yahoo", "t2_hourly_cc", "t3_hourly_binance"]``.
        daily: run the daily (T1) tranche.
        hourly: run the hourly tranches (T2, T3).

    Returns a summary dict with per-tranche results.
    """
    if tranches is None:
        tranches = []
        if daily:
            tranches.append("t1_daily_yahoo")
        if hourly:
            tranches.extend(["t2_hourly_cc", "t3_hourly_binance"])

    logger.info(f"=== Multi-tranche BTC data update starting: {tranches} ===")
    _ensure_data_dir()
    summary: dict = {"tranches": [], "started_at": pd.Timestamp.now("UTC").isoformat()}

    daily_existing = _read_cache(DAILY_CSV) if "t1_daily_yahoo" in tranches else pd.DataFrame()
    hourly_existing = _read_cache(HOURLY_CSV) if any(
        t.startswith("t2") or t.startswith("t3") for t in tranches
    ) else pd.DataFrame()

    if "t1_daily_yahoo" in tranches:
        result = _run_tranche(
            "T1",
            SRC_YAHOO,
            lambda start=YAHOO_BTC_EARLIEST: fetch_daily_yahoo(start=start),
            daily_existing,
            DAILY_CSV,
        )
        summary["tranches"].append(_result_to_dict(result))
        daily_existing = _read_cache(DAILY_CSV)

    if "t2_hourly_cc" in tranches:
        end_ts_t2 = int(BINANCE_BTC_START.tz_localize("UTC").timestamp()) - 1
        result = _run_tranche(
            "T2",
            SRC_CRYPTOCOMPARE,
            lambda end_ts=end_ts_t2: fetch_hourly_cryptocompare(end_ts=end_ts),
            hourly_existing,
            HOURLY_CSV,
        )
        summary["tranches"].append(_result_to_dict(result))
        hourly_existing = _read_cache(HOURLY_CSV)

    if "t3_hourly_binance" in tranches:
        result = _run_tranche(
            "T3",
            SRC_BINANCE,
            lambda: fetch_hourly_kraken(),
            hourly_existing,
            HOURLY_CSV,
        )
        summary["tranches"].append(_result_to_dict(result))
        hourly_existing = _read_cache(HOURLY_CSV)

    summary["ended_at"] = pd.Timestamp.now("UTC").isoformat()
    summary["daily_total"] = int(len(_read_cache(DAILY_CSV)))
    summary["hourly_total"] = int(len(_read_cache(HOURLY_CSV)))
    logger.info(
        f"=== Update complete: {summary['daily_total']} daily bars, {summary['hourly_total']} hourly bars ==="
    )
    return summary


def _result_to_dict(r: TrancheResult) -> dict:
    return {
        "name": r.name,
        "source": r.source,
        "rows_fetched": r.rows_fetched,
        "rows_added": r.rows_added,
        "start": r.start,
        "end": r.end,
        "error": r.error,
    }


# ---------------------------------------------------------------------------
# Public loaders (cache-first)
# ---------------------------------------------------------------------------


def load_daily(
    start: str | None = None, end: str | None = None, force_refresh: bool = False
) -> pd.DataFrame:
    """Return the daily BTC-USD DataFrame, fetching from Yahoo if cache is stale.

    Raises:
        DataPipelineError: If the fetch fails and no usable cache exists.
    """
    if force_refresh or not DAILY_CSV.exists():
        try:
            new = fetch_daily_yahoo()
        except Exception as exc:
            # Fetch failed — check if we have a usable cache to fall back on
            existing = _read_cache(DAILY_CSV)
            if existing.empty:
                raise DataPipelineError(
                    f"Daily BTC-USD fetch failed and no cache exists: {exc}"
                ) from exc
            logger.warning(f"Daily fetch failed; falling back to stale cache ({len(existing)} rows): {exc}")
            merged = existing
        else:
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
                    str(merged["ts"].max().date()) if not merged.empty else YAHOO_BTC_EARLIEST
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
    """Return the hourly BTC-USD DataFrame, fetching as needed.

    Raises:
        DataPipelineError: If the fetch fails and no usable cache exists.
    """
    if force_refresh or not HOURLY_CSV.exists():
        try:
            summary = update_cache(daily=False, hourly=True)
            logger.info(f"Initial hourly fetch summary: {summary}")
        except Exception as exc:
            # Fetch failed — check if we have a usable cache to fall back on
            existing = _read_cache(HOURLY_CSV)
            if existing.empty:
                raise DataPipelineError(
                    f"Hourly BTC-USD fetch failed and no cache exists: {exc}"
                ) from exc
            logger.warning(f"Hourly fetch failed; falling back to stale cache ({len(existing)} rows): {exc}")
    else:
        merged = _read_cache(HOURLY_CSV)
        if merged.empty or (
            pd.Timestamp.now("UTC").tz_convert(None) - merged["ts"].max()
        ) > pd.Timedelta(hours=2):
            try:
                # Re-run T3 only (the live tranche) for incremental updates
                summary = update_cache(tranches=["t3_hourly_binance"])
                logger.info(f"Hourly incremental update: {summary}")
            except Exception as e:
                logger.warning(f"Hourly auto-refresh failed; using stale cache: {e}")

    merged = _read_cache(HOURLY_CSV)
    if start is not None:
        merged = merged[merged["ts"] >= pd.Timestamp(start)]
    if end is not None:
        merged = merged[merged["ts"] <= pd.Timestamp(end)]
    return merged.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Summary helpers
# ---------------------------------------------------------------------------


def _cagr(start: float, end: float, years: float) -> float:
    if years <= 0 or start <= 0 or end <= 0:
        return 0.0
    return (end / start) ** (1.0 / years) - 1.0


def _max_drawdown(close: pd.Series) -> float:
    """Return the max drawdown as a *negative* fraction (e.g. -0.83 for 83%)."""
    if close.empty:
        return 0.0
    running_max = close.cummax()
    drawdown = close / running_max - 1.0
    return float(drawdown.min())


def data_summary(df: pd.DataFrame, trading_days_per_year: float = 365.25) -> dict:
    """Return a structured summary of a price dataframe (used by LLM tools).

    ``trading_days_per_year`` controls the sqrt-N annualization of per-bar vol.
    Default 365.25 = BTC daily cadence. Use 12 for monthly housing, 252 for equities.
    """
    if df.empty:
        return {"rows": 0}
    close = df["close"].astype(float)
    rets = close.pct_change().dropna()
    years = (df["ts"].iloc[-1] - df["ts"].iloc[0]).days / 365.25
    return {
        "rows": int(len(df)),
        "start": str(df["ts"].min().date()),
        "end": str(df["ts"].max().date()),
        "first_close": float(close.iloc[0]),
        "last_close": float(close.iloc[-1]),
        "total_return_pct": float((close.iloc[-1] / close.iloc[0] - 1.0) * 100.0),
        "cagr_pct": float(_cagr(close.iloc[0], close.iloc[-1], years) * 100.0),
        "realized_vol_annual_pct": float(rets.std() * (trading_days_per_year**0.5) * 100.0)
        if len(rets) > 1
        else 0.0,
        "max_drawdown_pct": float(_max_drawdown(close) * 100.0),
        "best_day_pct": float(rets.max() * 100.0) if len(rets) else 0.0,
        "worst_day_pct": float(rets.min() * 100.0) if len(rets) else 0.0,
        "sources": sorted(df["source"].unique().tolist()) if "source" in df.columns else [],
    }


# ---------------------------------------------------------------------------
# AssetRegistry population (T10)
#
# Deferred to end-of-module so all of BtcProvider / FredProvider /
# AlpacaProvider and the local BTC fetchers (load_daily / load_hourly) are
# fully defined. Building the registry at module top would hit an import
# cycle: src.research.data.btc imports load_daily/load_hourly from us.
#
# Cycle-safe ordering:
#   1. __init__.py finishes defining DataProvider, AssetConfig, load_daily,
#      load_hourly, data_summary, etc.
#   2. _build_asset_registry() is called.
#   3. Inside it, ``from src.research.data.btc import BtcProvider`` runs.
#      That module's top-level ``from src.research.data import DataProvider,
#      load_daily, load_hourly`` re-binds this (already fully loaded) module
#      without re-executing it -- so the cycle resolves cleanly.
#
# T16-T18 will later wire ``cycle_strategy`` to concrete Strategy subclasses;
# until then the placeholder is ``None`` (the AssetConfig default).
# ---------------------------------------------------------------------------


def _build_asset_registry() -> "dict[str, AssetConfig]":
    """Build the populated asset registry with deferred provider imports.

    Returns the 5-entry registry used across the research lab. Kept as a
    function (not a module-level literal) so the provider imports stay lazy
    and break the ``data/__init__.py`` <-> ``data/btc.py`` cycle.
    """
    from src.research.data.alpaca import AlpacaProvider
    from src.research.data.btc import BtcProvider
    from src.research.data.fred import FredProvider

    return {
        "BTC": AssetConfig(
            ticker="BTC-USD",
            display_name="Bitcoin",
            asset_class="crypto",
            calendar="247",
            trading_days_per_year=365.25,
            data_provider=BtcProvider,
            cycle_strategy=None,  # T16 wires HalvingCycleAccumulation
            indicator_whitelist=("rsi", "mayer", "fgi", "mvrv"),
            default_regime_multipliers={},  # tuned after W3 backrun validation
            publication_lag_days=0,
            tradeable=True,
            research_notes="",
        ),
        "GOLD": AssetConfig(
            ticker="GOLDAMGBD228NLBM",
            display_name="Gold (LBMA AM fix)",
            asset_class="commodity",
            calendar="NYSE",
            trading_days_per_year=252,
            data_provider=FredProvider,
            cycle_strategy=None,  # T16 wires RealRateCycleAccumulation
            indicator_whitelist=("rsi", "mayer"),
            default_regime_multipliers={},
            publication_lag_days=0,
            tradeable=True,
            research_notes="",
        ),
        "OIL": AssetConfig(
            ticker="DCOILWTICO",
            display_name="WTI Crude Oil (spot)",
            asset_class="commodity",
            calendar="NYSE",
            trading_days_per_year=252,
            data_provider=FredProvider,
            cycle_strategy=None,  # T17 wires OPECCycleAccumulation
            indicator_whitelist=("rsi", "mayer"),
            default_regime_multipliers={},
            publication_lag_days=0,
            tradeable=False,  # Metis EC3: spot index, not a tradeable instrument
            research_notes=(
                "Spot price index, not a tradeable instrument. "
                "Use for accumulation-style analysis only. "
                "Values can be negative (April 2020 -$37.63) -- pass through as-is."
            ),
        ),
        "EQUITIES": AssetConfig(
            ticker="SPY",
            display_name="US Broad Equities (S&P 500 via SPY)",
            asset_class="equity",
            calendar="NYSE",
            trading_days_per_year=252,
            data_provider=AlpacaProvider,
            cycle_strategy=None,  # T17 wires EarningsCycleAccumulation
            indicator_whitelist=("rsi", "mayer"),
            default_regime_multipliers={},
            publication_lag_days=0,
            tradeable=True,
            research_notes="",
        ),
        "HOUSING": AssetConfig(
            ticker="CSUSHPINSA",
            display_name="US Housing (Case-Shiller National)",
            asset_class="realestate",
            calendar="MONTHLY",
            trading_days_per_year=12,
            data_provider=FredProvider,
            cycle_strategy=None,  # T18 wires MortgageCycleAccumulation
            indicator_whitelist=("rsi", "mayer"),
            default_regime_multipliers={},
            publication_lag_days=60,  # Metis: Case-Shiller ~2-month publication lag
            tradeable=True,
            research_notes=(
                "Monthly cadence. NSA series (not seasonally adjusted) -- "
                "seasonal patterns present."
            ),
        ),
    }


# Keys: "BTC", "GOLD", "OIL", "EQUITIES", "HOUSING". Built once at import.
AssetRegistry: dict[str, AssetConfig] = _build_asset_registry()
