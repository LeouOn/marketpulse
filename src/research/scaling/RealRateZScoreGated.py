"""Real-rate z-score gated scaling model for gold.

Reads a pre-computed 10-year real-yield z-score from
``state["real_yield_10y_z"]`` and scales equity accumulation accordingly:

  - ``real_yield_10y_z > 1.5``  → 1.5x  (real yields unusually high —
                                        mean-revert down → gold up)
  - ``real_yield_10y_z < -1.0`` → 0.5x  (real yields unusually low —
                                        less upside for gold)
  - otherwise                   → 1.0x  (neutral)

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
class RealRateZScoreGated(ScalingModel):
    """Gold accumulation scaled by 10y real-yield z-score."""

    name: ClassVar[str] = "RealRateZScoreGated"
    description: ClassVar[str] = (
        "Scales gold accumulation by 10-year real-yield z-score. "
        "Unusually high real yields (>1.5z) imply mean-reversion down "
        "(bullish gold) → 1.5x; unusually low (<-1.0z) → 0.5x. "
        "Reads real_yield_10y_z from state; bands are parameterized."
    )
    default_params: ClassVar[dict[str, Any]] = {
        "driver_field": "real_yield_10y_z",
        "default_multiplier": 1.0,
        "multiplier_floor": 0.1,
        "multiplier_cap": 2.0,
        # Bands evaluated in order; first match wins.
        "bands": (
            ("gt", 1.5, 1.5),   # high real yields → gold bullish
            ("lt", -1.0, 0.5),  # low real yields → less upside
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
