"""Inventory z-score gated scaling model for oil.

Reads a pre-computed oil-inventory z-score from
``state["oil_inventories_z"]`` and scales equity accumulation accordingly:

  - ``oil_inventories_z < -1.0``  → 1.2x  (drawing inventories —
                                          bullish for oil)
  - ``oil_inventories_z > 1.0``   → 0.3x  (building inventories —
                                          bearish for oil)
  - otherwise                     → 1.0x  (neutral)

The scaler does **not** compute the z-score — it reads a value that the
engine injects via the ``state`` dict (IndicatorProvider extension, T16+).
All thresholds and multipliers live in ``default_params`` (no hardcoded
if/elif — Metis finding on the legacy ``MayerMultipleGated``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

import pandas as pd

from src.research.scaling import InvalidParamsError, ScalingModel


@dataclass
class InventoryZScoreGated(ScalingModel):
    """Oil accumulation scaled by inventory z-score."""

    name: ClassVar[str] = "InventoryZScoreGated"
    description: ClassVar[str] = (
        "Scales oil accumulation by inventory z-score. "
        "Drawing inventories (z < -1.0) are bullish → 1.2x; "
        "building inventories (z > 1.0) are bearish → 0.3x. "
        "Reads oil_inventories_z from state; bands are parameterized."
    )
    default_params: ClassVar[dict[str, Any]] = {
        "driver_field": "oil_inventories_z",
        "default_multiplier": 1.0,
        "multiplier_floor": 0.1,
        "multiplier_cap": 2.0,
        # Bands evaluated in order; first match wins.
        "bands": (
            ("lt", -1.0, 1.2),  # drawing → bullish
            ("gt", 1.0, 0.3),   # building → bearish
        ),
    }

    def validate_params(self, params: dict[str, Any]) -> None:
        floor = float(params.get("multiplier_floor", 0.1))
        cap = float(params.get("multiplier_cap", 2.0))
        if floor < 0:
            raise InvalidParamsError(
                f"multiplier_floor must be >= 0, got {floor}"
            )
        if cap <= floor:
            raise InvalidParamsError(
                f"multiplier_cap ({cap}) must be > multiplier_floor ({floor})"
            )
        if not params.get("bands"):
            raise InvalidParamsError("bands must be a non-empty tuple")
        if not params.get("driver_field"):
            raise InvalidParamsError("driver_field must be a non-empty string")

    def size(
        self,
        equity: float,
        position_value: float,
        price: float,
        recent_returns: pd.Series,
        state: dict[str, Any] | None = None,
    ) -> tuple[float, float]:
        default_mult = float(self.params["default_multiplier"])
        floor = float(self.params["multiplier_floor"])
        cap = float(self.params["multiplier_cap"])
        driver_field = self.params["driver_field"]
        bands = self.params["bands"]

        mult = default_mult
        if state is not None:
            driver_value = state.get(driver_field)
            if driver_value is not None and not pd.isna(driver_value):
                for comparator, threshold, band_mult in bands:
                    hit = (
                        driver_value < threshold
                        if comparator == "lt"
                        else driver_value > threshold
                    )
                    if hit:
                        mult = float(band_mult)
                        break

        mult = max(floor, min(mult, cap))
        return (equity * mult, 0.0)
