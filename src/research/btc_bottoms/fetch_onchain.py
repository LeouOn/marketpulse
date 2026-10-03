"""Keyless real on-chain + derivatives data for the BTC bottoms frame.

Two verified sources (both probed live 2026-10-03 from this host):

* **Coin Metrics community API** (no key): daily ``CapMVRVCur`` (MVRV ratio)
  and ``CapMrktCurUSD`` (market cap) for BTC, full history from 2010-07-18,
  served in one ``page_size=10000`` page with a ``next_page_url`` cursor.
  These are REAL series -- unlike ``on_chain.fetch_mvrv`` /
  ``data/cache/btc/mvrv.csv``, which are synthetic and must never be read.
* **Kraken Futures public API** (no key): hourly funding for ``PF_XBTUSD``
  with ``relativeFundingRate`` (dimensionless fraction per interval), a
  rolling ~1-year window (8799 records at probe time). Binance and Bybit are
  geo-blocked from this host; OKX's public funding history only reaches
  ~3 months back, so Kraken is the deepest keyless source available.

Funding events are timestamped at the END of their interval (00:00/06:00/…
UTC for Kraken), so every event stamped within UTC day D is known by the end
of day D; ``aggregate_funding_hourly`` sums the day's interval rates into a
daily total funding fraction. Series are returned *unshifted* -- all
point-in-time lag decisions live in :mod:`src.research.btc_bottoms.frame`.
"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import requests
from loguru import logger

from src.research.data._paths import cache_dir

__all__ = ["fetch_coinmetrics", "fetch_kraken_funding", "aggregate_funding_hourly"]

_CM_URL = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
_CM_METRICS = ["CapMVRVCur", "CapMrktCurUSD"]
_KRAKEN_URL = "https://futures.kraken.com/derivatives/api/v4/historicalfundingrates"
_KRAKEN_SYMBOL = "PF_XBTUSD"
_TIMEOUT = 60


def _cm_cache() -> Path:
    return cache_dir("btc_bottoms") / "coinmetrics.parquet"


def _funding_cache() -> Path:
    return cache_dir("btc_bottoms") / "funding.parquet"


def _read_parquet(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as exc:
        logger.warning(f"[btc_bottoms] corrupt cache {path}: {exc}")
        return None


def fetch_coinmetrics(refresh: bool = False) -> dict[str, pd.Series]:
    """Return ``{"mvrv": Series, "mcap_usd": Series}`` from the community API.

    Daily values, index = the API's ``time`` date (00:00 UTC boundary).
    Degrades to ``{}`` on failure -- the frame leaves the columns NaN.
    """
    path = _cm_cache()
    if not refresh:
        cached = _read_parquet(path)
        if cached is not None and not cached.empty:
            return {"mvrv": cached["mvrv"], "mcap_usd": cached["mcap_usd"]}

    url: str | None = _CM_URL
    params = {
        "assets": "btc",
        "metrics": ",".join(_CM_METRICS),
        "frequency": "1d",
        "page_size": 10000,
    }
    rows: list[dict] = []
    try:
        while url is not None:
            resp = requests.get(url, params=params, timeout=_TIMEOUT)
            resp.raise_for_status()
            payload = resp.json()
            rows.extend(payload.get("data", []))
            url = payload.get("next_page_url")
            params = None  # next_page_url already carries the query string
            if payload.get("next_page_token") is None:
                break
    except Exception as exc:
        logger.warning(f"[btc_bottoms] Coin Metrics community fetch failed: {exc}")
        cached = _read_parquet(path)
        if cached is not None and not cached.empty:
            return {"mvrv": cached["mvrv"], "mcap_usd": cached["mcap_usd"]}
        return {}

    if not rows:
        logger.warning("[btc_bottoms] Coin Metrics returned no rows")
        return {}

    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["time"]).dt.tz_localize(None).dt.normalize()
    df = df.drop_duplicates(subset="ts").sort_values("ts").set_index("ts")
    out = pd.DataFrame(
        {
            "mvrv": pd.to_numeric(df["CapMVRVCur"], errors="coerce"),
            "mcap_usd": pd.to_numeric(df["CapMrktCurUSD"], errors="coerce"),
        }
    ).dropna(how="all")
    tmp = path.with_suffix(".parquet.tmp")
    out.to_parquet(tmp)
    tmp.replace(path)
    logger.info(f"[btc_bottoms] Coin Metrics: {len(out)} days, {out.index.min().date()} -> {out.index.max().date()}")
    return {"mvrv": out["mvrv"], "mcap_usd": out["mcap_usd"]}


def aggregate_funding_hourly(rates: pd.Series) -> pd.Series:
    """Sum tz-aware hourly funding rates into naive daily totals.

    The event stamped T closed the interval ending T, so all events stamped
    within day D are known by the end of day D.
    """
    if rates.empty:
        return pd.Series(dtype=float, name="funding_rate")
    s = rates.dropna().sort_index()
    days = s.index.tz_convert(None).normalize() if s.index.tz is not None else s.index.normalize()
    daily = s.groupby(days).sum()
    daily.index.name = "ts"
    return daily.rename("funding_rate")


def fetch_kraken_funding(refresh: bool = False) -> pd.Series:
    """Daily summed funding rate for BTC perps from Kraken's public API.

    Returns an empty Series on failure (column left honestly NaN).
    """
    path = _funding_cache()
    if not refresh:
        cached = _read_parquet(path)
        if cached is not None and not cached.empty:
            return cached["funding_rate"]

    rows: list[dict] = []
    try:
        resp = requests.get(_KRAKEN_URL, params={"symbol": _KRAKEN_SYMBOL}, timeout=_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
        rows = payload.get("rates", [])
    except Exception as exc:
        logger.warning(f"[btc_bottoms] Kraken funding fetch failed: {exc}")
        cached = _read_parquet(path)
        if cached is not None and not cached.empty:
            return cached["funding_rate"]
        return pd.Series(dtype=float, name="funding_rate")

    if not rows:
        logger.warning("[btc_bottoms] Kraken returned no funding rows")
        return pd.Series(dtype=float, name="funding_rate")

    hourly = pd.Series(
        [float(r["relativeFundingRate"]) for r in rows],
        index=pd.to_datetime([r["timestamp"] for r in rows], utc=True),
        name="relativeFundingRate",
    ).sort_index()
    daily = aggregate_funding_hourly(hourly)
    out = daily.to_frame()
    tmp = path.with_suffix(".parquet.tmp")
    out.to_parquet(tmp)
    tmp.replace(path)
    logger.info(
        f"[btc_bottoms] Kraken funding: {len(hourly)} hourly events -> {len(daily)} days, "
        f"{daily.index.min().date()} -> {daily.index.max().date()}"
    )
    return daily


# Keep import-time side effects impossible: the module only defines functions.
_ = time  # noqa: F841  (reserved for future rate-limit pacing; see contract)
