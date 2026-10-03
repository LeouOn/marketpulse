"""Tests for the bottom-signal evaluation engine (wave 2a, g4).

Synthetic worlds where the truth is known, per the assignment:

* a perfect leader (hit rate 1, lift = 1 / base_rate);
* a pure-noise / never-near signal (placebo says unremarkable);
* a late-only signal (counted late, never usable);
* cooldown merging, overlap flagging, leave-one-out, determinism;
* mutation-pin tests: the lead-sign convention and the base-rate
  denominator are pinned by construction (flip the implementation and
  one of these fails);
* provisional-event exclusion, horizon filtering, empty inputs;
* a report-only latest-event view; markdown rendering keeps counts.

All offline; deterministic seeds only.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.research.btc_bottoms.study import (
    episodes,
    evaluate,
    evaluate_combination,
    forward_returns,
    latest_event_view,
    leave_one_out,
    placebo,
    render_markdown,
    summarise,
    sweep,
)

START = "2020-01-01"
N = 1000
IDX = pd.date_range(START, periods=N, freq="D", name="ts")
BOTTOMS = [200, 550, 810]  # day positions within IDX (irregular spacing)
CONFIRM_LAG = 20
BOTTOM_DATES = [IDX[b] for b in BOTTOMS]
CONFIRM_DATES = [IDX[b + CONFIRM_LAG] for b in BOTTOMS]

CFG = dict(pre_window=60, cooldown=10, forward_window=100)


def make_events(
    bottoms: list[int] | None = None,
    confirm_lag: int = CONFIRM_LAG,
    horizon: str | None = "cycle",
    provisional: list[bool] | None = None,
    bottom_price: list[float] | None = None,
) -> pd.DataFrame:
    """Contract-shaped events table from day positions."""
    bottoms = bottoms if bottoms is not None else BOTTOMS
    ev = pd.DataFrame(
        {
            "bottom_date": [IDX[b] for b in bottoms],
            "confirm_date": [IDX[min(b + confirm_lag, N - 1)] for b in bottoms],
        }
    )
    if horizon is not None:
        ev["horizon"] = horizon
    if provisional is not None:
        ev["provisional"] = provisional
    if bottom_price is not None:
        ev["bottom_price"] = bottom_price
    return ev


def fire_at(ranges: list[tuple[int, int]], n: int = N) -> pd.Series:
    """Boolean fire series, True on [a, b) day ranges."""
    s = pd.Series(False, index=IDX[:n])
    for a, b in ranges:
        s.iloc[a:b] = True
    return s


# ---------------------------------------------------------------------------
# Episodes and cooldown merging
# ---------------------------------------------------------------------------


class TestEpisodes:
    def test_runs_and_merge(self):
        s = fire_at([(100, 105), (115, 120), (400, 402)])
        eps = episodes(s, cooldown=10)
        # gap 115-104 = 11 > 10 -> NOT merged; use cooldown=15 to merge
        eps_merged = episodes(s, cooldown=15)
        assert len(eps) == 3
        assert len(eps_merged) == 2
        assert eps_merged.iloc[0]["start"] == IDX[100]
        assert eps_merged.iloc[0]["end"] == IDX[119]
        assert eps.iloc[0]["length_days"] == 4

    def test_merge_boundary_is_inclusive(self):
        # runs at days 100-104 and 116-119: gap = 116 - 104 = 12
        # (fire_at ranges are half-open).  Documented rule: gap <= cooldown merges.
        s = fire_at([(100, 105), (116, 120)])
        assert len(episodes(s, cooldown=12)) == 1
        assert len(episodes(s, cooldown=11)) == 2

    def test_na_reads_false_and_empty_ok(self):
        s = fire_at([(10, 15)]).astype("boolean")
        s.iloc[20] = pd.NA
        eps = episodes(s, cooldown=5)
        assert len(eps) == 1
        empty = pd.Series(False, index=IDX)
        assert len(episodes(empty, cooldown=5)) == 0


# ---------------------------------------------------------------------------
# The perfect leader (fixes the metric conventions)
# ---------------------------------------------------------------------------


class TestPerfectLeader:
    def test_hit_rate_lead_precision_lift(self):
        # Fires 30 days before each bottom, for 5 days.
        fire = fire_at([(b - 30, b - 25) for b in BOTTOMS])
        et = evaluate(fire, make_events(), **CFG)
        m = et.metrics
        assert m["n_events"] == 3
        assert m["n_covered"] == 3
        assert m["hit_rate"] == 1.0
        assert m["mean_lead_days"] == 30.0
        assert m["min_lead_days"] == m["max_lead_days"] == 30.0
        assert m["n_episodes"] == 3
        assert m["n_episode_hits"] == 3
        assert m["precision"] == 1.0
        # Base rate: each bottom covers F+1 = 101 anchor days; bottoms
        # are 300 days apart, so no overlap: 303/1000.
        assert m["base_rate_k"] == 303
        assert m["base_rate_n"] == 1000
        assert m["base_rate"] == pytest.approx(0.303)
        assert m["lift"] == pytest.approx(1.0 / 0.303)
        # MUTATION PIN (lead sign): lead = bottom - first_hit_start.
        # If the implementation flips the sign, this fails (and the
        # after-the-low test below fails the other way).
        assert m["mean_lead_days"] == 30.0
        # MUTATION PIN (base-rate denominator): the denominator is the
        # window-coverage fraction of days (0.303), NOT n_events/n_days
        # (0.003) nor 1/n_events; a mutated denominator moves lift by
        # ~100x and this assertion fails.
        assert m["lift"] == pytest.approx(3.3003, rel=1e-3)

    def test_lead_is_negative_when_firing_after_the_low(self):
        # Fires 10 days AFTER the bottom but before confirm (+20):
        # still a hit (identifiable window), lead must be negative.
        fire = fire_at([(b + 10, b + 12) for b in BOTTOMS])
        m = evaluate(fire, make_events(), **CFG).metrics
        assert m["n_covered"] == 3
        assert m["mean_lead_days"] == -10.0

    def test_crying_wolf_lowers_precision(self):
        # One extra episode far from any bottom.
        fire = fire_at([(b - 30, b - 25) for b in BOTTOMS] + [(50, 55)])
        m = evaluate(fire, make_events(), **CFG).metrics
        assert m["n_covered"] == 3  # all events still covered
        assert m["n_episodes"] == 4
        assert m["n_episode_hits"] == 3
        assert m["precision"] == pytest.approx(3 / 4)
        assert m["lift"] == pytest.approx(0.75 / 0.303, rel=1e-3)


class TestLateOnly:
    def test_fires_after_confirmation_counted_late(self):
        fire = fire_at([(b + CONFIRM_LAG + 1, b + CONFIRM_LAG + 6) for b in BOTTOMS])
        m = evaluate(fire, make_events(), **CFG).metrics
        assert m["n_covered"] == 0
        assert m["n_late_only"] == 3
        assert m["n_missed"] == 0  # late_only, not missed
        assert m["hit_rate"] == 0.0

    def test_fires_way_after_is_missed_not_late(self):
        # post_window defaults to forward_window=100: firing at
        # bottom+150 is outside both windows -> plain miss.
        fire = fire_at([(b + 150, b + 155) for b in BOTTOMS])
        m = evaluate(fire, make_events(), **CFG).metrics
        assert m["n_covered"] == 0
        assert m["n_late_only"] == 0
        assert m["n_missed"] == 3


# ---------------------------------------------------------------------------
# Placebo
# ---------------------------------------------------------------------------


class TestPlacebo:
    def test_never_near_events_is_unremarkable(self):
        # A single burst far from every event: zero observed hits, and
        # p_hits is exactly 1.0 because >= 0 is always true.  The
        # engine must not dress that up as evidence.
        fire = fire_at([(330, 341)])
        p = placebo(fire, make_events(), shifts=200, seed=7, **CFG)
        assert p.observed_hits == 0
        assert p.p_hits == 1.0
        assert "not a p-value" in p.power_note
        assert "resolution" in p.power_note

    def test_perfect_leader_beats_rotations_but_power_is_limited(self):
        # A deterministic leader covers 3/3; rigid circular rotations keep
        # the bursts' relative geometry (built at fixed offsets from the
        # same events), so a nontrivial fraction of rotations still covers
        # all three wide windows.  The honest assertions: most rotations do
        # worse than the truth, and the power note says so.  This is the
        # engine's real resolution limit, not a bug.
        fire = fire_at([(b - 30, b - 25) for b in BOTTOMS])
        p = placebo(fire, make_events(), shifts=300, seed=7, **CFG)
        assert p.observed_hits == 3
        assert 0 < p.p_hits <= 0.15
        assert p.p_lift <= 0.5
        assert "resolution" in p.power_note

    def test_determinism(self):
        fire = fire_at([(170, 190), (640, 660)])
        a = placebo(fire, make_events(), shifts=100, seed=13, **CFG)
        b = placebo(fire, make_events(), shifts=100, seed=13, **CFG)
        assert a.p_hits == b.p_hits
        assert a.p_lift == b.p_lift


# ---------------------------------------------------------------------------
# Robustness sweep and combinations
# ---------------------------------------------------------------------------


def _frame_for_sweep() -> pd.DataFrame:
    rng = np.random.default_rng(3)
    n = 600
    closes = np.concatenate(
        [
            np.full(200, 100.0),
            np.linspace(100.0, 45.0, 100),  # -55% crash around day 300
            np.linspace(45.0, 80.0, 300),
        ]
    )
    return pd.DataFrame(
        {
            "close": closes,
            "volume": np.full(n, 1e6) + rng.normal(0, 1e4, n),
        },
        index=pd.date_range(START, periods=n, freq="D", name="ts"),
    )


class TestSweep:
    def test_grid_cells_counted_and_primary_marked(self):
        df = _frame_for_sweep()
        ev = pd.DataFrame(
            {
                "bottom_date": [df.index[299]],
                "confirm_date": [df.index[319]],
                "horizon": "cycle",
            }
        )
        sw = sweep(df, "dd_ath", ev, grid={"threshold": [-0.2, -0.4, -0.5]}, **CFG)
        assert sw.n_cells == 3
        assert len(sw.rows) == 3
        assert sw.rows["is_primary"].sum() == 1  # default -0.50
        assert sw.primary["n_events"] == 1
        for key in ("hit_rate", "lift"):
            assert set(sw.summary[key]) == {"median", "min", "max"}

    def test_summary_excludes_primary(self):
        df = _frame_for_sweep()
        ev = pd.DataFrame({"bottom_date": [df.index[299]], "confirm_date": [df.index[319]]})
        sw = sweep(df, "dd_ath", ev, grid={"threshold": [-0.2, -0.4, -0.5]}, **CFG)
        non_primary = sw.rows[~sw.rows["is_primary"]]
        assert sw.summary["hit_rate"]["median"] == pytest.approx(non_primary["hit_rate"].median())


class TestCombination:
    def test_and_combination_and_label(self):
        a = fire_at([(b - 30, b - 25) for b in BOTTOMS])
        b_ = fire_at([(b - 28, b - 20) for b in BOTTOMS])
        noise = fire_at([(100, 110)])
        et = evaluate_combination({"sig_a": a, "sig_b": b_}, make_events(), **CFG)
        assert et.label == "sig_a & sig_b"
        assert et.metrics["n_covered"] == 3  # overlap [b-28, b-25)
        noisy = evaluate_combination({"sig_a": a, "noise": noise}, make_events(), **CFG)
        assert noisy.metrics["n_covered"] == 0  # never co-fire
        assert noisy.metrics["n_episodes"] == 0

    def test_requires_series(self):
        with pytest.raises(ValueError, match="at least one"):
            evaluate_combination({}, make_events())


# ---------------------------------------------------------------------------
# Leave-one-out, latest view, provisional/horizon handling
# ---------------------------------------------------------------------------


class TestLeaveOneOut:
    def test_each_event_held_out(self):
        fire = fire_at([(b - 30, b - 25) for b in BOTTOMS])
        loo = leave_one_out(fire, make_events(), **CFG)
        assert len(loo) == 3
        assert list(loo["held_out_bottom"]) == BOTTOM_DATES
        assert (loo["hit_rate"] == 1.0).all()
        assert (loo["n_events"] == 2).all()

    def test_detects_one_cycle_carrying_the_result(self):
        # Signal only leads the first bottom.
        fire = fire_at([(BOTTOMS[0] - 30, BOTTOMS[0] - 25)])
        loo = leave_one_out(fire, make_events(), **CFG)
        rates = list(loo["hit_rate"])
        # Holding out the only covered event -> 0/2; holding out either
        # uncovered event -> the covered one remains -> 1/2.
        assert rates[0] == 0.0
        assert rates[1] == 0.5 and rates[2] == 0.5


class TestLatestEventView:
    def test_report_only(self):
        fire = fire_at([(b - 30, b - 25) for b in BOTTOMS])
        view = latest_event_view(fire, make_events(), **CFG)
        assert view["report_only"] is True
        assert view["bottom_date"] == BOTTOM_DATES[-1]
        assert view["covered"] is True
        assert view["lead_days"] == 30
        assert "never use it to choose thresholds" in view["note"]


class TestEventNormalisation:
    def test_provisional_excluded_by_default_with_count(self):
        fire = fire_at([(b - 30, b - 25) for b in BOTTOMS])
        ev = make_events(provisional=[False, True, False])
        m = evaluate(fire, ev, **CFG).metrics
        assert m["n_events"] == 2
        assert m["events_excluded_provisional"] == 1
        assert m["n_covered"] == 2
        m_inc = evaluate(fire, ev, include_provisional=True, **CFG).metrics
        assert m_inc["n_events"] == 3
        assert m_inc["n_covered"] == 3

    def test_horizon_filter(self):
        fire = fire_at([(b - 30, b - 25) for b in BOTTOMS])
        ev = make_events()
        ev["horizon"] = ["cycle", "swing", "cycle"]
        m = evaluate(fire, ev, horizon="cycle", **CFG).metrics
        assert m["n_events"] == 2
        assert m["events_excluded_horizon"] == 1

    def test_missing_columns_rejected(self):
        with pytest.raises(ValueError, match="bottom_date"):
            evaluate(fire_at([(10, 20)]), pd.DataFrame({"confirm_date": [IDX[5]]}))

    def test_empty_events_no_crash(self):
        m = evaluate(fire_at([(10, 20)]), make_events(bottoms=[]), **CFG).metrics
        assert m["n_events"] == 0
        assert np.isnan(m["hit_rate"])
        assert np.isnan(m["lift"])

    def test_unknown_config_key_rejected(self):
        with pytest.raises(ValueError, match="unknown config keys"):
            evaluate(fire_at([(10, 20)]), make_events(), pre_wind=5)


# ---------------------------------------------------------------------------
# Forward returns and overlap flagging
# ---------------------------------------------------------------------------


class TestForwardReturns:
    def test_values_and_overlap_counts(self):
        close = pd.Series(np.linspace(100.0, 200.0, N), index=IDX)  # +0.1%/day drift
        fire = fire_at([(100, 102), (110, 112), (900, 902)])
        # cooldown=0: with CFG's cooldown=10 the runs at 100-101 and 110-111
        # (gap 9) would merge into ONE episode.
        fr = forward_returns(
            fire,
            close,
            make_events(bottom_price=[50.0, 60.0, 70.0]),
            cooldown=0,
            **{k: v for k, v in CFG.items() if k != "cooldown"},
        )
        # closes are linspace(100..200): close[i] = 100 + i*100/999
        exp = (100 + 130 * 100 / 999) / (100 + 100 * 100 / 999) - 1.0
        got = fr.episode_returns.loc[IDX[100], 30]
        assert got == pytest.approx(exp)
        # Overlap: anchors 100 and 110 are 10 <= 30 apart -> one pair;
        # anchor 900 is 800/790 days from the others -> never within a window.
        assert fr.overlap_pairs[30] == 1
        assert fr.overlap_pairs[90] == 1
        assert fr.overlap_pairs[180] == 1
        # Further drawdown: anchor 100 -> next bottom within 100d is
        # day 200 (price 50) -> 50/close(100)-1
        dd = fr.further_drawdown.loc[IDX[100]]
        assert dd == pytest.approx(50.0 / (100 + 100 * 100 / 999) - 1.0)
        # Unconditional distribution present with full counts
        assert len(fr.unconditional_returns) == N
        assert "overlap" in fr.unconditional_overlap_note

    def test_no_bottom_price_column_gives_nan_with_frame(self):
        close = pd.Series(np.full(N, 100.0), index=IDX)
        fire = fire_at([(100, 102)])
        fr = forward_returns(fire, close, make_events(), **CFG)
        assert fr.further_drawdown.isna().all()
        assert len(fr.episode_returns) == 1


# ---------------------------------------------------------------------------
# summarise + render_markdown
# ---------------------------------------------------------------------------


class TestReporting:
    def test_summarise_keeps_counts(self):
        perfect = evaluate(fire_at([(b - 30, b - 25) for b in BOTTOMS]), make_events(), **CFG)
        late = evaluate(
            fire_at([(b + CONFIRM_LAG + 1, b + CONFIRM_LAG + 3) for b in BOTTOMS]),
            make_events(),
            **CFG,
        )
        s = summarise({"perfect": perfect, "late": late})
        assert list(s.index) == ["perfect", "late"]
        assert s.loc["perfect", "covered"] == "3/3"
        assert s.loc["late", "covered"] == "0/3"
        assert s.loc["perfect", "base_rate"] == "303/1000"

    def test_render_markdown_shows_counts_and_notes(self):
        fire = fire_at([(b - 30, b - 25) for b in BOTTOMS])
        et = evaluate(fire, make_events(), **CFG)
        p = placebo(fire, make_events(), shifts=50, seed=3, **CFG)
        md = render_markdown(
            "Test study",
            summary=summarise({"sig": et}),
            evaluations={"sig": et},
            placebos={"sig": p},
            latest={"sig": latest_event_view(fire, make_events(), **CFG)},
        )
        assert "# Test study" in md
        assert "3/3" in md
        assert "303/1000" in md
        assert "not a p-value" in md
        assert "never use it to choose thresholds" in md
        assert "k of n" in md


# ---------------------------------------------------------------------------
# Real-frame plumbing smoke (clearly synthetic events; skipif no cache)
# ---------------------------------------------------------------------------

CACHE = Path(__file__).resolve().parents[2] / "data" / "cache" / "btc" / "daily.csv"


@pytest.mark.skipif(not CACHE.exists(), reason="cached BTC daily data not present (hermetic run)")
def test_real_frame_plumbing_smoke():
    """Mechanical invariants only - the events here are SYNTHETIC
    fixtures (g3's real events table has not landed), so nothing in
    this test is a claim about real bottoms."""
    from src.research.btc_bottoms.signals import compute_signals

    df = pd.read_csv(CACHE, parse_dates=["ts"]).set_index("ts")
    out = compute_signals(df)
    bottoms = [idx for idx in (2000, 2800, 3600) if idx < len(df)]
    ev = pd.DataFrame(
        {
            "bottom_date": [df.index[b] for b in bottoms],
            "confirm_date": [df.index[min(b + 20, len(df) - 1)] for b in bottoms],
            "horizon": "cycle",
        }
    )
    m = evaluate(out["dd_ath_fire"], ev, label="dd_ath", **CFG).metrics
    assert 0 <= m["hit_rate"] <= 1
    assert m["base_rate_n"] == len(df)
    p = placebo(out["dd_ath_fire"], ev, shifts=25, seed=1, **CFG)
    assert 0 <= p.p_hits <= 1
