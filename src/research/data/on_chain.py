"""On-chain metrics data fetchers with CSV caching.

Sources
-------
- Glassnode free API: ``https://api.glassnode.com/v1/metrics/...``
  The free tier provides limited historical data without an API key for
  some endpoints. When the API is unavailable (no key, rate-limited, or
  network failure), fetchers fall back to a deterministic synthetic series
  so that downstream code never crashes.

Metrics
-------
- **MVRV Z-score**: (market_value - realized_value) / std_dev.
  Range typically [-1, 7]. Low values indicate undervaluation.
- **Puell Multiple**: daily_issuance_usd / 365d_MA(daily_issuance_usd).
  Range typically [0.3, 5]. Low values indicate miner capitulation.

Output
------
- ``data/btc/mvrv.csv``  — columns ``ts, mvrv_z``
- ``data/btc/puell.csv``  — columns ``ts, puell``

Both fetchers also return a ``source`` column on the in-memory DataFrame
tagging each row's provenance: ``"real"`` (API-fetched), ``"cache"``
(served from local CSV), or ``"synthetic"`` (deterministic fallback).
The ``source`` column is not persisted to the CSV cache. Downstream code
(e.g. ``IndicatorProvider``) can inspect it to detect synthetic data and
warn the user that backtest results may not be meaningful.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from loguru import logger

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

DATA_DIR = Path("data/btc")
MVRV_CSV = DATA_DIR / "mvrv.csv"
PUELL_CSV = DATA_DIR / "puell.csv"

MVRV_API_URL = (
    "https://api.glassnode.com/v1/metrics/market/mvrv_z_score?a=BTC&i=24h"
)
PUELL_API_URL = (
    "https://api.glassnode.com/v1/metrics/mining/puell_multiple?a=BTC&i=24h"
)

REQ_TIMEOUT = 30


# ---------------------------------------------------------------------------
# CSV cache helpers
# ---------------------------------------------------------------------------


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _write_cache(df: pd.DataFrame, path: Path) -> None:
    """Write the cache atomically (write to .tmp, then replace)."""
    _ensure_data_dir()
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp, index=False, quoting=csv.QUOTE_MINIMAL)
    tmp.replace(path)


def _read_mvrv_cache(path: Path) -> pd.DataFrame:
    """Read MVRV CSV cache. Empty DataFrame if missing or corrupt."""
    if not path.exists():
        return pd.DataFrame(columns=["ts", "mvrv_z"])
    try:
        df = pd.read_csv(path, parse_dates=["ts"])
    except Exception as exc:
        logger.warning(f"Corrupt MVRV CSV cache {path}: {exc}; returning empty DataFrame")
        return pd.DataFrame(columns=["ts", "mvrv_z"])
    df = df.drop_duplicates(subset=["ts"]).sort_values("ts").reset_index(drop=True)
    return df


def _read_puell_cache(path: Path) -> pd.DataFrame:
    """Read Puell CSV cache. Empty DataFrame if missing or corrupt."""
    if not path.exists():
        return pd.DataFrame(columns=["ts", "puell"])
    try:
        df = pd.read_csv(path, parse_dates=["ts"])
    except Exception as exc:
        logger.warning(f"Corrupt Puell CSV cache {path}: {exc}; returning empty DataFrame")
        return pd.DataFrame(columns=["ts", "puell"])
    df = df.drop_duplicates(subset=["ts"]).sort_values("ts").reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Synthetic fallback generators
# ---------------------------------------------------------------------------


def _synthetic_mvrv(n_days: int = 2500) -> pd.DataFrame:
    """Deterministic synthetic MVRV Z-score series.

    Approximates BTC's historical MVRV cycle using a sine wave with a
    linearly decaying amplitude, superimposed on a baseline of ~1.0.
    This is NOT real data — it exists so that tests and offline runs
    have something to work with.
    """
    rng = np.random.default_rng(42)
    dates = pd.date_range(end=pd.Timestamp.now(), periods=n_days, freq="D")
    # Halving-cycle periodicity (~4 years = 1461 days)
    t = np.arange(n_days)
    cycle = np.sin(2 * np.pi * t / 1461)
    # Amplitude decays as market matures
    amp = 2.5 * np.exp(-t / 5000)
    mvrv_z = 1.0 + amp * cycle + rng.normal(0, 0.2, n_days)
    return pd.DataFrame({"ts": dates, "mvrv_z": mvrv_z})


def _synthetic_puell(n_days: int = 2500) -> pd.DataFrame:
    """Deterministic synthetic Puell Multiple series.

    Approximates BTC's historical Puell cycle. Low values (~0.4) indicate
    miner capitulation (good buy signal); high values (~3+) indicate
    overheated issuance economics.
    """
    rng = np.random.default_rng(43)
    dates = pd.date_range(end=pd.Timestamp.now(), periods=n_days, freq="D")
    t = np.arange(n_days)
    cycle = np.sin(2 * np.pi * t / 1461 + np.pi / 4)
    amp = 1.2 * np.exp(-t / 6000)
    puell = 1.0 + amp * cycle + rng.normal(0, 0.15, n_days)
    puell = np.clip(puell, 0.1, 6.0)
    return pd.DataFrame({"ts": dates, "puell": puell})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fetch_mvrv(force: bool = False) -> pd.DataFrame:
    """Fetch MVRV Z-score with local CSV caching.

    Args:
        force: If ``True``, re-fetch from the API even if a cache exists.

    Returns:
        DataFrame with columns ``ts`` (datetime), ``mvrv_z`` (float),
        and ``source`` (str). The ``source`` column tags data provenance:
        ``"real"`` for API-fetched rows, ``"cache"`` for rows served from
        the local CSV cache, and ``"synthetic"`` for the deterministic
        fallback series used when both API and cache are unavailable.
        Downstream code can inspect ``df["source"]`` to avoid silently
        running on synthetic noise.
    """
    # Return cached data if available and not forced.
    if not force and MVRV_CSV.exists():
        cached = _read_mvrv_cache(MVRV_CSV)
        if not cached.empty:
            logger.info(f"MVRV: returning {len(cached)} rows from cache")
            cached["source"] = "cache"
            return cached

    # Fetch from API.
    logger.info("MVRV: fetching from Glassnode API")
    try:
        resp = requests.get(MVRV_API_URL, timeout=REQ_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        logger.warning(f"MVRV fetch failed: {exc}")
        if MVRV_CSV.exists():
            logger.warning("MVRV: returning stale cache due to fetch error")
            stale = _read_mvrv_cache(MVRV_CSV)
            stale["source"] = "cache"
            return stale
        # Fall back to synthetic series
        logger.warning("MVRV: using synthetic fallback")
        df = _synthetic_mvrv()
        df["source"] = "synthetic"
        return df

    # Parse Glassnode response — list of {t: unix_timestamp, v: value}
    rows = []
    if isinstance(payload, list):
        for entry in payload:
            ts_unix = entry.get("t")
            value = entry.get("v")
            if ts_unix is None or value is None:
                continue
            rows.append(
                {
                    "ts": pd.Timestamp(int(ts_unix), unit="s"),
                    "mvrv_z": float(value),
                }
            )
    elif isinstance(payload, dict) and "error" in payload:
        logger.warning(f"MVRV API error: {payload['error']}")
        if MVRV_CSV.exists():
            stale = _read_mvrv_cache(MVRV_CSV)
            stale["source"] = "cache"
            return stale
        df = _synthetic_mvrv()
        df["source"] = "synthetic"
        return df

    if not rows:
        logger.warning("MVRV: API returned no data; using synthetic fallback")
        if MVRV_CSV.exists():
            stale = _read_mvrv_cache(MVRV_CSV)
            stale["source"] = "cache"
            return stale
        df = _synthetic_mvrv()
        df["source"] = "synthetic"
        return df

    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["ts"]).sort_values("ts").reset_index(drop=True)
    df["source"] = "real"
    _write_cache(df, MVRV_CSV)
    logger.info(f"MVRV: fetched and cached {len(df)} rows ({df['ts'].min().date()} -> {df['ts'].max().date()})")
    return df


def fetch_puell(force: bool = False) -> pd.DataFrame:
    """Fetch Puell Multiple with local CSV caching.

    Args:
        force: If ``True``, re-fetch from the API even if a cache exists.

    Returns:
        DataFrame with columns ``ts`` (datetime), ``puell`` (float),
        and ``source`` (str). The ``source`` column tags data provenance:
        ``"real"`` for API-fetched rows, ``"cache"`` for rows served from
        the local CSV cache, and ``"synthetic"`` for the deterministic
        fallback series used when both API and cache are unavailable.
        Downstream code can inspect ``df["source"]`` to avoid silently
        running on synthetic noise.
    """
    # Return cached data if available and not forced.
    if not force and PUELL_CSV.exists():
        cached = _read_puell_cache(PUELL_CSV)
        if not cached.empty:
            logger.info(f"Puell: returning {len(cached)} rows from cache")
            cached["source"] = "cache"
            return cached

    # Fetch from API.
    logger.info("Puell: fetching from Glassnode API")
    try:
        resp = requests.get(PUELL_API_URL, timeout=REQ_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        logger.warning(f"Puell fetch failed: {exc}")
        if PUELL_CSV.exists():
            logger.warning("Puell: returning stale cache due to fetch error")
            stale = _read_puell_cache(PUELL_CSV)
            stale["source"] = "cache"
            return stale
        logger.warning("Puell: using synthetic fallback")
        df = _synthetic_puell()
        df["source"] = "synthetic"
        return df

    # Parse Glassnode response
    rows = []
    if isinstance(payload, list):
        for entry in payload:
            ts_unix = entry.get("t")
            value = entry.get("v")
            if ts_unix is None or value is None:
                continue
            rows.append(
                {
                    "ts": pd.Timestamp(int(ts_unix), unit="s"),
                    "puell": float(value),
                }
            )
    elif isinstance(payload, dict) and "error" in payload:
        logger.warning(f"Puell API error: {payload['error']}")
        if PUELL_CSV.exists():
            stale = _read_puell_cache(PUELL_CSV)
            stale["source"] = "cache"
            return stale
        df = _synthetic_puell()
        df["source"] = "synthetic"
        return df

    if not rows:
        logger.warning("Puell: API returned no data; using synthetic fallback")
        if PUELL_CSV.exists():
            stale = _read_puell_cache(PUELL_CSV)
            stale["source"] = "cache"
            return stale
        df = _synthetic_puell()
        df["source"] = "synthetic"
        return df

    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["ts"]).sort_values("ts").reset_index(drop=True)
    df["source"] = "real"
    _write_cache(df, PUELL_CSV)
    logger.info(f"Puell: fetched and cached {len(df)} rows ({df['ts'].min().date()} -> {df['ts'].max().date()})")
    return df
