"""Tests for the curve simulation engine."""
import pytest
from src.warsh.simulator import CurveSimulator, SimulationResult


# Baseline yields for testing (approximate July 2026 levels)
BASELINE_CURVE = {
    "3mo": 3.84, "1y": 4.02, "2y": 4.16, "5y": 4.31,
    "7y": 4.44, "10y": 4.58, "20y": 5.09, "30y": 5.08,
}


def test_simulator_initializes_with_baseline():
    sim = CurveSimulator(BASELINE_CURVE)
    assert sim.baseline_2s10s is not None
    assert sim.baseline_2s10s == pytest.approx(42, abs=5)  # ~40-45bps


def test_simulator_with_current_tools_reproduces_baseline():
    """Running simulation at current tool values should approximately reproduce baseline."""
    sim = CurveSimulator(BASELINE_CURVE)
    result = sim.simulate()  # uses current tool values
    # At current deployment, net effect should be small (market already priced)
    assert abs(result.new_2s10s - sim.baseline_2s10s) < 15  # within 15bps


def test_aggressive_rmp_steepens_curve():
    """Maximizing RMP (buying more T-bills) should reduce 2Y more than 10Y."""
    sim = CurveSimulator(BASELINE_CURVE)
    result = sim.simulate(rmp=100, qt_pace=60, srf=500, mbs_sales=0, forward_guidance=1, bank_regulation=0.3)
    # High RMP suppresses 2Y → 2s10s should be higher than baseline
    assert result.new_2s10s > sim.baseline_2s10s


def test_zero_qt_steepens_curve():
    """Stopping QT (pace=0) should reduce long-end yields, steepening curve."""
    sim = CurveSimulator(BASELINE_CURVE)
    result = sim.simulate(rmp=40, qt_pace=0, srf=500, mbs_sales=0, forward_guidance=1, bank_regulation=0.3)
    assert result.new_2s10s > sim.baseline_2s10s


def test_removing_forward_guidance_increases_2y():
    """Removing forward guidance should push 2Y up (term premium returns)."""
    sim = CurveSimulator(BASELINE_CURVE)
    result = sim.simulate(rmp=40, qt_pace=60, srf=500, mbs_sales=0, forward_guidance=0, bank_regulation=0.3)
    assert result.adjusted_curve["2y"] > BASELINE_CURVE["2y"]


def test_relaxed_bank_regulation_steepens():
    """Relaxing bank regulation (index → 1) should steepen the curve."""
    sim = CurveSimulator(BASELINE_CURVE)
    result_relaxed = sim.simulate(rmp=40, qt_pace=60, srf=500, mbs_sales=0, forward_guidance=1, bank_regulation=1.0)
    result_strict = sim.simulate(rmp=40, qt_pace=60, srf=500, mbs_sales=0, forward_guidance=1, bank_regulation=0.0)
    assert result_relaxed.new_2s10s > result_strict.new_2s10s


def test_simulation_result_has_all_fields():
    sim = CurveSimulator(BASELINE_CURVE)
    result = sim.simulate()
    assert hasattr(result, "adjusted_curve")
    assert hasattr(result, "new_2s10s")
    assert hasattr(result, "new_3m10y")
    assert hasattr(result, "new_shape")
    assert hasattr(result, "delta_2s10s")
    assert hasattr(result, "tool_effects")
    assert len(result.adjusted_curve) == len(BASELINE_CURVE)


def test_scenario_preset_dovish():
    """The 'dovish' preset should steepen the curve significantly."""
    sim = CurveSimulator(BASELINE_CURVE)
    result = sim.simulate_scenario("dovish")
    assert result.delta_2s10s > 3  # steeper than baseline (heuristic model, conservative threshold)


def test_scenario_preset_hawkish():
    """The 'hawkish' preset should flatten the curve or keep it flat."""
    sim = CurveSimulator(BASELINE_CURVE)
    result = sim.simulate_scenario("hawkish")
    assert result.delta_2s10s < 5  # minimal steepening or flattening


def test_scenario_preset_current():
    """The 'current' preset should approximately reproduce baseline."""
    sim = CurveSimulator(BASELINE_CURVE)
    result = sim.simulate_scenario("current")
    assert abs(result.delta_2s10s) < 15  # within 15bps of baseline
