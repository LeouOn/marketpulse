"""Sentiment-modulated position scaling model.

Uses the Crypto Fear & Greed Index (FGI) to modulate buy size:
  - Extreme fear  (FGI < 25) → buy MORE  (1.5× base)
  - Fear          (FGI < 45) → buy NORM  (1.0×)
  - Neutral       (FGI < 55) → buy LESS  (0.75×)
  - Greed         (FGI < 75) → buy LESS  (0.5×)
  - Extreme greed (FGI ≥ 75) → buy MUCH LESS (0.25×)

If ``state["fgi_value"]`` is missing or NaN, falls back to 1.0× (no change).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

import numpy as np
import pandas as pd

from src.research.scaling import InvalidParamsError, ScalingModel


@dataclass
class SentimentModulated(ScalingModel):
    """Modulates buy size by Fear & Greed Index.

    Extreme fear (FGI<25) → 1.5x buy, extreme greed (FGI≥75) → 0.25x buy.
    """

    name: ClassVar[str] = "SentimentModulated"
    description: ClassVar[str] = (
        "Modulates buy size by Fear & Greed Index. "
        "Extreme fear (FGI<25) → 1.5x buy, extreme greed (FGI≥75) → 0.25x buy."
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
        base_mult = float(self.params["base_buy_multiplier"])

        # Read FGI from state; fall back to neutral (1.0×) if absent/NaN.
        fgi: float | None = None
        if state is not None:
            raw = state.get("fgi_value")
            if raw is not None:
                try:
                    fgi = float(raw)
                except (TypeError, ValueError):
                    fgi = None

        if fgi is None or (isinstance(fgi, float) and np.isnan(fgi)):
            multiplier = 1.0
        elif fgi < 25:
            multiplier = 1.5
        elif fgi < 45:
            multiplier = 1.0
        elif fgi < 55:
            multiplier = 0.75
        elif fgi < 75:
            multiplier = 0.5
        else:
            multiplier = 0.25

        buy_usd = equity * base_mult * multiplier
        return buy_usd, 0.0
