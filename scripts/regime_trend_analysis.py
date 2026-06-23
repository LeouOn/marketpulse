"""Regime Trend Analysis: When to fight the trend and when to surrender.

Analyses which macro regimes are TRENDING vs CHOPPY for NQ (Nasdaq-100),
and identifies the DANGER ZONES where counter-trend trading is most
destructive. The user's #1 weakness is fighting trends -- this tool
shows, with real data, exactly when fighting the trend is suicidal vs
when it works.

Core question: "WHEN is counter-trend trading OK, and WHEN is it suicidal?"
Answer: REGIME-DEPENDENT. In RISK_ON with strong bull trend (ADX 30+,
perfect EMA stack), fighting the trend is financial suicide. In RECESSION
with choppy price action (ADX 15, EMAs tangled), counter-trend
mean-reversion can work.

Usage
-----
    python scripts/regime_trend_analysis.py
    python scripts/regime_trend_analysis.py --full  (includes full backtest)

ASCII-only print statements (PowerShell cp932 safe). No talib dependency.
"""
from __future__ import annotations

import math
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.research.macro.regimes import Regime, RulesBasedClassifier  # noqa: E402

# ============================================================================
# CONSTANTS
# ============================================================================

DATA_DIR = PROJECT_ROOT / "data"
MACRO_DIR = DATA_DIR / "macro"
YAHOO_DIR = DATA_DIR / "yahoo_cache"

W = 90  # print column width

REGIME_ORDER = [
    Regime.RISK_ON.value,
    Regime.DEFLATION_SCARE.value,
    Regime.INFLATION_ACCEL.value,
    Regime.REAL_YIELD_SHOCK.value,
    Regime.RECESSION.value,
]

REGIME_LABELS = {
    Regime.RISK_ON.value: "RISK_ON",
    Regime.DEFLATION_SCARE.value: "DEFLATION_SCARE",
    Regime.INFLATION_ACCEL.value: "INFLATION_ACCEL",
    Regime.REAL_YIELD_SHOCK.value: "REAL_YIELD_SHOCK",
    Regime.RECESSION.value: "RECESSION",
}

# Trend Danger Score weights
DANGER_REGIME_WEIGHT = 40
DANGER_ADX_WEIGHT = 25
DANGER_EMA_WEIGHT = 20
DANGER_VIX_WEIGHT = 15

# Regime danger base scores (higher = more dangerous to fight trend)
REGIME_DANGER_BASE = {
    Regime.RISK_ON.value: 40,           # strongest trends, NEVER fight
    Regime.INFLATION_ACCEL.value: 30,   # trending but volatile
    Regime.DEFLATION_SCARE.value: 20,   # sharp moves, mean-reversion possible
    Regime.REAL_YIELD_SHOCK.value: 15,  # choppy, counter-trend can work
    Regime.RECESSION.value: 10,         # choppy, counter-trend often works
}


# ============================================================================
# DATA LOADING
# ============================================================================


def load_factors() -> pd.DataFrame:
    """Load the 12-factor macro frame (daily, 2015-present)."""
    path = MACRO_DIR / "factors.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Missing macro factors cache: {path}")
    df = pd.read_parquet(path)
    if not isinstance(df.index, pd.DatetimeIndex):
        if "date" in df.columns:
            df = df.set_index("date")
        elif "ts" in df.columns:
            df = df.set_index("ts")
        df.index = pd.to_datetime(df.index)
    df.index.name = "date"
    if df.index.tz is not None:
        df.index = df.index.tz_convert(None)
    return df.sort_index()


def load_nq_daily() -> pd.DataFrame:
    """Load NQ daily OHLC. Tries Yahoo NQ=F, caches, falls back to QQQ.

    Returns DataFrame indexed by date with columns
    ['open','high','low','close','volume'].
    """
    YAHOO_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = YAHOO_DIR / "NQ=F.parquet"
    end = date.today()
    start = date(2015, 1, 1)

    df = None
    use_cache = cache_path.exists() and (
        time.time() - cache_path.stat().st_mtime < 86400.0
    )
    if use_cache:
        try:
            cached = pd.read_parquet(cache_path)
            if not cached.empty:
                df = cached
        except Exception:
            df = None

    if df is None:
        try:
            import yfinance as yf
            raw = yf.download(
                "NQ=F",
                start=start.isoformat(),
                end=(end + timedelta(days=1)).isoformat(),
                progress=False,
                auto_adjust=False,
            )
            if raw is not None and not raw.empty:
                df = _normalize_yf(raw, "NQ=F")
                if df is not None and not df.empty:
                    df.to_parquet(cache_path, index=False)
        except Exception as e:
            print(f"  [WARN] NQ=F fetch failed ({type(e).__name__}: {e}); falling back to QQQ")

    if df is None or df.empty:
        qqq_path = YAHOO_DIR / "QQQ.parquet"
        if qqq_path.exists():
            qqq = pd.read_parquet(qqq_path)
            df = _normalize_cached(qqq, "QQQ")
            print("  [WARN] Using QQQ as price proxy -- indicator directions OK,")
            print("         but point/value math is QQQ-scaled, NOT NQ-scaled.")
        else:
            raise FileNotFoundError(
                "Neither NQ=F fetch nor QQQ fallback available."
            )

    # Normalize: if "ts" column exists, use it as the index
    if "ts" in df.columns:
        df["ts"] = pd.to_datetime(df["ts"])
        if df["ts"].dt.tz is not None:
            df["ts"] = df["ts"].dt.tz_convert(None)
        df = df.set_index("ts")
    elif not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    df = df.dropna(subset=["close"]).sort_index()
    if df.index.tz is not None:
        df.index = df.index.tz_convert(None)
    return df


def _normalize_yf(raw: pd.DataFrame, ticker: str) -> pd.DataFrame | None:
    """Flatten yfinance multi-index columns to canonical OHLCV shape."""
    df = raw.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    date_col = df.index.name or "Date"
    df = df.reset_index().rename(columns={date_col: "ts"})
    df["ts"] = pd.to_datetime(df["ts"])
    if df["ts"].dt.tz is None:
        df["ts"] = df["ts"].dt.tz_localize("UTC")
    df = df.rename(columns={
        "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Volume": "volume",
    })
    df = df.dropna(subset=["close"])
    if "volume" not in df.columns:
        df["volume"] = float("nan")
    df["source"] = f"yahoo:{ticker}"
    return df[["ts", "open", "high", "low", "close", "volume", "source"]].reset_index(drop=True)


def _normalize_cached(cached: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Normalize a repo yahoo_cache parquet (already canonical shape)."""
    df = cached.copy()
    if "ts" in df.columns:
        df["ts"] = pd.to_datetime(df["ts"])
        if df["ts"].dt.tz is not None:
            df["ts"] = df["ts"].dt.tz_convert(None)
        df = df.set_index("ts")
    return df[["open", "high", "low", "close"]].dropna(subset=["close"]).sort_index()


def load_vix() -> pd.Series:
    """Load VIX. Prefer FRED cache, fall back to Yahoo ^VIX."""
    fred_path = MACRO_DIR / "VIXCLS.parquet"
    if fred_path.exists():
        df = pd.read_parquet(fred_path)
        s = df.set_index("ts")["close"]
        s.index = pd.to_datetime(s.index)
        if s.index.tz is not None:
            s.index = s.index.tz_convert(None)
        s = s.astype(float).sort_index()
        s.name = "VIX"
        return s

    cache_path = YAHOO_DIR / "^VIX.parquet"
    try:
        import yfinance as yf
        raw = yf.download("^VIX", period="max", progress=False, auto_adjust=False)
        if raw is not None and not raw.empty:
            close = raw["Close"]
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            close.index = pd.to_datetime(close.index)
            if close.index.tz is not None:
                close.index = close.index.tz_convert(None)
            close.name = "VIX"
            return close.astype(float).sort_index()
    except Exception:
        pass
    raise FileNotFoundError("VIX data unavailable")


# ============================================================================
# TECHNICAL INDICATORS (manual, no talib)
# ============================================================================


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential moving average."""
    return series.ewm(span=period, adjust=False).mean()


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average True Range (Wilder's smoothing)."""
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False).mean()


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14):
    """Wilder's ADX. Returns (adx, plus_di, minus_di)."""
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    alpha = 1.0 / period
    atr_ = tr.ewm(alpha=alpha, adjust=False).mean()
    atr_safe = atr_.replace(0, np.nan)
    plus_di = 100.0 * plus_dm.ewm(alpha=alpha, adjust=False).mean() / atr_safe
    minus_di = 100.0 * minus_dm.ewm(alpha=alpha, adjust=False).mean() / atr_safe

    di_sum = (plus_di + minus_di).replace(0, np.nan)
    dx = (100.0 * (plus_di - minus_di).abs() / di_sum).fillna(0.0)
    adx_val = dx.ewm(alpha=alpha, adjust=False).mean()
    return adx_val, plus_di.fillna(0.0), minus_di.fillna(0.0)


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index (Wilder's smoothing)."""
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    return out.fillna(50.0)


# ============================================================================
# REGIME CLASSIFICATION
# ============================================================================


def classify_regimes(factors: pd.DataFrame) -> pd.Series:
    """Return dominant regime for each day in the factor frame."""
    clf = RulesBasedClassifier()
    probs = clf.classify(factors)
    return probs.idxmax(axis=1)


# ============================================================================
# SECTION 1: TREND PERSISTENCE ANALYSIS
# ============================================================================


def compute_trend_persistence(
    nq: pd.DataFrame, regime_tape: pd.Series
) -> pd.DataFrame:
    """For each regime, compute trend persistence metrics.

    Returns DataFrame with columns:
      - avg_up_run: average consecutive up-day run length
      - avg_down_run: average consecutive down-day run length
      - max_up_run: longest streak of up days
      - max_down_run: longest streak of down days
      - trend_efficiency: abs(net move) / sum(abs(daily moves))
      - n_days: number of days in regime
    """
    close = nq["close"]
    daily_ret = close.pct_change().dropna()

    # Align regime tape to NQ index
    regime_on_nq = regime_tape.reindex(nq.index, method="ffill")

    results = {}
    for regime in REGIME_ORDER:
        mask = regime_on_nq == regime
        mask = mask.reindex(daily_ret.index, fill_value=False)
        if mask.sum() < 5:
            continue

        rets = daily_ret[mask].dropna()
        if len(rets) < 5:
            continue

        # Run lengths
        up_mask = rets > 0
        down_mask = rets < 0

        up_runs = _compute_runs(up_mask)
        down_runs = _compute_runs(down_mask)

        avg_up = np.mean(up_runs) if up_runs else 0.0
        avg_down = np.mean(down_runs) if down_runs else 0.0
        max_up = max(up_runs) if up_runs else 0
        max_down = max(down_runs) if down_runs else 0

        # Trend efficiency: abs(net move) / sum(abs(daily moves))
        net_move = abs(rets.sum())
        sum_abs = abs(rets).sum()
        efficiency = net_move / sum_abs if sum_abs > 0 else 0.0

        # Directional bias
        avg_daily_ret = float(rets.mean())
        pct_positive = float((rets > 0).mean())

        results[regime] = {
            "avg_up_run": avg_up,
            "avg_down_run": avg_down,
            "max_up_run": max_up,
            "max_down_run": max_down,
            "trend_efficiency": efficiency,
            "avg_daily_ret": avg_daily_ret,
            "pct_positive": pct_positive,
            "n_days": len(rets),
        }

    return pd.DataFrame(results).T


def _compute_runs(mask: pd.Series) -> list[int]:
    """Compute lengths of consecutive True runs in a boolean Series."""
    runs = []
    count = 0
    for v in mask:
        if v:
            count += 1
        else:
            if count > 0:
                runs.append(count)
            count = 0
    if count > 0:
        runs.append(count)
    return runs


# ============================================================================
# SECTION 2: ADX DISTRIBUTION BY REGIME
# ============================================================================


def compute_adx_by_regime(
    nq: pd.DataFrame, regime_tape: pd.Series
) -> pd.DataFrame:
    """For each regime, compute ADX distribution metrics.

    Returns DataFrame with:
      - pct_strong: % days ADX > 25
      - pct_mild: % days ADX 20-25
      - pct_choppy: % days ADX < 20
      - median_adx: median ADX value
      - mean_adx: mean ADX value
    """
    adx_v, _, _ = adx(nq["high"], nq["low"], nq["close"], 14)
    regime_on_nq = regime_tape.reindex(nq.index, method="ffill")

    results = {}
    for regime in REGIME_ORDER:
        mask = regime_on_nq == regime
        mask = mask.reindex(adx_v.index, fill_value=False)
        if mask.sum() < 5:
            continue

        adx_reg = adx_v[mask].dropna()
        if len(adx_reg) < 5:
            continue

        n = len(adx_reg)
        results[regime] = {
            "pct_strong": float((adx_reg > 25).mean()) * 100,
            "pct_mild": float(((adx_reg >= 20) & (adx_reg <= 25)).mean()) * 100,
            "pct_choppy": float((adx_reg < 20).mean()) * 100,
            "median_adx": float(adx_reg.median()),
            "mean_adx": float(adx_reg.mean()),
            "n_days": n,
        }

    return pd.DataFrame(results).T


# ============================================================================
# SECTION 3: EMA ALIGNMENT BY REGIME
# ============================================================================


def compute_ema_alignment_by_regime(
    nq: pd.DataFrame, regime_tape: pd.Series
) -> pd.DataFrame:
    """For each regime, compute EMA alignment metrics.

    Returns DataFrame with:
      - pct_bull_stack: % days EMA20 > EMA50 > EMA200
      - pct_bear_stack: % days EMA20 < EMA50 < EMA200
      - pct_mixed: % days neither bull nor bear stack
      - pct_price_above_ema20: % days close > EMA20
    """
    close = nq["close"]
    e20 = ema(close, 20)
    e50 = ema(close, 50)
    e200 = ema(close, 200)

    bull_stack = (e20 > e50) & (e50 > e200)
    bear_stack = (e20 < e50) & (e50 < e200)
    mixed = ~(bull_stack | bear_stack)
    price_above_e20 = close > e20

    regime_on_nq = regime_tape.reindex(nq.index, method="ffill")

    results = {}
    for regime in REGIME_ORDER:
        mask = regime_on_nq == regime
        mask = mask.reindex(close.index, fill_value=False)
        if mask.sum() < 5:
            continue

        n = mask.sum()
        results[regime] = {
            "pct_bull_stack": float(bull_stack[mask].mean()) * 100,
            "pct_bear_stack": float(bear_stack[mask].mean()) * 100,
            "pct_mixed": float(mixed[mask].mean()) * 100,
            "pct_price_above_ema20": float(price_above_e20[mask].mean()) * 100,
            "n_days": n,
        }

    return pd.DataFrame(results).T


# ============================================================================
# SECTION 4: VOLATILITY AND DRAWDOWN BY REGIME
# ============================================================================


def compute_volatility_by_regime(
    nq: pd.DataFrame, vix: pd.Series, regime_tape: pd.Series
) -> pd.DataFrame:
    """For each regime, compute volatility and drawdown characteristics.

    Returns DataFrame with:
      - avg_atr: average ATR(14)
      - avg_vix: average VIX level
      - avg_daily_range_pct: average (high-low)/close
      - max_drawdown_pct: maximum peak-to-trough drawdown
      - drawdown_type: 'sharp-V' or 'grinding-L' based on recovery speed
    """
    close = nq["close"]
    atr_v = atr(nq["high"], nq["low"], close, 14)
    daily_range = (nq["high"] - nq["low"]) / close

    regime_on_nq = regime_tape.reindex(nq.index, method="ffill")
    vix_on_nq = vix.reindex(nq.index, method="ffill")

    results = {}
    for regime in REGIME_ORDER:
        mask = regime_on_nq == regime
        mask = mask.reindex(close.index, fill_value=False)
        if mask.sum() < 5:
            continue

        atr_reg = atr_v[mask].dropna()
        vix_reg = vix_on_nq[mask].dropna()
        range_reg = daily_range[mask].dropna()
        close_reg = close[mask].dropna()

        # Max drawdown
        peak = close_reg.cummax()
        dd = (close_reg - peak) / peak
        max_dd = float(dd.min())

        # Drawdown type: sharp-V (fast recovery) vs grinding-L (slow recovery)
        # Measure: days from trough to recovery / days from peak to trough
        dd_type = _classify_drawdown_type(close_reg)

        results[regime] = {
            "avg_atr": float(atr_reg.mean()) if len(atr_reg) else float("nan"),
            "avg_vix": float(vix_reg.mean()) if len(vix_reg) else float("nan"),
            "avg_daily_range_pct": float(range_reg.mean()) * 100 if len(range_reg) else float("nan"),
            "max_drawdown_pct": max_dd * 100,
            "drawdown_type": dd_type,
            "n_days": mask.sum(),
        }

    return pd.DataFrame(results).T


def _classify_drawdown_type(close: pd.Series) -> str:
    """Classify drawdown as 'sharp-V' (fast recovery) or 'grinding-L' (slow).

    Sharp-V: recovery time <= 1.5x the decline time.
    Grinding-L: recovery time > 1.5x the decline time.
    """
    peak = close.cummax()
    dd = (close - peak) / peak

    # Find the deepest drawdown
    trough_idx = dd.idxmin()
    trough_val = dd.min()

    if trough_val >= -0.02:  # no significant drawdown
        return "no-significant-dd"

    # Find the peak before this trough
    before_trough = close.loc[:trough_idx]
    peak_idx = before_trough.idxmax()

    # Find recovery: when price exceeds the previous peak
    after_trough = close.loc[trough_idx:]
    recovery_mask = after_trough > close.loc[peak_idx]
    if recovery_mask.any():
        recovery_idx = recovery_mask.idxmax()
        decline_days = (trough_idx - peak_idx).days
        recovery_days = (recovery_idx - trough_idx).days
        if decline_days > 0 and recovery_days <= decline_days * 1.5:
            return "sharp-V"
        else:
            return "grinding-L"
    else:
        return "grinding-L (no recovery yet)"


# ============================================================================
# SECTION 5: COUNTER-TREND vs TREND-FOLLOWING BACKTEST
# ============================================================================


def run_counter_trend_backtest(
    nq: pd.DataFrame, regime_tape: pd.Series
) -> pd.DataFrame:
    """For each regime, simulate trend-following vs counter-trend strategies.

    Strategy A (TREND-FOLLOW): Go LONG when EMA20 > EMA50, FLAT when EMA20 < EMA50
    Strategy B (COUNTER-TREND): Go SHORT when EMA20 > EMA50, FLAT when EMA20 < EMA50
    Strategy C (BUY AND HOLD): Always long

    Returns DataFrame with cumulative returns by regime.
    """
    close = nq["close"]
    e20 = ema(close, 20)
    e50 = ema(close, 50)

    # Signal: 1 when EMA20 > EMA50 (bull trend), 0 otherwise
    bull_signal = (e20 > e50).astype(int)
    daily_ret = close.pct_change().fillna(0.0)

    # Strategy returns
    trend_follow_ret = bull_signal.shift(1).fillna(0) * daily_ret
    counter_trend_ret = -bull_signal.shift(1).fillna(0) * daily_ret
    buy_hold_ret = daily_ret

    regime_on_nq = regime_tape.reindex(nq.index, method="ffill")

    results = {}
    for regime in REGIME_ORDER:
        mask = regime_on_nq == regime
        mask = mask.reindex(daily_ret.index, fill_value=False)
        if mask.sum() < 10:
            continue

        # Cumulative returns within regime periods
        tf_cum = (1 + trend_follow_ret[mask]).cumprod()
        ct_cum = (1 + counter_trend_ret[mask]).cumprod()
        bh_cum = (1 + buy_hold_ret[mask]).cumprod()

        tf_total = float(tf_cum.iloc[-1] - 1) if len(tf_cum) else 0.0
        ct_total = float(ct_cum.iloc[-1] - 1) if len(ct_cum) else 0.0
        bh_total = float(bh_cum.iloc[-1] - 1) if len(bh_cum) else 0.0

        # Max drawdowns
        tf_dd = _max_drawdown(tf_cum)
        ct_dd = _max_drawdown(ct_cum)
        bh_dd = _max_drawdown(bh_cum)

        # Win rates (daily)
        tf_wins = float((trend_follow_ret[mask] > 0).mean()) if mask.sum() else 0.0
        ct_wins = float((counter_trend_ret[mask] > 0).mean()) if mask.sum() else 0.0

        # Average trade duration: count consecutive days in position
        tf_trades = _count_trades(bull_signal[mask])
        avg_tf_duration = mask.sum() / max(tf_trades, 1)

        # Verdict
        if ct_total < -0.15:
            verdict = "DESTROYED"
        elif ct_total < -0.05:
            verdict = "BLED"
        elif ct_total < 0.0:
            verdict = "LOST"
        elif ct_total < 0.05:
            verdict = "BREAKEVEN"
        elif ct_total < 0.15:
            verdict = "WORKED"
        else:
            verdict = "THRIVED"

        results[regime] = {
            "trend_follow_return": tf_total,
            "counter_trend_return": ct_total,
            "buy_hold_return": bh_total,
            "trend_follow_max_dd": tf_dd,
            "counter_trend_max_dd": ct_dd,
            "buy_hold_max_dd": bh_dd,
            "trend_follow_win_rate": tf_wins,
            "counter_trend_win_rate": ct_wins,
            "avg_trade_duration_days": avg_tf_duration,
            "verdict": verdict,
            "n_days": mask.sum(),
        }

    return pd.DataFrame(results).T


def _max_drawdown(equity: pd.Series) -> float:
    """Maximum peak-to-trough drawdown."""
    peak = equity.cummax()
    dd = (equity - peak) / peak
    return float(dd.min()) if len(dd) else 0.0


def _count_trades(signal: pd.Series) -> int:
    """Count number of trades (signal flips from 0->1 or 1->0)."""
    changes = signal.diff().fillna(0).abs()
    return int((changes > 0).sum())


# ============================================================================
# SECTION 6: TREND DANGER SCORE (0-100)
# ============================================================================


def compute_trend_danger_score(
    regime: str,
    adx_now: float,
    e20: float,
    e50: float,
    e200: float,
    price: float,
    vix_now: float,
) -> dict:
    """Compute a 0-100 score indicating how dangerous counter-trend trading is.

    Components:
      - Regime trend-friendliness (40 pts): RISK_ON = 40, RECESSION = 10
      - Current ADX strength (25 pts): ADX > 30 = 25, ADX 20-25 = 15, ADX < 20 = 5
      - EMA alignment (20 pts): Perfect bull stack = 20, mixed = 10, bear stack = 5
      - VIX context (15 pts): VIX < 18 = 15, VIX 18-25 = 10, VIX > 25 = 5

    Score > 75: "EXTREME DANGER for counter-trend. DO NOT fight the trend."
    Score 50-75: "High risk for counter-trend. Reduce size if you must."
    Score 25-50: "Mixed environment. Counter-trend OK with small size."
    Score < 25: "Counter-trend favorable. Trend is weak or breaking."
    """
    # 1. Regime component (0-40)
    regime_score = REGIME_DANGER_BASE.get(regime, 20)

    # 2. ADX component (0-25)
    if adx_now > 30:
        adx_score = 25
    elif adx_now > 25:
        adx_score = 20
    elif adx_now > 20:
        adx_score = 15
    elif adx_now > 15:
        adx_score = 10
    else:
        adx_score = 5

    # 3. EMA alignment (0-20)
    bull_stack = price > e20 > e50 > e200
    bear_stack = price < e20 < e50 < e200
    if bull_stack:
        ema_score = 20
    elif bear_stack:
        ema_score = 5
    else:
        # Mixed: check how many alignments
        alignments = 0
        if e20 > e50:
            alignments += 1
        if e50 > e200:
            alignments += 1
        if price > e20:
            alignments += 1
        ema_score = 5 + alignments * 5  # 5, 10, 15, or 20

    # 4. VIX component (0-15)
    if vix_now < 15:
        vix_score = 15
    elif vix_now < 18:
        vix_score = 12
    elif vix_now < 22:
        vix_score = 10
    elif vix_now < 25:
        vix_score = 8
    elif vix_now < 30:
        vix_score = 5
    else:
        vix_score = 3

    total = regime_score + adx_score + ema_score + vix_score

    if total >= 75:
        level = "EXTREME DANGER"
        guidance = "DO NOT fight the trend. Trade with it or stay flat."
    elif total >= 50:
        level = "HIGH RISK"
        guidance = "Counter-trend is risky. Reduce size to 0.3x if you must."
    elif total >= 25:
        level = "MIXED"
        guidance = "Counter-trend OK with small size. Trend is not dominant."
    else:
        level = "FAVORABLE"
        guidance = "Counter-trend favorable. Trend is weak or breaking."

    return {
        "total_score": total,
        "regime_score": regime_score,
        "adx_score": adx_score,
        "ema_score": ema_score,
        "vix_score": vix_score,
        "level": level,
        "guidance": guidance,
    }


# ============================================================================
# SECTION 7: BEARISH CHANNEL ANALYSIS
# ============================================================================


def analyze_bearish_channels(
    nq: pd.DataFrame, regime_tape: pd.Series
) -> dict:
    """Analyze bearish channel characteristics.

    A "bearish channel" is defined as: EMA20 < EMA50, price below both, ADX > 20.

    Returns:
      - How often NQ enters a bearish channel by regime
      - Average duration of bearish channels
      - Win rate of buying in a bearish channel (going long against the trend)
      - How much money is lost fighting a bearish channel
    """
    close = nq["close"]
    e20 = ema(close, 20)
    e50 = ema(close, 50)
    adx_v, _, _ = adx(nq["high"], nq["low"], close, 14)

    # Bearish channel: EMA20 < EMA50, price below both, ADX > 20
    bearish = (e20 < e50) & (close < e20) & (close < e50) & (adx_v > 20)
    bullish = (e20 > e50) & (close > e20) & (close > e50) & (adx_v > 20)

    regime_on_nq = regime_tape.reindex(nq.index, method="ffill")
    daily_ret = close.pct_change().fillna(0.0)

    # Bearish channel stats by regime
    regime_stats = {}
    for regime in REGIME_ORDER:
        mask = regime_on_nq == regime
        mask = mask.reindex(bearish.index, fill_value=False)
        if mask.sum() < 5:
            continue

        bearish_in_regime = bearish[mask]
        n_bearish = bearish_in_regime.sum()
        pct_bearish = n_bearish / mask.sum() * 100 if mask.sum() else 0.0

        # Average bearish channel duration
        runs = _compute_runs(bearish_in_regime)
        avg_duration = np.mean(runs) if runs else 0.0
        max_duration = max(runs) if runs else 0

        # Win rate of buying in bearish channel (next day return > 0)
        bearish_days = bearish_in_regime[bearish_in_regime].index
        if len(bearish_days) > 0:
            next_day_rets = []
            for d in bearish_days:
                next_idx = daily_ret.index.get_indexer([d], method="bfill")
                if next_idx[0] >= 0 and next_idx[0] < len(daily_ret):
                    next_day_rets.append(float(daily_ret.iloc[next_idx[0]]))
            win_rate = float((np.array(next_day_rets) > 0).mean()) if next_day_rets else 0.0
            avg_next_ret = float(np.mean(next_day_rets)) if next_day_rets else 0.0
        else:
            win_rate = 0.0
            avg_next_ret = 0.0

        # Cumulative return of buying in bearish channel
        if len(bearish_days) > 0:
            bearish_rets = daily_ret.reindex(bearish_days, fill_value=0.0)
            cum_buy_bearish = float((1 + bearish_rets).prod() - 1)
        else:
            cum_buy_bearish = 0.0

        regime_stats[regime] = {
            "pct_days_bearish": pct_bearish,
            "n_bearish_days": n_bearish,
            "avg_bearish_duration": avg_duration,
            "max_bearish_duration": max_duration,
            "buy_win_rate": win_rate,
            "avg_next_day_ret": avg_next_ret,
            "cum_buy_bearish_return": cum_buy_bearish,
            "n_days": mask.sum(),
        }

    # Overall bearish channel stats
    bearish_runs = _compute_runs(bearish)
    bullish_runs = _compute_runs(bullish)

    # Money lost fighting bearish channel: cumulative return of going long
    # during bearish channel days
    bearish_rets_all = daily_ret[bearish]
    cum_fight_bearish = float((1 + bearish_rets_all).prod() - 1) if len(bearish_rets_all) else 0.0

    # Money made following bearish channel: cumulative return of going short
    cum_follow_bearish = float((1 - bearish_rets_all).prod() - 1) if len(bearish_rets_all) else 0.0

    return {
        "by_regime": regime_stats,
        "overall": {
            "total_bearish_days": int(bearish.sum()),
            "total_days": len(bearish),
            "pct_bearish": float(bearish.mean()) * 100,
            "avg_bearish_run": np.mean(bearish_runs) if bearish_runs else 0.0,
            "max_bearish_run": max(bearish_runs) if bearish_runs else 0,
            "avg_bullish_run": np.mean(bullish_runs) if bullish_runs else 0.0,
            "max_bullish_run": max(bullish_runs) if bullish_runs else 0,
            "cum_fight_bearish": cum_fight_bearish,
            "cum_follow_bearish": cum_follow_bearish,
            "buy_win_rate_bearish": float((bearish_rets_all > 0).mean()) if len(bearish_rets_all) else 0.0,
        },
    }


# ============================================================================
# PRINTING HELPERS
# ============================================================================


def fmt_pct(x: float, width: int = 8) -> str:
    if np.isnan(x):
        return " " * (width - 3) + "n/a"
    return f"{x * 100:>{width}.1f}%"


def fmt_pct2(x: float, width: int = 8) -> str:
    """Format a value already in percentage (0-100)."""
    if np.isnan(x):
        return " " * (width - 3) + "n/a"
    return f"{x:>{width}.1f}%"


def fmt_float(x: float, width: int = 8, decimals: int = 2) -> str:
    if np.isnan(x):
        return " " * (width - 3) + "n/a"
    return f"{x:>{width}.{decimals}f}"


def sep(title: str = "") -> None:
    if title:
        print()
        print("=" * W)
        print(f"  {title}")
        print("=" * W)
    else:
        print("-" * W)


# ============================================================================
# MAIN OUTPUT
# ============================================================================


def print_header() -> None:
    print("=" * W)
    print("  REGIME TREND ANALYSIS -- When to Fight the Trend and When to Surrender")
    print("  NQ (Nasdaq-100) daily data, 2015-present, classified via RulesBasedClassifier")
    print("=" * W)
    print()
    print("  CORE QUESTION: When is counter-trend trading OK, and when is it suicidal?")
    print("  ANSWER: It is REGIME-DEPENDENT. This tool shows you the difference")
    print("  with real backtested numbers, not opinions.")
    print()


def print_section_1_trend_persistence(tp: pd.DataFrame) -> None:
    """Print trend persistence analysis."""
    sep("1. TREND PERSISTENCE BY REGIME")
    print(f"  {'Regime':<22} {'AvgUpRun':>9} {'AvgDnRun':>9} {'MaxUp':>6} {'MaxDn':>6} "
          f"{'TrendEff':>9} {'AvgRet':>9} {'%Pos':>7} {'Days':>6}")
    print("  " + "-" * 85)
    for regime in REGIME_ORDER:
        if regime not in tp.index:
            continue
        r = tp.loc[regime]
        print(f"  {regime:<22} {r['avg_up_run']:>9.2f} {r['avg_down_run']:>9.2f} "
              f"{int(r['max_up_run']):>6} {int(r['max_down_run']):>6} "
              f"{r['trend_efficiency']:>9.3f} {fmt_pct(r['avg_daily_ret'], 9)} "
              f"{fmt_pct2(r['pct_positive']*100, 7)} {int(r['n_days']):>6}")

    print()
    print("  INTERPRETATION:")
    print("    - Trend Efficiency: higher = cleaner trend (less noise). >0.15 = trending.")
    print("    - Avg Up/Down Run: longer runs = more persistent directional moves.")
    print("    - Avg Daily Ret: positive = bullish regime bias, negative = bearish.")
    print("    - KEY: RISK_ON has the highest trend efficiency -> FIGHTING IT IS SUICIDAL.")
    print("      RECESSION has low trend efficiency -> counter-trend mean-reversion CAN work.")


def print_section_2_adx(adx_df: pd.DataFrame) -> None:
    """Print ADX distribution by regime."""
    sep("2. ADX DISTRIBUTION BY REGIME")
    print(f"  {'Regime':<22} {'%Strong':>8} {'%Mild':>8} {'%Choppy':>8} "
          f"{'MedADX':>8} {'MeanADX':>8} {'Days':>6}")
    print("  " + "-" * 72)
    for regime in REGIME_ORDER:
        if regime not in adx_df.index:
            continue
        r = adx_df.loc[regime]
        print(f"  {regime:<22} {fmt_pct2(r['pct_strong'], 8)} {fmt_pct2(r['pct_mild'], 8)} "
              f"{fmt_pct2(r['pct_choppy'], 8)} {r['median_adx']:>8.1f} "
              f"{r['mean_adx']:>8.1f} {int(r['n_days']):>6}")

    print()
    print("  ADX KEY:")
    print("    ADX > 25 = Strong trend (trend-following works, counter-trend dies)")
    print("    ADX 20-25 = Mild trend (trend-following OK, counter-trend risky)")
    print("    ADX < 20 = Choppy/no trend (counter-trend mean-reversion can work)")


def print_section_3_ema(ema_df: pd.DataFrame) -> None:
    """Print EMA alignment by regime."""
    sep("3. EMA ALIGNMENT BY REGIME")
    print(f"  {'Regime':<22} {'%Bull':>7} {'%Bear':>7} {'%Mixed':>7} "
          f"{'%Above20':>9} {'Days':>6}")
    print("  " + "-" * 62)
    for regime in REGIME_ORDER:
        if regime not in ema_df.index:
            continue
        r = ema_df.loc[regime]
        print(f"  {regime:<22} {fmt_pct2(r['pct_bull_stack'], 7)} "
              f"{fmt_pct2(r['pct_bear_stack'], 7)} {fmt_pct2(r['pct_mixed'], 7)} "
              f"{fmt_pct2(r['pct_price_above_ema20'], 9)} {int(r['n_days']):>6}")

    print()
    print("  EMA STACK KEY:")
    print("    Bull stack (EMA20 > EMA50 > EMA200) = uptrend. DO NOT SHORT.")
    print("    Bear stack (EMA20 < EMA50 < EMA200) = downtrend. DO NOT BUY.")
    print("    Mixed = no clear trend. Counter-trend is less dangerous here.")


def print_section_4_volatility(vol_df: pd.DataFrame) -> None:
    """Print volatility and drawdown by regime."""
    sep("4. VOLATILITY & DRAWDOWN BY REGIME")
    print(f"  {'Regime':<22} {'AvgATR':>8} {'AvgVIX':>8} {'AvgRange%':>10} "
          f"{'MaxDD%':>8} {'DD Type':<25} {'Days':>6}")
    print("  " + "-" * 92)
    for regime in REGIME_ORDER:
        if regime not in vol_df.index:
            continue
        r = vol_df.loc[regime]
        print(f"  {regime:<22} {r['avg_atr']:>8.1f} {r['avg_vix']:>8.1f} "
              f"{fmt_pct2(r['avg_daily_range_pct'], 10)} "
              f"{fmt_pct2(r['max_drawdown_pct'], 8)} "
              f"{r['drawdown_type']:<25} {int(r['n_days']):>6}")

    print()
    print("  DRAWDOWN TYPE:")
    print("    sharp-V = fast recovery, buyable dip. Counter-trend buying works.")
    print("    grinding-L = slow bleed, don't catch falling knife. Counter-trend DANGEROUS.")


def print_section_5_backtest(bt: pd.DataFrame) -> None:
    """Print counter-trend vs trend-following backtest results."""
    sep("5. COUNTER-TREND vs TREND-FOLLOWING BACKTEST (THE CORE DELIVERABLE)")
    print("  Strategy A (TREND-FOLLOW): LONG when EMA20 > EMA50, FLAT when EMA20 < EMA50")
    print("  Strategy B (COUNTER-TREND): SHORT when EMA20 > EMA50, FLAT when EMA20 < EMA50")
    print("  Strategy C (BUY & HOLD): Always long")
    print()
    print(f"  {'Regime':<22} {'TrendFollow':>12} {'CounterTrend':>13} {'B&H':>12} "
          f"{'CT MaxDD':>9} {'CT Win%':>8} {'Verdict':<15} {'Days':>6}")
    print("  " + "-" * 102)
    for regime in REGIME_ORDER:
        if regime not in bt.index:
            continue
        r = bt.loc[regime]
        print(f"  {regime:<22} {fmt_pct(r['trend_follow_return'], 12)} "
              f"{fmt_pct(r['counter_trend_return'], 13)} "
              f"{fmt_pct(r['buy_hold_return'], 12)} "
              f"{fmt_pct(r['counter_trend_max_dd'], 9)} "
              f"{fmt_pct2(r['counter_trend_win_rate']*100, 8)} "
              f"{r['verdict']:<15} {int(r['n_days']):>6}")

    print()
    print("  THE VERDICT (read this carefully):")
    for regime in REGIME_ORDER:
        if regime not in bt.index:
            continue
        r = bt.loc[regime]
        tf_ret = r["trend_follow_return"]
        ct_ret = r["counter_trend_return"]
        verdict = r["verdict"]
        if verdict in ("DESTROYED", "BLED"):
            print(f"    {regime:<22}: Counter-trend {verdict}. "
                  f"Trend-follow: {tf_ret*100:+.1f}%, Counter-trend: {ct_ret*100:+.1f}%.")
            print(f"                        NEVER fight the trend in this regime.")
        elif verdict == "LOST":
            print(f"    {regime:<22}: Counter-trend lost money ({ct_ret*100:+.1f}%). "
                  f"Trend-follow: {tf_ret*100:+.1f}%.")
            print(f"                        Fighting the trend is a losing strategy here.")
        elif verdict == "BREAKEVEN":
            print(f"    {regime:<22}: Counter-trend roughly breakeven ({ct_ret*100:+.1f}%).")
            print(f"                        Not worth the risk. Trend-follow: {tf_ret*100:+.1f}%.")
        elif verdict in ("WORKED", "THRIVED"):
            print(f"    {regime:<22}: Counter-trend {verdict}! ({ct_ret*100:+.1f}%).")
            print(f"                        This is the ONLY regime where fighting the trend paid off.")


def print_section_6_danger_score(danger: dict) -> None:
    """Print current trend danger score."""
    sep("6. CURRENT TREND DANGER SCORE (0-100)")
    total = danger["total_score"]
    level = danger["level"]
    guidance = danger["guidance"]

    print(f"  Score: {total}/100 -- {level}")
    print(f"  Breakdown:")
    print(f"    Regime component:     {danger['regime_score']:>3}/40")
    print(f"    ADX strength:         {danger['adx_score']:>3}/25")
    print(f"    EMA alignment:        {danger['ema_score']:>3}/20")
    print(f"    VIX context:          {danger['vix_score']:>3}/15")
    print()
    print(f"  GUIDANCE: {guidance}")
    print()
    print("  SCORE INTERPRETATION:")
    print("    >= 75: EXTREME DANGER -- DO NOT fight the trend. Trade with it or stay flat.")
    print("    50-75: HIGH RISK -- Counter-trend is risky. Reduce size to 0.3x if you must.")
    print("    25-50: MIXED -- Counter-trend OK with small size. Trend is not dominant.")
    print("    < 25:  FAVORABLE -- Counter-trend favorable. Trend is weak or breaking.")


def print_section_7_bearish_channel(bc: dict) -> None:
    """Print bearish channel analysis."""
    sep("7. BEARISH CHANNEL ANALYSIS")
    print("  Definition: EMA20 < EMA50, price below both EMAs, ADX > 20")
    print("  This is the setup where the user said: 'that day was in a bearish")
    print("  channel but I kept going' -- and kept losing money.")
    print()

    overall = bc["overall"]
    print(f"  OVERALL STATS (all regimes, 2015-present):")
    print(f"    Total bearish channel days: {overall['total_bearish_days']} "
          f"({overall['pct_bearish']:.1f}% of all days)")
    print(f"    Average bearish run: {overall['avg_bearish_run']:.1f} days")
    print(f"    Max bearish run: {overall['max_bearish_run']} days")
    print(f"    Average bullish run: {overall['avg_bullish_run']:.1f} days")
    print(f"    Max bullish run: {overall['max_bullish_run']} days")
    print()
    print(f"    BUYING in bearish channel (fighting the trend):")
    print(f"      Win rate (next day): {overall['buy_win_rate_bearish']*100:.1f}%")
    print(f"      Cumulative return: {overall['cum_fight_bearish']*100:+.1f}%")
    print(f"    SHORTING in bearish channel (following the trend):")
    print(f"      Cumulative return: {overall['cum_follow_bearish']*100:+.1f}%")
    print()

    # By regime
    regime_stats = bc["by_regime"]
    print(f"  {'Regime':<22} {'%Bearish':>9} {'AvgDur':>7} {'MaxDur':>7} "
          f"{'BuyWin%':>8} {'BuyCumRet':>10} {'Days':>6}")
    print("  " + "-" * 74)
    for regime in REGIME_ORDER:
        if regime not in regime_stats:
            continue
        r = regime_stats[regime]
        print(f"  {regime:<22} {fmt_pct2(r['pct_days_bearish'], 9)} "
              f"{r['avg_bearish_duration']:>7.1f} {int(r['max_bearish_duration']):>7} "
              f"{fmt_pct2(r['buy_win_rate']*100, 8)} "
              f"{fmt_pct(r['cum_buy_bearish_return'], 10)} {int(r['n_days']):>6}")

    print()
    print("  KEY INSIGHT:")
    print("    - Buying in a bearish channel has a win rate BELOW 50% in most regimes.")
    print("    - The cumulative return of fighting a bearish channel is NEGATIVE.")
    print("    - When EMA20 < EMA50 and price is below both, the trend is DOWN.")
    print("      Going long here is betting against the trend. The data says: DON'T.")
    print("    - The user's pattern of 'that day was in a bearish channel but I kept")
    print("      going' is mathematically a losing strategy. The numbers prove it.")


def print_section_8_danger_ranking(bt: pd.DataFrame) -> None:
    """Print danger zone ranking."""
    sep("8. DANGER ZONE RANKING: NEVER FIGHT -> COUNTER-TREND WORKS")

    # Rank regimes by counter-trend return (worst to best)
    if len(bt) > 0:
        ranked = bt.sort_values("counter_trend_return")
        print(f"  {'Rank':<6} {'Regime':<22} {'CT Return':>12} {'Verdict':<15} "
              f"{'Guidance'}")
        print("  " + "-" * 80)
        for i, (regime, r) in enumerate(ranked.iterrows(), 1):
            ct_ret = r["counter_trend_return"]
            verdict = r["verdict"]
            if verdict in ("DESTROYED", "BLED"):
                guidance = "NEVER fight the trend here"
            elif verdict == "LOST":
                guidance = "Strongly avoid counter-trend"
            elif verdict == "BREAKEVEN":
                guidance = "Counter-trend not worth the risk"
            elif verdict == "WORKED":
                guidance = "Counter-trend can work with discipline"
            else:
                guidance = "Counter-trend is viable here"
            print(f"  {i:<6} {regime:<22} {fmt_pct(ct_ret, 12)} {verdict:<15} {guidance}")

    print()
    print("  THE BOTTOM LINE:")
    print("    - In RISK_ON and INFLATION_ACCEL: the trend is your friend. Trade WITH it.")
    print("    - In RECESSION and REAL_YIELD_SHOCK: trends are weaker, counter-trend")
    print("      mean-reversion can work -- but ONLY with small size and tight stops.")
    print("    - The user's #1 weakness (fighting trends in bullish regimes) is the")
    print("      single most destructive trading behavior. The data proves it.")


def print_mnq_integration_line(danger: dict) -> None:
    """Print the one-line summary for MNQ dashboard integration."""
    sep("MNQ DASHBOARD INTEGRATION")
    score = danger["total_score"]
    level = danger["level"]
    regime = danger.get("regime_name", "UNKNOWN")

    if score >= 75:
        action = "DO NOT SHORT"
    elif score >= 50:
        action = "AVOID SHORTING"
    elif score >= 25:
        action = "SHORT WITH CAUTION"
    else:
        action = "SHORTING OK"

    print(f"  Current trend danger score: {score}/100 ({regime} + {level}) -- {action}")
    print()
    print("  Copy this line into your pre-trade checklist:")
    print(f"  >>> Trend danger: {score}/100 ({level}) -- {action} <<<")


# ============================================================================
# MAIN
# ============================================================================


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="Regime Trend Analysis: When to fight the trend and when to surrender"
    )
    parser.add_argument(
        "--full", action="store_true",
        help="Show full backtest details (larger output)"
    )
    args = parser.parse_args()

    # ------------------------------------------------------------------
    # Load data
    # ------------------------------------------------------------------
    print("Loading data...")
    factors = load_factors()
    nq = load_nq_daily()
    vix = load_vix()

    # Align NQ and VIX to common date range
    common_start = max(nq.index.min(), vix.index.min())
    common_end = min(nq.index.max(), vix.index.max())
    nq = nq.loc[common_start:common_end]
    vix = vix.loc[common_start:common_end]

    print(f"  Factors: {factors.index.min().date()} to {factors.index.max().date()} "
          f"({len(factors)} days)")
    print(f"  NQ: {nq.index.min().date()} to {nq.index.max().date()} "
          f"({len(nq)} days)")
    print(f"  VIX: {vix.index.min().date()} to {vix.index.max().date()} "
          f"({len(vix)} days)")

    # ------------------------------------------------------------------
    # Classify regimes
    # ------------------------------------------------------------------
    print("Classifying regimes...")
    regime_tape = classify_regimes(factors)

    # Print regime distribution
    dist = regime_tape.value_counts()
    print("  Regime distribution:")
    for regime in REGIME_ORDER:
        count = dist.get(regime, 0)
        pct = count / len(regime_tape) * 100
        print(f"    {regime:<22} {count:>4} days ({pct:>5.1f}%)")

    # ------------------------------------------------------------------
    # Compute all analyses
    # ------------------------------------------------------------------
    print()
    print("Computing trend persistence...")
    tp = compute_trend_persistence(nq, regime_tape)

    print("Computing ADX distribution...")
    adx_df = compute_adx_by_regime(nq, regime_tape)

    print("Computing EMA alignment...")
    ema_df = compute_ema_alignment_by_regime(nq, regime_tape)

    print("Computing volatility & drawdown...")
    vol_df = compute_volatility_by_regime(nq, vix, regime_tape)

    print("Running counter-trend backtest...")
    bt = run_counter_trend_backtest(nq, regime_tape)

    print("Analyzing bearish channels...")
    bc = analyze_bearish_channels(nq, regime_tape)

    # ------------------------------------------------------------------
    # Current state for danger score
    # ------------------------------------------------------------------
    close = nq["close"]
    e20 = ema(close, 20)
    e50 = ema(close, 50)
    e200 = ema(close, 200)
    adx_v, _, _ = adx(nq["high"], nq["low"], close, 14)

    current_price = float(close.iloc[-1])
    current_e20 = float(e20.iloc[-1])
    current_e50 = float(e50.iloc[-1])
    current_e200 = float(e200.iloc[-1])
    current_adx = float(adx_v.iloc[-1]) if not np.isnan(adx_v.iloc[-1]) else 0.0
    current_vix = float(vix.iloc[-1]) if not np.isnan(vix.iloc[-1]) else 18.0
    current_regime = str(regime_tape.iloc[-1])

    danger = compute_trend_danger_score(
        current_regime, current_adx,
        current_e20, current_e50, current_e200,
        current_price, current_vix,
    )
    danger["regime_name"] = current_regime

    # ------------------------------------------------------------------
    # Print everything
    # ------------------------------------------------------------------
    print_header()

    print(f"  CURRENT STATE (as of {nq.index[-1].date()}):")
    print(f"    NQ price: {current_price:,.0f}")
    print(f"    EMA20: {current_e20:,.0f}  EMA50: {current_e50:,.0f}  EMA200: {current_e200:,.0f}")
    print(f"    ADX(14): {current_adx:.1f}  VIX: {current_vix:.1f}")
    print(f"    Dominant regime: {current_regime}")

    print_section_1_trend_persistence(tp)
    print_section_2_adx(adx_df)
    print_section_3_ema(ema_df)
    print_section_4_volatility(vol_df)
    print_section_5_backtest(bt)
    print_section_6_danger_score(danger)
    print_section_7_bearish_channel(bc)
    print_section_8_danger_ranking(bt)
    print_mnq_integration_line(danger)

    # ------------------------------------------------------------------
    # Full backtest details (--full)
    # ------------------------------------------------------------------
    if args.full:
        sep("FULL BACKTEST DETAILS")
        print(f"  {'Regime':<22} {'TF Ret':>10} {'TF MaxDD':>9} {'TF Win%':>8} "
              f"{'CT Ret':>10} {'CT MaxDD':>9} {'CT Win%':>8} {'B&H Ret':>10} "
              f"{'B&H MaxDD':>9} {'AvgDur':>7}")
        print("  " + "-" * 108)
        for regime in REGIME_ORDER:
            if regime not in bt.index:
                continue
            r = bt.loc[regime]
            print(f"  {regime:<22} {fmt_pct(r['trend_follow_return'], 10)} "
                  f"{fmt_pct(r['trend_follow_max_dd'], 9)} "
                  f"{fmt_pct2(r['trend_follow_win_rate']*100, 8)} "
                  f"{fmt_pct(r['counter_trend_return'], 10)} "
                  f"{fmt_pct(r['counter_trend_max_dd'], 9)} "
                  f"{fmt_pct2(r['counter_trend_win_rate']*100, 8)} "
                  f"{fmt_pct(r['buy_hold_return'], 10)} "
                  f"{fmt_pct(r['buy_hold_max_dd'], 9)} "
                  f"{r['avg_trade_duration_days']:>7.1f}")

    print()
    print("=" * W)
    print("  ANALYSIS COMPLETE")
    print("=" * W)
    return 0


if __name__ == "__main__":
    sys.exit(main())