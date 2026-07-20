"""QE-without-QE tool definitions and curve effect models.

Each tool represents one of Warsh's alternate monetary policy instruments.
Curve effects are HEURISTIC — directionally correct based on market mechanics,
but not econometrically rigorous. Designed for visualization and hypothesis testing.

Effect convention: negative = yield DECREASE, positive = yield INCREASE.
Effects are measured in basis points (bps).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ToolName(str, Enum):
    """The six QE-without-QE tools in Warsh's toolkit."""
    RMP = "rmp"                    # Reserves Management Purchases
    QT_PACE = "qt_pace"            # Quantitative Tightening pace
    SRF = "srf"                    # Standing Repo Facility
    MBS_SALES = "mbs_sales"        # MBS sales (balance sheet composition)
    FORWARD_GUIDANCE = "fg"        # Forward guidance strength
    BANK_REGULATION = "bank_reg"   # Bank regulation index


@dataclass(frozen=True)
class FedTool:
    """Definition of one Fed policy tool and its curve effects.

    Attributes:
        name: Tool identifier
        display_name: Human-readable name for the UI
        description: What the tool does (1-2 sentences)
        min_value: Minimum adjustable value
        max_value: Maximum adjustable value
        current_value: Current real-world deployment level
        unit: Display unit (e.g., "$B/month", "on/off", "index 0-1")
        curve_effects: Dict mapping tenor -> (effect_per_unit_bps, is_boolean)
                       effect_per_unit_bps: how many bps per unit of deployment
                       is_boolean: if True, value is 0 or 1 (on/off)
        political_cover: What Warsh calls it publicly
    """
    name: ToolName
    display_name: str
    description: str
    min_value: float
    max_value: float
    current_value: float
    unit: str
    curve_effects: dict[str, float]  # tenor -> bps effect per unit
    political_cover: str = ""
    is_boolean: bool = False


def apply_tool_effect(tool: FedTool, value: float) -> dict[str, float]:
    """Calculate the curve effect (in bps) for a given tool at a given deployment level.

    Args:
        tool: The Fed tool definition
        value: The deployment level (e.g., $40B/month for RMP)

    Returns:
        Dict mapping tenor -> effect in bps (negative = yield decrease)
    """
    effects: dict[str, float] = {}

    if tool.is_boolean:
        # Boolean tools: effect depends on on/off state
        if tool.name == ToolName.FORWARD_GUIDANCE:
            if value < 0.5:
                # Forward guidance REMOVED — 2Y rises from term premium returning
                effects = {"2y": 8.0, "1y": 5.0, "5y": 3.0}
            else:
                # Forward guidance ACTIVE — minimal effect (baseline assumption)
                effects = {"2y": 0.0, "1y": 0.0, "5y": 0.0}
            return effects

    # Continuous tools: linear scaling
    for tenor, bps_per_unit in tool.curve_effects.items():
        effects[tenor] = bps_per_unit * value

    return effects


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

# Effect coefficients: how many bps of yield change per unit of deployment.
# These are HEURISTIC estimates based on market transmission mechanics.
# Tuned so that "current" deployment levels produce reasonable curve effects.

_RMP_EFFECTS = {
    # RMP buys T-bills — suppresses short-end yields
    # Per $10B/month: 3M drops ~2bps, 1Y drops ~1bp, 2Y drops ~0.5bps
    "3mo": -0.20,   # -2bps per $10B
    "1y": -0.10,    # -1bp per $10B
    "2y": -0.05,    # -0.5bps per $10B
}

_QT_EFFECTS = {
    # QT lets Treasuries/MBS roll off — upward pressure on yields
    # Per $10B/month: 10Y rises ~1.5bps, 30Y rises ~2bps, 5Y rises ~0.8bps
    "2y": 0.03,     # minimal effect on short end
    "5y": 0.08,
    "7y": 0.12,
    "10y": 0.15,    # +1.5bps per $10B
    "20y": 0.18,
    "30y": 0.20,    # +2bps per $10B
}

_SRF_EFFECTS = {
    # SRF provides backstop liquidity — reduces short-end stress
    # Per $100B increase in daily cap
    "3mo": -0.01,
    "1y": -0.005,
}

_MBS_SALES_EFFECTS = {
    # Selling MBS, buying Treasuries with proceeds
    # Net effect: slight Treasury demand support at 7-10Y
    # Per $10B/month of MBS sales
    "7y": -0.05,
    "10y": -0.05,
}

_BANK_REG_EFFECTS = {
    # Regulation relaxation index (0=strict, 1=relaxed)
    # Per 0.1 increase in relaxation index
    "2y": 0.05,     # short end rises slightly (growth expectations)
    "5y": 0.08,
    "10y": 0.10,
    "30y": 0.12,    # long end rises more (growth + inflation expectations)
    # Net effect: curve STEEPENS
}


def get_all_tools() -> list[FedTool]:
    """Return all six QE-without-QE tools with current deployment levels."""
    return [
        FedTool(
            name=ToolName.RMP,
            display_name="Reserves Management Purchases",
            description=(
                "Fed buys short-term T-bills to maintain 'ample reserves' in the "
                "banking system. Suppresses short-end yields without cutting the "
                "policy rate. The primary 'QE without QE' tool."
            ),
            min_value=0,
            max_value=100,
            current_value=40,
            unit="$B/month",
            curve_effects=_RMP_EFFECTS,
            political_cover="Technical operation to maintain ample reserves",
        ),
        FedTool(
            name=ToolName.QT_PACE,
            display_name="QT Pace (Balance Sheet Runoff)",
            description=(
                "Monthly pace of Treasury + MBS runoff from the Fed's $6.7T "
                "balance sheet. Higher pace = more selling pressure on bonds = "
                "higher yields. Slowing QT is functionally easing."
            ),
            min_value=0,
            max_value=95,
            current_value=60,
            unit="$B/month",
            curve_effects=_QT_EFFECTS,
            political_cover="Data-dependent balance sheet normalization",
        ),
        FedTool(
            name=ToolName.SRF,
            display_name="Standing Repo Facility Cap",
            description=(
                "Maximum daily repo the Fed offers to primary dealers. Higher cap "
                "= stronger backstop = lower short-term funding stress. Currently "
                "capped at $500B/day."
            ),
            min_value=0,
            max_value=2000,
            current_value=500,
            unit="$B/day cap",
            curve_effects=_SRF_EFFECTS,
            political_cover="Operational liquidity backstop",
        ),
        FedTool(
            name=ToolName.MBS_SALES,
            display_name="MBS Sales (Composition Shift)",
            description=(
                "Active selling of mortgage-backed securities, using proceeds to "
                "buy Treasuries. Warsh's stated goal: exit MBS entirely. Shifts "
                "demand toward government debt without expanding balance sheet."
            ),
            min_value=0,
            max_value=35,
            current_value=0,
            unit="$B/month",
            curve_effects=_MBS_SALES_EFFECTS,
            political_cover="Balance sheet composition optimization",
        ),
        FedTool(
            name=ToolName.FORWARD_GUIDANCE,
            display_name="Forward Guidance",
            description=(
                "Explicit Fed communication about future rate path (dot plot, "
                "threshold-based guidance). Warsh wants to REDUCE this — let "
                "markets price risk themselves. Removing guidance raises 2Y as "
                "term premium returns."
            ),
            min_value=0,
            max_value=1,
            current_value=1,
            unit="on/off (1=active, 0=removed)",
            curve_effects={},  # handled specially in apply_tool_effect
            political_cover="Market-based rate discovery",
            is_boolean=True,
        ),
        FedTool(
            name=ToolName.BANK_REGULATION,
            display_name="Bank Regulation Index",
            description=(
                "Index of bank regulation strictness (0=Dodd-Frank strict, "
                "1=fully relaxed). Less regulation = more lending = credit "
                "expansion = curve steepens from growth expectations. Warsh "
                "has written that Dodd-Frank went too far."
            ),
            min_value=0,
            max_value=1,
            current_value=0.3,
            unit="index (0=strict, 1=relaxed)",
            curve_effects=_BANK_REG_EFFECTS,
            political_cover="Financial system efficiency",
        ),
    ]
