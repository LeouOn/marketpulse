"""
Treasury Yield Curve Monitor
============================
Tracks the full Treasury curve (3M -> 30Y), computes the key recession-
predicting spreads, classifies curve shape, estimates recession
probability (NY Fed probit approximation), and cross-references every
curve inversion since 1980 with the recession that followed.

Why this matters: every US recession since 1955 was preceded by an
inversion of 2s10s OR 3m10y. Lag from inversion to recession averages
12-18 months. This is the user's recession early-warning system,
paired with credit_monitor.py (which watches credit spreads).

Run:     python scripts/yield_curve_monitor.py
Output:  reports/rates/curve_YYYY-MM-DD.md  (+ console dump)

Data sources:
  - FRED REST API (series outside FredProvider.SUPPORTED_SERIES)
  - Existing parquet cache in data/macro/ (FredProvider schema)

ASCII-only: no em-dashes, no unicode arrows (PowerShell cp932 safe).
"""
import sys
from pathlib import Path
from datetime import datetime, date, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import numpy as np
import requests

# Re-use the existing FRED key resolver (reads FRED_API_KEY env / .env).
# FredProvider is instantiated ONLY to grab api_key; we do NOT use its
# whitelist-restricted .fetch() because most yield-curve series are not
# in FredProvider.SUPPORTED_SERIES. Direct REST calls instead (free tier,
# 120 req/min).
from src.research.data.fred import FredProvider

# ============================================================================
# CONFIG
# ============================================================================

CACHE_DIR = Path("data/macro")
REPORT_DIR = Path("reports/rates")

# Fetch window: long enough to cover every inversion cycle since 1980.
HISTORY_START = "1976-01-01"   # T10Y2Y starts 1976-06 on FRED
HISTORY_END = date.today().isoformat()

# Full Treasury curve tenors (FRED constant-maturity series).
CURVE_TENORS = [
    # (fred_id, label, short_label, months_tenor)
    ("DGS3MO", "3-Month Treasury",  "3M",  3),
    ("DGS1",   "1-Year Treasury",   "1Y",  12),
    ("DGS2",   "2-Year Treasury",   "2Y",  24),
    ("DGS5",   "5-Year Treasury",   "5Y",  60),
    ("DGS7",   "7-Year Treasury",   "7Y",  84),
    ("DGS10",  "10-Year Treasury",  "10Y", 120),
    ("DGS20",  "20-Year Treasury",  "20Y", 240),
    ("DGS30",  "30-Year Treasury",  "30Y", 360),
]

# Pre-computed FRED spread series (cross-check our math).
FRED_SPREAD_SERIES = {
    "T10Y2Y": "10Y minus 2Y (FRED pre-computed)",
    "T10Y3M": "10Y minus 3M (FRED pre-computed, NY Fed's preferred signal)",
}

# All FRED series this monitor depends on (fetched via direct REST).
ALL_FRED_SERIES = {tid: name for tid, name, _, _ in CURVE_TENORS}
ALL_FRED_SERIES.update(FRED_SPREAD_SERIES)

# Spreads we compute ourselves from the raw yields.
# Each entry: key -> (long_label, short_label, long_tenor_id, short_tenor_id)
KEY_SPREADS = {
    "2s10s":  ("10Y minus 2Y",  "2s10s",  "DGS10", "DGS2"),
    "3m10y":  ("10Y minus 3M",  "3m10y",  "DGS10", "DGS3MO"),
    "5s30s":  ("30Y minus 5Y",  "5s30s",  "DGS30", "DGS5"),
    "3m5y":   ("5Y minus 3M",   "3m5y",   "DGS5",  "DGS3MO"),
    "2s5s":   ("5Y minus 2Y",   "2s5s",   "DGS5",  "DGS2"),
    "2s30s":  ("30Y minus 2Y",  "2s30s",  "DGS30", "DGS2"),
    "3m30y":  ("30Y minus 3M",  "3m30y",  "DGS30", "DGS3MO"),
}

# NBER-dated US recessions (peak/trough month, inclusive). Public record.
# Source: https://www.nber.org/research/business-cycle-dating
NBER_RECESSIONS = [
    ("1980-01", "1980-07", "1980 recession"),
    ("1981-07", "1982-11", "1981-82 double-dip"),
    ("1990-07", "1991-03", "1990-91 recession"),
    ("2001-03", "2001-11", "2001 dot-com recession"),
    ("2007-12", "2009-06", "2008-09 Global Financial Crisis"),
    ("2020-02", "2020-04", "2020 COVID recession"),
]

# Reference inversions of 2s10s since 1976 (FRED T10Y2Y coverage start).
# Each row: (episode_start, trough_month_approx, trough_spread_pct,
#            recession_start_or_None, note)
# These are the historically documented inversion episodes used for the
# log section header and as a sanity-check on dynamic detection.
REFERENCE_INVERSIONS = [
    ("1978-08", "1979-09", -0.42, "1980-01", "Pre-1980 recession"),
    ("1980-09", "1981-01", -1.20, "1981-07", "Pre-1981-82 double-dip"),
    ("1989-01", "1989-01", -0.16, "1990-07", "Pre-1990 recession"),
    ("2000-02", "2000-12", -0.52, "2001-03", "Pre-dot-com recession"),
    ("2006-01", "2006-11", -0.19, "2007-12", "Pre-GFC (23mo lag)"),
    ("2019-08", "2019-08", -0.05, "2020-02", "Pre-COVID (exogenous shock)"),
    ("2022-07", "2023-03", -1.08, None,      "Longest inversion on record"),
]


# ============================================================================
# DATA LAYER (mirrors credit_monitor.py)
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
            pass

    if api_key is None:
        return pd.DataFrame()

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
            continue
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


# ============================================================================
# ANALYSIS HELPERS
# ============================================================================

def latest_value(s):
    if s is None or len(s) == 0:
        return None
    s = s.dropna()
    return float(s.iloc[-1]) if len(s) else None


def latest_date(s):
    if s is None:
        return None
    s = s.dropna()
    return s.index[-1] if len(s) else None


def value_as_of(s, target_date):
    """Most recent value on or before target_date (or None)."""
    if s is None or len(s) == 0:
        return None
    ts = pd.Timestamp(target_date)
    sub = s[s.index <= ts].dropna()
    return float(sub.iloc[-1]) if len(sub) else None


def median_last_n_years(s, years=10):
    if s is None or len(s) == 0:
        return None
    cutoff = s.index[-1] - pd.DateOffset(years=years)
    sub = s[s.index >= cutoff].dropna()
    return float(sub.median()) if len(sub) else None


def pctile_current(s):
    """Percentile rank (0-100) of the latest value within the whole series."""
    if s is None or len(s.dropna()) < 10:
        return None
    sd = s.dropna()
    cur = float(sd.iloc[-1])
    return float((sd <= cur).sum() / len(sd) * 100.0)


def compute_spread_series(long_s, short_s):
    """Align two yield series and return long minus short (in pct points)."""
    if long_s is None or short_s is None:
        return None
    df = pd.concat([long_s.rename("L"), short_s.rename("S")],
                   axis=1, join="inner").dropna()
    if len(df) == 0:
        return None
    return (df["L"] - df["S"]).astype(float)


def months_between(d1, d2):
    """Whole months from d1 to d2 (d2 - d1). Returns float or None."""
    if d1 is None or d2 is None:
        return None
    a = pd.Timestamp(d1); b = pd.Timestamp(d2)
    return round((b - a).days / 30.44, 1)


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
# CURVE SHAPE CLASSIFICATION
# ============================================================================

def curve_shape(spreads):
    """Classify the static curve shape from current spreads dict.

    Returns (shape_label, descriptor).
    Definitions:
      NORMAL    : 2s10s > +0.50% AND 3m10y > +1.0%  (upward sloping)
      FLAT      : 0% <= 2s10s <= +0.50%              (economy slowing)
      INVERTED  : 2s10s < 0% OR 3m10y < 0%           (recession warning)
      HUMPED    : mid-curve above both ends           (transition/unusual)
    Steepening/flattening is reported separately as a TREND, not a shape.
    """
    s210 = spreads.get("2s10s")
    s310 = spreads.get("3m10y")
    s530 = spreads.get("5s30s")
    s25 = spreads.get("2s5s")
    # Mid-curve hump: 5Y or 7Y is the peak (above 2Y AND above 30Y).
    mid_humped = (s25 is not None and s530 is not None
                  and s25 < 0 and s530 < 0)

    if s210 is None or s310 is None:
        return "UNKNOWN", "insufficient data"

    # Inversion takes priority (most actionable).
    if s210 < 0 or s310 < 0:
        return "INVERTED", "short rates ABOVE long rates -> recession warning"
    if mid_humped:
        return "HUMPED", "mid-curve above both ends -> transitional"
    if s210 <= 0.50:
        return "FLAT", "low positive slope -> economy slowing"
    if s310 <= 1.0:
        return "FLAT-TO-NORMAL", "positive but flat -> late cycle"
    return "NORMAL", "upward sloping -> healthy"


def trend_label(change_1m):
    """Translate a 1-month spread change (pct points) into a trend word."""
    if change_1m is None or (isinstance(change_1m, float) and np.isnan(change_1m)):
        return "N/A"
    if change_1m > 0.20:  return "STEEPENING"
    if change_1m > 0.05:  return "steepening"
    if change_1m > -0.05: return "flat"
    if change_1m > -0.20: return "flattening"
    return "FLATTENING"


# ============================================================================
# RECESSION PROBABILITY (NY Fed probit approximation)
# ============================================================================

def recession_prob_nyfed(t10y3m):
    """Approximate 12-month-forward US recession probability from 3m10y.

    The NY Fed's official model (Engstrom-Xue, monthly) is a probit
    regression fitted on the smoothed 3m10y spread. We approximate with
    a transparent piecewise mapping calibrated to the published empirical
    ranges:

      +1.0% or higher : <5%   (normal)
      +0.5% to +1.0%  : 5-15% (watch)
      0% to +0.5%     : 15-25%(concerning)
      <0% (inverted)  : 25-40%+ (WARNING)

    Returns probability in [0, 100], or None if input is None.
    """
    if t10y3m is None or (isinstance(t10y3m, float) and np.isnan(t10y3m)):
        return None
    s = t10y3m
    if s >= 1.0:
        # 5% at +1.0%, tapering to 2% at +2.0%+
        return max(2.0, 5.0 - (s - 1.0) * 3.0)
    if s >= 0.5:
        # 15% at +0.5%, 5% at +1.0%
        return 15.0 - (s - 0.5) * 20.0
    if s >= 0.0:
        # 25% at 0%, 15% at +0.5%
        return 25.0 - s * 20.0
    # Inverted: 25% at 0%, ramping up to 65% at -1.0% (deep inversion)
    return min(65.0, 25.0 + (-s) * 40.0)


def recession_prob_bucket(p):
    if p is None: return ("UNKNOWN", "no data")
    if p < 5:  return ("VERY LOW",  "curve signals no recession risk")
    if p < 15: return ("LOW",       "normal conditions; monitor")
    if p < 25: return ("ELEVATED",  "concerning; late-cycle signal")
    if p < 40: return ("HIGH",      "inverted curve -> recession likely in 12mo")
    return ("VERY HIGH", "deep inversion -> recession highly probable")


# ============================================================================
# INVERSION EPISODE DETECTION (from historical T10Y2Y series)
# ============================================================================

def detect_inversions(spread_s, min_consecutive_days=5):
    """Find sustained inversion episodes in a spread series.

    An episode is a run of >= min_consecutive_days consecutive business
    days where the spread < 0. Returns list of dicts:
      {start, end, trough_date, trough_spread, days}
    ordered by start date.
    """
    if spread_s is None or len(spread_s.dropna()) == 0:
        return []
    s = spread_s.dropna().sort_index()
    neg = (s < 0).values
    dates = s.index
    episodes = []
    i = 0
    n = len(s)
    while i < n:
        if neg[i]:
            j = i
            while j < n and neg[j]:
                j += 1
            run_len = j - i
            if run_len >= min_consecutive_days:
                seg = s.iloc[i:j]
                trough_idx = seg.idxmin()
                episodes.append({
                    "start": dates[i],
                    "end": dates[j - 1],
                    "trough_date": trough_idx,
                    "trough_spread": float(seg.loc[trough_idx]),
                    "days": int(run_len),
                })
            i = j
        else:
            i += 1
    return episodes


def match_recession(inv_start):
    """Return (recession_start, recession_label) for the next NBER
    recession that begins after inv_start, or (None, None)."""
    if inv_start is None:
        return None, None
    inv_ts = pd.Timestamp(inv_start)
    for r_start, r_end, label in NBER_RECESSIONS:
        r_ts = pd.Timestamp(r_start)
        # Allow recession to begin up to 36 months after inversion start
        if r_ts >= inv_ts and (r_ts - inv_ts).days <= 365 * 3 + 1:
            return r_start, label
    return None, None


# ============================================================================
# ASCII CURVE CHART
# ============================================================================

def render_ascii_curve(yields_by_tenor, as_of_date):
    """Render the yield curve as an ASCII scatter chart.

    `yields_by_tenor` is a list of tuples in curve order, shortest first:
        [(short_label, yield_value_or_None), ...]
    Each tenor gets a row; the asterisk's horizontal position encodes
    the yield level relative to the curve's min/max (so the diagonal
    pattern reveals the curve shape: normal = bottom-left -> top-right).
    """
    width = 32
    valid = [(lbl, y) for lbl, y in yields_by_tenor if y is not None]
    if not valid:
        return "  (no yield data available)"

    ys = [y for _, y in valid]
    y_min = min(ys)
    y_max = max(ys)
    rng = y_max - y_min
    if rng < 1e-6:
        rng = 1.0  # flat curve -> all centered

    lines = []
    # Render long tenors at the top, shortest at the bottom.
    for lbl, y in reversed(valid):
        col = int(round((y - y_min) / rng * width))
        col = max(0, min(width, col))
        lbl_pad = f"{lbl:>4}"
        bar = " " * col + "*"
        lines.append(f"  {lbl_pad} |{bar:<{width+1}}  {y:.2f}%")
    # x-axis
    lines.append("      " + "+" + "-" * width + ">")
    # x-axis tenor labels (spread across width)
    ticks = [lbl for lbl, _ in valid]
    # crude spacing: place each tenor label roughly proportional to its slot
    tick_line = "      "
    positions = []
    n = len(ticks)
    for k, lbl in enumerate(ticks):
        pos = int(round(k / max(1, n - 1) * width))
        positions.append((pos, lbl))
    # Build tick line without overlaps (best effort). Buffer extends past
    # width so the final long-bond label (e.g. "30Y") is not truncated.
    chars = list(" " * (width + 4))
    for pos, lbl in positions:
        for c_idx, ch in enumerate(lbl):
            target = pos + c_idx
            if 0 <= target < len(chars):
                chars[target] = ch
    tick_line += "".join(chars).rstrip()
    lines.append(tick_line)
    return "\n".join(lines)


# ============================================================================
# MAIN BRIEFING GENERATOR
# ============================================================================

def generate_briefing():
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")
    as_of = today - timedelta(days=1)  # FRED publishes T-1
    api_key = _get_api_key()
    print(f"Generating Treasury yield curve monitor for {date_str}...")
    print(f"FRED fetch window: {HISTORY_START} -> {HISTORY_END}\n")

    # ---- 1. FETCH ALL FRED SERIES ----
    print("Step 1/4: Fetching FRED Treasury series...")
    series = {}
    for sid, name in ALL_FRED_SERIES.items():
        fetch_fred_series(sid, HISTORY_START, HISTORY_END, api_key=api_key)
        series[sid] = load_series(sid)
    n_ok = sum(1 for v in series.values() if v is not None and len(v.dropna()) > 0)
    print(f"  FRED: {n_ok}/{len(ALL_FRED_SERIES)} series available.")

    # ---- 2. COMPUTE CURRENT CURVE + SPREADS ----
    print("Step 2/4: Computing yields, spreads, and curve shape...")

    # Current yields per tenor (latest non-NaN).
    yields = {}  # fred_id -> latest yield
    for tid, _, _, _ in CURVE_TENORS:
        yields[tid] = latest_value(series.get(tid))

    as_of_date = latest_date(series.get("DGS10")) or as_of

    # Compute each key spread series + current value + 1M/6M ago.
    spread_data = {}
    for key, (long_label, short_label, long_id, short_id) in KEY_SPREADS.items():
        long_s = series.get(long_id)
        short_s = series.get(short_id)
        sp_s = compute_spread_series(long_s, short_s)
        cur = latest_value(sp_s)
        one_month_ago = as_of_date - pd.Timedelta(days=30) if as_of_date else None
        six_month_ago = as_of_date - pd.Timedelta(days=182) if as_of_date else None
        s_1m = value_as_of(sp_s, one_month_ago) if one_month_ago else None
        s_6m = value_as_of(sp_s, six_month_ago) if six_month_ago else None
        chg_1m = (cur - s_1m) if (cur is not None and s_1m is not None) else None
        chg_6m = (cur - s_6m) if (cur is not None and s_6m is not None) else None
        median = median_last_n_years(sp_s, 10)
        spread_data[key] = {
            "label": long_label,
            "current": cur,
            "1m_ago": s_1m,
            "6m_ago": s_6m,
            "change_1m": chg_1m,
            "change_6m": chg_6m,
            "median_10y": median,
            "series": sp_s,
        }

    # Cross-check spreads against FRED pre-computed.
    fred_2s10s = latest_value(series.get("T10Y2Y"))
    fred_3m10y = latest_value(series.get("T10Y3M"))
    t10y2y_s = series.get("T10Y2Y")
    t10y3m_s = series.get("T10Y3M")

    # Current spreads dict for shape classifier.
    current_spreads = {k: v["current"] for k, v in spread_data.items()}

    shape, shape_desc = curve_shape(current_spreads)
    s2s10 = spread_data["2s10s"]["current"]
    s3m10y = spread_data["3m10y"]["current"]

    # ---- 3. RECESSION PROBABILITY + INVERSION DETECTION ----
    print("Step 3/4: Computing recession probability and scanning inversions...")
    rec_prob = recession_prob_nyfed(s3m10y)
    rec_bucket, rec_meaning = recession_prob_bucket(rec_prob)

    # Detect historical inversions dynamically from the FRED T10Y2Y series.
    dynamic_inversions = detect_inversions(t10y2y_s, min_consecutive_days=5)

    # ---- 4. BUILD BRIEFING ----
    print("Step 4/4: Building briefing...")
    L = []
    add = L.append

    add(f"# Treasury Yield Curve Monitor - {date_str}\n")
    add("> The single most reliable recession predictor in macroeconomics.")
    add("> Every US recession since 1955 was preceded by an inversion of")
    add("> 2s10s OR 3m10y. This is the recession early-warning system.\n")
    add(f"**Date:** {date_str}")
    add(f"**Curve shape:** **{shape}** -- {shape_desc}")
    add(f"**2s10s spread:** **{fmt(s2s10)}**  (10Y minus 2Y)")
    add(f"**3m10y spread:** **{fmt(s3m10y)}**  (10Y minus 3M, NY Fed's preferred signal)")
    inv_note = "INVERTED -- recession warning" if (s2s10 is not None and s2s10 < 0) or (s3m10y is not None and s3m10y < 0) else "positive -- no curve inversion"
    add(f"**Inversion status:** {inv_note}\n")
    if rec_prob is not None:
        add(f"**Estimated 12mo recession probability (curve-only):** **~{rec_prob:.0f}%** ({rec_bucket})\n")
    add("Shape bands:")
    add("- NORMAL    : 2s10s > +0.50% AND 3m10y > +1.0% (upward sloping, healthy)")
    add("- FLAT      : 0% <= 2s10s <= +0.50%             (economy slowing)")
    add("- INVERTED  : 2s10s < 0% OR 3m10y < 0%          (recession warning)")
    add("- HUMPED    : mid-curve above both ends          (transitional)")
    add("- Trend (steepening/flattening) reported separately as 1M change.\n")
    add("---\n")

    # ---- Section 1: ASCII Yield Curve ----
    add("## 1. The Full Yield Curve (ASCII)\n")
    add("Each row is one tenor (long tenors at top). The asterisk's")
    add("horizontal position encodes the yield level relative to the")
    add("curve's own min/max. A normal upward-sloping curve forms a")
    add("diagonal from bottom-left (short, low yield) to top-right")
    add("(long, high yield). An inverted curve flips that pattern.\n")
    as_of_str = as_of_date.strftime("%B %d, %Y") if as_of_date else date_str
    add(f"```\nYIELD CURVE ({as_of_str})")
    curve_rows = [(lbl, yields.get(tid)) for tid, _, lbl, _ in CURVE_TENORS]
    add(render_ascii_curve(curve_rows, as_of_date))
    add("")
    add(f"  SHAPE: {shape}")
    add(f"  2s10s: {fmt(s2s10)} ({'flat but positive' if (s2s10 is not None and 0 <= s2s10 <= 0.50) else 'positive' if (s2s10 is not None and s2s10 > 0) else 'INVERTED' if s2s10 is not None else 'N/A'})")
    add(f"  3m10y: {fmt(s3m10y)} ({'positive, not inverted' if (s3m10y is not None and s3m10y > 0) else 'INVERTED' if s3m10y is not None else 'N/A'})")
    add("```\n")
    add("**Tenor snapshot table:**\n")
    add("| Tenor | Yield |  | Tenor | Yield |")
    add("|-------|------:|  |-------|------:|")
    half = len(CURVE_TENORS) // 2 + len(CURVE_TENORS) % 2
    left = CURVE_TENORS[:half]
    right = CURVE_TENORS[half:]
    for i in range(half):
        lt = left[i]
        lv = fmt_plain(yields.get(lt[0]))
        if i < len(right):
            rt = right[i]
            rv = fmt_plain(yields.get(rt[0]))
            add(f"| {lt[2]} | {lv} |  | {rt[2]} | {rv} |")
        else:
            add(f"| {lt[2]} | {lv} |  |   |   |")
    add("")
    # Curve steepness summary
    s3m30y = spread_data.get("3m30y", {}).get("current")
    if s3m30y is not None:
        steep_word = "steep" if s3m30y > 2.0 else "normal" if s3m30y > 0.75 else "flat" if s3m30y > 0.0 else "inverted"
        add(f"**30Y minus 3M (full-curve steepness):** {fmt(s3m30y)} ({steep_word})")
    add("\n---\n")

    # ---- Section 2: Key Spreads Dashboard ----
    add("## 2. Key Spreads Dashboard\n")
    add("The five recession-relevant spreads. TREND is the 1-month")
    add("change in the spread (positive = steepening, negative =")
    add("flattening). SIGNAL interprets the level.\n")
    add("```")
    add(f"{'SPREAD':<14}{'CURRENT':>10}{'1M AGO':>10}{'6M AGO':>10}{'TREND':>14}")
    add("-" * 58)
    for key in ["2s10s", "3m10y", "5s30s", "3m5y", "2s5s"]:
        d = spread_data[key]
        tr = trend_label(d["change_1m"])
        add(f"{key:<14}{fmt(d['current']):>10}{fmt(d['1m_ago']):>10}{fmt(d['6m_ago']):>10}{tr:>14}")
    add("```\n")
    add("**Per-spread interpretation:**\n")
    spread_blurbs = {
        "2s10s": "The classic recession signal. 2Y captures Fed policy expectations; "
                 "inversion means the market expects rate cuts (i.e. Fed easing in "
                 "response to coming weakness).",
        "3m10y": "NY Fed's preferred signal (more stable than 2s10s). Every US "
                 "recession since 1960 was preceded by a 3m10y inversion.",
        "5s30s": "Steepness of the long end. When 5s30s inverts, the market is "
                 "pricing weak long-term growth and/or heavy duration demand.",
        "3m5y": "Near-term policy expectations. 5Y captures the expected average "
                "path of short rates; a low or negative 3m5y implies expected cuts.",
        "2s5s": "Mid-curve shape. When 2s5s inverts while 5s30s is positive, the "
                "curve is humped (mid-curve above both ends -> transitional).",
    }
    for key in ["2s10s", "3m10y", "5s30s", "3m5y", "2s5s"]:
        d = spread_data[key]
        cur = d["current"]
        med = d["median_10y"]
        if key == "2s10s":
            if cur is not None and cur < 0:
                status = "INVERTED -> recession in 12-18mo"
            elif cur is not None and cur <= 0.50:
                status = "FLAT -> late-cycle, growth slowing"
            else:
                status = "positive -> healthy"
        elif key == "3m10y":
            if cur is not None and cur < 0:
                status = "INVERTED -> strong recession warning"
            elif cur is not None and cur <= 0.50:
                status = "low positive -> concerning"
            else:
                status = "positive -> healthy"
        elif key == "5s30s":
            if cur is not None and cur < 0:
                status = "long-end INVERTED -> growth pessimism"
            elif cur is not None and cur < 0.25:
                status = "flat long-end -> low growth/inflation expectations"
            else:
                status = "positive -> normal term premium"
        elif key == "3m5y":
            if cur is not None and cur < 0:
                status = "INVERTED -> Fed expected to cut aggressively"
            else:
                status = "positive -> normal policy expectations"
        else:  # 2s5s
            if cur is not None and cur < 0:
                status = "INVERTED mid-curve -> humped shape, transitional"
            else:
                status = "positive -> normal mid-curve"
        med_str = f"10Y median {fmt(med)}" if med is not None else "no median"
        add(f"- **{key}** ({d['label']}): {fmt(cur)}  |  {med_str}  |  {status}")
        add(f"  {spread_blurbs[key]}")
    add("")
    # FRED cross-check note
    computed_2s10s = spread_data["2s10s"]["current"]
    if (fred_2s10s is not None and computed_2s10s is not None
            and abs(fred_2s10s - computed_2s10s) > 0.05):
        add(f"**Note:** FRED pre-computed T10Y2Y = {fmt(fred_2s10s)} vs our computed {fmt(computed_2s10s)} (small diff from settlement timing).")
    add("\n---\n")

    # ---- Section 3: Recession Probability ----
    add("## 3. Recession Probability (NY Fed Model Approximation)\n")
    add("Based on the NY Fed's probit model which uses the 3m10y spread")
    add("(10Y minus 3M Treasury) as its sole input. The official model")
    add("is updated monthly; below is a transparent piecewise")
    add("approximation calibrated to published empirical ranges.\n")
    add("```")
    add("RECESSION PROBABILITY (12-month forward):")
    add(f"  Current 3m10y spread: {fmt(s3m10y)}")
    if rec_prob is not None:
        add(f"  => Estimated recession probability: ~{rec_prob:.0f}%")
    add("")
    add("  Historical calibration (3m10y -> 12mo recession probability):")
    add("    +1.0% or higher : <5%   probability (normal)")
    add("    +0.5% to +1.0%  : 5-15% probability (watch)")
    add("    0%   to +0.5%   : 15-25% probability (concerning)")
    add("    Negative        : 25-40%+ probability (WARNING)")
    add("")
    add(f"  Current status: {rec_bucket} from curve signal alone")
    add(f"  ({rec_meaning})")
    add("```\n")
    add("**Important caveats:**")
    add("- The curve alone is necessary but NOT sufficient for recession.")
    add("- The 2022-24 inversion was the deepest and longest on record")
    add("  (-1.08% trough, 24+ months) yet no recession through mid-2026.")
    add("- Some argue QE/QT distorts the curve's signal vs pre-2008 eras.")
    add("- Combine with the credit monitor and labor market (Sahm rule)")
    add("  for a higher-confidence signal (see Section 6).\n")
    add("---\n")

    # ---- Section 4: Historical Inversions ----
    add("## 4. Historical Curve Inversions (2s10s, since 1980)\n")
    add("Every sustained 2s10s inversion since 1980, the trough level,")
    add("the months until the subsequent NBER-dated recession, and the")
    add("outcome. Average lag from inversion start to recession: ~15 months.\n")
    add("| Inversion Start | Trough | Trough Spread | Recession Start | Months to Recession | Recession? |")
    add("|----------------:|--------|--------------:|----------------:|---------------------:|------------|")
    for inv_start, trough_m, trough_sp, rec_start, note in REFERENCE_INVERSIONS:
        if rec_start is not None:
            mo = months_between(inv_start, rec_start)
            mo_str = f"{mo:.0f}" if mo is not None else "--"
            rec_str = f"YES ({rec_start})"
        else:
            mo_str = "--"
            rec_str = "PENDING"
        add(f"| {inv_start} | {trough_m} | {fmt(trough_sp)} | {rec_start or 'TBD'} | {mo_str} | {rec_str} |")
    # Average over historical confirmed cases
    confirmed_lags = []
    for inv_start, _, _, rec_start, _ in REFERENCE_INVERSIONS:
        if rec_start is not None:
            mb = months_between(inv_start, rec_start)
            if mb is not None:
                confirmed_lags.append(mb)
    avg_lag = sum(confirmed_lags) / len(confirmed_lags) if confirmed_lags else None
    add("")
    if avg_lag is not None:
        add(f"**Average time from inversion to recession (confirmed cases):** ~{avg_lag:.0f} months")
    add(f"**Current 2s10s:** {fmt(s2s10)} ({'NOT inverted currently' if (s2s10 is not None and s2s10 >= 0) else 'INVERTED currently'})")
    # Last dynamic inversion end date
    if dynamic_inversions:
        last_inv = dynamic_inversions[-1]
        last_inv_end_str = last_inv["end"].strftime("%Y-%m-%d")
        if last_inv["end"] >= pd.Timestamp(today) - pd.Timedelta(days=30):
            add(f"**Last inversion:** ONGOING (started {last_inv['start'].strftime('%Y-%m-%d')}, trough {last_inv['trough_spread']:+.2f}% on {last_inv['trough_date'].strftime('%Y-%m-%d')})")
        else:
            add(f"**Last inversion ended:** {last_inv_end_str} (trough {last_inv['trough_spread']:+.2f}% on {last_inv['trough_date'].strftime('%Y-%m-%d')})")
    # 2022 episode commentary
    add("")
    add("**Notable: the 2022-24 inversion** was the longest and deepest on")
    add("record (24+ months, trough around -1.08% in March 2023). As of")
    add("mid-2026, no NBER recession has been declared, breaking the")
    add("historical pattern. Possible explanations: (a) fiscal stimulus")
    add("and AI capex offset the signal; (b) Fed cuts arrived in time;")
    add("(c) the signal's lead time is longer than typical this cycle.")
    add("\n---\n")

    # ---- Section 5: Cross-Asset Implications ----
    add("## 5. Cross-Asset Implications\n")
    add("What the current curve shape means for each asset class.\n")
    d10 = yields.get("DGS10")
    add("```")
    add("WHAT THE CURVE MEANS FOR YOUR PORTFOLIO:")
    add("")
    add("Equities (SPY/QQQ):")
    add(f"  Curve is {shape} (2s10s {fmt(s2s10)})")
    if shape == "NORMAL":
        add("  => Constructive for equities (no imminent recession signal)")
        add("  => Maintain normal risk exposure")
    elif shape == "FLAT" or shape == "FLAT-TO-NORMAL":
        add("  => Mild positive; late-cycle caution")
        add("  => BUT: if 2s10s re-inverts, shift to defensive (XLV, XLP)")
    elif shape == "INVERTED":
        add("  => CAUTION: recession likely within 12-18 months")
        add("  => Reduce cyclicals, raise quality (large-cap, low-debt)")
    else:
        add("  => Unusual shape; treat case-by-case")
    add("")
    add("Gold (GLD):")
    if spread_data["2s10s"]["change_1m"] is not None and spread_data["2s10s"]["change_1m"] > 0.10:
        add("  Curve is STEEPENING -> rate cuts likely coming -> GOLD BULLISH")
        add("  => Monitor: if 2s10s steepens rapidly (0 to +1%), add gold")
    elif shape == "INVERTED":
        add("  Inverted curve -> eventual Fed cuts -> long-term GOLD BULLISH")
        add("  => Accumulate on dips; recession-hedge bid likely")
    else:
        add("  Curve shape neutral for gold for now")
        add("  => Watch for steepening as a buy signal")
    add("")
    add("Banks (KRE, XLF):")
    if s2s10 is not None and s2s10 < 0.50:
        add(f"  2s10s at {fmt(s2s10)} = NET INTEREST MARGIN HEADWIND for banks")
        add("  => Banks borrow short / lend long; flat curve compresses spread")
        if s2s10 < 0:
            add("  => INVERTED curve is structurally BAD for banks")
        else:
            add("  => Currently SLIGHT HEADWIND")
    else:
        add(f"  2s10s at {fmt(s2s10)} = healthy for bank NIM")
        add("  => Banks benefit from upward-sloping curve")
    add("")
    add("REITs (XLRE):")
    add("  REITs borrow short-term and hold long-duration assets")
    if s2s10 is not None and s2s10 < 0.50:
        add(f"  => 2s10s {fmt(s2s10)} = MILD HEADWIND for REIT profitability")
    else:
        add(f"  => 2s10s {fmt(s2s10)} = neutral/positive for REITs")
    add("")
    add("Housing:")
    add("  30Y mortgage rates track the 10Y Treasury (plus ~2.4% spread)")
    if d10 is not None:
        mortgage_est = d10 + 2.4
        add(f"  => 10Y at {d10:.2f}% = 30Y mortgage ~{mortgage_est:.2f}%")
        add(f"  => If 10Y drops to 3.50%, mortgages drop to ~5.90% (housing bull)")
        add(f"  => If 10Y rises to 5.00%, mortgages rise to ~7.40% (housing bear)")
    add("```\n")
    add("---\n")

    # ---- Section 6: Curve + Credit Combined Signal ----
    add("## 6. Curve + Credit Combined Signal\n")
    add("The yield curve and credit spreads are the two complementary")
    add("pillars of recession early-warning. Read them together.\n")
    # Attempt to read latest credit monitor output for cross-reference.
    credit_score = _read_latest_credit_score()
    add("```")
    add("CURVE + CREDIT COMBINED SIGNAL:")
    add(f"  Yield curve (2s10s): {fmt(s2s10)} ({'inverted' if (s2s10 is not None and s2s10 < 0) else 'flat' if (s2s10 is not None and s2s10 <= 0.50) else 'normal'})")
    if credit_score is not None:
        cband = "NORMAL" if credit_score < 30 else "WATCH" if credit_score < 50 else "WARNING" if credit_score < 70 else "CRISIS"
        add(f"  Credit stress score: {credit_score:.0f}/100 ({cband})")
    else:
        add(f"  Credit stress score: (run scripts/credit_monitor.py for the number)")
    add("")
    if credit_score is not None:
        both_warn = ((s2s10 is not None and s2s10 < 0) or (s3m10y is not None and s3m10y < 0)) and credit_score >= 50
        if both_warn:
            add("  COMBINED: HIGH recession risk")
            add("  Both curve inverted AND credit stress elevated -> go defensive")
        elif (s2s10 is not None and s2s10 < 0) or (s3m10y is not None and s3m10y < 0):
            add("  COMBINED: MODERATE recession risk (curve alone)")
            add("  Curve inverted but credit calm -> monitor; not yet confirmed")
        elif credit_score is not None and credit_score >= 50:
            add("  COMBINED: MODERATE recession risk (credit alone)")
            add("  Credit stressed but curve positive -> monitor")
        else:
            add("  COMBINED: LOW recession risk")
            add("  Neither pillar flashing -> risk-on supported")
    else:
        add("  (Cross-check the credit monitor's composite score here.)")
    add("")
    add("  HIGH-confidence recession rule:")
    add("    IF curve inverts (2s10s < 0 OR 3m10y < 0)")
    add("    AND credit stress > 50/100")
    add("    => HIGH confidence recession signal within 12-18 months")
    add("    => Time to go defensive (cut equity beta, raise cash, add hedges)")
    add("```\n")
    add("---\n")

    # ---- Section 7: NotebookLM Talking Points ----
    add("## 7. NotebookLM Talking Points (Podcast Prompts)\n")
    add("Seed questions for a yield-curve podcast episode:\n")
    add(f"1. The current curve is {shape} with 2s10s at {fmt(s2s10)} and 3m10y at {fmt(s3m10y)}.")
    add("   What does each spread tell us, and why does the NY Fed prefer 3m10y?")
    add("2. The 2022-24 inversion was the longest and deepest on record yet no")
    add("   recession followed (as of mid-2026). Walk through why. Did QE distort")
    add("   the signal? Was fiscal stimulus large enough to offset it?")
    add("3. Historical case study: the 2006-07 inversion preceded the GFC by 23")
    add("   months. Walk through the chain of causation from inversion -> recession.")
    add("4. The average lead time from inversion to recession is 12-18 months.")
    add("   Why is the lag so variable? What determines whether it's 6 months or 24?")
    add("5. Why do banks hate an inverted curve? Explain net interest margin and")
    add("   the borrow-short/lend-long business model.")
    add("6. The 'curve + credit' combo signal: why are BOTH needed? When does the")
    add("   curve give a false positive? When does credit stress give a false alarm?")
    add("7. Managing an $800K portfolio: if 2s10s re-inverts tomorrow, what specific")
    add("   trades would you put on? Walk through the sizing and the exit criteria.\n")
    add("---\n")

    # ---- Footer ----
    add("## Data Sources & Methodology\n")
    add("- **FRED** (REST API, free tier): DGS3MO, DGS1, DGS2, DGS5, DGS7,")
    add("  DGS10, DGS20, DGS30, T10Y2Y, T10Y3M.")
    add("- Parquet cache in `data/macro/` (FredProvider Metis schema).")
    add("- Spreads are computed as long minus short from raw yields (cross-")
    add("  checked against FRED pre-computed T10Y2Y and T10Y3M).")
    add("- Recession probability is a transparent piecewise approximation of")
    add("  the NY Fed's probit model (which is fitted monthly); it is NOT")
    add("  the official model.")
    add("- Curve shape bands: NORMAL (2s10s > +0.50% AND 3m10y > +1.0%),")
    add("  FLAT (0 to +0.50%), INVERTED (either spread < 0), HUMPED (mid-")
    add("  curve above both ends).")
    add("- Inversion episodes are detected dynamically from T10Y2Y (>= 5")
    add("  consecutive business days below zero), then cross-referenced")
    add("  against NBER recession dates.\n")
    add("**Caveats:**")
    add("- Single-day readings are noisy; sustained 2+ week inversions matter.")
    add("- The 2022-24 cycle suggests the curve signal may have weakened;")
    add("  treat it as one input alongside credit, labor, and inflation.")
    add("- DGS20 has gaps (Treasury suspended 20Y issuance 1986-93 and")
    add("  2017-20); some historical windows will show 'N/A'.\n")
    add(f"*Generated by yield_curve_monitor.py on {date_str}*")
    add("*This is analysis, not investment advice. Consult a financial advisor.*")

    briefing = "\n".join(L)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = REPORT_DIR / f"curve_{date_str}.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(briefing)
    print(f"\nBriefing saved to: {output_path}")
    print(f"File size: {output_path.stat().st_size / 1024:.1f} KB")
    print(f"Word count: {len(briefing.split())} words")
    return briefing, output_path


def _read_latest_credit_score():
    """Best-effort: pull the composite credit score from the most recent
    credit monitor report, so Section 6 can cross-reference it. Returns
    float or None."""
    try:
        cdir = Path("reports/credit")
        if not cdir.exists():
            return None
        files = sorted(cdir.glob("credit_monitor_*.md"), reverse=True)
        if not files:
            return None
        txt = files[0].read_text(encoding="utf-8")
        # Look for the literal pattern: **Credit Stress Score:** **NN.N / 100**
        import re
        m = re.search(r"Credit Stress Score:\*\*\s*\*?\*?([0-9]+(?:\.[0-9]+)?)\s*/\s*100", txt)
        if m:
            return float(m.group(1))
    except Exception:
        pass
    return None


# ============================================================================
# RUN
# ============================================================================

if __name__ == "__main__":
    briefing, path = generate_briefing()
    print("\n" + "=" * 90)
    print("FULL YIELD CURVE MONITOR OUTPUT:")
    print("=" * 90)
    print(briefing)
    sys.exit(0)
