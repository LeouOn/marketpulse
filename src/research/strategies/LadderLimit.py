"""LadderLimit strategy — 4-tier limit ladder with cooldowns.

Buys at predefined percentage drops from a rolling 3-month high.
Each tier has an independent 30-day cooldown to prevent re-triggering.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

import pandas as pd

from src.research.strategies import InvalidParamsError, Strategy


@dataclass
class LadderLimit(Strategy):
    """4-tier limit ladder: buys at -5%, -10%, -15%, -20% drops from rolling
    3-month high with 30-day cooldowns per tier.

    The strategy returns ``1.0`` on any bar where a tier fires (independent
    cooldowns mean multiple tiers can fire on the same bar).  Position sizing
    is handled by composing with a ScalingModel that reads
    ``tranche_amounts_usd``.
    """

    name: ClassVar[str] = "LadderLimit"
    description: ClassVar[str] = (
        "4-tier limit ladder: buys at -5%, -10%, -15%, -20% drops from "
        "rolling 3-month high with 30-day cooldowns."
    )
    default_params: ClassVar[dict[str, Any]] = {
        "tranche_pcts": [-0.05, -0.10, -0.15, -0.20],
        "tranche_amounts_usd": [100, 200, 400, 800],
        "lookback_calendar_days": 90,
        "cooldown_calendar_days": 30,
    }

    def validate_params(self, params: dict[str, Any]) -> None:
        pcts = params.get("tranche_pcts", [])
        if not pcts or len(pcts) == 0:
            raise InvalidParamsError("tranche_pcts must be non-empty, got []")
        for p in pcts:
            if p >= 0:
                raise InvalidParamsError(
                    f"all tranche_pcts must be negative, got {p}"
                )
        cooldown = params.get("cooldown_calendar_days", 30)
        if cooldown <= 0:
            raise InvalidParamsError(
                f"cooldown_calendar_days must be > 0, got {cooldown}"
            )

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """Return a pd.Series indexed like ``df`` with values in {0.0, 1.0}.

        For each bar, check every tier (smallest drop first).  A tier fires
        when the price has dropped >= ``tranche_pcts[t]`` from the rolling
        high **and** that tier hasn't fired in the last
        ``cooldown_calendar_days`` days.
        """
        params = self.params
        tranche_pcts = sorted(params["tranche_pcts"])  # smallest drop first
        lookback = int(params["lookback_calendar_days"])
        cooldown_days = int(params["cooldown_calendar_days"])

        close = df["close"]
        rolling_high = close.rolling(window=lookback, min_periods=1).max()

        signal = pd.Series(0.0, index=df.index)

        # Per-tier cooldown tracker: {tier_idx: last_triggered_ts}
        last_triggered: dict[int, pd.Timestamp] = {}

        for i in range(len(df)):
            price = close.iloc[i]
            ts = pd.Timestamp(df["ts"].iloc[i])
            high = rolling_high.iloc[i]

            if pd.isna(price) or pd.isna(high) or high == 0:
                continue

            pct_drop = (price - high) / high  # negative when price < high

            for tier_idx, threshold in enumerate(tranche_pcts):
                if pct_drop <= threshold:
                    last_ts = last_triggered.get(tier_idx)
                    if last_ts is None or (ts - last_ts).days >= cooldown_days:
                        signal.iloc[i] = 1.0
                        last_triggered[tier_idx] = ts

        return signal
