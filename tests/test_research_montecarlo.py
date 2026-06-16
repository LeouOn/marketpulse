"""Tests for the Monte Carlo engine.

We verify:
- GBM closed-form sanity: mean terminal wealth matches s0*exp(mu*T)
- Block bootstrap preserves the empirical mean
- Regime switching produces finite, non-degenerate results
- Strategy simulation runs a backtest on each path
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.research.montecarlo import (
    SimulationResult,
    simulate_block_bootstrap,
    simulate_gbm,
    simulate_regime_switching,
    simulate_strategy,
)


# ---------------------------------------------------------------------------
# GBM
# ---------------------------------------------------------------------------


def test_gbm_shape():
    r = simulate_gbm(mu=0.5, sigma=0.8, s0=100.0, n_steps=100, n_paths=50, seed=0)
    assert r.paths.shape == (50, 101)
    assert r.terminal_values.shape == (50,)
    assert r.max_drawdowns.shape == (50,)
    assert r.paths[0, 0] == 100.0  # starts at s0


def test_gbm_invalid_args_raise():
    with pytest.raises(ValueError):
        simulate_gbm(mu=0.5, sigma=0.5, s0=0.0)
    with pytest.raises(ValueError):
        simulate_gbm(mu=0.5, sigma=0.5, s0=100.0, n_paths=0)
    with pytest.raises(ValueError):
        simulate_gbm(mu=0.5, sigma=-0.1, s0=100.0)


def test_gbm_mean_terminal_matches_closed_form():
    """E[S_T] = s0 * exp(mu * T). For 1000 paths of 1 year, mean should be close."""
    r = simulate_gbm(mu=0.5, sigma=0.4, s0=100.0, n_steps=365, n_paths=5000, seed=42)
    expected_mean = 100.0 * np.exp(0.5 * 1.0)
    actual_mean = float(r.terminal_values.mean())
    # Within 10% for 5000 paths
    assert abs(actual_mean - expected_mean) / expected_mean < 0.10


def test_gbm_paths_are_strictly_positive():
    r = simulate_gbm(mu=0.0, sigma=0.5, s0=100.0, n_steps=100, n_paths=50, seed=0)
    assert (r.paths > 0).all()


def test_gbm_summary_keys_present():
    r = simulate_gbm(mu=0.0, sigma=0.3, s0=100.0, n_steps=10, n_paths=100, seed=0)
    for key in (
        "terminal_median",
        "terminal_mean",
        "terminal_p05",
        "terminal_p95",
        "prob_profit_pct",
        "max_dd_median_pct",
    ):
        assert key in r.summary


def test_gbm_is_deterministic_with_seed():
    a = simulate_gbm(mu=0.1, sigma=0.2, s0=100.0, n_steps=50, n_paths=100, seed=123)
    b = simulate_gbm(mu=0.1, sigma=0.2, s0=100.0, n_steps=50, n_paths=100, seed=123)
    assert (a.paths == b.paths).all()
    assert (a.terminal_values == b.terminal_values).all()


# ---------------------------------------------------------------------------
# Block bootstrap
# ---------------------------------------------------------------------------


def test_block_bootstrap_shape():
    rets = pd.Series(np.random.default_rng(0).normal(0.001, 0.02, 1000))
    r = simulate_block_bootstrap(rets, n_paths=20, n_steps=500, block_size=10, seed=0)
    assert r.paths.shape == (20, 501)


def test_block_bootstrap_empty_raises():
    with pytest.raises(ValueError):
        simulate_block_bootstrap(pd.Series([], dtype=float))


def test_block_bootstrap_preserves_empirical_mean_approximately():
    """The mean of the simulated paths should be close to the empirical mean compounded."""
    rng = np.random.default_rng(0)
    rets = pd.Series(rng.normal(0.001, 0.02, 2000))
    expected_cum_return = float((1.0 + rets).prod())  # empirical compounded
    r = simulate_block_bootstrap(rets, starting_value=100.0, n_paths=500, n_steps=2000, block_size=20, seed=0)
    # Median terminal value should be in the same order of magnitude
    actual_median = float(np.median(r.terminal_values))
    # Within 50% of empirical compounded
    assert 0.5 * expected_cum_return * 100 < actual_median < 2.0 * expected_cum_return * 100


def test_block_bootstrap_block_size_too_large_raises():
    rets = pd.Series([0.01] * 5)
    with pytest.raises(ValueError):
        simulate_block_bootstrap(rets, block_size=10)


# ---------------------------------------------------------------------------
# Regime switching
# ---------------------------------------------------------------------------


def test_regime_switching_shape():
    rets = pd.Series(np.random.default_rng(0).normal(0.001, 0.02, 1000))
    r = simulate_regime_switching(rets, n_paths=20, n_steps=500, seed=0)
    assert r.paths.shape == (20, 501)


def test_regime_switching_empty_raises():
    with pytest.raises(ValueError):
        simulate_regime_switching(pd.Series([], dtype=float))


def test_regime_switching_paths_are_finite():
    rets = pd.Series(np.random.default_rng(0).normal(0.001, 0.02, 500))
    r = simulate_regime_switching(rets, n_paths=50, n_steps=300, seed=0)
    assert np.isfinite(r.paths).all()
    # No path should have lost everything (min > 0)
    assert (r.paths > 0).all()


def test_regime_switching_summary_reports_two_states():
    rets = pd.Series(np.random.default_rng(0).normal(0.0, 0.05, 1000))
    r = simulate_regime_switching(rets, n_paths=10, n_steps=200, seed=0)
    assert "mu_low" in r.params
    assert "mu_high" in r.params
    assert "sigma_low" in r.params
    assert "sigma_high" in r.params
    # High-vol regime should have higher sigma than low-vol
    assert r.params["sigma_high"] > r.params["sigma_low"]


# ---------------------------------------------------------------------------
# Strategy simulation
# ---------------------------------------------------------------------------


def test_simulate_strategy_runs_backtest_on_each_path():
    from src.research.strategies import BuyAndHold

    rets = pd.Series(np.random.default_rng(0).normal(0.001, 0.02, 200))
    out = simulate_strategy(
        rets,
        strategy_factory=lambda: BuyAndHold(),
        n_paths=5,
        n_steps=200,
        starting_equity=10_000.0,
        method="block_bootstrap",
        seed=0,
    )
    assert out["equity_paths"].shape == (5, 201)
    assert out["starting_equity"] == 10_000.0
    assert len(out["metrics_per_path"]) == 5
    # Each path should have produced a valid backtest result
    for m in out["metrics_per_path"]:
        assert "total_return_pct" in m
        assert "cagr_pct" in m


def test_simulate_strategy_unknown_method_raises():
    from src.research.strategies import BuyAndHold

    rets = pd.Series([0.01] * 100)
    with pytest.raises(ValueError):
        simulate_strategy(rets, lambda: BuyAndHold(), n_paths=2, method="bogus")
