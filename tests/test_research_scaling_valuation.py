"""Tests for per-asset valuation scaling models (W4 T19).

Covers 4 scalers:
  - PEZScoreGated        (equities, driver: cape_z)
  - RealRateZScoreGated  (gold,      driver: real_yield_10y_z)
  - InventoryZScoreGated (oil,       driver: oil_inventories_z)
  - AffordabilityGated   (housing,   driver: affordability_index)

Each scaler extends ScalingModel, reads a pre-computed signal from the
``state`` dict, maps it through parameterized bands to a multiplier, and
returns ``(equity * multiplier, 0.0)``. Falls back to ``default_multiplier``
when the state/driver is missing or NaN.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from src.research.scaling.AffordabilityGated import AffordabilityGated
from src.research.scaling.InventoryZScoreGated import InventoryZScoreGated
from src.research.scaling.PEZScoreGated import PEZScoreGated
from src.research.scaling.RealRateZScoreGated import RealRateZScoreGated

EQUITY = 10_000.0
_R = pd.Series([0.0] * 10)  # placeholder recent_returns (scalers ignore it)


# =============================================================================
# PEZScoreGated  (equities — Shiller P/E z-score)
#   Bands: cape_z < -1.0 → 1.5x | < -0.5 → 1.2x | > 3.0 → 0.1x | > 2.0 → 0.3x
#   Default: 1.0x
# =============================================================================


def _pe_size(cape_z):
    """Helper: run PEZScoreGated.size with the given cape_z in state."""
    scaler = PEZScoreGated()
    state = None if cape_z is _MISSING else {"cape_z": cape_z}
    return scaler.size(
        equity=EQUITY, position_value=0.0, price=1.0,
        recent_returns=_R, state=state,
    )


_MISSING = object()  # sentinel for "omit driver from state"


def test_pe_deep_value_band():
    buy, sell = _pe_size(-1.5)
    assert buy == pytest.approx(EQUITY * 1.5)
    assert sell == 0.0


def test_pe_moderate_value_band():
    buy, sell = _pe_size(-0.7)
    assert buy == pytest.approx(EQUITY * 1.2)
    assert sell == 0.0


def test_pe_neutral_band():
    buy, sell = _pe_size(0.5)
    assert buy == pytest.approx(EQUITY * 1.0)
    assert sell == 0.0


def test_pe_expensive_band():
    buy, sell = _pe_size(2.5)
    assert buy == pytest.approx(EQUITY * 0.3)
    assert sell == 0.0


def test_pe_manic_band():
    buy, sell = _pe_size(4.0)
    assert buy == pytest.approx(EQUITY * 0.1)
    assert sell == 0.0


def test_pe_boundary_minus_1_0_is_not_deep():
    """cape_z == -1.0 is NOT < -1.0, so falls to the -0.5 band (1.2x)."""
    buy, _ = _pe_size(-1.0)
    assert buy == pytest.approx(EQUITY * 1.2)


def test_pe_boundary_minus_0_5_is_neutral():
    """cape_z == -0.5 is NOT < -0.5, so falls to neutral (1.0x)."""
    buy, _ = _pe_size(-0.5)
    assert buy == pytest.approx(EQUITY * 1.0)


def test_pe_boundary_2_0_is_neutral():
    """cape_z == 2.0 is NOT > 2.0, so falls to neutral (1.0x)."""
    buy, _ = _pe_size(2.0)
    assert buy == pytest.approx(EQUITY * 1.0)


def test_pe_boundary_3_0_is_expensive_not_manic():
    """cape_z == 3.0 is NOT > 3.0, so falls to the 2.0 band (0.3x)."""
    buy, _ = _pe_size(3.0)
    assert buy == pytest.approx(EQUITY * 0.3)


def test_pe_missing_state_returns_default():
    scaler = PEZScoreGated()
    buy, sell = scaler.size(
        EQUITY, 0.0, 1.0, _R, state=None,
    )
    assert buy == pytest.approx(EQUITY * 1.0)
    assert sell == 0.0


def test_pe_missing_driver_returns_default():
    """Empty state dict (no cape_z key) → default multiplier."""
    scaler = PEZScoreGated()
    buy, sell = scaler.size(
        EQUITY, 0.0, 1.0, _R, state={},
    )
    assert buy == pytest.approx(EQUITY * 1.0)
    assert sell == 0.0


def test_pe_nan_driver_returns_default():
    buy, _ = _pe_size(float("nan"))
    assert buy == pytest.approx(EQUITY * 1.0)


def test_pe_default_params_not_hardcoded_if_elif():
    """Metis finding: bands must live in default_params, not inline if/elif."""
    params = PEZScoreGated.default_params
    assert "bands" in params
    assert isinstance(params["bands"], tuple)
    assert len(params["bands"]) >= 4  # at least 4 band entries
    assert params["driver_field"] == "cape_z"
    assert params["default_multiplier"] == 1.0


# =============================================================================
# RealRateZScoreGated  (gold — 10y real yield z-score)
#   Bands: real_yield_10y_z > 1.5 → 1.5x | < -1.0 → 0.5x
#   Default: 1.0x
# =============================================================================


def _rr_size(real_z):
    scaler = RealRateZScoreGated()
    state = None if real_z is _MISSING else {"real_yield_10y_z": real_z}
    return scaler.size(
        equity=EQUITY, position_value=0.0, price=1.0,
        recent_returns=_R, state=state,
    )


def test_rr_high_real_yield_band():
    """High real yields → mean-revert down → bullish gold → 1.5x."""
    buy, sell = _rr_size(2.0)
    assert buy == pytest.approx(EQUITY * 1.5)
    assert sell == 0.0


def test_rr_low_real_yield_band():
    """Low real yields → less gold upside → 0.5x."""
    buy, sell = _rr_size(-1.5)
    assert buy == pytest.approx(EQUITY * 0.5)
    assert sell == 0.0


def test_rr_neutral_band():
    buy, sell = _rr_size(0.0)
    assert buy == pytest.approx(EQUITY * 1.0)
    assert sell == 0.0


def test_rr_boundary_1_5_is_neutral():
    """real_z == 1.5 is NOT > 1.5, so neutral (1.0x)."""
    buy, _ = _rr_size(1.5)
    assert buy == pytest.approx(EQUITY * 1.0)


def test_rr_boundary_minus_1_0_is_neutral():
    """real_z == -1.0 is NOT < -1.0, so neutral (1.0x)."""
    buy, _ = _rr_size(-1.0)
    assert buy == pytest.approx(EQUITY * 1.0)


def test_rr_missing_state_returns_default():
    scaler = RealRateZScoreGated()
    buy, sell = scaler.size(EQUITY, 0.0, 1.0, _R, state=None)
    assert buy == pytest.approx(EQUITY * 1.0)
    assert sell == 0.0


def test_rr_missing_driver_returns_default():
    scaler = RealRateZScoreGated()
    buy, sell = scaler.size(EQUITY, 0.0, 1.0, _R, state={})
    assert buy == pytest.approx(EQUITY * 1.0)
    assert sell == 0.0


def test_rr_nan_driver_returns_default():
    buy, _ = _rr_size(float("nan"))
    assert buy == pytest.approx(EQUITY * 1.0)


def test_rr_default_params_structure():
    params = RealRateZScoreGated.default_params
    assert "bands" in params
    assert params["driver_field"] == "real_yield_10y_z"
    assert params["default_multiplier"] == 1.0


# =============================================================================
# InventoryZScoreGated  (oil — inventory z-score)
#   Bands: oil_inventories_z < -1.0 → 1.2x | > 1.0 → 0.3x
#   Default: 1.0x
# =============================================================================


def _inv_size(inv_z):
    scaler = InventoryZScoreGated()
    state = None if inv_z is _MISSING else {"oil_inventories_z": inv_z}
    return scaler.size(
        equity=EQUITY, position_value=0.0, price=1.0,
        recent_returns=_R, state=state,
    )


def test_inv_drawing_band():
    """Drawing inventories (z < -1.0) → bullish oil → 1.2x."""
    buy, sell = _inv_size(-1.5)
    assert buy == pytest.approx(EQUITY * 1.2)
    assert sell == 0.0


def test_inv_building_band():
    """Building inventories (z > 1.0) → bearish oil → 0.3x."""
    buy, sell = _inv_size(1.5)
    assert buy == pytest.approx(EQUITY * 0.3)
    assert sell == 0.0


def test_inv_neutral_band():
    buy, sell = _inv_size(0.0)
    assert buy == pytest.approx(EQUITY * 1.0)
    assert sell == 0.0


def test_inv_boundary_minus_1_0_is_neutral():
    buy, _ = _inv_size(-1.0)
    assert buy == pytest.approx(EQUITY * 1.0)


def test_inv_boundary_1_0_is_neutral():
    buy, _ = _inv_size(1.0)
    assert buy == pytest.approx(EQUITY * 1.0)


def test_inv_missing_state_returns_default():
    scaler = InventoryZScoreGated()
    buy, sell = scaler.size(EQUITY, 0.0, 1.0, _R, state=None)
    assert buy == pytest.approx(EQUITY * 1.0)
    assert sell == 0.0


def test_inv_missing_driver_returns_default():
    scaler = InventoryZScoreGated()
    buy, sell = scaler.size(EQUITY, 0.0, 1.0, _R, state={})
    assert buy == pytest.approx(EQUITY * 1.0)
    assert sell == 0.0


def test_inv_nan_driver_returns_default():
    buy, _ = _inv_size(float("nan"))
    assert buy == pytest.approx(EQUITY * 1.0)


def test_inv_default_params_structure():
    params = InventoryZScoreGated.default_params
    assert "bands" in params
    assert params["driver_field"] == "oil_inventories_z"
    assert params["default_multiplier"] == 1.0


# =============================================================================
# AffordabilityGated  (housing — affordability index, higher = better)
#   Bands: affordability_index > 1.0 → 1.5x | < -1.0 → 0.5x
#   Default: 1.0x
# =============================================================================


def _aff_size(aff):
    scaler = AffordabilityGated()
    state = None if aff is _MISSING else {"affordability_index": aff}
    return scaler.size(
        equity=EQUITY, position_value=0.0, price=1.0,
        recent_returns=_R, state=state,
    )


def test_aff_great_affordability_band():
    """Affordability well above mean → buy aggressively → 1.5x."""
    buy, sell = _aff_size(1.5)
    assert buy == pytest.approx(EQUITY * 1.5)
    assert sell == 0.0


def test_aff_poor_affordability_band():
    """Affordability well below mean → wait → 0.5x."""
    buy, sell = _aff_size(-1.5)
    assert buy == pytest.approx(EQUITY * 0.5)
    assert sell == 0.0


def test_aff_neutral_band():
    buy, sell = _aff_size(0.0)
    assert buy == pytest.approx(EQUITY * 1.0)
    assert sell == 0.0


def test_aff_boundary_1_0_is_neutral():
    buy, _ = _aff_size(1.0)
    assert buy == pytest.approx(EQUITY * 1.0)


def test_aff_boundary_minus_1_0_is_neutral():
    buy, _ = _aff_size(-1.0)
    assert buy == pytest.approx(EQUITY * 1.0)


def test_aff_missing_state_returns_default():
    scaler = AffordabilityGated()
    buy, sell = scaler.size(EQUITY, 0.0, 1.0, _R, state=None)
    assert buy == pytest.approx(EQUITY * 1.0)
    assert sell == 0.0


def test_aff_missing_driver_returns_default():
    scaler = AffordabilityGated()
    buy, sell = scaler.size(EQUITY, 0.0, 1.0, _R, state={})
    assert buy == pytest.approx(EQUITY * 1.0)
    assert sell == 0.0


def test_aff_nan_driver_returns_default():
    buy, _ = _aff_size(float("nan"))
    assert buy == pytest.approx(EQUITY * 1.0)


def test_aff_default_params_structure():
    params = AffordabilityGated.default_params
    assert "bands" in params
    assert params["driver_field"] == "affordability_index"
    assert params["default_multiplier"] == 1.0


# =============================================================================
# Shared: multiplier range [0.1, 2.0] honored across all 4 scalers
# =============================================================================


@pytest.mark.parametrize(
    "scaler_cls",
    [PEZScoreGated, RealRateZScoreGated, InventoryZScoreGated, AffordabilityGated],
)
def test_multiplier_floor_and_cap_in_defaults(scaler_cls):
    """Every scaler must declare a multiplier floor/cap respecting [0.1, 2.0]."""
    p = scaler_cls.default_params
    assert p["multiplier_floor"] >= 0.0
    assert p["multiplier_cap"] <= 2.0 + 1e-9
    assert p["multiplier_cap"] > p["multiplier_floor"]


@pytest.mark.parametrize(
    "scaler_cls",
    [PEZScoreGated, RealRateZScoreGated, InventoryZScoreGated, AffordabilityGated],
)
def test_extends_scaling_model_abc(scaler_cls):
    from src.research.scaling import ScalingModel
    assert issubclass(scaler_cls, ScalingModel)


@pytest.mark.parametrize(
    "scaler_cls",
    [PEZScoreGated, RealRateZScoreGated, InventoryZScoreGated, AffordabilityGated],
)
def test_has_nonempty_name_and_description(scaler_cls):
    assert scaler_cls.name
    assert scaler_cls.description
