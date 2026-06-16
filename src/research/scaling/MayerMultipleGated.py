"""Mayer Multiple gated scaling model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

import pandas as pd

from src.research.scaling import InvalidParamsError, ScalingModel


@dataclass
class MayerMultipleGated(ScalingModel):
    """Gates buy size by Mayer Multiple (price / SMA 200).

    Deep value (< 0.8)  → 1.5×, overheated (≥ 2.4) → 0.5×.
    """

    name: ClassVar[str] = "MayerMultipleGated"
    description: ClassVar[str] = (
        "Gates buy size by Mayer Multiple (price/SMA200). "
        "Deep value (<0.8) → 1.5x, overheated (>2.4) → 0.5x."
    )
    default_params: ClassVar[dict[str, Any]] = {"base_buy_multiplier": 1.0}

    def validate_params(self, params: dict[str, Any]) -> None:
        if params.get("base_buy_multiplier", 1.0) <= 0:
            raise InvalidParamsError(
                f"base_buy_multiplier must be > 0, got {params['base_buy_multiplier']}"
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
        mayer = (state or {}).get("mayer_multiple")

        if mayer is None or pd.isna(mayer):
            multiplier = 1.0
        elif mayer < 0.8:
            multiplier = 1.5
        elif mayer < 1.0:
            multiplier = 1.25
        elif mayer < 1.5:
            multiplier = 1.0
        elif mayer < 2.4:
            multiplier = 0.75
        else:
            multiplier = 0.5

        return (base * multiplier, 0.0)
