"""Equity accumulation strategy driven by the NBER recession / CAPE cycle.

Driver (recession arm):
    ``sahm_recession`` -- the Sahm-rule recession indicator already
    produced by ``MacroFactorProvider.load_factors`` (T11, derived from
    the unemployment series).  It is a *boolean* column (True == the
    Sahm rule has fired, which only happens inside an NBER-dated
    recession).  We use it as a proxy for the canonical FRED ``USREC``
    series (monthly 0/1) because T11 doesn't ingest ``USREC`` directly;
    both signals coincide in practice (Sahm triggers slightly later but
    strictly *inside* every NBER recession since 1970).

Driver (valuation arm):
    Shiller CAPE (cyclically Adjusted Price/Earnings), stubbed as
    ``None`` for v1.  Sourcing CAPE properly requires either scraping
    multpl.com or ingesting Shiller's Excel workbook -- both are out of
    scope for W4 (see MUST NOT DO).  Until CAPE is wired in a future
    task, the mania branch (``cape_z > 2``) is unreachable and the
    strategy degrades gracefully to a 2-tier phase logic.

Economic rationale (locked v1, see .omo/plans W4 T17):
    Recessions are when equities get cheap -- "be greedy when others are
    fearful" -- so we accumulate FASTER (1.5x).  Late-stage mania bulls
    (CAPE z > 2) are when valuations are stretched and mean reversion is
    imminent, so we accumulate SLOWER (0.3x).  In the normal expansion
    regime we run slightly below the canonical DCA cadence (0.7x), since
    baseline equity DCAs tend to overshoot in expansions and we want to
    leave room to lean in harder when the next recession arrives.

Phase thresholds (v1 defaults, LOCKED -- do not tune without a fresh
W3 backrun + a notepad decision):
    - sahm_recession == True                -> recession       -> 1.5
    - expansion_late AND cape_z > 2 (v2)    -> mania           -> 0.3
    - otherwise                             -> normal          -> 0.7

Spec: .omo/plans/multi-asset-macro-research-lab.md W4 T17 (L1399-1426).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

import pandas as pd

from src.research.strategies.cycle_base import CycleAccumulation


@dataclass
class EarningsCycleAccumulation(CycleAccumulation):
    """Cycle-aware equity accumulator driven by NBER recession + CAPE.

    Reads ``factor_df["sahm_recession"]`` (boolean, from T11) as a proxy
    for FRED ``USREC``.  CAPE is stubbed as ``None`` for v1: the mania
    branch is intentionally unreachable until a future task wires a real
    CAPE source (TODO: see module docstring).

    When the Sahm column is missing, the strategy returns the normal
    accumulation intensity (0.7) -- never raises.
    """

    name: ClassVar[str] = "EarningsCycleAccumulation"
    description: ClassVar[str] = (
        "Equity accumulation driven by NBER recession + CAPE valuation regime"
    )
    default_params: ClassVar[dict[str, Any]] = {
        "recession_intensity": 1.5,
        "mania_intensity": 0.3,
        "normal_intensity": 0.7,
        "cape_z_mania_threshold": 2.0,
    }

    def _cycle_phase(
        self, timestamp: pd.Timestamp, factor_df: pd.DataFrame
    ) -> float:
        """Return the equity accumulation intensity at ``timestamp``.

        Implements the v1 phase logic.  All fallback paths return the
        ``normal_intensity`` (0.7) -- never raise.

        TODO(v2): source Shiller CAPE (multpl.com scrape or Excel
        ingest) and wire the ``cape_z > mania_threshold`` mania branch.
        Until then the mania check is a no-op.
        """
        p = self.default_params
        col_name = "sahm_recession"

        if col_name not in factor_df.columns:
            return float(p["normal_intensity"])

        col = factor_df[col_name]

        # "current" value: last non-NaN at or before timestamp.
        try:
            current = col.asof(timestamp)
        except (KeyError, TypeError):
            return float(p["normal_intensity"])
        if current is None or pd.isna(current):
            return float(p["normal_intensity"])

        # sahm_recession is boolean; treat any truthy value as a recession.
        is_recession = bool(current)

        if is_recession:
            return float(p["recession_intensity"])

        # CAPE mania branch -- STUB for v1.  CAPE source is not wired yet
        # (see module docstring + TODO above).  Skip the mania check
        # entirely and fall through to the normal accumulation intensity.
        # When CAPE is sourced in a future task, the logic will be:
        #
        #   cape_z = self._read_cape_z(timestamp, factor_df)
        #   if cape_z is not None and cape_z > float(p["cape_z_mania_threshold"]):
        #       return float(p["mania_intensity"])

        return float(p["normal_intensity"])
