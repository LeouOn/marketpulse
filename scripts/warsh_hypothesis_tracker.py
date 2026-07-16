"""Warsh Framework Hypothesis Tracker

Tracks three competing hypotheses about Fed Chair Kevin Warsh's monetary policy
trajectory, with Bayesian-style probability updates based on observable signals.

Usage:
    python scripts/warsh_hypothesis_tracker.py              # Current state
    python scripts/warsh_hypothesis_tracker.py --update      # Pull latest curve data
    python scripts/warsh_hypothesis_tracker.py --signal "event description" --scenario C --direction confirm
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Hypothesis definitions
# ---------------------------------------------------------------------------


@dataclass
class Signal:
    """A piece of evidence that confirms or denies a hypothesis."""
    date: str
    description: str
    hypothesis: str  # "A", "B", or "C"
    direction: str   # "confirm" or "deny"
    weight: float    # 0.0-1.0, how strongly this signal affects probability
    source: str = ""


@dataclass
class Hypothesis:
    """A competing explanation for Warsh's policy trajectory."""
    key: str  # "A", "B", "C"
    name: str
    description: str
    probability: float  # 0.0-1.0
    confirming_signals: list[str] = field(default_factory=list)
    denying_signals: list[str] = field(default_factory=list)
    curve_implication: str = ""
    timeline: str = ""


@dataclass
class TrackerState:
    """Full state of the hypothesis tracker."""
    last_updated: str
    curve_2s10s: Optional[float] = None
    curve_3m10y: Optional[float] = None
    curve_shape: Optional[str] = None
    recession_prob: Optional[float] = None
    hypotheses: list[Hypothesis] = field(default_factory=list)
    signals: list[Signal] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Initial state — July 15, 2026 analysis session
# ---------------------------------------------------------------------------


def initial_state() -> TrackerState:
    """Create the initial hypothesis state from our July 15 analysis."""
    return TrackerState(
        last_updated="2026-07-15",
        curve_2s10s=40.0,
        curve_3m10y=74.0,
        curve_shape="NORMAL",
        recession_prob=0.018,
        hypotheses=[
            Hypothesis(
                key="A",
                name="Genuine Hawk",
                description=(
                    "Warsh truly believes in fighting inflation and the 2% target. "
                    "His rhetoric is not theater. Balance sheet shrinks aggressively. "
                    "QT continues. Rates stay higher for longer."
                ),
                probability=0.35,
                confirming_signals=[
                    "Balance sheet panel recommends aggressive QT with explicit size targets",
                    "Warsh raises rates or holds firm despite political pressure",
                    "Reserves management purchases remain minimal/temporary",
                    "Powell (as governor) votes against easing",
                    "Warsh maintains pure hawkish stance for 12+ months",
                ],
                denying_signals=[
                    "Warsh pivots to 'ample reserves' language without targets",
                    "QT slows or pauses before balance sheet reaches targets",
                    "Any rate cut within 6 months despite hawkish rhetoric",
                    "Reserves management purchases expand significantly",
                ],
                curve_implication="2s10s stays flat at +30-50bps for 12-18 months",
                timeline="Value rotation delayed 12-18+ months",
            ),
            Hypothesis(
                key="B",
                name="Pantomime (Hawkish Talk, Dovish Action)",
                description=(
                    "Warsh was appointed to SOUND hawkish while DOING dovish. "
                    "Shadow easing through reserves management, expanded repo, slowed QT. "
                    "The hawkish rhetoric provides political cover."
                ),
                probability=0.20,
                confirming_signals=[
                    "Balance sheet panel recommends 'ample reserves' without targets",
                    "Reserves management purchases expand and become permanent",
                    "QT slows dramatically or pauses",
                    "Standing repo facility expanded significantly",
                    "Warsh's language shifts from 'fighting inflation' to 'sustaining expansion'",
                ],
                denying_signals=[
                    "Warsh raises rates or tightens policy materially",
                    "Balance sheet shrinks toward $5T",
                    "Inflation drops below 2.5% AND Warsh still holds rates",
                ],
                curve_implication="2s10s steepens to +60-80bps within 3-6 months",
                timeline="Value rotation begins in 3-6 months",
            ),
            Hypothesis(
                key="C",
                name="Transition (Hawkish Now, Dovish Later)",
                description=(
                    "Warsh starts hawkish to establish credibility and independence. "
                    "Over 6-12 months, fiscal reality + political pressure + AI capex needs "
                    "force a pragmatic pivot. The 2% target becomes fiction. "
                    "Inflation drifts to 3-3.5% through tolerance."
                ),
                probability=0.45,
                confirming_signals=[
                    "Balance sheet panel recommends gradual QT with 'flexible' framework",
                    "Warsh's language gradually softens over 3-6 months",
                    "Reserves management purchases start small but grow",
                    "Warsh begins emphasizing 'growth' alongside 'inflation'",
                    "Rate hold language shifts from 'higher for longer' to 'patient'",
                ],
                denying_signals=[
                    "Warsh maintains pure hawkish stance for 12+ months",
                    "Balance sheet shrinks aggressively toward $5T",
                    "No expansion of reserves management purchases",
                    "Warsh explicitly rules out any form of QE or easing",
                ],
                curve_implication="2s10s flat at +30-50 for 3-6mo, then steepens to +60-100",
                timeline="Value rotation begins mid-to-late 2027",
            ),
        ],
        signals=[
            Signal(
                date="2026-07-14",
                description=(
                    "Warsh's first congressional testimony: defended 2% target, "
                    "criticized past Chairs, pledged 'regime change'. Markets initially "
                    "rallied day after appointment (calling bluff) but Warsh doubled down."
                ),
                hypothesis="A",
                direction="confirm",
                weight=0.10,
                source="CNN, CNBC, Fed.gov testimony",
            ),
            Signal(
                date="2026-07-14",
                description=(
                    "Warsh assembled balance sheet review panel — provides institutional "
                    "cover for eventual policy pivot. Deliberately ambiguous 'regime change' "
                    "language could mean tighter OR restructured."
                ),
                hypothesis="C",
                direction="confirm",
                weight=0.08,
                source="Bloomberg, Yahoo Finance",
            ),
            Signal(
                date="2026-07-08",
                description=(
                    "Trump's DOJ investigation of Powell for not cutting rates shows "
                    "Trump demands dovish policy. Warsh was appointed to replace the "
                    "non-compliant Chair."
                ),
                hypothesis="B",
                direction="confirm",
                weight=0.05,
                source="Multiple news sources",
            ),
            Signal(
                date="2026-07-15",
                description=(
                    "Curve stable at 2s10s +40bps over 30 days. Bond market has NOT "
                    "priced in any scenario shift. All yields rose 13bps in parallel "
                    "(inflation expectations up) but shape unchanged."
                ),
                hypothesis="A",
                direction="confirm",
                weight=0.05,
                source="FRED DGS2/DGS10, yield curve monitor",
            ),
        ],
    )


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------

STATE_FILE = Path("data/warsh_hypotheses.json")


def save_state(state: TrackerState) -> None:
    """Save tracker state to JSON."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "last_updated": state.last_updated,
        "curve_2s10s": state.curve_2s10s,
        "curve_3m10y": state.curve_3m10y,
        "curve_shape": state.curve_shape,
        "recession_prob": state.recession_prob,
        "hypotheses": [asdict(h) for h in state.hypotheses],
        "signals": [asdict(s) for s in state.signals],
    }
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(STATE_FILE)


def load_state() -> TrackerState:
    """Load tracker state from JSON, or initialize if not found."""
    if not STATE_FILE.exists():
        state = initial_state()
        save_state(state)
        return state

    data = json.loads(STATE_FILE.read_text())
    hypotheses = [Hypothesis(**h) for h in data.get("hypotheses", [])]
    signals = [Signal(**s) for s in data.get("signals", [])]
    return TrackerState(
        last_updated=data["last_updated"],
        curve_2s10s=data.get("curve_2s10s"),
        curve_3m10y=data.get("curve_3m10y"),
        curve_shape=data.get("curve_shape"),
        recession_prob=data.get("recession_prob"),
        hypotheses=hypotheses,
        signals=signals,
    )


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------


def display(state: TrackerState) -> None:
    """Print the current hypothesis tracker state."""
    print("=" * 70)
    print("WARSH FRAMEWORK HYPOTHESIS TRACKER")
    print(f"Last updated: {state.last_updated}")
    print("=" * 70)
    print()

    # Curve context
    print("CURVE CONTEXT:")
    if state.curve_2s10s is not None:
        print(f"  2s10s:         +{state.curve_2s10s:.0f} bps")
    if state.curve_3m10y is not None:
        print(f"  3m10y:         +{state.curve_3m10y:.0f} bps")
    if state.curve_shape:
        print(f"  Shape:         {state.curve_shape}")
    if state.recession_prob is not None:
        print(f"  Recession prob: {state.recession_prob*100:.1f}%")
    print()

    # Hypotheses
    print("HYPOTHESES (sorted by probability):")
    print("-" * 70)
    sorted_hyp = sorted(state.hypotheses, key=lambda h: h.probability, reverse=True)
    for h in sorted_hyp:
        bar_len = int(h.probability * 40)
        bar = "#" * bar_len + "." * (40 - bar_len)
        print(f"  Scenario {h.key}: {h.name}")
        print(f"  Probability: [{bar}] {h.probability*100:.0f}%")
        print(f"  {h.description[:100]}...")
        print(f"  Curve: {h.curve_implication}")
        print(f"  Timeline: {h.timeline}")
        print()

    # Signals
    print("RECENT SIGNALS:")
    print("-" * 70)
    for s in state.signals[-5:]:  # last 5 signals
        arrow = "CONFIRMS" if s.direction == "confirm" else "DENIES"
        print(f"  [{s.date}] {s.hypothesis} {arrow} ({s.weight*100:.0f}% weight)")
        print(f"    {s.description[:100]}...")
        if s.source:
            print(f"    Source: {s.source}")
        print()

    # What to watch
    print("NEXT SIGNALS TO WATCH:")
    print("-" * 70)
    print("  1. Balance sheet panel preliminary findings (Q3 2026)")
    print("     - Explicit targets = Scenario A")
    print("     - 'Ample reserves' no targets = Scenario B or C")
    print("  2. FOMC statement language shifts (late July)")
    print("     - 'Higher for longer' maintained = A")
    print("     - 'Patient' or 'data-dependent' softening = C")
    print("  3. 2s10s curve movement")
    print("     - Push through +50 = B or C accelerating")
    print("     - Drop below +30 = A intensifying")
    print("  4. Reserves management purchase volume")
    print("     - Minimal/temporary = A")
    print("     - Expanded/permanent = B or C")
    print()

    # Trading implication
    top = sorted_hyp[0]
    print("TRADING IMPLICATION (most likely scenario):")
    print("-" * 70)
    print(f"  {top.name} ({top.probability*100:.0f}% probability)")
    print(f"  {top.curve_implication}")
    print(f"  {top.timeline}")
    print()


# ---------------------------------------------------------------------------
# Update curve data
# ---------------------------------------------------------------------------


def update_curve(state: TrackerState) -> TrackerState:
    """Pull latest curve data from FRED and update state."""
    try:
        from datetime import date, timedelta
        from src.yield_curve.fetcher import FredCurveFetcher
        from src.yield_curve.curves import compute_spreads, classify_shape, nyfed_recession_prob

        f = FredCurveFetcher()
        today = date.today()
        data = f.fetch_tenors(["2y", "10y", "3mo"], today - timedelta(days=5), today)

        curve = {}
        for tenor, df in data.items():
            if not df.empty:
                curve[tenor] = float(df.iloc[-1]["close"])

        spreads = compute_spreads(curve)
        shape = classify_shape(curve)
        s3m10y = spreads.get("3m10y")
        prob = nyfed_recession_prob(s3m10y) if s3m10y is not None else None

        state.curve_2s10s = spreads.get("2s10s")
        state.curve_3m10y = s3m10y
        state.curve_shape = shape.value
        state.recession_prob = prob
        state.last_updated = today.isoformat()

        print(f"Curve updated: 2s10s={state.curve_2s10s}bps, shape={state.curve_shape}")

        # Check for regime signals
        if state.curve_2s10s and state.curve_2s10s > 50:
            print("  *** 2s10s above +50 — steepening signal! Scenario B/C may be accelerating ***")
        elif state.curve_2s10s and state.curve_2s10s < 30:
            print("  *** 2s10s below +30 — flattening warning! Scenario A may be intensifying ***")

    except Exception as exc:
        print(f"Could not update curve data: {exc}")
        print("Make sure FRED_API_KEY is set and src/yield_curve/ is importable.")

    return state


# ---------------------------------------------------------------------------
# Add signal
# ---------------------------------------------------------------------------


def add_signal(
    state: TrackerState,
    description: str,
    hypothesis: str,
    direction: str,
    weight: float = 0.05,
    source: str = "",
) -> TrackerState:
    """Add a new signal and update hypothesis probabilities."""
    today = date.today().isoformat()

    sig = Signal(
        date=today,
        description=description,
        hypothesis=hypothesis,
        direction=direction,
        weight=weight,
        source=source,
    )
    state.signals.append(sig)

    # Simple Bayesian-ish update: adjust probabilities based on signal
    # This is NOT rigorous Bayesian inference — it's a directional heuristic
    for h in state.hypotheses:
        if h.key == hypothesis:
            if direction == "confirm":
                h.probability = min(0.95, h.probability + weight * (1 - h.probability))
            else:
                h.probability = max(0.05, h.probability - weight * h.probability)
        else:
            # Redistribute from other hypotheses
            if direction == "confirm":
                h.probability = max(0.05, h.probability * (1 - weight * 0.5))
            else:
                h.probability = min(0.95, h.probability + weight * 0.3)

    # Normalize
    total = sum(h.probability for h in state.hypotheses)
    for h in state.hypotheses:
        h.probability = h.probability / total

    return state


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Warsh Framework Hypothesis Tracker")
    parser.add_argument("--update", action="store_true", help="Pull latest curve data")
    parser.add_argument("--signal", type=str, help="Add a new signal (description)")
    parser.add_argument("--scenario", choices=["A", "B", "C"], help="Which hypothesis")
    parser.add_argument("--direction", choices=["confirm", "deny"], help="Signal direction")
    parser.add_argument("--weight", type=float, default=0.05, help="Signal weight (0-1)")
    parser.add_argument("--source", type=str, default="", help="Signal source")
    args = parser.parse_args()

    state = load_state()

    if args.update:
        state = update_curve(state)
        save_state(state)
        print()

    if args.signal and args.scenario and args.direction:
        state = add_signal(
            state,
            description=args.signal,
            hypothesis=args.scenario,
            direction=args.direction,
            weight=args.weight,
            source=args.source,
        )
        save_state(state)
        print(f"Signal added. Probabilities updated.")
        print()

    display(state)


if __name__ == "__main__":
    main()