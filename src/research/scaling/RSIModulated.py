"""RSI-modulated position-scaling model.

Multiplies the base buy size by a weight derived from RSI(14):
  - RSI < 30  → 1.5×  (oversold, buy more)
  - RSI < 50  → 1.0×  (neutral)
  - RSI < 70  → 0.75× (getting overbought)
  - RSI ≥ 70  → 0.5×  (overbought, buy less)

Only modulates buys — always returns 0 sell USD.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

import numpy as np
import pandas as pd

from src.research.scaling import InvalidParamsError, ScalingModel


@dataclass
class RSIModulated(ScalingModel):
    name: ClassVar[str] = "RSIModulated"
    description: ClassVar[str] = (
        "Multiplies buy size by RSI(14)-derived weight: "
        "oversold → buy more, overbought → buy less."
    )
    default_params: ClassVar[dict[str, Any]] = {
        "lookback": 14,
        "base_buy_multiplier": 1.0,
    }

    def validate_params(self, params: dict[str, Any]) -> None:
        if params.get("lookback", 14) <= 0:
            raise InvalidParamsError(
                f"lookback must be > 0, got {params['lookback']}"
            )
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
        base = self.params["base_buy_multiplier"]

        rsi: float | None = None
        if state is not None:
            rsi = state.get("rsi_14")

        if rsi is None or (isinstance(rsi, float) and np.isnan(rsi)):
            weight = 1.0
        elif rsi < 30:
            weight = 1.5
        elif rsi < 50:
            weight = 1.0
        elif rsi < 70:
            weight = 0.75
        else:
            weight = 0.5

        return (base * weight, 0.0)
