"""Curve simulation engine — applies QE-without-QE tool effects to the yield curve.

Takes a baseline curve (current yields) and simulates how different combinations
of Warsh's policy tools would change the curve shape. The model is HEURISTIC:
it captures directional effects and relative magnitudes but is not an econometric
model. Designed for visualization and hypothesis testing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.warsh.tools import FedTool, ToolName, apply_tool_effect, get_all_tools
from src.yield_curve.curves import compute_spreads, classify_shape, CurveShape


# All tenors the simulator tracks
ALL_TENORS = ["3mo", "1y", "2y", "5y", "7y", "10y", "20y", "30y"]


@dataclass
class SimulationResult:
    """Output of a curve simulation run."""
    adjusted_curve: dict[str, float]       # tenor -> new yield %
    new_2s10s: float                        # new 2s10s spread in bps
    new_3m10y: float                        # new 3m10y spread in bps
    new_shape: str                          # new curve shape classification
    baseline_2s10s: float                   # original 2s10s for comparison
    delta_2s10s: float                      # change in 2s10s (positive = steepening)
    delta_3m10y: float                      # change in 3m10y
    tool_effects: dict[str, dict[str, float]]  # tool_name -> {tenor: bps_effect}
    scenario_label: str = "custom"


class CurveSimulator:
    """Simulates yield curve changes from Warsh's QE-without-QE toolkit.

    Usage:
        sim = CurveSimulator(current_yields)
        result = sim.simulate(rmp=80, qt_pace=30, forward_guidance=0)
        print(f"New 2s10s: {result.new_2s10s} bps (was {result.baseline_2s10s})")
    """

    def __init__(self, baseline_curve: dict[str, float]):
        """Initialize with current yields.

        Args:
            baseline_curve: Dict mapping tenor name to yield in percent.
                           e.g., {"2y": 4.16, "10y": 4.58, ...}
        """
        self.baseline_curve = dict(baseline_curve)
        self.tools = {t.name: t for t in get_all_tools()}

        # Calculate baseline spreads
        baseline_spreads = compute_spreads(baseline_curve)
        self.baseline_2s10s = baseline_spreads.get("2s10s", 0.0) or 0.0
        self.baseline_3m10y = baseline_spreads.get("3m10y", 0.0) or 0.0

    def simulate(
        self,
        rmp: Optional[float] = None,
        qt_pace: Optional[float] = None,
        srf: Optional[float] = None,
        mbs_sales: Optional[float] = None,
        forward_guidance: Optional[float] = None,
        bank_regulation: Optional[float] = None,
    ) -> SimulationResult:
        """Run a simulation with specified tool parameters.

        Args:
            Each parameter overrides the tool's current_value. If None, uses current.

        Returns:
            SimulationResult with adjusted curve and spread calculations.
        """
        # Build tool value overrides
        overrides = {
            ToolName.RMP: rmp,
            ToolName.QT_PACE: qt_pace,
            ToolName.SRF: srf,
            ToolName.MBS_SALES: mbs_sales,
            ToolName.FORWARD_GUIDANCE: forward_guidance,
            ToolName.BANK_REGULATION: bank_regulation,
        }

        tool_effects: dict[str, dict[str, float]] = {}
        cumulative_bps: dict[str, float] = {t: 0.0 for t in ALL_TENORS}

        for tool_name, override_value in overrides.items():
            tool = self.tools[tool_name]
            value = override_value if override_value is not None else tool.current_value

            baseline_eff = apply_tool_effect(tool, tool.current_value)
            proposed_eff = apply_tool_effect(tool, value)
            delta_eff: dict[str, float] = {}
            for tenor in ALL_TENORS:
                delta_eff[tenor] = proposed_eff.get(tenor, 0.0) - baseline_eff.get(tenor, 0.0)

            tool_effects[tool_name.value] = delta_eff

            for tenor, bps in delta_eff.items():
                cumulative_bps[tenor] = cumulative_bps.get(tenor, 0.0) + bps

        # Apply cumulative effects to baseline yields
        adjusted_curve: dict[str, float] = {}
        for tenor in ALL_TENORS:
            baseline_yield = self.baseline_curve.get(tenor, 4.0)
            bps_adjustment = cumulative_bps.get(tenor, 0.0)
            # Convert bps to percentage points: 1 bp = 0.01%
            adjusted_curve[tenor] = baseline_yield + bps_adjustment / 100.0

        # Calculate new spreads
        new_spreads = compute_spreads(adjusted_curve)
        new_2s10s = new_spreads.get("2s10s", self.baseline_2s10s) or self.baseline_2s10s
        new_3m10y = new_spreads.get("3m10y", self.baseline_3m10y) or self.baseline_3m10y

        # Classify new shape
        new_shape = classify_shape(adjusted_curve)

        return SimulationResult(
            adjusted_curve=adjusted_curve,
            new_2s10s=new_2s10s,
            new_3m10y=new_3m10y,
            new_shape=new_shape.value,
            baseline_2s10s=self.baseline_2s10s,
            delta_2s10s=new_2s10s - self.baseline_2s10s,
            delta_3m10y=new_3m10y - self.baseline_3m10y,
            tool_effects=tool_effects,
        )

    # -- Scenario presets ---------------------------------------------------

    # Preset tool configurations for each hypothesis scenario
    SCENARIO_PRESETS: dict[str, dict] = {
        "hawkish": {
            # Scenario A: genuine hawk — minimal shadow easing
            "rmp": 20,           # minimal RMP
            "qt_pace": 80,       # aggressive QT
            "srf": 500,          # unchanged
            "mbs_sales": 20,     # active MBS selling
            "forward_guidance": 0,  # Warsh removes guidance (his stated goal)
            "bank_regulation": 0.2,  # mostly strict
        },
        "pantomime": {
            # Scenario B: shadow easing from day one
            "rmp": 80,           # heavy RMP
            "qt_pace": 20,       # minimal QT
            "srf": 1000,         # expanded SRF
            "mbs_sales": 0,      # no active selling
            "forward_guidance": 0,  # remove guidance (let market price)
            "bank_regulation": 0.5,  # moderate relaxation
        },
        "dovish": {
            # Scenario C: full dovish pivot (the eventual transition target)
            "rmp": 80,           # heavy RMP
            "qt_pace": 0,        # stop QT entirely
            "srf": 1000,         # expanded SRF
            "mbs_sales": 0,      # no selling
            "forward_guidance": 1,  # keep guidance — dovish Fed guides toward low rates
            "bank_regulation": 0.8,  # significantly relaxed
        },
        "current": {
            # Current real-world deployment (as of July 2026)
            "rmp": 40,
            "qt_pace": 60,
            "srf": 500,
            "mbs_sales": 0,
            "forward_guidance": 1,
            "bank_regulation": 0.3,
        },
    }

    def simulate_scenario(self, scenario: str) -> SimulationResult:
        """Run a simulation using a preset scenario configuration.

        Args:
            scenario: One of "hawkish", "pantomime", "dovish", "current"

        Returns:
            SimulationResult with the scenario label set.
        """
        presets = self.SCENARIO_PRESETS.get(scenario, self.SCENARIO_PRESETS["current"])
        result = self.simulate(**presets)
        result.scenario_label = scenario
        return result
