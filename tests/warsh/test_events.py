"""Tests for market event shocks (X-factor + black swan)."""
from __future__ import annotations

import random

import pytest

from src.warsh.events import (
    MarketEvent,
    apply_event_to_curve,
    get_all_events,
    get_black_swan_events,
    get_x_factor_events,
    roll_event,
)


def test_all_events_have_valid_probabilities():
    """X-factor events: 0 < p < 0.25. Black swan events: 0 < p < 0.06."""
    for event in get_all_events():
        assert 0.0 < event.probability, f"{event.name} has zero probability"
        if event.category == "x_factor":
            assert event.probability < 0.25, (
                f"X-factor {event.name} probability {event.probability} >= 0.25"
            )
        elif event.category == "black_swan":
            assert event.probability < 0.06, (
                f"Black swan {event.name} probability {event.probability} >= 0.06"
            )
        else:
            pytest.fail(f"Unknown category: {event.category}")


def test_apply_event_modifies_curve():
    """Applying an event with non-zero effects must change the curve."""
    baseline = {
        "3mo": 3.84, "1y": 4.02, "2y": 4.16, "5y": 4.31,
        "7y": 4.44, "10y": 4.58, "20y": 5.09, "30y": 5.08,
    }
    event = next(e for e in get_all_events() if e.curve_effects)
    shocked = apply_event_to_curve(event, baseline)
    # At least one tenor must have changed
    diffs = [abs(shocked[t] - baseline[t]) for t in baseline]
    assert max(diffs) > 0, f"Event {event.name} had no effect on curve"


def test_roll_event_returns_none_or_valid_event():
    """roll_event returns None or a MarketEvent from the registry."""
    rng = random.Random(42)
    seen_none = False
    seen_event = False
    registry = set(id(e) for e in get_all_events())
    for _ in range(500):
        result = roll_event(rng=rng)
        if result is None:
            seen_none = True
        else:
            assert isinstance(result, MarketEvent)
            assert id(result) in registry, f"Returned event not in registry: {result.name}"
            seen_event = True
    # In 500 rolls we should see both outcomes given the probabilities.
    assert seen_none, "roll_event never returned None in 500 rolls"
    assert seen_event, "roll_event never fired an event in 500 rolls"


def test_black_swan_effects_are_larger_than_x_factor():
    """Average absolute curve effect of black swans must exceed X-factor average."""
    def avg_magnitude(events):
        total_bps = 0.0
        n = 0
        for e in events:
            for bps in e.curve_effects.values():
                total_bps += abs(bps)
                n += 1
        return total_bps / n if n else 0.0

    x_factor_avg = avg_magnitude(get_x_factor_events())
    black_swan_avg = avg_magnitude(get_black_swan_events())
    assert black_swan_avg > x_factor_avg, (
        f"Black swan avg effect {black_swan_avg:.2f}bps not larger than "
        f"X-factor avg {x_factor_avg:.2f}bps"
    )


def test_at_least_eight_x_factor_and_four_black_swan():
    """The spec requires ≥8 X-factor and ≥4 black swan events."""
    assert len(get_x_factor_events()) >= 8
    assert len(get_black_swan_events()) >= 4
    assert len(get_all_events()) >= 12


def test_event_required_fields_populated():
    """Every event needs name, description, market_reaction, emoji."""
    for event in get_all_events():
        assert event.name, f"Event missing name: {event}"
        assert event.description, f"{event.name} missing description"
        assert len(event.description) > 20, f"{event.name} description too short"
        assert event.market_reaction, f"{event.name} missing market_reaction"
        assert event.emoji, f"{event.name} missing emoji"
        assert event.category in ("x_factor", "black_swan")
