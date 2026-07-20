"""Market event shocks — X-factor events and black swans.

Defines a library of probabilistic market events that can shock the yield curve
on top of the structural QE-without-QE effects. Two categories:

- X-factor events: moderate probability (8-20% per turn), moderate curve impact.
  These represent the routine flow of macro surprises (jobs, inflation, geopolitical
  tension) that move markets a few basis points at a time.

- Black swan events: low probability (2-5% per turn), high impact. Pandemics,
  sovereign crises, Fed independence shocks — the tail risks that define eras.

Effect convention: positive curve_effects = yield INCREASE (in bps).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import random


@dataclass(frozen=True)
class MarketEvent:
    name: str
    description: str
    probability: float  # 0-1, chance per "turn"
    curve_effects: dict[str, float]  # tenor -> bps shock (positive = yield up)
    category: str  # "x_factor" or "black_swan"
    market_reaction: dict[str, str]  # asset_class -> "up"/"down"/"neutral"
    emoji: str = "📊"


# ---------------------------------------------------------------------------
# X-Factor events (probability 0.08-0.20)
# Moderate probability, moderate impact — the routine macro surprise flow
# ---------------------------------------------------------------------------

_HORMUZ_CLOSURE = MarketEvent(
    name="Hormuz Full Closure",
    description=(
        "Iran closes the Strait of Hormuz. Oil spikes to $120+, gasoline surges, "
        "and inflation fears reignite at the long end of the curve. Defense and "
        "energy equities rip; everything else sells off."
    ),
    probability=0.12,
    curve_effects={
        "5y": 8.0,
        "7y": 12.0,
        "10y": 15.0,
        "20y": 18.0,
        "30y": 20.0,
    },
    category="x_factor",
    market_reaction={
        "oil": "up",
        "stocks": "down",
        "bonds": "down",
        "gold": "up",
        "crypto": "down",
    },
    emoji="🛢️",
)

_AI_MIRACLE = MarketEvent(
    name="AI Productivity Miracle",
    description=(
        "Major AI deployment lifts productivity 2-3% across the economy. Growth "
        "expectations surge, all yields rise as the market prices a higher neutral "
        "rate, and tech stocks explode higher."
    ),
    probability=0.15,
    curve_effects={
        "2y": 6.0,
        "5y": 10.0,
        "7y": 12.0,
        "10y": 14.0,
        "30y": 12.0,
    },
    category="x_factor",
    market_reaction={
        "oil": "neutral",
        "stocks": "up",
        "bonds": "down",
        "gold": "down",
        "crypto": "up",
    },
    emoji="🤖",
)

_BANK_STRESS = MarketEvent(
    name="Bank Stress Event",
    description=(
        "A regional bank unveils heavy unrealized losses on its HTM Treasury book. "
        "Credit tightens across the sector, the short end rises on funding stress, "
        "and the long end falls as the market prices slower growth."
    ),
    probability=0.10,
    curve_effects={
        "3mo": 4.0,
        "1y": 5.0,
        "2y": 4.0,
        "5y": 0.0,
        "7y": -3.0,
        "10y": -6.0,
        "30y": -8.0,
    },
    category="x_factor",
    market_reaction={
        "oil": "down",
        "stocks": "down",
        "bonds": "up",
        "gold": "up",
        "crypto": "down",
    },
    emoji="🏦",
)

_STRONG_JOBS = MarketEvent(
    name="Strong Jobs Report",
    description=(
        "NFP prints +300k with upward revisions and rising wages. The Fed stays "
        "hawkish, the 2Y pops on sticky-rate expectations, and equities wobble on "
        "the 'good news is bad news' dynamic."
    ),
    probability=0.20,
    curve_effects={
        "3mo": 3.0,
        "1y": 5.0,
        "2y": 7.0,
        "5y": 3.0,
        "10y": 1.0,
    },
    category="x_factor",
    market_reaction={
        "oil": "neutral",
        "stocks": "down",
        "bonds": "down",
        "gold": "down",
        "crypto": "down",
    },
    emoji="💪",
)

_WEAK_INFLATION = MarketEvent(
    name="Weak Inflation Data",
    description=(
        "Core CPI prints 0.1% MoH, well below 0.3% expected. Markets immediately "
        "price a Fed pivot — 2Y drops hard, curve bull-steepens, and risk assets "
        "rally on the prospect of easier policy."
    ),
    probability=0.18,
    curve_effects={
        "3mo": -2.0,
        "1y": -5.0,
        "2y": -8.0,
        "5y": -4.0,
        "10y": -1.0,
    },
    category="x_factor",
    market_reaction={
        "oil": "neutral",
        "stocks": "up",
        "bonds": "up",
        "gold": "up",
        "crypto": "up",
    },
    emoji="📉",
)

_CHINA_DECOUPLE = MarketEvent(
    name="China Decoupling Accelerates",
    description=(
        "New export controls on chips and rare earths from both sides. Risk-off "
        "sentiment sweeps markets, flight-to-quality bids Treasuries across the "
        "curve, and gold catches a safe-haven bid."
    ),
    probability=0.13,
    curve_effects={
        "2y": -5.0,
        "5y": -6.0,
        "7y": -6.0,
        "10y": -5.0,
        "30y": -3.0,
    },
    category="x_factor",
    market_reaction={
        "oil": "down",
        "stocks": "down",
        "bonds": "up",
        "gold": "up",
        "crypto": "down",
    },
    emoji="🐉",
)

_OPEC_CUTS = MarketEvent(
    name="OPEC+ Emergency Cuts",
    description=(
        "Saudi Arabia surprises with a 1M bbl/day emergency production cut. Oil "
        "rips 8% in a session, inflation expectations climb at the long end, and "
        "energy equities lead the market."
    ),
    probability=0.14,
    curve_effects={
        "5y": 4.0,
        "7y": 6.0,
        "10y": 8.0,
        "20y": 10.0,
        "30y": 11.0,
    },
    category="x_factor",
    market_reaction={
        "oil": "up",
        "stocks": "neutral",
        "bonds": "down",
        "gold": "up",
        "crypto": "neutral",
    },
    emoji="🛢️",
)

_RECESSION_SCARE = MarketEvent(
    name="Recession Scare (ISM < 48)",
    description=(
        "ISM manufacturing prints 47.0, well into contraction. The curve bull-"
        "flattens violently as the market prices aggressive cuts — 2Y drops 15bps "
        "while the long end barely moves on stagflation concerns."
    ),
    probability=0.16,
    curve_effects={
        "3mo": -8.0,
        "1y": -12.0,
        "2y": -15.0,
        "5y": -8.0,
        "7y": -4.0,
        "10y": -1.0,
        "30y": 1.0,
    },
    category="x_factor",
    market_reaction={
        "oil": "down",
        "stocks": "down",
        "bonds": "up",
        "gold": "up",
        "crypto": "down",
    },
    emoji="📉",
)


# ---------------------------------------------------------------------------
# Black Swan events (probability 0.02-0.05)
# Low probability, catastrophic impact — the tail risks that define eras
# ---------------------------------------------------------------------------

_PANDEMIC_2 = MarketEvent(
    name="Pandemic 2.0",
    description=(
        "A novel respiratory virus with 3% CFR escapes containment in three major "
        "cities. Markets price immediate, aggressive easing — 2Y collapses 30bps "
        "in a session, curve steepens violently, and risk assets go bidless."
    ),
    probability=0.03,
    curve_effects={
        "3mo": -20.0,
        "1y": -28.0,
        "2y": -30.0,
        "5y": -18.0,
        "7y": -8.0,
        "10y": -2.0,
        "30y": 5.0,
    },
    category="black_swan",
    market_reaction={
        "oil": "down",
        "stocks": "down",
        "bonds": "up",
        "gold": "up",
        "crypto": "down",
    },
    emoji="🦠",
)

_SOVEREIGN_CRISIS = MarketEvent(
    name="Sovereign Debt Crisis",
    description=(
        "A failed 30Y Treasury auction draws only 1.8x bid-to-cover. Yields spike "
        "across the curve as foreign buyers strike, the dollar wobbles, and gold "
        "goes bidless-vertical. The fiscal dominance narrative goes mainstream."
    ),
    probability=0.04,
    curve_effects={
        "3mo": 15.0,
        "1y": 20.0,
        "2y": 25.0,
        "5y": 28.0,
        "7y": 32.0,
        "10y": 35.0,
        "20y": 38.0,
        "30y": 40.0,
    },
    category="black_swan",
    market_reaction={
        "oil": "up",
        "stocks": "down",
        "bonds": "down",
        "gold": "up",
        "crypto": "up",
    },
    emoji="💥",
)

_FIRES_WARSH = MarketEvent(
    name="Trump Fires Warsh",
    description=(
        "President Trump fires Fed Chair Warsh via Truth Social for refusing to "
        "cut rates. Fed independence is in question, the dollar sells off, and the "
        "curve reacts chaotically — front end down on expected easing, long end "
        "UP on inflation/fiscal-dominance fears."
    ),
    probability=0.05,
    curve_effects={
        "3mo": -15.0,
        "1y": -20.0,
        "2y": -18.0,
        "5y": 5.0,
        "7y": 15.0,
        "10y": 25.0,
        "20y": 30.0,
        "30y": 32.0,
    },
    category="black_swan",
    market_reaction={
        "oil": "up",
        "stocks": "down",
        "bonds": "down",
        "gold": "up",
        "crypto": "up",
    },
    emoji="🔥",
)

_ME_PEACE = MarketEvent(
    name="Middle East Peace Breakthrough",
    description=(
        "Israel and Saudi Arabia announce full normalization; Iran agrees to "
        "nuclear inspections. Oil crashes 15% in a session, inflation expectations "
        "collapse, and all yields fall as the term premium compresses. Historic "
        "risk-on rally in equities."
    ),
    probability=0.02,
    curve_effects={
        "3mo": -3.0,
        "1y": -5.0,
        "2y": -8.0,
        "5y": -10.0,
        "7y": -12.0,
        "10y": -14.0,
        "20y": -16.0,
        "30y": -18.0,
    },
    category="black_swan",
    market_reaction={
        "oil": "down",
        "stocks": "up",
        "bonds": "up",
        "gold": "down",
        "crypto": "up",
    },
    emoji="🕊️",
)


# ---------------------------------------------------------------------------
# Event registry
# ---------------------------------------------------------------------------

_X_FACTOR_EVENTS: tuple[MarketEvent, ...] = (
    _HORMUZ_CLOSURE,
    _AI_MIRACLE,
    _BANK_STRESS,
    _STRONG_JOBS,
    _WEAK_INFLATION,
    _CHINA_DECOUPLE,
    _OPEC_CUTS,
    _RECESSION_SCARE,
)

_BLACK_SWAN_EVENTS: tuple[MarketEvent, ...] = (
    _PANDEMIC_2,
    _SOVEREIGN_CRISIS,
    _FIRES_WARSH,
    _ME_PEACE,
)

_ALL_EVENTS: tuple[MarketEvent, ...] = _X_FACTOR_EVENTS + _BLACK_SWAN_EVENTS


def get_all_events() -> list[MarketEvent]:
    """Return all defined market events (X-factor + black swan)."""
    return list(_ALL_EVENTS)


def get_x_factor_events() -> list[MarketEvent]:
    """Return only X-factor events (moderate probability, moderate impact)."""
    return list(_X_FACTOR_EVENTS)


def get_black_swan_events() -> list[MarketEvent]:
    """Return only black swan events (low probability, high impact)."""
    return list(_BLACK_SWAN_EVENTS)


# ---------------------------------------------------------------------------
# Rolling + application
# ---------------------------------------------------------------------------


def roll_event(rng: Optional[random.Random] = None) -> Optional[MarketEvent]:
    """Randomly select an event based on probabilities. Returns None if no event.

    Each event is evaluated as an independent Bernoulli trial — the first event
    whose trial succeeds is returned. With 8 X-factor events at p≈0.08-0.20
    plus 4 black swans at p≈0.02-0.05, the probability of returning None on a
    given turn is roughly 24% (product of (1 - p_i) across all events).

    Args:
        rng: Optional random.Random instance for reproducibility. Defaults to
            the global random module.

    Returns:
        A MarketEvent that fired this turn, or None if no event occurred.
    """
    rand_func = rng.random if rng is not None else random.random

    # Independent trials per event. The X-factor probabilities sum to >1.0,
    # so a single-roll cumulative approach would never return None. Independent
    # trials preserve each event's per-turn probability and give a meaningful
    # chance of "no event this turn".
    for event in _ALL_EVENTS:
        if rand_func() < event.probability:
            return event
    return None


def apply_event_to_curve(event: MarketEvent, curve: dict[str, float]) -> dict[str, float]:
    """Apply an event's curve shock to a yield curve.

    Args:
        event: The MarketEvent to apply.
        curve: Dict mapping tenor name -> yield in percent.

    Returns:
        New dict with shocked yields. Tenors not in the original curve are
        skipped; tenors not in the event's curve_effects are passed through.
    """
    shocked: dict[str, float] = {}
    for tenor, yield_pct in curve.items():
        bps = event.curve_effects.get(tenor, 0.0)
        # 1 bp = 0.01 percentage point
        shocked[tenor] = yield_pct + bps / 100.0
    return shocked
