"""RecurringFundingDCA strategy — income-based DCA via periodic deposits.

Signals buy days to pair with the backtest engine's ``inflows`` parameter.
On each buy day, returns ``1.0`` (spend the deposit). On other days, returns
``NaN`` (skip). Pair with ``inflows=[{"every_n_bars": 30, "amount_usd": 500}]``
and a scaling model like ``FixedDollar(amount_usd=500)`` for income-based DCA.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

import numpy as np
import pandas as pd

from src.research.strategies import InvalidParamsError, Strategy


@dataclass
class RecurringFundingDCA(Strategy):
    """Signals buy days to pair with backtest inflows.

    On each buy day (every ``every_n_bars`` bars), returns ``1.0`` so the
    engine executes a buy. On other days, returns ``NaN`` so the engine
    skips rebalancing. The actual cash deposit comes from the engine's
    ``inflows`` parameter, not from the strategy itself.

    Typical usage::

        run_backtest(
            df,
            strategy=RecurringFundingDCA(params={"every_n_bars": 30}),
            scaling=FixedDollar(params={"amount_usd": 500}),
            starting_equity=0,
            inflows=[{"every_n_bars": 30, "amount_usd": 500}],
        )
    """

    name: ClassVar[str] = "RecurringFundingDCA"
    description: ClassVar[str] = (
        "Signals buy days to pair with backtest inflows. On each buy day, "
        "returns 1.0 (spend the deposit). On other days, returns NaN (skip). "
        "Pair with inflows=[{\"every_n_bars\": 30, \"amount_usd\": 500}] "
        "for income-based DCA."
    )
    default_params: ClassVar[dict[str, Any]] = {"every_n_bars": 30}

    def validate_params(self, params: dict[str, Any]) -> None:
        if params.get("every_n_bars", 1) <= 0:
            raise InvalidParamsError(
                f"every_n_bars must be > 0, got {params['every_n_bars']}"
            )

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        every = max(1, int(self.params["every_n_bars"]))
        signal = np.full(len(df), np.nan, dtype=float)
        signal[::every] = 1.0
        return pd.Series(signal, index=df.index)
