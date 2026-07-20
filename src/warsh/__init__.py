"""Warsh Framework Simulator — QE-without-QE toolkit modeling.

Heuristic simulation of Fed Chair Kevin Warsh's alternate monetary policy
tools and their effects on the Treasury yield curve. Not econometrically
rigorous — designed for directional visualization and hypothesis testing.

Extended with:
- events: X-factor and black swan market shocks
- gamification: Fed Chair rating system + scenario matching
"""
from src.warsh.tools import FedTool, ToolName, get_all_tools
from src.warsh.simulator import CurveSimulator, SimulationResult
from src.warsh.events import MarketEvent, roll_event, apply_event_to_curve, get_all_events
from src.warsh.gamification import (
    rate_fed_chair,
    calculate_scenario_match,
    get_market_prediction,
)

__all__ = [
    "FedTool",
    "ToolName",
    "get_all_tools",
    "CurveSimulator",
    "SimulationResult",
    "MarketEvent",
    "roll_event",
    "apply_event_to_curve",
    "get_all_events",
    "rate_fed_chair",
    "calculate_scenario_match",
    "get_market_prediction",
]
