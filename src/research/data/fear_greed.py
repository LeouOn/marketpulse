"""Crypto Fear & Greed Index data fetcher with CSV caching.

Source: https://alternative.me/crypto/fear-and-greed-index/

The API endpoint ``https://api.alternative.me/fng/?limit=0`` returns ALL
available daily FGI values (≈2 000+ days, starting from 2018-02-01).

Output: local CSV at ``data/btc/fear_greed.csv`` with columns
``ts, fgi_value, classification``.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
import requests
from loguru import logger

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

DATA_DIR = Path("data/btc")
FGI_CSV = DATA_DIR / "fear_greed.csv"
FGI_API_URL = "https://api.alternative.me/fng/?limit=0"
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


def _read_cache(path: Path) -> pd.DataFrame:
    """Read a cached CSV. Empty DataFrame if file is missing or corrupt."""
    if not path.exists():
        return pd.DataFrame(columns=["ts", "fgi_value", "classification"])
    try:
        df = pd.read_csv(path, parse_dates=["ts"])
    except Exception as exc:
        logger.warning(f"Corrupt CSV cache {path}: {exc}; returning empty DataFrame")
        return pd.DataFrame(columns=["ts", "fgi_value", "classification"])
    df = df.drop_duplicates(subset=["ts"]).sort_values("ts").reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fetch_fear_greed(force: bool = False) -> pd.DataFrame:
    """Fetch the Crypto Fear & Greed Index, with local CSV caching.

    Args:
        force: If ``True``, re-fetch from the API even if a cache exists.

    Returns:
        DataFrame with columns ``ts`` (datetime), ``fgi_value`` (int 0-100),
        ``classification`` (string).
    """
    # Return cached data if available and not forced.
    if not force and FGI_CSV.exists():
        cached = _read_cache(FGI_CSV)
        if not cached.empty:
            logger.info(f"FGI: returning {len(cached)} rows from cache")
            return cached

    # Fetch from API.
    logger.info("FGI: fetching from alternative.me API")
    try:
        resp = requests.get(FGI_API_URL, timeout=REQ_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        logger.warning(f"FGI fetch failed: {exc}")
        # If we have stale cache, return it; otherwise empty.
        if FGI_CSV.exists():
            logger.warning("FGI: returning stale cache due to fetch error")
            return _read_cache(FGI_CSV)
        return pd.DataFrame(columns=["ts", "fgi_value", "classification"])

    data = payload.get("data", [])
    if not data:
        logger.warning("FGI: API returned empty data list")
        return pd.DataFrame(columns=["ts", "fgi_value", "classification"])

    rows = []
    for entry in data:
        ts_unix = entry.get("timestamp")
        value = entry.get("value")
        classification = entry.get("value_classification", "")
        if ts_unix is None or value is None:
            continue
        rows.append(
            {
                "ts": pd.Timestamp(int(ts_unix), unit="s"),
                "fgi_value": int(value),
                "classification": str(classification),
            }
        )

    if not rows:
        return pd.DataFrame(columns=["ts", "fgi_value", "classification"])

    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["ts"]).sort_values("ts").reset_index(drop=True)
    _write_cache(df, FGI_CSV)
    logger.info(f"FGI: fetched and cached {len(df)} rows ({df['ts'].min().date()} -> {df['ts'].max().date()})")
    return df
