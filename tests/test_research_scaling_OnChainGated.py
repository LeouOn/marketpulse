"""Tests for OnChainGated scaling model."""

from __future__ import annotations

import pandas as pd
import pytest

from src.research.scaling import InvalidParamsError, list_scaling_models, get_scaling
from src.research.scaling.OnChainGated import OnChainGated


def _returns(n: int = 200) -> pd.Series:
    import numpy as np
    rng = np.random.default_rng(0)
    return pd.Series(rng.normal(0.001, 0.02, n))


# ---------------------------------------------------------------------------
# Construction & validation
# ---------------------------------------------------------------------------


def test_default_params_validate():
    """Default params should pass validation."""
    m = OnChainGated()
    assert m.params["base_buy_multiplier"] == 1.0


def test_reject_zero_base_buy_multiplier():
    with pytest.raises(InvalidParamsError, match="base_buy_multiplier must be > 0"):
        OnChainGated(params={"base_buy_multiplier": 0})


def test_reject_mismatched_bands_multipliers():
    with pytest.raises(InvalidParamsError, match="same non-zero length"):
        OnChainGated(params={"mvrv_bands": [-1, 0], "mvrv_multipliers": [2.0]})


def test_reject_empty_bands():
    with pytest.raises(InvalidParamsError, match="same non-zero length"):
        OnChainGated(params={"mvrv_bands": [], "mvrv_multipliers": []})


# ---------------------------------------------------------------------------
# Band logic
# ---------------------------------------------------------------------------


def test_mvrv_below_first_band_returns_2x():
    m = OnChainGated(params={"base_buy_multiplier": 500.0})
    buy, sell = m.size(
        equity=10_000, position_value=0, price=30_000,
        recent_returns=_returns(),
        state={"mvrv_z": -2.0},
    )
    # Below -1.0 band -> multiplier 2.0 -> 500 * 2.0 = 1000
    assert buy == 1000.0
    assert sell == 0.0


def test_mvrv_in_neutral_band_returns_1x():
    m = OnChainGated(params={"base_buy_multiplier": 500.0})
    buy, sell = m.size(
        equity=10_000, position_value=0, price=30_000,
        recent_returns=_returns(),
        state={"mvrv_z": 1.0},
    )
    # Between 0.0 and 1.5 -> multiplier 1.0 -> 500 * 1.0 = 500
    assert buy == 500.0
    assert sell == 0.0


def test_mvrv_above_last_band_returns_0_5x():
    m = OnChainGated(params={"base_buy_multiplier": 500.0})
    buy, sell = m.size(
        equity=10_000, position_value=0, price=30_000,
        recent_returns=_returns(),
        state={"mvrv_z": 6.0},
    )
    # Above 5.0 -> last multiplier 0.5 -> 500 * 0.5 = 250
    assert buy == 250.0
    assert sell == 0.0


def test_no_state_returns_neutral():
    m = OnChainGated(params={"base_buy_multiplier": 500.0})
    buy, sell = m.size(
        equity=10_000, position_value=0, price=30_000,
        recent_returns=_returns(),
        state=None,
    )
    assert buy == 500.0  # base * 1.0
    assert sell == 0.0


def test_none_mvrv_returns_neutral():
    m = OnChainGated(params={"base_buy_multiplier": 500.0})
    buy, sell = m.size(
        equity=10_000, position_value=0, price=30_000,
        recent_returns=_returns(),
        state={"mvrv_z": None},
    )
    assert buy == 500.0
    assert sell == 0.0


def test_bands_boundary_values():
    """Exact boundary values should use the NEXT band's multiplier."""
    m = OnChainGated(params={"base_buy_multiplier": 500.0})
    # mvrv_z == 0.0 exactly -> 0.0 < 0.0 is False, so it goes to next band (1.5)
    # Actually 0.0 < 0.0 is False, so it checks < 1.5 -> multiplier 1.0
    buy, _ = m.size(10_000, 0, 30_000, _returns(), state={"mvrv_z": 0.0})
    assert buy == 500.0  # band [0.0, 1.5) -> multiplier 1.0

    # mvrv_z == -1.0 exactly -> -1.0 < -1.0 is False -> next band 0.0 -> multiplier 1.5
    buy, _ = m.size(10_000, 0, 30_000, _returns(), state={"mvrv_z": -1.0})
    assert buy == 750.0  # 500 * 1.5

    # mvrv_z == 1.5 exactly -> 1.5 < 1.5 is False -> next band 3.0 -> multiplier 0.75
    buy, _ = m.size(10_000, 0, 30_000, _returns(), state={"mvrv_z": 1.5})
    assert buy == 375.0  # 500 * 0.75


def test_nan_mvrv_returns_neutral():
    m = OnChainGated(params={"base_buy_multiplier": 500.0})
    buy, sell = m.size(
        equity=10_000, position_value=0, price=30_000,
        recent_returns=_returns(),
        state={"mvrv_z": float("nan")},
    )
    assert buy == 500.0
    assert sell == 0.0


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_includes_onchaingated():
    names = {s["name"] for s in list_scaling_models()}
    assert "OnChainGated" in names


def test_get_scaling_returns_onchaingated():
    m = get_scaling("OnChainGated")
    assert isinstance(m, OnChainGated)
    assert m.name == "OnChainGated"
