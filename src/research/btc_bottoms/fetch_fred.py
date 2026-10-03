"""Thin FRED series fetcher for the BTC bottoms frame.

``FredProvider`` (``src/research.data.fred``) locks its series whitelist for
the multi-asset lab; the BTC study needs five series outside it
(``BAMLH0A0HYM2``, ``DGS2``, ``WALCL``, ``WTREGEN``, ``RRPONTSYD``). Rather
than widen a shared whitelist from this package, this module fetches directly
through :mod:`fredapi` with the same conventions:

* key lookup via :func:`src.core.keys.get_macro_key` (env -> .env -> yaml);
  a missing key is an honest absence (empty result), never a crash, and the
  key value is never logged;
* one parquet per series under ``data/cache/btc_bottoms/fred/``;
* fetch failures fall back to the stale cache when one exists.

Series are returned *unshifted*, indexed by observation date -- every
point-in-time lag decision lives in :mod:`src.research.btc_bottoms.frame`.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from loguru import logger

from src.core.keys import get_macro_key
from src.research.data._paths import cache_dir

__all__ = ["SERIES_DAILY", "SERIES_WEEKLY", "fetch_series"]

# Frame column -> FRED series id. Daily market series shift +1; weekly
# Wednesday-observed balance-sheet series shift +2 (see frame.LAG_TABLE).
SERIES_DAILY: dict[str, str] = {
    "dgs10": "DGS10",
    "dfii10": "DFII10",
    "t10yie": "T10YIE",
    "dgs2": "DGS2",
    "vix": "VIXCLS",
    "hy_oas": "BAMLH0A0HYM2",
    "baa10y": "BAA10Y",
    "dxy": "DTWEXBGS",
    "rrp_onday": "RRPONTSYD",
}
SERIES_WEEKLY: dict[str, str] = {
    "walcl": "WALCL",
    "wtregen": "WTREGEN",
}


def _cache_path(series_id: str) -> Path:
    return cache_dir("btc_bottoms/fred") / f"{series_id}.parquet"


def _read_cache(path: Path) -> pd.Series | None:
    if not path.exists():
        return None
    try:
        s = pd.read_parquet(path)["value"]
        s.index = pd.to_datetime(s.index)
        return s.sort_index()
    except Exception as exc:
        logger.warning(f"[btc_bottoms] corrupt FRED cache {path}: {exc}")
        return None


def fetch_series(series_id: str, refresh: bool = False) -> pd.Series | None:
    """Fetch one FRED series (full history), parquet-cached.

    Returns ``None`` when no key is configured or the fetch fails with no
    usable cache -- the frame then leaves the column honestly NaN.
    """
    path = _cache_path(series_id)
    if not refresh:
        cached = _read_cache(path)
        if cached is not None and not cached.empty:
            return cached

    key = get_macro_key("FRED_API_KEY")
    if not key:
        logger.warning(f"[btc_bottoms] FRED_API_KEY not configured; series {series_id} will be absent from the frame")
        return _read_cache(path)

    try:
        from fredapi import Fred

        s = Fred(api_key=key).get_series(series_id)
    except Exception as exc:
        logger.warning(f"[btc_bottoms] FRED fetch failed for {series_id}: {exc}")
        return _read_cache(path)

    if s is None or s.empty:
        logger.warning(f"[btc_bottoms] FRED returned empty series for {series_id}")
        return _read_cache(path)

    s = s.dropna().sort_index()
    s.index.name = "ts"
    out = s.rename("value").to_frame()
    tmp = path.with_suffix(".parquet.tmp")
    out.to_parquet(tmp)
    tmp.replace(path)
    logger.info(f"[btc_bottoms] FRED {series_id}: {len(s)} obs, {s.index.min().date()} -> {s.index.max().date()}")
    return s
