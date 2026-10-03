"""Tests for the Q1 runner (wave 2b, g4).

Synthetic worlds with known answers, through the core ``run`` function
(not the CLI), using the documented test seams (``only_signals`` /
``fires_override``; production runs leave them None).  Determinism and
the frame-hash guard are pinned.  No network, no cache dependence.
"""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from src.research.btc_bottoms import run_study
from src.research.btc_bottoms.run_study import (
    BOUNCE_2026,
    evaluable_events,
    event_sets,
    latest_question,
    run,
    verify_frame_hash,
)

# ---------------------------------------------------------------------------
# Synthetic world
# ---------------------------------------------------------------------------

N = 1000
IDX = pd.date_range("2024-01-01", periods=N, freq="D", name="ts")
A_BOTTOMS = [200, 550, 810]  # irregular spacing
B_BOTTOM = 400
P_BOTTOM = 900  # provisional 2026-analogue


def _events_cycle() -> pd.DataFrame:
    rows = []
    for b in A_BOTTOMS:
        rows.append(
            {
                "peak_date": IDX[b - 150],
                "bottom_date": IDX[b],
                "confirm_date": IDX[b + 20],
                "severity": "bear_bottom",
                "provisional": False,
                "bottom_price": 50.0,
                "horizon": "cycle",
            }
        )
    rows.append(
        {
            "peak_date": IDX[B_BOTTOM - 100],
            "bottom_date": IDX[B_BOTTOM],
            "confirm_date": IDX[B_BOTTOM + 15],
            "severity": "deep_correction",
            "provisional": False,
            "bottom_price": 70.0,
            "horizon": "cycle",
        }
    )
    rows.append(
        {
            "peak_date": IDX[P_BOTTOM - 120],
            "bottom_date": IDX[P_BOTTOM],
            "confirm_date": IDX[P_BOTTOM + 30],
            "severity": "deep_correction",
            "provisional": True,
            "bottom_price": 60.0,
            "horizon": "cycle",
        }
    )
    return pd.DataFrame(rows).sort_values("bottom_date").reset_index(drop=True)


def _events_swing() -> pd.DataFrame:
    rows = []
    for b in (100, 350, 620, 700):
        rows.append(
            {
                "peak_date": IDX[b - 30],
                "bottom_date": IDX[b],
                "confirm_date": IDX[b + 8],
                "severity": None,
                "provisional": False,
                "bottom_price": 80.0,
                "horizon": "swing",
            }
        )
    return pd.DataFrame(rows)


def _frame_asof() -> pd.DataFrame:
    closes = np.full(N, 100.0)
    closes[150:200] = np.linspace(120.0, 60.0, 50)  # crash into bottom 1
    closes[500:550] = np.linspace(110.0, 55.0, 50)
    closes[760:810] = np.linspace(115.0, 58.0, 50)
    fgi = np.full(N, 50.0)
    fgi[100:106] = 10.0
    fgi[600:606] = 12.0
    return pd.DataFrame({"close": closes, "volume": np.full(N, 1e6), "fgi_value": fgi}, index=IDX)


def _data() -> dict:
    return {
        "sha256": "0" * 64,
        "commit": "synthetic",
        "frame": None,
        "frame_asof": _frame_asof(),
        "events_cycle": _events_cycle(),
        "events_swing": _events_swing(),
    }


def _leader_fire() -> pd.Series:
    """Fires 30 days before each A bottom (perfect leader)."""
    s = pd.Series(False, index=IDX, dtype="boolean")
    for b in A_BOTTOMS:
        s.iloc[b - 30 : b - 25] = True
    return s


def _noise_fire() -> pd.Series:
    """Fires only in verified window-free gaps (cycle pre 180 windows
    cover [20,570] and [630,830]; swing pre 30 windows cover
    [70,108],[320,358],[590,628],[670,708])."""
    s = pd.Series(False, index=IDX, dtype="boolean")
    s.iloc[572:578] = True
    s.iloc[950:956] = True
    return s


# ---------------------------------------------------------------------------
# Frame hash guard
# ---------------------------------------------------------------------------


class TestFrameHash:
    def test_mismatch_raises(self, tmp_path):
        p = tmp_path / "frame.parquet"
        p.write_bytes(b"not the frozen frame")
        with pytest.raises(ValueError, match="hash mismatch"):
            verify_frame_hash(p)

    def test_match_returns_digest(self, tmp_path):
        p = tmp_path / "frame.parquet"
        p.write_bytes(b"frozen bytes")
        expected = hashlib.sha256(b"frozen bytes").hexdigest()
        assert verify_frame_hash(p, expected=expected) == expected


# ---------------------------------------------------------------------------
# Event sets and evaluability
# ---------------------------------------------------------------------------


class TestEventSets:
    def test_a_b_p_s_split(self):
        sets = event_sets(_events_cycle(), _events_swing())
        assert len(sets["A"]) == 3
        assert len(sets["B"]) == 1
        assert len(sets["P"]) == 1
        assert bool(sets["P"].iloc[0]["provisional"]) is True
        assert len(sets["S"]) == 4
        assert len(sets["A+B (pooled, descriptive)"]) == 4

    def test_evaluable_drops_nan_windows_and_lists_them(self):
        value = pd.Series(50.0, index=IDX)
        value.iloc[:601] = np.nan  # FGI-like: absent before 2025-08
        ev, dropped = evaluable_events(value, _events_cycle(), pre_window=180)
        # The 2024-07 bottom (day 200) and 2025-02 (day 400) windows are
        # fully inside the NaN region -> dropped; day 550 bottom (window
        # from day 370) has non-NaN values -> kept... window is
        # [bottom-180, confirm]; day 550 window starts at 370 < 601 -> all
        # NaN -> dropped too. Only days 810 and 900 survive.
        assert [str(d.date()) for d in dropped] == [str(IDX[b].date()) for b in (200, 400, 550)]
        assert len(ev) == 2


# ---------------------------------------------------------------------------
# The 2026 question (set P)
# ---------------------------------------------------------------------------


class TestLatestQuestion:
    def test_fields_as_constructed(self):
        fire = pd.Series(False, index=IDX, dtype="boolean")
        # 20 days before the low = 2026-05-29, safely AFTER the
        # BOUNCE_2026 cutoff (2026-05-10), so no prior false confirmation.
        fire.iloc[P_BOTTOM - 20 : P_BOTTOM - 15] = True
        close = pd.Series(np.linspace(100.0, 150.0, N), index=IDX)
        p_event = _events_cycle()[_events_cycle()["provisional"]]
        q = latest_question(fire, close, p_event)
        first = IDX[P_BOTTOM - 20]
        assert q["first_fire"] == str(first.date())
        assert q["days_vs_low"] == 20
        assert q["days_vs_confirm"] == 50
        assert q["close_at_first_fire"] == pytest.approx(float(close.loc[first]))
        assert q["premium_vs_low_close"] == pytest.approx(
            float(close.loc[first]) / float(close.loc[IDX[P_BOTTOM]]) - 1.0
        )
        assert q["return_first_fire_to_last_row"] == pytest.approx(
            float(close.loc[IDX[-1]]) / float(close.loc[first]) - 1.0
        )
        assert q["prior_false_confirmation"] is False  # fires after BOUNCE cutoff

    def test_prior_false_confirmation_uses_the_bounce_date(self):
        # Fire during the drawdown BEFORE the 2026-05-10 bounce analogue.
        fire = pd.Series(False, index=IDX, dtype="boolean")
        fire.iloc[P_BOTTOM - 100] = True  # ~4 months before the low
        close = pd.Series(np.full(N, 100.0), index=IDX)
        p_event = _events_cycle()[_events_cycle()["provisional"]]
        # The synthetic P event is in 2026; the real BOUNCE_2026 date
        # must gate the flag, so manufacture the check directly: a fire
        # on/before BOUNCE_2026 inside the span counts as prior.
        fire2 = fire.copy()
        fire2.loc[BOUNCE_2026 - pd.Timedelta(days=1)] = True
        # Extend the span to cover the real bounce date.
        ev = p_event.copy()
        ev["peak_date"] = [min(ev["peak_date"].iloc[0], BOUNCE_2026 - pd.Timedelta(days=30))]
        q = latest_question(fire2, close, ev)
        assert q["prior_false_confirmation"] is True


# ---------------------------------------------------------------------------
# End to end through run() (seams documented in run_study docstring)
# ---------------------------------------------------------------------------


class TestRunEndToEnd:
    def test_p_never_enters_the_battery(self):
        results = run(
            only_signals=["dd_ath"],
            fires_override={"dd_ath": _leader_fire()},
            data=_data(),
            placebo_shifts=10,
            placebo_seed=1,
        )
        battery = results["signals"]["dd_ath"]["battery"]
        assert "P" not in battery
        assert set(battery) == {"A", "B", "S", "A+B (pooled, descriptive)"}
        # P appears only as the question view.
        assert "question_2026" in results["signals"]["dd_ath"]

    def test_perfect_leader_and_noise_labels(self):
        results = run(
            only_signals=["dd_ath", "fgi"],
            fires_override={"dd_ath": _leader_fire(), "fgi": _noise_fire()},
            data=_data(),
            placebo_shifts=15,
            placebo_seed=1,
        )
        sig = results["signals"]
        # Perfect leader on A: 3/3 covered -> candidate or weak (the
        # synthetic sweep metrics decide which; both obey the rule).
        assert sig["dd_ath"]["battery"]["A"]["metrics"]["n_covered"] == 3
        assert sig["dd_ath"]["battery"]["A"]["metrics"]["n_events"] == 3
        assert sig["dd_ath"]["battery"]["A"]["metrics"]["mean_lead_days"] == 30.0
        assert sig["dd_ath"]["label_A"] in {"candidate", "weak"}
        # Noise: never a hit -> no evidence on every set.
        for set_label in ("label_A", "label_S"):
            assert sig["fgi"][set_label] == "no evidence"
        assert sig["fgi"]["battery"]["A"]["metrics"]["n_covered"] == 0
        # B has one event -> cannot evaluate by the n_evaluable rule.
        assert sig["dd_ath"]["label_B"] == "cannot evaluate"
        assert sig["fgi"]["label_B"] == "cannot evaluate"
        # Pooled is descriptive.
        assert sig["dd_ath"]["label_A+B"] == "pooled, descriptive only"

    def test_determinism_and_json(self, tmp_path):
        j1, j2 = tmp_path / "r1.json", tmp_path / "r2.json"
        r1 = run(
            only_signals=["dd_ath"],
            fires_override={"dd_ath": _leader_fire()},
            data=_data(),
            placebo_shifts=8,
            placebo_seed=3,
            out_json=j1,
        )
        r2 = run(
            only_signals=["dd_ath"],
            fires_override={"dd_ath": _leader_fire()},
            data=_data(),
            placebo_shifts=8,
            placebo_seed=3,
            out_json=j2,
        )
        assert json.loads(j1.read_text()) == json.loads(j2.read_text())
        assert _plain(r1) == _plain(r2)

    def test_cells_counted(self):
        results = run(
            only_signals=["dd_ath"],
            fires_override={"dd_ath": _leader_fire()},
            data=_data(),
            placebo_shifts=5,
            placebo_seed=1,
        )
        assert results["primary_cells"] == 38  # plan denominator, always printed
        assert results["sweep_cells_per_signal"]["dd_ath"] >= 1


def _plain(obj):
    """Round-trip through json for a plain-dict comparison."""
    return json.loads(json.dumps(run_study._to_builtin(obj)))
