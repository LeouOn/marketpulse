"""Loan and leverage modeling for the BTC research lab.

A :class:`Loan` models borrowed capital that accrues interest over time.
The backtest engine feeds each bar's timestamp to the loan so it can:

1. Accrue interest on outstanding principal (compound-daily).
2. Collect scheduled payments (interest-only, balloon at maturity).
3. Detect margin calls (:class:`MarginLoan`) or defaults
   (:class:`NoRecourseLoan`).

All four loan types share the same abstract interface::

    loan.accrued_interest(current_date)    # total interest accrued to date
    loan.scheduled_payment(current_date)   # payment due this date (0 if none)
    loan.remaining_principal(current_date) # outstanding principal
    loan.is_matured(current_date)          # term reached?

Loan-specific helpers (``should_margin_call``, ``should_default``,
``liquidation_price``) live on the relevant subclasses.

This module deliberately avoids importing from ``src.research.backtest``
or ``src.research.strategies`` to keep the dependency graph clean -- the
engine imports *from* here, never the other way around. A local
:class:`InvalidParamsError` is defined to avoid any cross-module coupling.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

import pandas as pd


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class InvalidParamsError(ValueError):
    """Raised when loan parameters fail validation."""


# ---------------------------------------------------------------------------
# Payment record (parallels Trade / Deposit in the backtest engine)
# ---------------------------------------------------------------------------


@dataclass
class LoanPayment:
    """One payment event from the borrower to the lender.

    Parallels ``Trade`` and ``Deposit`` in ``src.research.backtest``.
    Each payment splits into interest and principal components so the
    engine can track ``total_interest_paid`` separately from principal
    paydown.
    """

    ts: pd.Timestamp
    amount_usd: float
    interest_usd: float
    principal_usd: float
    loan_name: str  # identifies which loan (e.g. "FixedRateLoan")
    reason: str  # "scheduled" | "margin_call" | "maturity" | "default"


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------


_DAYS_PER_YEAR = 365.25


@dataclass
class Loan(ABC):
    """Abstract base class for all loan types.

    Subclasses set ``name``, ``description`` and ``default_params``
    ClassVars, implement the four abstract methods, and override
    :meth:`validate_params` to catch obviously bad inputs.

    Interest accrues compound-daily on the outstanding principal at
    ``apr / 365.25`` per day (the canonical BTC-lab day count).
    """

    name: ClassVar[str] = ""
    description: ClassVar[str] = ""
    default_params: ClassVar[dict[str, Any]] = {}

    principal: float  # initial loan amount in USD
    apr: float  # annual percentage rate (e.g. 0.08 for 8%)
    start_date: pd.Timestamp  # when the loan originates
    params: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError(
                f"{type(self).__name__} must set class-level 'name'"
            )
        merged = dict(self.default_params)
        merged.update(self.params)
        self.params = merged
        self.validate_params(self.params)

    def validate_params(self, params: dict[str, Any]) -> None:
        """Check *params* for invalid values; raise :class:`InvalidParamsError`.

        The default implementation is a no-op so subclasses only need to
        override it when they have constraints to enforce.
        """

    # --- shared helpers ---------------------------------------------------

    @staticmethod
    def _days_between(start: pd.Timestamp, end: pd.Timestamp) -> int:
        """Whole-day count between two timestamps, clamped to >= 0."""
        delta = int((pd.Timestamp(end) - pd.Timestamp(start)).days)
        return max(0, delta)

    @staticmethod
    def _compound(principal: float, daily_rate: float, days: int) -> float:
        """Compound *principal* at *daily_rate* over *days* days."""
        if days <= 0:
            return float(principal)
        return float(principal) * (1.0 + daily_rate) ** days

    # --- abstract interface ----------------------------------------------

    @abstractmethod
    def accrued_interest(self, current_date: pd.Timestamp) -> float:
        """Total interest accrued from ``start_date`` to ``current_date``."""

    @abstractmethod
    def scheduled_payment(self, current_date: pd.Timestamp) -> float:
        """Payment due on ``current_date`` (0.0 if not a payment date)."""

    @abstractmethod
    def remaining_principal(self, current_date: pd.Timestamp) -> float:
        """Outstanding principal at ``current_date``."""

    @abstractmethod
    def is_matured(self, current_date: pd.Timestamp) -> bool:
        """Whether the loan has reached its term end."""

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(principal={self.principal}, "
            f"apr={self.apr}, params={self.params})"
        )


# ---------------------------------------------------------------------------
# Fixed-Rate Term Loan
# ---------------------------------------------------------------------------


@dataclass
class FixedRateLoan(Loan):
    """Fixed-rate term loan with interest-only payments and a balloon.

    - Interest accrues daily at ``apr / 365.25`` (compound).
    - Interest-only payments every ``payment_freq_days``.
    - Balloon payment of the full principal at maturity (``term_years``).
    """

    name: ClassVar[str] = "FixedRateLoan"
    description: ClassVar[str] = (
        "Fixed-rate term loan: compound-daily interest, interest-only "
        "payments every payment_freq_days, balloon principal at maturity."
    )
    default_params: ClassVar[dict[str, Any]] = {
        "term_years": 5.0,
        "payment_freq_days": 30,
    }

    def validate_params(self, params: dict[str, Any]) -> None:
        if float(self.principal) <= 0:
            raise InvalidParamsError(
                f"principal must be > 0, got {self.principal}"
            )
        if float(self.apr) < 0:
            raise InvalidParamsError(
                f"apr must be >= 0, got {self.apr}"
            )
        if float(params.get("term_years", 5.0)) <= 0:
            raise InvalidParamsError(
                f"term_years must be > 0, got {params['term_years']}"
            )

    def _daily_rate(self) -> float:
        return float(self.apr) / _DAYS_PER_YEAR

    def accrued_interest(self, current_date: pd.Timestamp) -> float:
        days = self._days_between(self.start_date, current_date)
        if days <= 0:
            return 0.0
        return self._compound(
            float(self.principal), self._daily_rate(), days
        ) - float(self.principal)

    def scheduled_payment(self, current_date: pd.Timestamp) -> float:
        freq = int(self.params["payment_freq_days"])
        days_since = self._days_between(self.start_date, current_date)
        # No payment on day 0 (origination) or on non-payment days.
        if days_since <= 0 or freq <= 0 or days_since % freq != 0:
            return 0.0
        # After maturity the balloon is a separate event, not a scheduled payment.
        if self.is_matured(current_date):
            return 0.0
        # Interest-only payment for the period just elapsed.
        return self._compound(
            float(self.principal), self._daily_rate(), freq
        ) - float(self.principal)

    def remaining_principal(self, current_date: pd.Timestamp) -> float:
        # Interest-only: principal never amortizes; balloon at maturity.
        return float(self.principal)

    def is_matured(self, current_date: pd.Timestamp) -> bool:
        term_days = float(self.params["term_years"]) * _DAYS_PER_YEAR
        return self._days_between(self.start_date, current_date) >= term_days


# ---------------------------------------------------------------------------
# Variable-Rate Revolver (HELOC-style)
# ---------------------------------------------------------------------------


@dataclass
class VariableRateLoan(Loan):
    """Variable-rate revolver: the APR can change over time.

    - ``initial_rate`` (from ``default_params``) is the starting APR.
    - ``rate_changes`` maps date-strings/Timestamps to new APRs.
    - Interest accrues at the rate active on each day (compound-daily).
    - Interest-only payments every ``payment_freq_days``.
    - No fixed term: a revolver never matures on its own.

    The ``apr`` instance field is accepted for ABC conformance but the
    *effective* rate is always read from ``params['initial_rate']`` (and
    ``rate_changes``); set them consistently to avoid confusion.
    """

    name: ClassVar[str] = "VariableRateLoan"
    description: ClassVar[str] = (
        "Variable-rate revolver: interest accrues at the daily-active "
        "rate (initial_rate + rate_changes), interest-only payments, "
        "no maturity."
    )
    default_params: ClassVar[dict[str, Any]] = {
        "initial_rate": 0.08,
        "rate_changes": {},  # {date_str | Timestamp: new_apr}
        "payment_freq_days": 30,
    }

    def validate_params(self, params: dict[str, Any]) -> None:
        if float(self.principal) <= 0:
            raise InvalidParamsError(
                f"principal must be > 0, got {self.principal}"
            )
        initial = float(params.get("initial_rate", 0.08))
        if initial < 0:
            raise InvalidParamsError(
                f"initial_rate must be >= 0, got {initial}"
            )
        for d, r in (params.get("rate_changes") or {}).items():
            if float(r) < 0:
                raise InvalidParamsError(
                    f"rate_changes[{d!r}] must be >= 0, got {r}"
                )

    def _sorted_changes(self) -> list[tuple[pd.Timestamp, float]]:
        raw = self.params.get("rate_changes") or {}
        return sorted((pd.Timestamp(d), float(r)) for d, r in raw.items())

    def _rate_at(
        self,
        date: pd.Timestamp,
        changes: list[tuple[pd.Timestamp, float]],
    ) -> float:
        """APR active on *date* (most recent change at or before date)."""
        rate = float(self.params["initial_rate"])
        for change_date, new_rate in changes:
            if change_date <= date:
                rate = new_rate
            else:
                break
        return rate

    def accrued_interest(self, current_date: pd.Timestamp) -> float:
        days = self._days_between(self.start_date, current_date)
        if days <= 0:
            return 0.0
        current_date = pd.Timestamp(current_date)
        changes = self._sorted_changes()
        # Build segment boundaries (change dates strictly inside [start, current)).
        boundaries: list[pd.Timestamp] = [pd.Timestamp(self.start_date)]
        for change_date, _ in changes:
            if pd.Timestamp(self.start_date) < change_date < current_date:
                boundaries.append(change_date)
        boundaries.append(current_date)

        balance = float(self.principal)
        for i in range(len(boundaries) - 1):
            seg_start = boundaries[i]
            seg_end = boundaries[i + 1]
            seg_days = int((seg_end - seg_start).days)
            if seg_days > 0:
                rate = self._rate_at(seg_start, changes)
                balance *= (1.0 + rate / _DAYS_PER_YEAR) ** seg_days
        return balance - float(self.principal)

    def scheduled_payment(self, current_date: pd.Timestamp) -> float:
        freq = int(self.params["payment_freq_days"])
        days_since = self._days_between(self.start_date, current_date)
        if days_since <= 0 or freq <= 0 or days_since % freq != 0:
            return 0.0
        period_start = pd.Timestamp(current_date) - pd.Timedelta(days=freq)
        return (
            self.accrued_interest(current_date)
            - self.accrued_interest(period_start)
        )

    def remaining_principal(self, current_date: pd.Timestamp) -> float:
        # Revolver: principal never amortizes on its own.
        return float(self.principal)

    def is_matured(self, current_date: pd.Timestamp) -> bool:
        # Revolver: never matures.
        return False


# ---------------------------------------------------------------------------
# Margin Loan (collateral-based, with liquidation threshold)
# ---------------------------------------------------------------------------


@dataclass
class MarginLoan(Loan):
    """Margin loan backed by BTC collateral.

    - Interest accrues daily at ``apr / 365.25`` (compound).
    - No scheduled payments: interest compounds into the debt.
    - If ``equity / debt`` drops below ``liquidation_threshold`` the
      lender force-sells collateral; ``force_sell_pct`` controls how
      much of the position is liquidated (default: 100%).
    - No fixed term.
    """

    name: ClassVar[str] = "MarginLoan"
    description: ClassVar[str] = (
        "Collateralized margin loan: compound-daily interest, no scheduled "
        "payments, force-liquidation when equity/debt < liquidation_threshold."
    )
    default_params: ClassVar[dict[str, Any]] = {
        "liquidation_threshold": 0.30,  # equity/debt must stay above this
        "force_sell_pct": 1.0,  # sell 100% of BTC on a margin call
    }

    def validate_params(self, params: dict[str, Any]) -> None:
        if float(self.principal) <= 0:
            raise InvalidParamsError(
                f"principal must be > 0, got {self.principal}"
            )
        threshold = float(params.get("liquidation_threshold", 0.30))
        if not (0 < threshold < 1):
            raise InvalidParamsError(
                f"liquidation_threshold must be in (0, 1), got {threshold}"
            )

    def _daily_rate(self) -> float:
        return float(self.apr) / _DAYS_PER_YEAR

    def accrued_interest(self, current_date: pd.Timestamp) -> float:
        days = self._days_between(self.start_date, current_date)
        if days <= 0:
            return 0.0
        return self._compound(
            float(self.principal), self._daily_rate(), days
        ) - float(self.principal)

    def scheduled_payment(self, current_date: pd.Timestamp) -> float:
        # Margin loans have no scheduled payments; interest compounds.
        return 0.0

    def remaining_principal(self, current_date: pd.Timestamp) -> float:
        # Base principal; accrued (unpaid) interest is tracked by the engine.
        return float(self.principal)

    def is_matured(self, current_date: pd.Timestamp) -> bool:
        # Margin loans have no term.
        return False

    # --- margin-call helpers ---------------------------------------------

    def should_margin_call(self, equity: float, current_debt: float) -> bool:
        """Return True when ``equity / current_debt`` breaches the threshold."""
        if float(current_debt) <= 0:
            return False
        ratio = float(equity) / float(current_debt)
        return ratio < float(self.params["liquidation_threshold"])

    def liquidation_price(self, current_equity: float) -> float:
        """Equity level (USD) at which a margin call triggers.

        Equals ``liquidation_threshold * principal``.  If portfolio
        equity falls to this level the lender force-sells.  The engine
        converts this USD level to a BTC price using the current
        position size.  ``current_equity`` is accepted for API symmetry
        with :meth:`should_margin_call`.
        """
        _ = current_equity  # noqa: ARG002 -- reserved for future use
        return (
            float(self.params["liquidation_threshold"]) * float(self.principal)
        )


# ---------------------------------------------------------------------------
# No-Recourse Loan (default allowed)
# ---------------------------------------------------------------------------


@dataclass
class NoRecourseLoan(Loan):
    """Non-recourse term loan: the borrower may default and walk away.

    - Interest accrues daily at ``apr / 365.25`` (compound).
    - Interest-only payments every ``payment_freq_days``.
    - Balloon payment at maturity (``term_years``).
    - If ``equity < current_debt`` at any point the borrower defaults:
      the debt is written off, equity stays with the borrower, and a
      default event is recorded in the metrics.
    """

    name: ClassVar[str] = "NoRecourseLoan"
    description: ClassVar[str] = (
        "Non-recourse term loan: compound-daily interest, interest-only "
        "payments, balloon at maturity, borrower may default when "
        "equity < debt (debt written off on default)."
    )
    default_params: ClassVar[dict[str, Any]] = {
        "term_years": 5.0,
        "payment_freq_days": 30,
    }

    def validate_params(self, params: dict[str, Any]) -> None:
        if float(self.principal) <= 0:
            raise InvalidParamsError(
                f"principal must be > 0, got {self.principal}"
            )
        if float(self.apr) < 0:
            raise InvalidParamsError(
                f"apr must be >= 0, got {self.apr}"
            )

    def _daily_rate(self) -> float:
        return float(self.apr) / _DAYS_PER_YEAR

    def accrued_interest(self, current_date: pd.Timestamp) -> float:
        days = self._days_between(self.start_date, current_date)
        if days <= 0:
            return 0.0
        return self._compound(
            float(self.principal), self._daily_rate(), days
        ) - float(self.principal)

    def scheduled_payment(self, current_date: pd.Timestamp) -> float:
        freq = int(self.params["payment_freq_days"])
        days_since = self._days_between(self.start_date, current_date)
        if days_since <= 0 or freq <= 0 or days_since % freq != 0:
            return 0.0
        if self.is_matured(current_date):
            return 0.0
        return self._compound(
            float(self.principal), self._daily_rate(), freq
        ) - float(self.principal)

    def remaining_principal(self, current_date: pd.Timestamp) -> float:
        return float(self.principal)

    def is_matured(self, current_date: pd.Timestamp) -> bool:
        term_days = float(self.params["term_years"]) * _DAYS_PER_YEAR
        return self._days_between(self.start_date, current_date) >= term_days

    # --- default helper ---------------------------------------------------

    def should_default(self, equity: float, current_debt: float) -> bool:
        """Return True when the borrower is underwater (equity < debt)."""
        return float(equity) < float(current_debt)
