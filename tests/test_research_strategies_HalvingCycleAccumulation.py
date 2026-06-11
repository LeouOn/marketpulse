"""Tests for HalvingCycleAccumulation strategy."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.research.strategies import InvalidParamsError, list_strategies
from src.research.strategies.HalvingCycleAccumulation import HalvingCycleAccumulation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_df(
    start: str = "2020-05-11",
    end: str = "2024-04-19",
    freq: str = "D",
    price: float = 50000.0,
) -> pd.DataFrame:
    """Synthetic OHLCV at a flat price over the given date range."""
    dates = pd.date_range(start, end, freq=freq)
    n = len(dates)
    return pd.DataFrame(
        {
            "ts": dates,
            "open": np.full(n, price),
            "high": np.full(n, price),
            "low": np.full(n, price),
            "close": np.full(n, price),
            "volume": 1000.0,
        }
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHalvingCycleAccumulation:
    """HalvingCycleAccumulation signal-generation tests."""

    # -- basic instantiation --------------------------------------------------

    def test_default_params(self) -> None:
        strat = HalvingCycleAccumulation()
        assert len(strat.params["halving_dates"]) == 5
        assert strat.params["aggressive_frac"] == 0.9
        assert strat.params["conservative_frac"] == 0.3
        # Validate passes with defaults (no exception raised)

    # -- signal tests ---------------------------------------------------------

    def test_signals_in_aggressive_phase(self) -> None:
        """2020-12-01 to 2021-10-01 is months ~7-17 post 2020-05-11 halving.
        All signals should be aggressive_frac."""
        df = _make_df(start="2020-12-01", end="2021-10-01")
        strat = HalvingCycleAccumulation()
        signals = strat.generate_signals(df)
        # Every bar in this window should equal aggressive_frac
        assert np.allclose(signals.values, 0.9)

    def test_signals_in_conservative_phase(self) -> None:
        """2022-01-01 to 2022-06-01 is months ~20-25 post 2020 halving.
        Signals should be < aggressive_frac (linearly interpolating down)."""
        df = _make_df(start="2022-01-01", end="2022-06-01")
        strat = HalvingCycleAccumulation()
        signals = strat.generate_signals(df)
        # All signals should be strictly less than aggressive_frac
        assert (signals < 0.9).all()
        # And strictly greater than conservative_frac (still interpolating)
        assert (signals > 0.3).all()

    def test_no_past_halving(self) -> None:
        """Data before 2012-11-28 should return conservative_frac."""
        df = _make_df(start="2010-01-01", end="2012-01-01")
        strat = HalvingCycleAccumulation()
        signals = strat.generate_signals(df)
        assert np.allclose(signals.values, 0.3)

    def test_validate_rejects_inverted(self) -> None:
        """aggressive_frac < conservative_frac should raise InvalidParamsError."""
        with pytest.raises(InvalidParamsError, match="aggressive_frac"):
            HalvingCycleAccumulation(
                params={"aggressive_frac": 0.3, "conservative_frac": 0.9}
            )

    def test_registry_includes(self) -> None:
        """Verify HalvingCycleAccumulation is in the strategy registry."""
        names = {s["name"] for s in list_strategies()}
        assert "HalvingCycleAccumulation" in names
