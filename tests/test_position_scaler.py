"""Offline coverage for src/analysis/position_scaler.py.

PositionScaler is risk-critical sizing maths: streak-based scaling (3 wins
→ 2 contracts, 6 → 4, 2 losses → base), quarter-Kelly blending
(``get_recommended_size``), signal-strength adjustment
(``get_size_with_confidence``), and ``calculate_performance_stats`` from a
trade list. Pure logic — no clients to fake.

Trade objects are modelled with ``SimpleNamespace(win=..., pnl=...)``.

Tests marked ``test_bug_*`` fail on the pre-fix module (proven against a
HEAD copy in the cycle-16 report). None of the fixes change the size for
VALID input — the before/after table in the report covers every invalid
input whose outcome changed. Prefer rejecting invalid input (fall back to
streak-only / zero-Kelly / weakest-signal) over guessing.
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from src.analysis.position_scaler import (
    PositionScaler,
    ScalingStats,
    calculate_performance_stats,
)


def _trade(win, pnl=None):
    return SimpleNamespace(win=win, pnl=(500.0 if win else -250.0) if pnl is None else pnl)


def _wins(n):
    return [_trade(True) for _ in range(n)]


def _losses(n):
    return [_trade(False) for _ in range(n)]


def _stats(
    win_rate=60.0,
    avg_win=200.0,
    avg_loser=100.0,
    total=50,
    recent=None,
    cw=0,
    cl=0,
):
    return ScalingStats(
        win_rate=win_rate,
        average_winner=avg_win,
        average_loser=avg_loser,
        consecutive_wins=cw,
        consecutive_losses=cl,
        total_trades=total,
        recent_trades=recent or [],
    )


# ---------------------------------------------------------------------------
# Streak counting
# ---------------------------------------------------------------------------


def test_count_consecutive_wins_and_losses():
    s = PositionScaler()
    assert s.count_consecutive_wins([]) == 0
    assert s.count_consecutive_losses([]) == 0
    trades = _losses(2) + _wins(3)
    assert s.count_consecutive_wins(trades) == 3
    assert s.count_consecutive_losses(trades) == 0
    assert s.count_consecutive_wins(_wins(5)) == 5
    assert s.count_consecutive_losses(_losses(4)) == 4


def test_streak_counting_with_unset_win_field():
    s = PositionScaler()
    unset = SimpleNamespace(pnl=1.0)  # no .win attribute
    assert s.count_consecutive_wins([unset]) == 0
    # win=None (falsy) breaks the win streak and counts as a loss
    none_win = SimpleNamespace(win=None, pnl=1.0)
    assert s.count_consecutive_wins([none_win]) == 0
    assert s.count_consecutive_losses([none_win]) == 1


# ---------------------------------------------------------------------------
# Streak-based sizing
# ---------------------------------------------------------------------------


def test_contracts_from_streak_tiers():
    s = PositionScaler()
    assert s.calculate_contracts_from_streak([]) == 1
    assert s.calculate_contracts_from_streak(_wins(2)) == 1
    assert s.calculate_contracts_from_streak(_wins(3)) == 2  # scale_up_threshold
    assert s.calculate_contracts_from_streak(_wins(5)) == 2
    assert s.calculate_contracts_from_streak(_wins(6)) == 4  # hardcoded second tier
    assert s.calculate_contracts_from_streak(_wins(10)) == 4


def test_contracts_from_streak_loss_resets():
    s = PositionScaler()
    assert s.calculate_contracts_from_streak(_wins(5) + _losses(2)) == 1
    # A single trailing loss already breaks the win streak (counted from the
    # end), but scaling to base needs scale_down_threshold losses.
    assert s.calculate_contracts_from_streak(_losses(1) + _wins(3)) == 2
    assert s.calculate_contracts_from_streak(_wins(5) + _losses(1)) == 1


def test_contracts_custom_thresholds_and_bounds():
    s = PositionScaler(base_contracts=2, max_contracts=6, scale_up_threshold=4, scale_down_threshold=1)
    assert s.calculate_contracts_from_streak(_wins(4)) == 2
    assert s.calculate_contracts_from_streak(_losses(1)) == 2


# ---------------------------------------------------------------------------
# Kelly
# ---------------------------------------------------------------------------


def test_kelly_requires_data():
    s = PositionScaler()
    assert s.calculate_kelly_size(_stats(win_rate=0.0)) == 0.0
    assert s.calculate_kelly_size(_stats(avg_loser=0.0)) == 0.0
    assert s.calculate_kelly_size(_stats(total=9)) == 0.0


def test_kelly_happy_path_quarter_kelly():
    s = PositionScaler(kelly_fraction=0.25)
    # b=2, p=0.6, q=0.4 -> kelly=(2*0.6-0.4)/2=0.4 -> quarter -> 0.1
    assert s.calculate_kelly_size(_stats()) == pytest.approx(0.1)


def test_kelly_clamps_negative_and_above_one():
    s = PositionScaler(kelly_fraction=1.0)
    # negative edge: win_rate 30%, even odds -> -0.4 -> clamped to 0
    assert s.calculate_kelly_size(_stats(win_rate=30.0, avg_win=100.0, avg_loser=100.0)) == 0.0
    # extreme edge: p=1.0 -> kelly=1.0 -> clamped at 1.0
    assert s.calculate_kelly_size(_stats(win_rate=100.0, avg_win=300.0, avg_loser=100.0)) == pytest.approx(1.0)


def test_bug_kelly_zero_average_winner_no_crash():
    # b = 0/loser = 0 -> division by zero on the old code.
    s = PositionScaler()
    assert s.calculate_kelly_size(_stats(avg_win=0.0)) == 0.0


def test_bug_kelly_none_fields_no_crash():
    s = PositionScaler()
    assert s.calculate_kelly_size(_stats(win_rate=None)) == 0.0
    assert s.calculate_kelly_size(_stats(avg_win=None)) == 0.0
    assert s.calculate_kelly_size(_stats(avg_loser=None)) == 0.0


def test_kelly_nan_inputs_return_zero():
    # NaN propagates into min/max and happens to land at 0.0 today; pinned
    # explicitly so a refactor cannot turn it into a crash or a position.
    s = PositionScaler()
    assert s.calculate_kelly_size(_stats(win_rate=math.nan)) == 0.0
    assert s.calculate_kelly_size(_stats(avg_win=math.nan)) == 0.0
    assert s.calculate_kelly_size(_stats(avg_loser=math.inf)) == 0.0


# ---------------------------------------------------------------------------
# get_recommended_size
# ---------------------------------------------------------------------------


def test_recommend_without_kelly_or_history():
    s = PositionScaler(max_contracts=8)
    assert s.get_recommended_size(_stats(recent=_wins(6)), use_kelly=False) == 4
    assert s.get_recommended_size(_stats(recent=_wins(6), total=9), use_kelly=True) == 4  # too few trades


def test_recommend_negative_edge_falls_to_base():
    s = PositionScaler()
    stats = _stats(recent=_wins(3), win_rate=30.0, avg_win=100.0, avg_loser=100.0)
    assert s.get_recommended_size(stats, account_balance=10000) == 1  # kelly <= 0


def test_recommend_kelly_caps_streak():
    s = PositionScaler(kelly_fraction=0.25)
    # kelly 0.1 * 10000 / 1000 -> 1 contract from Kelly; streak wants 2
    stats = _stats(recent=_wins(3))
    assert s.get_recommended_size(stats, account_balance=10000) == 1
    # richer account lets the streak through
    assert s.get_recommended_size(stats, account_balance=100000) == 2


def test_recommend_respects_max_cap():
    s = PositionScaler(base_contracts=1, max_contracts=3)
    stats = _stats(recent=_wins(10), win_rate=100.0, avg_win=500.0, avg_loser=100.0)
    assert s.get_recommended_size(stats, account_balance=10_000_000) == 3


def test_bug_recommend_nan_balance_no_crash():
    s = PositionScaler()
    stats = _stats(recent=_wins(3))
    assert s.get_recommended_size(stats, account_balance=math.nan) == 2  # streak-only path


def test_bug_recommend_inf_balance_no_crash():
    s = PositionScaler()
    stats = _stats(recent=_wins(3))
    assert s.get_recommended_size(stats, account_balance=math.inf) == 2


def test_bug_recommend_none_balance_no_crash():
    s = PositionScaler()
    stats = _stats(recent=_wins(3))
    assert s.get_recommended_size(stats, account_balance=None) == 2


def test_bug_recommend_nonpositive_balance_uses_streak_path():
    s = PositionScaler()
    stats = _stats(recent=_wins(3))
    # A non-positive balance makes the Kelly leg meaningless: reject that leg
    # (streak-only, capped) rather than silently forcing base contracts.
    assert s.get_recommended_size(stats, account_balance=0) == 2
    assert s.get_recommended_size(stats, account_balance=-5000) == 2


# ---------------------------------------------------------------------------
# get_size_with_confidence
# ---------------------------------------------------------------------------


def test_confidence_sizing_tiers_and_floor():
    s = PositionScaler()
    stats = _stats(recent=_wins(3))
    strong = s.get_size_with_confidence(stats, signal_strength=85)
    assert strong["strength_multiplier"] == 1.0 and strong["contracts"] == strong["base_size"]
    weak = s.get_size_with_confidence(stats, signal_strength=40)
    assert weak["strength_multiplier"] == 0.25
    assert weak["contracts"] >= s.base_contracts  # weak signals floor at base (pinned)


def test_confidence_payload_shape():
    s = PositionScaler()
    out = s.get_size_with_confidence(_stats(recent=_wins(3)), signal_strength=75)
    for key in (
        "contracts",
        "base_size",
        "strength_multiplier",
        "signal_strength",
        "confidence",
        "consecutive_wins",
        "consecutive_losses",
        "win_rate",
        "kelly_fraction",
        "reason",
    ):
        assert key in out, key
    assert 0.0 <= out["confidence"] <= 100.0
    assert out["reason"]


def test_confidence_grows_with_signal_strength():
    s = PositionScaler()
    stats = _stats(total=40)
    low = s.get_size_with_confidence(stats, signal_strength=30)["confidence"]
    high = s.get_size_with_confidence(stats, signal_strength=90)["confidence"]
    assert high > low
    assert high <= 100.0


def test_bug_confidence_none_signal_no_crash():
    s = PositionScaler()
    out = s.get_size_with_confidence(_stats(recent=_wins(3)), signal_strength=None)
    assert out["strength_multiplier"] == 0.25  # treated as weakest signal


def test_bug_confidence_nan_signal_not_max_confidence():
    s = PositionScaler()
    out = s.get_size_with_confidence(_stats(total=0, recent=[]), signal_strength=math.nan)
    # Old code: NaN skipped every tier (-> 0.25 multiplier) but the NaN signal
    # score fell through min() as 100 confidence. Invalid input must not read
    # as maximum confidence.
    assert out["confidence"] < 100.0
    assert math.isfinite(out["confidence"])


def test_bug_confidence_out_of_range_signal_clamped():
    s = PositionScaler()
    stats = _stats(win_rate=0.0, total=0, recent=[])
    # 150 strength clamps to 100 -> score 25; old code scored 37.5.
    assert s.get_size_with_confidence(stats, signal_strength=150)["confidence"] == pytest.approx(35.0)
    assert s.get_size_with_confidence(stats, signal_strength=-20)["confidence"] == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# calculate_performance_stats
# ---------------------------------------------------------------------------


def test_performance_stats_empty_and_none():
    for trades in ([], None):
        stats = calculate_performance_stats(trades)
        assert stats.win_rate == 0.0 and stats.total_trades == 0
        assert stats.recent_trades == []


def test_performance_stats_mixed_history():
    trades = _losses(2) + _wins(3) + [_trade(True, pnl=1000.0), _trade(False, pnl=-500.0)]
    stats = calculate_performance_stats(trades)
    assert stats.total_trades == 7  # 2 losses + 3 wins + 1 win + 1 loss
    assert stats.win_rate == pytest.approx(100.0 * 4 / 7)
    assert stats.average_winner == pytest.approx((500 + 500 + 500 + 1000) / 4)
    assert stats.average_loser == pytest.approx((-250 - 250 - 500) / 3)
    assert stats.consecutive_wins == 0  # last trade is a loss
    assert stats.consecutive_losses == 1


def test_performance_stats_caps_recent_at_20():
    trades = _wins(30)
    stats = calculate_performance_stats(trades)
    assert len(stats.recent_trades) == 20
    # Streak counting runs over the FULL history, not the trimmed window.
    assert stats.consecutive_wins == 30
