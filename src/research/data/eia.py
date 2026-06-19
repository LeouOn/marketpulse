"""EIA v2 data provider for oil fundamentals (W2 T9).

Fetches oil-related series from the U.S. Energy Information Administration
(EIA) v2 REST API. EIA has no official Python SDK as of 2026, so this module
calls the REST endpoint directly via :mod:`requests`.

Scope is intentionally narrow: only the five oil series in
:data:`EiaProvider.SUPPORTED_SERIES` are fetchable (Metis SC4 lock-down).
Electricity, natural gas, and other EIA domains are out of scope.

Each series is cached as a parquet file under ``data/eia_cache/``. Cache
freshness is judged by the parquet file's ``mtime`` — a recently-written cache
is served without touching the network. Once ``max_staleness_days`` has
elapsed the provider attempts a refresh; if the refresh fails the provider
raises :class:`~src.research.data.DataPipelineError` rather than serving
stale oil data (strict freshness — stale fundamentals can mislead the
backtest, unlike equities where a stale price is usually close enough).
"""

from __future__ import annotations

import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests
from loguru import logger
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from src.research.data import DataPipelineError, DataProvider
from src.research.data._eia_key import get_eia_api_key

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EIA_V2_BASE = "https://api.eia.gov/v2"
EIA_TIMEOUT = 30
EIA_DEFAULT_CACHE_DIR = Path("data/eia_cache")

# Metis column contract — must match the BTC/DataProvider shape exactly so
# the backtest engine can consume EIA frames unchanged.
_CONTRACT_COLUMNS = ["ts", "open", "high", "low", "close", "volume", "source"]

# Per-series EIA v2 route + frequency metadata. Spot prices live under the
# ``petroleum/pri/spt`` route at daily frequency; weekly inventories live
# under ``petroleum/stoc/wstk`` at weekly frequency. The route+frequency are
# looked up at fetch time so the URL matches the series being requested.
# Each public (v1-style) series ID maps to (route, frequency, v2_facet_code).
# CRITICAL: v2 API facets[series][] expects SHORT codes (e.g. RWTC), not
# legacy dotted IDs. Filtering by dotted ID silently returns 0 rows.
_SERIES_ROUTE: dict[str, tuple[str, str, str]] = {
    "PET.RWTC.D":          ("petroleum/pri/spt/data",   "daily",  "RWTC"),
    "PET.RBRTE.D":         ("petroleum/pri/spt/data",   "daily",  "RBRTE"),
    "PET.WGFUPUS2.W":      ("petroleum/stoc/wstk/data", "weekly", "WCRSTUS1"),
    "PET.WPULEUS3.W":      ("petroleum/stoc/wstk/data", "weekly", "WGTSTUS1"),
    "PET.WPUP_NUS-Z1_2.W": ("petroleum/stoc/wstk/data", "weekly", "WDISTUS1"),
}


class EiaProvider(DataProvider):
    """Oil-fundamentals data provider backed by the EIA v2 REST API.

    DataFrame column contract (consumed by ``src.research.backtest``)::

        ts (datetime64[ns]), open, high, low, close, volume (NaN), source (f"eia:{sid}")

    EIA returns a single value per timestamp (a spot price or an inventory
    level), so ``open == high == low == close == value`` and ``volume`` is
    NaN — there is no intraday OHLC for these series.

    Series are locked to the :data:`SUPPORTED_SERIES` whitelist (Metis SC4).
    Any other ``series_id`` raises :class:`ValueError` at fetch time.
    """

    # Metis SC4 lock-down: only oil fundamentals. Reject anything else.
    SUPPORTED_SERIES: frozenset[str] = frozenset(_SERIES_ROUTE.keys())

    def __init__(
        self,
        api_key: str | None = None,
        cache_dir: Path = EIA_DEFAULT_CACHE_DIR,
        max_staleness_days: int = 7,
        series_id: str = "PET.RWTC.D",
        timeout: int = EIA_TIMEOUT,
        retry_attempts: int = 4,
        retry_initial_wait: float = 2.0,
        retry_max_wait: float = 60.0,
    ) -> None:
        # Fail fast on missing API key — mirrors _fred_key.py (T1 pattern).
        self.api_key: str = api_key if api_key is not None else get_eia_api_key()
        self.cache_dir: Path = Path(cache_dir)
        self.max_staleness_days: int = max_staleness_days
        # Default series used by load_daily() — WTI spot daily.
        self.series_id: str = series_id
        self.timeout: int = timeout
        self.retry_attempts: int = retry_attempts
        self.retry_initial_wait: float = retry_initial_wait
        self.retry_max_wait: float = retry_max_wait
        # Ensure cache dir exists for writes; reads tolerate missing files.
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # DataProvider ABC contract
    # ------------------------------------------------------------------

    @property
    def trading_days_per_year(self) -> float:
        """EIA daily series follow business days → 252 annualisation."""
        return 252.0

    def load_daily(self, start: date, end: date) -> pd.DataFrame:
        """Fetch the provider's default series (``self.series_id``)."""
        return self.fetch(self.series_id, start, end)

    # ------------------------------------------------------------------
    # Public fetch API
    # ------------------------------------------------------------------

    def fetch(self, series_id: str, start: date, end: date) -> pd.DataFrame:
        """Fetch ``series_id`` over ``[start, end]`` inclusive.

        Args:
            series_id: Must be in :data:`SUPPORTED_SERIES`.
            start: Inclusive start date (date object or ISO string).
            end: Inclusive end date (date object or ISO string).

        Returns:
            DataFrame with the Metis column contract.

        Raises:
            ValueError: If ``series_id`` is not in the whitelist.
            DataPipelineError: If the cache is stale/missing AND the EIA
                fetch fails (after retries).
        """
        # Accept both date objects and ISO date strings
        if isinstance(start, str):
            start = date.fromisoformat(start)
        if isinstance(end, str):
            end = date.fromisoformat(end)
        if series_id not in self.SUPPORTED_SERIES:
            raise ValueError(
                f"Unsupported EIA series: {series_id!r}. "
                f"Supported (oil only): {sorted(self.SUPPORTED_SERIES)}"
            )

        cache_path = self.cache_dir / f"{series_id}.parquet"

        # Fresh cache → serve without network.
        if self._cache_is_fresh(cache_path):
            cached = self._read_cache(cache_path)
            return self._slice(cached, start, end)

        # Cache stale or missing → must fetch.
        try:
            payload = self._fetch_raw(series_id, start, end)
        except Exception as exc:
            raise DataPipelineError(
                f"EIA fetch failed for {series_id} ({start} → {end}) "
                f"and no fresh cache is available: {exc}"
            ) from exc

        new_df = self._parse_payload(payload, series_id)
        existing = self._read_cache(cache_path)
        merged = self._merge(new_df, existing)
        if not merged.empty:
            self._write_cache(merged, cache_path)
        return self._slice(merged, start, end)

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _build_url(self, series_id: str, start: date, end: date) -> str:
        """Build the EIA v2 GET URL for one series over a date range."""
        route, frequency, facet = _SERIES_ROUTE[series_id]
        return (
            f"{EIA_V2_BASE}/{route}"
            f"?api_key={self.api_key}"
            f"&frequency={frequency}"
            f"&data[0]=value"
            f"&facets[series][]={facet}"
            f"&start={start.isoformat()}"
            f"&end={end.isoformat()}"
        )

    def _fetch_raw(self, series_id: str, start: date, end: date) -> dict:
        """GET the EIA v2 endpoint with retry/backoff. Returns parsed JSON.

        Retries on transient HTTP errors (5xx, 429, timeouts, connection
        errors). After ``retry_attempts`` failures the last exception is
        re-raised for the caller (``fetch``) to wrap in :class:`DataPipelineError`.
        """
        url = self._build_url(series_id, start, end)
        retryer = Retrying(
            stop=stop_after_attempt(self.retry_attempts),
            wait=wait_exponential_jitter(
                initial=self.retry_initial_wait, max=self.retry_max_wait
            ),
            retry=retry_if_exception_type(
                (requests.HTTPError, requests.Timeout, requests.ConnectionError)
            ),
            reraise=True,
        )
        for attempt in retryer:
            with attempt:
                r = requests.get(url, timeout=self.timeout)
                r.raise_for_status()
                return r.json()
        # Unreachable: reraise=True guarantees an exception propagates above.
        raise RuntimeError("EIA retry loop exited without a result or exception")

    # ------------------------------------------------------------------
    # EIA v2 JSON → DataFrame
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_payload(payload: dict, series_id: str) -> pd.DataFrame:
        """Parse EIA v2 ``{"response": {"data": [...]}}`` into contract rows.

        Rows with ``value is None`` or a missing ``value``/``period`` field
        are dropped (EIA emits null for unpublished periods). EIA's single
        value per timestamp is propagated to all four OHLC fields; volume is
        NaN; ``source`` is ``f"eia:{series_id}"``.
        """
        data = (payload or {}).get("response", {}).get("data", []) or []
        rows: list[dict] = []
        for d in data:
            value = d.get("value")
            period = d.get("period")
            if value is None or period is None:
                continue  # skip null/missing
            try:
                v = float(value)
            except (TypeError, ValueError):
                continue  # skip non-numeric
            rows.append(
                {
                    "ts": pd.Timestamp(period),
                    "open": v,
                    "high": v,
                    "low": v,
                    "close": v,
                    "volume": float("nan"),
                    "source": f"eia:{series_id}",
                }
            )
        return pd.DataFrame(rows, columns=_CONTRACT_COLUMNS)

    # ------------------------------------------------------------------
    # Parquet cache
    # ------------------------------------------------------------------

    def _cache_is_fresh(self, cache_path: Path) -> bool:
        """True iff the cache file exists and its mtime is within staleness."""
        if not cache_path.exists():
            return False
        age_seconds = time.time() - cache_path.stat().st_mtime
        return age_seconds <= self.max_staleness_days * 86400.0

    @staticmethod
    def _read_cache(cache_path: Path) -> pd.DataFrame:
        """Read a cached parquet. Empty contract-shaped frame if missing/corrupt."""
        empty = pd.DataFrame(columns=_CONTRACT_COLUMNS)
        if not cache_path.exists():
            return empty
        try:
            df = pd.read_parquet(cache_path)
        except Exception as exc:
            logger.warning(
                f"Corrupt EIA parquet cache {cache_path}: {exc}; treating as empty"
            )
            return empty
        if df.empty:
            return empty
        df = df.drop_duplicates(subset=["ts"]).sort_values("ts").reset_index(drop=True)
        return df

    def _write_cache(self, df: pd.DataFrame, cache_path: Path) -> None:
        """Write the cache atomically (write to ``.tmp`` then replace)."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = cache_path.with_suffix(cache_path.suffix + ".tmp")
        df.to_parquet(tmp, index=False)
        tmp.replace(cache_path)

    @staticmethod
    def _merge(new: pd.DataFrame, existing: pd.DataFrame) -> pd.DataFrame:
        """Combine new rows with existing cache, dedupe by ts (new wins), sort."""
        if existing.empty:
            combined = new.copy()
        elif new.empty:
            combined = existing.copy()
        else:
            combined = pd.concat([existing, new], ignore_index=True)
        combined = (
            combined.drop_duplicates(subset=["ts"], keep="last")
            .sort_values("ts")
            .reset_index(drop=True)
        )
        return combined

    @staticmethod
    def _slice(df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
        """Filter to ``[start, end]`` inclusive on ``ts``."""
        if df.empty:
            return df
        mask = (df["ts"] >= pd.Timestamp(start)) & (df["ts"] <= pd.Timestamp(end))
        return df[mask].reset_index(drop=True)
