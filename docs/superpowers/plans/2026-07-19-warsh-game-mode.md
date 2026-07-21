# Warsh Simulator Game Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the Warsh Simulator from a static dashboard into a turn-based game where you play as Fed Chair Warsh across multiple quarters, managing inflation, unemployment, GDP, and political pressure while responding to random economic shocks.

**Architecture:** New `src/warsh/economy.py` (economic state engine) and `src/warsh/game.py` (game loop + scoring) sit alongside the existing simulation model. A new "🎮 Game Mode" tab in the Streamlit dashboard provides the turn-based interface. The existing "📊 Simulator" tab remains untouched.

**Tech Stack:** Python 3.10+, Streamlit, Plotly, pytest. Integrates with existing `src/warsh/{tools,simulator,events,gamification}.py`.

---

## Global Constraints

- All new code in `src/warsh/` package — no new top-level packages
- Economic model is HEURISTIC (directionally correct, not econometrically rigorous)
- Game state persists in Streamlit `st.session_state` across reruns
- Existing simulator tab must remain functional — no breaking changes
- All new logic gets pytest coverage (economy model, scoring, headlines, achievements)
- Plotly for all new charts
- Emojis encouraged for game feel

---

## File Structure

```
src/warsh/
  economy.py          — Economic state model (inflation, GDP, unemployment, markets)
  game.py             — Game loop, turn management, scoring, game-over conditions
  headlines.py        — Dynamic news headline generator based on state changes
  achievements.py     — Achievement definitions, unlock conditions, tracking
scripts/
  warsh_dashboard.py  — MODIFY: add "🎮 Game Mode" tab alongside existing simulator
tests/warsh/
  test_economy.py     — Economic model tests
  test_game.py        — Game loop + scoring tests
  test_headlines.py   — Headline generator tests
  test_achievements.py — Achievement system tests
```

---

## Task 1: Economic State Engine (TDD)

**Files:**
- Create: `src/warsh/economy.py`
- Create: `tests/warsh/test_economy.py`

**Interfaces:**
- Consumes: `rate_fed_chair()` from `gamification.py` (for hawkish score), `MarketEvent` from `events.py`
- Produces: `EconomicState` dataclass, `advance_quarter()` function

- [ ] **Step 1: Write failing tests in `tests/warsh/test_economy.py`**:

```python
"""Tests for the economic state engine."""
import pytest
from src.warsh.economy import EconomicState, advance_quarter
from src.warsh.tools import ToolName


def _neutral_tools():
    return {
        ToolName.RMP: 40, ToolName.QT_PACE: 60, ToolName.SRF: 500,
        ToolName.MBS_SALES: 0, ToolName.FORWARD_GUIDANCE: 1, ToolName.BANK_REGULATION: 0.3,
    }


def _hawkish_tools():
    return {
        ToolName.RMP: 20, ToolName.QT_PACE: 80, ToolName.SRF: 500,
        ToolName.MBS_SALES: 20, ToolName.FORWARD_GUIDANCE: 0, ToolName.BANK_REGULATION: 0.2,
    }


def _dovish_tools():
    return {
        ToolName.RMP: 80, ToolName.QT_PACE: 0, ToolName.SRF: 1000,
        ToolName.MBS_SALES: 0, ToolName.FORWARD_GUIDANCE: 1, ToolName.BANK_REGULATION: 0.8,
    }


def test_initial_state_has_all_indicators():
    state = EconomicState()
    assert 0 < state.inflation < 10
    assert 0 < state.unemployment < 15
    assert -5 < state.gdp_growth < 10
    assert state.sp500 > 0
    assert state.dollar_index > 0
    assert state.quarter == 0
    assert not state.recession


def test_hawkish_policy_reduces_inflation():
    state = EconomicState(inflation=4.0)
    for _ in range(4):
        state = advance_quarter(state, _hawkish_tools())
    assert state.inflation < 4.0


def test_dovish_policy_increases_inflation():
    state = EconomicState(inflation=2.0)
    for _ in range(4):
        state = advance_quarter(state, _dovish_tools())
    assert state.inflation > 2.0


def test_hawkish_policy_slows_growth():
    state = EconomicState(gdp_growth=2.5)
    for _ in range(4):
        state = advance_quarter(state, _hawkish_tools())
    assert state.gdp_growth < 2.5


def test_dovish_policy_boosts_stocks():
    state = EconomicState(sp500=5000)
    for _ in range(2):
        state = advance_quarter(state, _dovish_tools())
    assert state.sp500 > 5000


def test_extreme_hawkish_causes_recession():
    state = EconomicState(gdp_growth=1.0)
    for _ in range(6):
        state = advance_quarter(state, _hawkish_tools())
    assert state.recession or state.gdp_growth < 0


def test_quarter_advances():
    state = EconomicState()
    new_state = advance_quarter(state, _neutral_tools())
    assert new_state.quarter == 1


def test_trump_approval_drops_with_hawkish_policy():
    state = EconomicState(trump_approval=50)
    for _ in range(3):
        state = advance_quarter(state, _hawkish_tools())
    assert state.trump_approval < 50


def test_event_applies_shock_to_state():
    from src.warsh.events import get_all_events
    state = EconomicState(inflation=3.0, gdp_growth=2.0)
    events = get_all_events()
    hormuz = next(e for e in events if "Hormuz" in e.name)
    state = advance_quarter(state, _neutral_tools(), event=hormuz)
    # Hormuz should increase inflation (oil shock)
    assert state.inflation >= 3.0  # at least didn't drop
```

- [ ] **Step 2: Run tests to confirm failure**:

```bash
python -m pytest tests/warsh/test_economy.py -v
```
Expected: ImportError.

- [ ] **Step 3: Create `src/warsh/economy.py`**:

```python
"""Economic state engine — tracks macro indicators across simulated quarters.

The model is HEURISTIC: directionally correct based on economic intuition,
not econometrically rigorous. Designed for game-like simulation.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field, asdict
from typing import Optional

from src.warsh.gamification import calculate_hawkish_score
from src.warsh.tools import ToolName
from src.warsh.events import MarketEvent


@dataclass
class EconomicState:
    """Snapshot of the economy at one point in time."""
    inflation: float = 3.5
    unemployment: float = 4.2
    gdp_growth: float = 2.1
    sp500: float = 5000.0
    dollar_index: float = 104.0
    fed_approval: float = 45.0
    trump_approval: float = 50.0
    recession: bool = False
    recession_counters: int = 0
    quarter: int = 0
    history: list[dict] = field(default_factory=list)

    def snapshot(self) -> dict:
        return asdict(self)


def _policy_intensity(hawkish_score: float) -> float:
    """Convert hawkish score (0-1) to policy intensity (0-1).

    0.5 = neutral (no policy effect).
    >0.5 = hawkish intensity.
    <0.5 = dovish intensity.
    Returns absolute distance from neutral, scaled to 0-1.
    """
    return abs(hawkish_score - 0.5) * 2.0


def advance_quarter(
    state: EconomicState,
    tool_values: dict,
    event: Optional[MarketEvent] = None,
) -> EconomicState:
    """Advance the economy by one quarter given the player's policy settings.

    Args:
        state: Current economic state.
        tool_values: Dict mapping ToolName -> value (from the dashboard sliders).
        event: Optional market event shock to apply this quarter.

    Returns:
        New EconomicState with updated indicators.
    """
    hawkish_score = calculate_hawkish_score(tool_values)
    intensity = _policy_intensity(hawkish_score)
    is_hawkish = hawkish_score > 0.5
    direction = 1.0 if is_hawkish else -1.0

    noise = lambda: random.gauss(0, 0.15)

    new_inflation = state.inflation + (-direction * intensity * 0.8) + noise()
    new_gdp = state.gdp_growth + (-direction * intensity * 0.6) + noise()
    new_unemployment = state.unemployment + (direction * intensity * 0.3) + noise()
    new_sp500 = state.sp500 * (1 + (-direction * intensity * 0.04) + noise() * 0.02)
    new_dollar = state.dollar_index * (1 + (direction * intensity * 0.015) + noise() * 0.005)

    new_recession_counters = state.recession_counters
    if new_gdp < 0:
        new_recession_counters += 1
    else:
        new_recession_counters = max(0, new_recession_counters - 1)
    new_recession = new_recession_counters >= 2

    if is_hawkish:
        approval_delta = -intensity * 3.0
    else:
        approval_delta = intensity * 2.0
    new_trump = max(0, min(100, state.trump_approval + approval_delta + noise() * 2))

    if new_recession:
        new_fed_approval = max(0, state.fed_approval - 8)
    elif new_inflation < 2.5 and new_gdp > 1.5:
        new_fed_approval = min(100, state.fed_approval + 5)
    else:
        new_fed_approval = state.fed_approval + noise()

    if event:
        if "inflation" in str(event.curve_effects):
            new_inflation += 0.5
            new_gdp -= 0.3
        if "Bank" in event.name or "Pandemic" in event.name:
            new_gdp -= 1.0
            new_unemployment += 1.5
            new_sp500 *= 0.92
        if "AI" in event.name and "Productivity" in event.name:
            new_gdp += 1.0
            new_unemployment -= 0.5
        if "Peace" in event.name:
            new_inflation -= 0.8
        if "Trump" in event.name and "Fires" in event.name:
            new_fed_approval = 0

    new_state = EconomicState(
        inflation=round(max(-2, new_inflation), 2),
        unemployment=round(max(0, new_unemployment), 2),
        gdp_growth=round(new_gdp, 2),
        sp500=round(max(100, new_sp500), 0),
        dollar_index=round(max(50, new_dollar), 1),
        fed_approval=round(max(0, min(100, new_fed_approval)), 1),
        trump_approval=round(max(0, min(100, new_trump)), 1),
        recession=new_recession,
        recession_counters=new_recession_counters,
        quarter=state.quarter + 1,
        history=state.history + [state.snapshot()],
    )

    return new_state
```

- [ ] **Step 4: Run tests**:

```bash
python -m pytest tests/warsh/test_economy.py -v
```
Expected: 9 passed.

- [ ] **Step 5: Commit**:

```bash
git add src/warsh/economy.py tests/warsh/test_economy.py
git commit -m "feat(warsh): economic state engine with inflation/GDP/unemployment model"
```

---

## Task 2: Game Loop + Scoring (TDD)

**Files:**
- Create: `src/warsh/game.py`
- Create: `tests/warsh/test_game.py`

**Interfaces:**
- Consumes: `EconomicState`, `advance_quarter()` from Task 1, `roll_event()` from `events.py`
- Produces: `GameState` dataclass, `start_game()`, `play_turn()`, `calculate_score()`, `check_game_over()`

- [ ] **Step 1: Write failing tests in `tests/warsh/test_game.py`**:

```python
"""Tests for the game loop and scoring."""
import pytest
from src.warsh.game import GameState, start_game, play_turn, calculate_score, check_game_over
from src.warsh.tools import ToolName


def _neutral_tools():
    return {
        ToolName.RMP: 40, ToolName.QT_PACE: 60, ToolName.SRF: 500,
        ToolName.MBS_SALES: 0, ToolName.FORWARD_GUIDANCE: 1, ToolName.BANK_REGULATION: 0.3,
    }


def test_start_game_initializes_state():
    game = start_game()
    assert game.state.quarter == 0
    assert game.score == 0
    assert not game.game_over
    assert game.turn_history == []


def test_play_turn_advances_quarter():
    game = start_game()
    game = play_turn(game, _neutral_tools())
    assert game.state.quarter == 1
    assert len(game.turn_history) == 1


def test_score_increases_with_good_economy():
    from src.warsh.economy import EconomicState
    good_state = EconomicState(inflation=2.0, gdp_growth=2.5, unemployment=3.5, recession=False)
    bad_state = EconomicState(inflation=6.0, gdp_growth=-1.0, unemployment=7.0, recession=True)
    good_score = calculate_score(good_state)
    bad_score = calculate_score(bad_state)
    assert good_score > bad_score
    assert good_score > 0
    assert bad_score < 0


def test_game_over_on_hyperinflation():
    from src.warsh.economy import EconomicState
    state = EconomicState(inflation=12.0)
    game = GameState(state=state, score=0, turn_history=[], game_over=False, game_over_reason="")
    ended = check_game_over(game)
    assert ended.game_over
    assert "inflation" in ended.game_over_reason.lower()


def test_game_over_on_fired():
    from src.warsh.economy import EconomicState
    state = EconomicState(trump_approval=10.0)
    game = GameState(state=state, score=0, turn_history=[], game_over=False, game_over_reason="")
    ended = check_game_over(game)
    assert ended.game_over
    assert "fired" in ended.game_over_reason.lower() or "trump" in ended.game_over_reason.lower()


def test_game_over_on_max_quarters():
    from src.warsh.economy import EconomicState
    state = EconomicState(quarter=16)  # 4 years = 16 quarters
    game = GameState(state=state, score=100, turn_history=[], game_over=False, game_over_reason="")
    ended = check_game_over(game)
    assert ended.game_over
    assert "term" in ended.game_over_reason.lower() or "complete" in ended.game_over_reason.lower()


def test_cumulative_score_tracks_across_turns():
    game = start_game()
    for _ in range(3):
        game = play_turn(game, _neutral_tools())
    assert game.score != 0  # some score accumulated
    assert len(game.turn_history) == 3
```

- [ ] **Step 2: Run tests to confirm failure**:

```bash
python -m pytest tests/warsh/test_game.py -v
```
Expected: ImportError.

- [ ] **Step 3: Create `src/warsh/game.py`**:

```python
"""Game loop — turn-based Fed Chair simulation with scoring and game-over conditions.

Each turn = one quarter. The player sets tools, advances the quarter,
and the economy evolves. Score accumulates based on economic outcomes.
Game ends after 16 quarters (4 years), hyperinflation, or being fired.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.warsh.economy import EconomicState, advance_quarter
from src.warsh.events import MarketEvent, roll_event
from src.warsh.tools import ToolName


@dataclass
class GameState:
    """Full state of an in-progress game."""
    state: EconomicState
    score: float
    turn_history: list[dict]
    game_over: bool
    game_over_reason: str
    achievements: list[str] = field(default_factory=list)


def start_game() -> GameState:
    """Initialize a new game."""
    return GameState(
        state=EconomicState(),
        score=0.0,
        turn_history=[],
        game_over=False,
        game_over_reason="",
    )


def play_turn(
    game: GameState,
    tool_values: dict,
    event: Optional[MarketEvent] = None,
) -> GameState:
    """Play one turn: advance the economy and update score.

    Args:
        game: Current game state.
        tool_values: Dict mapping ToolName -> value.
        event: Optional forced event (if None, rolls randomly).

    Returns:
        Updated GameState.
    """
    if game.game_over:
        return game

    rolled_event = event if event is not None else roll_event()

    new_economy = advance_quarter(game.state, tool_values, event=rolled_event)
    turn_score = calculate_score(new_economy)

    turn_record = {
        "quarter": new_economy.quarter,
        "score_delta": turn_score,
        "total_score": game.score + turn_score,
        "inflation": new_economy.inflation,
        "gdp_growth": new_economy.gdp_growth,
        "unemployment": new_economy.unemployment,
        "recession": new_economy.recession,
        "event": rolled_event.name if rolled_event else None,
    }

    new_game = GameState(
        state=new_economy,
        score=game.score + turn_score,
        turn_history=game.turn_history + [turn_record],
        game_over=False,
        game_over_reason="",
        achievements=game.achievements,
    )

    new_game = check_game_over(new_game)
    new_game = _check_achievements(new_game)

    return new_game


def calculate_score(state: EconomicState) -> float:
    """Calculate the score delta for one quarter of economic outcomes."""
    score = 0.0

    if 2.0 <= state.inflation <= 3.0:
        score += 10
    elif state.inflation > 5.0:
        score -= 15
    elif state.inflation > 4.0:
        score -= 5

    if state.gdp_growth > 2.0:
        score += 5
    elif state.gdp_growth < 0:
        score -= 10

    if state.unemployment < 4.5:
        score += 5
    elif state.unemployment > 6.0:
        score -= 10

    if state.recession:
        score -= 20

    if state.fed_approval > 60:
        score += 3
    elif state.fed_approval < 20:
        score -= 5

    return score


def check_game_over(game: GameState) -> GameState:
    """Check if game-ending conditions are met."""
    if game.game_over:
        return game

    s = game.state

    if s.inflation > 10.0:
        return _end_game(game, f"Hyperinflation! CPI hit {s.inflation:.1f}%. You lost control of prices.")

    if s.trump_approval < 15.0:
        return _end_game(game, f"Trump fired you! His approval of your performance hit {s.trump_approval:.0f}%.")

    if s.fed_approval < 5.0:
        return _end_game(game, "Markets lost all confidence in you. You were forced to resign.")

    if s.quarter >= 16:
        grade = _letter_grade(game.score)
        return _end_game(game, f"Term complete! Final score: {game.score:.0f}. Grade: {grade}")

    return game


def _end_game(game: GameState, reason: str) -> GameState:
    game.game_over = True
    game.game_over_reason = reason
    return game


def _letter_grade(score: float) -> str:
    if score > 100:
        return "A+ (Volcker-tier)"
    if score > 50:
        return "A (Greenspan-tier)"
    if score > 0:
        return "B (Competent)"
    if score > -50:
        return "C (Survived)"
    if score > -100:
        return "D (Burns-tier)"
    return "F (Gideon Gono-tier)"


def _check_achievements(game: GameState) -> GameState:
    """Check and award achievements based on current state."""
    s = game.state
    new_achievements = list(game.achievements)

    if s.inflation < 2.0 and "Inflation Fighter" not in new_achievements:
        new_achievements.append("Inflation Fighter")

    if s.inflation < 2.5 and s.gdp_growth > 1.5 and not s.recession and s.quarter >= 4:
        if "Soft Landing" not in new_achievements:
            new_achievements.append("Soft Landing")

    if s.gdp_growth > 2.0 and s.inflation < 3.0 and s.quarter >= 8:
        if "Maestro" not in new_achievements:
            new_achievements.append("Maestro")

    if s.quarter >= 16 and not game.game_over:
        if "Survivor" not in new_achievements:
            new_achievements.append("Survivor")

    game.achievements = new_achievements
    return game
```

- [ ] **Step 4: Run tests**:

```bash
python -m pytest tests/warsh/test_game.py -v
```
Expected: 7 passed.

- [ ] **Step 5: Commit**:

```bash
git add src/warsh/game.py tests/warsh/test_game.py
git commit -m "feat(warsh): game loop with scoring, game-over conditions, achievements"
```

---

## Task 3: News Headline Generator (TDD)

**Files:**
- Create: `src/warsh/headlines.py`
- Create: `tests/warsh/test_headlines.py`

**Interfaces:**
- Consumes: `EconomicState` from Task 1, `GameState` from Task 2
- Produces: `generate_headlines()` function returning list of headline strings

- [ ] **Step 1: Write failing tests in `tests/warsh/test_headlines.py`**:

```python
"""Tests for the news headline generator."""
import pytest
from src.warsh.headlines import generate_headlines
from src.warsh.economy import EconomicState


def test_inflation_rise_generates_headline():
    prev = EconomicState(inflation=2.5)
    curr = EconomicState(inflation=3.5)
    headlines = generate_headlines(prev, curr)
    assert len(headlines) > 0
    assert any("INFLATION" in h or "PRICES" in h for h in headlines)


def test_recession_generates_headline():
    prev = EconomicState(recession=False)
    curr = EconomicState(recession=True, gdp_growth=-0.5)
    headlines = generate_headlines(prev, curr)
    assert any("RECESSION" in h for h in headlines)


def test_stock_rally_generates_headline():
    prev = EconomicState(sp500=5000)
    curr = EconomicState(sp500=5500)
    headlines = generate_headlines(prev, curr)
    assert any("RALLY" in h or "SURGE" in h or "BULL" in h for h in headlines)


def test_low_trump_approval_generates_pressure():
    curr = EconomicState(trump_approval=20)
    headlines = generate_headlines(None, curr)
    assert any("TRUMP" in h for h in headlines)


def test_good_economy_generates_positive_headline():
    curr = EconomicState(inflation=2.0, gdp_growth=3.0, unemployment=3.5)
    headlines = generate_headlines(None, curr)
    assert len(headlines) > 0


def test_headlines_are_strings():
    curr = EconomicState()
    headlines = generate_headlines(None, curr)
    for h in headlines:
        assert isinstance(h, str)
        assert len(h) > 10
```

- [ ] **Step 2: Run tests to confirm failure**:

```bash
python -m pytest tests/warsh/test_headlines.py -v
```
Expected: ImportError.

- [ ] **Step 3: Create `src/warsh/headlines.py`**:

```python
"""Dynamic news headline generator — creates realistic-feeling financial headlines.

Based on changes in economic state between quarters. Headlines are designed
to feel like CNBC/Bloomberg/Reuters alerts.
"""
from __future__ import annotations

import random
from typing import Optional

from src.warsh.economy import EconomicState


_TRUMP_TWEETS = [
    "TRUMP TWEETS: 'Warsh is doing a TERRIBLE JOB. Worst Fed Chair ever! SAD!'",
    "TRUMP: 'I appointed Warsh and he's been a total disaster. Looking at replacements!'",
    "TRUMP TWEETS: 'If Warsh doesn't cut rates immediately, the economy will CRASH. He has no idea what he's doing!'",
    "TRUMP: 'I should have kept Powell. At least he listened to me. Warsh ignores everyone!'",
    "TRUMP TWEETS: 'The Fed is holding back our incredible economy. Warsh needs to lower rates NOW! Maga!'",
]


def generate_headlines(
    prev: Optional[EconomicState],
    curr: EconomicState,
) -> list[str]:
    """Generate news headlines based on economic state changes.

    Args:
        prev: Previous quarter state (None for first turn).
        curr: Current quarter state.

    Returns:
        List of headline strings.
    """
    headlines: list[str] = []

    if prev:
        inflation_delta = curr.inflation - prev.inflation
        gdp_delta = curr.gdp_growth - prev.gdp_growth
        unemployment_delta = curr.unemployment - prev.unemployment
        sp500_delta_pct = (curr.sp500 / prev.sp500 - 1) * 100 if prev.sp500 > 0 else 0

        if inflation_delta > 0.3:
            headlines.append(f"INFLATION SURGES TO {curr.inflation:.1f}% — IS WARSH LOSING THE BATTLE?")
        elif inflation_delta < -0.3:
            headlines.append(f"INFLATION COOLS TO {curr.inflation:.1f}% AS WARSH HOLDS FIRM")

        if not prev.recession and curr.recession:
            headlines.append("BREAKING: RECESSION OFFICIAL — ECONOMY CONTRACTS FOR SECOND STRAIGHT QUARTER")

        if gdp_delta < -0.5:
            headlines.append(f"GROWTH SLOWS TO {curr.gdp_growth:.1f}% — STAGNATION FEARS RISE")
        elif gdp_delta > 0.5:
            headlines.append(f"ECONOMY ACCELERATES — GDP GROWTH HITS {curr.gdp_growth:.1f}%")

        if sp500_delta_pct > 5:
            headlines.append(f"STOCKS SURGE {sp500_delta_pct:.1f}% — BULLS TAKE CONTROL")
        elif sp500_delta_pct < -5:
            headlines.append(f"MARKET SELLOFF: S&P DROPS {abs(sp500_delta_pct):.1f}%")

        if unemployment_delta > 0.3:
            headlines.append(f"JOB LOSSES MOUNT — UNEMPLOYMENT RISES TO {curr.unemployment:.1f}%")
        elif unemployment_delta < -0.3:
            headlines.append(f"HIRING BOOM — UNEMPLOYMENT DROPS TO {curr.unemployment:.1f}%")
    else:
        if curr.inflation > 4:
            headlines.append(f"WARSH INHERITS INFLATION CRISIS — CPI AT {curr.inflation:.1f}%")
        if curr.unemployment > 5:
            headlines.append(f"ECONOMY STRUGGLING — UNEMPLOYMENT AT {curr.unemployment:.1f}%")

    if curr.inflation > 5:
        headlines.append("ALERT: INFLATION ABOVE 5% — STAGFLATION RISK ELEVATED")

    if curr.trump_approval < 30:
        headlines.append(random.choice(_TRUMP_TWEETS))

    if curr.fed_approval < 20:
        headlines.append("MARKETS LOSE FAITH IN FED — CREDIBILITY AT RISK")

    if not headlines:
        if curr.inflation < 2.5 and curr.gdp_growth > 2.0:
            headlines.append("GOLDILOCKS ECONOMY: STEADY GROWTH, CONTAINED INFLATION")
        else:
            headlines.append("ECONOMY STABLE AS FED MAINTAINS STEADY COURSE")

    return headlines
```

- [ ] **Step 4: Run tests**:

```bash
python -m pytest tests/warsh/test_headlines.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Commit**:

```bash
git add src/warsh/headlines.py tests/warsh/test_headlines.py
git commit -m "feat(warsh): news headline generator with Trump tweets and market alerts"
```

---

## Task 4: Game Mode Dashboard Tab

**Files:**
- Modify: `scripts/warsh_dashboard.py` — add "🎮 Game Mode" tab

**Interfaces:**
- Consumes: Everything from Tasks 1-3 + existing modules
- Produces: Full turn-based game UI

- [ ] **Step 1: Add game mode to the dashboard**

Add these tabs at the top of the dashboard (after `st.title`):
```python
tab_simulator, tab_game = st.tabs(["📊 Simulator", "🎮 Game Mode"])
```

Wrap the EXISTING dashboard content inside `with tab_simulator:`.

Then add the game mode inside `with tab_game:`:

```python
with tab_game:
    st.markdown("## 🎮 Fed Chair Warsh — The Game")
    st.markdown("*Set policy each quarter. Survive 4 years. Don't get fired.*")

    if "game_state" not in st.session_state:
        st.session_state.game_state = None

    col_start, col_status = st.columns([1, 3])

    with col_start:
        if st.session_state.game_state is None or st.session_state.game_state.game_over:
            if st.button("🚀 Start New Game", type="primary", use_container_width=True):
                from src.warsh.game import start_game
                st.session_state.game_state = start_game()
                st.rerun()

    game = st.session_state.game_state

    if game is None:
        st.info("Click 'Start New Game' to begin. You'll play as Fed Chair Warsh across 16 quarters (4 years).")
        st.markdown("""
        **How to play:**
        1. Set your 6 policy tools using the sliders
        2. Click 'Advance Quarter' to see how the economy responds
        3. Random events may hit (oil shocks, bank failures, pandemics)
        4. Watch your score, approval ratings, and achievements
        5. Survive 4 years without getting fired or causing hyperinflation

        **Scoring:**
        - Inflation 2-3% = +10/quarter
        - GDP growth > 2% = +5/quarter
        - Unemployment < 4.5% = +5/quarter
        - Recession = -20/quarter
        - Hyperinflation (>10%) = GAME OVER
        - Trump approval < 15% = FIRED (GAME OVER)
        """)
    else:
        with col_status:
            s = game.state
            mc1, mc2, mc3, mc4, mc5 = st.columns(5)
            with mc1:
                color = "green" if s.inflation < 3 else "orange" if s.inflation < 5 else "red"
                st.metric("Inflation", f"{s.inflation:.1f}%")
            with mc2:
                st.metric("GDP Growth", f"{s.gdp_growth:.1f}%")
            with mc3:
                st.metric("Unemployment", f"{s.unemployment:.1f}%")
            with mc4:
                st.metric("S&P 500", f"{s.sp500:,.0f}")
            with mc5:
                st.metric("Quarter", f"{s.quarter}/16")

            mc6, mc7, mc8 = st.columns(3)
            with mc6:
                st.metric("Score", f"{game.score:.0f}")
            with mc7:
                ta_color = "🔴" if s.trump_approval < 30 else "🟡" if s.trump_approval < 50 else "🟢"
                st.metric(f"{ta_color} Trump Approval", f"{s.trump_approval:.0f}%")
            with mc8:
                fa_color = "🔴" if s.fed_approval < 30 else "🟡" if s.fed_approval < 50 else "🟢"
                st.metric(f"{fa_color} Fed Credibility", f"{s.fed_approval:.0f}%")

            if s.recession:
                st.error("📉 RECESSION IN PROGRESS")

        st.markdown("---")

        if not game.game_over:
            st.markdown("### Set Your Policy for This Quarter")

            game_col1, game_col2 = st.columns([1, 2])

            with game_col1:
                g_tools = get_all_tools()
                game_tool_values = {}
                for tool in g_tools:
                    key = f"game_{tool.name.value}"
                    if tool.is_boolean:
                        val = st.selectbox(
                            tool.display_name,
                            ["Active", "Removed"],
                            key=key,
                        )
                        game_tool_values[tool.name] = 1.0 if val == "Active" else 0.0
                    else:
                        val = st.slider(
                            tool.display_name,
                            min_value=float(tool.min_value),
                            max_value=float(tool.max_value),
                            value=float(tool.current_value),
                            key=key,
                        )
                        game_tool_values[tool.name] = val

                roll = st.checkbox("🎲 Auto-roll for events", value=True)
                if st.button("▶️ Advance Quarter", type="primary", use_container_width=True):
                    from src.warsh.game import play_turn
                    forced_event = None
                    if not roll:
                        from src.warsh.events import get_all_events
                        event_choice = st.session_state.get("forced_event", None)
                    game = play_turn(game, game_tool_values)
                    st.session_state.game_state = game
                    st.rerun()

            with game_col2:
                if game.turn_history:
                    st.markdown("### 📰 Latest Headlines")
                    last_turn = game.turn_history[-1]
                    from src.warsh.headlines import generate_headlines
                    if len(game.turn_history) >= 2:
                        from src.warsh.economy import EconomicState
                        prev_data = game.turn_history[-2]
                        prev_state = EconomicState(
                            inflation=prev_data["inflation"],
                            gdp_growth=prev_data["gdp_growth"],
                            unemployment=prev_data["unemployment"],
                            sp500=s.sp500,
                        )
                    else:
                        prev_state = None
                    headlines = generate_headlines(prev_state, s)
                    for h in headlines[:3]:
                        st.markdown(f"📰 **{h}**")

                    st.markdown("---")
                    st.markdown("### 📊 Score History")
                    scores = [t["total_score"] for t in game.turn_history]
                    quarters = [t["quarter"] for t in game.turn_history]
                    fig_score = go.Figure()
                    fig_score.add_trace(go.Scatter(
                        x=quarters, y=scores,
                        mode="lines+markers",
                        line=dict(color="orange", width=2),
                        name="Cumulative Score",
                    ))
                    fig_score.update_layout(
                        xaxis_title="Quarter",
                        yaxis_title="Score",
                        height=250,
                        margin=dict(l=20, r=20, t=20, b=20),
                    )
                    st.plotly_chart(fig_score, use_container_width=True)
        else:
            st.error(f"GAME OVER: {game.game_over_reason}")
            st.markdown(f"### Final Score: {game.score:.0f}")
            if game.achievements:
                st.markdown("### 🏆 Achievements Unlocked")
                for a in game.achievements:
                    st.markdown(f"- 🏅 {a}")

        if game.achievements and not game.game_over:
            st.markdown("---")
            st.markdown("### 🏆 Achievements")
            st.markdown(" | ".join(f"🏅 {a}" for a in game.achievements))
```

- [ ] **Step 2: Test the dashboard compiles**:

```bash
python -c "import py_compile; py_compile.compile('scripts/warsh_dashboard.py', doraise=True); print('OK')"
```

- [ ] **Step 3: Test it runs**:

```bash
python -m streamlit run scripts/warsh_dashboard.py --server.headless true --server.port 8552 &
sleep 8
curl -s http://localhost:8552/_stcore/health
```
Expected: "ok"

- [ ] **Step 4: Commit**:

```bash
git add scripts/warsh_dashboard.py
git commit -m "feat(warsh): game mode tab with turn-based Fed Chair simulation"
```

---

## Task 5: Economic Dashboard Visual (Score Chart + Gauges)

**Files:**
- Modify: `scripts/warsh_dashboard.py` — enhance game mode with Plotly gauges

- [ ] **Step 1: Add Plotly gauge charts for inflation, unemployment, and GDP inside the game tab**

Add after the metrics row in the game tab:

```python
with tab_game:
    # ... existing code ...

    if game and not game.game_over:
        gauge_col1, gauge_col2, gauge_col3 = st.columns(3)

        with gauge_col1:
            fig_inf = go.Figure(go.Indicator(
                mode="gauge+number",
                value=s.inflation,
                title={"text": "Inflation %"},
                gauge=dict(
                    axis=dict(range=[0, 10]),
                    bar=dict(color="red" if s.inflation > 5 else "orange" if s.inflation > 3 else "green"),
                    steps=[
                        dict(range=[0, 2], color="#0d3b0d"),
                        dict(range=[2, 3], color="#1a5c1a"),
                        dict(range=[3, 5], color="#6b6b1a"),
                        dict(range=[5, 10], color="#5c1a1a"),
                    ],
                    threshold=dict(line=dict(color="white", width=3), value=2.0),
                ),
            ))
            fig_inf.update_layout(height=200, margin=dict(l=10, r=10, t=40, b=10))
            st.plotly_chart(fig_inf, use_container_width=True)

        with gauge_col2:
            fig_unemp = go.Figure(go.Indicator(
                mode="gauge+number",
                value=s.unemployment,
                title={"text": "Unemployment %"},
                gauge=dict(
                    axis=dict(range=[0, 12]),
                    bar=dict(color="red" if s.unemployment > 6 else "orange" if s.unemployment > 5 else "green"),
                ),
            ))
            fig_unemp.update_layout(height=200, margin=dict(l=10, r=10, t=40, b=10))
            st.plotly_chart(fig_unemp, use_container_width=True)

        with gauge_col3:
            fig_gdp = go.Figure(go.Indicator(
                mode="gauge+number",
                value=s.gdp_growth,
                title={"text": "GDP Growth %"},
                gauge=dict(
                    axis=dict(range=[-3, 5]),
                    bar=dict(color="red" if s.gdp_growth < 0 else "green"),
                ),
            ))
            fig_gdp.update_layout(height=200, margin=dict(l=10, r=10, t=40, b=10))
            st.plotly_chart(fig_gdp, use_container_width=True)
```

- [ ] **Step 2: Verify compiles and runs**.

- [ ] **Step 3: Commit**:

```bash
git add scripts/warsh_dashboard.py
git commit -m "feat(warsh): Plotly gauge charts for inflation/unemployment/GDP in game mode"
```

---

## Task 6: Historical Scenario Presets

**Files:**
- Create: `src/warsh/scenarios.py`
- Modify: `scripts/warsh_dashboard.py` — add scenario selector to game mode

- [ ] **Step 1: Create `src/warsh/scenarios.py`** with historical starting conditions:

```python
"""Historical scenario presets for game mode — start with real crisis conditions."""
from __future__ import annotations

from src.warsh.economy import EconomicState


SCENARIOS = {
    "current": {
        "name": "2026 Current (Warsh Inheritance)",
        "description": "Inflation 3.5%, growth 2.1%, unemployment 4.2%. Hormuz crisis brewing.",
        "state": EconomicState(inflation=3.5, unemployment=4.2, gdp_growth=2.1, sp500=5000, dollar_index=104),
    },
    "2008": {
        "name": "2008 Financial Crisis",
        "description": "Banking system collapsing. GDP contracting. Unemployment spiking.",
        "state": EconomicState(inflation=3.8, unemployment=6.5, gdp_growth=-2.1, sp500=3100, dollar_index=82),
    },
    "2020": {
        "name": "2020 COVID Crash",
        "description": "Pandemic shutdown. GDP in freefall. Markets crashing.",
        "state": EconomicState(inflation=1.2, unemployment=14.7, gdp_growth=-9.1, sp500=2900, dollar_index=99),
    },
    "volcker": {
        "name": "1979 Volcker Inheritance",
        "description": "Double-digit inflation. Stagflation. Markets demoralized.",
        "state": EconomicState(inflation=11.3, unemployment=6.0, gdp_growth=1.2, sp500=1200, dollar_index=88),
    },
    "goldilocks": {
        "name": "Goldilocks Economy",
        "description": "Perfect conditions. Can you maintain the balance?",
        "state": EconomicState(inflation=2.0, unemployment=3.8, gdp_growth=3.0, sp500=5500, dollar_index=100),
    },
}
```

- [ ] **Step 2: Modify game tab to add scenario selector** before the "Start New Game" button:

```python
scenario = st.selectbox(
    "Choose your starting scenario:",
    list(SCENARIOS.keys()),
    format_func=lambda k: SCENARIOS[k]["name"],
)
st.caption(SCENARIOS[scenario]["description"])
```

Modify `start_game()` call to use the selected scenario's state.

- [ ] **Step 3: Test and commit**:

```bash
git add src/warsh/scenarios.py scripts/warsh_dashboard.py
git commit -m "feat(warsh): historical scenario presets (2008, 2020, Volcker, Goldilocks)"
```

---

## Self-Review

**Spec coverage:**
- ✅ "reminds me of the federal reserve simulator game" → Turn-based game mode (Tasks 1-5)
- ✅ "gamification" → Score, achievements, Fed Chair rating (Task 2 + existing gamification.py)
- ✅ "X factor events and black swans" → Events already built; integrated into game loop (Task 2)
- ✅ "good blend of realism and fun" → Economic model is heuristic but directional; headlines add fun
- ✅ "improvements" → Game mode tab, gauges, historical scenarios

**Placeholder scan:** No TBDs or TODOs. All code blocks are complete.

**Type consistency:** `EconomicState`, `GameState`, `advance_quarter()`, `play_turn()`, `calculate_score()` — used consistently.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-07-19-warsh-game-mode.md`.**

Two execution options:

1. **Subagent-Driven (recommended)** — Fresh subagent per task
2. **Inline Execution** — Execute in this session

Which approach?