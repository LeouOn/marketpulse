"""On-chain gated scaling model.

Multiplies buy size by MVRV Z-score bands. Low MVRV (cheap) = buy more,
high MVRV (expensive) = buy less.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

import pandas as pd

from src.research.scaling import InvalidParamsError, ScalingModel


@dataclass
class OnChainGated(ScalingModel):
    """Gates buy size by on-chain MVRV Z-score bands.

    Low MVRV (undervalued) → higher multiplier, high MVRV (overvalued) →
    lower multiplier. Falls back to 1.0× when MVRV data is unavailable.
    """

    name: ClassVar[str] = "OnChainGated"
    description: ClassVar[str] = (
        "Multiplies buy size by on-chain MVRV Z-score bands. "
        "Low MVRV (cheap) = buy more, high MVRV (expensive) = buy less."
    )
    default_params: ClassVar[dict[str, Any]] = {
        "base_buy_multiplier": 500.0,
        "mvrv_bands": [-1.0, 0.0, 1.5, 3.0, 5.0],
        "mvrv_multipliers": [2.0, 1.5, 1.0, 0.75, 0.5],
    }

    def validate_params(self, params: dict[str, Any]) -> None:
        if params.get("base_buy_multiplier", 500.0) <= 0:
            raise InvalidParamsError(
                f"base_buy_multiplier must be > 0, got {params['base_buy_multiplier']}"
            )
        bands = params.get("mvrv_bands", [-1.0, 0.0, 1.5, 3.0, 5.0])
        mults = params.get("mvrv_multipliers", [2.0, 1.5, 1.0, 0.75, 0.5])
        if len(bands) != len(mults) or len(bands) == 0:
            raise InvalidParamsError(
                f"mvrv_bands and mvrv_multipliers must be same non-zero length, "
                f"got {len(bands)} bands and {len(mults)} multipliers"
            )

    def size(
        self,
        equity: float,
        position_value: float,
        price: float,
        recent_returns: pd.Series,
        state: dict[str, Any] | None = None,
    ) -> tuple[float, float]:
        base = float(self.params["base_buy_multiplier"])
        bands = list(self.params["mvrv_bands"])
        mults = list(self.params["mvrv_multipliers"])
        mvrv_z = (state or {}).get("mvrv_z")

        if mvrv_z is None or pd.isna(mvrv_z):
            return (base * 1.0, 0.0)

        # Find the first band where mvrv_z < band value
        for i, band in enumerate(bands):
            if mvrv_z < band:
                return (base * mults[i], 0.0)

        # Above all bands — use the last multiplier
        return (base * mults[-1], 0.0)
