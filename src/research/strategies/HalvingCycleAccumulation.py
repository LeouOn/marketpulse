"""HalvingCycleAccumulation strategy — cycle-aware accumulator.

Targets higher BTC allocation in months 6-18 post-halving (bull phase),
lower in months 30-48 (cycle peak), and interpolates between.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

import numpy as np
import pandas as pd

from src.research.strategies import InvalidParamsError, Strategy


@dataclass
class HalvingCycleAccumulation(Strategy):
    """Cycle-aware accumulator: modulates accumulation speed based on BTC's
    4-year halving cycle.

    * Months 0-6 post-halving  → conservative (early post-halving)
    * Months 6-18               → aggressive  (bull phase)
    * Months 18-30              → linear ramp from aggressive → conservative
    * Months 30+                → conservative (cycle peak / bear phase)
    * No past halving found     → conservative
    """

    name: ClassVar[str] = "HalvingCycleAccumulation"
    description: ClassVar[str] = (
        "Cycle-aware accumulator: target higher BTC allocation in months 6-18 "
        "post-halving (bull phase), lower in months 30-48 (cycle peak), "
        "interpolate between."
    )
    default_params: ClassVar[dict[str, Any]] = {
        "halving_dates": [
            pd.Timestamp("2012-11-28"),
            pd.Timestamp("2016-07-09"),
            pd.Timestamp("2020-05-11"),
            pd.Timestamp("2024-04-19"),
            pd.Timestamp("2028-04-15"),
        ],
        "aggressive_frac": 0.9,
        "conservative_frac": 0.3,
    }

    def validate_params(self, params: dict[str, Any]) -> None:
        dates = params.get("halving_dates", [])
        if not dates or len(dates) == 0:
            raise InvalidParamsError(
                "halving_dates must contain at least one date, got []"
            )
        agg = params.get("aggressive_frac", 0.9)
        con = params.get("conservative_frac", 0.3)
        if not (0 <= agg <= 1):
            raise InvalidParamsError(
                f"aggressive_frac must be in [0, 1], got {agg}"
            )
        if not (0 <= con <= 1):
            raise InvalidParamsError(
                f"conservative_frac must be in [0, 1], got {con}"
            )
        if agg <= con:
            raise InvalidParamsError(
                f"aggressive_frac ({agg}) must be > conservative_frac ({con})"
            )

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """Return a pd.Series indexed like ``df`` with values in [0, 1].

        For each bar, find the most recent halving date <= bar's timestamp
        and compute months since that halving to determine the signal.
        """
        params = self.params
        halving_dates = sorted(params["halving_dates"])
        aggressive_frac = float(params["aggressive_frac"])
        conservative_frac = float(params["conservative_frac"])

        n = len(df)
        signal = np.full(n, conservative_frac, dtype=float)

        for i in range(n):
            ts = pd.Timestamp(df["ts"].iloc[i])

            # Find the most recent halving date <= ts
            last_halving: pd.Timestamp | None = None
            for hd in reversed(halving_dates):
                if hd <= ts:
                    last_halving = hd
                    break

            if last_halving is None:
                # No past halving found → conservative
                signal[i] = conservative_frac
                continue

            months_since = (ts - last_halving).days / 30.44

            if months_since < 6:
                signal[i] = conservative_frac
            elif months_since <= 18:
                signal[i] = aggressive_frac
            elif months_since <= 30:
                # Linear interpolation from aggressive → conservative
                frac = (months_since - 18) / 12.0
                signal[i] = aggressive_frac + frac * (
                    conservative_frac - aggressive_frac
                )
            else:
                signal[i] = conservative_frac

        return pd.Series(signal, index=df.index)
