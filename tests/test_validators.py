"""Offline coverage for src/core/validators.py.

The module had no dedicated tests. These pin the public surface:

* ``ValidationResult`` construction / merge semantics
* ``validate_freshness`` — fresh / boundary / stale / None / negative / NaN
* ``validate_change_from_previous`` — valid, boundary, excessive, None,
  non-positive prev close, non-numeric, NaN
* ``validate_cross_symbol_consistency`` — agree / diverge / boundary / one
  missing / NaN change_pct
* ``validate_futures_spot_consistency`` — ES and NQ legs, thresholds, gaps
* ``validate_ohlc`` — valid candle, high/low violations, non-positive,
  multi-issue accumulation, None, non-numeric, NaN
* ``validate_market_internals`` — empty, metadata skip, non-dict entry,
  negative volume, embedded bad OHLC, non-dict internals
* ``is_data_usable`` — synthetic/mock, missing core symbols, bad price,
  good data, non-dict internals, None/NaN/str price
* ``flag_data_quality`` — good / stale / missing symbols / synthetic /
  non-dict spy entry / non-dict internals

Callers (src/data/market_collector.py) rely on: ``validation.issues`` being
joinable strings, ``is_data_usable`` returning ``(bool, reason)``, and
``flag_data_quality`` returning the ``data_quality`` / ``issues`` /
``missing_symbols`` keys — all pinned here.

Tests marked ``test_bug_*`` fail on the pre-fix module (proven against a
HEAD copy in the cycle-7 report); the rest pin existing correct behaviour
and pass on both versions.

All tests reference the module through ``validators.<fn>`` attribute access
so the HEAD-copy proof can swap ``sys.modules`` entries.
"""

from __future__ import annotations

import math
import sys

from src.core import validators

# ---------------------------------------------------------------------------
# ValidationResult
# ---------------------------------------------------------------------------


def test_validation_result_defaults_and_repr():
    r = validators.ValidationResult(True)
    assert r.is_valid is True
    assert r.issues == []
    assert r.warnings == []
    assert "VALID" in repr(r)
    assert "INVALID" in repr(validators.ValidationResult(False, ["x"]))


def test_validation_result_merge():
    a = validators.ValidationResult(False, ["i1"], ["w1"])
    b = validators.ValidationResult(True, ["i2"], ["w2"])
    m = a.merge(b)
    assert m.is_valid is False  # AND semantics
    assert m.issues == ["i1", "i2"]
    assert m.warnings == ["w1", "w2"]
    assert validators.ValidationResult(True).merge(validators.ValidationResult(True)).is_valid is True


# ---------------------------------------------------------------------------
# validate_freshness
# ---------------------------------------------------------------------------


def test_freshness_valid_and_boundary():
    assert validators.validate_freshness(0).is_valid is True
    at_limit = validators.validate_freshness(validators.FRESHNESS_THRESHOLD_SECONDS)
    assert at_limit.is_valid is True
    assert at_limit.warnings == []  # exactly at the limit is not stale (strict >)


def test_freshness_stale_warns_but_still_valid():
    r = validators.validate_freshness(validators.FRESHNESS_THRESHOLD_SECONDS + 1)
    assert r.is_valid is True  # stale is a warning, never a failure
    assert len(r.warnings) == 1
    assert "stale" in r.warnings[0]


def test_freshness_none_age_warns_unknown():
    r = validators.validate_freshness(None)
    assert r.is_valid is True
    assert r.warnings == ["Data age unknown (timestamp missing)"]


def test_bug_freshness_nan_age_is_not_silent():
    # NaN comparisons are all False, so old code returned a clean "fresh".
    r = validators.validate_freshness(math.nan)
    assert r.is_valid is True
    assert r.warnings and "unknown" in r.warnings[0].lower()


def test_bug_freshness_negative_age_warns_future_timestamp():
    r = validators.validate_freshness(-30.0)
    assert r.is_valid is True
    assert r.warnings and any("negative" in w.lower() or "future" in w.lower() for w in r.warnings)


def test_freshness_infinite_age_is_stale():
    r = validators.validate_freshness(math.inf)
    assert r.is_valid is True
    assert "stale" in r.warnings[0].lower()


# ---------------------------------------------------------------------------
# validate_change_from_previous
# ---------------------------------------------------------------------------


def test_change_valid_and_boundary():
    assert validators.validate_change_from_previous(105.0, 100.0).is_valid is True
    exactly_max = validators.validate_change_from_previous(108.0, 100.0)  # 8.0% == max
    assert exactly_max.is_valid is True
    assert exactly_max.issues == []


def test_change_excessive_flagged_with_message():
    r = validators.validate_change_from_previous(90.0, 100.0)  # -10%
    assert r.is_valid is False
    assert "exceeds max" in r.issues[0]


def test_change_none_and_bad_prev_close():
    assert validators.validate_change_from_previous(None, 100.0).is_valid is False
    assert validators.validate_change_from_previous(100.0, None).is_valid is False
    r = validators.validate_change_from_previous(100.0, 0.0)
    assert r.is_valid is False
    assert "Invalid previous close" in r.issues[0]
    assert validators.validate_change_from_previous(100.0, -5.0).is_valid is False


def test_bug_change_nan_price_is_invalid():
    r = validators.validate_change_from_previous(math.nan, 100.0)
    assert r.is_valid is False
    assert r.issues


def test_bug_change_nan_prev_close_is_invalid():
    r = validators.validate_change_from_previous(100.0, math.nan)
    assert r.is_valid is False
    assert r.issues


def test_bug_change_non_numeric_price_returns_result_not_crash():
    r = validators.validate_change_from_previous("abc", 100.0)
    assert r.is_valid is False
    assert r.issues


def test_bug_change_bool_price_is_invalid():
    r = validators.validate_change_from_previous(True, 100.0)
    assert r.is_valid is False
    assert r.issues


# ---------------------------------------------------------------------------
# validate_cross_symbol_consistency
# ---------------------------------------------------------------------------


def _internals(spy_pct=0.0, qqq_pct=0.0):
    return {
        "spy": {"price": 450.0, "change_pct": spy_pct},
        "qqq": {"price": 380.0, "change_pct": qqq_pct},
    }


def test_cross_symbol_agree_and_boundary():
    assert validators.validate_cross_symbol_consistency(_internals(1.0, 1.5)).warnings == []
    boundary = validators.validate_cross_symbol_consistency(_internals(2.0, 12.0))  # exactly 10%
    assert boundary.warnings == []  # strict >


def test_cross_symbol_divergence_warns():
    r = validators.validate_cross_symbol_consistency(_internals(2.0, 15.0))  # 13%
    assert r.is_valid is True  # divergence is a warning, not a failure
    assert len(r.warnings) == 1
    assert "diverge" in r.warnings[0]
    assert "+2.00%" in r.warnings[0] and "+15.00%" in r.warnings[0]


def test_cross_symbol_one_missing_or_flat():
    assert validators.validate_cross_symbol_consistency({"spy": {"change_pct": 5.0}}).warnings == []
    assert validators.validate_cross_symbol_consistency(_internals(0.0, 0.0)).warnings == []


def test_bug_cross_symbol_nan_change_warns():
    r = validators.validate_cross_symbol_consistency(_internals(math.nan, 2.0))
    assert r.is_valid is True
    assert r.warnings  # cannot-verify note instead of silent pass


# ---------------------------------------------------------------------------
# validate_futures_spot_consistency
# ---------------------------------------------------------------------------


def _futures_internals(es_pct=0.5, spy_pct=0.5, nq_pct=0.5, qqq_pct=0.5):
    return {
        "es=f": {"price": 5500.0, "change_pct": es_pct},
        "spy": {"price": 450.0, "change_pct": spy_pct},
        "nq=f": {"price": 19000.0, "change_pct": nq_pct},
        "qqq": {"price": 380.0, "change_pct": qqq_pct},
    }


def test_futures_consistent_no_warning():
    assert validators.validate_futures_spot_consistency(_futures_internals()).warnings == []


def test_futures_es_leg_warns_past_threshold():
    r = validators.validate_futures_spot_consistency(_futures_internals(es_pct=4.0, spy_pct=0.0))
    assert len(r.warnings) == 1
    assert "ES=F" in r.warnings[0]


def test_futures_nq_leg_warns_past_threshold():
    r = validators.validate_futures_spot_consistency(_futures_internals(nq_pct=6.0, qqq_pct=0.0))
    assert len(r.warnings) == 1
    assert "NQ=F" in r.warnings[0]


def test_futures_missing_legs_no_warning():
    assert validators.validate_futures_spot_consistency({"spy": {"price": 1.0}}).warnings == []


# ---------------------------------------------------------------------------
# validate_ohlc
# ---------------------------------------------------------------------------


def test_ohlc_valid_candle():
    r = validators.validate_ohlc(100.0, 110.0, 95.0, 105.0)
    assert r.is_valid is True
    assert r.issues == []


def test_ohlc_high_and_low_violations():
    r = validators.validate_ohlc(100.0, 99.0, 101.0, 105.0)
    assert r.is_valid is False
    assert any("High" in i for i in r.issues)
    assert any("Low" in i for i in r.issues)


def test_ohlc_non_positive_price():
    r = validators.validate_ohlc(100.0, 110.0, 0.0, 105.0)
    assert r.is_valid is False
    assert any("non-positive" in i for i in r.issues)


def test_ohlc_none_invalid():
    r = validators.validate_ohlc(100.0, None, 95.0, 105.0)
    assert r.is_valid is False
    assert "None" in r.issues[0]


def test_bug_ohlc_nan_is_invalid():
    r = validators.validate_ohlc(100.0, math.nan, 95.0, 105.0)
    assert r.is_valid is False
    assert r.issues


def test_bug_ohlc_non_numeric_returns_result_not_crash():
    r = validators.validate_ohlc("open", 110.0, 95.0, 105.0)
    assert r.is_valid is False
    assert r.issues


# ---------------------------------------------------------------------------
# validate_market_internals
# ---------------------------------------------------------------------------


def _good_spy(age=60.0):
    return {
        "spy": {"price": 450.0, "change_pct": 0.5, "data_age_seconds": age, "volume": 1000},
        "qqq": {"price": 380.0, "change_pct": 0.6, "data_age_seconds": age, "volume": 800},
        "vix": {"price": 15.0, "change_pct": -1.0, "data_age_seconds": age},
        "data_source": "yahoo",
    }


def test_market_internals_empty_and_metadata_skip():
    assert validators.validate_market_internals({}).is_valid is True
    r = validators.validate_market_internals({"data_quality": "good", "timestamp": 1})
    assert r.is_valid is True


def test_market_internals_non_dict_entry():
    r = validators.validate_market_internals({"spy": 123.0})
    assert r.is_valid is False
    assert any("not a dict" in i for i in r.issues)


def test_market_internals_negative_volume():
    r = validators.validate_market_internals({"spy": {"price": 1.0, "volume": -5}})
    assert r.is_valid is False
    assert any("negative volume" in i for i in r.issues)


def test_market_internals_embedded_bad_ohlc():
    bad = {"spy": {"open": 100.0, "high": 90.0, "low": 95.0, "close": 105.0}}
    r = validators.validate_market_internals(bad)
    assert r.is_valid is False
    assert any("High" in i for i in r.issues)


def test_bug_market_internals_non_dict_internals_returns_result_not_crash():
    r = validators.validate_market_internals(None)
    assert r.is_valid is False
    assert r.issues


# ---------------------------------------------------------------------------
# is_data_usable
# ---------------------------------------------------------------------------


def _usable_base():
    return {
        "spy": {"price": 450.0},
        "qqq": {"price": 380.0},
        "data_source": "yahoo",
    }


def test_usable_good_data():
    ok, reason = validators.is_data_usable(_usable_base())
    assert ok is True
    assert "passes" in reason


def test_usable_synthetic_or_mock():
    for extra in ({"synthetic": True}, {"data_source": "mock"}):
        internals = {**_usable_base(), **extra}
        ok, reason = validators.is_data_usable(internals)
        assert ok is False
        assert "synthetic" in reason.lower() or "mock" in reason.lower()


def test_usable_missing_core_symbol():
    internals = _usable_base()
    del internals["spy"]
    ok, reason = validators.is_data_usable(internals)
    assert ok is False
    assert "SPY" in reason


def test_usable_non_positive_price():
    internals = _usable_base()
    internals["qqq"]["price"] = 0
    ok, reason = validators.is_data_usable(internals)
    assert ok is False
    assert "QQQ" in reason and "invalid" in reason


def test_bug_usable_none_price_returns_false_not_crash():
    internals = _usable_base()
    internals["spy"]["price"] = None
    ok, reason = validators.is_data_usable(internals)
    assert ok is False
    assert "invalid" in reason


def test_bug_usable_nan_price_is_not_usable():
    internals = _usable_base()
    internals["spy"]["price"] = math.nan
    ok, _ = validators.is_data_usable(internals)
    assert ok is False


def test_bug_usable_str_price_returns_false_not_crash():
    internals = _usable_base()
    internals["spy"]["price"] = "450"
    ok, reason = validators.is_data_usable(internals)
    assert ok is False
    assert "invalid" in reason


def test_bug_usable_none_internals_returns_false_not_crash():
    ok, reason = validators.is_data_usable(None)
    assert ok is False
    assert reason


# ---------------------------------------------------------------------------
# flag_data_quality
# ---------------------------------------------------------------------------


def test_flag_quality_good_data():
    flags = validators.flag_data_quality(_good_spy())
    assert flags["data_quality"] == "good"
    assert flags["validation_passed"] is True
    assert flags["freshness_status"] == "fresh"
    assert flags["missing_symbols"] == []
    assert flags["synthetic"] is False


def test_flag_quality_stale_and_missing_symbols():
    flags = validators.flag_data_quality(_good_spy(age=validators.FRESHNESS_THRESHOLD_SECONDS + 1))
    assert flags["freshness_status"] == "stale"
    assert flags["data_quality"] == "partial"  # stale warning alone degrades to partial
    assert any("stale" in w.lower() for w in flags["warnings"])

    stripped = _good_spy(age=60.0)
    del stripped["vix"]
    flags2 = validators.flag_data_quality(stripped)
    assert flags2["missing_symbols"] == ["vix"]  # spy+qqq present, vix absent
    assert any("vix" in w.lower() for w in flags2["warnings"])


def test_flag_quality_synthetic_is_poor():
    internals = {**_good_spy(), "vix": {"price": 15.0}, "synthetic": True}
    flags = validators.flag_data_quality(internals)
    assert flags["data_quality"] == "poor"
    assert flags["synthetic"] is True


def test_bug_flag_quality_non_dict_spy_entry_no_crash():
    flags = validators.flag_data_quality({"spy": 123.0, "qqq": {"price": 1.0}})
    assert "data_quality" in flags  # returns flags instead of AttributeError
    assert flags["data_quality"] in ("poor", "partial", "unknown", "good")


def test_bug_flag_quality_none_internals_no_crash():
    flags = validators.flag_data_quality(None)
    assert flags["data_quality"] in ("poor", "partial", "unknown")
    assert flags["missing_symbols"] == ["spy", "qqq", "vix"]


# ---------------------------------------------------------------------------
# Oversized inputs (no pathological behaviour at scale)
# ---------------------------------------------------------------------------


def test_oversized_internals_walk():
    internals = {f"sym{i}": {"price": 1.0, "volume": 1} for i in range(2000)}
    internals["spy"] = {"price": 450.0, "change_pct": 0.0}
    internals["qqq"] = {"price": 380.0, "change_pct": 0.0}
    r = validators.validate_market_internals(internals)
    assert r.is_valid is True


def test_oversized_price_magnitudes():
    big = 1e12
    assert validators.validate_change_from_previous(big, big).is_valid is True
    r = validators.validate_ohlc(big, big * 2, big / 2, big)
    assert r.is_valid is True


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for fn in tests:
        try:
            fn()
            passed += 1
        except Exception:
            import traceback

            print(f"  FAIL: {fn.__name__}")
            traceback.print_exc()
            failed += 1
    print(f"\nResults: {passed}/{len(tests)} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
