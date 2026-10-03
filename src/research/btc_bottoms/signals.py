"""Causal bottom-signal library for the BTC bottom study (wave 1).

Owned by g4 under the shared contract
(``btc-bottoms-contract.md``).  This module computes *candidate* bottom
signals from BTC OHLCV and (optionally) the Fear & Greed Index.  Wave 2
tests which of these actually preceded bottoms; wave 1 only guarantees
that every signal is **causal**, honest about missing data, and cheap to
sweep.

Design decisions (the ones a reviewer should challenge)
-------------------------------------------------------
1. **Causality.**  Every value in row ``D`` uses only rows ``<= D``:
   no centered windows, no ``shift(-n)``, no full-sample statistics.
   The prefix-invariance property test (truncating the frame at ``t``
   must reproduce the first ``t`` rows of the full run) is applied to
   *every* column in ``test_btc_bottoms_signals.py``.
2. **Missing data is NaN, never zero.**  A frame without ``fgi_value``
   yields all-NaN sentiment columns; a frame shorter than a warm-up
   yields NaN for that signal.  FGI streaks are computed on the
   FGI-present sub-series and re-indexed, so a gap reads NaN instead of
   silently joining the banks of the gap; ``fgi_mean_30`` requires 30
   non-null observations inside its calendar window (min_periods).
   Compound booleans follow Kleene logic: ``NA & False`` is ``False``
   (a leg that is definitively off settles the compound) while
   ``NA & True`` stays ``NA`` (genuinely unknown).
3. **``close vs SMA(200)`` is the Mayer multiple.**  The candidate list
   names both; they are the same quantity, so the module exposes it
   once as ``mayer_multiple`` (dropped duplicate, per contract).
4. **200-week MA as a 1400-calendar-day rolling mean.**  BTC prints a
   close every calendar day, and 1400 = 7 x 200, so a trailing
   1400-day window covers exactly 200 of each weekday - the daily-mean
   over that window equals the average of 200 weekly closes regardless
   of week phase.  Warm-up is 1400 rows (~3.8 y): the 2015 and 2018
   bottoms predate it on the cached frame; 2022 and 2026 do not.
5. **Running ATH means "since frame start".**  ``dd_ath`` /
   ``days_since_ath`` use the running max of closes in the given frame
   (g1's frame starts 2014-09-17).  Earlier historical peaks (e.g.
   Nov-2013) are invisible to it; that is a property of the data, not a
   bug, and is restated in the study doc in wave 2.
6. **Weekly RSI availability.**  Weekly closes are the last close of
   each Mon-Sun week (``resample("W-SUN").last()``); a week's RSI
   becomes usable on days ``D >= week_end`` (end-of-day-D data is
   allowed by the contract, so Sunday reads its own completed week and
   Monday reads the week that ended yesterday).  The in-progress week
   is never read.
7. **No candle-shape signals.**  Every chosen candidate is a function
   of ``close``, ``volume`` and ``fgi_value`` only, so ``open`` /
   ``high`` / ``low`` are not required inputs and are not read.
8. **Conditions vs turns.**  Deep drawdown, low RSI, extreme fear and
   capitulation volume are *conditions* (still falling).  "Stopped
   making new lows" is a *turn*: ``days_since_low_90`` and the two
   stabilise compounds are turn signals.  Wave 2 tests both families
   separately.
9. **MVRV / Puell are never read** (contract honesty rule 2: the cached
   MVRV series is synthetic).  This module imports nothing from
   ``src.research.data.on_chain``.

Warm-up table (rows of NaN before a value exists)
-------------------------------------------------
===========================  ============  =====================================
signal                       warm-up       cause
===========================  ============  =====================================
dd_ath, days_since_ath       0             running max from row 0
dd_90d                       89            rolling 90-day high
mayer_multiple               199           SMA(200)
close_vs_sma200w             1399          SMA(1400)
rsi_14                       14            Wilder RSI seed
rsi_14w                      ~15 weeks     weekly seed + first completed week
vol_z_90, vol_ratio_90       90            rolling 90-day volume stats
rvol_pct_2y                  760           1 return + 30-day vol + 730-day rank
downstreak                   1             needs a prior close
days_since_low_90            >= 90         first 90-day low must exist
fgi, fgi_extreme_streak      FGI extent    NaN where FGI is absent/gapped
fgi_mean_30                  30 non-null   rolling calendar mean
===========================  ============  =====================================

Reuse: ``rsi_14`` / ``rsi_14w`` call ``src.research.backtest.indicators.compute_rsi``
(Wilder formulation).  ``mayer_multiple`` matches the inline formula in
``IndicatorProvider.compute`` (close / SMA(200)); that helper is not
factored out there, so the two-line formula is restated here rather
than importing the network-touching provider class.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from src.research.backtest.indicators import compute_rsi

__all__ = ["SIGNAL_REGISTRY", "DEFAULT_PARAMS", "FIRE_DIRECTIONS", "compute_signals", "fire"]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
# SIGNAL_REGISTRY maps a signal name to a 3-tuple
# ``(kind, default_threshold, grid)`` per the shared contract:
#
#   kind              "continuous" (a value column, plus a boolean
#                     ``<name>_fire`` column at ``default_threshold``)
#                     or "boolean" (a pure compound, no value column).
#   default_threshold the threshold the shipped ``_fire`` column uses,
#                     or None for multi-parameter compounds (whose
#                     defaults then live in DEFAULT_PARAMS only).
#   grid              the neighbourhood sweep for wave 2:
#                     param name -> candidate values.  Single-threshold
#                     signals use the key "threshold".
#
# Fire direction (which side of the threshold means "on") is documented
# per signal below and encoded in FIRE_DIRECTIONS: "le" fires when the
# value is <= threshold (oversold / compressed / cheap), "ge" fires on
# >= (depth, streaks, spikes).  Threshold sweeps must re-call
# compute_signals with params; the _fire column alone is not parametric
# after the fact.

SIGNAL_REGISTRY: dict[str, tuple[str, float | None, dict[str, list[float]]]] = {
    # -- price depth (conditions) -------------------------------------
    "dd_ath": (
        "continuous",
        -0.50,
        {"threshold": [-0.35, -0.40, -0.45, -0.50, -0.55, -0.60, -0.65]},
    ),
    "days_since_ath": (
        "continuous",
        365,
        {"threshold": [90, 180, 270, 365, 540, 730]},
    ),
    "dd_90d": (
        "continuous",
        -0.25,
        {"threshold": [-0.15, -0.20, -0.25, -0.30, -0.35, -0.40]},
    ),
    # -- valuation versus moving averages (conditions) ------------------
    "mayer_multiple": (
        "continuous",
        0.80,
        {"threshold": [0.6, 0.7, 0.8, 0.9, 1.0, 1.1]},
    ),
    "close_vs_sma200w": (
        "continuous",
        1.00,
        {"threshold": [0.8, 0.9, 1.0, 1.1, 1.2, 1.4]},
    ),
    # -- momentum / oscillators (conditions) ----------------------------
    "rsi_14": (
        "continuous",
        30,
        {"threshold": [20, 25, 30, 35, 40]},
    ),
    "rsi_14w": (
        "continuous",
        40,
        {"threshold": [30, 35, 40, 45, 50]},
    ),
    # -- volume behaviour (conditions) ----------------------------------
    "vol_z_90": (
        "continuous",
        2.0,
        {"threshold": [1.5, 2.0, 2.5, 3.0]},
    ),
    "vol_ratio_90": (
        "continuous",
        0.60,
        {"threshold": [0.4, 0.5, 0.6, 0.7, 0.8]},
    ),
    "capitulation_vol": (
        "boolean",
        None,
        {"vol_z": [1.5, 2.0, 2.5, 3.0], "ret": [-0.03, -0.05, -0.08]},
    ),
    "vol_exhaustion": (
        "boolean",
        None,
        {"vol_ratio": [0.4, 0.5, 0.6, 0.7, 0.8], "ret30_max": [-0.10, -0.05, 0.0]},
    ),
    # -- realised volatility (condition) --------------------------------
    "rvol_pct_2y": (
        "continuous",
        0.40,
        {"threshold": [0.2, 0.3, 0.4, 0.5]},
    ),
    "rvol_compress_after_spike": (
        "boolean",
        None,
        {"compress": [0.3, 0.4, 0.5], "spike": [0.8, 0.9, 0.95], "lookback": [60, 90, 180]},
    ),
    # -- downside persistence (condition) -------------------------------
    "downstreak": (
        "continuous",
        4,
        {"threshold": [3, 4, 5, 6, 8]},
    ),
    # -- turns: stopped making new lows ---------------------------------
    "days_since_low_90": (
        "continuous",
        21,
        {"threshold": [7, 14, 21, 30, 45]},
    ),
    # -- Fear & Greed (conditions + one turn compound) -------------------
    "fgi": (
        "continuous",
        25,
        {"threshold": [10, 15, 20, 25, 30]},
    ),
    "fgi_extreme_streak": (
        "continuous",
        3,
        {"fgi_thresh": [15, 20, 25], "threshold": [2, 3, 5, 7]},
    ),
    "fgi_mean_30": (
        "continuous",
        25,
        {"threshold": [15, 20, 25, 30, 35]},
    ),
    "washout_stabilise": (
        "boolean",
        None,
        {"fgi_thresh": [10, 15, 20], "washout_lookback": [5, 10, 20], "stabilise_days": [5, 10, 20, 30]},
    ),
}

# Which side of the threshold fires, for every continuous signal.
FIRE_DIRECTIONS: dict[str, str] = {
    "dd_ath": "le",  # deeper drawdown than -0.50
    "days_since_ath": "ge",  # ATH is stale
    "dd_90d": "le",
    "mayer_multiple": "le",  # cheap vs SMA200
    "close_vs_sma200w": "le",  # at/below the 200-week MA
    "rsi_14": "le",  # oversold
    "rsi_14w": "le",
    "vol_z_90": "ge",  # volume spike
    "vol_ratio_90": "le",  # volume dried up
    "rvol_pct_2y": "le",  # compressed vs own 2y history
    "downstreak": "ge",  # long losing streak
    "days_since_low_90": "ge",  # no new low for a while (turn)
    "fgi": "le",  # extreme fear
    "fgi_extreme_streak": "ge",  # fear has persisted
    "fgi_mean_30": "le",
}

# Computation defaults.  Keys mirror the grid parameter names; wave 2
# overrides any of these via compute_signals(df, params={name: {...}}).
DEFAULT_PARAMS: dict[str, dict[str, float]] = {
    "fgi_extreme_streak": {"fgi_thresh": 25},
    "capitulation_vol": {"vol_z": 2.0, "ret": -0.05},
    "vol_exhaustion": {"vol_ratio": 0.6, "ret30_max": 0.0},
    "rvol_compress_after_spike": {"compress": 0.4, "spike": 0.9, "lookback": 90},
    "washout_stabilise": {"fgi_thresh": 15, "washout_lookback": 10, "stabilise_days": 10},
}

# Fixed structural windows (documented, not swept in wave 1).
_HIGH_LOOKBACK = 90  # trailing high for dd_90d and new-low detection
_SMA_DAILY = 200  # Mayer window
_SMA_WEEKLY_DAYS = 1400  # 7 * 200 (see docstring decision 4)
_VOL_WINDOW = 90  # volume mean/std window
_RV_WINDOW = 30  # realised-vol window (daily log returns)
_RV_RANK_WINDOW = 730  # trailing window for the vol percentile
_FGI_MEAN_WINDOW = 30  # calendar days for the FGI mean


def _merge_params(name: str, params: dict[str, Any] | None) -> dict[str, float]:
    """Return the effective parameter dict for ``name``.

    Precedence: caller ``params`` > ``DEFAULT_PARAMS`` > registry
    ``default_threshold`` (as ``threshold``).  Unknown keys are a
    ``ValueError`` - a mistyped sweep parameter must fail loudly, not
    silently no-op.
    """
    eff = dict(DEFAULT_PARAMS.get(name, {}))
    thr = SIGNAL_REGISTRY[name][1]
    if thr is not None:
        eff.setdefault("threshold", thr)
    if params:
        unknown = set(params) - set(eff)
        if unknown:
            raise ValueError(
                f"unknown params for signal {name!r}: {sorted(unknown)}; "
                f"known: {sorted(eff)} (see SIGNAL_REGISTRY grid)"
            )
        eff.update({k: float(v) for k, v in params.items()})
    return eff


def _fire_column(values: pd.Series, threshold: float, direction: str) -> pd.Series:
    """Nullable-boolean threshold test with NaN propagation.

    A plain ``values <= t`` would turn NaN into ``False`` ("signal
    confidently off") - exactly the dishonesty rule 2 forbids - so the
    comparison is done in pandas nullable dtypes, where NaN compares to
    ``<NA>``.
    """
    if direction == "le":
        fired = values.astype("Float64") <= threshold
    elif direction == "ge":
        fired = values.astype("Float64") >= threshold
    else:  # pragma: no cover - guarded by registry consistency test
        raise ValueError(f"unknown fire direction {direction!r}")
    return fired.astype("boolean")


def _and(*conditions: pd.Series) -> pd.Series:
    """Nullable-boolean AND: NaN input -> NA, never False-by-accident."""
    out = conditions[0].astype("boolean")
    for cond in conditions[1:]:
        out = out & cond.astype("boolean")
    return out


# ---------------------------------------------------------------------------
# Signal computations (each returns float64/boolean series on df.index)
# ---------------------------------------------------------------------------


def _dd_ath(close: pd.Series) -> pd.Series:
    """Drawdown from the running ATH (``close / cummax(close) - 1``)."""
    ath = close.cummax()
    return close / ath - 1.0


def _days_since_ath(close: pd.Series, index: pd.Series) -> pd.Series:
    """Days since the last new ATH print.

    A close that exactly re-ties the ATH does not reset the counter
    (only a strictly higher close does); row 0 counts as a print.
    """
    ath = close.cummax()
    prev_ath = ath.shift(1)
    new_ath = (close >= ath) & (prev_ath.isna() | close.gt(prev_ath))
    last_ath_date = index.where(new_ath).ffill()
    return (index - last_ath_date).dt.days.astype("float64")


def _dd_trailing(close: pd.Series, window: int) -> pd.Series:
    high = close.rolling(window, min_periods=window).max()
    return close / high - 1.0


def _mayer(close: pd.Series) -> pd.Series:
    sma = close.rolling(_SMA_DAILY, min_periods=_SMA_DAILY).mean()
    return close / sma


def _sma_ratio(close: pd.Series, window: int) -> pd.Series:
    sma = close.rolling(window, min_periods=window).mean()
    return close / sma


def _weekly_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Weekly RSI(14), mapped to daily rows (docstring decision 6).

    Weekly closes are the last close of each Mon-Sun week.  A weekly
    value with week-end label ``S`` is visible on daily rows ``D >= S``
    (end-of-day data allowed), so the daily mapping is a forward-fill
    reindex over labels ``<= D``.  The in-progress week is never read.
    """
    weekly_close = close.resample("W-SUN").last()
    weekly = compute_rsi(weekly_close, period)
    return weekly.reindex(close.index, method="ffill")


def _vol_z(volume: pd.Series) -> pd.Series:
    mean = volume.rolling(_VOL_WINDOW, min_periods=_VOL_WINDOW).mean()
    std = volume.rolling(_VOL_WINDOW, min_periods=_VOL_WINDOW).std()
    return (volume - mean) / std


def _vol_ratio(volume: pd.Series) -> pd.Series:
    mean = volume.rolling(_VOL_WINDOW, min_periods=_VOL_WINDOW).mean()
    return volume / mean


def _rvol_pct(close: pd.Series) -> pd.Series:
    """Percentile of 30-day realised vol within its trailing 2 years.

    ``pct`` = fraction of the trailing 730 daily values that are <= the
    current value (1.0 = highest vol in 2 years).  Causal by
    construction; O(n * window) via a rolling apply, ~3M comparisons on
    the 4.4k-row cached frame.
    """
    # row 0 -> NaN by design; errstate keeps the row-0 log quiet
    with np.errstate(invalid="ignore", divide="ignore"):
        logret = np.log(close / close.shift(1))
        rv = logret.rolling(_RV_WINDOW, min_periods=_RV_WINDOW).std()
    return rv.rolling(_RV_RANK_WINDOW, min_periods=_RV_RANK_WINDOW).apply(
        lambda a: float((a <= a[-1]).mean()), raw=True
    )


def _downstreak(close: pd.Series) -> pd.Series:
    """Consecutive down days; NaN until the first valid return."""
    ret = close.pct_change()
    streak = np.full(len(close), np.nan)
    values = ret.to_numpy()
    running = 0
    seen_valid = False
    for i, r in enumerate(values):
        if np.isnan(r):
            running = 0
            continue
        seen_valid = True
        running = running + 1 if r < 0 else 0
        streak[i] = running
    if not seen_valid:  # pragma: no cover - single-row frame
        pass
    return pd.Series(streak, index=close.index, dtype="float64")


def _days_since_low(close: pd.Series, index: pd.Series, window: int) -> pd.Series:
    """Days since the close last broke below its trailing ``window``-day min.

    A "new low" is a close strictly below the min of the *previous*
    ``window`` closes (today excluded), so flat stretches do not tie
    their way into new lows.  Warm-up: NaN until a full ``window`` has
    filled AND the first new low has occurred.
    """
    low_prev = close.shift(1).rolling(window, min_periods=window).min()
    new_low = close.lt(low_prev)
    last_low_date = index.where(new_low).ffill()
    return (index - last_low_date).dt.days.astype("float64")


def _fgi_series(df: pd.DataFrame) -> pd.Series | None:
    if "fgi_value" not in df.columns:
        return None
    return df["fgi_value"].astype("float64")


def _fgi_extreme_streak(fgi: pd.Series, fgi_thresh: float) -> pd.Series:
    """Consecutive FGI days <= ``fgi_thresh``, NaN across gaps.

    Computed on the FGI-present sub-series then re-indexed, so a row
    whose own FGI is missing reads NaN rather than borrowing a streak
    from the other side of the gap (docstring decision 2).
    """
    present = fgi.dropna()
    extreme = present <= fgi_thresh
    streak = extreme.groupby((~extreme).cumsum()).cumsum().astype("float64")
    return streak.reindex(fgi.index)


def _fgi_mean(fgi: pd.Series) -> pd.Series:
    """30-calendar-day FGI mean; needs 30 non-null values in-window."""
    return fgi.rolling(_FGI_MEAN_WINDOW, min_periods=_FGI_MEAN_WINDOW).mean()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def compute_signals(df: pd.DataFrame, params: dict[str, Any] | None = None) -> pd.DataFrame:
    """Compute every registered bottom signal for a daily BTC frame.

    Parameters
    ----------
    df : pd.DataFrame
        Frame per the shared contract: one row per UTC calendar day,
        sorted unique tz-naive ``DatetimeIndex`` named ``ts``; column
        ``close`` is required (``KeyError`` otherwise); ``volume`` is
        optional (absent -> all-NaN volume signals); ``fgi_value`` (0-100)
        optional.  ``open`` / ``high`` / ``low`` are accepted but
        unread (docstring decision 7).
    params : dict[str, dict[str, float]] | None
        Per-signal parameter overrides, e.g.
        ``{"rsi_14": {"threshold": 25},
           "washout_stabilise": {"stabilise_days": 20}}``.  Unknown
        signal names or unknown parameter keys raise ``ValueError``.

    Returns
    -------
    pd.DataFrame
        Same index as ``df``.  One column per continuous signal (the
        value) plus a nullable-boolean ``<name>_fire`` column at the
        effective threshold; one column per boolean compound.  Missing
        inputs and warm-up rows are NaN/NA, never zero/False.
    """
    params = params or {}
    unknown_signals = set(params) - set(SIGNAL_REGISTRY)
    if unknown_signals:
        raise ValueError(f"unknown signals in params: {sorted(unknown_signals)}")

    df = df.sort_index()
    close = df["close"].astype("float64")
    index = df.index.to_series()
    out = pd.DataFrame(index=df.index)

    # -- depth / valuation ----------------------------------------------
    out["dd_ath"] = _dd_ath(close)
    out["days_since_ath"] = _days_since_ath(close, index)
    out["dd_90d"] = _dd_trailing(close, _HIGH_LOOKBACK)
    out["mayer_multiple"] = _mayer(close)
    out["close_vs_sma200w"] = _sma_ratio(close, _SMA_WEEKLY_DAYS)

    # -- oscillators ------------------------------------------------------
    out["rsi_14"] = compute_rsi(close, 14)
    out["rsi_14w"] = _weekly_rsi(close, 14)

    # -- volume (optional column: absent -> all-NaN volume signals) -----
    ret_1d = close.pct_change()
    ret_30d = close.pct_change(30)
    if "volume" in df.columns:
        volume = df["volume"].astype("float64")
    else:
        volume = pd.Series(np.nan, index=df.index)
    vol_z = _vol_z(volume)
    vol_ratio = _vol_ratio(volume)
    out["vol_z_90"] = vol_z
    out["vol_ratio_90"] = vol_ratio
    cap = _merge_params("capitulation_vol", params.get("capitulation_vol"))
    out["capitulation_vol"] = _and(
        vol_z.ge(cap["vol_z"]).astype("boolean").where(vol_z.notna()),
        ret_1d.le(cap["ret"]).astype("boolean").where(ret_1d.notna()),
    )
    exh = _merge_params("vol_exhaustion", params.get("vol_exhaustion"))
    out["vol_exhaustion"] = _and(
        vol_ratio.le(exh["vol_ratio"]).astype("boolean").where(vol_ratio.notna()),
        ret_30d.le(exh["ret30_max"]).astype("boolean").where(ret_30d.notna()),
    )

    # -- realised volatility ------------------------------------------------
    rvol = _rvol_pct(close)
    out["rvol_pct_2y"] = rvol
    rcs = _merge_params("rvol_compress_after_spike", params.get("rvol_compress_after_spike"))
    spike_max = rvol.rolling(int(rcs["lookback"]), min_periods=int(rcs["lookback"])).max()
    spiked_recent = spike_max.ge(rcs["spike"]).astype("boolean").where(spike_max.notna())
    out["rvol_compress_after_spike"] = _and(
        rvol.le(rcs["compress"]).astype("boolean").where(rvol.notna()),
        spiked_recent,
    )

    # -- persistence / turns --------------------------------------------------
    out["downstreak"] = _downstreak(close)
    dsl = _days_since_low(close, index, _HIGH_LOOKBACK)
    out["days_since_low_90"] = dsl

    # -- Fear & Greed -----------------------------------------------------
    fgi = _fgi_series(df)
    if fgi is None:
        for col in ("fgi", "fgi_extreme_streak", "fgi_mean_30", "washout_stabilise"):
            out[col] = pd.Series(np.nan, index=df.index, dtype="float64")
            if col == "washout_stabilise":
                out[col] = out[col].astype("boolean")
    else:
        out["fgi"] = fgi
        fes = _merge_params("fgi_extreme_streak", params.get("fgi_extreme_streak"))
        out["fgi_extreme_streak"] = _fgi_extreme_streak(fgi, fes["fgi_thresh"])
        out["fgi_mean_30"] = _fgi_mean(fgi)
        ws = _merge_params("washout_stabilise", params.get("washout_stabilise"))
        # extreme must carry NaN through the rolling max (a gap is
        # "unknown", not "no fear"): le() alone would flatten NaN to False
        # and min_periods would then count gap days as evidence.
        extreme = pd.Series(
            np.where(fgi.notna(), (fgi <= ws["fgi_thresh"]).to_numpy(), np.nan),
            index=fgi.index,
            dtype="float64",
        )
        extreme_max = extreme.rolling(int(ws["washout_lookback"]), min_periods=int(ws["washout_lookback"])).max()
        washout_recent = extreme_max.ge(1).astype("boolean").where(extreme_max.notna())
        out["washout_stabilise"] = _and(
            washout_recent,
            dsl.ge(ws["stabilise_days"]).astype("boolean").where(dsl.notna()),
        )

    # -- fire columns at the effective thresholds ---------------------------
    for name, (kind, _default, _grid) in SIGNAL_REGISTRY.items():
        if kind != "continuous":
            continue
        eff = _merge_params(name, params.get(name))
        out[f"{name}_fire"] = _fire_column(out[name], eff["threshold"], FIRE_DIRECTIONS[name])

    return out


def fire(signals: pd.DataFrame, name: str, threshold: float | None = None) -> pd.Series:
    """Re-threshold a continuous signal column without recomputing.

    Convenience for wave-2 sweeps that only move a threshold: reads the
    value column ``name`` from ``signals`` (the output of
    ``compute_signals``) and applies the registry fire direction.  For
    anything richer than a single threshold, re-call
    ``compute_signals`` with ``params``.
    """
    if name not in FIRE_DIRECTIONS:
        raise ValueError(f"{name!r} is not a continuous signal with a fire direction")
    eff = _merge_params(name, None)
    thr = eff["threshold"] if threshold is None else threshold
    return _fire_column(signals[name], thr, FIRE_DIRECTIONS[name])
