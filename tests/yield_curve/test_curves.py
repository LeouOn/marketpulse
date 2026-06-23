"""Unit tests for pure curve math (no I/O)."""
from datetime import date

import pytest

from src.yield_curve.curves import (
    CurveShape,
    classify_shape,
    classify_trend,
    compute_spreads,
    nyfed_recession_prob,
)


def test_compute_spreads_normal_curve():
    # 3M=5.0, 2Y=4.5, 10Y=4.4, 30Y=4.6 -> 2s10s = -10bps? No: yields in %,
    # spread = (long - short) in basis points = (4.4 - 4.5) * 100 = -10 bps
    curve = {"3mo": 5.0, "1y": 4.8, "2y": 4.5, "5y": 4.35, "7y": 4.40, "10y": 4.40, "20y": 4.55, "30y": 4.60}
    spreads = compute_spreads(curve)
    assert spreads["2s10s"] == pytest.approx((4.40 - 4.50) * 100, abs=0.01)
    assert spreads["3m10y"] == pytest.approx((4.40 - 5.00) * 100, abs=0.01)
    assert spreads["5s30s"] == pytest.approx((4.60 - 4.35) * 100, abs=0.01)
    assert spreads["2s30s"] == pytest.approx((4.60 - 4.50) * 100, abs=0.01)


def test_compute_spreads_missing_tenor_returns_none():
    curve = {"2y": 4.5, "10y": 4.4}
    spreads = compute_spreads(curve)
    assert spreads["2s10s"] == pytest.approx(-10.0, abs=0.01)
    assert spreads["3m10y"] is None
    assert spreads["5s30s"] is None


def test_classify_shape_normal():
    curve = {"2y": 4.5, "5y": 4.4, "10y": 4.6, "30y": 4.8}
    assert classify_shape(curve) == CurveShape.NORMAL


def test_classify_shape_inverted_2s10s():
    # 2y > 10y -> inverted
    curve = {"2y": 4.6, "5y": 4.5, "10y": 4.4, "30y": 4.6}
    assert classify_shape(curve) == CurveShape.INVERTED


def test_classify_shape_flat():
    # All tenors within 25bps band -> FLAT
    curve = {"2y": 4.40, "5y": 4.41, "10y": 4.42, "30y": 4.43}
    assert classify_shape(curve) == CurveShape.FLAT


def test_classify_trend_steepening():
    today = {"2y": 4.40, "10y": 4.60}  # 2s10s = +20
    baseline = {"2y": 4.45, "10y": 4.55}  # 2s10s = +10
    assert classify_trend(today, baseline) == "STEEPENING"


def test_classify_trend_flattening():
    today = {"2y": 4.40, "10y": 4.50}  # 2s10s = +10
    baseline = {"2y": 4.45, "10y": 4.65}  # 2s10s = +20
    assert classify_trend(today, baseline) == "FLATTENING"


def test_classify_trend_stable():
    today = {"2y": 4.40, "10y": 4.50}
    baseline = {"2y": 4.401, "10y": 4.501}
    assert classify_trend(today, baseline) == "STABLE"


def test_nyfed_recession_prob_high_when_3m10y_deeply_inverted():
    # 3m10y = -150bps -> very high recession prob (>= 0.90)
    prob = nyfed_recession_prob(-150.0)
    assert 0.0 <= prob <= 1.0
    assert prob >= 0.90


def test_nyfed_recession_prob_low_when_curve_steep():
    # 3m10y = +200bps -> very low recession prob (<= 0.05)
    prob = nyfed_recession_prob(200.0)
    assert 0.0 <= prob <= 1.0
    assert prob <= 0.05


def test_nyfed_recession_prob_monotone_decreasing():
    # Higher 3m10y spread -> lower recession probability.
    p_neg = nyfed_recession_prob(-100.0)
    p_pos = nyfed_recession_prob(100.0)
    assert p_neg > p_pos
