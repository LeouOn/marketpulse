"""Affordability gated scaling model for housing.

Reads a pre-computed affordability index from
``state["affordability_index"]`` (higher = better affordability, already
standardized so that +/-1.0 ≈ one standard deviation from the rolling
mean) and scales equity accumulation accordingly:

  - ``affordability_index > 1.0``   → 1.5x  (great affordability —
                                            buy aggressively)
  - ``affordability_index < -1.0``  → 0.5x  (poor affordability — wait)
  - otherwise                       → 1.0x  (neutral)

The scaler does **not** standardize the index or compute the rolling
mean — it reads a pre-standardized value that the engine injects via
the ``state`` dict (IndicatorProvider extension, T16+). All thresholds
and multipliers live in ``default_params`` (no hardcoded if/elif —
Metis finding on the legacy ``MayerMultipleGated``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

import pandas as pd

from src.research.scaling import InvalidParamsError, ScalingModel


@dataclass
class AffordabilityGated(ScalingModel):
    """Housing accumulation scaled by affordability index."""

    name: ClassVar[str] = "AffordabilityGated"
    description: ClassVar[str] = (
        "Scales housing accumulation by a pre-standardized affordability "
        "index (higher = better). Great affordability (>1.0 std above "
        "mean) → 1.5x; poor (<-1.0 std below mean) → 0.5x. "
        "Reads affordability_index from state; bands are parameterized."
    )
    default_params: ClassVar[dict[str, Any]] = {
        "driver_field": "affordability_index",
        "default_multiplier": 1.0,
        "multiplier_floor": 0.1,
        "multiplier_cap": 2.0,
        # Bands evaluated in order; first match wins.
        "bands": (
            ("gt", 1.0, 1.5),    # great affordability → buy aggressively
            ("lt", -1.0, 0.5),   # poor affordability → wait
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
