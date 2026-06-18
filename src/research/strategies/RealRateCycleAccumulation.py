"""Gold accumulation strategy driven by the 10Y real-yield cycle.

Driver: ``real_yield_10y`` (FRED series ``DFII10`` -- 10-Year Treasury
Inflation-Indexed Security Rate, constant maturity). Values are in
PERCENT (a quote of 2.5 means 2.5% real yield), so the 1Y change in
percentage points is simply ``current - prior`` -- no scaling required.

Economic rationale (locked v1, see .omo/plans W4 T16):
    Lower real yields reduce the opportunity cost of holding non-yielding
    gold, so a *falling* real yield regime is bullish for gold -- we
    accumulate FASTER (1.5x).  A *rising* real yield regime makes cash
    and bonds more attractive vs. gold, so we accumulate SLOWER (0.3x).
    In the neutral band we accumulate at the standard 1.0x DCA cadence.

Phase thresholds (v1 defaults, LOCKED -- do not tune without a fresh
W3 backrun + a notepad decision):
    - 1Y change < -0.5pp  -> falling fast  -> intensity 1.5
    - 1Y change > +0.5pp  -> rising fast   -> intensity 0.3
    - otherwise           -> neutral       -> intensity 1.0

Spec: .omo/plans/multi-asset-macro-research-lab.md W4 T16 (L1364-1395).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

import pandas as pd

from src.research.strategies.cycle_base import CycleAccumulation


@dataclass
class RealRateCycleAccumulation(CycleAccumulation):
    """Cycle-aware gold accumulator driven by 10Y real yields (DFII10).

    The ``real_yield_10y`` column comes from
    ``MacroFactorProvider.load_factors`` (T11).  When it's missing, the
    strategy returns the neutral 1.0 intensity (DCA fallback).
    """

    name: ClassVar[str] = "RealRateCycleAccumulation"
    description: ClassVar[str] = (
        "Real-rate-cycle gold accumulation: faster when real yields are "
        "falling (bullish for non-yielding gold), slower when rising. "
        "Driver: 10Y real yield (FRED DFII10)."
    )
    default_params: ClassVar[dict[str, Any]] = {
        # 1Y of NYSE trading days. Gold is on the NYSE calendar (T10).
        "lookback_days": 252,
        # All thresholds in PERCENTAGE POINTS (DFII10 is already in %).
        "falling_threshold_pp": -0.5,
        "rising_threshold_pp": 0.5,
        # Intensities are the v1 LOCKED values; see module docstring.
        "falling_intensity": 1.5,
        "rising_intensity": 0.3,
        "neutral_intensity": 1.0,
    }

    def _cycle_phase(
        self, timestamp: pd.Timestamp, factor_df: pd.DataFrame
    ) -> float:
        """Return the gold accumulation intensity at ``timestamp``.

        Implements the 3-tier phase logic from the v1 spec.  All fallback
        paths return ``neutral_intensity`` (1.0) -- never raise.
        """
        p = self.default_params
        col_name = "real_yield_10y"

        if col_name not in factor_df.columns:
            return float(p["neutral_intensity"])

        col = factor_df[col_name]

        # --- "current" value: last non-NaN at or before timestamp -----
        try:
            current = col.asof(timestamp)
        except (KeyError, TypeError):
            return float(p["neutral_intensity"])
        if current is None or pd.isna(current):
            return float(p["neutral_intensity"])

        # --- "prior" value: ~1Y earlier in the same factor frame -----
        prior_mask = factor_df.index <= timestamp
        prior_slice = col[prior_mask]
        lookback = int(p["lookback_days"])
        # Need at least half a year of history to call it a "1Y change".
        if len(prior_slice) < max(1, lookback // 2):
            return float(p["neutral_intensity"])

        if len(prior_slice) >= lookback:
            prior = prior_slice.iloc[-lookback]
        else:
            # Not enough history for a full 1Y lookback; use the earliest
            # available row as the best proxy.
            prior = prior_slice.iloc[0]

        if prior is None or pd.isna(prior):
            return float(p["neutral_intensity"])

        # DFII10 is already in PERCENT, so the raw difference IS in pp.
        change_pp = float(current) - float(prior)

        if change_pp < float(p["falling_threshold_pp"]):
            return float(p["falling_intensity"])
        if change_pp > float(p["rising_threshold_pp"]):
            return float(p["rising_intensity"])
        return float(p["neutral_intensity"])
