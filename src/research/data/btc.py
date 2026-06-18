"""BTC data provider wrapping existing fetchers in ``src.research.data.__init__``.

The existing BTC fetchers (``fetch_daily_yahoo``, ``fetch_hourly_cryptocompare``,
``fetch_hourly_kraken``, ``load_daily``, ``load_hourly``) stay in
``src/research/data/__init__.py`` for back-compat -- T2 explicitly preserved them
and many existing callers import them directly.

``BtcProvider`` exposes them via the :class:`src.research.data.DataProvider` ABC
so :data:`src.research.data.AssetRegistry` (T10) can reference BTC uniformly
alongside the other asset providers (FredProvider, AlpacaProvider, ...).

Spec: ``.omo/plans/multi-asset-macro-research-lab.md`` lines 1295-1356.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from src.research.data import DataProvider, load_daily, load_hourly


class BtcProvider(DataProvider):
    """BTC OHLCV provider -- 24/7 calendar, 365.25 trading days/year.

    A thin adapter: the real fetching/caching lives in
    :func:`src.research.data.load_daily` and
    :func:`src.research.data.load_hourly`. Those functions already return
    DataFrames in the Metis column contract (``ts, open, high, low, close,
    volume, source``), so no reshaping is needed here.

    Args:
        cache_dir: accepted for ABC signature symmetry with the other
            providers but **ignored** -- the existing fetchers manage their
            own cache at ``data/btc/{daily,hourly}.csv``.
    """

    def __init__(self, cache_dir: Path | None = None) -> None:
        # cache_dir intentionally ignored: existing fetchers own their cache.
        self.cache_dir: Path | None = cache_dir

    def load_daily(self, start: date, end: date) -> pd.DataFrame:
        """Delegate to the existing :func:`src.research.data.load_daily`.

        Returns a DataFrame already in the Metis column contract.
        """
        return load_daily(start=str(start), end=str(end))

    def load_intraday(self, start: date, end: date) -> pd.DataFrame | None:
        """Best-effort hourly load.

        Returns ``None`` if the hourly fetch fails for any reason (network,
        missing cache, rate limit). Callers that need daily-only data should
        use :meth:`load_daily` instead.
        """
        try:
            return load_hourly(start=str(start), end=str(end))
        except Exception:
            # Swallow -- DataProvider.load_intraday is documented as optional
            # and returns None when no intraday source is available.
            return None

    @property
    def trading_days_per_year(self) -> float:
        """BTC trades 24/7/365 -- annualisation factor is 365.25."""
        return 365.25
