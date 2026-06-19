"""Housing accumulation strategy driven by the 30Y mortgage-rate cycle.

Driver: ``mortgage_30y`` (FRED series ``MORTGAGE30US`` -- 30-Year Fixed
Rate Mortgage Average in the United States, weekly cadence forward-filled
to daily by T11's ``MacroFactorProvider``).  Values are in PERCENT (a
quote of 7.0 means 7.0% nominal APR), so the 1Y change in percentage
points is simply ``current - prior`` -- no scaling required (T11 finding).

Economic rationale (locked v1, see .omo/plans W4 T18):
    Falling mortgage rates improve housing affordability (more house for
    the same monthly payment) and open refinance windows, so a *falling*
    mortgage-rate regime is bullish for housing -- we accumulate FASTER
    (1.5x).  A *rising* mortgage-rate regime cools buyer demand and
    compresses affordability, so we accumulate SLOWER (0.3x).  In the
    neutral band we accumulate at the standard 1.0x DCA cadence.

Phase thresholds (v1 defaults, LOCKED -- do not tune without a fresh
W3 backrun + a notepad decision):
    - 1Y change < -0.5pp  -> falling fast  -> intensity 1.5
    - 1Y change > +0.5pp  -> rising fast   -> intensity 0.3
    - otherwise           -> neutral       -> intensity 1.0

Spec: .omo/plans/multi-asset-macro-research-lab.md W4 T18 (L1430-1469).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

import pandas as pd

from src.research.strategies.cycle_base import CycleAccumulation


@dataclass
class MortgageCycleAccumulation(CycleAccumulation):
    """Housing accumulation driven by the 30Y mortgage-rate cycle.

    INTEREST-ONLY PROXY (Metis SC5 simplification):
        This strategy uses :class:`src.research.loans.FixedRateLoan` as a
        simplified interest-only proxy for a 30Y fixed-rate mortgage.
        Real mortgages amortize principal monthly; ``FixedRateLoan``
        accrues interest compound-daily with interest-only payments
        every 30 days and a balloon payment of the full principal at
        maturity. This is a *documented simplification* of the housing
        backtest -- the interest-only approximation overstates cash-flow
        burden (no principal paydown between payments) but does NOT
        change the balloon obligation, so terminal-equity comparisons
        remain meaningful. See ``src/research/loans.py:FixedRateLoan``
        for the loan contract.

        v2 may add a true amortizing mortgage loan class
        (``AmortizingMortgage``). Out of scope for v1 per Metis SC5.

    The ``mortgage_30y`` column comes from ``MacroFactorProvider.load_factors``
    (T11).  When it's missing, the strategy returns the neutral 1.0
    intensity (DCA fallback).
    """

    name: ClassVar[str] = "MortgageCycleAccumulation"
    description: ClassVar[str] = (
        "Mortgage-rate-cycle housing accumulation: faster when 30Y "
        "mortgage rates are falling (improving affordability + refi "
        "window), slower when rising. Driver: 30Y mortgage rate "
        "(FRED MORTGAGE30US). Uses FixedRateLoan as interest-only proxy "
        "(Metis SC5 simplification)."
    )
    default_params: ClassVar[dict[str, Any]] = {
        # 1Y of trading days. Housing is monthly but the mortgage rate
        # factor is forward-filled to daily by MacroFactorProvider (T11),
        # so the daily-trading-day lookback still applies.
        "lookback_days": 252,
        # All thresholds in PERCENTAGE POINTS (MORTGAGE30US is in %).
        "falling_threshold_pp": -0.5,
        "rising_threshold_pp": 0.5,
        # Intensities are the v1 LOCKED values; see module docstring.
        "falling_intensity": 1.5,
        "rising_intensity": 0.3,
        "neutral_intensity": 1.0,
        # --- Mortgage integration params (Metis SC5: interest-only proxy) ---
        # Default 7.0% rate reflects current 30Y mortgage rates (2026).
        # Overridden at runtime by the current MORTGAGE30US quote when
        # the engine builds a loan via :meth:`_create_mortgage`.
        "loan_rate": 0.07,
        "loan_term_years": 30,
        "down_payment_pct": 0.20,  # 20% down (conventional conforming)
    }

    def _cycle_phase(
        self, timestamp: pd.Timestamp, factor_df: pd.DataFrame
    ) -> float:
        """Return the housing accumulation intensity at ``timestamp``.

        Implements the 3-tier phase logic from the v1 spec.  All
        fallback paths return ``neutral_intensity`` (1.0) -- never raise
        (Metis G6: a FRED outage must never zero out a DCA plan).
        """
        p = self.default_params
        col_name = "mortgage_30y"

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

        # MORTGAGE30US is already in PERCENT, so the raw difference IS in pp.
        change_pp = float(current) - float(prior)

        if change_pp < float(p["falling_threshold_pp"]):
            return float(p["falling_intensity"])
        if change_pp > float(p["rising_threshold_pp"]):
            return float(p["rising_intensity"])
        return float(p["neutral_intensity"])

    def _create_mortgage(
        self, current_rate: float, purchase_price: float
    ) -> "Any":
        """Build a :class:`FixedRateLoan` as a 30Y mortgage interest-only proxy.

        Convenience helper for downstream engine integration (e.g. T21
        CLI dispatching a housing backtest with leverage). The returned
        loan carries the *current* 30Y mortgage rate (typically pulled
        from ``factor_df['mortgage_30y']`` at purchase time) rather than
        the strategy's static ``loan_rate`` default.

        Principal is computed as ``purchase_price * (1 - down_payment_pct)``
        (20% down by default). Term and payment cadence come from
        ``default_params``.

        This method does NOT mutate any state and is NOT called by
        :meth:`_cycle_phase`; it exists purely so the engine has a
        single, documented entry point for instantiating the mortgage
        proxy with strategy-consistent params (Metis SC5).

        Parameters
        ----------
        current_rate
            Annualized interest rate (e.g. ``0.065`` for 6.5%). Pulled
            from the live ``mortgage_30y`` factor at purchase time.
        purchase_price
            Total property purchase price in USD. The loan principal
            equals ``purchase_price * (1 - down_payment_pct)``.

        Returns
        -------
        FixedRateLoan
            Interest-only term loan with a balloon at maturity; see the
            class docstring for the Metis SC5 simplification disclaimer.
        """
        # Deferred import keeps the strategies layer decoupled from the
        # loans layer at module-load time (loans.py is engine-adjacent;
        # importing it eagerly here would create a load-time dependency
        # that complicates T20/T21 wiring).
        from src.research.loans import FixedRateLoan

        p = self.default_params
        down_pct = float(p["down_payment_pct"])
        principal = float(purchase_price) * (1.0 - down_pct)

        return FixedRateLoan(
            principal=principal,
            apr=float(current_rate),
            start_date=pd.Timestamp.now(tz="UTC").tz_convert(None),
            params={
                "term_years": float(p["loan_term_years"]),
                "payment_freq_days": 30,
            },
        )
