"""Fetch and cache Hong Kong macro + developer equity data for the HK property model.

Two data sources:
  1. FRED REST API (BIS HK residential property indices, HK credit, exchange rates)
  2. yfinance (Hang Seng Index, iShares Hong Kong ETF, HK developer equities)

Each series is cached as parquet under data/macro/ (FRED) or data/yahoo_cache/ (Yahoo),
using the Metis OHLCV contract (ts, open, high, low, close, volume, source) so the
HK model script can load them with the same loader as bay_area_risk_v3.py.

DATA DISCOVERY NOTES (what we found searching FRED in June 2026):
  - The task spec IDs (QHKG628BIS, MANMM101HKM189S, INTGSBHKM193N, HKGEXPGSA) DO NOT
    EXIST on FRED -- all return 400 "series does not exist". The correct BIS IDs are
    QHKN628BIS (nominal) and QHKR628BIS (real), where N=Nominal/R=Real.
  - QHKN368BIS / QHKR368BIS also exist but their values go NEGATIVE recently (looks
    like a gap/ratio measure, not a level). We skip them.
  - FRED has NO monthly HK property index -- BIS only publishes quarterly. We use the
    quarterly BIS index as the primary HK property series (NOT a proxy).
  - Yahoo Finance provides daily HK developer equities (Sun Hung Kai 0016.HK,
    Henderson 0012.HK, CK Asset 1113.HK, New World 0017.HK, Swire 0019.HK) and the
    Hang Seng Index (^HSI) and iShares MSCI Hong Kong ETF (EWH) -- all of which we use
    as additional high-frequency property-sector proxies.

API stewardship: each series is cached; if the parquet exists and is recent enough
(<200 days old for FRED monthly/quarterly, <1 day old for Yahoo), no API call is made.
Delete the parquet to force a refetch.

This script fetches RAW data only. It does NOT modify FredProvider.SUPPORTED_SERIES
or AssetRegistry -- exploratory analysis only.
"""
from __future__ import annotations

import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests
import yfinance

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.research.data.fred import FredProvider

MACRO_DIR = PROJECT_ROOT / "data" / "macro"
YAHOO_DIR = PROJECT_ROOT / "data" / "yahoo_cache"
MACRO_DIR.mkdir(parents=True, exist_ok=True)
YAHOO_DIR.mkdir(parents=True, exist_ok=True)

# Fetch full available history. BIS HK series start 1979-80; Yahoo HK developers
# typically start late 1990s / early 2000s.
FETCH_START = date(1979, 1, 1)
FETCH_END = date.today()

# ---------------------------------------------------------------------------
# FRED HK series discovered via /fred/series/search?search_text=...
# (the spec IDs were wrong; these are the REAL ones that exist)
# ---------------------------------------------------------------------------

FRED_HK_SERIES = [
    # PRIMARY: BIS HK residential property price index (NOMINAL, quarterly)
    # 1979-Q4 to 2025-Q4 (current). Values 10.9 (1980) -> 197.3 (2025-Q4).
    # Captures: 1997 AFC (-50%), 2003 SARS (-30%), 2008 GFC, 2010-18 boom,
    # 2019 protests, 2022-24 correction. THE definitive HK property series.
    ("QHKN628BIS",  "BIS HK Nominal Residential Property Prices (quarterly)",   "quarterly"),
    # Real (CPI-deflated) version of the same index. Same window.
    ("QHKR628BIS",  "BIS HK Real Residential Property Prices (quarterly)",      "quarterly"),
    # HK real broad effective exchange rate (monthly 1994-2026).
    # Captures HK competitiveness vs trading partners. Because HKD is pegged to
    # USD, the REAL exchange rate moves when HK inflation differs from trading
    # partners even though HKD/USD nominal is locked at 7.75-7.85.
    ("RBHKBIS",     "HK Real Broad Effective Exchange Rate (monthly)",          "monthly"),
    # HK nominal broad effective exchange rate (monthly 1994-2026).
    # Mostly tracks USD moves (since HKD is pegged). Shows when HK is "expensive"
    # vs Asia because USD is strong -- the 2022-23 USD surge hurt HK property.
    ("NBHKBIS",     "HK Nominal Broad Effective Exchange Rate (monthly)",       "monthly"),
    # HK household credit (quarterly 1990-2025).
    # Proxy for HK household leverage / mortgage exposure. 26 (1990) -> 375 (2025-Q4).
    # Hockey-stick growth -- key indicator of leverage-driven property risk.
    ("QHKHAMUSDA",  "HK Total Credit to Households (quarterly)",               "quarterly"),
    # HK total private non-financial sector credit (quarterly 1978-2025).
    # Broader leverage proxy (includes corporate + mortgage). 100 (1978) -> 328 (2025-Q4).
    ("QHKPAM770A",  "HK Total Credit to Private Non-Fin Sector (quarterly)",   "quarterly"),
]

# ---------------------------------------------------------------------------
# Yahoo tickers: HK developer equities + benchmarks
# ---------------------------------------------------------------------------

YAHOO_HK_TICKERS = [
    # iShares MSCI Hong Kong ETF (US-listed, USD). Best HK proxy for US investors.
    # Liquid, holds 40%+ property developers. Started Dec 1999.
    ("EWH",      "iShares MSCI Hong Kong ETF (USD)"),
    # Hang Seng Index -- HK broad equity benchmark. ~30% weight in property/financials.
    ("^HSI",     "Hang Seng Index (HKD)"),
    # Sun Hung Kai Properties -- largest HK developer by market cap. Family-controlled.
    ("0016.HK",  "Sun Hung Kai Properties (largest HK developer)"),
    # Henderson Land -- second major HK developer (Lee Shau Kee family).
    ("0012.HK",  "Henderson Land Development"),
    # CK Asset Holdings -- Li Ka-shing property vehicle (post-Cheung Kong重组).
    ("1113.HK",  "CK Asset Holdings (Li Ka-shing)"),
    # New World Development -- Cheng family developer.
    ("0017.HK",  "New World Development"),
    # Swire Properties -- primary Central/Admiralty office + retail landlord.
    ("1972.HK",  "Swire Properties (CBD office/retail)"),
    # BTC and S&P 500 -- for cross-asset correlations vs HK property.
    ("BTC-USD",  "Bitcoin (USD) -- cross-asset comparison"),
    ("SPY",      "SPDR S&P 500 ETF -- global equity benchmark"),
]


# ---------------------------------------------------------------------------
# FRED fetch (mirrors fetch_bay_area_metros.fetch_observations)
# ---------------------------------------------------------------------------


def fetch_fred_observations(series_id: str, api_key: str, start: date, end: date) -> pd.DataFrame:
    """Hit FRED series/observations endpoint directly, return Metis-shape DataFrame.

    Returns columns: ts, open, high, low, close, volume, source (O=H=L=C for index
    data; volume is NaN; source=f"fred:{series_id}").
    """
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
    obs = r.json().get("observations", [])
    if not obs:
        return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume", "source"])

    rows = []
    for o in obs:
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


def cache_covers_fred(path: Path, requested_start: date) -> bool:
    """FRED cache freshness check (mirrors fetch_bay_area_metros.cache_covers)."""
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
    start_gap_days = abs((cache_start - requested_start).days)
    age_days = (today - cache_end).days
    # 200 days covers BOTH monthly and quarterly publication lags generously.
    return start_gap_days <= 180 and age_days <= 200


# ---------------------------------------------------------------------------
# Yahoo fetch (mirrors YahooProvider._to_contract)
# ---------------------------------------------------------------------------


def fetch_yahoo_ticker(ticker: str, start: date, end: date) -> pd.DataFrame:
    """Fetch daily OHLCV via yfinance, return Metis-shape DataFrame."""
    # yfinance end is exclusive; add a day to include today.
    end_iso = (end + timedelta(days=1)).isoformat()
    raw = yfinance.download(
        ticker,
        start=start.isoformat(),
        end=end_iso,
        progress=False,
        auto_adjust=False,
    )
    if raw is None or raw.empty:
        return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume", "source"])

    df = raw.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    date_col = df.index.name or "Date"
    df = df.reset_index().rename(columns={date_col: "ts"})

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
    df = df.dropna(subset=["close"])
    if "volume" not in df.columns:
        df["volume"] = float("nan")
    df["source"] = f"yahoo:{ticker}"
    return df[["ts", "open", "high", "low", "close", "volume", "source"]].reset_index(drop=True)


def cache_covers_yahoo(path: Path) -> bool:
    """Yahoo cache freshness: refetch if older than 1 day (live fills)."""
    if not path.exists():
        return False
    try:
        df = pd.read_parquet(path)
    except Exception:
        return False
    if df.empty:
        return False
    age_days = (time.time() - path.stat().st_mtime) / 86400.0
    return age_days < 1.0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    fp = FredProvider()
    key = fp.api_key
    print(f"Using FRED key: prefix={key[:6]}... len={len(key)}")
    print(f"Macro cache:   {MACRO_DIR}")
    print(f"Yahoo cache:   {YAHOO_DIR}")
    print()

    print("=" * 80)
    print("FRED HK SERIES")
    print("=" * 80)
    for series_id, label, freq in FRED_HK_SERIES:
        path = MACRO_DIR / f"{series_id}.parquet"
        if cache_covers_fred(path, FETCH_START):
            existing = pd.read_parquet(path)
            print(f"  [CACHE] {series_id:<14} ({label})")
            print(f"          {len(existing)} rows, "
                  f"{existing['ts'].min().date()} to {existing['ts'].max().date()}")
            continue

        print(f"  [FETCH] {series_id:<14} ({label}) [{FETCH_START} to {FETCH_END}]...")
        try:
            df = fetch_fred_observations(series_id, key, FETCH_START, FETCH_END)
        except requests.HTTPError as e:
            print(f"          HTTP ERROR: {e.response.status_code} {e.response.text[:120]}")
            continue
        except Exception as e:
            print(f"          ERROR: {type(e).__name__}: {e}")
            continue

        if df.empty:
            print("          NO DATA returned")
            continue

        tmp = path.with_suffix(path.suffix + ".tmp")
        df.to_parquet(tmp, index=False)
        tmp.replace(path)
        print(f"          OK: {len(df)} rows, "
              f"{df['ts'].min().date()} to {df['ts'].max().date()}  ->  {path.name}")

    print()
    print("=" * 80)
    print("YAHOO HK TICKERS")
    print("=" * 80)
    # yfinance rate-limits aggressively in 2026; sleep between calls.
    for ticker, label in YAHOO_HK_TICKERS:
        path = YAHOO_DIR / f"{ticker}.parquet"
        if cache_covers_yahoo(path):
            existing = pd.read_parquet(path)
            print(f"  [CACHE] {ticker:<10} ({label})")
            print(f"          {len(existing)} rows, "
                  f"{existing['ts'].min().date()} to {existing['ts'].max().date()}")
            continue

        print(f"  [FETCH] {ticker:<10} ({label})...")
        try:
            df = fetch_yahoo_ticker(ticker, date(1995, 1, 1), FETCH_END)
        except Exception as e:
            print(f"          ERROR: {type(e).__name__}: {e}")
            time.sleep(2.0)
            continue

        if df.empty:
            print("          NO DATA returned (may be a delisted/unknown symbol)")
            time.sleep(2.0)
            continue

        tmp = path.with_suffix(path.suffix + ".tmp")
        df.to_parquet(tmp, index=False)
        tmp.replace(path)
        print(f"          OK: {len(df)} rows, "
              f"{df['ts'].min().date()} to {df['ts'].max().date()}  ->  {path.name}")
        time.sleep(2.0)  # be polite to yahoo

    # Summary
    print()
    print("=" * 80)
    print("CACHE SUMMARY")
    print("=" * 80)
    print("\nFRED macro:")
    for series_id, label, _ in FRED_HK_SERIES:
        p = MACRO_DIR / f"{series_id}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            print(f"  {series_id:<14} {len(df):>5} rows  "
                  f"{df['ts'].min().date()} to {df['ts'].max().date()}  {label}")
        else:
            print(f"  {series_id:<14} MISSING  ({label})")
    print("\nYahoo:")
    for ticker, label in YAHOO_HK_TICKERS:
        p = YAHOO_DIR / f"{ticker}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            print(f"  {ticker:<10} {len(df):>5} rows  "
                  f"{df['ts'].min().date()} to {df['ts'].max().date()}  {label}")
        else:
            print(f"  {ticker:<10} MISSING  ({label})")


if __name__ == "__main__":
    main()
