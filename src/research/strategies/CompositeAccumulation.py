"""CompositeAccumulation strategy — multi-signal weighted accumulator.

Combines FGI, RSI, Mayer Multiple, and SMA trend into a single composite
score that maps to a target position fraction. Naturally deploys more
capital in bearish conditions (low FGI, low RSI, low Mayer, below SMA)
and less in bullish conditions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

import numpy as np
import pandas as pd

from src.research.strategies import InvalidParamsError, Strategy


@dataclass
class CompositeAccumulation(Strategy):
    """Multi-signal accumulator combining FGI, RSI, Mayer Multiple, and SMA trend.

    Weights each signal and maps the composite score to a target fraction
    in [conservative_frac, aggressive_frac].
    """

    name: ClassVar[str] = "CompositeAccumulation"
    description: ClassVar[str] = (
        "Multi-signal accumulator combining FGI, RSI, Mayer Multiple, and "
        "SMA trend. Weights each signal and maps the composite score to a "
        "target fraction in [conservative_frac, aggressive_frac]."
    )
    default_params: ClassVar[dict[str, Any]] = {
        "fgi_weight": 0.3,
        "rsi_weight": 0.2,
        "mayer_weight": 0.3,
        "sma_trend_weight": 0.2,
        "sma_period": 200,
        "aggressive_frac": 0.9,
        "conservative_frac": 0.3,
        "rsi_period": 14,
    }

    def validate_params(self, params: dict[str, Any]) -> None:
        for key in ("fgi_weight", "rsi_weight", "mayer_weight", "sma_trend_weight"):
            v = params.get(key, 0.0)
            if not (0 <= v <= 1):
                raise InvalidParamsError(
                    f"{key} must be in [0, 1], got {v}"
                )
        if params.get("sma_period", 200) < 2:
            raise InvalidParamsError(
                f"sma_period must be >= 2, got {params.get('sma_period')}"
            )
        if params.get("rsi_period", 14) < 2:
            raise InvalidParamsError(
                f"rsi_period must be >= 2, got {params.get('rsi_period')}"
            )
        aggr = params.get("aggressive_frac", 0.9)
        cons = params.get("conservative_frac", 0.3)
        if not (0 <= cons <= 1):
            raise InvalidParamsError(
                f"conservative_frac must be in [0, 1], got {cons}"
            )
        if not (0 <= aggr <= 1):
            raise InvalidParamsError(
                f"aggressive_frac must be in [0, 1], got {aggr}"
            )
        if aggr <= cons:
            raise InvalidParamsError(
                f"aggressive_frac ({aggr}) must be > conservative_frac ({cons})"
            )

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        p = self.params
        fgi_w = float(p["fgi_weight"])
        rsi_w = float(p["rsi_weight"])
        mayer_w = float(p["mayer_weight"])
        sma_trend_w = float(p["sma_trend_weight"])
        sma_period = int(p["sma_period"])
        rsi_period = int(p["rsi_period"])
        aggr = float(p["aggressive_frac"])
        cons = float(p["conservative_frac"])

        close = df["close"]

        # --- FGI score (0 = extreme fear → bullish → score 1.0) ---
        if "fgi_value" in df.columns:
            fgi = df["fgi_value"].astype(float)
            fgi_score = 1.0 - fgi / 100.0
        else:
            fgi_score = pd.Series(0.5, index=df.index)

        # --- RSI score (low RSI → bullish → score 1.0) ---
        # Lazy import to avoid a circular import: backtest/__init__.py
        # re-exports from src.research.strategies.
        from src.research.backtest.indicators import compute_rsi

        rsi = compute_rsi(close, rsi_period)
        rsi = rsi.fillna(50.0)
        rsi_score = ((50.0 - rsi) / 50.0).clip(lower=0.0, upper=1.0)

        # --- Mayer Multiple score (low Mayer → bullish → score 1.0) ---
        sma = close.rolling(sma_period, min_periods=sma_period).mean()
        mayer = close / sma.replace(0.0, np.nan)
        # mayer_score: mayer around 0.5 → score 1.0, mayer around 2.5 → score 0.0
        mayer_score = 1.0 - (mayer - 0.5) / 2.0
        mayer_score = mayer_score.clip(lower=0.0, upper=1.0)

        # --- SMA trend score (binary contrarian: 1 if close < SMA, else 0) ---
        # Below SMA = bearish -> score 1.0 -> buy more (contrarian, matching
        # the FGI/RSI/Mayer sibling signals which all reward bearish conditions).
        sma_trend_score = (close < sma).astype(float)
        # During SMA warmup (first sma_period bars), sma is NaN so the
        # comparison yields False (0.0) — i.e. "not below SMA". Use a neutral
        # 0.5 so warmup doesn't bias the composite toward the conservative side.
        warmup = sma.isna()
        sma_trend_score[warmup] = 0.5

        # Fill NaN sub-signals with neutral (0.5)
        fgi_score = fgi_score.fillna(0.5)
        rsi_score = rsi_score.fillna(0.5)
        mayer_score = mayer_score.fillna(0.5)
        sma_trend_score = sma_trend_score.fillna(0.5)

        # --- Weighted composite (normalize weights to sum to 1) ---
        w_sum = fgi_w + rsi_w + mayer_w + sma_trend_w
        if w_sum == 0:
            w_sum = 1.0
        composite = (
            fgi_w * fgi_score
            + rsi_w * rsi_score
            + mayer_w * mayer_score
            + sma_trend_w * sma_trend_score
        ) / w_sum

        # --- Map to target fraction ---
        target = cons + composite * (aggr - cons)
        return self._clip01(target)
