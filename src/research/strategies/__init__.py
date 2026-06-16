"""Strategy library for the BTC research lab.

A ``Strategy`` consumes a price DataFrame and produces a *target position
fraction* in ``[0.0, 1.0]`` for each bar. The fraction is the share of
available equity that the strategy wants to hold at the close of that bar.

The backtester is responsible for converting target fractions into actual buy/
sell orders and accounting for fees and slippage.
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
    """Raised when strategy parameters fail validation."""


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


@dataclass
class Strategy(ABC):
    """Abstract base class for all strategies.

    Subclasses must set ``name`` (registry key) and implement
    ``generate_signals(df) -> pd.Series[float]``.
    """

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
    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """Return a pd.Series indexed the same as ``df`` with target fractions in [0, 1]."""

    # --- helpers -----------------------------------------------------------

    @staticmethod
    def _clip01(series: pd.Series) -> pd.Series:
        return series.clip(lower=0.0, upper=1.0)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.params})"


# ---------------------------------------------------------------------------
# Baselines
# ---------------------------------------------------------------------------


@dataclass
class BuyAndHold(Strategy):
    """Always fully invested. Baseline."""

    name: ClassVar[str] = "BuyAndHold"
    description: ClassVar[str] = "Hold 100% BTC for the entire period. Baseline."
    default_params: ClassVar[dict[str, Any]] = {}

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        return pd.Series(1.0, index=df.index)


@dataclass
class NoTrade(Strategy):
    """Never invest. Baseline (should produce 0% return)."""

    name: ClassVar[str] = "NoTrade"
    description: ClassVar[str] = "Stay in cash. Baseline (0% return, 0% drawdown)."
    default_params: ClassVar[dict[str, Any]] = {}

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        return pd.Series(0.0, index=df.index)


# ---------------------------------------------------------------------------
# Dollar-Cost Averaging variants
# ---------------------------------------------------------------------------


@dataclass
class DCAFixedAmount(Strategy):
    """Buy a fixed USD amount every ``every_n_bars`` bars, hold the rest.

    The position fraction depends on how many bars have elapsed, so the
    signal is a step function: 0 until the first buy, then ramps up
    asymptotically as more BTC is accumulated at varying prices.
    """

    name: ClassVar[str] = "DCAFixedAmount"
    description: ClassVar[str] = (
        "Buy a fixed USD amount at a fixed cadence (e.g. $100 every 7 days), "
        "hold the rest in cash. The classic DCA baseline."
    )
    default_params: ClassVar[dict[str, Any]] = {
        "amount_usd": 100.0,
        "every_n_bars": 7,  # 7 daily bars ~= weekly
    }

    def validate_params(self, params: dict[str, Any]) -> None:
        if params.get("every_n_bars", 1) <= 0:
            raise InvalidParamsError(
                f"every_n_bars must be > 0, got {params['every_n_bars']}"
            )
        if params.get("amount_usd", 1) <= 0:
            raise InvalidParamsError(
                f"amount_usd must be > 0, got {params['amount_usd']}"
            )

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        every = max(1, int(self.params["every_n_bars"]))
        # Use a binary "buying day" signal: 1.0 on buy days, NaN otherwise.
        # The backtester interprets this as "spend `amount_usd` then hold".
        signal = np.full(len(df), np.nan, dtype=float)
        signal[::every] = 1.0
        return pd.Series(signal, index=df.index)


@dataclass
class DCAValueAveraging(Strategy):
    """Buy just enough on each interval so the *target* portfolio value is hit.

    This is the "value averaging" approach: if the portfolio is below target,
    buy; if above, sell. We approximate the target as a linear ramp.
    """

    name: ClassVar[str] = "DCAValueAveraging"
    description: ClassVar[str] = (
        "Value Averaging: on each interval, buy/sell to hit a linearly "
        "increasing target portfolio value. Smooths entry price over time."
    )
    default_params: ClassVar[dict[str, Any]] = {
        "target_final_usd": 10000.0,
        "every_n_bars": 7,
    }

    def validate_params(self, params: dict[str, Any]) -> None:
        if params.get("every_n_bars", 1) <= 0:
            raise InvalidParamsError(
                f"every_n_bars must be > 0, got {params['every_n_bars']}"
            )
        if params.get("target_final_usd", 1) <= 0:
            raise InvalidParamsError(
                f"target_final_usd must be > 0, got {params['target_final_usd']}"
            )

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        every = max(1, int(self.params["every_n_bars"]))
        # The signal is the *target position fraction* if we were rebalancing
        # from cash each interval -- which the backtester will translate to
        # "buy/sell to hit this fraction" on the buy day.
        n = len(df)
        # Linear target: 0 at bar 0, 1 at last bar
        target = np.linspace(0.0, 1.0, n)
        # Zero out non-buy days to keep the signal sparse
        mask = np.zeros(n, dtype=bool)
        mask[::every] = True
        # On buy days, signal = target fraction; on other days, hold (NaN
        # means "no change" to the backtester, but we set 0 to be explicit
        # and add a flag column).
        sig = np.where(mask, target, np.nan)
        return pd.Series(sig, index=df.index)


# ---------------------------------------------------------------------------
# Trend / momentum
# ---------------------------------------------------------------------------


@dataclass
class MomentumTrend(Strategy):
    """Long when close > SMA(N), flat otherwise. Classic trend filter."""

    name: ClassVar[str] = "MomentumTrend"
    description: ClassVar[str] = (
        "Long 100% when close > SMA(N), flat (0%) otherwise. Trend-following baseline."
    )
    default_params: ClassVar[dict[str, Any]] = {"sma_period": 200}

    def validate_params(self, params: dict[str, Any]) -> None:
        if params.get("sma_period", 200) < 2:
            raise InvalidParamsError(
                f"sma_period must be >= 2, got {params['sma_period']}"
            )

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        n = int(self.params["sma_period"])
        if n < 2:
            return pd.Series(1.0, index=df.index)
        sma = df["close"].rolling(n, min_periods=n).mean()
        signal = (df["close"] > sma).astype(float)
        # First n-1 bars have NaN SMA; default to flat (0)
        signal = signal.fillna(0.0)
        return self._clip01(signal)


# ---------------------------------------------------------------------------
# Mean-reversion
# ---------------------------------------------------------------------------


@dataclass
class MeanReversionBollinger(Strategy):
    """Long when close < lower Bollinger Band, exit at middle band."""

    name: ClassVar[str] = "MeanReversionBollinger"
    description: ClassVar[str] = (
        "Long when close < lower Bollinger Band; exit when close crosses back "
        "above the middle band. Mean-reversion strategy."
    )
    default_params: ClassVar[dict[str, Any]] = {"period": 20, "num_std": 2.0}

    def validate_params(self, params: dict[str, Any]) -> None:
        if params.get("period", 20) < 2:
            raise InvalidParamsError(
                f"period must be >= 2, got {params['period']}"
            )
        if params.get("num_std", 2.0) <= 0:
            raise InvalidParamsError(
                f"num_std must be > 0, got {params['num_std']}"
            )

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        period = int(self.params["period"])
        num_std = float(self.params["num_std"])
        close = df["close"]
        sma = close.rolling(period, min_periods=period).mean()
        std = close.rolling(period, min_periods=period).std()
        lower = sma - num_std * std
        middle = sma
        signal = pd.Series(0.0, index=df.index)
        in_position = False
        for i in range(len(df)):
            c = close.iloc[i]
            if pd.isna(c) or pd.isna(sma.iloc[i]) or pd.isna(lower.iloc[i]):
                signal.iloc[i] = 0.0
                continue
            if not in_position and c < lower.iloc[i]:
                in_position = True
            elif in_position and c > middle.iloc[i]:
                in_position = False
            signal.iloc[i] = 1.0 if in_position else 0.0
        return signal


@dataclass
class MeanReversionRSI(Strategy):
    """Long when RSI < threshold, exit when RSI > exit threshold."""

    name: ClassVar[str] = "MeanReversionRSI"
    description: ClassVar[str] = (
        "Long when RSI(period) < entry_threshold, exit when RSI > exit_threshold. "
        "Captures oversold bounces."
    )
    default_params: ClassVar[dict[str, Any]] = {
        "period": 14,
        "entry_threshold": 30.0,
        "exit_threshold": 50.0,
    }

    def validate_params(self, params: dict[str, Any]) -> None:
        if params.get("period", 14) < 2:
            raise InvalidParamsError(
                f"period must be >= 2, got {params['period']}"
            )
        entry = params.get("entry_threshold", 30.0)
        exit_ = params.get("exit_threshold", 50.0)
        if not (0 <= entry <= 100):
            raise InvalidParamsError(
                f"entry_threshold must be in [0, 100], got {entry}"
            )
        if not (0 <= exit_ <= 100):
            raise InvalidParamsError(
                f"exit_threshold must be in [0, 100], got {exit_}"
            )
        if entry >= exit_:
            raise InvalidParamsError(
                f"entry_threshold ({entry}) must be < exit_threshold ({exit_})"
            )

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        period = int(self.params["period"])
        entry = float(self.params["entry_threshold"])
        exit_ = float(self.params["exit_threshold"])
        close = df["close"]
        # Lazy import to avoid a circular import: backtest/__init__.py
        # re-exports from this module.
        from src.research.backtest.indicators import compute_rsi

        rsi = compute_rsi(close, period)
        rsi = rsi.fillna(50.0)
        signal = pd.Series(0.0, index=df.index)
        in_position = False
        for i in range(len(df)):
            r = rsi.iloc[i]
            if pd.isna(r):
                continue
            if not in_position and r < entry:
                in_position = True
            elif in_position and r > exit_:
                in_position = False
            signal.iloc[i] = 1.0 if in_position else 0.0
        return signal


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

from src.research.strategies.LadderLimit import LadderLimit  # noqa: E402
from src.research.strategies.RecurringFundingDCA import RecurringFundingDCA  # noqa: E402
from src.research.strategies.HalvingCycleAccumulation import HalvingCycleAccumulation  # noqa: E402
from src.research.strategies.CompositeAccumulation import CompositeAccumulation  # noqa: E402

_REGISTRY: dict[str, type[Strategy]] = {
    "BuyAndHold": BuyAndHold,
    "NoTrade": NoTrade,
    "DCAFixedAmount": DCAFixedAmount,
    "DCAValueAveraging": DCAValueAveraging,
    "MomentumTrend": MomentumTrend,
    "MeanReversionBollinger": MeanReversionBollinger,
    "MeanReversionRSI": MeanReversionRSI,
    "LadderLimit": LadderLimit,
    "RecurringFundingDCA": RecurringFundingDCA,
    "HalvingCycleAccumulation": HalvingCycleAccumulation,
    "CompositeAccumulation": CompositeAccumulation,
}


def list_strategies() -> list[dict[str, Any]]:
    """Return a list of {name, description, default_params} for the LLM."""
    return [
        {
            "name": cls.name,
            "description": cls.description,
            "default_params": dict(cls.default_params),
        }
        for cls in _REGISTRY.values()
    ]


def get_strategy(name: str, params: dict[str, Any] | None = None) -> Strategy:
    """Instantiate a strategy by registry name."""
    if name not in _REGISTRY:
        raise KeyError(f"Unknown strategy '{name}'. Known: {sorted(_REGISTRY)}")
    return _REGISTRY[name](params=dict(params or {}))


def describe_strategy(name: str) -> dict[str, Any]:
    """Return a description of one strategy."""
    if name not in _REGISTRY:
        raise KeyError(f"Unknown strategy '{name}'. Known: {sorted(_REGISTRY)}")
    cls = _REGISTRY[name]
    return {
        "name": cls.name,
        "description": cls.description,
        "default_params": dict(cls.default_params),
    }
