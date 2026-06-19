"""FRED (Federal Reserve Economic Data) provider with parquet caching.

Implements :class:`src.research.data.DataProvider` for the 13 FRED series
locked down by Metis SC4 (gold AM/PM, WTI spot, Case-Shiller, real/nominal
yields, breakevens, trade-weighted USD, VIX, Fed Funds, unemployment, CPI,
30Y mortgage). Any other series id is rejected at :meth:`FredProvider.fetch`.

Design notes
------------

* **Cache**: each series is cached as a single parquet file at
  ``cache_dir / f"{series_id}.parquet"``. A cache file that *covers* the
  requested ``[start, end]`` range is served without an API call
  (Metis EC9: "never re-fetch if cache is fresh"). Otherwise the full
  requested range is fetched and the cache file is overwritten.
* **Staleness**: after a fresh fetch, if the query is "current"
  (``end`` within ``max_staleness_days`` of today) the most recent
  observation is checked against ``max_staleness_days``; older source
  data raises :class:`DataPipelineError`. Historical queries
  (``end`` well in the past) are exempt -- old data is *expected* to be old.
* **Negative prices**: WTI spot (``DCOILWTICO``) went to -$37.63 on
  2020-04-20. Values are passed through verbatim; Metis EC3 explicitly
  forbids skipping them.
* **Retry**: transient ``requests.ConnectionError`` / ``requests.HTTPError``
  are retried with exponential backoff + jitter via ``tenacity``. The
  retry config is held on public instance attributes so tests can zero
  the wait for sub-second runs.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests
from fredapi import Fred
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from src.research.data import DataPipelineError, DataProvider
from src.research.data._fred_key import get_fred_api_key

# ---------------------------------------------------------------------------
# Metis-contract column order (must match src/research/data.DataProvider docstring)
# ---------------------------------------------------------------------------

_METIS_COLUMNS: list[str] = [
    "ts",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "source",
]

_EMPTY_FRAME: pd.DataFrame = pd.DataFrame(columns=_METIS_COLUMNS)


class FredProvider(DataProvider):
    """FRED API data provider with parquet caching and staleness checks.

    DataFrame column contract (from :class:`DataProvider`)::

        ts (datetime64[ns]), open, high, low, close,
        volume (NaN -- FRED publishes single values, not OHLCV),
        source (str: f"fred:{series_id}")
    """

    # Metis SC4 lockdown. Originally 13 series (W2/T6); T11 (W3) added
    # ``ISM_MANUFACTURING`` because the macro-factor table requires ``ism_pmi``
    # (monthly ISM Manufacturing PMI) and no whitelist member covered it.
    # The original T6 spec said "the whitelist already includes all the series
    # you need" -- that was inaccurate; ISM was the one missing primitive.
    SUPPORTED_SERIES: frozenset[str] = frozenset(
        {
            "DCOILWTICO",  # WTI spot
            "CSUSHPINSA",  # Case-Shiller National NSA (monthly)
            "DFII10",  # 10Y real yield
            "DGS10",  # 10Y nominal yield
            "T10YIE",  # 10Y breakeven inflation
            "DTWEXBGS",  # Trade-weighted USD index
            "VIXCLS",  # VIX
            "DFF",  # Fed Funds effective rate
            "UNRATE",  # Unemployment rate (monthly)
            "CPIAUCSL",  # CPI all urban consumers (monthly)
            "MORTGAGE30US",  # 30Y fixed mortgage rate (weekly)
            "IPMAN",  # Industrial Production Manufacturing (monthly; ISM PMI proxy — ISM removed from FRED 2016)
        }
    )

    # Retry config. Public instance attributes so tests can zero the wait;
    # production callers should leave the class defaults.
    RETRY_ATTEMPTS: int = 5
    RETRY_INITIAL_WAIT: float = 2.0
    RETRY_MAX_WAIT: float = 60.0
    RETRY_JITTER: float = 1.0

    def __init__(
        self,
        api_key: str | None = None,
        cache_dir: Path = Path("data/macro"),
        max_staleness_days: int = 60,
        series_id: str = "DFF",  # default to a working series (gold LBMA removed from FRED)
    ) -> None:
        # Resolve the API key first so a missing key fails fast before any
        # filesystem work (T1 fail-fast helper).
        self.api_key: str = api_key or get_fred_api_key()
        self.cache_dir: Path = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_staleness_days: int = int(max_staleness_days)
        if series_id not in self.SUPPORTED_SERIES:
            raise ValueError(
                f"Unsupported FRED series: {series_id}. "
                f"Supported: {sorted(self.SUPPORTED_SERIES)}"
            )
        self.series_id: str = series_id
        # Lazy-init: the real Fred client is only built when first needed,
        # so tests can inject a mock via `provider._client = ...`.
        self._client: Fred | None = None

    # ------------------------------------------------------------------
    # DataProvider ABC
    # ------------------------------------------------------------------

    @property
    def client(self) -> Fred:
        """Lazily-constructed :class:`fredapi.Fred` client."""
        if self._client is None:
            self._client = Fred(api_key=self.api_key)
        return self._client

    @property
    def trading_days_per_year(self) -> float:
        # FRED publishes on the observation date (daily for most series,
        # monthly for Case-Shiller / CPI / unemployment). 365.25 matches the
        # daily cadence and is safely re-used by callers that resample.
        return 365.25

    def load_daily(self, start: date, end: date) -> pd.DataFrame:
        """Dispatch to :meth:`fetch` using the configured default series."""
        return self.fetch(self.series_id, start, end)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch(self, series_id: str, start: date, end: date) -> pd.DataFrame:
        """Fetch a FRED series as a Metis-contract DataFrame.

        Args:
            series_id: must be in :attr:`SUPPORTED_SERIES`.
            start: inclusive start date (date object or ISO string).
            end: inclusive end date (date object or ISO string).

        Returns:
            DataFrame with columns ``ts, open, high, low, close, volume, source``.
            ``open == high == low == close`` (FRED is single-value-per-ts);
            ``volume`` is NaN; ``source`` is ``f"fred:{series_id}"``.

        Raises:
            ValueError: ``series_id`` is not in :attr:`SUPPORTED_SERIES`.
            DataPipelineError: fresh fetch returned data older than
                ``max_staleness_days`` for a current query.
        """
        # Accept both date objects and ISO date strings
        if isinstance(start, str):
            start = date.fromisoformat(start)
        if isinstance(end, str):
            end = date.fromisoformat(end)
        if series_id not in self.SUPPORTED_SERIES:
            raise ValueError(
                f"Unsupported FRED series: {series_id}. "
                f"Supported: {sorted(self.SUPPORTED_SERIES)}"
            )

        cache_path = self.cache_dir / f"{series_id}.parquet"

        # 1. Serve from cache if it covers the requested range (Metis EC9:
        #    "never re-fetch if cache is fresh").
        cached = self._read_cache(cache_path)
        if self._cache_covers(cached, start, end):
            logger.info(
                f"FRED {series_id}: cache hit ({len(cached)} rows "
                f"{cached['ts'].min().date()} -> {cached['ts'].max().date()})"
            )
            return self._slice(cached, start, end)

        # 2. Cache miss or partial -> fetch the full requested range.
        logger.info(f"FRED {series_id}: fetching [{start} -> {end}] from FRED API")
        raw = self._call_fred(series_id, start, end)
        df = self._to_metis_frame(raw, series_id)

        # 3. Staleness guard (only fires for "current" queries; see method doc).
        if not df.empty:
            self._check_staleness(df, series_id, end)

        # 4. Persist and serve the requested slice.
        self._write_cache(df, cache_path)
        logger.info(
            f"FRED {series_id}: fetched {len(df)} rows "
            f"({df['ts'].min().date() if not df.empty else 'n/a'} -> "
            f"{df['ts'].max().date() if not df.empty else 'n/a'})"
        )
        return self._slice(df, start, end)

    # ------------------------------------------------------------------
    # FRED API call (with retry)
    # ------------------------------------------------------------------

    def _call_fred(self, series_id: str, start: date, end: date) -> pd.Series:
        """Call ``Fred.get_series`` with tenacity retry.

        The decorator is rebuilt on each call so tests can override the
        ``RETRY_*`` instance attributes for sub-second runs.
        """

        @retry(
            stop=stop_after_attempt(self.RETRY_ATTEMPTS),
            wait=wait_exponential_jitter(
                initial=self.RETRY_INITIAL_WAIT,
                max=self.RETRY_MAX_WAIT,
                jitter=self.RETRY_JITTER,
            ),
            retry=retry_if_exception_type(
                (requests.ConnectionError, requests.HTTPError)
            ),
            reraise=True,
        )
        def _do() -> pd.Series:
            return self.client.get_series(
                series_id,
                observation_start=start.isoformat(),
                observation_end=end.isoformat(),
            )

        return _do()

    # ------------------------------------------------------------------
    # Frame conversion
    # ------------------------------------------------------------------

    def _to_metis_frame(self, series: pd.Series, series_id: str) -> pd.DataFrame:
        """Convert a FRED ``pd.Series`` to the Metis OHLCV contract.

        FRED publishes a single value per timestamp, so ``open == high ==
        low == close``. ``volume`` is NaN. ``source`` is ``f"fred:{id}"``.

        Note: DCOILWTICO can be negative (April 2020 -$37.63). Do not skip;
        pass through as-is. (Metis EC3.)
        """
        if series is None or series.empty:
            return _EMPTY_FRAME.copy()

        # FRED dates are tz-naive midnights (UTC dates). Localize to UTC then
        # strip tz to match the rest of the codebase (datetime64[ns]).
        ts = pd.to_datetime(series.index, utc=True).tz_convert(None)
        values = series.to_numpy(dtype=float)

        df = pd.DataFrame(
            {
                "ts": ts,
                "open": values,
                "high": values,
                "low": values,
                "close": values,
                "volume": float("nan"),
                "source": f"fred:{series_id}",
            }
        )
        # Drop rows where FRED reported no observation (NaN in the value).
        df = df.dropna(subset=["close"])
        df = df.drop_duplicates(subset=["ts"]).sort_values("ts").reset_index(drop=True)
        return df

    # ------------------------------------------------------------------
    # Cache helpers (parquet)
    # ------------------------------------------------------------------

    def _read_cache(self, path: Path) -> pd.DataFrame:
        """Read a cached parquet file. Empty frame if missing or corrupt.

        On corruption the file is deleted so the next call refetches cleanly.
        """
        if not path.exists():
            return _EMPTY_FRAME.copy()
        try:
            df = pd.read_parquet(path)
        except Exception as exc:
            logger.warning(
                f"FRED: corrupt cache file {path}: {exc}; deleting and refetching"
            )
            try:
                path.unlink()
            except OSError as unlink_exc:
                logger.warning(f"FRED: could not delete corrupt cache {path}: {unlink_exc}")
            return _EMPTY_FRAME.copy()
        return df

    def _write_cache(self, df: pd.DataFrame, path: Path) -> None:
        """Atomically overwrite the cache file (write .tmp then replace).

        Spec: "Save full fetched range to cache (overwrites if exists)".
        """
        if df.empty:
            return
        tmp = path.with_suffix(path.suffix + ".tmp")
        df.to_parquet(tmp, index=False)
        tmp.replace(path)

    def _cache_covers(self, cached: pd.DataFrame, start: date, end: date) -> bool:
        """True if ``cached`` spans at least ``[start, end]``."""
        if cached.empty:
            return False
        return bool(
            cached["ts"].min().date() <= start and cached["ts"].max().date() >= end
        )

    def _slice(self, df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
        """Return the ``[start, end]`` inclusive slice of ``df``."""
        if df.empty:
            return df.reset_index(drop=True)
        start_ts = pd.Timestamp(start)
        # Include the whole end date (FRED daily data sits at midnight UTC).
        end_ts_exclusive = pd.Timestamp(end) + pd.Timedelta(days=1)
        mask = (df["ts"] >= start_ts) & (df["ts"] < end_ts_exclusive)
        return df[mask].reset_index(drop=True)

    # ------------------------------------------------------------------
    # Staleness guard
    # ------------------------------------------------------------------

    # Monthly series publish with ~2-month lag (e.g. Case-Shiller March data
    # lands late May). Their latest observation is routinely 60-110 days old
    # even when perfectly fresh. Give them a larger staleness allowance.
    _MONTHLY_SERIES: frozenset[str] = frozenset({
        "CSUSHPINSA", "UNRATE", "CPIAUCSL", "IPMAN",
    })

    def _staleness_limit(self, series_id: str) -> int:
        """Cadence-aware staleness threshold in days."""
        if series_id in self._MONTHLY_SERIES:
            return max(self.max_staleness_days, 120)
        return self.max_staleness_days

    def _check_staleness(
        self, df: pd.DataFrame, series_id: str, query_end: date
    ) -> None:
        """Raise :class:`DataPipelineError` if source data is too stale.

        Only enforced for *current* queries -- i.e. ``query_end`` is within
        the staleness window of today. Historical backtests fetch old data
        on purpose and must not trip this guard. Monthly-lagged series get
        a larger allowance (120d) to account for publication lag.
        """
        today = date.today()
        limit = self._staleness_limit(series_id)
        if query_end < today - timedelta(days=limit):
            return  # historical query -- staleness does not apply
        if df.empty:
            return
        last_ts = df["ts"].max()
        last_date = last_ts.date() if hasattr(last_ts, "date") else pd.Timestamp(last_ts).date()
        age_days = (today - last_date).days
        if age_days > limit:
            raise DataPipelineError(
                f"FRED series {series_id} is stale: last update {last_date}, "
                f"max staleness {limit}d"
            )
