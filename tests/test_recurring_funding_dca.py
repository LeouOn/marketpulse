"""Extended offline coverage for the RecurringFundingDCA strategy (cycle 14).

Complements ``tests/test_research_strategies_RecurringFundingDCA.py`` (defaults,
buy-day signals, zero-rejection, registry, engine happy path) with the
bad-input, empty/NaN/None and accounting-invariant axes the row asks for.

Bugs pinned here (each fix's test fails on the pre-change module):

* ``every_n_bars=None/"30"/[30]`` crashed ``validate_params`` with a raw
  ``TypeError`` instead of the declared ``InvalidParamsError``;
* ``every_n_bars=NaN/inf`` PASSED validation and then crashed
  ``generate_signals`` (``cannot convert float NaN/Infinity to integer``);
* ``every_n_bars=2.5`` passed validation and was silently truncated to 2
  (buy pattern differed from the requested cadence).

All series are small and deterministic; every call is in-process (nothing can
hang).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.research.backtest import run_backtest
from src.research.scaling import FixedDollar
from src.research.strategies import InvalidParamsError, RecurringFundingDCA


def _frame(n: int, closes) -> pd.DataFrame:
    closes = list(closes)
    return pd.DataFrame(
        {
            "ts": pd.date_range("2024-01-01", periods=n, freq="D"),
            "open": closes,
            "high": [c * 1.001 for c in closes],
            "low": [c * 0.999 for c in closes],
            "close": closes,
            "volume": 1.0,
            "source": "synthetic",
        }
    )


def _flat(n: int = 90, price: float = 50_000.0) -> pd.DataFrame:
    return _frame(n, [price] * n)


# ---------------------------------------------------------------------------
# Bad input: validate_params must reject with InvalidParamsError, never crash
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [None, "30", [30], float("nan"), float("inf"), -float("inf"), 0, -5, 2.5, True],
    ids=["none", "str", "list", "nan", "inf", "neginf", "zero", "negative", "fractional", "bool"],
)
def test_validate_rejects_bad_every_n_bars(bad):
    with pytest.raises(InvalidParamsError, match="every_n_bars"):
        RecurringFundingDCA(params={"every_n_bars": bad})


@pytest.mark.parametrize("good", [1, 3, 30, 30.0])
def test_validate_accepts_positive_integers(good):
    s = RecurringFundingDCA(params={"every_n_bars": good})
    assert s.generate_signals(_flat(10)).iloc[0] == 1.0


def test_missing_key_falls_back_to_default():
    """Omitted every_n_bars keeps the documented default (30) and validates."""
    s = RecurringFundingDCA(params={})
    sig = s.generate_signals(_flat(31))
    assert int(np.nansum(sig)) == 2  # bars 0 and 30


# ---------------------------------------------------------------------------
# Signal semantics: cadence, boundaries, independence of prices (no look-ahead)
# ---------------------------------------------------------------------------


def test_every_n_bars_one_buys_every_day():
    sig = RecurringFundingDCA(params={"every_n_bars": 1}).generate_signals(_flat(7))
    assert len(sig.dropna()) == 7
    assert (sig.dropna() == 1.0).all()


def test_first_bar_is_always_a_buy_day():
    for every in (1, 2, 7, 30):
        sig = RecurringFundingDCA(params={"every_n_bars": every}).generate_signals(_flat(60))
        assert sig.iloc[0] == 1.0, every


def test_signals_do_not_depend_on_prices():
    """The cadence is positional; identical index, wildly different prices must
    produce an identical signal mask (no look-ahead, no value dependence)."""
    flat = RecurringFundingDCA(params={"every_n_bars": 5}).generate_signals(_flat(50, price=100.0))
    rng = np.random.default_rng(7)
    wild = np.cumsum(rng.normal(0, 1, 50)) + 100.0
    wild_sig = RecurringFundingDCA(params={"every_n_bars": 5}).generate_signals(_frame(50, wild))
    assert flat.equals(wild_sig)


def test_empty_frame_returns_empty_signals():
    sig = RecurringFundingDCA(params={"every_n_bars": 3}).generate_signals(_flat(0))
    assert len(sig) == 0


def test_signal_values_are_only_one_or_nan():
    sig = RecurringFundingDCA(params={"every_n_bars": 4}).generate_signals(_flat(41))
    values = set(sig.dropna().tolist())
    assert values == {1.0}
    assert int(np.isnan(sig).sum()) == 41 - len(sig.dropna())


# ---------------------------------------------------------------------------
# Accounting invariants with the backtest engine (deterministic flat prices)
# ---------------------------------------------------------------------------


def _run_dca(df, every=30, amount=500.0):
    return run_backtest(
        df,
        strategy=RecurringFundingDCA(params={"every_n_bars": every}),
        scaling=FixedDollar(params={"amount_usd": amount}),
        starting_equity=0.0,
        inflows=[{"every_n_bars": every, "amount_usd": amount}],
    )


def test_flat_price_accounting_invariants():
    r = _run_dca(_flat(90))
    m = r.metrics
    assert m["num_deposits"] == 3
    assert m["num_buys"] == 3  # every deposit is spent exactly once
    assert m["num_sells"] == 0  # DCA never sells
    assert m["total_deposited"] == pytest.approx(1500.0)
    # Fees only ever reduce equity on flat prices; keep a wide but bounded band.
    assert 0.99 * 1500.0 <= r.ending_equity <= 1500.0
    # Cash never goes negative at any trade.
    assert all(t.cash_after >= -1e-9 for t in r.trades)
    # Each buy's notional is the deposit (allowing only the small fee/slippage).
    for t in (t for t in r.trades if t.side == "buy"):
        assert 0.98 * 500.0 <= t.notional_usd <= 500.0


def test_rising_prices_still_spends_every_deposit():
    closes = [50_000.0 * (1.0 + 0.01 * i) for i in range(90)]  # +1%/day
    r = _run_dca(_frame(90, closes))
    assert r.metrics["num_buys"] == r.metrics["num_deposits"] == 3
    # Later deposits buy fewer units at higher prices — monotone non-increasing buys.
    buys = [t for t in r.trades if t.side == "buy"]
    units = [t.units for t in buys]
    assert units == sorted(units, reverse=True)
    assert r.ending_equity > r.metrics["total_deposited"]  # uptrend accrues gains


def test_no_inflow_cash_left_unspent_on_flat_prices():
    r = _run_dca(_flat(90))
    spent = sum(t.notional_usd + t.fee_usd for t in r.trades if t.side == "buy")
    assert spent <= r.metrics["total_deposited"] + 1e-6
    leftover = r.metrics["total_deposited"] - spent
    assert leftover < 500.0  # nothing close to a full unspent deposit remains
