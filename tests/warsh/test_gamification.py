"""Tests for the Fed Chair gamification module."""
from __future__ import annotations

from src.warsh.gamification import (
    calculate_hawkish_score,
    calculate_scenario_match,
    get_market_prediction,
    rate_fed_chair,
)
from src.warsh.tools import ToolName


# Hawkish configuration: minimal RMP, aggressive QT, large MBS sales,
# forward guidance ON, strict bank regulation, low SRF.
HAWKISH_CONFIG = {
    ToolName.RMP: 0,
    ToolName.QT_PACE: 95,
    ToolName.SRF: 0,
    ToolName.MBS_SALES: 35,
    ToolName.FORWARD_GUIDANCE: 1,
    ToolName.BANK_REGULATION: 0.0,
}

# Dovish configuration: max RMP, no QT, no MBS sales, guidance OFF,
# fully relaxed bank regulation, max SRF.
DOVISH_CONFIG = {
    ToolName.RMP: 100,
    ToolName.QT_PACE: 0,
    ToolName.SRF: 2000,
    ToolName.MBS_SALES: 0,
    ToolName.FORWARD_GUIDANCE: 0,
    ToolName.BANK_REGULATION: 1.0,
}


def test_hawkish_config_gets_volcker_rating():
    name, emoji, _ = rate_fed_chair(HAWKISH_CONFIG)
    assert name == "Volcker Disciple"
    assert emoji == "🦅"


def test_dovish_config_gets_trump_puppet_rating():
    name, emoji, _ = rate_fed_chair(DOVISH_CONFIG)
    assert name == "Trump Puppet"
    assert emoji == "🤡"


def test_scenario_match_returns_three_probabilities():
    result = calculate_scenario_match(HAWKISH_CONFIG)
    assert set(result.keys()) == {"A", "B", "C"}
    for letter, score in result.items():
        assert 0.0 <= score <= 1.0, f"Scenario {letter} score {score} out of [0,1]"
    # Hawkish config should match Scenario A best
    assert result["A"] > result["B"]
    assert result["A"] > result["C"]


def test_market_prediction_returns_all_assets():
    expected = {"stocks", "bonds", "gold", "crypto", "oil", "dollar"}
    result = get_market_prediction(HAWKISH_CONFIG)
    assert set(result.keys()) == expected
    for asset, direction in result.items():
        assert direction in ("bullish", "bearish", "neutral"), (
            f"{asset} direction {direction!r} not valid"
        )


def test_hawkish_score_extremes():
    """Score for max-hawkish should be near 1.0; max-dovish near 0.0."""
    hawk = calculate_hawkish_score(HAWKISH_CONFIG)
    dove = calculate_hawkish_score(DOVISH_CONFIG)
    assert hawk > 0.7, f"Hawkish score {hawk} should be > 0.7"
    assert dove < 0.15, f"Dovish score {dove} should be < 0.15"


def test_market_prediction_dovish_is_bullish_for_risk():
    """A dovish config should predict bullish stocks/bonds/crypto/gold."""
    result = get_market_prediction(DOVISH_CONFIG)
    assert result["stocks"] == "bullish"
    assert result["bonds"] == "bullish"
    assert result["gold"] == "bullish"
    assert result["crypto"] == "bullish"
    assert result["dollar"] == "bearish"


def test_string_keys_also_accepted():
    """The functions should accept string keys (e.g., 'rmp') as well as enums."""
    string_config = {tn.value: val for tn, val in HAWKISH_CONFIG.items()}
    enum_score = calculate_hawkish_score(HAWKISH_CONFIG)
    string_score = calculate_hawkish_score(string_config)
    assert abs(enum_score - string_score) < 1e-9
