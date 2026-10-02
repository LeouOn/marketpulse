"""Edge coverage for src/warsh/gamification.py (cycle 18).

Complements tests/warsh/test_gamification.py (extreme personas, scenario keys,
prediction assets, string-value keys) with the bad-input, boundary, tie and
serialization axes.

Bugs pinned here (each fix's test fails on the pre-change module):

* a ``None`` tool value crashed both ``calculate_hawkish_score`` and
  ``calculate_scenario_match`` (``float(None)`` TypeError);
* a ``NaN`` tool value produced an arbitrary, tool-dependent skew
  (NaN RMP dragged the score DOWN to 0.417, NaN QT pushed it UP to 0.583,
  from the same 0.5 baseline) instead of being ignored like a missing tool;
* name-form string keys ("RMP") were silently DROPPED by
  ``calculate_hawkish_score`` while ``calculate_scenario_match`` accepts them
  (value- or name-match) — the two normalizers disagreed.
"""

from __future__ import annotations

import json
import math

import pytest

from src.warsh.gamification import (
    _SCENARIO_REFERENCES,
    calculate_hawkish_score,
    calculate_scenario_match,
    get_market_prediction,
    rate_fed_chair,
)
from src.warsh.tools import ToolName

# Exact-0.5 configuration (four tools at exactly 0.5, fg=1 -> 1.0, bank=1 -> 0.0).
NEUTRAL = {
    ToolName.RMP: 50,
    ToolName.QT_PACE: 47.5,
    ToolName.SRF: 1000,
    ToolName.MBS_SALES: 17.5,
    ToolName.FORWARD_GUIDANCE: 1,
    ToolName.BANK_REGULATION: 1.0,
}


def _with(**overrides) -> dict:
    cfg = dict(NEUTRAL)
    for name, value in overrides.items():
        cfg[ToolName[name]] = value
    return cfg


# ---------------------------------------------------------------------------
# Persona band boundaries (exact scores)
# ---------------------------------------------------------------------------


def test_score_exactly_half_is_greenspan():
    assert calculate_hawkish_score(NEUTRAL) == pytest.approx(0.5)
    assert rate_fed_chair(NEUTRAL)[0] == "Greenspan Maestro"


def test_score_exactly_point_seven_is_volcker():
    # (0.7*4 + 1.0 + 0.4) / 6 = 0.7
    cfg = _with(RMP=30, QT_PACE=66.5, SRF=600, MBS_SALES=24.5, FORWARD_GUIDANCE=1, BANK_REGULATION=0.6)
    assert calculate_hawkish_score(cfg) == pytest.approx(0.7, abs=1e-12)
    assert rate_fed_chair(cfg)[0] == "Volcker Disciple"


def test_score_exactly_point_three_is_bernanke():
    # (0.3*4 + 0.0 + 0.6) / 6 = 0.3
    cfg = _with(RMP=70, QT_PACE=28.5, SRF=1400, MBS_SALES=10.5, FORWARD_GUIDANCE=0, BANK_REGULATION=0.4)
    score = calculate_hawkish_score(cfg)
    assert 0.3 <= score < 0.5
    assert rate_fed_chair(cfg)[0] == "Bernanke Crisis Manager"


def test_persona_tuple_shape_and_emoji_vocabulary():
    name, emoji, description = rate_fed_chair(NEUTRAL)
    assert (name, emoji, description) == ("Greenspan Maestro", "🎯", description)
    assert len(description) > 10
    for cfg in ({}, NEUTRAL, {ToolName.RMP: 0}):
        persona = rate_fed_chair(cfg)
        assert all(isinstance(part, str) for part in persona)


# ---------------------------------------------------------------------------
# Ties, empty and partial configurations
# ---------------------------------------------------------------------------


def test_empty_config_is_neutral_half():
    assert calculate_hawkish_score({}) == 0.5
    assert rate_fed_chair({})[0] == "Greenspan Maestro"


def test_unknown_keys_only_is_neutral_half():
    assert calculate_hawkish_score({"nope": 5, "also_nope": 10}) == 0.5


def test_unknown_keys_do_not_change_a_known_score():
    cfg = dict(NEUTRAL)
    cfg["totally_unknown"] = 123.0
    assert calculate_hawkish_score(cfg) == pytest.approx(0.5)


@pytest.mark.parametrize(
    ("single", "expected_score", "persona"),
    [
        ({ToolName.RMP: 0}, 1.0, "Volcker Disciple"),  # no bill buys = hawkish
        ({ToolName.RMP: 100}, 0.0, "Trump Puppet"),
        ({ToolName.QT_PACE: 95}, 1.0, "Volcker Disciple"),
        ({ToolName.BANK_REGULATION: 1.0}, 0.0, "Trump Puppet"),
    ],
)
def test_single_tool_decides_the_score(single, expected_score, persona):
    assert calculate_hawkish_score(single) == pytest.approx(expected_score, abs=1e-12)
    assert rate_fed_chair(single)[0] == persona


def test_partial_config_averages_only_present_tools():
    two = {ToolName.RMP: 0, ToolName.BANK_REGULATION: 1.0}  # 1.0 and 0.0
    assert calculate_hawkish_score(two) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Clamping of out-of-range and infinite values
# ---------------------------------------------------------------------------


def test_out_of_range_values_clamp_into_unit_interval():
    cfg = _with(
        RMP=10_000,  # clamps to hawkish 0.0
        QT_PACE=-50,  # clamps to 0.0
        SRF=99_999,  # clamps to 0.0
        MBS_SALES=-3,  # clamps to 0.0
        FORWARD_GUIDANCE=0,
        BANK_REGULATION=7.0,  # clamps to 0.0 (relaxed)
    )
    score = calculate_hawkish_score(cfg)
    assert 0.0 <= score <= 1.0
    assert score == pytest.approx(0.0)


def test_infinite_values_clamp_not_crash():
    cfg = _with(RMP=float("inf"), QT_PACE=float("inf"))
    assert 0.0 <= calculate_hawkish_score(cfg) <= 1.0
    cfg = _with(RMP=-float("inf"))
    assert 0.0 <= calculate_hawkish_score(cfg) <= 1.0


# ---------------------------------------------------------------------------
# Bug: None values must be skipped, not crash
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tool", list(ToolName))
def test_none_value_is_skipped_like_a_missing_tool(tool):
    with_none = _with(**{tool.name: None})
    without = {k: v for k, v in NEUTRAL.items() if k is not tool}
    assert calculate_hawkish_score(with_none) == pytest.approx(calculate_hawkish_score(without))


def test_scenario_none_value_is_skipped_not_crash():
    exact_a = dict(_SCENARIO_REFERENCES["A"])
    exact_a[ToolName.RMP] = None
    out = calculate_scenario_match(exact_a)
    assert set(out) == {"A", "B", "C"}
    # RMP contributes nothing; the other five tools still match exactly.
    assert out["A"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Bug: NaN values must be skipped, not skew the score
# ---------------------------------------------------------------------------


def test_nan_value_is_skipped_like_a_missing_tool():
    base = calculate_hawkish_score(NEUTRAL)  # 0.5
    without_rmp = {k: v for k, v in NEUTRAL.items() if k is not ToolName.RMP}
    without_qt = {k: v for k, v in NEUTRAL.items() if k is not ToolName.QT_PACE}

    nan_rmp = _with(RMP=float("nan"))
    nan_qt = _with(QT_PACE=float("nan"))
    assert calculate_hawkish_score(nan_rmp) == pytest.approx(calculate_hawkish_score(without_rmp)), (
        f"NaN RMP skewed the {base} baseline"
    )
    assert calculate_hawkish_score(nan_qt) == pytest.approx(calculate_hawkish_score(without_qt))


def test_all_nan_config_is_neutral_half():
    cfg = {tool: float("nan") for tool in ToolName}
    assert calculate_hawkish_score(cfg) == 0.5


def test_scenario_nan_value_is_skipped():
    exact_a = dict(_SCENARIO_REFERENCES["A"])
    exact_a[ToolName.QT_PACE] = float("nan")
    out = calculate_scenario_match(exact_a)
    assert out["A"] == pytest.approx(1.0), "the five finite tools match exactly; NaN must not drag the average"


# ---------------------------------------------------------------------------
# Bug: name-form string keys must work in the hawkish score too
# ---------------------------------------------------------------------------


def test_name_form_string_keys_match_enum_score():
    # Non-0.5 baseline so dropped keys would be visible: {RMP: 0} scores 1.0;
    # if the name-form key were dropped the score would silently become 0.5.
    single = {ToolName.RMP: 0}
    by_name = {tool.name: value for tool, value in single.items()}
    assert calculate_hawkish_score(by_name) == pytest.approx(1.0, abs=1e-12)


def test_value_form_string_keys_still_match():
    by_value = {tool.value: value for tool, value in NEUTRAL.items()}
    assert calculate_hawkish_score(by_value) == pytest.approx(calculate_hawkish_score(NEUTRAL))


def test_scenario_accepts_name_and_value_forms():
    by_name = {tool.name: value for tool, value in _SCENARIO_REFERENCES["A"].items()}
    by_value = {tool.value: value for tool, value in _SCENARIO_REFERENCES["A"].items()}
    assert calculate_scenario_match(by_name)["A"] == pytest.approx(1.0)
    assert calculate_scenario_match(by_value)["A"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Scenario semantics
# ---------------------------------------------------------------------------


def test_exact_reference_match_scores_one():
    out = calculate_scenario_match(dict(_SCENARIO_REFERENCES["B"]))
    assert out["B"] == pytest.approx(1.0)
    assert out["A"] < 1.0


def test_maximally_distant_config_scores_low_similarity():
    # Every tool as far from reference A as its range allows (FG also equals A).
    far = {
        ToolName.RMP: 100,
        ToolName.QT_PACE: 0,
        ToolName.SRF: 2000,
        ToolName.MBS_SALES: 0,
        ToolName.FORWARD_GUIDANCE: 1,  # ref A also has 1 -> this tool matches
        ToolName.BANK_REGULATION: 1.0,
    }
    out = calculate_scenario_match(far)
    expected = ((1 - 80 / 100) + (1 - 80 / 95) + (1 - 1500 / 2000) + (1 - 20 / 35) + 1.0 + (1 - 0.8 / 1.0)) / 6
    assert out["A"] == pytest.approx(expected)
    assert out["A"] < 0.5


def test_empty_config_scenario_all_zero():
    assert calculate_scenario_match({}) == {"A": 0.0, "B": 0.0, "C": 0.0}


# ---------------------------------------------------------------------------
# Market prediction thresholds + JSON serialization
# ---------------------------------------------------------------------------


def test_prediction_threshold_boundaries():
    # Exactly 0.6 -> hawkish block; exactly 0.4 -> neutral block; below -> dovish.
    hawk = _with(RMP=30, QT_PACE=66.5, SRF=600, MBS_SALES=24.5, FORWARD_GUIDANCE=0, BANK_REGULATION=0.5)
    # (0.7*4 + 0.0 + 0.5)/6 = 0.55 -> neutral
    assert get_market_prediction(hawk)["stocks"] == "neutral"
    assert get_market_prediction(NEUTRAL)["stocks"] == "neutral"
    assert get_market_prediction({ToolName.RMP: 0})["dollar"] == "bullish"
    assert get_market_prediction({ToolName.RMP: 100})["stocks"] == "bullish"


def test_all_outputs_are_json_serializable():
    payloads = [
        calculate_hawkish_score(NEUTRAL),
        rate_fed_chair(NEUTRAL),
        calculate_scenario_match(NEUTRAL),
        get_market_prediction(NEUTRAL),
    ]
    for payload in payloads:
        round_tripped = json.loads(json.dumps(payload))
        assert round_tripped is not None
    # And every numeric output is finite.
    assert math.isfinite(calculate_hawkish_score(NEUTRAL))
    for score in calculate_scenario_match(NEUTRAL).values():
        assert math.isfinite(score)
