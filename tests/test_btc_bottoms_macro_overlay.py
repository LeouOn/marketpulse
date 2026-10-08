"""Offline tests for the Q2 macro overlay (BTC bottom study, wave 2b, g1).

Synthetic data only: no network, no cache files, no keys. The conditions'
causality (prefix-invariance), NaN honesty, the descriptive comparator and
the combination plumbing are pinned on hand-computable toy worlds.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.research.btc_bottoms.macro_overlay import (
    COMBINATIONS,
    M_EXTRA_THRESHOLDS,
    descriptive,
    macro_conditions,
    prepare_macro_frame,
)

CAL = pd.date_range("2025-06-01", "2026-03-31", freq="D", name="ts")


def _toy_asof_frame() -> pd.DataFrame:
    n = len(CAL)
    rng = np.random.default_rng(7)
    df = pd.DataFrame(index=CAL)
    df["close"] = np.linspace(70_000.0, 50_000.0, n)  # steady decline -> deep dd later
    # dfii10: rising then falling -> M1 false then true
    df["dfii10"] = np.concatenate([np.linspace(1.0, 2.0, n // 2), np.linspace(2.0, 1.0, n - n // 2)])
    # dxy_ice: falling then rising -> M2 true then false
    df["dxy_ice"] = np.concatenate([np.linspace(110.0, 100.0, n // 2), np.linspace(100.0, 110.0, n - n // 2)])
    # vix: calm at 15 with a spike to 40 in the middle -> M3a false during spike
    vix = np.full(n, 15.0)
    vix[n // 2 - 3 : n // 2 + 3] = 40.0
    df["vix"] = vix
    # baa10y: constant -> M3b NaN-safe zero change... make it strictly falling
    df["baa10y"] = np.linspace(3.0, 2.0, n)
    # net liquidity: falling then rising -> M4 false then true
    nl = np.concatenate([np.linspace(6_000.0, 5_000.0, n // 2), np.linspace(5_000.0, 6_500.0, n - n // 2)])
    df["net_liquidity"] = nl
    # mvrv_z: negative first half, crosses (0.5, 1.0) early in the second half -> M5 variants distinguishable
    df["mvrv_z"] = np.concatenate([np.linspace(-2.0, -0.5, n // 2), np.linspace(0.6, 3.0, n - n // 2)])
    df["walcl"] = 6_000.0 + rng.random(n)
    df["wtregen"] = 500.0 + rng.random(n)
    df["rrp_onday"] = 0.5 + rng.random(n)
    return df


@pytest.fixture()
def toy():
    return _toy_asof_frame()


class TestMacroConditions:
    def test_m1_real_yield_easing_diff21_below_zero(self, toy):
        conds = macro_conditions(toy)
        expected_chg = toy["dfii10"].diff(21)
        # a late frame day in the falling half
        d = CAL[-10]
        assert conds.loc[d, "m1"] == float(expected_chg.loc[d] < 0)
        early = CAL[5]
        assert np.isnan(conds.loc[early, "m1"])  # warm-up: diff(21) NaN

    def test_m2_dollar_easing_pct_change_below_zero(self, toy):
        conds = macro_conditions(toy)
        expected = toy["dxy_ice"].pct_change(21) < 0
        d = CAL[40]
        assert conds.loc[d, "m2"] == float(expected.loc[d])

    def test_m3a_vix_fade_vs_trailing_max(self, toy):
        conds = macro_conditions(toy)
        roll_max = toy["vix"].rolling(21).max()
        d_spike = CAL[len(CAL) // 2]  # during the 40 spike
        d_faded = CAL[len(CAL) // 2 + 10]  # calm again, spike still inside the window
        d_flat = CAL[-5]  # calm, spike long gone: a flat-calm world has NO fade
        assert conds.loc[d_spike, "m3a"] == float(toy["vix"].loc[d_spike] <= 0.8 * roll_max.loc[d_spike])
        assert conds.loc[d_faded, "m3a"] == 1.0  # 15 <= 0.8 * 40
        assert conds.loc[d_flat, "m3a"] == 0.0  # 15 <= 0.8 * 15 is false

    def test_m3b_credit_easing(self, toy):
        conds = macro_conditions(toy)
        assert conds.loc[CAL[-1], "m3b"] == 1.0  # strictly falling series

    def test_m4_liquidity_up_63d(self, toy):
        conds = macro_conditions(toy)
        d = CAL[-1]
        assert conds.loc[d, "m4"] == float(toy["net_liquidity"].diff(63).loc[d] > 0)

    def test_m5_valuation_low_and_extras(self, toy):
        conds = macro_conditions(toy)
        d = CAL[10]
        assert conds.loc[d, "m5"] == 1.0  # mvrv_z ~ -2
        for thr in M_EXTRA_THRESHOLDS:
            col = f"m5_lt_{thr}"
            assert col in conds.columns
            assert conds.loc[d, col] == float(toy["mvrv_z"].loc[d] < thr)
        d2 = CAL[len(CAL) // 2]  # mvrv_z = 0.6: m5 false, m5_lt_0.5 false, m5_lt_1.0 true
        assert conds.loc[d2, "m5"] == 0.0
        assert conds.loc[d2, "m5_lt_0.5"] == 0.0
        assert conds.loc[d2, "m5_lt_1.0"] == 1.0

    def test_nan_input_never_false(self, toy):
        holed = toy.copy()
        holed.loc[CAL[100:130], "vix"] = np.nan  # 31-day hole > asof limit
        conds = macro_conditions(holed)
        # rolling(21).max() NaN through the hole and 20 days after
        assert conds.loc[CAL[110], "m3a"] is np.nan or np.isnan(conds.loc[CAL[110], "m3a"])
        # a NaN diff endpoint stays NaN
        holed2 = toy.copy()
        holed2.loc[CAL[-1], "dfii10"] = np.nan
        conds2 = macro_conditions(holed2)
        assert np.isnan(conds2.loc[CAL[-1], "m1"])

    @pytest.mark.parametrize("col", ["m1", "m2", "m3a", "m3b", "m4", "m5", "m5_lt_0.5", "m5_lt_1.0"])
    def test_prefix_invariance_every_condition(self, toy, col):
        full = macro_conditions(toy)
        t = CAL[len(CAL) // 2]
        prefix = macro_conditions(toy.loc[:t])
        pd.testing.assert_series_equal(prefix[col], full[col].loc[:t], check_names=False)

    @pytest.mark.parametrize("col", ["m1", "m2", "m3a", "m3b", "m4", "m5"])
    def test_future_poisoning_leaves_past_unchanged(self, toy, col):
        base = macro_conditions(toy)
        t = CAL[len(CAL) // 2]
        poisoned = toy.copy()
        poisoned.loc[t:, "dfii10"] = 9.0
        poisoned.loc[t:, "dxy_ice"] = 200.0
        poisoned.loc[t:, "vix"] = 80.0
        poisoned.loc[t:, "baa10y"] = 9.0
        poisoned.loc[t:, "net_liquidity"] = 1.0
        poisoned.loc[t:, "mvrv_z"] = 9.0
        changed = macro_conditions(poisoned)
        pd.testing.assert_series_equal(
            base[col].loc[: t - pd.Timedelta(days=1)], changed[col].loc[: t - pd.Timedelta(days=1)], check_names=False
        )


class TestPrepareMacroFrame:
    def test_net_liquidity_recomputed_from_filled_columns(self):
        frame = pd.DataFrame(index=CAL)
        frame["close"] = 60_000.0
        # In the real frame walcl/wtregen are weekly series ALREADY forward-filled
        # (with _age) before asof; the daily RRP column is the one carrying holes.
        frame["walcl"] = 6_000.0
        frame["wtregen"] = 500.0
        rrp = pd.Series(0.5, index=CAL)
        rrp.loc[CAL[7::7]] = np.nan  # weekly holes in a daily FRED column
        frame["rrp_onday"] = rrp
        af = prepare_macro_frame(frame)
        # after asof(5) the holes are filled; net_liquidity uses filled inputs
        assert af["net_liquidity"].notna().all()
        expected = af["walcl"] - af["wtregen"] - 1_000.0 * af["rrp_onday"]
        pd.testing.assert_series_equal(af["net_liquidity"], expected, check_names=False)


class TestDescriptive:
    def _world(self):
        toy = _toy_asof_frame()
        n = len(CAL)
        # force deep drawdown everywhere late in the frame
        toy.loc[:, "close"] = np.where(np.arange(n) < n // 3, 100_000.0, 40_000.0)
        events = pd.DataFrame(
            {
                "horizon": ["cycle", "cycle", "swing"],
                "bottom_date": [CAL[n // 2], CAL[n // 2 + 40], CAL[n // 3 + 10]],
                "confirm_date": [CAL[n // 2 + 20], CAL[n // 2 + 60], CAL[n // 3 + 15]],
                "provisional": [False, False, False],
            }
        )
        return toy, events

    def test_window_share_counts_k_of_n(self):
        toy, events = self._world()
        conds = macro_conditions(toy)
        tables = descriptive(toy, conds, events)
        row = tables["per_event"]
        b = CAL[len(CAL) // 2]
        win = pd.date_range(b - pd.Timedelta(days=60), b, freq="D")
        expected_k = int(conds.loc[win, "m3b"].sum())  # strictly falling -> all true where non-NaN
        got = row[(row["bottom_date"] == b) & (row["condition"] == "m3b")].iloc[0]
        assert got["k"] == expected_k
        assert got["n"] == int(conds.loc[win, "m3b"].notna().sum())

    def test_comparator_excludes_event_windows(self):
        toy, events = self._world()
        conds = macro_conditions(toy)
        tables = descriptive(toy, conds, events)
        comp = tables["comparator"]
        dd = toy["close"] / toy["close"].cummax() - 1.0
        deep = dd <= -0.40
        windows = []
        for b in events["bottom_date"]:
            windows.append(pd.date_range(b - pd.Timedelta(days=60), b, freq="D"))
        excluded = pd.DatetimeIndex([]).append(windows)
        expected_days = deep & ~toy.index.isin(excluded)
        m3b_row = comp[comp["condition"] == "m3b"].iloc[0]
        assert m3b_row["n"] == int((expected_days & conds["m3b"].notna()).sum())

    def test_majority_count_over_a_events(self):
        toy, events = self._world()
        conds = macro_conditions(toy)
        tables = descriptive(toy, conds, events)
        maj = tables["majority_A"]
        # m3b is strictly falling -> every window all-true -> majority in all A events (2 here)
        assert maj.loc[maj["condition"] == "m3b", "n_events_majority"].iloc[0] == 2


class TestCombinations:
    def test_declared_combinations_exact(self):
        assert COMBINATIONS == {
            "C1": ("fgi_extreme_streak", "m3a"),
            "C2": ("dd_ath", "m1"),
            "C3": ("mayer_multiple", "m4"),
            "C4": ("washout_stabilise", "m3b"),
            "C5": ("dd_ath", "m5"),
            "C6": ("capitulation_vol", "m2"),
        }

    def test_and_semantics_nan_never_false(self):
        from src.research.btc_bottoms.macro_overlay import _and_boolean

        s1 = pd.Series([True, True, False, None], dtype="boolean")
        s2 = pd.Series([True, None, True, True], dtype="boolean")
        out = _and_boolean(s1, s2)
        assert out.tolist() == [True, pd.NA, False, pd.NA]

    def test_funding_2026_view_is_descriptive_only(self):
        from src.research.btc_bottoms.macro_overlay import funding_2026_view

        toy = _toy_asof_frame()
        toy["funding_rate"] = 1e-4
        out = funding_2026_view(toy, low=CAL[100], last=CAL[-1])
        # low-to-last mean over available days, counts reported
        assert out["n_days"] > 0
        assert out["mean_daily"] == pytest.approx(1e-4)


class TestEpisodeView:
    def _world(self):
        idx = pd.date_range("2025-10-01", "2026-09-30", freq="D", name="ts")
        fire = pd.Series(False, index=idx, dtype="boolean")
        fire.loc[pd.Timestamp("2026-06-27") : pd.Timestamp("2026-06-30")] = True  # 4 days, 3 before the low
        close = pd.Series(np.linspace(120_000.0, 90_000.0, len(idx)), index=idx)
        close.loc[pd.Timestamp("2026-06-30")] = 58_559.0
        return fire, close

    def test_fires_and_offsets(self):
        from src.research.btc_bottoms.macro_overlay import episode_view

        fire, close = self._world()
        out = episode_view(
            fire,
            close,
            peak=pd.Timestamp("2025-10-06"),
            low=pd.Timestamp("2026-06-30"),
            confirm=pd.Timestamp("2026-08-21"),
        )
        assert out["fire_days"] == 4
        assert out["first_fire"] == pd.Timestamp("2026-06-27")
        assert out["days_before_low"] == 3
        assert out["days_before_confirm"] == 55
        assert out["close_at_first_fire"] == close.loc[pd.Timestamp("2026-06-27")]
        assert out["ret_first_fire_to_last"] == close.iloc[-1] / close.loc[pd.Timestamp("2026-06-27")] - 1.0

    def test_zero_fires_reports_absence_not_error(self):
        from src.research.btc_bottoms.macro_overlay import episode_view

        fire, close = self._world()
        out = episode_view(
            pd.Series(False, index=fire.index, dtype="boolean"),
            close,
            peak=pd.Timestamp("2025-10-06"),
            low=pd.Timestamp("2026-06-30"),
            confirm=pd.Timestamp("2026-08-21"),
        )
        assert out["fire_days"] == 0 and out["first_fire"] is None and out["ret_first_fire_to_last"] is None


class TestDiagnosticsColumns:
    def test_fire_day_share_and_episodes_per_year_present(self):
        # structural: the evaluated rows carry the two new diagnostic columns
        from pathlib import Path

        import src.research.btc_bottoms.macro_overlay as mo

        src = Path(mo.__file__).read_text()
        assert '"fire_day_share"' in src and '"episodes_per_year"' in src


class TestCombinationRobustnessSweep:
    def test_cells_counted_and_lifts_reported(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MARKETPULSE_DATA_DIR", str(tmp_path))
        from src.research.btc_bottoms import macro_overlay as mo

        toy = _toy_asof_frame()
        conds = macro_conditions(toy)
        events = pd.DataFrame(
            {
                "horizon": ["cycle", "cycle"],
                "bottom_date": [CAL[120], CAL[180]],
                "confirm_date": [CAL[130], CAL[190]],
                "provisional": [False, False],
            }
        )
        out = mo.combination_robustness_sweep(toy, conds["m3b"], "mayer_multiple", events)
        assert out["n_cells"] > 1
        assert out["n_never_firing"] >= 0
        assert out["n_cells"] >= 1
        # the sweep must have tried the registry grid (mayer has a threshold grid)
        from src.research.btc_bottoms.signals import SIGNAL_REGISTRY

        grid = SIGNAL_REGISTRY["mayer_multiple"][2]
        expected_cells = 1
        for k in grid:
            expected_cells *= len(grid[k])
        assert out["n_cells"] == expected_cells
