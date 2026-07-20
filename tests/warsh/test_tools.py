"""Tests for QE-without-QE tool definitions."""
import pytest
from src.warsh.tools import FedTool, ToolName, get_all_tools, apply_tool_effect


def test_all_six_tools_exist():
    tools = get_all_tools()
    names = {t.name for t in tools}
    assert ToolName.RMP in names
    assert ToolName.QT_PACE in names
    assert ToolName.SRF in names
    assert ToolName.MBS_SALES in names
    assert ToolName.FORWARD_GUIDANCE in names
    assert ToolName.BANK_REGULATION in names


def test_tool_has_required_fields():
    tools = get_all_tools()
    for t in tools:
        assert t.name is not None
        assert t.display_name is not None
        assert t.description is not None
        assert t.min_value <= t.current_value <= t.max_value
        assert t.unit is not None
        assert len(t.curve_effects) > 0  # must affect at least one tenor


def test_rmp_reduces_short_end_yields():
    """RMP buys T-bills — should reduce 3M, 1Y, 2Y yields."""
    tools = get_all_tools()
    rmp = next(t for t in tools if t.name == ToolName.RMP)
    # At current value ($40B/month), should have measurable effect
    effects = apply_tool_effect(rmp, rmp.current_value)
    assert "3mo" in effects
    assert effects["3mo"] < 0  # negative = yield reduction
    assert effects["3mo"] < effects.get("2y", 0)  # bigger effect on shorter tenors


def test_qt_increases_long_end_yields():
    """QT sells/lets mature Treasuries — should increase 10Y, 30Y."""
    tools = get_all_tools()
    qt = next(t for t in tools if t.name == ToolName.QT_PACE)
    effects = apply_tool_effect(qt, qt.current_value)
    assert "10y" in effects
    assert effects["10y"] > 0  # positive = yield increase
    assert effects["10y"] > effects.get("2y", 0)  # bigger effect on longer tenors


def test_tool_effect_scales_linearly():
    """Double the tool deployment, roughly double the effect."""
    tools = get_all_tools()
    rmp = next(t for t in tools if t.name == ToolName.RMP)
    effects_low = apply_tool_effect(rmp, 20)
    effects_high = apply_tool_effect(rmp, 40)
    # 40B should have roughly 2x the effect of 20B on 3M
    ratio = abs(effects_high["3mo"]) / abs(effects_low["3mo"]) if effects_low["3mo"] != 0 else 0
    assert 1.8 < ratio < 2.2  # approximately linear


def test_zero_deployment_has_zero_effect():
    """If a tool is set to 0, it should have no curve effect."""
    tools = get_all_tools()
    qt = next(t for t in tools if t.name == ToolName.QT_PACE)
    effects = apply_tool_effect(qt, 0)
    for tenor, value in effects.items():
        assert value == pytest.approx(0, abs=0.01)


def test_forward_guidance_is_boolean():
    """Forward guidance is on/off, not a continuous parameter."""
    tools = get_all_tools()
    fg = next(t for t in tools if t.name == ToolName.FORWARD_GUIDANCE)
    assert fg.min_value == 0
    assert fg.max_value == 1
    # When guidance is removed (value=0), 2Y should increase
    effects_off = apply_tool_effect(fg, 0)
    assert effects_off.get("2y", 0) > 0  # removing guidance increases 2Y
    # When guidance is active (value=1), minimal effect
    effects_on = apply_tool_effect(fg, 1)
    assert abs(effects_on.get("2y", 0)) < 1  # near-zero effect when active
