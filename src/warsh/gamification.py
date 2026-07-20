"""Gamification — rate the user's policy configuration.

Computes an aggregate "hawkish score" from the six QE-without-QE tool values and
maps it to a Fed Chair persona. Also provides scenario-matching (which of the
three hypotheses the configuration most resembles) and market-reaction predictions.

The hawkish score is normalized to [0, 1] where:
- 1.0 = maximally hawkish (Volcker-style)
- 0.0 = maximally dovish (hyper-accommodative)
"""
from __future__ import annotations

from src.warsh.tools import ToolName


# ---------------------------------------------------------------------------
# Persona definitions
# ---------------------------------------------------------------------------

# (min_score_inclusive, max_score_exclusive, persona_name, emoji, description)
# Evaluated top-down; the first band that contains the score wins.
_PERSONAS: tuple[tuple[float, float, str, str, str], ...] = (
    (
        0.70,
        float("inf"),
        "Volcker Disciple",
        "🦅",
        "Maximum hawkish. Inflation will be defeated, even at the cost of recession.",
    ),
    (
        0.50,
        0.70,
        "Greenspan Maestro",
        "🎯",
        "Pragmatic and balanced. Flexible enough to pivot when needed.",
    ),
    (
        0.30,
        0.50,
        "Bernanke Crisis Manager",
        "🚁",
        "Accommodative. Providing liquidity while maintaining credibility.",
    ),
    (
        0.15,
        0.30,
        "Powell Flip-Flopper",
        "🎢",
        "Reactive and inconsistent. Markets don't know what to expect.",
    ),
    (
        -float("inf"),
        0.15,
        "Trump Puppet",
        "🤡",
        "Maximum dovish. The printer goes brrr. Inflation be damned.",
    ),
)


# ---------------------------------------------------------------------------
# Tool value normalization
# ---------------------------------------------------------------------------
# Each tool's raw value is mapped to a [0, 1] hawkish score. The scores are
# combined into an aggregate via the weights below. Higher = more hawkish.


def _rmp_hawkish(value: float) -> float:
    """RMP buys T-bills — more RMP = more dovish (suppresses yields)."""
    # max=100, min=0; invert so high RMP → low hawkish score
    return 1.0 - max(0.0, min(1.0, value / 100.0))


def _qt_hawkish(value: float) -> float:
    """QT pace — more QT = more hawkish (sells bonds)."""
    return max(0.0, min(1.0, value / 95.0))


def _srf_hawkish(value: float) -> float:
    """SRF cap — higher cap = more dovish (stronger backstop)."""
    return 1.0 - max(0.0, min(1.0, value / 2000.0))


def _mbs_hawkish(value: float) -> float:
    """MBS sales — active selling = more hawkish (reduces balance sheet)."""
    return max(0.0, min(1.0, value / 35.0))


def _fg_hawkish(value: float) -> float:
    """Forward guidance — keeping it active = more hawkish commitment."""
    return 1.0 if value >= 0.5 else 0.0


def _bank_reg_hawkish(value: float) -> float:
    """Bank regulation — STRICT (low value) = more hawkish credit conditions."""
    # value 0=strict, 1=relaxed; invert so strict → high hawkish score
    return 1.0 - max(0.0, min(1.0, value))


# Equal-weighted by default — all six tools contribute symmetrically.
_TOOL_WEIGHTS: dict[ToolName, float] = {
    ToolName.RMP: 1.0,
    ToolName.QT_PACE: 1.0,
    ToolName.SRF: 1.0,
    ToolName.MBS_SALES: 1.0,
    ToolName.FORWARD_GUIDANCE: 1.0,
    ToolName.BANK_REGULATION: 1.0,
}


def calculate_hawkish_score(tool_values: dict) -> float:
    """Calculate an aggregate hawkish score in [0, 1] from tool values.

    Args:
        tool_values: Dict that may use either ToolName enum keys or string
            tool-name values. Accepts both {'rmp': 40} and {ToolName.RMP: 40}.

    Returns:
        Hawkish score in [0, 1]. Higher = more hawkish.
    """
    # Normalize keys to ToolName enum (accept strings or enums).
    normalized: dict[ToolName, float] = {}
    for key, value in tool_values.items():
        if isinstance(key, ToolName):
            normalized[key] = float(value)
        elif isinstance(key, str):
            try:
                normalized[ToolName(key)] = float(value)
            except ValueError:
                # Try matching by enum value (e.g. "rmp")
                for tn in ToolName:
                    if tn.value == key:
                        normalized[tn] = float(value)
                        break

    score_funcs = {
        ToolName.RMP: _rmp_hawkish,
        ToolName.QT_PACE: _qt_hawkish,
        ToolName.SRF: _srf_hawkish,
        ToolName.MBS_SALES: _mbs_hawkish,
        ToolName.FORWARD_GUIDANCE: _fg_hawkish,
        ToolName.BANK_REGULATION: _bank_reg_hawkish,
    }

    total_weight = 0.0
    weighted_sum = 0.0
    for tool_name, weight in _TOOL_WEIGHTS.items():
        value = normalized.get(tool_name)
        if value is None:
            continue
        score = score_funcs[tool_name](value)
        weighted_sum += score * weight
        total_weight += weight

    if total_weight == 0:
        return 0.5  # neutral default if no recognizable tools provided

    return max(0.0, min(1.0, weighted_sum / total_weight))


def rate_fed_chair(tool_values: dict) -> tuple[str, str, str]:
    """Rate the user's policy configuration.

    Args:
        tool_values: Dict of tool values (same format as calculate_hawkish_score).

    Returns:
        Tuple of (persona_name, emoji, description).
    """
    score = calculate_hawkish_score(tool_values)
    for low, high, name, emoji, description in _PERSONAS:
        if low <= score < high:
            return name, emoji, description
    # Fallback (should never hit if personas cover the real line)
    return "Powell Flip-Flopper", "🎢", "Reactive and inconsistent."


# ---------------------------------------------------------------------------
# Scenario matching
# ---------------------------------------------------------------------------

# Reference configurations for each hypothesis scenario. Used to compute how
# closely a user's configuration matches each hypothesis.
_SCENARIO_REFERENCES: dict[str, dict[ToolName, float]] = {
    "A": {  # Hawkish: minimal shadow easing
        ToolName.RMP: 20,
        ToolName.QT_PACE: 80,
        ToolName.SRF: 500,
        ToolName.MBS_SALES: 20,
        ToolName.FORWARD_GUIDANCE: 1,
        ToolName.BANK_REGULATION: 0.2,
    },
    "B": {  # Pantomime: shadow easing from day one
        ToolName.RMP: 80,
        ToolName.QT_PACE: 20,
        ToolName.SRF: 1000,
        ToolName.MBS_SALES: 0,
        ToolName.FORWARD_GUIDANCE: 0,
        ToolName.BANK_REGULATION: 0.5,
    },
    "C": {  # Transition: full dovish pivot
        ToolName.RMP: 80,
        ToolName.QT_PACE: 0,
        ToolName.SRF: 1000,
        ToolName.MBS_SALES: 0,
        ToolName.FORWARD_GUIDANCE: 0,
        ToolName.BANK_REGULATION: 0.8,
    },
}

# Max absolute difference per tool (for normalization to similarity score)
_MAX_DIFFS: dict[ToolName, float] = {
    ToolName.RMP: 100.0,
    ToolName.QT_PACE: 95.0,
    ToolName.SRF: 2000.0,
    ToolName.MBS_SALES: 35.0,
    ToolName.FORWARD_GUIDANCE: 1.0,
    ToolName.BANK_REGULATION: 1.0,
}


def calculate_scenario_match(tool_values: dict) -> dict[str, float]:
    """How closely does the configuration match each hypothesis?

    For each scenario (A/B/C), computes a similarity score in [0, 1] using
    inverse-distance: 1.0 = exact match, 0.0 = maximally distant.

    Args:
        tool_values: Dict of tool values.

    Returns:
        Dict with keys "A", "B", "C" mapping to similarity scores in [0, 1].
        The three scores sum to approximately 1.0 if normalized, but here we
        return raw similarity (so multiple can be high if scenarios overlap).
    """
    # Normalize input keys.
    user: dict[ToolName, float] = {}
    for key, value in tool_values.items():
        if isinstance(key, ToolName):
            user[key] = float(value)
        elif isinstance(key, str):
            for tn in ToolName:
                if tn.value == key or tn.name == key:
                    user[tn] = float(value)
                    break

    out: dict[str, float] = {}
    for scenario, ref in _SCENARIO_REFERENCES.items():
        diffs = []
        for tool_name, ref_value in ref.items():
            if tool_name not in user:
                continue
            abs_diff = abs(user[tool_name] - ref_value)
            max_diff = _MAX_DIFFS[tool_name]
            # Similarity per tool = 1 - normalized distance
            similarity = max(0.0, 1.0 - abs_diff / max_diff) if max_diff > 0 else 1.0
            diffs.append(similarity)
        out[scenario] = sum(diffs) / len(diffs) if diffs else 0.0

    return out


# ---------------------------------------------------------------------------
# Market prediction
# ---------------------------------------------------------------------------

# Asset classes covered
_ASSET_CLASSES = ("stocks", "bonds", "gold", "crypto", "oil", "dollar")


def get_market_prediction(tool_values: dict) -> dict[str, str]:
    """Predict market reactions from the configuration.

    Uses the hawkish score to derive directional calls:
    - Hawkish config → dollar up, bonds down (yields up), stocks mixed/down,
      gold down, crypto down, oil neutral/down (slower growth).
    - Dovish config → the inverse.

    Args:
        tool_values: Dict of tool values.

    Returns:
        Dict mapping asset_class -> one of "bullish"/"bearish"/"neutral".
    """
    score = calculate_hawkish_score(tool_values)

    # Thresholds for directional calls
    if score >= 0.6:
        # Strongly hawkish
        return {
            "stocks": "bearish",   # multiple compression
            "bonds": "bearish",    # yields up = prices down
            "gold": "bearish",     # real rates up
            "crypto": "bearish",   # risk-off
            "oil": "neutral",      # demand destruction vs. dollar
            "dollar": "bullish",   # higher real yields attract flows
        }
    if score >= 0.4:
        # Balanced / neutral
        return {
            "stocks": "neutral",
            "bonds": "neutral",
            "gold": "neutral",
            "crypto": "neutral",
            "oil": "neutral",
            "dollar": "neutral",
        }
    # Dovish
    return {
        "stocks": "bullish",   # multiple expansion
        "bonds": "bullish",    # yields down = prices up
        "gold": "bullish",     # real rates down
        "crypto": "bullish",   # risk-on + liquidity
        "oil": "bullish",      # growth stimulus + weak dollar
        "dollar": "bearish",   # lower real yields
    }
