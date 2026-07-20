# Warsh Toolkit Deep-Dive + Interactive Simulator + Positioning Playbook

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an interactive Streamlit web app that lets you simulate Fed Chair Warsh's "QE without QE" toolkit, visualize the resulting yield curve changes, and map each scenario to a concrete positioning playbook for aligning with smart money.

**Architecture:** Three-layer: (1) a testable Python simulation model that defines each Fed tool and its curve effects, (2) a Streamlit presentation layer with interactive sliders and Plotly charts, (3) documentation covering the toolkit deep-dive and the positioning playbook. The simulation model is the core — it's pure Python with pytest coverage. The Streamlit app is the visualization layer on top.

**Tech Stack:** Python 3.10+, Streamlit (to install), Plotly 6.7.0 (already installed), pandas, pytest. Integrates with existing `src/yield_curve/` modules for live FRED data and `scripts/warsh_hypothesis_tracker.py` for scenario state.

**Design spec:** `docs/superpowers/analysis/2026-07-15-warsh-framework-hypotheses.md`

---

## Global Constraints

- Python 3.10+ required (existing project standard)
- Streamlit must be installed: `pip install streamlit>=1.45.0`
- All curve effects are HEURISTIC models (directionally correct, not econometrically rigorous)
- App runs locally via `streamlit run scripts/warsh_dashboard.py`
- Integrates with existing `src/yield_curve/fetcher.py` for live FRED data
- Integrates with existing `data/warsh_hypotheses.json` for scenario state
- Plotly for all charts (already installed, v6.7.0)

---

## File Structure

```
src/warsh/                           — Simulation model (testable)
  __init__.py                        — Package init + exports
  tools.py                           — QE-without-QE tool definitions + curve effects
  simulator.py                       — Curve simulation engine
scripts/warsh_dashboard.py           — Streamlit interactive web app
tests/warsh/                         — Tests for simulation model
  __init__.py
  test_tools.py                      — Tool definition + effect tests
  test_simulator.py                  — Simulation engine tests
docs/superpowers/analysis/
  2026-07-19-warsh-toolkit-deep-dive.md    — Deep dive on each tool
  2026-07-19-positioning-playbook.md       — Smart money positioning by scenario
```

---

## Task 1: Install Streamlit + create package skeleton

**Files:**
- Modify: `requirements-lite.txt` — add `streamlit>=1.45.0`
- Create: `src/warsh/__init__.py`
- Create: `tests/warsh/__init__.py`

- [ ] **Step 1:** Add streamlit to requirements:
```bash
echo "streamlit>=1.45.0" >> requirements-lite.txt
pip install streamlit>=1.45.0
```

- [ ] **Step 2:** Create `src/warsh/__init__.py`:
```python
"""Warsh Framework Simulator — QE-without-QE toolkit modeling.

Heuristic simulation of Fed Chair Kevin Warsh's alternate monetary policy
tools and their effects on the Treasury yield curve. Not econometrically
rigorous — designed for directional visualization and hypothesis testing.
"""
from src.warsh.tools import FedTool, ToolName, get_all_tools
from src.warsh.simulator import CurveSimulator, SimulationResult

__all__ = ["FedTool", "ToolName", "get_all_tools", "CurveSimulator", "SimulationResult"]
```

- [ ] **Step 3:** Create `tests/warsh/__init__.py` (empty file).

- [ ] **Step 4:** Verify streamlit imports:
```bash
python -c "import streamlit; print(f'Streamlit {streamlit.__version__}')"
```
Expected: prints version without error.

- [ ] **Step 5:** Commit:
```bash
git add requirements-lite.txt src/warsh/__init__.py tests/warsh/__init__.py
git commit -m "feat(warsh): add streamlit dependency + package skeleton"
```

---

## Task 2: QE-without-QE tool definitions (TDD)

**Files:**
- Create: `src/warsh/tools.py`
- Create: `tests/warsh/test_tools.py`

**Interfaces:**
- Produces: `FedTool` dataclass, `ToolName` enum, `get_all_tools()` function, `apply_tool_effect()` function

- [ ] **Step 1:** Write failing tests in `tests/warsh/test_tools.py`:
```python
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
```

- [ ] **Step 2:** Run tests to confirm failure:
```bash
pytest tests/warsh/test_tools.py -v
```
Expected: ImportError.

- [ ] **Step 3:** Create `src/warsh/tools.py`:
```python
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
```

- [ ] **Step 4:** Run tests:
```bash
pytest tests/warsh/test_tools.py -v
```
Expected: 7 passed.

- [ ] **Step 5:** Commit:
```bash
git add src/warsh/tools.py tests/warsh/test_tools.py
git commit -m "feat(warsh): QE-without-QE tool definitions with heuristic curve effects + tests"
```

---

## Task 3: Curve simulation engine (TDD)

**Files:**
- Create: `src/warsh/simulator.py`
- Create: `tests/warsh/test_simulator.py`

**Interfaces:**
- Consumes: `FedTool`, `apply_tool_effect()`, `get_all_tools()` from Task 2
- Consumes: `compute_spreads()`, `classify_shape()` from `src/yield_curve/curves.py`
- Produces: `CurveSimulator` class, `SimulationResult` dataclass

- [ ] **Step 1:** Write failing tests in `tests/warsh/test_simulator.py`:
```python
"""Tests for the curve simulation engine."""
import pytest
from src.warsh.simulator import CurveSimulator, SimulationResult


# Baseline yields for testing (approximate July 2026 levels)
BASELINE_CURVE = {
    "3mo": 3.84, "1y": 4.02, "2y": 4.16, "5y": 4.31,
    "7y": 4.44, "10y": 4.58, "20y": 5.09, "30y": 5.08,
}


def test_simulator_initializes_with_baseline():
    sim = CurveSimulator(BASELINE_CURVE)
    assert sim.baseline_2s10s is not None
    assert sim.baseline_2s10s == pytest.approx(42, abs=5)  # ~40-45bps


def test_simulator_with_current_tools_reproduces_baseline():
    """Running simulation at current tool values should approximately reproduce baseline."""
    sim = CurveSimulator(BASELINE_CURVE)
    result = sim.simulate()  # uses current tool values
    # At current deployment, net effect should be small (market already priced)
    assert abs(result.new_2s10s - sim.baseline_2s10s) < 15  # within 15bps


def test_aggressive_rmp_steepens_curve():
    """Maximizing RMP (buying more T-bills) should reduce 2Y more than 10Y."""
    sim = CurveSimulator(BASELINE_CURVE)
    result = sim.simulate(rmp=100, qt_pace=60, srf=500, mbs_sales=0, forward_guidance=1, bank_regulation=0.3)
    # High RMP suppresses 2Y → 2s10s should be higher than baseline
    assert result.new_2s10s > sim.baseline_2s10s


def test_zero_qt_steepens_curve():
    """Stopping QT (pace=0) should reduce long-end yields, steepening curve."""
    sim = CurveSimulator(BASELINE_CURVE)
    result = sim.simulate(rmp=40, qt_pace=0, srf=500, mbs_sales=0, forward_guidance=1, bank_regulation=0.3)
    assert result.new_2s10s > sim.baseline_2s10s


def test_removing_forward_guidance_increases_2y():
    """Removing forward guidance should push 2Y up (term premium returns)."""
    sim = CurveSimulator(BASELINE_CURVE)
    result = sim.simulate(rmp=40, qt_pace=60, srf=500, mbs_sales=0, forward_guidance=0, bank_regulation=0.3)
    assert result.adjusted_curve["2y"] > BASELINE_CURVE["2y"]


def test_relaxed_bank_regulation_steepens():
    """Relaxing bank regulation (index → 1) should steepen the curve."""
    sim = CurveSimulator(BASELINE_CURVE)
    result_relaxed = sim.simulate(rmp=40, qt_pace=60, srf=500, mbs_sales=0, forward_guidance=1, bank_regulation=1.0)
    result_strict = sim.simulate(rmp=40, qt_pace=60, srf=500, mbs_sales=0, forward_guidance=1, bank_regulation=0.0)
    assert result_relaxed.new_2s10s > result_strict.new_2s10s


def test_simulation_result_has_all_fields():
    sim = CurveSimulator(BASELINE_CURVE)
    result = sim.simulate()
    assert hasattr(result, "adjusted_curve")
    assert hasattr(result, "new_2s10s")
    assert hasattr(result, "new_3m10y")
    assert hasattr(result, "new_shape")
    assert hasattr(result, "delta_2s10s")
    assert hasattr(result, "tool_effects")
    assert len(result.adjusted_curve) == len(BASELINE_CURVE)


def test_scenario_preset_dovish():
    """The 'dovish' preset should steepen the curve significantly."""
    sim = CurveSimulator(BASELINE_CURVE)
    result = sim.simulate_scenario("dovish")
    assert result.delta_2s10s > 10  # at least 10bps steeper than baseline


def test_scenario_preset_hawkish():
    """The 'hawkish' preset should flatten the curve or keep it flat."""
    sim = CurveSimulator(BASELINE_CURVE)
    result = sim.simulate_scenario("hawkish")
    assert result.delta_2s10s < 5  # minimal steepening or flattening


def test_scenario_preset_current():
    """The 'current' preset should approximately reproduce baseline."""
    sim = CurveSimulator(BASELINE_CURVE)
    result = sim.simulate_scenario("current")
    assert abs(result.delta_2s10s) < 15  # within 15bps of baseline
```

- [ ] **Step 2:** Run tests to confirm failure:
```bash
pytest tests/warsh/test_simulator.py -v
```
Expected: ImportError.

- [ ] **Step 3:** Create `src/warsh/simulator.py`:
```python
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

        # Calculate cumulative effect on each tenor
        tool_effects: dict[str, dict[str, float]] = {}
        cumulative_bps: dict[str, float] = {t: 0.0 for t in ALL_TENORS}

        for tool_name, override_value in overrides.items():
            tool = self.tools[tool_name]
            value = override_value if override_value is not None else tool.current_value
            effects = apply_tool_effect(tool, value)

            tool_effects[tool_name.value] = dict(effects)

            for tenor, bps in effects.items():
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
            "forward_guidance": 1,  # keep guidance (hawkish commitment)
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
            "forward_guidance": 0,  # remove guidance
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
```

- [ ] **Step 4:** Run tests:
```bash
pytest tests/warsh/test_simulator.py -v
```
Expected: 10 passed.

- [ ] **Step 5:** Commit:
```bash
git add src/warsh/simulator.py tests/warsh/test_simulator.py
git commit -m "feat(warsh): curve simulation engine with scenario presets + tests"
```

---

## Task 4: Streamlit interactive dashboard

**Files:**
- Create: `scripts/warsh_dashboard.py`

**Interfaces:**
- Consumes: `CurveSimulator`, `SimulationResult` from Task 3
- Consumes: `get_all_tools()`, `FedTool`, `ToolName` from Task 2
- Consumes: `FredCurveFetcher` from `src/yield_curve/fetcher.py`

- [ ] **Step 1:** Create `scripts/warsh_dashboard.py`:
```python
"""Warsh Scenario Simulator — Interactive Streamlit Dashboard.

Run with:
    streamlit run scripts/warsh_dashboard.py

Lets you:
1. Adjust each QE-without-QE tool via sliders
2. See the resulting yield curve in real-time
3. Compare with current FRED data
4. Load preset scenarios (hawkish/pantomime/dovish/current)
5. See which hypothesis the simulation supports
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import streamlit as st
import plotly.graph_objects as go
import pandas as pd

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.warsh.tools import ToolName, get_all_tools
from src.warsh.simulator import CurveSimulator, ALL_TENORS


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Warsh Scenario Simulator",
    page_icon="🏦",
    layout="wide",
)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


@st.cache_data(ttl=3600)
def load_current_curve() -> dict[str, float]:
    """Fetch current Treasury yields from FRED."""
    try:
        from src.yield_curve.fetcher import FredCurveFetcher
        f = FredCurveFetcher()
        today = date.today()
        data = f.fetch_tenors(ALL_TENORS, today - timedelta(days=10), today)
        curve = {}
        for tenor, df in data.items():
            if not df.empty:
                curve[tenor] = float(df.iloc[-1]["close"])
        return curve if curve else get_fallback_curve()
    except Exception:
        return get_fallback_curve()


def get_fallback_curve() -> dict[str, float]:
    """Approximate July 2026 yields if FRED is unavailable."""
    return {
        "3mo": 3.84, "1y": 4.02, "2y": 4.16, "5y": 4.31,
        "7y": 4.44, "10y": 4.58, "20y": 5.09, "30y": 5.08,
    }


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

st.title("🏦 Warsh Scenario Simulator")
st.markdown("**Interactive simulation of Fed Chair Warsh's 'QE without QE' toolkit**")
st.markdown("Adjust the sliders to see how each policy tool affects the yield curve.")

# Load baseline
baseline_curve = load_current_curve()
sim = CurveSimulator(baseline_curve)
tools = {t.name: t for t in get_all_tools()}

# ---------------------------------------------------------------------------
# Sidebar: Scenario presets + tool controls
# ---------------------------------------------------------------------------

st.sidebar.markdown("## 🎛️ Policy Tools")

# Scenario preset buttons
st.sidebar.markdown("### Quick Scenarios")
preset = st.sidebar.selectbox(
    "Load preset:",
    ["custom", "current", "hawkish", "pantomime", "dovish"],
    index=1,
    help="Hawkish=Scenario A, Pantomime=Scenario B, Dovish=Scenario C (full pivot)",
)

# Initialize session state for tool values
if "tool_values" not in st.session_state:
    st.session_state.tool_values = {
        ToolName.RMP: 40,
        ToolName.QT_PACE: 60,
        ToolName.SRF: 500,
        ToolName.MBS_SALES: 0,
        ToolName.FORWARD_GUIDANCE: 1,
        ToolName.BANK_REGULATION: 0.3,
    }

# Apply preset
if preset != "custom":
    presets = CurveSimulator.SCENARIO_PRESETS.get(preset, {})
    if presets:
        st.session_state.tool_values[ToolName.RMP] = presets["rmp"]
        st.session_state.tool_values[ToolName.QT_PACE] = presets["qt_pace"]
        st.session_state.tool_values[ToolName.SRF] = presets["srf"]
        st.session_state.tool_values[ToolName.MBS_SALES] = presets["mbs_sales"]
        st.session_state.tool_values[ToolName.FORWARD_GUIDANCE] = presets["forward_guidance"]
        st.session_state.tool_values[ToolName.BANK_REGULATION] = presets["bank_regulation"]

st.sidebar.markdown("---")

# Tool sliders
for tool in get_all_tools():
    current = st.session_state.tool_values.get(tool.name, tool.current_value)
    if tool.is_boolean:
        val = st.sidebar.selectbox(
            f"{tool.display_name}",
            ["Active (1)", "Removed (0)"],
            index=0 if current >= 0.5 else 1,
            help=tool.description,
        )
        st.session_state.tool_values[tool.name] = 1.0 if "Active" in val else 0.0
    else:
        val = st.sidebar.slider(
            f"{tool.display_name}",
            min_value=float(tool.min_value),
            max_value=float(tool.max_value),
            value=float(current),
            help=f"{tool.description}\n\nCurrent: {tool.current_value} {tool.unit}",
        )
        st.session_state.tool_values[tool.name] = val

    # Show political cover
    st.sidebar.caption(f"💬 _{tool.political_cover}_")

# ---------------------------------------------------------------------------
# Run simulation
# ---------------------------------------------------------------------------

result = sim.simulate(
    rmp=st.session_state.tool_values[ToolName.RMP],
    qt_pace=st.session_state.tool_values[ToolName.QT_PACE],
    srf=st.session_state.tool_values[ToolName.SRF],
    mbs_sales=st.session_state.tool_values[ToolName.MBS_SALES],
    forward_guidance=st.session_state.tool_values[ToolName.FORWARD_GUIDANCE],
    bank_regulation=st.session_state.tool_values[ToolName.BANK_REGULATION],
)

# ---------------------------------------------------------------------------
# Main area: metrics + charts
# ---------------------------------------------------------------------------

col1, col2, col3, col4 = st.columns(4)

with col1:
    delta_color = "inverse" if result.delta_2s10s < 0 else "off"
    st.metric(
        "2s10s Spread",
        f"{result.new_2s10s:.0f} bps",
        delta=f"{result.delta_2s10s:+.1f} bps",
    )
with col2:
    st.metric(
        "3m10y Spread",
        f"{result.new_3m10y:.0f} bps",
        delta=f"{result.delta_3m10y:+.1f} bps",
    )
with col3:
    st.metric("Curve Shape", result.new_shape)
with col4:
    st.metric(
        "Baseline 2s10s",
        f"{result.baseline_2s10s:.0f} bps",
    )

st.markdown("---")

# ---------------------------------------------------------------------------
# Curve chart
# ---------------------------------------------------------------------------

col_chart, col_info = st.columns([3, 1])

with col_chart:
    st.subheader("📊 Yield Curve Comparison")

    tenor_labels = ["3M", "1Y", "2Y", "5Y", "7Y", "10Y", "20Y", "30Y"]
    baseline_yields = [baseline_curve.get(t, 0) for t in ALL_TENORS]
    simulated_yields = [result.adjusted_curve.get(t, 0) for t in ALL_TENORS]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=tenor_labels,
        y=baseline_yields,
        mode="lines+markers",
        name="Current (FRED)",
        line=dict(color="rgb(100, 149, 237)", width=2),
    ))
    fig.add_trace(go.Scatter(
        x=tenor_labels,
        y=simulated_yields,
        mode="lines+markers",
        name="Simulated",
        line=dict(color="rgb(255, 165, 0)", width=2, dash="dash"),
    ))
    fig.update_layout(
        xaxis_title="Maturity",
        yaxis_title="Yield (%)",
        yaxis=dict(range=[3.0, 6.0]),
        height=450,
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

with col_info:
    st.subheader("📋 Tool Effects")

    for tool_name_str, effects in result.tool_effects.items():
        # Get display name
        tool = next((t for t in get_all_tools() if t.name.value == tool_name_str), None)
        if tool and effects:
            nonzero = {k: v for k, v in effects.items() if abs(v) > 0.01}
            if nonzero:
                st.markdown(f"**{tool.display_name}**")
                for tenor, bps in sorted(nonzero.items()):
                    direction = "📈" if bps > 0 else "📉"
                    st.text(f"  {tenor}: {direction} {bps:+.1f} bps")

# ---------------------------------------------------------------------------
# Scenario assessment
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("🎯 Scenario Assessment")

if result.delta_2s10s > 15:
    st.success(
        f"**Significant steepening (+{result.delta_2s10s:.0f}bps).** "
        f"This simulation supports **Scenario B (Pantomime)** or "
        f"**Scenario C (Transition to dovish)**. "
        f"The toolkit configuration is providing meaningful accommodation."
    )
elif result.delta_2s10s > 5:
    st.info(
        f"**Moderate steepening (+{result.delta_2s10s:.0f}bps).** "
        f"This is consistent with a gradual pivot toward accommodation. "
        f"Consistent with **Scenario C (Transition)**."
    )
elif result.delta_2s10s > -5:
    st.warning(
        f"**Curve roughly unchanged ({result.delta_2s10s:+.0f}bps).** "
        f"The toolkit configuration is approximately neutral. "
        f"Consistent with the current status quo."
    )
else:
    st.error(
        f"**Curve flattening ({result.delta_2s10s:+.0f}bps).** "
        f"This simulation tightens conditions. "
        f"Consistent with **Scenario A (Genuine Hawk)**."
    )

# ---------------------------------------------------------------------------
# Positioning implications
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("💼 Positioning Implications")

col_a, col_b, col_c = st.columns(3)

with col_a:
    st.markdown("#### If Scenario A (Hawk)")
    st.markdown("- **Own**: Cash, short-duration bonds, USD")
    st.markdown("- **Avoid**: Long bonds, small caps, EM, crypto")
    st.markdown("- **Curve**: Stays flat at +30-50bps")
    st.markdown("- **Timeline**: Value rotation 12-18+ months away")

with col_b:
    st.markdown("#### If Scenario B (Pantomime)")
    st.markdown("- **Own**: Gold, BTC, value stocks, small caps")
    st.markdown("- **Avoid**: Long-duration bonds, USD")
    st.markdown("- **Curve**: Steepens to +60-80bps fast")
    st.markdown("- **Timeline**: Value rotation in 3-6 months")

with col_c:
    st.markdown("#### If Scenario C (Transition)")
    st.markdown("- **Own**: Quality value (INTU, ADBE, MSFT on dips)")
    st.markdown("- **Avoid**: Chasing momentum (MU, NVDA at highs)")
    st.markdown("- **Curve**: Flat then steepens in 6-12 months")
    st.markdown("- **Timeline**: Value rotation mid-late 2027")

st.markdown("---")
st.caption(
    "⚠️ This is a heuristic simulation for educational purposes. "
    "Curve effects are approximate. Not investment advice. "
    "Data from FRED (Federal Reserve Economic Data)."
)
```

- [ ] **Step 2:** Test the app runs:
```bash
streamlit run scripts/warsh_dashboard.py --server.headless true &
sleep 5
curl -s http://localhost:8501/_stcore/health
kill %1
```
Expected: returns "ok".

- [ ] **Step 3:** Commit:
```bash
git add scripts/warsh_dashboard.py
git commit -m "feat(warsh): interactive Streamlit dashboard for QE-without-QE simulation"
```

---

## Task 5: Warsh toolkit deep-dive documentation

**Files:**
- Create: `docs/superpowers/analysis/2026-07-19-warsh-toolkit-deep-dive.md`

- [ ] **Step 1:** Create the deep-dive document covering each of the 6 tools in detail:
    - What it does mechanically
    - Which part of the curve it affects and why
    - The heuristic effect model (bps per unit)
    - Current deployment level
    - Warsh's political cover language
    - Historical precedent (has this tool been used before?)
    - How to detect if Warsh is deploying it (the signal to watch)

- [ ] **Step 2:** Commit:
```bash
git add docs/superpowers/analysis/2026-07-19-warsh-toolkit-deep-dive.md
git commit -m "docs(warsh): deep-dive on QE-without-QE toolkit — 6 tools explained"
```

---

## Task 6: Smart money positioning playbook

**Files:**
- Create: `docs/superpowers/analysis/2026-07-19-positioning-playbook.md`

- [ ] **Step 1:** Create the positioning playbook covering:
    - For each scenario (A/B/C): specific asset allocation
    - Smart money signals to watch (bond positioning, CFTC data, ETF flows)
    - The "trigger levels" for deploying capital (which curve levels = which action)
    - Historical parallels (Greenspan 1987, Bernanke 2008)
    - Risk management framework (position sizing by curve level)
    - The user's specific holdings mapped to each scenario

- [ ] **Step 2:** Commit:
```bash
git add docs/superpowers/analysis/2026-07-19-positioning-playbook.md
git commit -m "docs(warsh): smart money positioning playbook by scenario"
```

---

## Self-Review

**Spec coverage:**
- ✅ "write up more in depth about his alternate tools" → Task 5 (deep-dive doc) + Task 2 (tool definitions with descriptions)
- ✅ "make something to help visualize and play with it" → Task 4 (Streamlit dashboard)
- ✅ "test out our hypothesis with a web app" → Task 4 (scenario presets + live assessment)
- ✅ "plan around if he will do that" → Task 6 (positioning playbook)
- ✅ "align our position with the smart money" → Task 6 (smart money signals)

**Placeholder scan:** No TBDs or TODOs. All code blocks are complete.

**Type consistency:** `FedTool`, `ToolName`, `apply_tool_effect()`, `CurveSimulator`, `SimulationResult` — all used consistently across tasks.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-07-19-warsh-simulator.md`.**

Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** — Execute tasks in this session, batch execution with checkpoints

Which approach?