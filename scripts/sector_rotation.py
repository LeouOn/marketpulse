"""
Sector Rotation Tracker
======================
Tells you WHAT THE MARKET IS BETTING ON before the charts confirm it.

Tracks all 11 S&P sector ETFs plus 6 key sub-sectors, ranks them by relative
strength vs SPY, identifies the rotation pattern (RISK_ON, DEFENSIVE,
INFLATION, RATE-SENSITIVE, FLIGHT-TO-SAFETY), and maps it to the business
cycle. The KEY OUTPUT for this user is the NQ/MNQ implication section:
Tech (XLK) + Semis (SMH) are ~50% of Nasdaq weight, so their leadership
directly determines whether MNQ trend-following is favorable or dangerous.

Run:     python scripts/sector_rotation.py
Output:  reports/sectors/rotation_YYYY-MM-DD.md  (+ console dump)

Data sources:
  - yfinance (cached to data/yahoo_cache/*.parquet, schema-compatible
    with the existing Yahoo cache: ts, open, high, low, close, volume, source)
  - Benchmarks: SPY (S&P 500), QQQ (Nasdaq 100)

ASCII-only: no em-dashes, no unicode arrows (PowerShell cp932 safe).
"""
import sys
from pathlib import Path
from datetime import datetime, date, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import numpy as np
import yfinance as yf

# ============================================================================
# CONFIG
# ============================================================================

CACHE_DIR = Path("data/yahoo_cache")
REPORT_DIR = Path("reports/sectors")

# Fetch window: 1 year gives us 50d/200d MAs, 6M/YTD returns, and 52w high.
FETCH_PERIOD = "1y"

# 11 S&P sector ETFs (the official Select Sector SPDRs).
SP_SECTORS = {
    "XLK":  "Technology",
    "XLF":  "Financials",
    "XLE":  "Energy",
    "XLV":  "Health Care",
    "XLY":  "Consumer Discretionary",
    "XLP":  "Consumer Staples",
    "XLI":  "Industrials",
    "XLU":  "Utilities",
    "XLB":  "Materials",
    "XLRE": "Real Estate",
    "XLC":  "Communication Services",
}

# Key sub-sectors (institutional beta proxies).
SUB_SECTORS = {
    "SMH": "Semiconductors",
    "KRE": "Regional Banks",
    "XOP": "Oil & Gas E&P",
    "IYT": "Transportation",
    "IHI": "Medical Devices",
    "XME": "Metals & Mining",
}

# Benchmarks for relative-strength computation.
BENCHMARKS = {
    "SPY": "S&P 500 (primary benchmark)",
    "QQQ": "Nasdaq 100 (tech-heavy benchmark)",
}

# Rotation buckets used for pattern detection. Average rank (1 = strongest)
# within each bucket determines which rotation regime is active.
ROTATION_BUCKETS = {
    "RISK_ON":          ["XLK", "XLY", "XLI", "SMH"],            # growth bet
    "DEFENSIVE":        ["XLP", "XLU", "XLV"],                   # risk-off
    "INFLATION":        ["XLE", "XLB", "XOP", "XME"],            # commodity bet
    "RATE_SENSITIVE":   ["XLF", "XLRE", "KRE"],                  # rate expectations
    "FLIGHT_TO_SAFETY": ["XLU", "XLP"],                          # panic bid
}

# Business-cycle mapping (4-quadrant framework).
CYCLE_BUCKETS = {
    "EARLY":     ["XLK", "XLY", "XLI", "XLF"],          # growth leaders
    "MID":       ["XLI", "XLB", "XLE", "XOP"],          # cyclical leaders
    "LATE":      ["XLE", "XLB", "XLP", "XME"],          # commodity + defensives
    "RECESSION": ["XLP", "XLU", "XLV"],                 # defensive leaders
}

# Smart money (institutional favorites) vs risk money (retail/growth favorites).
SMART_MONEY = ["XLF", "XLI", "XLB"]
RISK_MONEY  = ["XLK", "XLY", "SMH"]

# NQ / Nasdaq-100 weights (approximate, public record). XLK + SMH together
# are the dominant driver of NQ direction -- this is why we flag them.
NQ_TECH_DRIVERS = ["XLK", "SMH"]

# Return windows in trading days.
WINDOWS = {"1W": 5, "1M": 21, "3M": 63, "6M": 126}

# Momentum composite weights (sum to 1.0). Relative-to-SPY returns only.
MOMENTUM_WEIGHTS = {"1W": 0.10, "1M": 0.25, "3M": 0.30, "6M": 0.20, "YTD": 0.15}


# ============================================================================
# DATA LAYER
# ============================================================================

def fetch_sector_history(tickers, period=FETCH_PERIOD, force=False):
    """Fetch close-price history for a list of tickers.

    Cache-first against data/yahoo_cache/{ticker}.parquet (schema-compatible
    with the existing Yahoo cache: ts, open, high, low, close, volume, source).
    A cache file younger than ~12 hours is served without a network call
    unless force=True. Returns dict: ticker -> pd.Series (close, indexed by ts).
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out = {}
    # Batch download in one call (much faster than per-ticker).
    need_fetch = []
    for t in tickers:
        cache_path = CACHE_DIR / f"{t}.parquet"
        if not force and _cache_fresh(cache_path):
            s = _load_series_from_cache(cache_path, period)
            if s is not None and len(s) >= 30:
                out[t] = s
                continue
        need_fetch.append(t)

    if need_fetch:
        try:
            df = yf.download(" ".join(need_fetch), period=period,
                             progress=False, auto_adjust=False, group_by="column",
                             actions=False)
        except Exception as e:
            print(f"[WARN] yf.download failed for {need_fetch}: {type(e).__name__}: {e}")
            df = None

        if df is not None and len(df) > 0:
            for t in need_fetch:
                try:
                    s = _extract_close(df, t)
                except Exception as e:
                    print(f"[WARN] could not extract {t} from batch: {e}")
                    s = None
                if s is None or len(s) < 30:
                    # Fall back to per-ticker fetch (some tickers fail in batch).
                    s = _fetch_single(t, period)
                if s is not None and len(s) >= 30:
                    _write_cache(t, s)
                    out[t] = s
                else:
                    # Last resort: stale cache if present.
                    cache_path = CACHE_DIR / f"{t}.parquet"
                    if cache_path.exists():
                        stale = _load_series_from_cache(cache_path, period)
                        if stale is not None and len(stale) >= 30:
                            print(f"[WARN] {t}: using STALE cache (fetch failed).")
                            out[t] = stale
    return out


def _extract_close(df, ticker):
    """Extract a clean close Series for one ticker from a batch yf dataframe."""
    close = df["Close"]
    if isinstance(close, pd.DataFrame):
        if ticker in close.columns:
            close = close[ticker]
        else:
            close = close.iloc[:, 0]
    close = close.dropna()
    if len(close) == 0:
        return None
    return close.astype(float)


def _fetch_single(ticker, period):
    """Per-ticker fallback when batch download drops a symbol."""
    try:
        df = yf.download(ticker, period=period, progress=False,
                         auto_adjust=False, actions=False)
        if df is None or len(df) == 0:
            return None
        close = df["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        close = close.dropna()
        return close.astype(float) if len(close) > 0 else None
    except Exception as e:
        print(f"[WARN] single fetch {ticker}: {type(e).__name__}: {e}")
        return None


def _cache_fresh(cache_path, max_age_hours=12):
    """True if cache exists and is younger than max_age_hours."""
    if not cache_path.exists():
        return False
    try:
        age = (datetime.now().timestamp() - cache_path.stat().st_mtime) / 3600.0
        return age < max_age_hours
    except Exception:
        return False


def _load_series_from_cache(cache_path, period):
    """Load close Series from a parquet cache file (any period)."""
    try:
        df = pd.read_parquet(cache_path)
        if "ts" not in df.columns and df.index.name == "ts":
            df = df.reset_index()
        if "ts" not in df.columns:
            return None
        df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_localize(None)
        df = df.drop_duplicates(subset=["ts"]).sort_values("ts")
        s = df.set_index("ts")["close"].astype(float)
        s = s[~s.index.duplicated(keep="last")]
        return s
    except Exception:
        return None


def _write_cache(ticker, series):
    """Write a close Series to the Yahoo-style cache schema."""
    cache_path = CACHE_DIR / f"{ticker}.parquet"
    try:
        idx = series.index
        if hasattr(idx, "tz") and idx.tz is not None:
            idx = idx.tz_convert("UTC")
        df = pd.DataFrame({
            "ts": idx,
            "open": np.nan,
            "high": np.nan,
            "low": np.nan,
            "close": series.values.astype(float),
            "volume": np.nan,
            "source": f"yahoo:{ticker}",
        })
        df.to_parquet(cache_path, index=False)
    except Exception as e:
        print(f"[WARN] could not write cache for {ticker}: {e}")


# ============================================================================
# ANALYSIS HELPERS
# ============================================================================

def yf_return(s, days):
    """Trailing N-trading-day return (percent), or None."""
    if s is None or len(s) < 2:
        return None
    n = min(days, len(s) - 1)
    if n <= 0:
        return None
    start = float(s.iloc[-1 - n])
    if start <= 0:
        return None
    return (float(s.iloc[-1]) / start - 1.0) * 100.0


def ytd_return(s):
    """Year-to-date return (percent), or None."""
    if s is None or len(s) < 2:
        return None
    today = s.index[-1]
    year_start = pd.Timestamp(today.year, 1, 1)
    prior = s[s.index <= year_start]
    base = float(prior.iloc[-1]) if len(prior) > 0 else float(s.iloc[0])
    if base <= 0:
        return None
    return (float(s.iloc[-1]) / base - 1.0) * 100.0


def all_returns(s):
    """Return dict of {1W, 1M, 3M, 6M, YTD} percent returns."""
    return {
        "1W": yf_return(s, WINDOWS["1W"]),
        "1M": yf_return(s, WINDOWS["1M"]),
        "3M": yf_return(s, WINDOWS["3M"]),
        "6M": yf_return(s, WINDOWS["6M"]),
        "YTD": ytd_return(s),
    }


def relative_returns(abs_returns, bench_returns):
    """Sector return minus benchmark return, per window."""
    out = {}
    for k in ["1W", "1M", "3M", "6M", "YTD"]:
        a = abs_returns.get(k)
        b = bench_returns.get(k)
        out[k] = (a - b) if (a is not None and b is not None) else None
    return out


def momentum_score(rel_returns):
    """Composite momentum score from relative returns.

    Weighted blend across timeframes. Positive = outperforming SPY.
    """
    parts = []
    for w, weight in MOMENTUM_WEIGHTS.items():
        v = rel_returns.get(w)
        if v is not None:
            parts.append(v * weight)
    return float(sum(parts)) if parts else 0.0


def rsi_wilder(s, window=14):
    """Wilder's RSI on close prices (0-100)."""
    if s is None or len(s) < window + 1:
        return None
    delta = s.diff().dropna()
    if len(delta) < window:
        return None
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    # Wilder smoothing (EMA with alpha = 1/window).
    avg_gain = gain.ewm(alpha=1.0 / window, adjust=False).mean().iloc[-1]
    avg_loss = loss.ewm(alpha=1.0 / window, adjust=False).mean().iloc[-1]
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100.0 - (100.0 / (1.0 + rs)))


def moving_average(s, window):
    """Simple N-day moving average at the latest bar, or None."""
    if s is None or len(s) < window:
        return None
    return float(s.iloc[-window:].mean())


def distance_from_high(s):
    """Percent distance below the 52-week (trailing) high. Negative or 0."""
    if s is None or len(s) < 2:
        return None
    window = min(len(s), 252)
    hi = float(s.iloc[-window:].max())
    last = float(s.iloc[-1])
    if hi <= 0:
        return None
    return (last / hi - 1.0) * 100.0


def trend_classification(s):
    """Classify trend from 50d/200d MA alignment.

    Returns (label, detail) where label is BULL/BEAR/NEUTRAL.
    detail notes golden cross (50>200) or death cross (50<200).
    """
    ma50 = moving_average(s, 50)
    ma200 = moving_average(s, 200)
    last = float(s.iloc[-1]) if s is not None and len(s) > 0 else None
    if ma50 is None or ma200 is None or last is None:
        return "N/A", "insufficient history"
    cross = "golden cross (50d > 200d)" if ma50 > ma200 else "death cross (50d < 200d)"
    if last > ma50 > ma200:
        return "BULL", cross + ", price > 50d > 200d"
    if last < ma50 < ma200:
        return "BEAR", cross + ", price < 50d < 200d"
    return "NEUTRAL", cross + ", mixed alignment"


def signal_from_rank(rank, total):
    """Map rank to Leading/Neutral/Lagging label (terciles)."""
    if rank is None:
        return "N/A"
    third = max(1, total // 3)
    if rank <= third:
        return "Leading"
    if rank > total - third:
        return "Lagging"
    return "Neutral"


def fmt(v, suffix="%", digits=1, na="--"):
    """Format with leading sign (for changes/relative returns)."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return na
    return f"{v:+.{digits}f}{suffix}"


def fmt_plain(v, suffix="%", digits=1, na="--"):
    """Format without leading sign (for absolute levels)."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return na
    return f"{v:.{digits}f}{suffix}"


# ============================================================================
# ROTATION PATTERN DETECTION
# ============================================================================

def avg_rank_of_bucket(ranks_by_ticker, bucket_tickers):
    """Average rank (1=strongest) of the tickers in a bucket.

    Missing tickers are skipped. Returns None if bucket is empty.
    """
    present = [ranks_by_ticker[t] for t in bucket_tickers if t in ranks_by_ticker]
    if not present:
        return None
    return float(np.mean(present))


def detect_rotation_pattern(ranks_by_ticker, rel_3m):
    """Classify the current rotation pattern.

    Compares the average rank (by 3M relative return) of each rotation
    bucket. The bucket with the strongest (lowest) average rank wins, with
    narrative explaining the macro implication.

    Returns dict with: pattern, leading, lagging, narrative, nq_note.
    """
    total = len(ranks_by_ticker)
    bucket_avg = {}
    for name, members in ROTATION_BUCKETS.items():
        bucket_avg[name] = avg_rank_of_bucket(ranks_by_ticker, members)

    # Sort buckets by average rank ascending (strongest first).
    ranked_buckets = sorted(
        [(n, a) for n, a in bucket_avg.items() if a is not None],
        key=lambda x: x[1],
    )

    if not ranked_buckets:
        return {
            "pattern": "UNKNOWN",
            "leading": [], "lagging": [],
            "narrative": "Insufficient data to classify rotation.",
            "nq_note": "NQ bias: indeterminate.",
        }

    winner_name, winner_avg = ranked_buckets[0]
    # The "lagging" bucket is the weakest (highest average rank).
    loser_name, loser_avg = ranked_buckets[-1]

    leading_members = [t for t in ROTATION_BUCKETS[winner_name] if t in ranks_by_ticker]
    lagging_members = [t for t in ROTATION_BUCKETS[loser_name] if t in ranks_by_ticker]

    narratives = {
        "RISK_ON": (
            "Market is betting on GROWTH and RISK. Tech + Discretionary + "
            "Industrials are leading. Capital flowing into high-beta, "
            "cyclical, and growth names. This is a trend-following regime."),
        "DEFENSIVE": (
            "Market is going RISK-OFF. Staples + Utilities + Health Care "
            "are leading. Defensive bid -- institutions de-risking, "
            "concerns about growth or credit. Reduce risk exposure."),
        "INFLATION": (
            "Market is betting on INFLATION / COMMODITY STRENGTH. Energy + "
            "Materials leading. Real-asset hedge bid, commodity bull, "
            "often with rising breakevens. Watch for rate-hike risk."),
        "RATE_SENSITIVE": (
            "RATE-EXPECTATIONS SHIFT. Financials + REITs + Regional Banks "
            "diverging from the broad market. Either pricing steeper curve "
            "(banks help, REITs hurt) or Fed-cut expectations (opposite)."),
        "FLIGHT_TO_SAFETY": (
            "FLIGHT TO SAFETY. Utilities + Staples leading. Classic "
            "risk-off panic bid. Equity drawdown often in progress or "
            "imminent. Defensive positioning strongly advised."),
    }

    nq_notes = {
        "RISK_ON": "NQ tailwind: Tech leadership supports Nasdaq. Trend-following favorable. Do NOT short NQ.",
        "DEFENSIVE": "NQ headwind: defensive bid implies growth/tech weakness. Reduce longs, do not chase.",
        "INFLATION": "NQ mixed-to-headwind: commodity strength often drains tech. Be selective on NQ longs.",
        "RATE_SENSITIVE": "NQ mixed: rate-driven rotation; NQ direction depends on which way rates break.",
        "FLIGHT_TO_SAFETY": "NQ headwind: panic bid for defensives = broad risk selling. Cut NQ size sharply.",
    }

    return {
        "pattern": winner_name,
        "winner_avg_rank": winner_avg,
        "loser_pattern": loser_name,
        "loser_avg_rank": loser_avg,
        "leading": leading_members,
        "lagging": lagging_members,
        "all_bucket_ranks": bucket_avg,
        "narrative": narratives[winner_name],
        "nq_note": nq_notes[winner_name],
    }


def cycle_position(ranks_by_ticker):
    """Map the current leadership to a 4-quadrant business-cycle position."""
    bucket_avg = {}
    for name, members in CYCLE_BUCKETS.items():
        bucket_avg[name] = avg_rank_of_bucket(ranks_by_ticker, members)
    ranked = sorted(
        [(n, a) for n, a in bucket_avg.items() if a is not None],
        key=lambda x: x[1],
    )
    if not ranked:
        return "UNKNOWN", "Insufficient data."
    stage = ranked[0][0]
    notes = {
        "EARLY": ("Early cycle: Tech + Discretionary + Financials leading. "
                  "Growth re-accelerating after a slowdown. Risk-on, "
                  "trend-following favorable."),
        "MID": ("Mid cycle: Industrials + Materials + Energy leading. "
                "Broadening out, capacity tight, commodity strength. "
                "Late-stage risk-on."),
        "LATE": ("Late cycle: Energy + Materials + Staples leading. "
                 "Commodity pressure, margin compression, defensive money "
                 "starting to rotate. Caution increasing."),
        "RECESSION": ("Recession positioning: Staples + Utilities + Health "
                      "Care leading. Defensive bid dominant. Risk-off."),
    }
    return stage, notes.get(stage, "")


def smart_vs_dumb_money(ranks_by_ticker):
    """Compare smart-money sectors vs risk-money sectors.

    Smart money: Financials, Industrials, Materials (institutional favorites).
    Risk money: Tech, Discretionary, Semis (retail/growth favorites).

    Returns dict with both average ranks, the divergence direction, and a
    narrative flagging institutional caution vs retail euphoria.
    """
    smart_ranks = [ranks_by_ticker[t] for t in SMART_MONEY if t in ranks_by_ticker]
    risk_ranks = [ranks_by_ticker[t] for t in RISK_MONEY if t in ranks_by_ticker]
    smart_avg = float(np.mean(smart_ranks)) if smart_ranks else None
    risk_avg = float(np.mean(risk_ranks)) if risk_ranks else None
    if smart_avg is None or risk_avg is None:
        return {"smart_avg": smart_avg, "risk_avg": risk_avg, "divergence": "N/A",
                "narrative": "Insufficient data for smart-vs-risk read."}
    # Lower rank = stronger. If smart is much lower (stronger) than risk,
    # institutions are leading -> caution. If risk is much lower, retail
    # euphoria -> also caution (late-stage).
    delta = risk_avg - smart_avg  # positive = risk stronger (lower rank)
    if delta <= -2.0:
        divergence = "SMART_MONEY_LEADING"
        narrative = ("Smart money (Financials/Industrials/Materials) is "
                     "outperforming risk money (Tech/Discretionary/Semis). "
                     "Institutional caution: institutions rotate to "
                     "cyclical/value when they see growth slowing or risk "
                     "premia too thin. Often a LATE-CYCLE warning.")
    elif delta >= 2.0:
        divergence = "RISK_MONEY_LEADING"
        narrative = ("Risk money (Tech/Discretionary/Semis) is "
                     "outperforming smart money. Retail/growth euphoria: "
                     "often seen in blow-off tops or early-cycle ramps. "
                     "If RISK_ON regime confirmed, trend is strong; if not, "
                     "treat as a caution flag.")
    else:
        divergence = "ALIGNED"
        narrative = ("Smart money and risk money are aligned within ~2 rank "
                     "positions. No divergence signal -- rotation is broad "
                     "and consistent.")
    return {
        "smart_avg": smart_avg, "risk_avg": risk_avg,
        "delta": delta, "divergence": divergence, "narrative": narrative,
    }


# ============================================================================
# NQ / MNQ IMPLICATION (THE KEY OUTPUT)
# ============================================================================

def nq_implication(ranks_by_ticker, rel_returns_by_ticker, rotation, total):
    """Derive the NQ/MNQ trading implication from Tech leadership.

    Tech (XLK) + Semis (SMH) are ~50% of Nasdaq-100 weight, so their
    relative strength directly determines NQ direction.

    Returns dict with: xlk_rank, smh_rank, tech_3m_rel, verdict, sizing_note,
    action_notes.
    """
    xlk_rank = ranks_by_ticker.get("XLK")
    smh_rank = ranks_by_ticker.get("SMH")
    xlk_3m = rel_returns_by_ticker.get("XLK", {}).get("3M")
    smh_3m = rel_returns_by_ticker.get("SMH", {}).get("3M")

    # Tech-leadership score: average rank of XLK and SMH (lower = stronger).
    tech_ranks = [r for r in [xlk_rank, smh_rank] if r is not None]
    tech_avg_rank = float(np.mean(tech_ranks)) if tech_ranks else None

    pattern = rotation.get("pattern", "UNKNOWN")

    # Verdict logic: tech top-third + RISK_ON = strong tailwind.
    third = max(1, total // 3)
    if tech_avg_rank is not None and tech_avg_rank <= third and pattern == "RISK_ON":
        verdict = "STRONG TAILWIND"
        sizing = "Standard or larger MNQ size (per dashboard). Trend-following."
        notes = [
            "Tech (XLK) + Semis (SMH) are in the top third of relative strength.",
            "RISK_ON rotation confirmed by sector leadership.",
            "=> NQ is in a TRENDING environment.",
            "=> Trend danger score should be HIGH: do NOT fight the trend.",
            "=> MNQ sizing: standard or larger; long-bias favored.",
        ]
    elif tech_avg_rank is not None and tech_avg_rank <= third:
        verdict = "TAILWIND"
        sizing = "Standard MNQ size; long-bias favorable with stops."
        notes = [
            "Tech leadership is positive for NQ, but the broader rotation",
            f"({pattern}) is not a clean RISK_ON. Be selective.",
            "=> Longs favored but manage risk; not all boats rising.",
        ]
    elif tech_avg_rank is not None and tech_avg_rank > total - third:
        verdict = "HEADWIND"
        sizing = "Reduce MNQ longs 50%+; counter-trend shorts dangerous too."
        notes = [
            "Tech (XLK/SMH) is in the BOTTOM third of relative strength.",
            "=> NQ is vulnerable; reduce long exposure.",
            "=> Do NOT assume mean-reversion: bottom-ranked tech can fall further.",
            "=> If defensive sectors are also overtaking tech, REGIME CHANGE warning.",
        ]
    else:
        verdict = "MIXED / NEUTRAL"
        sizing = "Reduced MNQ size; trade both directions with discipline."
        notes = [
            "Tech is in the middle of the pack. No strong directional edge.",
            "=> NQ likely range-bound; counter-trend tactics OK with small size.",
        ]

    return {
        "xlk_rank": xlk_rank, "smh_rank": smh_rank,
        "xlk_3m_rel": xlk_3m, "smh_3m_rel": smh_3m,
        "tech_avg_rank": tech_avg_rank, "total": total,
        "verdict": verdict, "sizing_note": sizing,
        "action_notes": notes,
        "rotation_pattern": pattern,
    }


# ============================================================================
# MAIN
# ============================================================================

def generate_briefing():
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")
    print(f"Generating sector rotation tracker for {date_str}...")

    # ---- 1. FETCH ALL DATA ----
    all_tickers = list(SP_SECTORS.keys()) + list(SUB_SECTORS.keys()) + list(BENCHMARKS.keys())
    print(f"Step 1/4: Fetching {len(all_tickers)} tickers (cache-first)...")
    hist = fetch_sector_history(all_tickers, period=FETCH_PERIOD)
    available = sorted(hist.keys())
    print(f"  Available: {len(hist)}/{len(all_tickers)} -> {', '.join(available)}")

    spy = hist.get("SPY")
    qqq = hist.get("QQQ")
    if spy is None:
        print("[ERROR] SPY benchmark unavailable -- cannot compute relative strength.")
    if qqq is None:
        print("[WARN] QQQ benchmark unavailable -- Nasdaq-relative metrics will be missing.")

    spy_returns = all_returns(spy) if spy is not None else {k: None for k in WINDOWS}
    spy_returns["YTD"] = ytd_return(spy) if spy is not None else None
    qqq_returns = all_returns(qqq) if qqq is not None else {k: None for k in WINDOWS}
    qqq_returns["YTD"] = ytd_return(qqq) if qqq is not None else None

    # ---- 2. COMPUTE PER-SECTOR METRICS ----
    print("Step 2/4: Computing relative strength, momentum, trend, RSI...")
    sectors_to_rank = [t for t in (list(SP_SECTORS.keys()) + list(SUB_SECTORS.keys()))
                       if t in hist]
    metrics = {}
    for t in sectors_to_rank:
        s = hist[t]
        abs_r = all_returns(s)
        abs_r["YTD"] = ytd_return(s)
        rel_spy = relative_returns(abs_r, spy_returns)
        rel_qqq = relative_returns(abs_r, qqq_returns)
        mom = momentum_score(rel_spy)
        trend, trend_detail = trend_classification(s)
        rsi = rsi_wilder(s, 14)
        dist_hi = distance_from_high(s)
        ma50 = moving_average(s, 50)
        ma200 = moving_average(s, 200)
        last = float(s.iloc[-1])
        metrics[t] = {
            "ticker": t,
            "name": SP_SECTORS.get(t) or SUB_SECTORS.get(t) or t,
            "is_sp_sector": t in SP_SECTORS,
            "abs": abs_r,
            "rel_spy": rel_spy,
            "rel_qqq": rel_qqq,
            "momentum": mom,
            "trend": trend,
            "trend_detail": trend_detail,
            "rsi": rsi,
            "dist_high": dist_hi,
            "ma50": ma50,
            "ma200": ma200,
            "last": last,
            "last_date": s.index[-1].strftime("%Y-%m-%d"),
        }

    # Rank by 3M relative-to-SPY return (the core relative-strength ranking).
    def rank_key(t):
        r = metrics[t]["rel_spy"].get("3M")
        return r if r is not None else -999.0  # missing -> ranked last
    ranked_tickers = sorted(metrics.keys(), key=rank_key, reverse=True)
    ranks_by_ticker = {t: i + 1 for i, t in enumerate(ranked_tickers)}
    total = len(ranked_tickers)
    for t in metrics:
        metrics[t]["rank"] = ranks_by_ticker[t]
        metrics[t]["signal"] = signal_from_rank(ranks_by_ticker[t], total)

    rel_returns_by_ticker = {t: metrics[t]["rel_spy"] for t in metrics}

    # ---- 3. DETECT ROTATION + NQ IMPLICATION ----
    print("Step 3/4: Detecting rotation pattern and NQ implication...")
    rotation = detect_rotation_pattern(ranks_by_ticker, rel_returns_by_ticker)
    cycle_stage, cycle_note = cycle_position(ranks_by_ticker)
    smart_risk = smart_vs_dumb_money(ranks_by_ticker)
    nq = nq_implication(ranks_by_ticker, rel_returns_by_ticker, rotation, total)

    # ---- 4. BUILD BRIEFING ----
    print("Step 4/4: Building briefing...")
    L = []
    add = L.append

    add(f"# Sector Rotation Tracker - {date_str}\n")
    add("> WHAT THE MARKET IS BETTING ON. Sector leadership reveals the macro")
    add("> consensus BEFORE the charts confirm it. The NQ/MNQ implication")
    add("> section is the key output for this user (Tech = ~50% of Nasdaq).\n")
    add(f"**Date:** {date_str}")
    add(f"**As-of:** {metrics[ranked_tickers[0]]['last_date'] if ranked_tickers else 'N/A'}")
    add(f"**Universe:** {total} sector/sub-sector ETFs ranked vs SPY (3M relative return)")
    add(f"**Current Rotation:** **{rotation['pattern']}**")
    add(f"**Cycle Stage:** **{cycle_stage}**")
    add(f"**NQ/MNQ Verdict:** **{nq['verdict']}**\n")
    add("Rotation patterns: RISK_ON (growth) | DEFENSIVE (risk-off) | "
        "INFLATION (commodity) | RATE_SENSITIVE (curve) | FLIGHT_TO_SAFETY (panic)\n")
    add("---\n")

    # ---- Section 1: Ranking Table (CORE OUTPUT) ----
    add("## 1. Sector Rotation Ranking (vs SPY, 3-month relative return)\n")
    add("Lower rank = stronger relative performance vs SPY. Signal uses terciles:")
    add("top third = Leading, middle = Neutral, bottom third = Lagging.\n")
    add("```")
    add(f"{'Rank':>4}  {'Ticker':<7} {'Sector':<22} "
        f"{'1M':>7} {'3M':>7} {'6M':>7} {'YTD':>7} "
        f"{'Trend':<8} {'RSI':>5} {'Signal':<10}")
    add("-" * 100)
    for t in ranked_tickers:
        m = metrics[t]
        rel = m["rel_spy"]
        tag = "(sub)" if not m["is_sp_sector"] else "     "
        add(f"{m['rank']:>4}  {m['ticker']:<7} {m['name']:<22} "
            f"{fmt(rel.get('1M')):>7} {fmt(rel.get('3M')):>7} "
            f"{fmt(rel.get('6M')):>7} {fmt(rel.get('YTD')):>7} "
            f"{m['trend']:<8} {fmt_plain(m['rsi'], suffix='', digits=0):>5} "
            f"{m['signal']:<10} {tag}")
    add("```")
    add("All return columns are RELATIVE TO SPY (sector return minus SPY return).")
    add("RSI is on the sector's own price; >70 overbought, <30 oversold.\n")
    add("---\n")

    # ---- Section 2: Rotation Pattern Detection ----
    add("## 2. Current Rotation Pattern: " + rotation["pattern"] + "\n")
    add(f"**Pattern:** **{rotation['pattern']}** "
        f"(avg rank of leaders: {rotation.get('winner_avg_rank', float('nan')):.1f}/{total})")
    add(f"**Lagging pattern:** {rotation.get('loser_pattern', 'N/A')} "
        f"(avg rank: {rotation.get('loser_avg_rank', float('nan')):.1f}/{total})\n")
    leading_str = ", ".join(
        f"{t} ({SP_SECTORS.get(t) or SUB_SECTORS.get(t)}, rank {ranks_by_ticker[t]})"
        for t in rotation["leading"]) or "N/A"
    lagging_str = ", ".join(
        f"{t} ({SP_SECTORS.get(t) or SUB_SECTORS.get(t)}, rank {ranks_by_ticker[t]})"
        for t in rotation["lagging"]) or "N/A"
    add(f"**Leading:** {leading_str}")
    add(f"**Lagging:** {lagging_str}\n")
    add(f"**Narrative:** {rotation['narrative']}\n")

    add("### All rotation buckets (avg rank, lower = stronger):\n")
    add("```")
    add(f"  {'Bucket':<18} {'Avg Rank':>9}  {'Members':<40}")
    add("  " + "-" * 70)
    for name in ROTATION_BUCKETS:
        members = ", ".join(ROTATION_BUCKETS[name])
        avg = rotation["all_bucket_ranks"].get(name)
        avg_str = f"{avg:.1f}/{total}" if avg is not None else "N/A"
        marker = " <-- LEADING" if name == rotation["pattern"] else ""
        add(f"  {name:<18} {avg_str:>9}  {members:<40}{marker}")
    add("```\n")
    add("---\n")

    # ---- Section 3: NQ/MNQ Direct Implication ----
    add("## 3. NQ/MNQ Implication (KEY OUTPUT)\n")
    add("Tech (XLK) + Semis (SMH) are ~50% of Nasdaq-100 weight. Their relative")
    add("strength IS the NQ directional signal. Read this before sizing MNQ.\n")
    add(f"- **XLK (Tech) rank:** {nq['xlk_rank']}/{total if nq['xlk_rank'] else 'N/A'}"
        f"  (3M rel to SPY: {fmt(metrics.get('XLK', {}).get('rel_spy', {}).get('3M'))})")
    add(f"- **SMH (Semis) rank:** {nq['smh_rank']}/{total if nq['smh_rank'] else 'N/A'}"
        f"  (3M rel to SPY: {fmt(metrics.get('SMH', {}).get('rel_spy', {}).get('3M'))})")
    if nq["tech_avg_rank"] is not None:
        add(f"- **Tech composite rank (XLK+SMH avg):** {nq['tech_avg_rank']:.1f}/{total}")
    add(f"- **Rotation pattern:** {nq['rotation_pattern']}")
    add(f"- **Verdict:** **{nq['verdict']}**")
    add(f"- **MNQ sizing:** {nq['sizing_note']}\n")
    add("**Action notes:**")
    for note in nq["action_notes"]:
        add(f"  - {note}")
    add("")
    add("**Decision rules:**")
    add("- If Tech top-third AND RISK_ON rotation -> trend-follow longs, larger size.")
    add("- If Tech top-third but rotation not clean RISK_ON -> longs OK, manage risk.")
    add("- If Tech bottom-third -> NQ headwind; reduce longs 50%+.")
    add("- If defensive sectors OVERTAKE Tech in rank -> REGIME CHANGE warning.")
    add("- Combine with the trend danger score (weekly macro briefing) for final bias.\n")
    add("---\n")

    # ---- Section 4: 4-Quadrant Business Cycle Framework ----
    add("## 4. Business-Cycle Position (4-Quadrant Framework)\n")
    add("```")
    add("                    INFLATION RISING")
    add("                          |")
    add("        Energy       |      Materials")
    add("        (XLE)        |      (XLB)")
    add("                     |")
    add(" EARLY CYCLE --------+-------- LATE CYCLE")
    add(" (Tech, Discretion)  |   (Industrials, Energy)")
    add("                     |")
    add("        Staples      |      Utilities")
    add("        (XLP)        |      (XLU)")
    add("                     |")
    add("                    INFLATION FALLING")
    add("```\n")
    add(f"**Current stage:** **{cycle_stage}**\n")
    add(f"{cycle_note}\n")
    add("Cycle buckets by average rank (lower = stronger leadership):\n")
    add("| Stage | Avg Rank | Members |")
    add("|-------|---------:|---------|")
    for stage_name in CYCLE_BUCKETS:
        members = ", ".join(CYCLE_BUCKETS[stage_name])
        avg = avg_rank_of_bucket(ranks_by_ticker, CYCLE_BUCKETS[stage_name])
        avg_str = f"{avg:.1f}/{total}" if avg is not None else "N/A"
        marker = " **<-- NOW**" if stage_name == cycle_stage else ""
        add(f"| {stage_name}{marker} | {avg_str} | {members} |")
    add("\n---\n")

    # ---- Section 5: Historical Context (per sector) ----
    add("## 5. Historical Context (RSI, distance from highs/200d MA)\n")
    add("Momentum extremes and trend location. Use to spot exhaustion or setups.\n")
    add("| Ticker | Sector | RSI | Dist 52w High | vs 50d MA | vs 200d MA | Trend |")
    add("|--------|--------|----:|--------------:|----------:|-----------:|-------|")
    for t in ranked_tickers:
        m = metrics[t]
        last = m["last"]
        vs_50 = ((last / m["ma50"] - 1) * 100) if (m["ma50"] and m["ma50"] > 0) else None
        vs_200 = ((last / m["ma200"] - 1) * 100) if (m["ma200"] and m["ma200"] > 0) else None
        add(f"| {m['ticker']} | {m['name']} | "
            f"{fmt_plain(m['rsi'], suffix='', digits=0)} | "
            f"{fmt(m['dist_high'])} | {fmt(vs_50)} | {fmt(vs_200)} | {m['trend']} |")
    add("\nReads:")
    add("- RSI > 70 = overbought (potential exhaustion), < 30 = oversold (potential bounce).")
    add("- Far below 52w high + below 200d MA = downtrend, do not catch falling knife.")
    add("- At 52w high + above 50d MA = strong uptrend, buy-the-dip candidate.\n")
    add("---\n")

    # ---- Section 6: Smart Money vs Dumb Money Divergence ----
    add("## 6. Smart Money vs Risk Money Divergence\n")
    add("Compares institutional favorites (Financials/Industrials/Materials) against")
    add("retail/growth favorites (Tech/Discretionary/Semis). Divergences flag")
    add("positioning extremes.\n")
    smart_avg = smart_risk.get("smart_avg")
    risk_avg = smart_risk.get("risk_avg")
    add(f"- **Smart money avg rank** (XLF, XLI, XLB): "
        f"{smart_avg:.1f}/{total}" if smart_avg is not None else "- Smart money: N/A")
    add(f"- **Risk money avg rank** (XLK, XLY, SMH): "
        f"{risk_avg:.1f}/{total}" if risk_avg is not None else "- Risk money: N/A")
    if smart_avg is not None and risk_avg is not None:
        delta = smart_risk["delta"]
        add(f"- **Divergence delta** (risk - smart, positive = risk stronger): {delta:+.1f}")
    add(f"- **Classification:** **{smart_risk['divergence']}**\n")
    add(f"**Read:** {smart_risk['narrative']}\n")
    add("---\n")

    # ---- Section 7: Absolute Performance Snapshot ----
    add("## 7. Absolute Performance Snapshot\n")
    add("Sector ETF returns (absolute, NOT relative to SPY). For reference.\n")
    add("| Ticker | Sector | 1W | 1M | 3M | 6M | YTD |")
    add("|--------|--------|---:|---:|---:|---:|----:|")
    for t in ranked_tickers:
        a = metrics[t]["abs"]
        add(f"| {metrics[t]['ticker']} | {metrics[t]['name']} | "
            f"{fmt(a.get('1W'))} | {fmt(a.get('1M'))} | {fmt(a.get('3M'))} | "
            f"{fmt(a.get('6M'))} | {fmt(a.get('YTD'))} |")
    add(f"\n**SPY (benchmark):** 1W {fmt(spy_returns.get('1W'))}, "
        f"1M {fmt(spy_returns.get('1M'))}, 3M {fmt(spy_returns.get('3M'))}, "
        f"6M {fmt(spy_returns.get('6M'))}, YTD {fmt(spy_returns.get('YTD'))}")
    if qqq is not None:
        add(f"**QQQ (Nasdaq):** 1W {fmt(qqq_returns.get('1W'))}, "
            f"1M {fmt(qqq_returns.get('1M'))}, 3M {fmt(qqq_returns.get('3M'))}, "
            f"6M {fmt(qqq_returns.get('6M'))}, YTD {fmt(qqq_returns.get('YTD'))}")
    add("\n---\n")

    # ---- Section 8: NotebookLM Talking Points ----
    add("## 8. NotebookLM Talking Points (Podcast Prompts)\n")
    add("Seed questions for a sector-rotation podcast episode:\n")
    add(f"1. The current rotation pattern is {rotation['pattern']}. What does that "
        f"say about the market's macro view? Which sectors are leading and why?")
    add(f"2. Tech (XLK) is ranked {nq['xlk_rank']}/{total} and Semis (SMH) "
        f"{nq['smh_rank']}/{total}. What does that imply for Nasdaq (NQ/MNQ) "
        f"traders over the next 1-3 weeks? Walk through the trend-danger logic.")
    add(f"3. We are in the **{cycle_stage}** stage of the business cycle. "
        f"What does historical performance look like for each sector at this stage?")
    add("4. Explain the smart-money vs risk-money divergence concept. When smart "
        "money (banks/industrials/materials) outperforms risk money "
        "(tech/discretionary/semis), what is the market telling us?")
    add("5. Walk through the 5 rotation patterns (RISK_ON, DEFENSIVE, INFLATION, "
        "RATE_SENSITIVE, FLIGHT_TO_SAFETY). What triggers each? How should a ")
    add("   Nasdaq futures trader position for each?")
    add("6. Regional banks (KRE) are the canary in the coal mine for credit stress. "
        "Where does KRE rank today vs SPY? What is the historical analog?")
    add("7. Semis (SMH) often lead the entire market. Is SMH currently leading or "
        "lagging? What does SMH weakness historically predict for the S&P 500?\n")
    add("---\n")

    # ---- Section 9: Trading Bias Summary ----
    add("## 9. Trading Bias Summary (for MNQ/NQ trader)\n")
    add("Synthesizes rotation + cycle + tech leadership into one actionable bias.\n")
    rotation_signal = {
        "RISK_ON": "trend-follow long bias",
        "DEFENSIVE": "risk-off; reduce longs",
        "INFLATION": "selective longs only",
        "RATE_SENSITIVE": "wait for curve clarity",
        "FLIGHT_TO_SAFETY": "defensive; cut size",
    }.get(rotation["pattern"], "N/A")
    third = max(1, total // 3)
    tech_rank = nq.get("tech_avg_rank")
    if tech_rank is not None:
        if tech_rank <= third:
            tech_bucket = "TOP"
        elif tech_rank > total - third:
            tech_bucket = "BOTTOM"
        else:
            tech_bucket = "MIDDLE"
        tech_cell = f"{tech_bucket} (rank {tech_rank:.1f}/{total})"
    else:
        tech_cell = "N/A"
    add("| Input | Reading | Signal |")
    add("|-------|---------|--------|")
    add(f"| Rotation pattern | {rotation['pattern']} | {rotation_signal} |")
    add(f"| Cycle stage | {cycle_stage} | see cycle framework above |")
    add(f"| Tech leadership | {tech_cell} | top=tailwind, bottom=headwind |")
    add(f"| Smart vs Risk | {smart_risk['divergence']} | see Section 6 |")
    add(f"| **NQ Verdict** | **{nq['verdict']}** | **{nq['sizing_note']}** |\n")
    add("**Combine with:**")
    add("- Trend danger score (weekly_macro_briefing.py) -> confirms trend-favorable.")
    add("- Credit stress score (credit_monitor.py) -> early-warning if rising.")
    add("- VIX level -> size down above 25, defensive above 30.")
    add("- Never trade this signal in isolation; sector rotation is one input.\n")
    add("---\n")

    # ---- Footer ----
    add("## Data Sources & Methodology\n")
    add("- **yfinance**: 11 S&P sector ETFs (XLK/XLF/XLE/XLV/XLY/XLP/XLI/XLU/XLB/XLRE/XLC),")
    add("  6 sub-sectors (SMH/KRE/XOP/IYT/IHI/XME), benchmarks SPY and QQQ.")
    add(f"- **Cache:** {CACHE_DIR}/{{ticker}}.parquet (12h freshness; stale cache used")
    add("  as a fallback when fetch fails).")
    add("- **Relative strength:** sector 3M return minus SPY 3M return. Rank 1 = strongest.")
    add("- **Momentum score:** weighted relative-return blend "
        "(1W 10% + 1M 25% + 3M 30% + 6M 20% + YTD 15%).")
    add("- **Trend:** 50d/200d MA alignment (BULL = price > 50d > 200d; "
        "BEAR = price < 50d < 200d; else NEUTRAL).")
    add("- **RSI:** Wilder's 14-day RSI on sector's own close.")
    add("- **Rotation buckets:** average rank within named sector groups; "
        "lowest avg rank = current pattern.")
    add("- **NQ implication:** Tech (XLK) + Semis (SMH) leadership + rotation pattern.\n")
    add("**Caveats:**")
    add("- Single-day readings are noisy; look for sustained 1-2 week patterns.")
    add("- Sub-sector ETFs (SMH, KRE, etc.) overlap their parent sector; ranks are")
    add("  not strictly independent.")
    add("- Rotation detection is a heuristic, not a forecasting model. Confirm with")
    add("  the weekly macro regime before acting.")
    add("- YTD uses calendar-year start; for early January this can be noisy.\n")
    add(f"*Generated by sector_rotation.py on {date_str}*")
    add("*This is analysis, not investment advice. Consult a financial advisor.*")

    briefing = "\n".join(L)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = REPORT_DIR / f"rotation_{date_str}.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(briefing)
    print(f"\nBriefing saved to: {output_path}")
    print(f"File size: {output_path.stat().st_size / 1024:.1f} KB")
    print(f"Word count: {len(briefing.split())} words")
    return briefing, output_path


# ============================================================================
# RUN
# ============================================================================

if __name__ == "__main__":
    try:
        briefing, path = generate_briefing()
        print("\n" + "=" * 90)
        print("FULL SECTOR ROTATION TRACKER OUTPUT:")
        print("=" * 90)
        print(briefing)
    except Exception as e:
        # MUST NOT exit non-zero on errors -- print and exit 0.
        import traceback
        print(f"\n[FATAL] {type(e).__name__}: {e}")
        traceback.print_exc()
        print("\nExiting 0 per spec (do not fail the pipeline on data errors).")
    sys.exit(0)
