"""Offline tests for ``src/llm/regime_classifier.py``.

The LLM client is fully faked (LMStudioClient is monkeypatched at the module
seam; no sockets), so prompt assembly, response parsing (well-formed, partial,
think-tagged, malformed), the rule-based fallback and the convenience wrapper
are all exercised deterministically and fail fast.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import src.llm.regime_classifier as rc
from src.llm.regime_classifier import (
    MarketData,
    MarketRegimeClassifier,
    RegimeAnalysis,
    classify_current_regime,
)


def _market_data(**overrides) -> MarketData:
    base = dict(
        symbol="NQ",
        current_price=21000.0,
        range_points=150.0,
        volume=120_000,
        avg_volume=100_000,
        vix=18.0,
        vix_percentile=55.0,
        atr=180.0,
        nq_spy_corr=0.85,
        recent_high=21100.0,
        recent_low=20850.0,
    )
    base.update(overrides)
    return MarketData(**base)


# ---------------------------------------------------------------------------
# Dataclass contracts
# ---------------------------------------------------------------------------


def test_regime_analysis_defaults_are_filled():
    analysis = RegimeAnalysis(regime="RANGE_BOUND", confidence=60.0, recommended_bias="neutral", optimal_strategy="s")

    assert analysis.risk_factors == []
    assert analysis.opportunities == []
    assert analysis.timestamp is not None
    assert analysis.key_support is None and analysis.key_resistance is None


def test_market_data_optionals_default_to_none():
    md = MarketData(
        symbol="NQ",
        current_price=1.0,
        range_points=1.0,
        volume=1,
        avg_volume=1,
        vix=1.0,
        vix_percentile=1.0,
        atr=1.0,
        nq_spy_corr=1.0,
    )

    assert md.nq_btc_corr is None
    assert md.sma_20 is None and md.sma_50 is None and md.ema_21 is None
    assert md.session == "US Regular"


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------


def test_prompt_contains_the_market_facts():
    prompt = MarketRegimeClassifier()._build_classification_prompt(_market_data())

    assert "NQ" in prompt
    assert "$21000.00" in prompt
    assert "1.20x" in prompt  # volume / avg_volume
    assert "VIX: 18.00" in prompt
    assert "TRENDING_BULLISH" in prompt and "BREAKOUT_PENDING" in prompt
    assert "Session: US Regular" in prompt


def test_prompt_marks_missing_optionals_and_price_vs_sma():
    md = _market_data(sma_20=20900.0)
    prompt = MarketRegimeClassifier()._build_classification_prompt(md)

    assert "SMA(20): $20900.00" in prompt
    assert "SMA(50): $N/A" in prompt and "EMA(21): $N/A" in prompt
    assert "Price vs SMA(20): Above" in prompt

    below = MarketRegimeClassifier()._build_classification_prompt(_market_data(sma_20=21000.0))
    assert "Price vs SMA(20): Below" in below


def test_prompt_survives_zero_average_volume():
    """A flat/empty feed (avg_volume=0) used to crash prompt assembly with
    ZeroDivisionError; it must degrade to a 0.00x ratio instead."""
    prompt = MarketRegimeClassifier()._build_classification_prompt(_market_data(avg_volume=0))

    assert "0.00x" in prompt


def test_prompt_survives_nan_metrics():
    prompt = MarketRegimeClassifier()._build_classification_prompt(_market_data(vix=float("nan"), atr=float("nan")))

    assert "NQ" in prompt  # assembled, not crashed


# ---------------------------------------------------------------------------
# _parse_llm_response
# ---------------------------------------------------------------------------


WELL_FORMED = """Regime classification: TRENDING_BULLISH
Confidence: 85%
Recommended bias: long
Optimal strategy: Buy FVG retracements with wide stops.
Key support 20850, resistance 21100.
Risks: momentum stall.
Opportunities: continuation higher."""


def test_parse_well_formed_response():
    md = _market_data()
    analysis = MarketRegimeClassifier()._parse_llm_response(WELL_FORMED, md)

    assert analysis.regime == "TRENDING_BULLISH"
    assert analysis.confidence == 85.0
    assert analysis.recommended_bias == "long"
    assert "buy fvg retracements" in analysis.optimal_strategy
    assert analysis.key_support == md.recent_low
    assert analysis.key_resistance == md.recent_high
    assert analysis.reasoning == WELL_FORMED


def test_parse_handles_think_tags_and_spaces():
    tagged = "<think>internal deliberation about ranges</think>The regime is TRENDING_BEARISH. Confidence: 70%. Bias: short. Optimal strategy: Fade rallies into resistance. avoid longs"
    analysis = MarketRegimeClassifier()._parse_llm_response(tagged, _market_data())

    assert analysis.regime == "TRENDING_BEARISH"
    assert analysis.confidence == 70.0
    assert analysis.recommended_bias == "short"


def test_parse_partial_response_uses_defaults():
    analysis = MarketRegimeClassifier()._parse_llm_response("I would say trending_bullish.", _market_data())

    assert analysis.regime == "TRENDING_BULLISH"
    assert analysis.confidence == 75.0  # default when unparsable
    assert analysis.recommended_bias == "neutral"
    assert analysis.optimal_strategy == "Trade according to regime"


def test_parse_garbage_and_empty_response():
    classifier = MarketRegimeClassifier()

    for junk in ["", "no useful content", "42", None]:
        analysis = classifier._parse_llm_response(junk, _market_data())
        assert analysis.regime == "RANGE_BOUND"  # safe default
        assert analysis.recommended_bias == "neutral"


def test_parse_spaced_regime_names():
    analysis = MarketRegimeClassifier()._parse_llm_response("choppy avoid regime, confidence: 60", _market_data())

    assert analysis.regime == "CHOPPY_AVOID"
    assert analysis.confidence == 60.0


def test_parse_confidence_is_clamped_to_0_100():
    """A model answering 'Confidence: 150%' produced confidence=150, outside
    the documented 0-100 range."""
    classifier = MarketRegimeClassifier()

    assert classifier._parse_llm_response("confidence: 150%", _market_data()).confidence == 100.0
    assert classifier._parse_llm_response("confidence: 0%", _market_data()).confidence == 0.0


def test_parse_avoid_bias():
    analysis = MarketRegimeClassifier()._parse_llm_response(
        "regime: choppy_avoid, confidence: 80. avoid trading", _market_data()
    )

    assert analysis.recommended_bias == "avoid"


# ---------------------------------------------------------------------------
# Rule-based classification
# ---------------------------------------------------------------------------


def test_rules_detect_bullish_trend():
    md = _market_data(current_price=21000.0, sma_20=20900.0, sma_50=20800.0, vix=15.0, atr=100.0)
    analysis = MarketRegimeClassifier()._classify_with_rules(md)

    assert analysis.regime == "TRENDING_BULLISH"
    assert analysis.recommended_bias == "long"
    assert analysis.key_support == 20900.0


def test_rules_detect_bearish_trend():
    md = _market_data(current_price=20700.0, sma_20=20900.0, sma_50=21000.0, vix=18.0, atr=150.0)
    analysis = MarketRegimeClassifier()._classify_with_rules(md)

    assert analysis.regime == "TRENDING_BEARISH"
    assert analysis.recommended_bias == "short"


def test_rules_flag_high_volatility_as_choppy():
    md = _market_data(vix=35.0)
    analysis = MarketRegimeClassifier()._classify_with_rules(md)

    assert analysis.regime == "CHOPPY_AVOID"
    assert analysis.recommended_bias == "avoid"


def test_rules_flag_low_volatility_coil_as_breakout_pending():
    md = _market_data(vix=12.0, atr=210.0)  # 1% of price < 1.5%
    analysis = MarketRegimeClassifier()._classify_with_rules(md)

    assert analysis.regime == "BREAKOUT_PENDING"
    assert analysis.recommended_bias == "neutral"


def test_rules_default_to_range_bound_and_skip_partial_trend_data():
    md = _market_data(sma_20=20900.0, sma_50=None, vix=18.0, atr=290.0)  # atr ~1.4%
    analysis = MarketRegimeClassifier()._classify_with_rules(md)

    assert analysis.regime == "RANGE_BOUND"
    assert analysis.key_support == md.recent_low
    assert analysis.key_resistance == md.recent_high


# ---------------------------------------------------------------------------
# classify_regime: LLM path + fallback
# ---------------------------------------------------------------------------


class _FakeLMStudio:
    """Stands in for LMStudioClient; a callable returning an async context."""

    def __init__(self, payload=None, error=None):
        _FakeLMStudio.payload = payload
        _FakeLMStudio.error = error

    def __call__(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def generate_completion(self, **kwargs):
        if _FakeLMStudio.error:
            raise _FakeLMStudio.error
        return _FakeLMStudio.payload


@pytest.fixture
def fake_llm(monkeypatch):
    monkeypatch.setattr(rc, "LLM_AVAILABLE", True)
    monkeypatch.setattr(rc, "LMStudioClient", _FakeLMStudio())
    return _FakeLMStudio


async def test_classify_regime_uses_llm_when_available(fake_llm):
    fake_llm(payload={"choices": [{"message": {"content": WELL_FORMED}}]})

    analysis = await MarketRegimeClassifier().classify_regime(_market_data())

    assert analysis.regime == "TRENDING_BULLISH"
    assert analysis.confidence == 85.0


async def test_classify_regime_falls_back_to_rules_on_llm_error(fake_llm):
    fake_llm(error=OSError("LM Studio unreachable (fake)"))

    md = _market_data(current_price=21000.0, sma_20=20900.0, sma_50=20800.0, vix=15.0, atr=100.0)
    analysis = await MarketRegimeClassifier().classify_regime(md)

    assert analysis.regime == "TRENDING_BULLISH"  # from the rules, not the LLM
    assert analysis.reasoning.startswith("Price > SMA20")  # rule reasoning marker


async def test_classify_regime_falls_back_on_empty_llm_response(fake_llm):
    fake_llm(payload=None)

    analysis = await MarketRegimeClassifier().classify_regime(_market_data(vix=35.0))

    assert analysis.regime == "CHOPPY_AVOID"  # rules answered


async def test_classify_regime_without_llm_goes_straight_to_rules(monkeypatch):
    monkeypatch.setattr(rc, "LLM_AVAILABLE", False)

    md = _market_data(current_price=21000.0, sma_20=20900.0, sma_50=20800.0, vix=15.0, atr=100.0)
    analysis = await MarketRegimeClassifier().classify_regime(md)

    assert analysis.regime == "TRENDING_BULLISH"


# ---------------------------------------------------------------------------
# classify_current_regime: convenience wrapper with faked data pulls
# ---------------------------------------------------------------------------


def _fake_bars_frame(symbols_data):
    async def _not_needed(*a, **k):  # pragma: no cover - bars_frame is sync?
        raise AssertionError("unexpected async call")

    def bars_frame(client, symbol, period="5d", interval="5m"):
        return symbols_data[symbol].copy()

    return bars_frame


def _synthetic_frame(n=80, base=21000.0, seed=3):
    rng = np.random.default_rng(seed)
    close = base + np.cumsum(rng.normal(0, 30, n))
    idx = pd.date_range("2026-01-05 09:30", periods=n, freq="5min")
    return pd.DataFrame(
        {
            "open": close - 10,
            "high": close + 60,
            "low": close - 60,
            "close": close,
            "volume": rng.integers(80_000, 120_000, n).astype(float),
        },
        index=idx,
    )


async def test_classify_current_regime_assembles_data_and_classifies(monkeypatch):
    import src.analysis.yahoo_bars as yb

    frames = {
        "NQ": _synthetic_frame(),
        "^VIX": _synthetic_frame(n=10, base=18.0, seed=4),
        "SPY": _synthetic_frame(n=80, base=600.0, seed=5),
    }
    monkeypatch.setattr(yb, "bars_frame", _fake_bars_frame(frames))
    # Route the wrapper's late import through the same fake.
    import sys

    monkeypatch.setitem(sys.modules, "src.analysis.yahoo_bars", yb)

    # Keep the classification deterministic: LLM off -> rules.
    monkeypatch.setattr(rc, "LLM_AVAILABLE", False)

    class _ClientStub:
        pass

    import src.api.yahoo_client as yc

    monkeypatch.setattr(yc, "YahooFinanceClient", _ClientStub)

    analysis = await classify_current_regime("NQ")

    assert isinstance(analysis, RegimeAnalysis)
    assert analysis.regime in {
        "TRENDING_BULLISH",
        "TRENDING_BEARISH",
        "RANGE_BOUND",
        "CHOPPY_AVOID",
        "BREAKOUT_PENDING",
    }
    assert 0 <= analysis.confidence <= 100


async def test_classify_current_regime_raises_on_empty_data(monkeypatch):
    import src.analysis.yahoo_bars as yb

    empty = {"NQ": pd.DataFrame(columns=["open", "high", "low", "close", "volume"])}
    monkeypatch.setattr(yb, "bars_frame", _fake_bars_frame(empty))

    class _ClientStub:
        pass

    import src.api.yahoo_client as yc

    monkeypatch.setattr(yc, "YahooFinanceClient", _ClientStub)

    with pytest.raises(ValueError, match="No data available"):
        await classify_current_regime("NQ")
