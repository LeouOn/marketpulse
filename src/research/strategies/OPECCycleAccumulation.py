"""Oil accumulation strategy driven by EIA inventory cycles + spot trend.

Drivers:
    ``oil_inventories_z`` -- z-scored EIA crude inventory surprise
    (relative to a 5Y seasonal norm).  Positive = inventories building
    (bearish); negative = inventories drawing (bullish).

    ``oil_spot_trend`` -- sign of the recent spot-price change
    (positive = spot rising, negative = spot falling).  Used as a
    trend-confirmation gate on the draw signal.

    **T11 does NOT populate either column** (EIA inventories are not in
    T11's macro-factor list).  For v1 we handle this gracefully: if
    ``oil_inventories_z`` is absent we return the neutral intensity
    (1.0) and emit one ``logger.warning`` per process.  This keeps the
    strategy usable on T11's factor set today while remaining correct
    when a future task wires the EIA inventory feed.

Economic rationale (locked v1, see .omo/plans W4 T17):
    Oil is a flow market: when inventories draw *and* the spot price is
    rising, demand has overtaken supply -- trend-follow into it (1.0x;
    neutral, not amplified, since oil's high volatility makes
    amplification dangerous).  When inventories build, supply has
    overtaken demand -- slow down (0.3x) since mean reversion is
    imminent.  In the neutral band, hold the standard 1.0x cadence.

Phase thresholds (v1 defaults, LOCKED -- do not tune without a fresh
W3 backrun + a notepad decision):
    - inventory_z < -1.0 AND spot_trend > 0   -> drawing      -> 1.0
    - inventory_z > +1.0                       -> building     -> 0.3
    - otherwise                                -> neutral      -> 1.0

Spec: .omo/plans/multi-asset-macro-research-lab.md W4 T17 (L1399-1426).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, ClassVar

import pandas as pd
from loguru import logger

from src.research.strategies.cycle_base import CycleAccumulation


@dataclass
class OPECCycleAccumulation(CycleAccumulation):
    """Cycle-aware oil accumulator driven by EIA inventory draws/builds.

    Reads ``factor_df["oil_inventories_z"]`` and (optionally)
    ``factor_df["oil_spot_trend"]``.  When the inventory column is
    missing -- the common case on T11's v1 factor set -- the strategy
    returns the neutral intensity (1.0) and emits a single warning per
    process (throttled via a class-level lock + flag).
    """

    name: ClassVar[str] = "OPECCycleAccumulation"
    description: ClassVar[str] = (
        "Oil accumulation driven by inventory cycles (EIA + spot trend)"
    )
    default_params: ClassVar[dict[str, Any]] = {
        "draw_threshold": -1.0,
        "build_threshold": 1.0,
        "draw_intensity": 1.0,
        "build_intensity": 0.3,
        "neutral_intensity": 1.0,
    }

    #: Throttle for the missing-column warning.  We want exactly one
    #: warning per process (not one per bar) -- a 10-year backtest has
    #: ~2,500 bars and we don't want to spam the log.  Lock-protected so
    #: concurrent backtest workers don't double-warn.
    _missing_col_warned: ClassVar[bool] = False
    _missing_col_lock: ClassVar[threading.Lock] = threading.Lock()

    @classmethod
    def _warn_missing_col_once(cls, col_name: str) -> None:
        """Emit one ``logger.warning`` per process for a missing column."""
        with cls._missing_col_lock:
            if cls._missing_col_warned:
                return
            cls._missing_col_warned = True
        logger.warning(
            f"{cls.__name__}: '{col_name}' not in factor_df -- "
            f"EIA inventory driver not wired (T11 v1 factor set). "
            f"Falling back to neutral_intensity for every bar. "
            f"Wire the EIA feed in a future task to enable phase logic."
        )

    def _cycle_phase(
        self, timestamp: pd.Timestamp, factor_df: pd.DataFrame
    ) -> float:
        """Return the oil accumulation intensity at ``timestamp``.

        Implements the v1 phase logic.  All fallback paths return the
        ``neutral_intensity`` (1.0) -- never raise.
        """
        p = self.default_params
        inv_col = "oil_inventories_z"

        if inv_col not in factor_df.columns:
            self._warn_missing_col_once(inv_col)
            return float(p["neutral_intensity"])

        col = factor_df[inv_col]

        # "current" value: last non-NaN at or before timestamp.
        try:
            inventory_z = col.asof(timestamp)
        except (KeyError, TypeError):
            return float(p["neutral_intensity"])
        if inventory_z is None or pd.isna(inventory_z):
            return float(p["neutral_intensity"])

        inventory_z = float(inventory_z)

        # spot_trend is optional -- not in T11's factor set either.  If
        # absent we treat it as 0.0 (no trend confirmation), which makes
        # the AND-conditional draw branch unreachable and the row falls
        # through to neutral or building.  This is a conservative
        # choice: don't lean in without price confirmation.
        spot_trend = 0.0
        if "oil_spot_trend" in factor_df.columns:
            try:
                st_val = factor_df["oil_spot_trend"].asof(timestamp)
                if st_val is not None and not pd.isna(st_val):
                    spot_trend = float(st_val)
            except (KeyError, TypeError):
                pass

        # Phase logic (v1 LOCKED):
        if inventory_z < float(p["draw_threshold"]) and spot_trend > 0.0:
            return float(p["draw_intensity"])
        if inventory_z > float(p["build_threshold"]):
            return float(p["build_intensity"])
        return float(p["neutral_intensity"])
