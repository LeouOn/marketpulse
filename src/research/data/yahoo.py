"""YahooProvider -- thin ``yfinance.download`` wrapper with caching + retry.

YahooProvider is for live fills and ETF proxies. For bulk historical macro
data (gold LBMA, oil spot, housing), use FredProvider. yfinance rate-limits
aggressively in 2026.

This provider implements the ``DataProvider`` ABC (see
``src/research/data/__init__.py``). It is NEVER the primary source for any
asset per the Metis A5 decision -- FRED is primary for macro; this exists
for live fills and for ETF/index proxies (e.g. GLD for gold, CL=F for oil)
that FRED cannot provide.

The ``MACRO_SYMBOLS`` class-level dict is a *copy* of the dict in
``src/api/yahoo_client.py`` (kept in place there for back-compat). If you
edit one, edit both -- ``tests/test_research_data_yahoo.py`` enforces
parity.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

from src.research.data import DataPipelineError, DataProvider

# Grace window (calendar days) applied to cache coverage checks. Daily macro
# data has weekends + holidays at boundaries, and yfinance's ``end`` is
# exclusive, so a strict ``cached_min <= start`` check would spuriously
# miss on otherwise-complete caches. 7 days covers any long-weekend gap.
_COVERAGE_GRACE_DAYS = 7


def _coerce_date(value: date | str) -> date:
    """Accept ``date``/``datetime`` or ISO ``"YYYY-MM-DD"`` string -> ``date``."""
    if isinstance(value, str):
        return date.fromisoformat(value)
    if isinstance(value, datetime):
        return value.date()
    return value


class YahooProvider(DataProvider):
    """``DataProvider`` backed by ``yfinance.download`` with parquet caching.

    DataFrame column contract (Metis)::

        ts (datetime64[ns, UTC]), open, high, low, close,
        volume, source (str: "yahoo:{ticker}")

    Rate-limit aware: ``yfinance.download`` is wrapped in a tenacity retry
    (exponential jitter, max 3 attempts). Final failure raises
    :class:`DataPipelineError` with a pointer to FredProvider.

    Args:
        cache_dir: Directory for ``{ticker}.parquet`` cache files. Created
            if it does not exist.
        cache_ttl_days: Max age (in days) of a cache file before it is
            considered stale and re-fetched.
        ticker: Default ticker used by :meth:`load_daily`. Defaults to
            ``"GLD"`` (gold ETF proxy).
    """

    # Lifted from ``src/api/yahoo_client.py`` YahooFinanceClient.macro_symbols.
    # DO NOT remove the original -- it stays for back-compat. This is a copy.
    # Parity is enforced by tests/test_research_data_yahoo.py.
    MACRO_SYMBOLS: dict[str, str] = {
        # Commodities & Indices
        "DXY": "UUP",  # US Dollar Index ETF
        "GC": "GLD",  # Gold ETF
        "CL": "CL=F",  # Crude Oil Futures (WTI) - Direct symbol
        "TNX": "^TNX",  # 10-Year Treasury Yield (^TNX)
        # Cryptocurrencies
        "BTC": "BTC-USD",  # Bitcoin
        "ETH": "ETH-USD",  # Ethereum
        "SOL": "SOL-USD",  # Solana
        "XRP": "XRP-USD",  # Ripple
        # Asian Markets
        "NIKKEI": "^N225",  # Nikkei 225 (Japan)
        "HSI": "^HSI",  # Hang Seng (Hong Kong)
        "SSE": "000001.SS",  # Shanghai Composite (China)
        "ASX": "^AXJO",  # ASX 200 (Australia)
        # European Markets
        "FTSE": "^FTSE",  # FTSE 100 (UK)
        "DAX": "^GDAXI",  # DAX (Germany)
        "CAC": "^FCHI",  # CAC 40 (France)
        "STOXX": "^STOXX50E",  # Euro Stoxx 50
        # Forex (Major Pairs)
        "EURUSD": "EURUSD=X",  # Euro / US Dollar
        "GBPUSD": "GBPUSD=X",  # British Pound / US Dollar
        "USDJPY": "USDJPY=X",  # US Dollar / Japanese Yen
        "AUDUSD": "AUDUSD=X",  # Australian Dollar / US Dollar
        "USDCAD": "USDCAD=X",  # US Dollar / Canadian Dollar
        "USDCHF": "USDCHF=X",  # US Dollar / Swiss Franc
    }

    def __init__(
        self,
        cache_dir: Path = Path("data/yahoo_cache"),
        cache_ttl_days: int = 1,
        ticker: str = "GLD",
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl_days = cache_ttl_days
        self.ticker = ticker

    # ------------------------------------------------------------------
    # DataProvider ABC
    # ------------------------------------------------------------------

    @property
    def trading_days_per_year(self) -> float:
        # Yahoo Finance follows the NYSE calendar.
        return 252.0

    def load_daily(self, start: date, end: date) -> pd.DataFrame:
        """Return daily OHLCV for the provider's default ``ticker``."""
        return self.fetch(self.ticker, start, end)

    # ------------------------------------------------------------------
    # Core fetch (cache-first, retry-wrapped)
    # ------------------------------------------------------------------

    def fetch(self, ticker: str, start: date | str, end: date | str) -> pd.DataFrame:
        """Fetch daily OHLCV for ``ticker`` over ``[start, end]`` (cache-first).

        Cache hit requires: file exists AND ``mtime + cache_ttl_days > now``
        AND the cached range covers ``[start, end]`` (with a small grace
        window for weekend/holiday boundaries). On miss, fetches via
        ``yfinance.download`` (retry on failure), maps to the Metis contract,
        drops NaN-close rows, persists, and returns the requested slice.

        ``start``/``end`` accept ``date`` or ISO ``"YYYY-MM-DD"`` strings.
        """
        start = _coerce_date(start)
        end = _coerce_date(end)
        cache_path = self.cache_dir / f"{ticker}.parquet"
        cached = self._read_cache(cache_path)
        if cached is not None and self._cache_is_fresh(cache_path) and self._cache_covers(cached, start, end):
            logger.debug(f"[yahoo] cache hit for {ticker} [{start}..{end}]")
            return self._slice(cached, start, end)

        logger.info(f"[yahoo] fetching {ticker} [{start}..{end}]")
        try:
            raw = self._download(ticker, start.isoformat(), end.isoformat())
        except Exception as exc:
            # Retry exhausted (or hard failure) -- surface a helpful error
            # pointing to FredProvider, per Metis A5 (FRED is primary).
            raise DataPipelineError(
                f"Yahoo Finance rate-limited or unreachable for {ticker}. "
                f"Try again later or use FredProvider for bulk historical data."
            ) from exc
        df = self._to_contract(raw, ticker)
        self._write_cache(df, cache_path)
        return self._slice(df, start, end)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(), reraise=True)
    def _download(self, ticker: str, start_iso: str, end_iso: str) -> pd.DataFrame:
        """Call ``yfinance.download`` with rate-limit retry.

        ``auto_adjust=False`` so the raw ``Close`` is returned (we map
        ``close`` <- ``Close``, NOT ``Adj Close``). The retry uses
        exponential jitter (default initial ~1s); tests patch ``time.sleep``
        to make retries instant.
        """
        return yfinance.download(
            ticker,
            start=start_iso,
            end=end_iso,
            progress=False,
            auto_adjust=False,
        )

    # ------------------------------------------------------------------
    # DataFrame mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _to_contract(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
        """Map a ``yfinance.download`` DataFrame to the Metis contract.

        Handles both flat columns (``Open, High, ...``) and the MultiIndex
        shape (``("Open", ticker), ...``) that yfinance 1.x returns by
        default for a single ticker. Uses ``Close`` (raw), not ``Adj Close``.
        Drops rows where close is NaN (weekends/holidays).
        """
        df = raw.copy()
        # Flatten MultiIndex columns to just the field-name level.
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # yfinance indexes the date as "Date" (or unnamed DatetimeIndex).
        date_col = df.index.name or "Date"
        df = df.reset_index().rename(columns={date_col: "ts"})

        # Localize naive dates to UTC (Metis contract: datetime64[ns, UTC]).
        ts = pd.to_datetime(df["ts"])
        if ts.dt.tz is None:
            ts = ts.dt.tz_localize("UTC")
        df["ts"] = ts

        df = df.rename(
            columns={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            }
        )

        # Drop NaN close (weekends/holidays yfinance pads with NaN).
        df = df.dropna(subset=["close"])

        # Ensure volume column exists (indices/forex may omit it).
        if "volume" not in df.columns:
            df["volume"] = float("nan")

        df["source"] = f"yahoo:{ticker}"
        return df[["ts", "open", "high", "low", "close", "volume", "source"]].reset_index(drop=True)

    # ------------------------------------------------------------------
    # Cache helpers (parquet)
    # ------------------------------------------------------------------

    def _read_cache(self, path: Path) -> pd.DataFrame | None:
        if not path.exists():
            return None
        try:
            return pd.read_parquet(path)
        except Exception as exc:  # corrupt parquet -> treat as miss
            logger.warning(f"[yahoo] corrupt cache {path}: {exc}; ignoring")
            return None

    def _write_cache(self, df: pd.DataFrame, path: Path) -> None:
        if df.empty:
            return
        # Atomic write: tmp then replace.
        tmp = path.with_suffix(path.suffix + ".tmp")
        df.to_parquet(tmp, index=False)
        tmp.replace(path)

    def _cache_is_fresh(self, path: Path) -> bool:
        if not path.exists():
            return False
        age_days = (time.time() - path.stat().st_mtime) / 86400.0
        return age_days < self.cache_ttl_days

    @staticmethod
    def _cache_covers(cached: pd.DataFrame, start: date, end: date) -> bool:
        if cached.empty:
            return False
        grace = timedelta(days=_COVERAGE_GRACE_DAYS)
        cached_min = pd.Timestamp(cached["ts"].min())
        cached_max = pd.Timestamp(cached["ts"].max())
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)
        # Normalize tz for comparison (drop to naive if either side is tz-aware).
        if cached_min.tz is not None:
            cached_min = cached_min.tz_convert(None)
            cached_max = cached_max.tz_convert(None)
        return (cached_min - grace) <= start_ts and (cached_max + grace) >= end_ts

    @staticmethod
    def _slice(df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
        """Return rows with ``start <= ts.date() <= end``."""
        ts = df["ts"]
        if ts.dt.tz is not None:
            ts = ts.dt.tz_convert(None)
        mask = (ts.dt.date >= start) & (ts.dt.date <= end)
        return df[mask].reset_index(drop=True)
