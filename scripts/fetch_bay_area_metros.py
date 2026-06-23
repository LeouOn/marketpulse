"""Fetch and cache Case-Shiller metro + SF tier + Oakland FHFA series from FRED.

Caches each series as parquet at data/macro/<ID>.parquet using the Metis
OHLCV contract (ts, open, high, low, close, volume, source) - same shape as
existing CSUSHPINSA.parquet so v3 can load them with the same loader.

API stewardship: each series is cached; if the parquet exists and covers
the requested window, no API call is made. Just delete the parquet to
force a refetch.

This script fetches RAW data only. It does NOT add the series to
FredProvider.SUPPORTED_SERIES - that's a separate refactor.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.research.data.fred import FredProvider

CACHE_DIR = PROJECT_ROOT / "data" / "macro"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Full available history - Case-Shiller metros start 1987/1990/2000, FHFA 1975.
# We fetch the maximum range FRED has; analysis script slices as needed.
FETCH_START = date(1987, 1, 1)
FETCH_END = date(2026, 6, 1)

# Series to cache for the Bay Area v3 analysis.
# (series_id, label, frequency, fetch_start_override)
SERIES = [
    # National baseline - refetch at FULL history so v3 can compute long-window betas
    # (existing cache only had 2015-2026; overwriting with 1987-2026 is SAFE because
    # cache_covers() still passes for any 2015-2026 production request)
    ("CSUSHPINSA", "National Case-Shiller (NSA)",          "monthly",   None),
    # Primary SF Bay Area - Case-Shiller metros (monthly)
    ("SFXRNSA",   "SF Case-Shiller (NSA)",                 "monthly",   None),
    ("LXXRNSA",   "LA Case-Shiller (NSA)",                 "monthly",   None),
    ("SEXRNSA",   "Seattle Case-Shiller (NSA)",            "monthly",   date(1990, 1, 1)),
    ("LVXRNSA",   "Las Vegas Case-Shiller (NSA)",          "monthly",   None),
    ("PHXRNSA",   "Phoenix Case-Shiller (NSA)",            "monthly",   date(1989, 1, 1)),
    ("SDXRNSA",   "San Diego Case-Shiller (NSA)",          "monthly",   None),
    ("POXRNSA",   "Portland Case-Shiller (NSA)",           "monthly",   None),
    # SF price tiers (monthly, NSA) - replaces v2 hand-waved "SF condo" / "SF SFH"
    ("SFXRHTNSA", "SF High Tier (NSA)",                    "monthly",   None),
    ("SFXRMTNSA", "SF Middle Tier (NSA)",                  "monthly",   None),
    ("SFXRLTNSA", "SF Low Tier (NSA)",                     "monthly",   None),
    ("SFXRCNSA",  "SF Condo (NSA)",                        "monthly",   date(1995, 1, 1)),
    # Oakland-Berkeley-Livermore MSA (FHFA, quarterly - analysis will resample)
    ("ATNHPIUS36084Q", "Oakland-Berkeley-Livermore FHFA",  "quarterly", date(1975, 1, 1)),
]


def fetch_observations(series_id: str, api_key: str, start: date, end: date) -> pd.DataFrame:
    """Hit FRED series/observations endpoint directly, return Metis-shape DataFrame."""
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start.isoformat(),
        "observation_end": end.isoformat(),
    }
    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    data = r.json()
    obs = data.get("observations", [])
    if not obs:
        return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume", "source"])

    rows = []
    for o in obs:
        # FRED returns "." for missing values
        v = o["value"]
        if v == ".":
            continue
        try:
            f = float(v)
        except ValueError:
            continue
        rows.append((o["date"], f))
    if not rows:
        return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume", "source"])

    df = pd.DataFrame(rows, columns=["date", "value"])
    df["ts"] = pd.to_datetime(df["date"])
    df = df.drop(columns="date").sort_values("ts").reset_index(drop=True)
    df["open"] = df["value"]
    df["high"] = df["value"]
    df["low"] = df["value"]
    df["close"] = df["value"]
    df["volume"] = float("nan")
    df["source"] = f"fred:{series_id}"
    return df[["ts", "open", "high", "low", "close", "volume", "source"]]


def cache_covers(path: Path, start: date, requested_end: date) -> bool:
    """True if cache covers `start` AND is "fresh enough" given FRED's publication lag.

    FRED publishes monthly Case-Shiller with ~2-3 month lag (Mar 2026 data lands
    late May 2026). Quarterly FHFA series lag ~4-6 months. We don't want to
    refetch every run just because the requested end is slightly beyond what
    FRED has. So: cache is "fresh enough" if its end is within 200 days of
    today (covers BOTH monthly and quarterly publication lags generously).

    The `requested_end` arg is kept for API symmetry but not used as a hard
    requirement - FRED will only ever return what it has.

    For `start`: FRED may not have data going back as far as requested
    (e.g. Oakland FHFA requested from 1975-01-01 but FRED only has from
    1975-04-01). We allow the cache start to be within ~6 months of the
    requested start to handle these cases without forcing a refetch.
    """
    if not path.exists():
        return False
    try:
        df = pd.read_parquet(path)
    except Exception:
        return False
    if df.empty:
        return False
    cache_start = df["ts"].min().date()
    cache_end = df["ts"].max().date()
    today = date.today()
    # Cache start must be at-or-before requested start, OR within 180 days of it
    # (FRED may not have data for the exact requested start date).
    start_gap_days = abs((cache_start - start).days)
    # End must be no more than 200 days old (covers monthly+quarterly pub lags).
    age_days = (today - cache_end).days
    return start_gap_days <= 180 and age_days <= 200


def main() -> None:
    fp = FredProvider()
    key = fp.api_key
    print(f"Using FRED key: prefix={key[:6]}... len={len(key)}")
    print(f"Cache dir: {CACHE_DIR}")
    print()

    for series_id, label, _freq, start_override in SERIES:
        start = start_override or FETCH_START
        path = CACHE_DIR / f"{series_id}.parquet"
        if cache_covers(path, start, FETCH_END):
            existing = pd.read_parquet(path)
            print(f"  [CACHE] {series_id:<18} ({label})")
            print(f"          {len(existing)} rows, "
                  f"{existing['ts'].min().date()} to {existing['ts'].max().date()}")
            continue

        print(f"  [FETCH] {series_id:<18} ({label}) [{start} to {FETCH_END}]...")
        try:
            df = fetch_observations(series_id, key, start, FETCH_END)
        except requests.HTTPError as e:
            print(f"          HTTP ERROR: {e.response.status_code} {e.response.text[:120]}")
            continue
        except Exception as e:
            print(f"          ERROR: {type(e).__name__}: {e}")
            continue

        if df.empty:
            print("          NO DATA returned")
            continue

        # Atomic write: .tmp then rename
        tmp = path.with_suffix(path.suffix + ".tmp")
        df.to_parquet(tmp, index=False)
        tmp.replace(path)

        print(f"          OK: {len(df)} rows, "
              f"{df['ts'].min().date()} to {df['ts'].max().date()}  ->  {path.name}")

    # Summary
    print()
    print("Cache summary:")
    for series_id, label, _, _ in SERIES:
        p = CACHE_DIR / f"{series_id}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            print(f"  {series_id:<18} {len(df):>5} rows  "
                  f"{df['ts'].min().date()} to {df['ts'].max().date()}  {label}")
        else:
            print(f"  {series_id:<18} MISSING")


if __name__ == "__main__":
    main()
