"""Tests for FixedRateLoan used as a 30Y mortgage interest-only proxy (W4/T18).

Metis SC5 (mandatory simplification, documented in
``MortgageCycleAccumulation.__doc__``): the housing backtest reuses the
existing ``FixedRateLoan`` (interest-only with a balloon at maturity)
as a simplified proxy for a true 30Y amortizing mortgage. This file
locks that contract with concrete tests:

1. ``FixedRateLoan`` accepts mortgage-shaped parameters
   (principal=$400K, apr=7%, term=30Y).
2. A scheduled interest-only payment matches the canonical formula
   ``principal * apr / 12`` (within compounding tolerance).
3. The loan never amortizes principal before maturity (balloon structure).
4. ``MortgageCycleAccumulation._create_mortgage`` returns a
   ``FixedRateLoan`` with the requested rate, term, and 20% down payment.
5. Down payment calculation: ``purchase_price * down_payment_pct``.
6. Smoke test: 30Y of synthetic monthly Case-Shiller appreciation + a
   mortgage-backed DCA produces positive terminal equity.

Spec: .omo/plans/multi-asset-macro-research-lab.md W4 T18 (L1430-1469).
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.research.loans import FixedRateLoan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _monthly_dti_factor_df(
    n_months: int = 360,
    prior_value: float = 7.0,
    current_value: float | None = None,
    start: str = "1990-01-31",
) -> pd.DataFrame:
    """Monthly-cadence factor DataFrame with a ``mortgage_30y`` column.

    The smoke test runs on monthly Case-Shiller bars; the macro factor
    must align to that cadence so ``_cycle_phase`` has enough history.
    """
    values = [prior_value] * n_months
    if current_value is not None:
        values[-1] = current_value
    return pd.DataFrame(
        {"mortgage_30y": values},
        index=pd.date_range(start, periods=n_months, freq="ME"),
    )


# ---------------------------------------------------------------------------
# Test 1: FixedRateLoan accepts mortgage-shaped params
# ---------------------------------------------------------------------------


def test_fixed_rate_loan_accepts_mortgage_params() -> None:
    """Instantiate FixedRateLoan with 30Y mortgage-like parameters."""
    start = pd.Timestamp("2020-01-01")
    loan = FixedRateLoan(
        principal=400_000.0,
        apr=0.07,
        start_date=start,
        params={"term_years": 30.0, "payment_freq_days": 30},
    )

    assert loan.principal == pytest.approx(400_000.0)
    assert loan.apr == pytest.approx(0.07)
    assert loan.params["term_years"] == pytest.approx(30.0)
    # Not matured at origination.
    assert loan.is_matured(start) is False


# ---------------------------------------------------------------------------
# Test 2: Monthly interest-only payment matches canonical formula
# ---------------------------------------------------------------------------


def test_monthly_interest_only_payment_matches_formula() -> None:
    """Scheduled interest-only payment ~= principal * apr / 12.

    FixedRateLoan accrues interest compound-daily at apr/365.25 with
    payments every ``payment_freq_days=30`` days. The 30-day compound
    factor is ``(1 + apr/365.25)^30 - 1`` = 0.5766% at 7% APR, vs the
    flat monthly rate ``apr/12`` = 0.5833%. The daily-compounded number
    is ~1.2% *smaller* than the flat monthly convention -- a known
    discrepancy between two legitimate interest accrual conventions.
    The 2% tolerance below comfortably covers that gap while still
    catching gross errors (e.g. principal-amortizing payment, double
    accrual, wrong rate).
    """
    start = pd.Timestamp("2020-01-01")
    principal = 400_000.0
    apr = 0.07
    loan = FixedRateLoan(
        principal=principal,
        apr=apr,
        start_date=start,
        params={"term_years": 30.0, "payment_freq_days": 30},
    )

    # First scheduled payment falls 30 days after origination.
    payment_date = start + pd.Timedelta(days=30)
    payment = loan.scheduled_payment(payment_date)

    expected_monthly_interest = principal * apr / 12.0
    # Compound-daily vs flat monthly: ~1.2% relative difference at 7% APR.
    assert payment == pytest.approx(expected_monthly_interest, rel=0.02)


# ---------------------------------------------------------------------------
# Test 3: Principal never amortizes before maturity (balloon structure)
# ---------------------------------------------------------------------------


def test_principal_does_not_amortize_before_maturity() -> None:
    """Interest-only: principal is unchanged throughout the term.

    A real 30Y amortizing mortgage pays down principal every month; the
    FixedRateLoan proxy keeps the full principal outstanding until the
    balloon at maturity (Metis SC5 documented simplification).
    """
    start = pd.Timestamp("2020-01-01")
    loan = FixedRateLoan(
        principal=400_000.0,
        apr=0.07,
        start_date=start,
        params={"term_years": 30.0, "payment_freq_days": 30},
    )

    # Halfway through the term -- principal must still be intact.
    halfway = start + pd.Timedelta(days=365 * 15)
    assert loan.remaining_principal(halfway) == pytest.approx(400_000.0)
    assert loan.remaining_debt(halfway) == pytest.approx(400_000.0)

    # Just before maturity: still intact (balloon hasn't fired).
    just_before = start + pd.Timedelta(days=365 * 30 - 1)
    assert loan.remaining_principal(just_before) == pytest.approx(400_000.0)

    # At maturity: still principal (balloon is an engine event, not a
    # scheduled payment; see FixedRateLoan.scheduled_payment). Use a
    # date comfortably past the 30Y * 365.25-day threshold so the int
    # truncation in ``_days_between`` can't flip the verdict.
    at_maturity = start + pd.Timedelta(days=366 * 30)
    assert loan.is_matured(at_maturity) is True
    assert loan.remaining_principal(at_maturity) == pytest.approx(400_000.0)


# ---------------------------------------------------------------------------
# Test 4: _create_mortgage helper returns FixedRateLoan with correct params
# ---------------------------------------------------------------------------


def test_create_mortgage_helper_returns_fixed_rate_loan() -> None:
    """_create_mortgage(current_rate, purchase_price) builds a 30Y FixedRateLoan."""
    from src.research.strategies.MortgageCycleAccumulation import (
        MortgageCycleAccumulation,
    )

    strat = MortgageCycleAccumulation()
    purchase_price = 500_000.0
    current_rate = 0.065  # 6.5% -- runtime override from MORTGAGE30US.

    loan = strat._create_mortgage(
        current_rate=current_rate, purchase_price=purchase_price
    )

    assert isinstance(loan, FixedRateLoan)
    # Loan principal = purchase_price * (1 - down_payment_pct) = 500K * 0.80.
    assert loan.principal == pytest.approx(400_000.0)
    # APR overridden by the runtime mortgage rate.
    assert loan.apr == pytest.approx(0.065)
    # Term matches the strategy default (30Y).
    assert loan.params["term_years"] == pytest.approx(30.0)


# ---------------------------------------------------------------------------
# Test 5: Down payment calculation
# ---------------------------------------------------------------------------


def test_down_payment_calculation_is_20_percent() -> None:
    """The 20% down payment is withheld; only 80% of price becomes loan principal."""
    from src.research.strategies.MortgageCycleAccumulation import (
        MortgageCycleAccumulation,
    )

    strat = MortgageCycleAccumulation()
    purchase_price = 500_000.0

    loan = strat._create_mortgage(
        current_rate=0.07, purchase_price=purchase_price
    )

    expected_down = purchase_price * strat.default_params["down_payment_pct"]
    expected_principal = purchase_price - expected_down

    assert expected_down == pytest.approx(100_000.0)  # 20% of 500K
    assert loan.principal == pytest.approx(expected_principal)
    assert loan.principal == pytest.approx(400_000.0)  # 80% of 500K


# ---------------------------------------------------------------------------
# Test 6: Smoke test -- 30Y housing DCA + mortgage -> positive terminal equity
# ---------------------------------------------------------------------------


def test_thirty_year_housing_dca_with_mortgage_positive_equity() -> None:
    """30Y of monthly housing appreciation + mortgage produces positive equity.

    Synthetic Case-Shiller-style monthly bars: 4% annualized appreciation
    (roughly the long-run US national average). The strategy buys one
    unit per month at the cycle intensity. Terminal equity = property
    value - remaining debt (balloon principal). With 4% appreciation
    over 30Y, the property far outgrows the static interest-only
    principal, so equity must be strongly positive.
    """
    from src.research.strategies.MortgageCycleAccumulation import (
        MortgageCycleAccumulation,
    )

    # --- Synthetic monthly Case-Shiller index (4% annual appreciation) ----
    n_months = 360
    monthly_growth = (1.04) ** (1.0 / 12.0)
    starts_at = 100.0
    closes = [starts_at * (monthly_growth ** i) for i in range(n_months)]
    idx = pd.date_range("1990-01-31", periods=n_months, freq="ME")
    ohlcv = pd.DataFrame(
        {
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": 1.0,
        },
        index=idx,
    )

    # --- Mortgage: 80% LTV on the entry-price property --------------------
    strat = MortgageCycleAccumulation()
    entry_price = closes[0]
    loan = strat._create_mortgage(
        current_rate=0.07, purchase_price=entry_price * 1000.0
    )
    # Track loan principal outstanding (interest-only -> constant until balloon).
    principal_outstanding = loan.principal

    # --- Walk bars: at each month, accumulate `intensity` units of housing
    # at the prevailing price. Property units accumulate; debt stays flat ---
    factor_df = _monthly_dti_factor_df(
        n_months=n_months, prior_value=7.0, current_value=7.0
    )
    signals = strat.generate_signals(ohlcv, factor_df=factor_df)

    units_owned = 0.0
    cash_deployed = 0.0
    for i, ts in enumerate(ohlcv.index):
        price = float(ohlcv["close"].iloc[i])
        intensity = float(signals.iloc[i])
        # $1000 monthly contribution scaled by the cycle intensity.
        contribution = 1000.0 * intensity
        units_bought = contribution / price
        units_owned += units_bought
        cash_deployed += contribution

    final_price = float(ohlcv["close"].iloc[-1])
    property_value = units_owned * final_price
    # Equity = property value - outstanding debt (interest-only balloon).
    terminal_equity = property_value - principal_outstanding

    # Sanity: must be positive -- 30Y of 4% appreciation crushes a static
    # 7% interest-only principal. A negative number would indicate a
    # broken accumulation path or a flipped sign somewhere.
    assert terminal_equity > 0, (
        f"Expected positive terminal equity after 30Y of housing DCA + "
        f"mortgage, got ${terminal_equity:,.2f} (property=${property_value:,.2f}, "
        f"debt=${principal_outstanding:,.2f}, cash_deployed=${cash_deployed:,.2f})"
    )
