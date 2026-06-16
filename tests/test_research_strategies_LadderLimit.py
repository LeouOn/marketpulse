"""Tests for LadderLimit strategy."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.research.strategies.LadderLimit import LadderLimit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_decline_df(
    n_bars: int = 200,
    start_price: float = 50000.0,
    peak_price: float = 60000.0,
    peak_day: int = 100,
    decline_rate: float = 500.0,
) -> pd.DataFrame:
    """Synthetic OHLCV: ramp up then linear decline.

    * Days ``0..peak_day``  — linear ramp ``start_price`` → ``peak_price``
    * Days ``peak_day+1..`` — decline ``decline_rate`` per day
    """
    dates = pd.date_range("2024-01-01", periods=n_bars, freq="D")
    prices = np.empty(n_bars, dtype=float)
    for i in range(n_bars):
        if i <= peak_day:
            prices[i] = start_price + (peak_price - start_price) * i / peak_day
        else:
            prices[i] = peak_price - decline_rate * (i - peak_day)
    return pd.DataFrame(
        {
            "ts": dates,
            "open": prices,
            "high": prices,
            "low": prices,
            "close": prices,
            "volume": 1000.0,
        }
    )


def _make_crash_df(n_before: int = 120) -> pd.DataFrame:
    """Price flat at 60000 then flash-crashes to 45000 (-25%) on the last bar."""
    n = n_before + 1
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    prices = np.concatenate([np.full(n_before, 60000.0), np.array([45000.0])])
    return pd.DataFrame(
        {
            "ts": dates,
            "open": prices,
            "high": prices,
            "low": prices,
            "close": prices,
            "volume": 1000.0,
        }
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLadderLimit:
    """LadderLimit signal-generation tests."""

    # -- basic instantiation --------------------------------------------------

    def test_default_params(self) -> None:
        strat = LadderLimit()
        assert strat.params["tranche_pcts"] == [-0.05, -0.10, -0.15, -0.20]
        assert strat.params["tranche_amounts_usd"] == [100, 200, 400, 800]
        assert strat.params["lookback_calendar_days"] == 90
        assert strat.params["cooldown_calendar_days"] == 30

    # -- signal tests ---------------------------------------------------------

    def test_no_signal_when_price_near_high(self) -> None:
        """During ramp-up the current price IS the rolling high — no triggers."""
        df = _make_decline_df()
        strat = LadderLimit()
        signals = strat.generate_signals(df)
        assert (signals.iloc[:100] == 0.0).all()

    def test_first_tier_triggers_at_5pct_drop(self) -> None:
        """Day 106: price = 57000 = 60000 × 0.95 → tier-0 fires."""
        df = _make_decline_df()
        strat = LadderLimit()
        signals = strat.generate_signals(df)
        assert signals.iloc[106] == 1.0

    def test_second_tier_triggers_at_10pct_drop(self) -> None:
        """Day 112: price = 54000 = 60000 × 0.90 → tier-1 fires."""
        df = _make_decline_df()
        strat = LadderLimit()
        signals = strat.generate_signals(df)
        assert signals.iloc[112] == 1.0

    def test_cooldown_prevents_retrigger(self) -> None:
        """After tier-0 fires on day 106, bars 107-111 stay at 0 (cooldown)."""
        df = _make_decline_df()
        strat = LadderLimit()
        signals = strat.generate_signals(df)
        # Price is still below -5% from high, but tier-0 is cooling down and
        # the drop hasn't yet reached -10% (tier-1 threshold).
        for day in range(107, 112):
            assert signals.iloc[day] == 0.0, f"Unexpected signal at day {day}"

    def test_multiple_tiers_same_bar(self) -> None:
        """Flash crash to -25% fires all 4 tiers simultaneously."""
        df = _make_crash_df()
        strat = LadderLimit()
        signals = strat.generate_signals(df)
        # Pre-crash bars: no triggers (price at the high)
        assert (signals.iloc[:-1] == 0.0).all()
        # Crash bar: all tiers fire → signal = 1.0
        assert signals.iloc[-1] == 1.0

    def test_custom_tranche_params(self) -> None:
        """Custom 2-tier params (-3%, -7%) with custom amounts."""
        strat = LadderLimit(
            params={
                "tranche_pcts": [-0.03, -0.07],
                "tranche_amounts_usd": [50, 100],
            }
        )
        # Verify params merged correctly
        assert strat.params["tranche_pcts"] == [-0.03, -0.07]
        assert strat.params["tranche_amounts_usd"] == [50, 100]

        # Flat at 60000 for 50 bars then decline 200/day
        n = 100
        dates = pd.date_range("2024-01-01", periods=n, freq="D")
        prices = np.empty(n, dtype=float)
        for i in range(n):
            if i < 50:
                prices[i] = 60000.0
            else:
                prices[i] = 60000.0 - 200.0 * (i - 50)
        df = pd.DataFrame(
            {
                "ts": dates,
                "open": prices,
                "high": prices,
                "low": prices,
                "close": prices,
                "volume": 1000.0,
            }
        )

        signals = strat.generate_signals(df)

        # Tier 0 at -3%: 60000×0.97 = 58200 → day 50+(60000-58200)/200 = day 59
        assert signals.iloc[59] == 1.0
        # Tier 1 at -7%: 60000×0.93 = 55800 → day 50+(60000-55800)/200 = day 71
        assert signals.iloc[71] == 1.0
        # Both tiers fired at least once
        assert (signals == 1.0).sum() >= 2
