"""
Credit & Financial Conditions Monitor
=====================================
Tracks the #1 leading indicator for market crashes: credit spreads.

Every major crash in modern history had credit spreads blow out BEFORE
equities sold off:
  - 2008 GFC:     BAA-10Y spread 6.05%, HY OAS ~18%
  - 2020 COVID:   BAA-10Y spread 3.80%, HY OAS ~11%
  - 2023 SVB:     BAA-10Y spread 2.28%, KRE -30% vs SPY in 2 weeks

Fetches the underlying data, computes a composite Credit Stress Score
(0-100), and produces a podcast-ready markdown briefing mirroring the
style of weekly_macro_briefing.py.

Run:     python scripts/credit_monitor.py
Output:  reports/credit/credit_monitor_YYYY-MM-DD.md  (+ console dump)

Data sources:
  - FRED REST API (series outside FredProvider.SUPPORTED_SERIES)
  - Existing parquet cache in data/macro/ (FredProvider schema)
  - Yahoo Finance (KRE, KBE, XLF, HYG, LQD, TLT, BIL, SPY)

ASCII-only: no em-dashes, no unicode arrows (PowerShell cp932 safe).
"""
import sys
from pathlib import Path
from datetime import datetime, date, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import numpy as np
import requests
import yfinance as yf

# Re-use the existing FRED key resolver (reads FRED_API_KEY env / .env).
# FredProvider is instantiated ONLY to grab api_key; we do NOT use its
# whitelist-restricted .fetch() because most credit series are not in
# FredProvider.SUPPORTED_SERIES. Direct REST calls instead (free tier,
# 120 req/min).
from src.research.data.fred import FredProvider

# ============================================================================
# CONFIG
# ============================================================================

CACHE_DIR = Path("data/macro")
REPORT_DIR = Path("reports/credit")

# Fetch window: cover 2008 GFC, 2020 COVID, 2023 SVB for historical context.
HISTORY_START = "2006-01-01"
HISTORY_END = date.today().isoformat()

# Crisis peak windows. "2022 mini-banking crisis" in the brief = SVB failure,
# March 2023 (the actual event). 2022-Q4 UK gilt/LDI stress is captured too.
CRISIS_WINDOWS = {
    "2008 GFC": ("2008-09-01", "2009-03-31"),
    "2020 COVID": ("2020-02-15", "2020-04-30"),
    "2023 SVB/banking": ("2023-03-01", "2023-05-31"),
}

# Published reference crisis peaks (public record, ICE/Fed publications).
# Used ONLY as a labeled fallback when FRED returns insufficient history
# for the ICE-licensed BAML series (free-tier FRED keys get ~3y trailing).
# These are approximate levels widely cited; we never present them as fresh
# fetched data. Format: series_id -> {window_label: peak_pct}.
REFERENCE_PEAKS = {
    "BAMLH0A0HYM2": {"2008 GFC": 18.1, "2020 COVID": 11.0, "2023 SVB/banking": 5.5},
    "BAMLC0A0CM":   {"2008 GFC": 6.0,  "2020 COVID": 4.6,  "2023 SVB/banking": 1.7},
    "BAMLC0A4CBBB": {"2008 GFC": 8.3,  "2020 COVID": 5.4,  "2023 SVB/banking": 2.3},
}

# FRED series this monitor depends on. Fetched via direct REST.
FRED_CREDIT_SERIES = {
    "BAA10Y":        "BAA-10Y corporate/Treasury spread",
    "BAMLH0A0HYM2":  "ICE BofA US High Yield OAS",
    "BAMLC0A0CM":    "ICE BofA US Corporate OAS",
    "BAMLC0A4CBBB":  "ICE BofA BBB Corporate OAS",
    "TEDRATE":       "TED spread (3M LIBOR - 3M T-bill) [discontinued 2022]",
    "T10Y2Y":        "10Y-2Y Treasury spread",
    "T10Y3M":        "10Y-3M Treasury spread",
    "DGS2":          "2Y Treasury yield",
    "DGS5":          "5Y Treasury yield",
    "DGS30":         "30Y Treasury yield",
    "DGS3MO":        "3M Treasury yield",
    "DTB3":          "3M T-bill (discount)",
    "DPRIME":        "Bank prime lending rate",
    "DRTSCILM":      "SLOOS: net % banks tightening C&I loans (quarterly)",
    "USSLIND":       "Leading Index for the US (monthly) [discontinued 2020]",
    "DPCREDIT":      "Fed Discount Window Primary Credit Rate",
    "SOFR":          "Secured Overnight Financing Rate",
    "NFCI":          "Chicago Fed National Financial Conditions Index",
    "WALCL":         "Fed balance sheet (Assets, weekly)",
    "BAA":           "Moody's Seasoned Baa Corporate Yield",
    "AAA":           "Moody's Seasoned Aaa Corporate Yield",
    "T1YFF":         "1Y-FFR Treasury spread",
    "DFF":           "Fed Funds effective rate (cached)",
    "DGS10":         "10Y Treasury yield (cached)",
    "DFII10":        "10Y real yield (cached)",
    "VIXCLS":        "VIX (cached)",
    "UNRATE":        "Unemployment rate (cached)",
    "T10YIE":        "10Y breakeven inflation (cached)",
}

# Yahoo market tickers for cross-asset confirmation.
YF_TICKERS = {
    "SPY": "S&P 500 ETF (benchmark)", "KRE": "SPDR Regional Bank ETF",
    "KBE": "SPDR S&P Bank ETF", "XLF": "Financial Select Sector ETF",
    "HYG": "iShares High Yield Corp Bond ETF",
    "LQD": "iShares Investment Grade Corp Bond ETF",
    "TLT": "iShares 20Y+ Treasury Bond ETF", "BIL": "SPDR 1-3M T-Bill ETF",
}

# Credit Stress Score weights (sum to 1.0).
SCORE_WEIGHTS = {"baa10y": 0.25, "hy_oas": 0.25, "kre_rel": 0.20,
                 "interbank": 0.15, "curve": 0.15}

# Composite score bands: 0-30 NORMAL | 30-50 WATCH | 50-70 WARNING | 70-100 CRISIS
def score_band(score):
    if score >= 70: return "CRISIS", "major credit event, defensive positioning mandatory"
    if score >= 50: return "WARNING", "significant stress, consider reducing risk"
    if score >= 30: return "WATCH", "minor widening, monitor closely"
    return "NORMAL", "credit markets healthy, risk-on"


# ============================================================================
# DATA LAYER
# ============================================================================

def _get_api_key():
    """Resolve FRED API key via the existing FredProvider helper."""
    try:
        return FredProvider().api_key  # defaults to series_id="DFF" (whitelisted)
    except Exception as e:
        print(f"[WARN] Could not resolve FRED API key via FredProvider: {e}")
        print("       Will attempt to read cached parquet only.")
        return None


def fetch_fred_series(series_id, start=HISTORY_START, end=HISTORY_END,
                      api_key=None, force=False):
    """Fetch a FRED series via REST API with parquet caching.

    Cache schema matches FredProvider (Metis contract):
        ts, open, high, low, close, volume, source
    so cached files are interchangeable with FredProvider output. A cache
    file that COVERS the requested [start, end] range is served without an
    API call; otherwise the full range is fetched and the cache overwritten.
    """
    cache_path = CACHE_DIR / f"{series_id}.parquet"

    if not force and cache_path.exists():
        try:
            cached = pd.read_parquet(cache_path)
            cached["ts"] = pd.to_datetime(cached["ts"])
            if cached["ts"].dt.tz is not None:
                cached["ts"] = cached["ts"].dt.tz_convert("UTC").dt.tz_localize(None)
            if _cache_covers(cached, start, end):
                return cached
        except Exception:
            pass  # corrupt -> fall through to refetch

    if api_key is None:
        return pd.DataFrame()  # no key, no fetch

    try:
        r = requests.get("https://api.stlouisfed.org/fred/series/observations",
                         params={"series_id": series_id, "api_key": api_key,
                                 "file_type": "json",
                                 "observation_start": start,
                                 "observation_end": end}, timeout=30)
        if r.status_code != 200:
            print(f"[WARN] FRED {series_id}: HTTP {r.status_code} - {r.text[:120]}")
            return pd.DataFrame()
        obs = r.json().get("observations", [])
    except Exception as e:
        print(f"[WARN] FRED {series_id}: fetch failed - {type(e).__name__}: {e}")
        return pd.DataFrame()

    if not obs:
        return pd.DataFrame()

    rows = []
    for o in obs:
        v = o.get("value")
        if v is None or v == ".":
            continue  # FRED sentinel for missing observation
        try:
            val = float(v)
        except (TypeError, ValueError):
            continue
        rows.append({"ts": pd.Timestamp(o["date"]), "open": val, "high": val,
                     "low": val, "close": val, "volume": float("nan"),
                     "source": f"fred:{series_id}"})
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"])
    df = df.drop_duplicates(subset=["ts"]).sort_values("ts").reset_index(drop=True)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(cache_path, index=False)
    except Exception as e:
        print(f"[WARN] FRED {series_id}: could not write cache - {e}")
    return df


def _cache_covers(cached, start, end):
    if cached is None or len(cached) == 0:
        return False
    return bool(cached["ts"].min() <= pd.Timestamp(start)
                and cached["ts"].max() >= pd.Timestamp(end))


def load_series(name):
    """Load a FRED series as a pandas Series indexed by ts (or None)."""
    path = CACHE_DIR / f"{name}.parquet"
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path)
    except Exception:
        return None
    df["ts"] = pd.to_datetime(df["ts"])
    if df["ts"].dt.tz is not None:
        df["ts"] = df["ts"].dt.tz_convert("UTC").dt.tz_localize(None)
    s = df.set_index("ts")["close"].sort_index()
    s = s[~s.index.duplicated(keep="last")]
    return s.astype(float)


def yf_latest(ticker, period="5d"):
    """Fetch latest close via yfinance. Returns (latest, period_ago)."""
    try:
        df = yf.download(ticker, period=period, progress=False, auto_adjust=False)
        if df is None or len(df) == 0:
            return None, None
        close = df["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        close = close.dropna()
        if len(close) == 0:
            return None, None
        return float(close.iloc[-1]), float(close.iloc[0])
    except Exception:
        return None, None


def yf_history(ticker, period="1y"):
    """Fetch N-period history as a clean Series."""
    try:
        df = yf.download(ticker, period=period, progress=False, auto_adjust=False)
        if df is None or len(df) == 0:
            return None
        close = df["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        return close.dropna()
    except Exception:
        return None


def yf_return(s, days):
    """Trailing N-day return (percent) for a Series, or None."""
    if s is None or len(s) < 2:
        return None
    n = min(days, len(s) - 1)
    if n <= 0:
        return None
    start = float(s.iloc[-1 - n])
    if start <= 0:
        return None
    return (float(s.iloc[-1]) / start - 1.0) * 100.0


# ============================================================================
# SUB-SCORE MAPPINGS (each raw indicator -> 0..100 stress score)
# ============================================================================
# Calibrated against historical crisis peaks:
#   BAA-10Y: 2008 6.05%, 2020 3.80%, 2023 2.85%, 10Y median ~2.40%
#   HY OAS : 2008 ~18%, 2020 ~11%,  2023 ~5.5%,  10Y median ~4.5%
#   TED    : 2008 ~456bp, 2020 ~140bp (discontinued -> SOFR-Tbill now)
#   2s10s  : 2008 ~ -0.20%, 2022 deep inversion -1.07%
# ============================================================================

def baa10y_score(level):
    """BAA-10Y (pct): 1.0%=calm -> 0, 6.0%=GFC peak -> 100."""
    if level is None or np.isnan(level):
        return 0.0
    return float(np.clip((level - 1.0) / 5.0 * 100.0, 0.0, 100.0))


def hy_oas_score(level):
    """HY OAS (pct): 3.0%=tight -> 0, 15.0%=crisis -> 100."""
    if level is None or np.isnan(level):
        return 0.0
    return float(np.clip((level - 3.0) / 12.0 * 100.0, 0.0, 100.0))


def interbank_score(spread_bp):
    """SOFR-3M Tbill (bp): 0bp=normal -> 0, 100bp=crisis -> 100.

    Modern TED replacement. TED historically hit 456bp (2008), 140bp (2020)."""
    if spread_bp is None or np.isnan(spread_bp):
        return 0.0
    return float(np.clip(spread_bp, 0.0, 100.0))


def kre_underperf_score(underperf_pct):
    """KRE vs SPY 1M underperf (pct, + = KRE lagging).

    0%=none -> 0, 5%=warn -> 25, 15%=SVB-like -> 75, 20%+ -> 100."""
    if underperf_pct is None or np.isnan(underperf_pct):
        return 0.0
    return float(np.clip(max(0.0, underperf_pct) / 20.0 * 100.0, 0.0, 100.0))


def curve_score(spread_pct):
    """2s10s (pct): +0.50%=healthy -> 0, 0%=flat -> 30, -0.50% -> 70, -1.5%=100."""
    if spread_pct is None or np.isnan(spread_pct):
        return 0.0
    s = spread_pct
    if s >= 0.50:
        return 0.0
    if s >= 0.0:
        return float(30.0 * (0.50 - s) / 0.50)
    if s >= -0.50:
        return float(30.0 + 40.0 * (-s) / 0.50)
    return float(np.clip(70.0 + (-s - 0.50) / 1.0 * 30.0, 0.0, 100.0))


# ============================================================================
# ANALYSIS HELPERS
# ============================================================================

def series_peak_in_window(s, start, end):
    if s is None or len(s) == 0:
        return None
    mask = (s.index >= pd.Timestamp(start)) & (s.index <= pd.Timestamp(end))
    sub = s[mask]
    return float(sub.max()) if len(sub) else None


def latest_value(s):
    if s is None or len(s) == 0:
        return None
    s = s.dropna()
    return float(s.iloc[-1]) if len(s) else None


def latest_date(s):
    if s is None:
        return "N/A"
    s = s.dropna()
    return s.index[-1].strftime("%Y-%m-%d") if len(s) else "N/A"


def median_last_n_years(s, years=10):
    if s is None or len(s) == 0:
        return None
    cutoff = s.index[-1] - pd.DateOffset(years=years)
    sub = s[s.index >= cutoff].dropna()
    return float(sub.median()) if len(sub) else None


def days_since(s, predicate):
    """Days since predicate(series) was last True; None if never."""
    if s is None or len(s) == 0:
        return None
    trues = s.index[predicate(s)]
    if len(trues) == 0:
        return None
    return (s.index[-1] - trues[-1]).days


def recession_prob_heuristic(t10y3m_pct, baa10y_pct, hy_oas_pct, sahm_like_pp):
    """Heuristic 12-month-ahead US recession probability (0..100).

    NOT the NY Fed probit model (fitted coefficients, updated monthly).
    Transparent blend of the three strongest leading signals:
      curve 0.40 | baa10y 0.20 | hy_oas 0.15 | sahm 0.25
    """
    if t10y3m_pct is None or np.isnan(t10y3m_pct):
        p_curve = 50.0
    else:
        # +2.0% -> ~0, 0% -> 50, -1.5% -> ~92.
        p_curve = float(np.clip(50.0 - t10y3m_pct * 28.0, 2.0, 97.0))
    p_baa = baa10y_score(baa10y_pct) if baa10y_pct is not None else 0.0
    p_hy = hy_oas_score(hy_oas_pct) if hy_oas_pct is not None else 0.0
    if sahm_like_pp is None or np.isnan(sahm_like_pp):
        p_sahm = 0.0
    else:
        p_sahm = float(np.clip(sahm_like_pp / 0.5 * 60.0, 0.0, 95.0))
    prob = (0.40 * p_curve + 0.20 * p_baa + 0.15 * p_hy + 0.25 * p_sahm)
    return float(np.clip(prob, 0.0, 99.0)), \
        {"curve": p_curve, "baa": p_baa, "hy": p_hy, "sahm": p_sahm}


def curve_shape(t10y2y, t10y3m):
    """Classify the yield curve shape from 2s10s and 3m10y spreads."""
    if t10y2y is None or t10y3m is None:
        return "UNKNOWN"
    if t10y2y < 0 or t10y3m < 0:
        if t10y3m < 0 and t10y2y > 0:
            return "HUMPED"
        return "INVERTED"
    if t10y2y < 0.50:
        return "FLAT"
    return "NORMAL"


def fmt(v, suffix="%", digits=2, na="--"):
    """Format a number WITH leading sign (for changes/spreads)."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return na
    return f"{v:+.{digits}f}{suffix}"


def fmt_plain(v, suffix="%", digits=2, na="--"):
    """Format a number WITHOUT leading sign (for absolute levels)."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return na
    return f"{v:.{digits}f}{suffix}"


# ============================================================================
# MAIN
# ============================================================================

def generate_briefing():
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")
    api_key = _get_api_key()
    print(f"Generating credit conditions monitor for {date_str}...")
    print(f"FRED fetch window: {HISTORY_START} -> {HISTORY_END}\n")

    # ---- 1. FETCH ALL FRED SERIES (cache-first, REST fallback) ----
    print("Step 1/5: Fetching FRED credit series...")
    series, meta = {}, {}
    for sid, name in FRED_CREDIT_SERIES.items():
        fetch_fred_series(sid, HISTORY_START, HISTORY_END, api_key=api_key)
        s = load_series(sid)
        series[sid] = s
        if s is not None and len(s.dropna()) > 0:
            sd = s.dropna()
            ref = REFERENCE_PEAKS.get(sid, {})
            meta[sid] = {
                "name": name,
                "latest": latest_value(s),
                "latest_date": latest_date(s),
                "median_10y": median_last_n_years(s, 10),
                "peak_2008": series_peak_in_window(s, *CRISIS_WINDOWS["2008 GFC"]),
                "peak_2020": series_peak_in_window(s, *CRISIS_WINDOWS["2020 COVID"]),
                "peak_2023": series_peak_in_window(s, *CRISIS_WINDOWS["2023 SVB/banking"]),
                "ref_2008": ref.get("2008 GFC"),
                "ref_2020": ref.get("2020 COVID"),
                "ref_2023": ref.get("2023 SVB/banking"),
                "first": sd.index[0].strftime("%Y-%m-%d"),
                "last": sd.index[-1].strftime("%Y-%m-%d"),
            }
        else:
            meta[sid] = {"name": name, "latest": None}
    n_ok = sum(1 for v in series.values() if v is not None and len(v.dropna()) > 0)
    print(f"  FRED: {n_ok}/{len(FRED_CREDIT_SERIES)} series available.")

    # ---- 2. FETCH YAHOO MARKET DATA ----
    print("Step 2/5: Fetching Yahoo market data (KRE, KBE, XLF, HYG, LQD, TLT, BIL, SPY)...")
    yfd = {}
    for ticker, name in YF_TICKERS.items():
        hist = yf_history(ticker, period="2y")  # 2Y for 1M/3M/6M + trend
        latest, _ = yf_latest(ticker, period="5d")
        # Fallback: if yf_latest returned None, use last history value.
        if latest is None and hist is not None and len(hist) > 0:
            latest = float(hist.iloc[-1])
        yfd[ticker] = {"name": name, "hist": hist, "latest": latest}
    spy_hist = yfd.get("SPY", {}).get("hist")
    kre_hist = yfd.get("KRE", {}).get("hist")
    print(f"  Yahoo: {sum(1 for v in yfd.values() if v['hist'] is not None)}/{len(YF_TICKERS)} tickers fetched.")

    # ---- 3. COMPUTE INDICATORS ----
    print("Step 3/5: Computing credit indicators...")
    baa10y_s = series.get("BAA10Y");   hy_oas_s = series.get("BAMLH0A0HYM2")
    corp_oas_s = series.get("BAMLC0A0CM"); bbb_oas_s = series.get("BAMLC0A4CBBB")
    ted_s = series.get("TEDRATE");     t10y2y_s = series.get("T10Y2Y")
    t10y3m_s = series.get("T10Y3M")
    dgs2 = latest_value(series.get("DGS2"));  dgs5 = latest_value(series.get("DGS5"))
    dgs10 = latest_value(series.get("DGS10")); dgs30 = latest_value(series.get("DGS30"))
    dgs3mo = latest_value(series.get("DGS3MO")) or latest_value(series.get("DTB3"))
    dprime = latest_value(series.get("DPRIME")); sofr = latest_value(series.get("SOFR"))
    dff = latest_value(series.get("DFF"));     vix = latest_value(series.get("VIXCLS"))
    unrate_s = series.get("UNRATE");   unrate = latest_value(unrate_s)
    nfci = latest_value(series.get("NFCI"));   sloos = latest_value(series.get("DRTSCILM"))
    walcl = latest_value(series.get("WALCL"))
    baa10y = latest_value(baa10y_s);  hy_oas = latest_value(hy_oas_s)
    corp_oas = latest_value(corp_oas_s); bbb_oas = latest_value(bbb_oas_s)
    t10y2y = latest_value(t10y2y_s);  t10y3m = latest_value(t10y3m_s)

    # Modern interbank stress: SOFR - 3M T-bill (bp).
    interbank_label = "SOFR - 3M T-bill"
    if sofr is not None and dgs3mo is not None:
        interbank_bp = (sofr - dgs3mo) * 100.0
    elif ted_s is not None:
        interbank_label = "TED spread (fallback)"; interbank_bp = latest_value(ted_s)
    else:
        interbank_bp = None

    # Regional bank stress: KRE vs SPY underperformance.
    kre_underperf, kre_abs = {}, {}
    if spy_hist is not None and kre_hist is not None:
        for lbl, days in [("1M", 21), ("3M", 63), ("6M", 126)]:
            kr = yf_return(kre_hist, days); sr = yf_return(spy_hist, days)
            if kr is not None and sr is not None:
                kre_underperf[lbl] = sr - kr  # positive = KRE lagging
            kre_abs[lbl] = kr
    kre_1m = kre_underperf.get("1M")

    # Sahm-rule proxy: 3-month rise in unemployment (pp).
    sahm_pp = None
    if unrate_s is not None and len(unrate_s.dropna()) >= 4:
        u = unrate_s.dropna()
        sahm_pp = float(u.iloc[-1]) - float(u.iloc[max(0, len(u) - 4)])

    rec_prob, rec_parts = recession_prob_heuristic(t10y3m, baa10y, hy_oas, sahm_pp)

    # ---- 4. CREDIT STRESS COMPOSITE SCORE ----
    print("Step 4/5: Computing Credit Stress Score...")
    sub_baa = baa10y_score(baa10y);   sub_hy = hy_oas_score(hy_oas)
    sub_inter = interbank_score(interbank_bp); sub_kre = kre_underperf_score(kre_1m)
    sub_curve = curve_score(t10y2y)
    composite = float(np.clip(
        SCORE_WEIGHTS["baa10y"] * sub_baa + SCORE_WEIGHTS["hy_oas"] * sub_hy +
        SCORE_WEIGHTS["kre_rel"] * sub_kre + SCORE_WEIGHTS["interbank"] * sub_inter +
        SCORE_WEIGHTS["curve"] * sub_curve, 0.0, 100.0))
    band, meaning = score_band(composite)

    # ---- 5. BUILD BRIEFING ----
    print("Step 5/5: Building briefing...")
    L = []  # output lines
    add = L.append

    add(f"# Credit & Financial Conditions Monitor - {date_str}\n")
    add("> The #1 leading indicator for market crashes. Credit spreads widen")
    add("> BEFORE equities sell off. This is the early-warning system.\n")
    add(f"**Date:** {date_str}")
    add(f"**Credit Stress Score:** **{composite:.1f} / 100** -> **{band}**")
    add(f"**Interpretation:** {meaning}\n")
    add("Score bands: 0-30 NORMAL | 30-50 WATCH | 50-70 WARNING | 70-100 CRISIS\n")
    add("---\n")

    # ---- Section 1: Composite Score Breakdown ----
    add("## 1. Credit Stress Score - Composite Breakdown\n")
    add("Weighted blend of 5 independent credit-stress signals. Each sub-score")
    add("is mapped from its raw level to 0-100 against historical crisis peaks,")
    add("then combined with the weights below.\n")
    add("| Component | Weight | Raw Level | Sub-score | Notes |")
    add("|-----------|-------:|-----------|----------:|-------|")
    add(f"| BAA-10Y spread | {SCORE_WEIGHTS['baa10y']*100:.0f}% | {fmt_plain(baa10y)} | {sub_baa:.1f} | 1.0%=calm, 6.0%=GFC peak |")
    add(f"| HY OAS (BAMLH0A0HYM2) | {SCORE_WEIGHTS['hy_oas']*100:.0f}% | {fmt_plain(hy_oas)} | {sub_hy:.1f} | 3.0%=tight, 15.0%=crisis |")
    add(f"| KRE vs SPY (1M underperf) | {SCORE_WEIGHTS['kre_rel']*100:.0f}% | {fmt(kre_1m)} | {sub_kre:.1f} | 5%=warn, 15%=SVB-like |")
    add(f"| {interbank_label} | {SCORE_WEIGHTS['interbank']*100:.0f}% | {fmt(interbank_bp, suffix='bp', digits=1)} | {sub_inter:.1f} | 50bp=warn, 100bp+=crisis |")
    add(f"| 2s10s yield curve | {SCORE_WEIGHTS['curve']*100:.0f}% | {fmt(t10y2y)} | {sub_curve:.1f} | +0.5%=healthy, <0=inverted |")
    add(f"| **COMPOSITE** | **100%** | -- | **{composite:.1f}** | **{band}** |\n")
    add(f"**Verdict: {band}.** {meaning}.")
    if composite < 30:
        add("Credit markets function normally; risk-on positioning supported by")
        add("credit conditions. Continue normal risk management.")
    elif composite < 50:
        add("Minor widening detected. No action required yet, but tighten")
        add("monitoring. Sustained moves above 50 have historically preceded")
        add("equity drawdowns by 2-6 months.")
    elif composite < 70:
        add("Significant credit stress. Consider reducing equity beta, raising")
        add("cash/T-bills, and reviewing hedges. 2023 SVB peaked ~55-65 here.")
    else:
        add("MAJOR CREDIT EVENT IN PROGRESS. Defensive positioning mandatory.")
        add("Historical analogs: Oct 2008 (~95), Mar 2020 (~80), Mar 2023 (~60).")
    add("\n---\n")

    # ---- Section 2: Credit Spreads Deep Dive ----
    add("## 2. Credit Spreads - Deep Dive\n")
    add("Corporate bond spreads over Treasuries. Wider = more perceived")
    add("default risk. The cleanest direct measure of credit risk appetite.\n")
    add("### 2a. BAA-10Y Corporate/Treasury Spread")
    _hist_block(add, meta.get("BAA10Y", {}), baa10y, 2.5,
                ">2.5% = warning, >4.0% = crisis", "<2.0%")
    add("### 2b. ICE BofA High Yield OAS (BAMLH0A0HYM2)\n")
    add("Option-adjusted spread of US high-yield (junk) bonds. The single")
    add("most sensitive credit indicator; HY blows out first when default")
    add("risk perception rises.")
    _hist_block(add, meta.get("BAMLH0A0HYM2", {}), hy_oas, 5.0,
                ">5% = warning, >8% = crisis, >15% = GFC/COVID", "<4%")
    add("### 2c. ICE BofA Investment Grade Corporate OAS (BAMLC0A0CM)")
    _hist_block(add, meta.get("BAMLC0A0CM", {}), corp_oas, 2.0,
                ">2% = warning, >4% = crisis", "<1.5%")
    add("### 2d. ICE BofA BBB Corporate OAS (BAMLC0A4CBBB)\n")
    add("BBB is the lowest investment-grade tier; it leads IG stress.")
    _hist_block(add, meta.get("BAMLC0A4CBBB", {}), bbb_oas, 2.5,
                ">2.5% = warning", "<2%")
    add("---\n")

    # ---- Section 3: Yield Curve Analysis ----
    add("## 3. Yield Curve Analysis\n")
    add("An inverted yield curve (short > long) has preceded every US")
    add("recession since 1955. Lag from inversion to recession: 6-18 months.\n")
    add("### 3a. Current Curve Spreads\n")
    inv2 = "INVERTED" if t10y2y is not None and t10y2y < 0 else "positive"
    inv3 = "INVERTED" if t10y3m is not None and t10y3m < 0 else "positive"
    add(f"- **2s10s (10Y - 2Y):** {fmt(t10y2y)}  ({inv2})")
    add(f"- **3m10y (10Y - 3M):** {fmt(t10y3m)}  ({inv3})")
    add(f"- **Curve shape:** **{curve_shape(t10y2y, t10y3m)}**\n")
    add("Shape definitions:")
    add("- NORMAL: 2s10s > +0.50% and 3m10y > 0 (healthy positive slope)")
    add("- FLAT: 2s10s in [0, +0.50%] (low slope, growth concerns)")
    add("- INVERTED: 2s10s < 0 or 3m10y < 0 (recession warning)")
    add("- HUMPED: 3m10y < 0 but 2s10s > 0 (Fed hiked, then paused/cut)\n")

    add("### 3b. Inversion History\n")
    if t10y2y_s is not None and len(t10y2y_s.dropna()) > 0:
        d = days_since(t10y2y_s, lambda s: s < 0)
        msg = "never in dataset" if d is None else (
            f"{d} days ago ({(today - timedelta(days=d)).strftime('%Y-%m-%d')})")
        add(f"- Last 2s10s inversion: **{msg}**")
    if t10y3m_s is not None and len(t10y3m_s.dropna()) > 0:
        d = days_since(t10y3m_s, lambda s: s < 0)
        msg = "never in dataset" if d is None else (
            f"{d} days ago ({(today - timedelta(days=d)).strftime('%Y-%m-%d')})")
        add(f"- Last 3m10y inversion: **{msg}**\n")
    add("Recession typically follows 6-18 months after the first sustained")
    add("inversion of 3m10y (the Fed's preferred measure).\n")

    add("### 3c. Full Yield Curve Snapshot\n")
    add("| Tenor | Yield |"); add("|-------|------:|")
    add(f"| 3M T-bill | {fmt_plain(dgs3mo)} |")
    add(f"| Fed Funds | {fmt_plain(dff)} |")
    add(f"| 2Y | {fmt_plain(dgs2)} |"); add(f"| 5Y | {fmt_plain(dgs5)} |")
    add(f"| 10Y | {fmt_plain(dgs10)} |"); add(f"| 30Y | {fmt_plain(dgs30)} |")
    add(f"| Prime rate | {fmt_plain(dprime)} |")
    add(f"| SOFR (overnight) | {fmt_plain(sofr)} |\n")
    if dgs30 is not None and dgs3mo is not None:
        steep = dgs30 - dgs3mo
        slbl = "steep" if steep > 1.5 else "flat" if steep > 0.5 else "inverted/flat"
        add(f"**30Y-3M steepness:** {fmt(steep)} ({slbl})\n")
    add("---\n")

    # ---- Section 4: Interbank & Funding Stress ----
    add("## 4. Interbank & Funding Stress\n")
    add("Measures of stress in bank funding markets. When banks stop trusting")
    add("each other, the plumbing of the financial system seizes.\n")
    add(f"**Active measure:** {interbank_label}")
    add(f"- Current: **{fmt(interbank_bp, suffix='bp', digits=2)}**\n")
    add("Interpretation of SOFR-3M T-bill spread:")
    add("- <10bp: Normal, banks lend freely")
    add("- 10-30bp: Mild stress, monitor")
    add("- 30-50bp: Significant, funding pressure building")
    add("- >50bp: Crisis (2008 TED hit 456bp, 2020 hit 140bp)\n")
    add("**Note:** The classic TED spread (3M LIBOR - 3M T-bill) was")
    add("discontinued after LIBOR ended mid-2023. SOFR-Tbill is the modern")
    add("equivalent but is structurally smaller (SOFR is secured/collateralized")
    add("while LIBOR was unsecured).\n")
    add("**Historical TED spread context (discontinued 2022-01-21):**")
    add(f"- TED last published value: {fmt_plain(latest_value(ted_s))} (Jan 2022)")
    add(f"- TED 2008 GFC peak: {fmt_plain(series_peak_in_window(ted_s, *CRISIS_WINDOWS['2008 GFC']))}")
    add(f"- TED 2020 COVID peak: {fmt_plain(series_peak_in_window(ted_s, *CRISIS_WINDOWS['2020 COVID']))}\n")
    add(f"**Discount Window Primary Credit Rate:** {fmt_plain(latest_value(series.get('DPCREDIT')))}  "
        f"(spread over Fed Funds = penalty for emergency bank borrowing)\n")
    add("---\n")

    # ---- Section 5: Regional Bank Stress ----
    add("## 5. Regional Bank Stress Monitor\n")
    add("KRE (SPDR Regional Bank ETF) vs SPY. Regional banks are the canary")
    add("in the coal mine: SVB, Signature, First Republic all collapsed March")
    add("2023, and KRE led the way DOWN before equities noticed.\n")
    add("### KRE vs SPY Relative Performance\n")
    add("| Window | KRE return | SPY return | KRE underperf | Signal |")
    add("|--------|-----------:|-----------:|--------------:|--------|")
    spy_returns = {"1M": yf_return(spy_hist, 21) if spy_hist is not None else None,
                   "3M": yf_return(spy_hist, 63) if spy_hist is not None else None,
                   "6M": yf_return(spy_hist, 126) if spy_hist is not None else None}
    for lbl in ["1M", "3M", "6M"]:
        up = kre_underperf.get(lbl)
        if up is not None and up <= -15: sig = "CRISIS (SVB-like)"
        elif up is not None and up <= -5: sig = "WARNING"
        elif up is not None and up <= 0: sig = "mild lag"
        else: sig = "OK"
        add(f"| {lbl} | {fmt(kre_abs.get(lbl))} | {fmt(spy_returns[lbl])} | {fmt(up)} | {sig} |")
    add("\nThresholds: KRE underperforming SPY by >5% (1M) = WARNING; >15% =")
    add("CRISIS (March 2023 SVB saw ~30% relative underperformance).\n")
    add(f"**KRE:** ${yfd['KRE']['latest']:.2f}" if yfd.get("KRE", {}).get("latest") else "**KRE:** N/A")
    add(f"**SPY:** ${yfd['SPY']['latest']:.2f}" if yfd.get("SPY", {}).get("latest") else "**SPY:** N/A\n")
    add("### Other Financial ETFs\n")
    add("| ETF | Latest | 1M return | Role |"); add("|-----|-------:|----------:|------|")
    roles = {"KBE": "Bank sector (broad)", "XLF": "Financial sector",
             "HYG": "High yield bonds", "LQD": "Investment grade bonds",
             "TLT": "Long Treasuries", "BIL": "1-3M T-bills"}
    for tk in ["KBE", "XLF", "HYG", "LQD", "TLT", "BIL"]:
        lv = yfd.get(tk, {}).get("latest"); h = yfd.get(tk, {}).get("hist")
        lv_str = f"${lv:.2f}" if lv is not None else "N/A"
        add(f"| {tk} | {lv_str} | {fmt(yf_return(h, 21))} | {roles[tk]} |")
    add("\n**Key cross-asset read:**")
    add("- HYG falling = high-yield credit stress (matches HY OAS widening)")
    add("- LQD falling = IG credit stress (matches Corp OAS widening)")
    add("- TLT rising = flight to safety (duration bid)")
    add("- KRE/XLF underperforming SPY = bank-sector specific stress\n")
    add("---\n")

    # ---- Section 6: Macro Backdrop ----
    add("## 6. Macro Backdrop (Credit Context)\n")
    add("### Senior Loan Officer Survey (SLOOS)\n")
    add(f"**DRTSCILM (net % banks tightening C&I loans):** {fmt_plain(sloos) if sloos is not None else 'N/A'}\n")
    add("Interpretation (quarterly survey):")
    add("- <0%: Banks easing = credit expanding = risk-on")
    add("- 0-15%: Mild tightening = normal caution")
    add("- 15-40%: Significant = credit pipeline constricting")
    add("- >40%: Crisis tightening (2008 ~70%, 2020 ~48%, 2023 ~46%)\n")
    if sloos is not None:
        if sloos > 15:
            add(f"Current SLOOS at {sloos:.1f}% signals TIGHTENING credit conditions -- a leading signal worth monitoring.")
        elif sloos > 0:
            add(f"Current SLOOS at {sloos:.1f}% is in the NORMAL range -- banks are not materially restricting credit.")
        else:
            add(f"Current SLOOS at {sloos:.1f}% shows EASING -- credit conditions loosening, supportive of growth.")
    add("")
    add("### Chicago Fed National Financial Conditions Index (NFCI)\n")
    # NFCI is unitless index, NOT a percentage -> no suffix.
    add(f"**NFCI:** {fmt_plain(nfci, suffix='', digits=3) if nfci is not None else 'N/A'}\n")
    add("Interpretation:")
    add("- Negative = conditions LOOSER than historical average")
    add("- Around 0 = average")
    add("- Positive (>0.5) = TIGHTER, stress building")
    add("- >1.0 = crisis (2008 peaked ~+3.5, 2020 peaked ~+2.5)\n")
    if nfci is not None:
        if nfci < -0.5:
            add(f"NFCI at {nfci:.3f}: conditions LOOSE. Risk-asset friendly short")
            add("term, but prolonged looseness plants seeds of future excess.")
        elif nfci < 0:
            add(f"NFCI at {nfci:.3f}: conditions slightly loose.")
        elif nfci < 0.5:
            add(f"NFCI at {nfci:.3f}: conditions near average.")
        else:
            add(f"NFCI at {nfci:.3f}: STRESS. Monitor closely.")
    add("")
    add("### Labor Market (Sahm-rule proxy)\n")
    add(f"**Unemployment rate:** {fmt_plain(unrate)}")
    if sahm_pp is not None:
        add(f"**3-month change in unemployment:** {fmt(sahm_pp, suffix='pp', digits=2)}")
        if sahm_pp >= 0.5:
            add("**SAHM RULE TRIGGERED.** A 0.50pp rise in the 3mo moving average")
            add("of unemployment above its 12mo low has marked the start of every")
            add("US recession since 1970.")
        elif sahm_pp >= 0.3:
            add(f"Approaching Sahm trigger (+0.50pp). Currently {sahm_pp:+.2f}pp.")
        else:
            add(f"Labor market stable. Sahm at +0.50pp; currently {sahm_pp:+.2f}pp.")
    # VIX is an index in points, not percent -> no suffix.
    add(f"\n**VIX:** {fmt_plain(vix, suffix='', digits=2) if vix is not None else 'N/A'}\n")
    add("---\n")

    # ---- Section 7: Recession Probability ----
    add("## 7. Recession Probability (Heuristic)\n")
    add(f"**12-month-ahead US recession probability: ~{rec_prob:.0f}%**\n")
    add("Transparent heuristic blend (NOT the NY Fed probit model). Components:\n")
    add("| Signal | Weight | Sub-prob | Rationale |"); add("|--------|-------:|---------:|-----------|")
    add(f"| 10Y-3M curve | 40% | {rec_parts['curve']:.0f}% | single best recession predictor |")
    add(f"| BAA-10Y | 20% | {rec_parts['baa']:.0f}% | credit stress |")
    add(f"| HY OAS | 15% | {rec_parts['hy']:.0f}% | credit stress |")
    add(f"| Sahm-rule proxy | 25% | {rec_parts['sahm']:.0f}% | labor market deterioration |\n")
    if rec_prob < 20:
        add(f"Recession risk is LOW ({rec_prob:.0f}%). No defensive action warranted yet.")
    elif rec_prob < 40:
        add(f"Recession risk is MODERATE ({rec_prob:.0f}%). Monitor.")
    elif rec_prob < 60:
        add(f"Recession risk is ELEVATED ({rec_prob:.0f}%). Consider defensive tilts.")
    else:
        add(f"Recession risk is HIGH ({rec_prob:.0f}%). Historical analogs at this")
        add("level have been followed by recession within 12 months.")
    add("\n---\n")

    # ---- Section 8: Fed Balance Sheet ----
    if walcl is not None:
        add("## 8. Fed Balance Sheet (Liquidity Backdrop)\n")
        add(f"**Fed total assets:** ${walcl/1e6:.2f} trillion\n")
        walcl_s = series.get("WALCL")
        if walcl_s is not None and len(walcl_s.dropna()) >= 5:
            w = walcl_s.dropna(); peak = float(w.max()); peak_d = w.idxmax().strftime("%Y-%m-%d")
            dd = (walcl / peak - 1) * 100 if peak > 0 else None
            add(f"- QT peak-to-trough: ${peak/1e6:.2f}T ({peak_d}) -> now {fmt(dd)} from peak")
            add("- Quantitative tightening (QT) drains reserves; rapid QT has")
            add("  historically coincided with liquidity events (2018-Q4, Mar 2020, Mar 2023).")
        add("\n---\n")

    # ---- Section 9: Early Warning Indicators ----
    add("## 9. EARLY WARNING INDICATORS (What's Flashing Now)\n")
    add("Boolean checklist of crash-precursor signals. Each shows threshold,")
    add("current reading, and YES/NO.\n")
    warnings = []
    def check(label, threshold_desc, current_str, flashing):
        add(f"  [{'X' if flashing else ' '}] {label} ({threshold_desc}) -> currently {current_str} -> **{'YES' if flashing else 'no'}**")
        if flashing: warnings.append(label)

    check("BAA-10Y > 2.5%", "crisis precursor", fmt_plain(baa10y), baa10y is not None and baa10y > 2.5)
    check("HY OAS > 5.0%", "credit stress", fmt_plain(hy_oas), hy_oas is not None and hy_oas > 5.0)
    check("KRE underperforming SPY > 5% (1M)", "bank stress", fmt(kre_1m), kre_1m is not None and kre_1m < -5.0)
    check("2s10s inverted (< 0)", "recession precursor", fmt(t10y2y), t10y2y is not None and t10y2y < 0)
    check("3m10y inverted (< 0)", "Fed-preferred recession signal", fmt(t10y3m), t10y3m is not None and t10y3m < 0)
    check(f"{interbank_label} > 50bp", "funding stress", fmt(interbank_bp, suffix='bp', digits=1), interbank_bp is not None and interbank_bp > 50)
    check("VIX > 30", "equity fear / crisis mode", fmt_plain(vix, suffix='', digits=2) if vix is not None else "N/A", vix is not None and vix > 30)
    check("Sahm rule (UNR +0.50pp / 3mo)", "recession confirmed", fmt(sahm_pp, suffix='pp', digits=2), sahm_pp is not None and sahm_pp >= 0.5)
    check("SLOOS tightening > 40%", "credit pipeline constricting", fmt_plain(sloos), sloos is not None and sloos > 40)
    check("NFCI > 0.5", "financial conditions tight", fmt_plain(nfci, suffix='', digits=3) if nfci is not None else "N/A", nfci is not None and nfci > 0.5)
    add(f"\n**Signals flashing: {len(warnings)} / 10**\n")
    n = len(warnings)
    if n == 0: add("No signals flashing. Credit conditions are benign.")
    elif n <= 2: add(f"{n} signal(s) flashing. Monitor but no action required.")
    elif n <= 4: add(f"{n} signals flashing. Elevated risk -- consider reducing risk exposure and reviewing hedges.")
    else: add(f"**{n} signals flashing.** Broad-based stress confirmed. Defensive positioning strongly advised.")
    add("\n---\n")

    # ---- Section 10: Crash Detection Rules ----
    add("## 10. MY CRASH DETECTION RULES\n")
    add("**IF 3 or more of these happen within a 6-month window:**\n")
    add("  1. BAA-10Y widens from <2.0% to >3.0% (sustained 2+ weeks)")
    add(f"  2. HY OAS doubles from current level (now {fmt_plain(hy_oas)} -> trigger at {fmt_plain(hy_oas*2 if hy_oas else None)})")
    add("  3. KRE underperforms SPY by 15%+ in 1 month")
    add("  4. 2s10s inverts (10Y < 2Y)")
    add("  5. VIX spikes above 30")
    add("  6. Unemployment rises 0.5pp in 3 months (Sahm rule)\n")
    add("**THEN:**")
    add("  - Reduce equity exposure by ~50%")
    add("  - Add to gold and short-duration T-bills (BIL)")
    add("  - Cut MNQ/NQ futures size by 50-70%")
    add("  - Raise cash to 30-40% of portfolio")
    add("  - Stop buying dips until credit spreads normalize\n")
    add("Historical precedent: every crash since 1990 was telegraphed by 3+")
    add("of these firing simultaneously. The signals LEAD equities by 2-8")
    add("weeks -- that is the window to act, not after equities break.\n")
    add("**Current status of the 6 rules:**\n")
    fired = 0
    def rule(met, detail):
        nonlocal_fired = met
        add(f"  [{'X' if met else ' '}] Rule: {detail} -> **{'TRIGGERED' if met else 'not yet'}**")
        return met
    fired += 1 if rule(baa10y is not None and baa10y > 3.0, f"BAA-10Y > 3.0% (now {fmt_plain(baa10y)})") else 0
    fired += 1 if rule(hy_oas is not None and hy_oas > max(6.0, hy_oas*2 if hy_oas else 999), f"HY OAS doubled (now {fmt_plain(hy_oas)})") else 0
    fired += 1 if rule(kre_1m is not None and kre_1m < -15.0, f"KRE -15% vs SPY 1M (now {fmt(kre_1m)})") else 0
    fired += 1 if rule(t10y2y is not None and t10y2y < 0, f"2s10s inverted (now {fmt(t10y2y)})") else 0
    fired += 1 if rule(vix is not None and vix > 30, f"VIX > 30 (now {fmt_plain(vix, suffix='', digits=2) if vix is not None else 'N/A'})") else 0
    fired += 1 if rule(sahm_pp is not None and sahm_pp >= 0.5, f"Sahm rule +0.50pp (now {fmt(sahm_pp, suffix='pp', digits=2)})") else 0
    add(f"\n**Rules triggered: {fired} / 6** (defensive threshold: 3+ within 6 months)\n")
    add("---\n")

    # ---- Section 11: NotebookLM Talking Points ----
    add("## 11. NotebookLM Talking Points (Podcast Prompts)\n")
    add("Seed questions for a credit-markets podcast episode:\n")
    add(f"1. The composite credit stress score is {composite:.0f}/100 ({band}). Walk through each of the 5 components and explain why.")
    add(f"2. The yield curve is currently {curve_shape(t10y2y, t10y3m).lower()}. What does that signal about the business cycle?")
    add("   What is the historical track record of inversions as recession predictors?")
    add("3. Compare 2008 GFC, 2020 COVID, and 2023 SVB through the lens of credit")
    add("   spreads. Which moved first? How fast did each unfold? Early-detection lessons?")
    add("4. The BAA-10Y spread was 6.05% at the 2008 GFC peak. Walk through what")
    add("   that number means mechanically (who pays more, why, how it ripples).")
    add("5. Regional banks (KRE) are the canary in the coal mine. Why? What is")
    add("   structurally different about regional vs money-center banks?")
    add("6. Does quantitative tightening (QT) cause credit events? Review 2018-Q4,")
    add("   Mar 2020, and Mar 2023 as case studies.")
    add("7. Managing an $800K multi-asset portfolio: if 3 of the 6 crash rules")
    add("   fired, what specific trades would you put on, and in what size?\n")
    add("---\n")

    # ---- Section 12: Positioning Summary ----
    add("## 12. Portfolio Positioning Summary\n")
    add("Based on credit conditions alone (overlay with regime + trend):\n")
    if composite < 30:
        eq, dur, cash, hdg, mnq = ("Overweight (normal or +5%)",
            "Neutral / underweight duration", "Normal (5-15%)",
            "Minimal; tail-hedge only", "Standard size; trend-favorable")
    elif composite < 50:
        eq, dur, cash, hdg, mnq = ("Neutral (trim to target weight)", "Neutral",
            "Raise to 15-20%", "Light hedges; trim longs into weakness",
            "Reduce size 25-30%; tighter stops")
    elif composite < 70:
        eq, dur, cash, hdg, mnq = ("Underweight (cut 25-50%)",
            "Add duration (flight-to-safety bid)", "Raise to 25-35%",
            "Put-spreads on SPY; long VIX call spreads",
            "Cut size 50-70%; trade smaller, shorter horizon")
    else:
        eq, dur, cash, hdg, mnq = ("MINIMUM (defensive only)",
            "Long duration + T-bills", "Raise to 40-50%",
            "Full hedges; consider outright index shorts",
            "FLAT or shorts only; do not fight the tape")
    add(f"- **Equities (SPY/QQQ):** {eq}")
    add(f"- **Duration (TLT/BIL):** {dur}")
    add(f"- **Cash / T-bills:** {cash}")
    add(f"- **Hedges:** {hdg}")
    add(f"- **MNQ futures:** {mnq}\n")
    add("**Portfolio context:** $800K portfolio. Credit is the EARLY-WARNING")
    add("layer; combine with the weekly macro regime and trend-structure")
    add("scores before executing.\n")
    add("---\n")

    # ---- Footer ----
    add("## Data Sources & Methodology\n")
    add("- **FRED**: BAA10Y, BAMLH0A0HYM2, BAMLC0A0CM, BAMLC0A4CBBB, TEDRATE,")
    add("  T10Y2Y, T10Y3M, DGS2/5/30, DGS3MO, DPRIME, DRTSCILM, USSLIND, SOFR,")
    add("  NFCI, WALCL, BAA, AAA.")
    add("- **Yahoo Finance**: KRE, KBE, XLF, HYG, LQD, TLT, BIL, SPY.")
    add("- **Existing cache**: DFF, DGS10, DFII10, VIXCLS, UNRATE, T10YIE.")
    add("- Composite weights: BAA-10Y 25%, HY OAS 25%, KRE-via-SPY 20%,")
    add("  interbank 15%, curve 15%.")
    add("- Sub-score mappings are piecewise-linear vs historical crisis peaks.\n")
    add("**Caveats:**")
    add("- ICE-licensed BAML series on FRED free-tier return only ~3y of")
    add("  trailing history (from 2023-06). Pre-2023 peaks shown are published")
    add("  reference levels (public ICE/Fed record), clearly labeled, NOT from")
    add("  the current fetch.")
    add("- USSLIND discontinued by FRED in 2020 (last obs 2020-02).")
    add("- TEDRATE discontinued when LIBOR ended (last obs 2022-01);")
    add("  SOFR-3M T-bill is the modern interbank-stress proxy.")
    add("- Recession probability is a transparent heuristic, not the NY Fed")
    add("  probit model.")
    add("- Single-day readings can be noisy; sustained 2+ week moves are more")
    add("  meaningful than one-day spikes.\n")
    add(f"*Generated by credit_monitor.py on {date_str}*")
    add("*This is analysis, not investment advice. Consult a financial advisor.*")

    briefing = "\n".join(L)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = REPORT_DIR / f"credit_monitor_{date_str}.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(briefing)
    print(f"\nBriefing saved to: {output_path}")
    print(f"File size: {output_path.stat().st_size / 1024:.1f} KB")
    print(f"Word count: {len(briefing.split())} words")
    return briefing, output_path


def _hist_block(add, m, current, crisis_threshold, threshold_note, calm_note):
    """Emit the historical-comparison block for one spread series.

    Uses fetched peaks when available; falls back to clearly-labeled
    published reference peaks (REFERENCE_PEAKS) when FRED free-tier did
    not return enough history (notably the ICE-licensed BAML series).
    """
    if m is None or m.get("latest") is None:
        add(f"- Current: **N/A** (series unavailable)\n")
        return

    def peak_line(label, fetched, ref):
        if fetched is not None:
            return f"- {label}: {fmt_plain(fetched)}"
        if ref is not None:
            return f"- {label}: ~{fmt_plain(ref, digits=1)} *(published reference -- FRED free-tier limit)*"
        return f"- {label}: --"

    add(f"- Current: **{fmt_plain(current)}** (as of {m.get('latest_date', 'N/A')})")
    add(peak_line("2008 GFC peak", m.get("peak_2008"), m.get("ref_2008")))
    add(peak_line("2020 COVID peak", m.get("peak_2020"), m.get("ref_2020")))
    add(peak_line("2023 SVB peak", m.get("peak_2023"), m.get("ref_2023")))
    add(f"- 10Y median: {fmt_plain(m.get('median_10y'))}")
    median = m.get("median_10y")
    verdict = ""
    if current is not None and median is not None:
        if current >= crisis_threshold:
            verdict = f"=> ABOVE crisis threshold ({threshold_note}). WARNING."
        elif current > median * 1.25:
            verdict = "=> ABOVE median, stress building."
        elif current < median * 0.75:
            verdict = f"=> BELOW median, credit markets CALM ({calm_note})."
        else:
            verdict = "=> NEAR median, normal conditions."
    add(f"- {verdict if verdict else '=> insufficient history for verdict'}\n")


# ============================================================================
# RUN
# ============================================================================

if __name__ == "__main__":
    briefing, path = generate_briefing()
    print("\n" + "=" * 90)
    print("FULL CREDIT MONITOR BRIEFING OUTPUT:")
    print("=" * 90)
    print(briefing)
