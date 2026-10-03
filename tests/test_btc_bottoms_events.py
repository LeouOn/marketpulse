"""Bottom-event labeller for the BTC bottom study (wave 1, g3).

``src.research.btc_bottoms.events.find_bottoms`` produces *hindsight* labels of
cycle and swing bottoms with a ``confirm_date`` marking when each low became
identifiable. These tests pin the labeller's design decisions on synthetic
price paths with hand-computed answers, plus input-contract, param-sweep and
prefix-stability behaviour. All offline: no network, no keys, no LLM.

Shape coverage required by the wave-1 brief: V shape, W shape, slow bleed,
failed bounce, still-falling-at-the-end, new-ATH-ends-episode, swing nesting
inside a cycle episode, swing window semantics, provisional marking.

Day counting convention: ``days_to_confirm`` is the number of calendar days
from ``bottom_date`` to ``confirm_date``; every hand computation below counts
day offsets from a ``2020-01-01`` daily index (day N = index position N).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.research.btc_bottoms import events as ev

# ---------------------------------------------------------------------------
# Path builders
# ---------------------------------------------------------------------------


def _frame(closes: list[float], lows: list[float] | None = None, start: str = "2020-01-01") -> pd.DataFrame:
    """Daily close-only frame (plus optional intraday lows) named per contract."""
    idx = pd.date_range(start, periods=len(closes), freq="D", name="ts")
    data: dict[str, list[float]] = {"close": [float(c) for c in closes]}
    if lows is not None:
        assert len(lows) == len(closes)
        data["low"] = [float(v) for v in lows]
    return pd.DataFrame(data, index=idx)


def _flat(*segments: tuple[float, int]) -> list[float]:
    """Flatten (level, days) segments into a close list -- exact flat levels."""
    out: list[float] = []
    for level, days in segments:
        out.extend([float(level)] * days)
    return out


def _day(i: int) -> pd.Timestamp:
    return pd.Timestamp("2020-01-01") + pd.Timedelta(days=i)


# ---------------------------------------------------------------------------
# Cycle horizon: synthetic shapes
# ---------------------------------------------------------------------------


class TestCycleShapes:
    def test_v_shape_single_event(self):
        closes = _flat((100, 5), (200, 1), (100, 5), (135, 1), (250, 10))
        lows = [c - 5 for c in closes]
        out = ev.find_bottoms(_frame(closes, lows=lows), "cycle")
        assert len(out) == 1
        row = out.iloc[0]
        assert row["horizon"] == "cycle"
        assert row["peak_date"] == _day(5) and row["peak_price"] == 200.0
        assert row["bottom_date"] == _day(6) and row["bottom_price"] == 100.0
        assert row["bottom_intraday_low"] == 95.0  # intraday low reported, not used
        assert row["drawdown"] == pytest.approx(-0.5)
        assert row["confirm_date"] == _day(11)  # first close >= 100 * 1.30 = 130
        assert row["days_to_confirm"] == 5
        assert row["recovered_date"] == _day(12)  # first close > 200 after bottom
        assert bool(row["provisional"]) is False

    def test_w_shape_single_event_at_global_min(self):
        closes = _flat((100, 3), (200, 1), (110, 4), (150, 1), (95, 4), (160, 2), (250, 5))
        out = ev.find_bottoms(_frame(closes), "cycle")
        # One bear market = one episode ATH -> new ATH: the +36% bounce off 110
        # must NOT split it; the label is the span minimum.
        assert len(out) == 1
        row = out.iloc[0]
        assert row["peak_date"] == _day(3) and row["peak_price"] == 200.0
        assert row["bottom_date"] == _day(9) and row["bottom_price"] == 95.0
        assert row["drawdown"] == pytest.approx(-0.525)
        assert row["confirm_date"] == _day(13)  # 160 >= 95 * 1.30 = 123.5
        assert row["days_to_confirm"] == 4
        assert row["recovered_date"] == _day(15)  # new ATH ends the episode
        assert bool(row["provisional"]) is False

    def test_cycle_bounce_without_new_ath_stays_provisional(self):
        closes = _flat((100, 3), (200, 1), (100, 4), (140, 2))
        out = ev.find_bottoms(_frame(closes), "cycle")
        assert len(out) == 1
        row = out.iloc[0]
        # The +40% bounce makes the low identifiable, but the episode is still
        # open: without a new ATH the bottom is NOT final.
        assert bool(row["provisional"]) is True
        assert row["bottom_date"] == _day(4) and row["bottom_price"] == 100.0
        assert row["confirm_date"] == _day(8)  # 140 >= 100 * 1.30
        assert pd.isna(row["recovered_date"])

    def test_slow_bleed_single_event(self):
        closes = [200] + [180, 165, 150, 140, 145, 135, 125, 120, 124, 115, 105] + [140, 160, 210]
        out = ev.find_bottoms(_frame(closes), "cycle")
        assert len(out) == 1
        row = out.iloc[0]
        # Small bounces (+3.6%, +3.3%) must not confirm or split the episode.
        assert row["bottom_date"] == _day(11) and row["bottom_price"] == 105.0
        assert row["confirm_date"] == _day(12)  # 140 >= 105 * 1.30 = 136.5
        assert row["recovered_date"] == _day(14)  # 210 > 200

    def test_failed_bounce_does_not_confirm(self):
        closes = _flat((100, 2), (200, 1), (100, 3), (125, 2), (90, 2), (130, 1), (250, 3))
        out = ev.find_bottoms(_frame(closes), "cycle")
        assert len(out) == 1
        row = out.iloc[0]
        # +25% off 100 stays inside the episode; the low moves to 90.
        assert row["bottom_date"] == _day(8) and row["bottom_price"] == 90.0
        assert row["confirm_date"] == _day(10)  # 130 >= 90 * 1.30 = 117
        assert row["days_to_confirm"] == 2
        assert row["recovered_date"] == _day(11)

    def test_still_falling_at_end_is_provisional(self):
        closes = _flat((100, 3), (200, 1), (120, 2), (100, 4), (85, 3))
        out = ev.find_bottoms(_frame(closes), "cycle")
        assert len(out) == 1
        row = out.iloc[0]
        assert bool(row["provisional"]) is True
        assert row["bottom_date"] == _day(10) and row["bottom_price"] == 85.0
        assert row["drawdown"] == pytest.approx(-0.575)
        assert pd.isna(row["confirm_date"])
        assert pd.isna(row["days_to_confirm"])
        assert pd.isna(row["recovered_date"])

    def test_new_ath_ends_episode_and_no_retrigger_on_shallow_dip(self):
        closes = _flat((100, 5), (200, 1), (110, 1), (145, 1), (250, 3), (205, 3))
        out = ev.find_bottoms(_frame(closes), "cycle")
        assert len(out) == 1
        row = out.iloc[0]
        assert row["confirm_date"] == _day(7)  # 145 >= 110 * 1.30 = 143
        assert row["recovered_date"] == _day(8)  # 250 > 200 (new ATH)
        assert row["confirm_date"] < row["recovered_date"]
        # The -18% dip to 205 after the new ATH must not open a new episode.

    def test_drawdown_above_threshold_yields_no_cycle_event(self):
        closes = _flat((100, 3), (200, 1), (120, 5), (160, 3), (250, 3))
        out = ev.find_bottoms(_frame(closes), "cycle")
        assert len(out) == 0

    def test_confirmed_events_are_stable_under_truncation(self):
        """Honesty property: labels already confirmed never change as data grows."""
        rng = np.random.default_rng(42)
        chunks = [np.array([100.0])]
        level = 100.0
        for _ in range(4):  # rally to new highs, crash ~-55%, recover past the old peak
            for days, mu, sigma in ((100, 0.004, 0.03), (120, -0.007, 0.05), (200, 0.008, 0.03)):
                segment = np.cumprod(1.0 + rng.normal(mu, sigma, days)) * level
                chunks.append(segment)
                level = float(segment[-1])
        df = _frame(list(np.concatenate(chunks)))
        full = ev.find_bottoms(df, "cycle")
        full_confirmed = full[~full["provisional"].astype(bool)]
        assert len(full_confirmed) >= 2  # the walk must contain confirmed bottoms
        for t in range(50, len(df), 25):
            prefix = ev.find_bottoms(df.iloc[:t], "cycle")
            confirmed = prefix[~prefix["provisional"].astype(bool)]
            if len(confirmed) == 0:
                continue
            merged = confirmed.merge(
                full_confirmed, on=["horizon", "peak_date", "bottom_date"], how="left", suffixes=("", "_full")
            )
            assert merged["bottom_price_full"].notna().all(), f"prefix t={t} invented or lost events"
            # recovered_date is deliberately excluded: it can only appear as
            # data grows (a new ATH may arrive after the prefix was cut), so it
            # is not part of the confirmed-label stability guarantee.
            for col in ("peak_price", "bottom_price", "drawdown", "confirm_date", "days_to_confirm"):
                assert (merged[col] == merged[f"{col}_full"]).all(), f"prefix t={t} changed {col}"


# ---------------------------------------------------------------------------
# Swing horizon: synthetic shapes
# ---------------------------------------------------------------------------


class TestSwingShapes:
    def test_swing_v_single_event(self):
        closes = _flat((100, 5), (78, 3), (92, 1), (120, 5))
        out = ev.find_bottoms(_frame(closes), "swing")
        assert len(out) == 1
        row = out.iloc[0]
        assert row["horizon"] == "swing"
        assert row["peak_date"] == _day(0) and row["peak_price"] == 100.0  # 90d rolling-high anchor
        assert row["bottom_date"] == _day(5) and row["bottom_price"] == 78.0
        assert row["drawdown"] == pytest.approx(-0.22)
        assert row["confirm_date"] == _day(8)  # 92 >= 78 * 1.15 = 89.7
        assert row["days_to_confirm"] == 3
        assert row["recovered_date"] == _day(9)  # 120 > 100
        assert bool(row["provisional"]) is False

    def test_swing_events_nested_inside_cycle_event(self):
        closes = _flat((100, 4), (70, 2), (85, 2), (50, 3), (65, 1), (90, 4), (110, 2))
        df = _frame(closes)
        cyc = ev.find_bottoms(df, "cycle")
        sw = ev.find_bottoms(df, "swing")
        assert len(cyc) == 1
        assert cyc.iloc[0]["bottom_date"] == _day(8) and cyc.iloc[0]["bottom_price"] == 50.0
        assert cyc.iloc[0]["confirm_date"] == _day(11)  # 65 >= 50 * 1.30
        assert cyc.iloc[0]["recovered_date"] == _day(16)  # 110 > 100
        assert len(sw) == 2
        s1, s2 = sw.iloc[0], sw.iloc[1]
        assert s1["bottom_date"] == _day(4) and s1["bottom_price"] == 70.0
        assert s1["confirm_date"] == _day(6)  # 85 >= 70 * 1.15 = 80.5
        assert s2["bottom_date"] == _day(8) and s2["bottom_price"] == 50.0
        assert s2["confirm_date"] == _day(11)  # 65 >= 50 * 1.15 = 57.5
        # Swings deliberately overlap the cycle episode: independent state machines.
        assert s2["bottom_date"] == cyc.iloc[0]["bottom_date"]

    def test_swing_grind_without_rebound_stays_provisional(self):
        closes = _flat((100, 5), (80, 3), (84, 4), (87, 4))
        out = ev.find_bottoms(_frame(closes), "swing")
        assert len(out) == 1
        row = out.iloc[0]
        assert bool(row["provisional"]) is True
        assert row["bottom_date"] == _day(5) and row["bottom_price"] == 80.0
        assert pd.isna(row["confirm_date"])
        assert pd.isna(row["days_to_confirm"])
        assert pd.isna(row["recovered_date"])

    def test_swing_window_trailing_high_semantics(self):
        # A high older than the window drops out of the anchor.
        closes = _flat((100, 1), (96, 100), (76, 3), (90, 5))
        out = ev.find_bottoms(_frame(closes), "swing")
        assert len(out) == 1
        row = out.iloc[0]
        # At the trigger day (first 76) the 90d window holds only 96s.
        assert row["peak_price"] == 96.0
        assert row["drawdown"] == pytest.approx(76.0 / 96.0 - 1)
        assert row["confirm_date"] == _day(104)  # 90 >= 76 * 1.15 = 87.4

        # Same path but the 100 is still inside the window: anchored to 100.
        closes2 = _flat((100, 1), (96, 60), (76, 3), (90, 5))
        out2 = ev.find_bottoms(_frame(closes2), "swing")
        assert len(out2) == 1
        assert out2.iloc[0]["peak_price"] == 100.0

        # A 19.2% drawdown from the in-window high is not a swing trigger.
        closes3 = _flat((100, 1), (96, 15), (99, 80), (80, 3))
        out3 = ev.find_bottoms(_frame(closes3), "swing")
        assert len(out3) == 0

    def test_swing_confirm_rebound_boundary(self):
        # 91 is below 80 * 1.15 (~91.999...): stays unconfirmed to the end.
        no = ev.find_bottoms(_frame(_flat((100, 5), (80, 2), (91, 3))), "swing")
        assert len(no) == 1 and bool(no.iloc[0]["provisional"]) is True
        # 93 clears it: confirmed.
        yes = ev.find_bottoms(_frame(_flat((100, 5), (80, 2), (93, 1), (120, 3))), "swing")
        assert len(yes) == 1 and bool(yes.iloc[0]["provisional"]) is False
        assert yes.iloc[0]["confirm_date"] == _day(7)


# ---------------------------------------------------------------------------
# Input contract and output schema
# ---------------------------------------------------------------------------


class TestContract:
    def test_output_columns_and_dtypes(self):
        closes = _flat((100, 5), (200, 1), (100, 5), (135, 1), (250, 5))
        out = ev.find_bottoms(_frame(closes), "cycle")
        assert list(out.columns) == ev.EVENT_COLUMNS
        assert str(out["confirm_date"].dtype).startswith("datetime64")
        assert str(out["recovered_date"].dtype).startswith("datetime64")
        assert str(out["days_to_confirm"].dtype) == "Int64"
        assert out["provisional"].dtype == bool
        assert (out["horizon"] == "cycle").all()
        assert out["drawdown"].lt(0).all()
        # Rows sorted by bottom_date.
        assert out["bottom_date"].is_monotonic_increasing

    def test_intraday_low_column_optional(self):
        closes = _flat((100, 5), (200, 1), (100, 5), (135, 1), (250, 5))
        without = ev.find_bottoms(_frame(closes), "cycle")
        assert without.iloc[0]["bottom_intraday_low"] != without.iloc[0]["bottom_intraday_low"]

    def test_empty_input_returns_empty_frame_with_columns(self):
        out = ev.find_bottoms(_frame([]), "cycle")
        assert len(out) == 0 and list(out.columns) == ev.EVENT_COLUMNS

    def test_all_nan_closes_return_empty_frame(self):
        df = _frame([np.nan, np.nan, np.nan])
        assert len(ev.find_bottoms(df, "cycle")) == 0

    def test_nan_close_days_are_skipped(self):
        closes = _flat((100, 3), (200, 1), (150, 1), (140, 1), (105, 1), (140, 1), (250, 3))
        # NaN on the unique trigger/min day (the 105): the episode never opens.
        hole = _frame(closes)
        hole.iloc[6, hole.columns.get_loc("close")] = np.nan
        assert len(ev.find_bottoms(hole, "cycle")) == 0
        # NaN on an irrelevant mid-fall day (a 140): the label is unchanged.
        intact = _frame(closes)
        intact.iloc[5, intact.columns.get_loc("close")] = np.nan
        out = ev.find_bottoms(intact, "cycle")
        assert len(out) == 1
        assert out.iloc[0]["bottom_date"] == _day(6) and out.iloc[0]["bottom_price"] == 105.0
        assert out.iloc[0]["confirm_date"] == _day(7)  # 140 >= 105 * 1.30

    def test_input_frame_is_not_mutated(self):
        closes = _flat((100, 3), (200, 1), (100, 5), (135, 1), (250, 5))
        df = _frame(closes)
        before = df.copy(deep=True)
        ev.find_bottoms(df, "cycle")
        ev.find_bottoms(df, "swing")
        pd.testing.assert_frame_equal(df, before)

    def test_invalid_horizon_raises(self):
        with pytest.raises(ValueError, match="horizon"):
            ev.find_bottoms(_frame(_flat((100, 5))), "daily")

    def test_cross_horizon_params_rejected(self):
        df = _frame(_flat((100, 5)))
        with pytest.raises(ValueError, match="swing_window"):
            ev.find_bottoms(df, "cycle", swing_window=60)
        with pytest.raises(ValueError, match="cycle_dd"):
            ev.find_bottoms(df, "swing", cycle_dd=0.5)

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"cycle_dd": 0.0},
            {"cycle_dd": 1.0},
            {"cycle_confirm": 0.0},
            {"swing_dd": 0.0},
            {"swing_dd": 1.5},
            {"swing_confirm": -0.1},
            {"swing_window": 0},
            {"swing_window": 2.5},
        ],
    )
    def test_invalid_params_raise(self, kwargs):
        horizon = "cycle" if set(kwargs) & {"cycle_dd", "cycle_confirm"} else "swing"
        with pytest.raises(ValueError):
            ev.find_bottoms(_frame(_flat((100, 5))), horizon, **kwargs)

    def test_non_datetime_index_raises(self):
        df = pd.DataFrame({"close": [100.0, 90.0, 85.0, 99.0]})
        with pytest.raises(ValueError, match="DatetimeIndex"):
            ev.find_bottoms(df, "cycle")

    def test_missing_close_column_raises(self):
        df = pd.DataFrame({"price": [1.0, 2.0]}, index=pd.date_range("2020-01-01", periods=2, name="ts"))
        with pytest.raises(ValueError, match="close"):
            ev.find_bottoms(df, "cycle")

    def test_reproducible(self):
        rng = np.random.default_rng(7)
        closes = 100.0 * np.cumprod(1.0 + rng.normal(0.0, 0.04, 400))
        df = _frame(list(closes))
        a = ev.find_bottoms(df, "cycle")
        b = ev.find_bottoms(df, "cycle")
        pd.testing.assert_frame_equal(a, b)


# ---------------------------------------------------------------------------
# Parameter sweeps: label sets and stability
# ---------------------------------------------------------------------------


class TestGridAndStability:
    def test_grid_labels_long_form(self):
        # Two separate ATH eras: era 1 dips -42% (qualifies only at dd<=0.40),
        # era 2 dips -52% (qualifies throughout).
        closes = _flat(
            (100, 3),
            (200, 1),
            (116, 2),
            (250, 3),  # era 1: new ATH closes it
            (120, 2),
            (300, 3),  # era 2
        )
        df = _frame(closes)
        grid = {"cycle_dd": [0.40, 0.45, 0.50]}
        out = ev.grid_labels(df, "cycle", grid=grid)
        assert list(out["cycle_dd"].unique()) == [0.40, 0.45, 0.50]
        counts = out.groupby("cycle_dd").size()
        assert counts.loc[0.40] == 2  # the -42% era qualifies too
        assert counts.loc[0.45] == 1
        assert counts.loc[0.50] == 1  # only the -52% era qualifies
        assert set(ev.EVENT_COLUMNS).issubset(out.columns)

    def test_stability_summary_counts(self):
        closes = _flat(
            (100, 3),
            (200, 1),
            (116, 2),
            (250, 3),
            (120, 2),
            (300, 3),
        )
        df = _frame(closes)
        summary = ev.stability_summary(df, "cycle", grid={"cycle_dd": [0.45, 0.40, 0.50]})
        assert len(summary) == 3
        base = summary[summary["cycle_dd"] == 0.45].iloc[0]
        assert base["matched"] == 1 and base["appeared"] == 0 and base["disappeared"] == 0
        looser = summary[summary["cycle_dd"] == 0.40].iloc[0]
        assert looser["matched"] == 1 and looser["appeared"] == 1 and looser["disappeared"] == 0
        tighter = summary[summary["cycle_dd"] == 0.50].iloc[0]
        assert tighter["matched"] == 1 and tighter["disappeared"] == 0 and tighter["appeared"] == 0

    def test_cycle_bottom_is_invariant_to_trigger_threshold(self):
        # Documented property: the cycle bottom is the span minimum, so moving
        # cycle_dd cannot shift bottom dates -- it only decides whether an era
        # qualifies at all.
        rng = np.random.default_rng(3)
        closes = 100.0 * np.cumprod(1.0 + rng.normal(-0.002, 0.05, 600))
        closes = np.append(closes, [closes[-1] * 3])  # force a new ATH to close the era
        df = _frame(list(closes))
        bottoms = [ev.find_bottoms(df, "cycle", cycle_dd=dd)["bottom_date"].tolist() for dd in (0.35, 0.45, 0.55)]
        assert bottoms[0] == bottoms[1] == bottoms[2]

    def test_stability_summary_counts_shifted_bottoms(self):
        # Swing episodes end at the rebound, so a threshold change can merge
        # two swings into one whose bottom sits on the later, deeper low.
        closes = _flat((200, 3), (134, 1), (180, 1), (129, 1), (168, 2))
        df = _frame(closes)
        summary = ev.stability_summary(df, "swing", grid={"swing_dd": [0.35]}, baseline={"swing_dd": 0.30})
        row = summary.iloc[0]
        assert row["n_baseline"] == 2 and row["n_combo"] == 1
        assert row["matched"] == 1
        assert row["shifted"] == 1
        assert row["max_shift_days"] == 2  # day 3 (134) vs day 5 (129)
        assert row["appeared"] == 0 and row["disappeared"] == 1

    def test_default_grid_central_combo_matches_find_bottoms(self):
        closes = _flat((100, 3), (200, 1), (110, 4), (150, 1), (95, 4), (160, 2), (250, 5))
        df = _frame(closes)
        out = ev.grid_labels(df, "cycle", grid=None)
        # Default cycle grid = dd x confirm, includes the central defaults.
        central = out[(out["cycle_dd"] == 0.45) & (out["cycle_confirm"] == 0.30)]
        direct = ev.find_bottoms(df, "cycle")
        cols = ev.EVENT_COLUMNS
        pd.testing.assert_frame_equal(
            central[cols].reset_index(drop=True), direct[cols].reset_index(drop=True), check_dtype=False
        )


# ---------------------------------------------------------------------------
# Real-data sanity (runs only where the local BTC cache exists; read-only)
# ---------------------------------------------------------------------------

_REAL_CSV = Path(__file__).resolve().parents[1] / "data" / "cache" / "btc" / "daily.csv"


@pytest.mark.skipif(not _REAL_CSV.exists(), reason="local BTC daily cache not present")
class TestRealDataSanity:
    @pytest.fixture()
    def btc(self) -> pd.DataFrame:
        df = pd.read_csv(_REAL_CSV, parse_dates=["ts"]).set_index("ts")
        df = df[["open", "high", "low", "close", "volume"]].sort_index()
        assert df.index.min() >= pd.Timestamp("2014-09-17")
        return df

    def test_cycle_events_include_known_lows(self, btc: pd.DataFrame):
        out = ev.find_bottoms(btc, "cycle")
        assert len(out) >= 3  # tiny sample: report counts, no p-values
        for window_start, window_end in [
            ("2018-11-01", "2019-01-31"),
            ("2022-10-01", "2022-12-31"),
            ("2026-05-01", "2026-08-31"),
        ]:
            win = btc.loc[window_start:window_end, "close"]
            true_bottom = win.idxmin()
            hit = out[(out["bottom_date"] >= window_start) & (out["bottom_date"] <= window_end)]
            assert len(hit) == 1, (
                f"expected exactly one cycle bottom in {window_start}..{window_end}, got {hit.to_dict('records')}"
            )
            assert hit.iloc[0]["bottom_date"] == true_bottom
            assert hit.iloc[0]["bottom_price"] == pytest.approx(win.min())

    def test_swing_events_are_sparse_and_sorted(self, btc: pd.DataFrame):
        out = ev.find_bottoms(btc, "swing")
        assert 5 <= len(out) <= 80  # weeks-scale lows: dozens, not hundreds
        assert out["bottom_date"].is_monotonic_increasing
        assert out["drawdown"].lt(-0.19).all()  # every event clears its trigger threshold
        assert out["confirm_date"].notna().mean() > 0.8  # most swings confirmed within the data
