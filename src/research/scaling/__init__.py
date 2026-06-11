"""Position-scaling models for the BTC research lab.

A ``ScalingModel`` answers the question: *given my current state, how much
should the next buy (or sell) be in USD?* It does not decide *whether* to
buy — that comes from the ``Strategy``. The backtester feeds each
``ScalingModel.size(...)`` call:

- ``equity``: current total equity (cash + position value) in USD
- ``position_value``: current BTC position value in USD
- ``price``: current BTC close price
- ``recent_returns``: pd.Series of recent daily (or per-bar) returns
- ``params``: dict of strategy-specific knobs (e.g. lookback window)
- ``state``: dict of strategy state (e.g. last buy size, win streak)

It returns a tuple ``(buy_usd, sell_usd)`` — both are non-negative
floats representing dollar amounts. The backtester clamps these to
available cash and current position.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class InvalidParamsError(ValueError):
    """Raised when scaling model parameters fail validation."""


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


@dataclass
class ScalingModel(ABC):
    name: ClassVar[str] = ""
    description: ClassVar[str] = ""
    default_params: ClassVar[dict[str, Any]] = {}

    params: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError(f"{type(self).__name__} must set class-level 'name'")
        # Always start from default_params, then overlay any user-supplied params.
        merged = dict(self.default_params)
        merged.update(self.params)
        self.params = merged
        self.validate_params(self.params)

    def validate_params(self, params: dict[str, Any]) -> None:
        """Check *params* for invalid values and raise ``InvalidParamsError``.

        The default implementation is a no-op so that existing subclasses
        continue to work without overriding this method.
        """

    @abstractmethod
    def size(
        self,
        equity: float,
        position_value: float,
        price: float,
        recent_returns: pd.Series,
        state: dict[str, Any] | None = None,
    ) -> tuple[float, float]:
        """Return ``(buy_usd, sell_usd)`` for this bar."""

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.params})"


# ---------------------------------------------------------------------------
# Fixed variants
# ---------------------------------------------------------------------------


@dataclass
class FixedFractional(ScalingModel):
    """Risk a fixed % of equity per buy (e.g. 1% per DCA)."""

    name: ClassVar[str] = "FixedFractional"
    description: ClassVar[str] = (
        "Risk a fixed fraction of equity per buy (e.g. 1%). Position size "
        "grows/shrinks with equity."
    )
    default_params: ClassVar[dict[str, Any]] = {"fraction": 0.01}

    def validate_params(self, params: dict[str, Any]) -> None:
        f = params.get("fraction", 0.01)
        if not (0 < f < 1):
            raise InvalidParamsError(
                f"fraction must be in (0, 1), got {f}"
            )

    def size(
        self,
        equity: float,
        position_value: float,
        price: float,
        recent_returns: pd.Series,
        state: dict[str, Any] | None = None,
    ) -> tuple[float, float]:
        fraction = float(self.params["fraction"])
        return equity * fraction, 0.0


@dataclass
class FixedDollar(ScalingModel):
    """Buy exactly $N each bar (DCA constant)."""

    name: ClassVar[str] = "FixedDollar"
    description: ClassVar[str] = (
        "Buy a fixed USD amount each bar (e.g. $100/week). The classic DCA."
    )
    default_params: ClassVar[dict[str, Any]] = {"amount_usd": 100.0}

    def validate_params(self, params: dict[str, Any]) -> None:
        if params.get("amount_usd", 100.0) < 0:
            raise InvalidParamsError(
                f"amount_usd must be >= 0, got {params['amount_usd']}"
            )

    def size(
        self,
        equity: float,
        position_value: float,
        price: float,
        recent_returns: pd.Series,
        state: dict[str, Any] | None = None,
    ) -> tuple[float, float]:
        amount = float(self.params["amount_usd"])
        return amount, 0.0


# ---------------------------------------------------------------------------
# Kelly
# ---------------------------------------------------------------------------


@dataclass
class KellyCriterion(ScalingModel):
    """Bet a fraction f* of equity, where f* = (mu - rf) / sigma^2.

    Full Kelly is aggressive; ``fraction`` is a multiplier (e.g. 0.5 = half-Kelly).
    Uses recent returns to estimate mu and sigma; falls back to a configurable
    default if recent_returns is too short or has zero variance.
    """

    name: ClassVar[str] = "KellyCriterion"
    description: ClassVar[str] = (
        "Bet a Kelly-optimal fraction of equity: f* = (mu - 0) / sigma^2. "
        "Default uses 0.5x Kelly (half-Kelly) for safety. Requires recent returns."
    )
    default_params: ClassVar[dict[str, Any]] = {
        "fraction": 0.5,  # half-Kelly
        "lookback": 252,
        "fallback_fraction": 0.01,  # if we can't compute Kelly, use 1%
    }

    def validate_params(self, params: dict[str, Any]) -> None:
        f = params.get("fraction", 0.5)
        if not (0 < f < 1):
            raise InvalidParamsError(
                f"fraction must be in (0, 1), got {f}"
            )
        if params.get("lookback", 252) <= 0:
            raise InvalidParamsError(
                f"lookback must be > 0, got {params['lookback']}"
            )

    def size(
        self,
        equity: float,
        position_value: float,
        price: float,
        recent_returns: pd.Series,
        state: dict[str, Any] | None = None,
    ) -> tuple[float, float]:
        lookback = int(self.params["lookback"])
        mult = float(self.params["fraction"])
        fallback = float(self.params["fallback_fraction"])

        if recent_returns is None or len(recent_returns) < 5:
            return equity * fallback, 0.0

        r = recent_returns.tail(lookback)
        mu = float(r.mean())
        sigma2 = float(r.var(ddof=0))
        if sigma2 <= 0 or not np.isfinite(sigma2):
            return equity * fallback, 0.0

        f_star = mu / sigma2
        f_star = max(0.0, f_star)  # negative Kelly means don't bet
        f = f_star * mult
        # Cap at 100% of equity to be safe
        f = min(f, 1.0)
        return equity * f, 0.0


# ---------------------------------------------------------------------------
# Volatility-targeted
# ---------------------------------------------------------------------------


@dataclass
class VolatilityTargeted(ScalingModel):
    """Size inversely to recent vol, targeting a constant annual vol.

    size_pct = target_vol / realized_vol, clipped to [0, max_fraction].
    """

    name: ClassVar[str] = "VolatilityTargeted"
    description: ClassVar[str] = (
        "Size positions so that the *expected* position volatility is constant. "
        "If realized vol is high, buy less; if low, buy more. "
        "Common in risk parity and vol-targeting strategies."
    )
    default_params: ClassVar[dict[str, Any]] = {
        "target_annual_vol": 0.20,  # 20% target vol
        "lookback": 60,
        "max_fraction": 1.0,
        "min_fraction": 0.0,
    }

    def validate_params(self, params: dict[str, Any]) -> None:
        if params.get("target_annual_vol", 0.20) <= 0:
            raise InvalidParamsError(
                f"target_annual_vol must be > 0, got {params['target_annual_vol']}"
            )
        mf = params.get("max_fraction", 1.0)
        if not (0 < mf <= 1):
            raise InvalidParamsError(
                f"max_fraction must be in (0, 1], got {mf}"
            )

    def size(
        self,
        equity: float,
        position_value: float,
        price: float,
        recent_returns: pd.Series,
        state: dict[str, Any] | None = None,
    ) -> tuple[float, float]:
        target = float(self.params["target_annual_vol"])
        lookback = int(self.params["lookback"])
        fmax = float(self.params["max_fraction"])
        fmin = float(self.params["min_fraction"])

        if recent_returns is None or len(recent_returns) < 5:
            return equity * (target / 0.5), 0.0  # assume 50% vol fallback

        r = recent_returns.tail(lookback)
        realized_vol_annual = float(r.std(ddof=0) * np.sqrt(365.25))
        if realized_vol_annual <= 0 or not np.isfinite(realized_vol_annual):
            return equity * fmin, 0.0

        f = target / realized_vol_annual
        f = max(fmin, min(f, fmax))
        return equity * f, 0.0


# ---------------------------------------------------------------------------
# Risk-parity
# ---------------------------------------------------------------------------


@dataclass
class RiskParity(ScalingModel):
    """Equal risk contribution: size inversely to recent vol.

    Equivalent to volatility-targeted with target=1/N (single asset: target=1).
    Returns a fraction of equity = 1 / realized_vol_annual.
    """

    name: ClassVar[str] = "RiskParity"
    description: ClassVar[str] = (
        "Risk parity: size inversely to realized vol so each unit of equity "
        "contributes equal risk. Single-asset version: fraction = 1 / vol_annual."
    )
    default_params: ClassVar[dict[str, Any]] = {"lookback": 60, "max_fraction": 1.0}

    def validate_params(self, params: dict[str, Any]) -> None:
        mf = params.get("max_fraction", 1.0)
        if not (0 < mf <= 1):
            raise InvalidParamsError(
                f"max_fraction must be in (0, 1], got {mf}"
            )
        if params.get("lookback", 60) <= 0:
            raise InvalidParamsError(
                f"lookback must be > 0, got {params['lookback']}"
            )

    def size(
        self,
        equity: float,
        position_value: float,
        price: float,
        recent_returns: pd.Series,
        state: dict[str, Any] | None = None,
    ) -> tuple[float, float]:
        lookback = int(self.params["lookback"])
        fmax = float(self.params["max_fraction"])
        if recent_returns is None or len(recent_returns) < 5:
            return 0.0, 0.0
        r = recent_returns.tail(lookback)
        vol = float(r.std(ddof=0) * np.sqrt(365.25))
        if vol <= 0 or not np.isfinite(vol):
            return 0.0, 0.0
        f = min(1.0 / vol, fmax)
        return equity * f, 0.0


# ---------------------------------------------------------------------------
# Drawdown-scaled
# ---------------------------------------------------------------------------


@dataclass
class DrawdownScaled(ScalingModel):
    """Reduce size as equity falls below its rolling peak.

    fraction = base_fraction * (equity / peak_equity) ** exponent.
    """

    name: ClassVar[str] = "DrawdownScaled"
    description: ClassVar[str] = (
        "Reduce buy size as equity falls below the rolling peak (drawdown). "
        "Exponent controls how aggressively to de-risk."
    )
    default_params: ClassVar[dict[str, Any]] = {
        "base_fraction": 0.05,
        "lookback_peak": 252,
        "exponent": 1.0,
    }

    def validate_params(self, params: dict[str, Any]) -> None:
        if params.get("base_fraction", 0.05) <= 0:
            raise InvalidParamsError(
                f"base_fraction must be > 0, got {params['base_fraction']}"
            )
        if params.get("exponent", 1.0) <= 0:
            raise InvalidParamsError(
                f"exponent must be > 0, got {params['exponent']}"
            )

    def size(
        self,
        equity: float,
        position_value: float,
        price: float,
        recent_returns: pd.Series,
        state: dict[str, Any] | None = None,
    ) -> tuple[float, float]:
        base = float(self.params["base_fraction"])
        exp = float(self.params["exponent"])
        lookback = int(self.params["lookback_peak"])

        # peak equity is tracked by the backtester in state
        peak = equity
        if state is not None and "peak_equity" in state:
            peak = float(state["peak_equity"])
        elif recent_returns is not None and len(recent_returns) > 0:
            # Approximate peak from cumulative returns (1 + r).cumprod()
            cum = (1.0 + recent_returns.tail(lookback).fillna(0.0)).cumprod()
            # equity / cumprod[-1] ~= starting equity -> infer peak
            starting_equity = equity / cum.iloc[-1] if cum.iloc[-1] > 0 else equity
            peak = starting_equity * float(cum.max())

        if peak <= 0:
            return equity * base, 0.0
        dd = equity / peak  # 1.0 = at peak, 0.5 = 50% drawdown
        dd = max(0.0, min(1.0, dd))
        f = base * (dd**exp)
        return equity * f, 0.0


# ---------------------------------------------------------------------------
# Martingale variants (for comparison / "why you lose" demos)
# ---------------------------------------------------------------------------


@dataclass
class AntiMartingale(ScalingModel):
    """Double the buy size after each win, reset after each loss.

    Tracks win streak via ``state["win_streak"]``.
    """

    name: ClassVar[str] = "AntiMartingale"
    description: ClassVar[str] = (
        "Anti-martingale: increase buy size after consecutive wins, reset "
        "after a loss. Capitalizes on hot streaks."
    )
    default_params: ClassVar[dict[str, Any]] = {
        "base_amount": 100.0,
        "growth_factor": 2.0,
        "max_streak": 5,
    }

    def validate_params(self, params: dict[str, Any]) -> None:
        if params.get("base_amount", 100.0) <= 0:
            raise InvalidParamsError(
                f"base_amount must be > 0, got {params['base_amount']}"
            )
        if params.get("growth_factor", 2.0) <= 0:
            raise InvalidParamsError(
                f"growth_factor must be > 0, got {params['growth_factor']}"
            )
        if params.get("max_streak", 5) <= 0:
            raise InvalidParamsError(
                f"max_streak must be > 0, got {params['max_streak']}"
            )

    def size(
        self,
        equity: float,
        position_value: float,
        price: float,
        recent_returns: pd.Series,
        state: dict[str, Any] | None = None,
    ) -> tuple[float, float]:
        base = float(self.params["base_amount"])
        g = float(self.params["growth_factor"])
        max_s = int(self.params["max_streak"])
        state = state or {}
        streak = int(state.get("win_streak", 0))
        streak = min(streak, max_s)
        return base * (g**streak), 0.0


@dataclass
class Martingale(ScalingModel):
    """Double the buy size after each loss, reset after a win. (Lose-quick baseline.)"""

    name: ClassVar[str] = "Martingale"
    description: ClassVar[str] = (
        "Martingale: double the buy size after each loss, reset after a win. "
        "Included as a baseline that demonstrates why martingale is dangerous."
    )
    default_params: ClassVar[dict[str, Any]] = {
        "base_amount": 100.0,
        "growth_factor": 2.0,
        "max_streak": 5,
    }

    def validate_params(self, params: dict[str, Any]) -> None:
        if params.get("base_amount", 100.0) <= 0:
            raise InvalidParamsError(
                f"base_amount must be > 0, got {params['base_amount']}"
            )
        if params.get("growth_factor", 2.0) <= 0:
            raise InvalidParamsError(
                f"growth_factor must be > 0, got {params['growth_factor']}"
            )
        if params.get("max_streak", 5) <= 0:
            raise InvalidParamsError(
                f"max_streak must be > 0, got {params['max_streak']}"
            )

    def size(
        self,
        equity: float,
        position_value: float,
        price: float,
        recent_returns: pd.Series,
        state: dict[str, Any] | None = None,
    ) -> tuple[float, float]:
        base = float(self.params["base_amount"])
        g = float(self.params["growth_factor"])
        max_s = int(self.params["max_streak"])
        state = state or {}
        streak = int(state.get("loss_streak", 0))
        streak = min(streak, max_s)
        return base * (g**streak), 0.0


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

from src.research.scaling.MayerMultipleGated import MayerMultipleGated  # noqa: E402
from src.research.scaling.OnChainGated import OnChainGated  # noqa: E402
from src.research.scaling.RSIModulated import RSIModulated  # noqa: E402
from src.research.scaling.SentimentModulated import SentimentModulated  # noqa: E402

_REGISTRY: dict[str, type[ScalingModel]] = {
    "FixedFractional": FixedFractional,
    "FixedDollar": FixedDollar,
    "KellyCriterion": KellyCriterion,
    "VolatilityTargeted": VolatilityTargeted,
    "RiskParity": RiskParity,
    "DrawdownScaled": DrawdownScaled,
    "AntiMartingale": AntiMartingale,
    "Martingale": Martingale,
    "MayerMultipleGated": MayerMultipleGated,
    "OnChainGated": OnChainGated,
    "RSIModulated": RSIModulated,
    "SentimentModulated": SentimentModulated,
}


def list_scaling_models() -> list[dict[str, Any]]:
    return [
        {
            "name": cls.name,
            "description": cls.description,
            "default_params": dict(cls.default_params),
        }
        for cls in _REGISTRY.values()
    ]


def get_scaling(name: str, params: dict[str, Any] | None = None) -> ScalingModel:
    if name not in _REGISTRY:
        raise KeyError(f"Unknown scaling model '{name}'. Known: {sorted(_REGISTRY)}")
    return _REGISTRY[name](params=dict(params or {}))


def describe_scaling(name: str) -> dict[str, Any]:
    if name not in _REGISTRY:
        raise KeyError(f"Unknown scaling model '{name}'. Known: {sorted(_REGISTRY)}")
    cls = _REGISTRY[name]
    return {
        "name": cls.name,
        "description": cls.description,
        "default_params": dict(cls.default_params),
    }
