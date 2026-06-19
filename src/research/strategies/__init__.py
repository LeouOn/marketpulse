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
# MacroGateMixin (W3/T15)
# ---------------------------------------------------------------------------


from src.research.macro.regimes import Regime  # noqa: E402


class MacroGateMixin:
    """Mixin that scales a Strategy's signal by current macro regime.

    GATES ONLY -- does NOT allocate across assets (Metis SC3 guardrail).
    Compose: ``class GatedDCA(MacroGateMixin, DCAFixedAmount): ...``.

    The mixin adds a single method, :meth:`generate_signals_gated`, which
    calls the host strategy's ``generate_signals`` and multiplies the
    result element-wise by a per-regime scalar.  It deliberately does NOT
    override ``generate_signals`` -- the host strategy retains its
    un-gated behaviour when called directly.

    When ``regime_tape`` is ``None`` (no macro layer wired up) the method
    is a no-op pass-through of the base signal.  When ``regime_tape``
    contains NaN values (e.g. FRED outage / warmup gap) those rows fall
    back to a neutral multiplier of 1.0 -- the strategy continues
    accumulating (Metis G6).

    Subclasses tune the gate by overriding ``regime_multipliers``;
    default is all-1.0 (no gating).  Tuning happens per-asset in T16-T18.
    """

    #: Per-regime scalar multiplier applied to the base signal.  Default
    #: is 1.0 across the board (no-op gate); subclasses override to add
    #: real gating.  Values >1.0 amplify (capped at 1.5 post-clip),
    #: values <1.0 attenuate, 0.0 fully suppresses.
    regime_multipliers: dict[Regime, float] = {r: 1.0 for r in Regime}

    def generate_signals_gated(
        self,
        df: pd.DataFrame,
        regime_tape: pd.Series | None,
    ) -> pd.Series:
        """Multiply the base strategy signal by the per-regime multiplier.

        Parameters
        ----------
        df
            OHLCV DataFrame passed through to the host's
            ``generate_signals``.
        regime_tape
            Series indexed like ``df`` whose values are either
            :class:`Regime` enum members or their string values
            (``"RISK_ON"`` etc. -- interop with T12's classifier output,
            whose ``dominant_regime`` column is a string).  ``None``
            disables the gate entirely.  NaN values map to the neutral
            1.0 multiplier.

        Returns
        -------
        pd.Series
            Indexed like ``df``, values clipped to ``[0.0, 1.5]``.
        """
        base = self.generate_signals(df)

        if regime_tape is None:
            return base

        multiplier = regime_tape.map(self._regime_to_multiplier).fillna(1.0)

        # Reindex defensively: if regime_tape's index differs from base's
        # we still want base * 1.0 (no info -> neutral) rather than NaNs.
        multiplier = multiplier.reindex(base.index).fillna(1.0)

        return (base * multiplier).clip(0.0, 1.5)

    def _regime_to_multiplier(self, r: object) -> float:
        """Resolve a regime value to its scalar multiplier.

        Handles Regime enum members, their string values, NaN/None
        (FRED outage / warmup gap), and unknown strings (defensive:
        a bad regime label must never zero out the strategy).
        """
        if r is None or pd.isna(r):
            return 1.0
        # Direct dict hit.  Because ``Regime`` is a ``str, Enum``, a
        # string value hashes identically to its enum member, so this
        # branch covers both enum and string inputs in one shot.
        try:
            if r in self.regime_multipliers:
                return float(self.regime_multipliers[r])
        except TypeError:
            # Unhashable input (defensive) -- fall through to default.
            pass
        # Last resort: try parsing as a Regime string, else neutral.
        if isinstance(r, str):
            try:
                return float(self.regime_multipliers.get(Regime(r), 1.0))
            except ValueError:
                return 1.0
        return 1.0


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

from src.research.strategies.CompositeAccumulation import CompositeAccumulation  # noqa: E402
from src.research.strategies.EarningsCycleAccumulation import (  # noqa: E402
    EarningsCycleAccumulation,
)
from src.research.strategies.HalvingCycleAccumulation import HalvingCycleAccumulation  # noqa: E402
from src.research.strategies.LadderLimit import LadderLimit  # noqa: E402
from src.research.strategies.MortgageCycleAccumulation import (  # noqa: E402
    MortgageCycleAccumulation,
)
from src.research.strategies.OPECCycleAccumulation import (  # noqa: E402
    OPECCycleAccumulation,
)
from src.research.strategies.RealRateCycleAccumulation import (  # noqa: E402
    RealRateCycleAccumulation,
)
from src.research.strategies.RecurringFundingDCA import RecurringFundingDCA  # noqa: E402

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
    # W4 T16: per-asset cycle hierarchy. CycleAccumulation itself is
    # abstract so is intentionally NOT registered; only concrete
    # subclasses appear here. T17/T18 add the others.
    "RealRateCycleAccumulation": RealRateCycleAccumulation,
    "EarningsCycleAccumulation": EarningsCycleAccumulation,
    "OPECCycleAccumulation": OPECCycleAccumulation,
    "MortgageCycleAccumulation": MortgageCycleAccumulation,
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
