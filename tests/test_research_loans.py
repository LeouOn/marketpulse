"""Unit tests for the loan/leverage hierarchy (``src.research.loans``).

Covers every loan type's abstract methods (``accrued_interest``,
``scheduled_payment``, ``remaining_principal``, ``is_matured``) plus
validation and the subclass-specific helpers (``should_margin_call``,
``liquidation_price``, ``should_default``).
"""

from __future__ import annotations

from dataclasses import fields

import pandas as pd
import pytest

from src.research.loans import (
    FixedRateLoan,
    InvalidParamsError,
    Loan,
    LoanPayment,
    MarginLoan,
    NoRecourseLoan,
    VariableRateLoan,
)


START = pd.Timestamp("2024-01-01")
DAYS_PER_YEAR = 365.25


# ---------------------------------------------------------------------------
# LoanPayment dataclass
# ---------------------------------------------------------------------------


def test_loan_payment_dataclass():
    """LoanPayment stores all fields correctly."""
    payment = LoanPayment(
        ts=pd.Timestamp("2024-01-31"),
        amount_usd=65.91,
        interest_usd=65.91,
        principal_usd=0.0,
        loan_name="FixedRateLoan",
        reason="scheduled",
    )
    assert payment.ts == pd.Timestamp("2024-01-31")
    assert payment.amount_usd == pytest.approx(65.91)
    assert payment.interest_usd == pytest.approx(65.91)
    assert payment.principal_usd == pytest.approx(0.0)
    assert payment.loan_name == "FixedRateLoan"
    assert payment.reason == "scheduled"


def test_loan_payment_field_names():
    """LoanPayment has exactly the fields specified in the plan."""
    names = {f.name for f in fields(LoanPayment)}
    assert names == {
        "ts",
        "amount_usd",
        "interest_usd",
        "principal_usd",
        "loan_name",
        "reason",
    }


# ---------------------------------------------------------------------------
# Loan ABC is not directly instantiable
# ---------------------------------------------------------------------------


def test_loan_is_abstract():
    """Loan is an ABC and cannot be instantiated directly."""
    with pytest.raises(TypeError):
        Loan(principal=1000, apr=0.05, start_date=START)  # type: ignore[abstract]


# ===========================================================================
# FixedRateLoan
# ===========================================================================


def test_fixed_rate_loan_creation():
    """FixedRateLoan instantiates with default params and sets ClassVars."""
    loan = FixedRateLoan(principal=10_000, apr=0.08, start_date=START)
    assert loan.name == "FixedRateLoan"
    assert loan.principal == 10_000
    assert loan.apr == pytest.approx(0.08)
    assert loan.start_date == START
    # default_params merged into params
    assert loan.params["term_years"] == 5.0
    assert loan.params["payment_freq_days"] == 30


def test_fixed_rate_loan_validate_negative_principal():
    """Negative principal is rejected."""
    with pytest.raises(InvalidParamsError, match="principal must be > 0"):
        FixedRateLoan(principal=-1_000, apr=0.08, start_date=START)


def test_fixed_rate_loan_validate_zero_principal():
    """Zero principal is rejected (must be strictly positive)."""
    with pytest.raises(InvalidParamsError, match="principal must be > 0"):
        FixedRateLoan(principal=0, apr=0.08, start_date=START)


def test_fixed_rate_loan_validate_negative_apr():
    """Negative APR is rejected."""
    with pytest.raises(InvalidParamsError, match="apr must be >= 0"):
        FixedRateLoan(principal=10_000, apr=-0.01, start_date=START)


def test_fixed_rate_loan_validate_zero_term():
    """Non-positive term_years is rejected."""
    with pytest.raises(InvalidParamsError, match="term_years must be > 0"):
        FixedRateLoan(
            principal=10_000, apr=0.08, start_date=START,
            params={"term_years": 0},
        )


def test_fixed_rate_loan_accrued_interest_at_start():
    """No interest has accrued on the start date."""
    loan = FixedRateLoan(principal=10_000, apr=0.08, start_date=START)
    assert loan.accrued_interest(START) == pytest.approx(0.0)


def test_fixed_rate_loan_accrued_interest_after_30_days():
    """After 30 days interest is positive and roughly proportional."""
    loan = FixedRateLoan(principal=10_000, apr=0.08, start_date=START)
    d = START + pd.Timedelta(days=30)
    interest = loan.accrued_interest(d)
    assert interest > 0
    # Expect ~ 10000 * (1 + 0.08/365.25)^30 - 10000
    expected = 10_000 * (1 + 0.08 / DAYS_PER_YEAR) ** 30 - 10_000
    assert interest == pytest.approx(expected, rel=1e-9)


def test_fixed_rate_loan_accrued_interest_after_1_year():
    """After ~1 year interest is close to ``apr * principal``."""
    loan = FixedRateLoan(principal=10_000, apr=0.08, start_date=START)
    d = START + pd.Timedelta(days=365)
    interest = loan.accrued_interest(d)
    expected_exact = 10_000 * (1 + 0.08 / DAYS_PER_YEAR) ** 365 - 10_000
    assert interest == pytest.approx(expected_exact, rel=1e-9)
    # Sanity: compound interest is slightly above simple interest.
    assert interest > 0.08 * 10_000 * 0.99  # ~apr*principal


def test_fixed_rate_loan_scheduled_payment_on_day_0():
    """No scheduled payment on the origination date."""
    loan = FixedRateLoan(principal=10_000, apr=0.08, start_date=START)
    assert loan.scheduled_payment(START) == pytest.approx(0.0)


def test_fixed_rate_loan_scheduled_payment_on_day_30():
    """On a payment date the scheduled payment is the period's interest."""
    loan = FixedRateLoan(principal=10_000, apr=0.08, start_date=START)
    d = START + pd.Timedelta(days=30)
    payment = loan.scheduled_payment(d)
    assert payment > 0
    # Interest-only: equals the compound interest over one payment period.
    expected = 10_000 * (1 + 0.08 / DAYS_PER_YEAR) ** 30 - 10_000
    assert payment == pytest.approx(expected, rel=1e-9)


def test_fixed_rate_loan_scheduled_payment_non_payment_day():
    """On a non-payment day (not a multiple of freq) no payment is due."""
    loan = FixedRateLoan(principal=10_000, apr=0.08, start_date=START)
    d = START + pd.Timedelta(days=15)  # 15 is not a multiple of 30
    assert loan.scheduled_payment(d) == pytest.approx(0.0)


def test_fixed_rate_loan_scheduled_payment_after_maturity():
    """After maturity the balloon is separate; scheduled payment is zero."""
    loan = FixedRateLoan(
        principal=10_000, apr=0.08, start_date=START,
        params={"term_years": 1.0},
    )
    after = START + pd.Timedelta(days=400)
    assert loan.is_matured(after)
    assert loan.scheduled_payment(after) == pytest.approx(0.0)


def test_fixed_rate_loan_remaining_principal_before_maturity():
    """Interest-only loan: principal is unchanged before maturity."""
    loan = FixedRateLoan(principal=10_000, apr=0.08, start_date=START)
    d = START + pd.Timedelta(days=200)
    assert loan.remaining_principal(d) == pytest.approx(10_000)


def test_fixed_rate_loan_remaining_principal_at_maturity():
    """Principal is still outstanding at maturity (balloon due)."""
    loan = FixedRateLoan(
        principal=10_000, apr=0.08, start_date=START,
        params={"term_years": 1.0},
    )
    d = START + pd.Timedelta(days=400)
    assert loan.is_matured(d)
    assert loan.remaining_principal(d) == pytest.approx(10_000)


def test_fixed_rate_loan_is_matured():
    """is_matured is False before the term and True after."""
    loan = FixedRateLoan(
        principal=10_000, apr=0.08, start_date=START,
        params={"term_years": 2.0},
    )
    before = START + pd.Timedelta(days=500)  # < 2*365.25
    after = START + pd.Timedelta(days=800)  # > 2*365.25
    assert loan.is_matured(before) is False
    assert loan.is_matured(after) is True


# ===========================================================================
# VariableRateLoan
# ===========================================================================


def test_variable_rate_loan_creation():
    """VariableRateLoan instantiates and reads initial_rate from params."""
    loan = VariableRateLoan(principal=10_000, apr=0.08, start_date=START)
    assert loan.name == "VariableRateLoan"
    assert loan.params["initial_rate"] == 0.08
    assert loan.params["rate_changes"] == {}
    assert loan.params["payment_freq_days"] == 30


def test_variable_rate_loan_default_rate():
    """Without rate_changes the loan accrues at the initial rate."""
    loan = VariableRateLoan(
        principal=10_000, apr=0.08, start_date=START,
        params={"initial_rate": 0.08},
    )
    d = START + pd.Timedelta(days=90)
    interest = loan.accrued_interest(d)
    expected = 10_000 * (1 + 0.08 / DAYS_PER_YEAR) ** 90 - 10_000
    assert interest == pytest.approx(expected, rel=1e-9)


def test_variable_rate_loan_with_rate_changes():
    """A rate hike causes faster accrual after the change date."""
    loan_flat = VariableRateLoan(
        principal=10_000, apr=0.08, start_date=START,
        params={"initial_rate": 0.08},
    )
    loan_hike = VariableRateLoan(
        principal=10_000, apr=0.08, start_date=START,
        params={
            "initial_rate": 0.08,
            "rate_changes": {"2024-06-01": 0.20},
        },
    )
    # Before the change date both accrue identically.
    before = pd.Timestamp("2024-05-01")
    assert loan_flat.accrued_interest(before) == pytest.approx(
        loan_hike.accrued_interest(before), rel=1e-9
    )
    # After the change date the hiked loan accrues more.
    after = pd.Timestamp("2024-12-01")
    assert loan_hike.accrued_interest(after) > loan_flat.accrued_interest(after)


def test_variable_rate_loan_validate_negative_initial_rate():
    """Negative initial_rate is rejected."""
    with pytest.raises(InvalidParamsError, match="initial_rate must be >= 0"):
        VariableRateLoan(
            principal=10_000, apr=0.08, start_date=START,
            params={"initial_rate": -0.01},
        )


def test_variable_rate_loan_validate_negative_change_rate():
    """A negative rate inside rate_changes is rejected."""
    with pytest.raises(InvalidParamsError, match="must be >= 0"):
        VariableRateLoan(
            principal=10_000, apr=0.08, start_date=START,
            params={
                "initial_rate": 0.08,
                "rate_changes": {"2024-06-01": -0.05},
            },
        )


def test_variable_rate_loan_is_matured_never():
    """A revolver never matures on its own."""
    loan = VariableRateLoan(principal=10_000, apr=0.08, start_date=START)
    far_future = pd.Timestamp("2099-01-01")
    assert loan.is_matured(far_future) is False


def test_variable_rate_loan_scheduled_payment():
    """Interest-only payment is due on payment dates."""
    loan = VariableRateLoan(
        principal=10_000, apr=0.08, start_date=START,
        params={"initial_rate": 0.08, "payment_freq_days": 30},
    )
    pay_day = START + pd.Timedelta(days=30)
    non_pay_day = START + pd.Timedelta(days=15)
    assert loan.scheduled_payment(pay_day) > 0
    assert loan.scheduled_payment(non_pay_day) == pytest.approx(0.0)


# ===========================================================================
# MarginLoan
# ===========================================================================


def test_margin_loan_creation():
    """MarginLoan instantiates with default liquidation threshold."""
    loan = MarginLoan(principal=10_000, apr=0.08, start_date=START)
    assert loan.name == "MarginLoan"
    assert loan.principal == 10_000
    assert loan.params["liquidation_threshold"] == 0.30
    assert loan.params["force_sell_pct"] == 1.0


def test_margin_loan_no_call_when_equity_above_threshold():
    """No margin call when equity/debt is comfortably above threshold."""
    loan = MarginLoan(principal=10_000, apr=0.08, start_date=START)
    # equity/debt = 5000/10000 = 0.5 > 0.30
    assert loan.should_margin_call(equity=5_000, current_debt=10_000) is False


def test_margin_loan_triggers_call_when_equity_drops():
    """Margin call fires when equity/debt drops below the threshold."""
    loan = MarginLoan(principal=10_000, apr=0.08, start_date=START)
    # equity/debt = 2000/10000 = 0.2 < 0.30
    assert loan.should_margin_call(equity=2_000, current_debt=10_000) is True


def test_margin_loan_no_call_when_debt_zero():
    """No margin call when there is no debt (paid off)."""
    loan = MarginLoan(principal=10_000, apr=0.08, start_date=START)
    assert loan.should_margin_call(equity=0, current_debt=0) is False


def test_margin_loan_liquidation_price_calculation():
    """liquidation_price = threshold * principal."""
    loan = MarginLoan(principal=10_000, apr=0.08, start_date=START)
    # 0.30 * 10_000 = 3_000
    assert loan.liquidation_price(current_equity=99_999) == pytest.approx(
        3_000.0
    )
    # Custom threshold
    loan2 = MarginLoan(
        principal=50_000, apr=0.05, start_date=START,
        params={"liquidation_threshold": 0.50},
    )
    assert loan2.liquidation_price(current_equity=100_000) == pytest.approx(
        25_000.0
    )


def test_margin_loan_validate_threshold_out_of_range():
    """liquidation_threshold must be strictly in (0, 1)."""
    with pytest.raises(InvalidParamsError, match="liquidation_threshold"):
        MarginLoan(
            principal=10_000, apr=0.08, start_date=START,
            params={"liquidation_threshold": 0.0},
        )
    with pytest.raises(InvalidParamsError, match="liquidation_threshold"):
        MarginLoan(
            principal=10_000, apr=0.08, start_date=START,
            params={"liquidation_threshold": 1.0},
        )
    with pytest.raises(InvalidParamsError, match="liquidation_threshold"):
        MarginLoan(
            principal=10_000, apr=0.08, start_date=START,
            params={"liquidation_threshold": 1.5},
        )


def test_margin_loan_no_scheduled_payment():
    """Margin loans have no scheduled payments (interest compounds)."""
    loan = MarginLoan(principal=10_000, apr=0.08, start_date=START)
    d = START + pd.Timedelta(days=30)
    assert loan.scheduled_payment(d) == pytest.approx(0.0)


def test_margin_loan_accrued_interest_compounds():
    """Interest accrues compound-daily on MarginLoan."""
    loan = MarginLoan(principal=10_000, apr=0.08, start_date=START)
    d = START + pd.Timedelta(days=60)
    interest = loan.accrued_interest(d)
    expected = 10_000 * (1 + 0.08 / DAYS_PER_YEAR) ** 60 - 10_000
    assert interest == pytest.approx(expected, rel=1e-9)


def test_margin_loan_is_matured_never():
    """Margin loans have no term."""
    loan = MarginLoan(principal=10_000, apr=0.08, start_date=START)
    assert loan.is_matured(pd.Timestamp("2099-01-01")) is False


# ===========================================================================
# NoRecourseLoan
# ===========================================================================


def test_no_recourse_loan_creation():
    """NoRecourseLoan instantiates with default term."""
    loan = NoRecourseLoan(principal=10_000, apr=0.08, start_date=START)
    assert loan.name == "NoRecourseLoan"
    assert loan.principal == 10_000
    assert loan.params["term_years"] == 5.0
    assert loan.params["payment_freq_days"] == 30


def test_no_recourse_loan_no_default_when_equity_above_debt():
    """No default when equity exceeds debt."""
    loan = NoRecourseLoan(principal=10_000, apr=0.08, start_date=START)
    assert loan.should_default(equity=15_000, current_debt=10_000) is False


def test_no_recourse_loan_default_when_equity_below_debt():
    """Default fires when equity falls below debt (underwater)."""
    loan = NoRecourseLoan(principal=10_000, apr=0.08, start_date=START)
    assert loan.should_default(equity=5_000, current_debt=10_000) is True


def test_no_recourse_loan_is_matured():
    """NoRecourseLoan matures after its term."""
    loan = NoRecourseLoan(
        principal=10_000, apr=0.08, start_date=START,
        params={"term_years": 1.0},
    )
    before = START + pd.Timedelta(days=300)
    after = START + pd.Timedelta(days=400)
    assert loan.is_matured(before) is False
    assert loan.is_matured(after) is True


def test_no_recourse_loan_accrued_interest():
    """Interest accrues compound-daily on NoRecourseLoan."""
    loan = NoRecourseLoan(principal=10_000, apr=0.06, start_date=START)
    d = START + pd.Timedelta(days=90)
    interest = loan.accrued_interest(d)
    expected = 10_000 * (1 + 0.06 / DAYS_PER_YEAR) ** 90 - 10_000
    assert interest == pytest.approx(expected, rel=1e-9)


def test_no_recourse_loan_validate_negative_apr():
    """Negative APR is rejected for NoRecourseLoan."""
    with pytest.raises(InvalidParamsError, match="apr must be >= 0"):
        NoRecourseLoan(principal=10_000, apr=-0.05, start_date=START)


def test_no_recourse_loan_scheduled_payment():
    """Interest-only payments are due on payment dates."""
    loan = NoRecourseLoan(principal=10_000, apr=0.08, start_date=START)
    pay_day = START + pd.Timedelta(days=30)
    assert loan.scheduled_payment(pay_day) > 0
    assert loan.scheduled_payment(START) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Cross-cutting: repr, default_params integrity
# ---------------------------------------------------------------------------


def test_loan_repr_contains_class_name():
    """__repr__ includes the subclass name and principal."""
    loan = FixedRateLoan(principal=10_000, apr=0.08, start_date=START)
    r = repr(loan)
    assert "FixedRateLoan" in r
    assert "10000" in r


def test_default_params_not_mutated_by_instances():
    """Each instance gets its own params dict (no shared mutable state)."""
    loan1 = FixedRateLoan(
        principal=10_000, apr=0.08, start_date=START,
        params={"term_years": 3.0},
    )
    loan2 = FixedRateLoan(principal=10_000, apr=0.08, start_date=START)
    assert loan1.params["term_years"] == 3.0
    assert loan2.params["term_years"] == 5.0
    # Class-level default untouched
    assert FixedRateLoan.default_params["term_years"] == 5.0
