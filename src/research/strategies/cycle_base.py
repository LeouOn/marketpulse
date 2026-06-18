"""Abstract base for per-asset cycle-driven accumulation strategies.

A ``CycleAccumulation`` modulates the speed of dollar-cost averaging based
on a per-asset cyclical driver (real yields for gold, earnings cycle for
equities, OPEC cuts for oil, mortgage credit for housing). Subclasses
implement :meth:`_cycle_phase` returning an *accumulation intensity* in
``[0.0, 1.5]``: 1.0 = neutral (standard DCA), > 1.0 = accumulate faster,
< 1.0 = slower.

The concrete :meth:`generate_signals` walks each bar of the OHLCV frame
and asks the subclass for its phase intensity, then clips the result to
``[0.0, 1.5]``. When macro data is unavailable (``factor_df=None``,
empty, or simply doesn't cover the requested range) every bar falls back
to a neutral intensity of 1.0 -- the strategy continues accumulating
(Metis G6: a FRED outage must never zero out a DCA plan).

Spec: .omo/plans/multi-asset-macro-research-lab.md W4 T16 (lines 1364-1395).
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar

import pandas as pd

from src.research.strategies import Strategy


@dataclass
class CycleAccumulation(Strategy):
    """Abstract cycle-driven accumulator.

    Concrete subclasses (``RealRateCycleAccumulation`` for gold,
    ``EarningsCycleAccumulation`` for equities, ``OPECCycleAccumulation``
    for oil, ``MortgageCycleAccumulation`` for housing) implement
    :meth:`_cycle_phase`.

    The driver factor is read from ``factor_df`` at the strategy's
    :meth:`_cycle_phase` call site; the ABC itself is driver-agnostic.

    The class is decorated with ``@dataclass`` for consistency with the
    rest of the strategy hierarchy (``Strategy`` is itself a dataclass).
    No new fields are added -- the decorator exists purely so the MRO
    inherits ``Strategy.__post_init__`` cleanly.
    """

    name: ClassVar[str] = ""
    description: ClassVar[str] = ""
    default_params: ClassVar[dict[str, Any]] = {}

    @abstractmethod
    def _cycle_phase(
        self, timestamp: pd.Timestamp, factor_df: pd.DataFrame
    ) -> float:
        """Return the accumulation intensity for ``timestamp`` in ``[0.0, 1.5]``.

        1.0 = neutral (standard DCA cadence), > 1.0 = accumulate faster,
        < 1.0 = slower. Implementations MUST stay within the clipped range
        (the caller enforces it defensively, but clean implementations
        don't rely on the clip).

        Parameters
        ----------
        timestamp
            The OHLCV bar's timestamp. The macro factor at-or-before this
            timestamp defines the "current" regime.
        factor_df
            Macro factor frame (e.g. output of
            ``MacroFactorProvider.load_factors``). May be empty or missing
            the subclass's expected column -- in that case return the
            neutral 1.0 intensity rather than raising.
        """
        ...

    def generate_signals(
        self, df: pd.DataFrame, *, factor_df: pd.DataFrame | None = None
    ) -> pd.Series:
        """Return per-bar accumulation intensities in ``[0.0, 1.5]``.

        If ``factor_df`` is ``None`` or empty, returns a uniform 1.0
        (DCA fallback) -- the strategy continues accumulating at the
        baseline cadence regardless of macro data availability.

        Per-bar exceptions raised by ``_cycle_phase`` are swallowed and
        that bar falls back to 1.0 (Metis G6: a bad macro row must not
        halt accumulation across the whole window).

        The output is named ``"signal"`` and clipped to ``[0.0, 1.5]``.
        """
        if factor_df is None or factor_df.empty:
            return pd.Series(1.0, index=df.index, name="signal")

        intensities: list[float] = []
        for ts in df.index:
            try:
                intensity = self._cycle_phase(pd.Timestamp(ts), factor_df)
            except Exception:
                # Defensive: a bad row in factor_df must not halt the
                # whole series -- fall back to neutral for this bar only.
                intensity = self.default_params.get(
                    "neutral_intensity", 1.0
                )
            intensities.append(float(intensity))

        return (
            pd.Series(intensities, index=df.index, name="signal")
            .clip(lower=0.0, upper=1.5)
        )
