"""Edge/property tests for src/warsh/simulator.py.

tests/warsh/test_simulator.py already covers initialization, directional
effects (RMP/QT/guidance/regulation), result shape, and the hawkish/dovish/
current presets. This file adds ONLY what that file does not: determinism,
monotonicity/sanity properties, arithmetic exactness, the pantomime preset,
sparse-curve fill behavior, input immutability — and the bad-input paths
(out-of-range, negative, NaN/inf overrides; empty or NaN baselines; unknown
scenario names). Everything is pure computation: fast, offline, no waits.
"""

from __future__ import annotations

import math

import pytest

from src.warsh.simulator import ALL_TENORS, CurveSimulator

BASELINE = {
    "3mo": 3.84,
    "1y": 4.02,
    "2y": 4.16,
    "5y": 4.31,
    "7y": 4.44,
    "10y": 4.58,
    "20y": 5.09,
    "30y": 5.08,
}


# ---------------------------------------------------------------------------
# Determinism / sanity properties
# ---------------------------------------------------------------------------


def test_simulation_is_deterministic():
    sim = CurveSimulator(BASELINE)
    kwargs = dict(rmp=80, qt_pace=30, srf=800, mbs_sales=10, forward_guidance=0, bank_regulation=0.6)

    first = sim.simulate(**kwargs)
    second = sim.simulate(**kwargs)

    assert first.adjusted_curve == second.adjusted_curve
    assert first.new_2s10s == second.new_2s10s
    assert first.new_3m10y == second.new_3m10y
    assert first.new_shape == second.new_shape
    assert first.tool_effects == second.tool_effects


def test_higher_rmp_never_flattens_monotonically():
    """RMP suppresses the front end: more RMP -> 2s10s non-decreasing."""
    sim = CurveSimulator(BASELINE)
    spreads = [sim.simulate(rmp=level).new_2s10s for level in (0, 25, 50, 75, 100)]

    assert all(a <= b for a, b in zip(spreads, spreads[1:], strict=False)), spreads


def test_lower_qt_pace_never_flattens_monotonically():
    """Less QT -> lower long-end yields: 2s10s non-decreasing as pace drops."""
    sim = CurveSimulator(BASELINE)
    spreads = [sim.simulate(qt_pace=pace).new_2s10s for pace in (95, 70, 45, 20, 0)]

    assert all(a <= b for a, b in zip(spreads, spreads[1:], strict=False)), spreads


def test_adjusted_curve_is_exact_baseline_plus_bps_over_100():
    sim = CurveSimulator(BASELINE)
    result = sim.simulate(rmp=100)

    for tenor in ALL_TENORS:
        total_bps = sum(effects[tenor] for effects in result.tool_effects.values())
        expected = BASELINE.get(tenor, 4.0) + total_bps / 100.0
        assert result.adjusted_curve[tenor] == pytest.approx(expected), tenor


def test_tool_effects_cover_all_six_tools_and_zero_when_unchanged():
    sim = CurveSimulator(BASELINE)
    result = sim.simulate()  # all current values -> all deltas zero

    from src.warsh.tools import ToolName

    assert set(result.tool_effects) == {t.value for t in ToolName}
    assert all(bps == 0.0 for effects in result.tool_effects.values() for bps in effects.values())


def test_baseline_input_dict_is_not_mutated():
    original = dict(BASELINE)
    CurveSimulator(BASELINE).simulate(rmp=90)
    assert BASELINE == original


def test_sparse_baseline_fills_missing_tenors_with_default():
    """Documented fill behavior: missing tenors default to 4.0 in the output."""
    result = CurveSimulator({"2y": 4.16, "10y": 4.58}).simulate(rmp=60)

    assert set(result.adjusted_curve) == set(ALL_TENORS)
    assert result.adjusted_curve["2y"] != 4.0  # real input used
    assert result.adjusted_curve["30y"] == pytest.approx(
        4.0 + sum(e["30y"] for e in result.tool_effects.values()) / 100.0
    )


# ---------------------------------------------------------------------------
# Scenario presets
# ---------------------------------------------------------------------------


def test_pantomime_preset_steepens_and_is_labelled():
    """The untested fourth preset: shadow easing steepens, between hawkish and dovish."""
    sim = CurveSimulator(BASELINE)
    pantomime = sim.simulate_scenario("pantomime")
    hawkish = sim.simulate_scenario("hawkish")
    dovish = sim.simulate_scenario("dovish")

    assert pantomime.scenario_label == "pantomime"
    assert hawkish.delta_2s10s < pantomime.delta_2s10s < dovish.delta_2s10s


@pytest.mark.parametrize("scenario", ["hawkish", "pantomime", "dovish", "current"])
def test_every_scenario_sets_its_label(scenario):
    result = CurveSimulator(BASELINE).simulate_scenario(scenario)
    assert result.scenario_label == scenario


def test_unknown_scenario_is_a_clear_error():
    with pytest.raises(ValueError, match="bogus"):
        CurveSimulator(BASELINE).simulate_scenario("bogus")


# ---------------------------------------------------------------------------
# Override validation (bad input)
# ---------------------------------------------------------------------------


def test_override_above_tool_max_is_rejected():
    with pytest.raises(ValueError, match="rmp"):
        CurveSimulator(BASELINE).simulate(rmp=200)  # max is 100


def test_negative_override_is_rejected():
    with pytest.raises(ValueError, match="qt_pace"):
        CurveSimulator(BASELINE).simulate(qt_pace=-10)


def test_nan_override_is_rejected():
    with pytest.raises(ValueError, match="rmp"):
        CurveSimulator(BASELINE).simulate(rmp=math.nan)


def test_inf_override_is_rejected():
    with pytest.raises(ValueError, match="srf"):
        CurveSimulator(BASELINE).simulate(srf=math.inf)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"rmp": 0},
        {"rmp": 100},
        {"qt_pace": 0},
        {"qt_pace": 95},
        {"forward_guidance": 0},
        {"forward_guidance": 1},
        {"bank_regulation": 0.0},
        {"bank_regulation": 1.0},
    ],
)
def test_exact_tool_bounds_are_accepted(kwargs):
    result = CurveSimulator(BASELINE).simulate(**kwargs)
    assert len(result.adjusted_curve) == len(ALL_TENORS)


# ---------------------------------------------------------------------------
# Baseline validation (bad input)
# ---------------------------------------------------------------------------


def test_empty_baseline_is_a_clear_error():
    with pytest.raises(ValueError, match="empty"):
        CurveSimulator({})


def test_nan_baseline_yield_is_a_clear_error():
    with pytest.raises(ValueError, match="finite"):
        CurveSimulator({"2y": math.nan, "10y": 4.58})


def test_none_baseline_yield_is_a_clear_error():
    with pytest.raises(ValueError, match="finite"):
        CurveSimulator({"2y": None, "10y": 4.58})
