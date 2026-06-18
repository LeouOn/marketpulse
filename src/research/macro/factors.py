"""Macro factor provider for the multi-asset research lab (W3/T11).

Composes :class:`src.research.data.fred.FredProvider` (macro primitives)
and :class:`src.research.data.yahoo.YahooProvider` (oil futures curve)
into a single ``factor_df`` of 12 macro factors + the Sahm recession
rule. The downstream classifier (T12) consumes ``factor_df`` and
:meth:`MacroFactorProvider.compute_zscores` to detect macro regimes.

Factor list (locked, 12 columns)
--------------------------------

================== =============== ================================= =========
Factor name        Source          FRED series / Yahoo ticker         Cadence
================== =============== ================================= =========
``real_yield_10y`` FRED            ``DFII10``                         Daily
``nominal_10y``    FRED            ``DGS10``                          Daily
``breakeven_10y``  FRED            ``T10YIE``                         Daily
``dxy``            FRED            ``DTWEXBGS``                       Daily
``vix``            FRED            ``VIXCLS``                         Daily
``fed_funds``      FRED            ``DFF``                            Daily
``ism_pmi``        FRED            ``ISM_MANUFACTURING``              Monthly
``unemployment``   FRED            ``UNRATE``                         Monthly
``cpi_yoy``        Derived         YoY pct change of ``CPIAUCSL``    Monthly
``sahm_recession`` Derived         Sahm rule on ``unemployment``     Monthly
``oil_term_structure`` Yahoo       ``CL=F`` - 12M forward             Daily
``mortgage_30y``   FRED            ``MORTGAGE30US``                   Weekly
================== =============== ================================= =========

Behaviour notes
---------------

* **Monthly -> daily forward-fill.** Monthly factors (CPI, ISM,
  unemployment, Sahm) are reindexed onto a daily DatetimeIndex with
  ``method="ffill"`` so non-publication days carry the most-recent
  observation. Days before the first publication in the requested
  window remain NaN -- no back-fill.
* **Missing factors are NOT imputed.** If a series fetch fails or
  returns empty, the column stays NaN. The downstream classifier
  (T12) handles this by setting that regime's probability to 0 and
  renormalising (Metis EC1).
* **Cache.** A single ``data/macro/factors.parquet`` holds the joined
  frame. A cache file that *covers* the requested ``[start, end]``
  range is served without any Fred/Yahoo call. Otherwise the full
  range is fetched and the cache is overwritten.
* **Sahm rule** (Claudia Sahm): recession triggers when the 3-month
  moving average of unemployment rises >= 0.5pp above its 12-month
  low. Reference: https://fred.stlouisfed.org/series/SAHMREALTIME
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Protocol

import pandas as pd
from loguru import logger

from src.research.data.fred import FredProvider
from src.research.data.yahoo import YahooProvider


# ---------------------------------------------------------------------------
# Provider Protocols -- structural typing so unit-test stubs work without
# inheriting from FredProvider / YahooProvider (whose constructors reach
# for API keys). Both concrete providers satisfy these implicitly.
# ---------------------------------------------------------------------------


class _FredLike(Protocol):
    """Anything with a FRED-style ``fetch(series_id, start, end)``."""

    def fetch(self, series_id: str, start: date, end: date) -> pd.DataFrame: ...


class _YahooLike(Protocol):
    """Anything with a Yahoo-style ``fetch(ticker, start, end)``."""

    def fetch(self, ticker: str, start: date, end: date) -> pd.DataFrame: ...

# ---------------------------------------------------------------------------
# Spec lockdown -- the 12 canonical factor column names + providers
# ---------------------------------------------------------------------------

#: Canonical column order of the returned ``factor_df``. T12 reads this
#: in order; do not re-order without coordinating with T12.
FACTOR_COLUMNS: tuple[str, ...] = (
    "real_yield_10y",
    "nominal_10y",
    "breakeven_10y",
    "dxy",
    "vix",
    "fed_funds",
    "ism_pmi",
    "unemployment",
    "cpi_yoy",
    "sahm_recession",
    "oil_term_structure",
    "mortgage_30y",
)

#: Map of factor name -> FRED series id, for the 8 "direct" factors
#: (the 4 derived factors -- ``cpi_yoy``, ``sahm_recession``,
#: ``oil_term_structure``, and the CPI level input -- are handled
#: separately below).
_FRED_DIRECT: dict[str, str] = {
    "real_yield_10y": "DFII10",
    "nominal_10y": "DGS10",
    "breakeven_10y": "T10YIE",
    "dxy": "DTWEXBGS",
    "vix": "VIXCLS",
    "fed_funds": "DFF",
    "ism_pmi": "ISM_MANUFACTURING",
    "unemployment": "UNRATE",
    "mortgage_30y": "MORTGAGE30US",
}

#: FRED series id for the CPI level (input to ``cpi_yoy``).
_CPI_LEVEL_SERIES_ID: str = "CPIAUCSL"

#: Number of months of extra CPI history to fetch so that the YoY pct
#: change is defined at the very start of the requested window.
_CPI_HISTORY_LOOKBACK_DAYS: int = 400

#: Yahoo tickers for the oil term structure.
OIL_FRONT_TICKER: str = "CL=F"
#: 12-month-ish forward WTI contract. yfinance exposes specific
#: contracts via ``{root}{month}{yy}.NYM``; ``CLZ27.NYM`` is Dec-2027
#: WTI, a stable far-dated proxy. If yfinance lacks this ticker at
#: runtime, ``oil_term_structure`` becomes NaN -- graceful degradation.
OIL_BACK_TICKER: str = "CLZ27.NYM"

#: Cache filename (under ``cache_dir``).
_CACHE_FILENAME: str = "factors.parquet"


# ---------------------------------------------------------------------------
# MacroFactorProvider
# ---------------------------------------------------------------------------


class MacroFactorProvider:
    """Compose FRED + Yahoo into a 12-column macro factor frame.

    Args:
        fred: Optional :class:`FredProvider`. Built with the default
            constructor (which requires ``FRED_API_KEY``) if omitted.
        yahoo: Optional :class:`YahooProvider`. Built default if omitted.
        cache_dir: Directory holding ``factors.parquet``. Created if
            missing. Defaults to ``data/macro`` (same dir FredProvider
            uses, so FRED primitives and the joined factor frame share
            a parent -- but distinct filenames).
    """

    def __init__(
        self,
        fred: _FredLike | None = None,
        yahoo: _YahooLike | None = None,
        cache_dir: Path = Path("data/macro"),
    ) -> None:
        self.fred: _FredLike = fred if fred is not None else FredProvider()
        self.yahoo: _YahooLike = yahoo if yahoo is not None else YahooProvider()
        self.cache_dir: Path = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_factors(self, start: date, end: date) -> pd.DataFrame:
        """Fetch and join all 12 macro factors over ``[start, end]``.

        Returns a ``pd.DataFrame`` with:

        * a daily ``DatetimeIndex`` (named ``"date"``) spanning
          ``[start, end]`` inclusive,
        * the 12 columns in :data:`FACTOR_COLUMNS` (in order),
        * monthly / weekly / daily values forward-filled onto daily
          rows (see module docstring).

        Cache: a covering ``factors.parquet`` is served without any
        upstream calls. Otherwise the full range is fetched and the
        cache is overwritten.
        """
        cache_path = self.cache_dir / _CACHE_FILENAME
        cached = self._read_cache(cache_path)
        if cached is not None and self._cache_covers(cached, start, end):
            logger.info(
                f"factors: cache hit ({len(cached)} rows "
                f"{cached.index.min().date()} -> {cached.index.max().date()})"
            )
            return self._slice(cached, start, end)

        logger.info(f"factors: cache miss; fetching [{start} -> {end}]")
        raw = self._fetch_raw_factors(start, end)
        factor_df = self._assemble_daily(raw, start, end)
        self._write_cache(factor_df, cache_path)
        return factor_df

    def compute_zscores(
        self,
        factor_df: pd.DataFrame,
        window_days: int = 5 * 365,
    ) -> pd.DataFrame:
        """Rolling z-score per column using a ``window_days`` lookback.

        Returns a frame with the same shape / index / columns as the
        input. Each cell is ``(value - rolling_mean) / rolling_std``
        over the trailing ``window_days`` window. Cells where the
        rolling std is 0 (constant column) or undefined (insufficient
        history) are NaN -- avoids division-by-zero and matches the
        downstream classifier's expectation that "no information =
        NaN", not "NaN = 0".
        """
        # ``window=...D`` (string) interprets the window as a calendar
        # span on the DatetimeIndex, so weekends / holidays are not
        # counted as observations but DO extend the lookback in
        # calendar time. min_periods=2 lets the first non-trivial pair
        # produce a defined std.
        window = f"{window_days}D"
        rolling = factor_df.rolling(window=window, min_periods=2)
        mean = rolling.mean()
        std = rolling.std()
        # ddof=1 (default for pandas .std); replace 0-std with NaN so
        # we don't blow up on constant columns.
        std_safe = std.where(std > 0, other=pd.NA)
        return (factor_df - mean) / std_safe

    # ------------------------------------------------------------------
    # Derived-factor formulas (public -- tests exercise directly)
    # ------------------------------------------------------------------

    def _compute_sahm(self, unemployment: pd.Series) -> pd.Series:
        """Sahm recession rule.

        Formula::

            ma_3mo         = unemployment.rolling(3).mean()
            rolling_12mo_min = ma_3mo.rolling(12).min()
            sahm_value     = max(0, ma_3mo - rolling_12mo_min)
            recession_flag = sahm_value >= 0.5

        Returns a ``bool`` Series (True = recession), indexed the same
        as ``unemployment``. Cells with insufficient history for the
        12-month min are NaN (boolean-NaN).

        Reference: https://fred.stlouisfed.org/series/SAHMREALTIME
        """
        ma_3mo = unemployment.rolling(3).mean()
        rolling_12mo_min = ma_3mo.rolling(12).min()
        sahm_value = (ma_3mo - rolling_12mo_min).clip(lower=0.0)
        return (sahm_value >= 0.5).rename("sahm_recession")

    def _compute_cpi_yoy(self, cpi_level: pd.Series) -> pd.Series:
        """Year-over-year pct change of the CPI level (``periods=12``).

        The CPI level series is monthly; the 12-period lag therefore
        captures the same calendar month one year prior. Returns a
        Series indexed the same as ``cpi_level``, with the first 12
        rows NaN (no prior year).
        """
        return (cpi_level.pct_change(periods=12)).rename("cpi_yoy")

    def _compute_oil_term_structure(
        self,
        front: pd.DataFrame,
        back: pd.DataFrame,
    ) -> pd.Series:
        """Front-month WTI close minus 12M-forward WTI close.

        ``front`` / ``back`` are Metis-contract DataFrames (as returned
        by :class:`YahooProvider`). Their ``close`` columns are aligned
        on their ``ts`` columns; non-matching dates produce NaN.
        """
        front_close = front.set_index("ts")["close"]
        back_close = back.set_index("ts")["close"]
        # Outer join so we keep all observation dates; the subtraction
        # then yields NaN where only one leg is present.
        aligned = pd.concat(
            [front_close.rename("front"), back_close.rename("back")],
            axis=1,
            join="outer",
        ).sort_index()
        return (aligned["front"] - aligned["back"]).rename("oil_term_structure")

    # ------------------------------------------------------------------
    # Orchestration: fetch + assemble
    # ------------------------------------------------------------------

    def _fetch_raw_factors(
        self, start: date, end: date
    ) -> dict[str, pd.Series]:
        """Fetch each upstream series and return ``{factor_name: Series}``.

        Each returned Series is indexed by ``ts`` (Timestamp) and named
        after its factor. Failed fetches emit a warning and are simply
        omitted from the dict -- the assembler then leaves that column
        as all-NaN.
        """
        raw: dict[str, pd.Series] = {}

        # 1. Direct FRED factors.
        for factor_name, series_id in _FRED_DIRECT.items():
            series = self._safe_fred_fetch(series_id, start, end)
            if series is not None:
                series.name = factor_name
                raw[factor_name] = series

        # 2. CPI level -> cpi_yoy. Fetch extra history so the YoY at
        #    the start of the window is defined.
        cpi_start = start - timedelta(days=_CPI_HISTORY_LOOKBACK_DAYS)
        cpi_level = self._safe_fred_fetch(_CPI_LEVEL_SERIES_ID, cpi_start, end)
        if cpi_level is not None:
            cpi_yoy = self._compute_cpi_yoy(cpi_level)
            raw["cpi_yoy"] = cpi_yoy

        # 3. Sahm rule (derived from unemployment).
        if "unemployment" in raw:
            sahm = self._compute_sahm(raw["unemployment"])
            raw["sahm_recession"] = sahm

        # 4. Oil term structure from Yahoo.
        try:
            front = self.yahoo.fetch(OIL_FRONT_TICKER, start, end)
            back = self.yahoo.fetch(OIL_BACK_TICKER, start, end)
            if not front.empty and not back.empty:
                ts_raw = self._compute_oil_term_structure(front, back)
                raw["oil_term_structure"] = ts_raw
            elif front.empty and back.empty:
                logger.warning(
                    "oil_term_structure: both Yahoo legs empty; "
                    "factor will be NaN"
                )
            else:
                logger.warning(
                    "oil_term_structure: one Yahoo leg empty "
                    f"(front={len(front)}, back={len(back)}); "
                    "factor will be NaN"
                )
        except Exception as exc:  # pragma: no cover -- defensive
            logger.warning(f"oil_term_structure: Yahoo fetch failed: {exc}")

        return raw

    def _safe_fred_fetch(
        self, series_id: str, start: date, end: date
    ) -> pd.Series | None:
        """Fetch a FRED series, returning ``close`` indexed by ``ts``.

        Returns ``None`` on any error or empty result (caller leaves
        the corresponding factor column as NaN).
        """
        try:
            df = self.fred.fetch(series_id, start, end)
        except Exception as exc:  # pragma: no cover -- defensive
            logger.warning(f"FRED {series_id}: fetch failed: {exc}")
            return None
        if df.empty:
            logger.info(f"FRED {series_id}: no observations in range")
            return None
        s = df.set_index("ts")["close"]
        # Drop duplicate timestamps if any (defensive; FredProvider
        # already dedupes, but be safe).
        s = s[~s.index.duplicated(keep="last")].sort_index()
        return s

    def _assemble_daily(
        self,
        raw: dict[str, pd.Series],
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """Reindex all factors onto a daily ``DatetimeIndex`` and ffill.

        Each raw series is reindexed onto ``date_range(start, end,
        freq="D")`` with ``method="ffill"`` so that monthly/weekly
        publications carry forward onto non-publication days. Factors
        not present in ``raw`` get an all-NaN column.
        """
        daily_index = pd.date_range(start, end, freq="D", name="date")
        factor_df = pd.DataFrame(index=daily_index)
        for col in FACTOR_COLUMNS:
            if col in raw:
                s = raw[col]
                # boolean dtype (Sahm) -> cast to object to allow NaN
                # placeholders on days before the first publication.
                factor_df[col] = s.reindex(daily_index, method="ffill")
            else:
                factor_df[col] = pd.NA
        return factor_df

    # ------------------------------------------------------------------
    # Cache helpers (single factors.parquet file)
    # ------------------------------------------------------------------

    def _read_cache(self, path: Path) -> pd.DataFrame | None:
        if not path.exists():
            return None
        try:
            df = pd.read_parquet(path)
        except Exception as exc:
            logger.warning(
                f"factors: corrupt cache file {path}: {exc}; "
                "deleting and refetching"
            )
            try:
                path.unlink()
            except OSError as unlink_exc:
                logger.warning(
                    f"factors: could not delete corrupt cache {path}: {unlink_exc}"
                )
            return None
        # Restore the named DatetimeIndex if parquet round-tripped it
        # to a regular column.
        if "date" in df.columns:
            df = df.set_index("date")
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        df.index.name = "date"
        return df

    def _write_cache(self, df: pd.DataFrame, path: Path) -> None:
        if df.empty:
            return
        tmp = path.with_suffix(path.suffix + ".tmp")
        df.to_parquet(tmp, index=True)
        tmp.replace(path)

    @staticmethod
    def _cache_covers(cached: pd.DataFrame, start: date, end: date) -> bool:
        if cached.empty:
            return False
        return bool(
            cached.index.min().date() <= start and cached.index.max().date() >= end
        )

    @staticmethod
    def _slice(df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
        """Return the ``[start, end]`` inclusive slice of ``df``."""
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end) + pd.Timedelta(days=1)  # exclusive upper
        sliced = df.loc[(df.index >= start_ts) & (df.index < end_ts)]
        return sliced.copy()
