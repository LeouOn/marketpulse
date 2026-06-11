"""Tests for the scaling-model library."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.research.scaling import (
    AntiMartingale,
    DrawdownScaled,
    FixedDollar,
    FixedFractional,
    InvalidParamsError,
    KellyCriterion,
    Martingale,
    RiskParity,
    VolatilityTargeted,
    describe_scaling,
    get_scaling,
    list_scaling_models,
)


def _returns(mean: float = 0.001, std: float = 0.02, n: int = 200, seed: int = 0) -> pd.Series:
    rng = np.random.default_rng(seed)
    return pd.Series(rng.normal(mean, std, n))


# ---------------------------------------------------------------------------
# Fixed variants
# ---------------------------------------------------------------------------


def test_fixed_dollar_always_returns_base():
    s = FixedDollar(params={"amount_usd": 250.0})
    buy, sell = s.size(equity=10_000, position_value=0, price=30_000, recent_returns=_returns())
    assert buy == 250.0
    assert sell == 0.0


def test_fixed_fractional_scales_with_equity():
    s = FixedFractional(params={"fraction": 0.01})
    buy_low, _ = s.size(1_000, 0, 30_000, _returns())
    buy_high, _ = s.size(100_000, 0, 30_000, _returns())
    assert buy_low == 10.0
    assert buy_high == 1_000.0


# ---------------------------------------------------------------------------
# Kelly
# ---------------------------------------------------------------------------


def test_kelly_falls_back_when_returns_too_short():
    s = KellyCriterion()
    buy, _ = s.size(10_000, 0, 30_000, recent_returns=pd.Series([0.01, 0.02, 0.03]))
    # 3 returns < 5, so uses fallback_fraction (0.01) -> $100
    assert buy == 100.0


def test_kelly_zero_when_vol_zero():
    s = KellyCriterion()
    # All returns equal -> var = 0
    r = pd.Series([0.01] * 50)
    buy, _ = s.size(10_000, 0, 30_000, r)
    # sigma2 = 0 -> fallback
    assert buy == 100.0


def test_kelly_positive_on_positive_drift():
    s = KellyCriterion(params={"fraction": 0.5, "lookback": 252, "fallback_fraction": 0.0})
    r = _returns(mean=0.005, std=0.05, n=500)  # strong positive drift
    buy, _ = s.size(10_000, 0, 30_000, r)
    assert buy > 0


def test_kelly_zero_on_negative_drift():
    s = KellyCriterion(params={"fraction": 0.5, "fallback_fraction": 0.0})
    r = _returns(mean=-0.005, std=0.05, n=500)
    buy, _ = s.size(10_000, 0, 30_000, r)
    # Negative Kelly clipped to 0
    assert buy == 0.0


# ---------------------------------------------------------------------------
# Vol-targeting
# ---------------------------------------------------------------------------


def test_vol_targeted_inverse_to_vol():
    s = VolatilityTargeted(params={"target_annual_vol": 0.20, "lookback": 60})
    low_vol_returns = _returns(mean=0.0, std=0.005, n=200)
    high_vol_returns = _returns(mean=0.0, std=0.10, n=200)
    buy_low, _ = s.size(10_000, 0, 30_000, low_vol_returns)
    buy_high, _ = s.size(10_000, 0, 30_000, high_vol_returns)
    # Lower vol should produce a larger size
    assert buy_low > buy_high


def test_vol_targeted_capped_at_max_fraction():
    s = VolatilityTargeted(params={"target_annual_vol": 1.0, "max_fraction": 0.1})
    r = _returns(std=0.001, n=200)  # very low vol
    buy, _ = s.size(10_000, 0, 30_000, r)
    # 1.0 / very_low_vol > 0.1, capped to 0.1
    assert buy == 1_000.0


# ---------------------------------------------------------------------------
# Risk parity
# ---------------------------------------------------------------------------


def test_risk_parity_inverse_to_vol():
    s = RiskParity()
    low_vol = _returns(std=0.001, n=200)  # very low vol
    high_vol = _returns(std=0.10, n=200)
    buy_low, _ = s.size(10_000, 0, 30_000, low_vol)
    buy_high, _ = s.size(10_000, 0, 30_000, high_vol)
    assert buy_low > buy_high
    # Low vol -> large fraction, possibly capped at 1.0
    assert buy_low >= buy_high


# ---------------------------------------------------------------------------
# Drawdown-scaled
# ---------------------------------------------------------------------------


def test_drawdown_scaled_reduces_size_in_drawdown():
    s = DrawdownScaled(params={"base_fraction": 0.05, "exponent": 1.0})
    # At peak: dd=1.0 -> 5% of equity (10_000) = $500
    buy_peak, _ = s.size(10_000, 0, 30_000, _returns(0, 0.02, 200), state={"peak_equity": 10_000})
    # 50% drawdown: dd=0.5 -> 2.5% of *current* equity (5_000) = $125
    buy_dd, _ = s.size(5_000, 0, 30_000, _returns(0, 0.02, 200), state={"peak_equity": 10_000})
    assert buy_peak == 500.0
    assert buy_dd == 125.0
    # And dd-scaled should always be <= the peak-scaled (when equity is below peak)
    assert buy_dd < buy_peak


# ---------------------------------------------------------------------------
# Martingale variants
# ---------------------------------------------------------------------------


def test_anti_martingale_grows_on_win_streak():
    s = AntiMartingale(params={"base_amount": 100.0, "growth_factor": 2.0, "max_streak": 5})
    buy_s0, _ = s.size(10_000, 0, 30_000, _returns(), state={"win_streak": 0})
    buy_s2, _ = s.size(10_000, 0, 30_000, _returns(), state={"win_streak": 2})
    buy_s5, _ = s.size(10_000, 0, 30_000, _returns(), state={"win_streak": 5})
    assert buy_s0 == 100.0
    assert buy_s2 == 400.0
    assert buy_s5 == 3_200.0


def test_martingale_grows_on_loss_streak():
    s = Martingale(params={"base_amount": 100.0, "growth_factor": 2.0, "max_streak": 5})
    buy_s0, _ = s.size(10_000, 0, 30_000, _returns(), state={"loss_streak": 0})
    buy_s3, _ = s.size(10_000, 0, 30_000, _returns(), state={"loss_streak": 3})
    assert buy_s0 == 100.0
    assert buy_s3 == 800.0


def test_martingale_capped_at_max_streak():
    s = Martingale(params={"base_amount": 100.0, "max_streak": 3})
    buy, _ = s.size(10_000, 0, 30_000, _returns(), state={"loss_streak": 10})
    # streak capped to 3 -> 800
    assert buy == 800.0


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_list_scaling_returns_all_known():
    names = {s["name"] for s in list_scaling_models()}
    assert names == {
        "FixedFractional",
        "FixedDollar",
        "KellyCriterion",
        "VolatilityTargeted",
        "RiskParity",
        "DrawdownScaled",
        "AntiMartingale",
        "Martingale",
        "MayerMultipleGated",
        "RSIModulated",
        "SentimentModulated",
    }


def test_describe_scaling_returns_dict():
    d = describe_scaling("KellyCriterion")
    assert d["name"] == "KellyCriterion"
    assert "fraction" in d["default_params"]


def test_get_scaling_unknown_raises():
    with pytest.raises(KeyError):
        get_scaling("NotARealScalingModel")


def test_get_scaling_with_params():
    s = get_scaling("FixedDollar", {"amount_usd": 50.0})
    assert s.params["amount_usd"] == 50.0


def test_all_scaling_models_return_nonneg_sizes():
    """Every scaling model must return non-negative buy/sell amounts."""
    r = _returns(0.0, 0.02, 200)
    for cls in [
        FixedFractional,
        FixedDollar,
        KellyCriterion,
        VolatilityTargeted,
        RiskParity,
        DrawdownScaled,
        AntiMartingale,
        Martingale,
    ]:
        s = cls()
        for eq, pv, st in [(10_000.0, 0.0, {}), (5_000.0, 3_000.0, {"win_streak": 1})]:
            buy, sell = s.size(eq, pv, 30_000.0, r, st)
            assert buy >= 0, f"{cls.__name__} returned negative buy: {buy}"
            assert sell >= 0, f"{cls.__name__} returned negative sell: {sell}"


# ---------------------------------------------------------------------------
# Parameter validation
# ---------------------------------------------------------------------------


def test_validate_fixed_fractional_rejects_bad_params():
    with pytest.raises(InvalidParamsError, match="fraction must be in"):
        FixedFractional(params={"fraction": 5.0})
    with pytest.raises(InvalidParamsError, match="fraction must be in"):
        FixedFractional(params={"fraction": 0.0})


def test_validate_fixed_dollar_rejects_bad_params():
    with pytest.raises(InvalidParamsError, match="amount_usd must be >= 0"):
        FixedDollar(params={"amount_usd": -100})


def test_validate_kelly_criterion_rejects_bad_params():
    with pytest.raises(InvalidParamsError, match="fraction must be in"):
        KellyCriterion(params={"fraction": 0.0})
    with pytest.raises(InvalidParamsError, match="lookback must be > 0"):
        KellyCriterion(params={"lookback": 0})


def test_validate_volatility_targeted_rejects_bad_params():
    with pytest.raises(InvalidParamsError, match="target_annual_vol must be > 0"):
        VolatilityTargeted(params={"target_annual_vol": 0})
    with pytest.raises(InvalidParamsError, match="max_fraction must be in"):
        VolatilityTargeted(params={"max_fraction": 0})


def test_validate_risk_parity_rejects_bad_params():
    with pytest.raises(InvalidParamsError, match="max_fraction must be in"):
        RiskParity(params={"max_fraction": 0})
    with pytest.raises(InvalidParamsError, match="lookback must be > 0"):
        RiskParity(params={"lookback": -1})


def test_validate_drawdown_scaled_rejects_bad_params():
    with pytest.raises(InvalidParamsError, match="base_fraction must be > 0"):
        DrawdownScaled(params={"base_fraction": -0.1})
    with pytest.raises(InvalidParamsError, match="exponent must be > 0"):
        DrawdownScaled(params={"exponent": 0})


def test_validate_anti_martingale_rejects_bad_params():
    with pytest.raises(InvalidParamsError, match="base_amount must be > 0"):
        AntiMartingale(params={"base_amount": 0})
    with pytest.raises(InvalidParamsError, match="growth_factor must be > 0"):
        AntiMartingale(params={"growth_factor": -1})
    with pytest.raises(InvalidParamsError, match="max_streak must be > 0"):
        AntiMartingale(params={"max_streak": 0})


def test_validate_martingale_rejects_bad_params():
    with pytest.raises(InvalidParamsError, match="growth_factor must be > 0"):
        Martingale(params={"growth_factor": 0})


def test_validate_rsi_modulated_rejects_bad_params():
    from src.research.scaling import RSIModulated

    with pytest.raises(InvalidParamsError, match="lookback must be > 0"):
        RSIModulated(params={"lookback": 0})
    with pytest.raises(InvalidParamsError, match="base_buy_multiplier must be > 0"):
        RSIModulated(params={"base_buy_multiplier": -1})


def test_validate_mayer_multiple_gated_rejects_bad_params():
    from src.research.scaling import MayerMultipleGated

    with pytest.raises(InvalidParamsError, match="base_buy_multiplier must be > 0"):
        MayerMultipleGated(params={"base_buy_multiplier": 0})


def test_validate_sentiment_modulated_rejects_bad_params():
    from src.research.scaling import SentimentModulated

    with pytest.raises(InvalidParamsError, match="base_buy_multiplier must be > 0"):
        SentimentModulated(params={"base_buy_multiplier": -1})
