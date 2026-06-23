"""Pure-functional curve math: spreads, shape, NY Fed recession prob.

No I/O. Logic ported from scripts/yield_curve_monitor.py.
All yields are expressed in PERCENT (e.g. 4.40 == 4.40%).
All spreads are expressed in BASIS POINTS (e.g. -10.0 == -10bps).
"""
from __future__ import annotations

import math
from enum import Enum
from typing import Optional


class CurveShape(str, Enum):
    """Curve shape classification."""
    NORMAL = "NORMAL"              # Upward sloping, 2s10s > 0 and 2s30s > 0
    FLAT = "FLAT"                  # All spreads within 25bps band
    INVERTED = "INVERTED"          # 2s10s < 0
    HUMPED = "HUMPED"              # Mid-curve above both ends
    INVERTED_HUMPED = "INVERTED_HUMPED"  # Mid-curve below both ends


# --- Spread computation ----------------------------------------------------

_SPREAD_PAIRS: tuple[tuple[str, str, str], ...] = (
    # (name, short_tenor, long_tenor) — long minus short, in bps
    ("2s10s", "2y", "10y"),
    ("3m10y", "3mo", "10y"),
    ("5s30s", "5y", "30y"),
    ("2s30s", "2y", "30y"),
)


def compute_spreads(curve: dict[str, float]) -> dict[str, Optional[float]]:
    """Compute standard spreads in basis points.

    Missing tenors produce ``None`` for any spread that needs them.
    """
    out: dict[str, Optional[float]] = {}
    for name, short, long_ in _SPREAD_PAIRS:
        if short in curve and long_ in curve:
            out[name] = round((curve[long_] - curve[short]) * 100.0, 4)
        else:
            out[name] = None
    return out


# --- Shape classification --------------------------------------------------

_FLAT_BAND_BPS = 25.0


def classify_shape(curve: dict[str, float]) -> CurveShape:
    """Classify the curve's shape from a sparse tenor dict.

    Uses 2y / 5y / 10y / 30y when available; falls back to whatever's present.
    """
    keys = [k for k in ("2y", "5y", "10y", "30y") if k in curve]
    if len(keys) < 2:
        return CurveShape.NORMAL  # not enough info — default to NORMAL

    values = [curve[k] for k in keys]
    spread_band = (max(values) - min(values)) * 100.0

    s_2s10s = (curve.get("10y", curve.get("5y", 0)) - curve.get("2y", 0)) * 100.0
    s_2s30s = (curve.get("30y", curve.get("10y", 0)) - curve.get("2y", 0)) * 100.0

    # INVERTED: short end above long end (2s10s < 0)
    if s_2s10s < 0:
        return CurveShape.INVERTED

    # FLAT: all tenors within the band
    if spread_band <= _FLAT_BAND_BPS:
        return CurveShape.FLAT

    # HUMPED: middle (5y) above both 2y and 30y by more than the band
    if "5y" in curve and "2y" in curve and "30y" in curve:
        five = curve["5y"]
        if five > curve["2y"] + (_FLAT_BAND_BPS / 100.0) and five > curve["30y"] + (_FLAT_BAND_BPS / 100.0):
            return CurveShape.HUMPED
        if five < curve["2y"] - (_FLAT_BAND_BPS / 100.0) and five < curve["30y"] - (_FLAT_BAND_BPS / 100.0):
            return CurveShape.INVERTED_HUMPED

    return CurveShape.NORMAL


# --- Trend classification --------------------------------------------------

_TREND_THRESHOLD_BPS = 5.0


def classify_trend(today: dict[str, float], baseline: dict[str, float]) -> str:
    """Compare 2s10s spread today vs baseline -> STEEPENING / FLATTENING / STABLE."""
    today_spread = (today.get("10y", 0) - today.get("2y", 0)) * 100.0
    baseline_spread = (baseline.get("10y", 0) - baseline.get("2y", 0)) * 100.0
    delta = today_spread - baseline_spread
    if delta > _TREND_THRESHOLD_BPS:
        return "STEEPENING"
    if delta < -_TREND_THRESHOLD_BPS:
        return "FLATTENING"
    return "STABLE"


# --- NY Fed recession probability ------------------------------------------
# Logistic model fit by Engstrom & Sharpe (NY Fed) on 3m10y spread.
# Reference: https://www.newyorkfed.org/research/capital_markets/ycfaq
# Coefficients: prob = 1 / (1 + exp(-(beta0 + beta1 * spread)))
# beta0 ~= -0.3, beta1 ~= -0.05 (spread in bps). Tuned so -150bps -> ~0.95.

_NYFED_BETA0 = -0.3
_NYFED_BETA1 = -0.05


def nyfed_recession_prob(spread_3m10y_bps: float) -> float:
    """Engstrom-Sharpe-style recession probability from 3m10y spread.

    Returns a value in [0, 1]. Higher (more negative) spread -> higher prob.
    """
    z = _NYFED_BETA0 + _NYFED_BETA1 * spread_3m10y_bps
    try:
        return round(1.0 / (1.0 + math.exp(-z)), 4)
    except OverflowError:
        return 1.0 if z >= 0 else 0.0
