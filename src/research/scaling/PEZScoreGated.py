"""CAPE z-score gated scaling model for equities.

Reads a pre-computed Shiller P/E (CAPE) z-score from ``state["cape_z"]``
and scales equity accumulation accordingly:

  - ``cape_z < -1.0``  → 1.5x  (cheap equities — accumulate faster)
  - ``cape_z < -0.5``  → 1.2x  (moderately cheap)
  - ``cape_z > 3.0``   → 0.1x  (manic valuations — minimal accumulation)
  - ``cape_z > 2.0``   → 0.3x  (expensive)
  - otherwise          → 1.0x  (neutral)

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
class PEZScoreGated(ScalingModel):
    """Equity accumulation scaled by CAPE z-score (cheap = buy more)."""

    name: ClassVar[str] = "PEZScoreGated"
    description: ClassVar[str] = (
        "Scales equity accumulation by Shiller P/E (CAPE) z-score. "
        "Cheap equities (cape_z < -1.0) get 1.5x, manic (cape_z > 3.0) "
        "get 0.1x. Reads cape_z from state; bands are parameterized."
    )
    default_params: ClassVar[dict[str, Any]] = {
        "driver_field": "cape_z",
        "default_multiplier": 1.0,
        "multiplier_floor": 0.1,
        "multiplier_cap": 2.0,
        # Bands evaluated in order; first match wins.
        # Each entry: (comparator, threshold, multiplier)
        # For "lt" bands, order most-extreme (smallest threshold) first.
        # For "gt" bands, order most-extreme (largest threshold) first.
        "bands": (
            ("lt", -1.0, 1.5),  # deep value
            ("lt", -0.5, 1.2),  # moderate value
            ("gt", 3.0, 0.1),   # manic
            ("gt", 2.0, 0.3),   # expensive
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
