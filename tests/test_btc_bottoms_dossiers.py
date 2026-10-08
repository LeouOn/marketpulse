"""Q3 case files: dossiers and the current reading (wave 2b, g3).

``src.research.btc_bottoms.dossiers`` builds the plan-section-5 tables: per
cycle event a snapshot across eight stages (peak, bottom-90/60/30/7, bottom,
confirm, last) with close, drawdown, the 19 registry signal readings and fire
flags, macro conditions M1-M5 and valuation/liquidity context; the
false-confirmation timeline per event; and the current reading at the last
frame row. These tests are offline and synthetic (no cache, no network).

Standing limits carried by the module (plan section 7): hindsight labels;
``confirm_date`` is optimistic (a +30% bounce occurred before the final low in
2018, 2022 and 2026); the 2026 low is provisional and can still move; MVRV-Z
amplitude has decayed across cycles; revised macro series are excluded; Coin
Metrics restates its latest days; BTC prices come from Yahoo.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.research.btc_bottoms import dossiers as dos
from src.research.btc_bottoms import events as ev
from src.research.btc_bottoms.frame import build_frame

_REAL_CACHE = Path(os.environ.get("MARKETPULSE_DATA_DIR") or "data/cache") / "btc_bottoms" / "frame.parquet"


# ---------------------------------------------------------------------------
# Synthetic frames
# ---------------------------------------------------------------------------


def _synth(n: int = 400, start: str = "2020-01-01") -> pd.DataFrame:
    """A deterministic frame with every column dossiers touches.

    Price path: 100 -> 220 peak -> 100 bottom (-55%) -> 300 new ATH, plus flat
    macro columns arranged so each condition is testable by mutation.
    """
    idx = pd.date_range(start, periods=n, freq="D", name="ts")
    peak_i, bottom_i = max(2, n // 5), max(4, n // 2)
    closes = np.full(n, 150.0)
    closes[:peak_i] = np.linspace(100, 220, peak_i)
    closes[peak_i:bottom_i] = np.linspace(220, 100, bottom_i - peak_i)
    closes[bottom_i:] = np.linspace(100, 300, n - bottom_i)
    df = pd.DataFrame(
        {
            "open": closes,
            "high": closes * 1.01,
            "low": closes * 0.99,
            "close": closes,
            "volume": np.full(n, 1e4),
            "fgi_value": np.full(n, 50.0),
            "dfii10": np.linspace(3.0, 2.0, n),  # 21d diff < 0 -> M1 True
            "dxy_ice": np.linspace(100.0, 110.0, n),  # 21d pct chg > 0 -> M2 False
            "vix": np.full(n, 20.0),  # vix == rolling max -> M3a False (20 > 16)
            "baa10y": np.linspace(3.0, 2.5, n),  # 21d diff < 0 -> M3b True
            "mvrv_z": np.full(n, 0.5),  # not < 0 -> M5 False
            "walcl": np.linspace(8_000_000, 8_100_000, n),
            "wtregen": np.full(n, 800_000.0),
            "rrp_onday": np.full(n, 300.0),
        },
        index=idx,
    )
    return df


def _prepared(n: int = 400) -> pd.DataFrame:
    """A synthetic frame run through g1's prepare (asof + net_liquidity)."""
    from src.research.btc_bottoms import macro_overlay

    return macro_overlay.prepare_macro_frame(_synth(n))


class TestMacroConditions:
    def test_definitions_on_flat_synthetic_frame(self):
        from src.research.btc_bottoms import macro_overlay

        m = dos.macro_conditions(macro_overlay.prepare_macro_frame(_synth()))
        assert list(m.columns) == [
            "M1_real_yield_easing",
            "M2_dollar_easing",
            "M3a_vix_fade",
            "M3b_credit_easing",
            "M4_liquidity_up",
            "M5_valuation_low",
        ]
        tail = m.iloc[-1]
        assert bool(tail["M1_real_yield_easing"]) is True  # dfii10 falling
        assert bool(tail["M2_dollar_easing"]) is False  # dxy rising
        assert bool(tail["M3a_vix_fade"]) is False  # vix flat at its max
        assert bool(tail["M3b_credit_easing"]) is True  # baa10y falling
        assert bool(tail["M4_liquidity_up"]) is True  # walcl rising
        assert bool(tail["M5_valuation_low"]) is False  # mvrv_z = 0.5

    def test_m3a_fires_when_vix_fades_off_its_21d_max(self):
        df = _synth()
        vix = np.full(len(df), 20.0)
        vix[100:121] = 30.0  # spike
        vix[121:] = 22.0  # fade to 0.733x of the spike
        df["vix"] = vix
        from src.research.btc_bottoms import macro_overlay

        m = dos.macro_conditions(macro_overlay.prepare_macro_frame(df))
        # At day 125 the 21-day window still holds the 30-spike: 22 <= 24.
        assert bool(m["M3a_vix_fade"].iloc[125]) is True
        # During the spike the vix sits at its own maximum: no fade.
        assert bool(m["M3a_vix_fade"].iloc[110]) is False
        # Long after the spike the window only sees 22s: 22 > 17.6, no fade.
        assert bool(m["M3a_vix_fade"].iloc[-1]) is False

    def test_nan_inputs_stay_na_not_false(self):
        df = _synth()
        # Gaps longer than the 5-day asof bridge stay NaN through prepare.
        df.loc[df.index[-6] :, "dfii10"] = np.nan
        df.loc[df.index[-6] :, "vix"] = np.nan
        from src.research.btc_bottoms import macro_overlay

        prepared = macro_overlay.prepare_macro_frame(df)
        m = dos.macro_conditions(prepared)
        assert pd.isna(m["M1_real_yield_easing"].iloc[-1])
        assert pd.isna(m["M3a_vix_fade"].iloc[-1])

    def test_net_liquidity_recomputed_by_prepare(self):
        from src.research.btc_bottoms import macro_overlay

        df = _synth()
        # Sunday-style gap in rrp_onday (an asof column): prepare bridges it
        # and net_liquidity is rebuilt from the filled components. A gap in a
        # weekly, non-asof component (walcl) honestly stays NaN.
        df.loc[df.index[-2], "rrp_onday"] = np.nan
        df.loc[df.index[-3], "walcl"] = np.nan
        prepared = macro_overlay.prepare_macro_frame(df)
        assert not pd.isna(prepared["net_liquidity"].iloc[-2])
        assert pd.isna(prepared["net_liquidity"].iloc[-3])
        m = dos.macro_conditions(prepared)
        assert bool(m["M4_liquidity_up"].iloc[-1]) is True

    def test_conditions_delegate_to_g1_exactly(self):
        """Single source of truth: values AND NaN pattern equal g1's module."""
        from src.research.btc_bottoms import macro_overlay

        prepared = macro_overlay.prepare_macro_frame(_synth())
        mine = dos.macro_conditions(prepared)
        theirs = macro_overlay.macro_conditions(prepared)
        for mine_col, g1_col in dos.MACRO_TO_G1.items():
            mine_f = mine[mine_col].astype("float")  # True->1.0, NA->NaN
            assert mine_f.equals(theirs[g1_col]), f"{mine_col} drifted from {g1_col}"

    def test_warmup_rows_are_na_not_false(self):
        """Plan rule: NaN is never False-by-default; warm-up rows are NA."""
        from src.research.btc_bottoms import macro_overlay

        prepared = macro_overlay.prepare_macro_frame(_synth())
        m = dos.macro_conditions(prepared)
        # diff(21) conditions need 21 prior rows: NA for the first 21 rows.
        for col in ("M1_real_yield_easing", "M3b_credit_easing"):
            assert m[col].iloc[:21].isna().all(), f"{col} must be NA during warm-up"
            assert m[col].iloc[21:].notna().all(), f"{col} should be defined after warm-up"
        # rolling(21) reaches a full window one row earlier.
        assert m["M3a_vix_fade"].iloc[:20].isna().all()
        assert m["M3a_vix_fade"].iloc[20:].notna().all()
        # M4 needs a 63-day change; M5 needs no window at all.
        assert m["M4_liquidity_up"].iloc[:63].isna().all()
        assert m["M5_valuation_low"].notna().all()


class TestFalseConfirmTimeline:
    def test_w_shape_yields_one_dated_false_confirm(self):
        closes = [100.0] * 3 + [200.0] + [110.0] * 4 + [160.0] * 2 + [95.0] * 4 + [160.0] * 2 + [250.0] * 5
        idx = pd.date_range("2020-01-01", periods=len(closes), freq="D", name="ts")
        df = pd.DataFrame({"close": closes}, index=idx)
        events = ev.find_bottoms(df, "cycle")
        assert events.iloc[0]["false_confirms"] == 1
        tl = dos.false_confirm_timeline(df, events.iloc[0])
        assert len(tl) == 1
        row = tl.iloc[0]
        assert row["low_date"] == idx[4] and row["low_close"] == 110.0
        assert row["confirm_date"] == idx[8] and row["confirm_close"] == 160.0
        assert row["broken_date"] == idx[10] and row["broken_close"] == 95.0

    def test_double_failed_bounce_yields_two(self):
        closes = (
            [100.0] * 3
            + [200.0]
            + [108.0] * 2
            + [145.0] * 2
            + [102.0] * 2
            + [140.0] * 2
            + [95.0] * 2
            + [130.0] * 2
            + [250.0] * 3
        )
        idx = pd.date_range("2020-01-01", periods=len(closes), freq="D", name="ts")
        df = pd.DataFrame({"close": closes}, index=idx)
        events = ev.find_bottoms(df, "cycle")
        assert events.iloc[0]["false_confirms"] == 2
        tl = dos.false_confirm_timeline(df, events.iloc[0])
        assert len(tl) == 2
        assert tl.iloc[0]["low_close"] == 108.0 and tl.iloc[0]["broken_close"] == 102.0
        assert tl.iloc[1]["low_close"] == 102.0 and tl.iloc[1]["broken_close"] == 95.0
        # The count always agrees with the events module's own counter.
        assert len(tl) == int(events.iloc[0]["false_confirms"])

    def test_clean_v_has_no_false_confirms(self):
        closes = [100.0] * 5 + [200.0] + [100.0] * 5 + [135.0] + [250.0] * 5
        idx = pd.date_range("2020-01-01", periods=len(closes), freq="D", name="ts")
        df = pd.DataFrame({"close": closes}, index=idx)
        events = ev.find_bottoms(df, "cycle")
        tl = dos.false_confirm_timeline(df, events.iloc[0])
        assert len(tl) == 0


class TestDossier:
    def test_snapshot_stages_and_dates_on_synthetic_path(self):
        df = _prepared()
        events = ev.find_bottoms(df, "cycle")
        assert len(events) == 1
        d = dos.dossier(df, events, 0)
        assert list(d.index) == dos.SNAPSHOT_STAGES
        bottom = events.iloc[0]["bottom_date"]
        peak = events.iloc[0]["peak_date"]
        confirm = events.iloc[0]["confirm_date"]
        assert d.loc["peak", "date"] == peak
        assert d.loc["bottom", "date"] == bottom
        assert d.loc["confirm", "date"] == confirm
        assert d.loc["last", "date"] == df.index[-1]
        # bottom-N stages snap causally: last row on or before bottom - N days.
        assert d.loc["bottom-30", "date"] == df.index[df.index <= bottom - pd.Timedelta(days=30)][-1]
        assert d.loc["bottom-90", "date"] == df.index[df.index <= bottom - pd.Timedelta(days=90)][-1]
        # Drawdown at the bottom equals the event's own drawdown.
        assert d.loc["bottom", "dd_ath"] == pytest.approx(events.iloc[0]["drawdown"])
        # Signals and fires present for all 19 registry names.
        for name in dos.SIGNAL_NAMES:
            assert name in d.columns
            assert f"{name}_fire" in d.columns

    def test_stage_before_frame_start_is_all_nan(self):
        # Dedicated path: peak on day 0, bottom ~day 40 -> bottom-90/-60
        # predate the data and must render as all-NaN stages.
        n = 61
        fall = np.linspace(220.0, 99.0, 41)
        rise = np.linspace(99.0, 200.0, n - 41)
        closes = np.concatenate([fall, rise])
        df = _prepared(n=n)
        df["close"] = closes
        events = ev.find_bottoms(df, "cycle")
        assert len(events) == 1
        d = dos.dossier(df, events, 0)
        assert pd.isna(d.loc["bottom-90", "close"])
        assert pd.isna(d.loc["bottom-90", "date"])
        assert pd.isna(d.loc["bottom-60", "close"])
        assert not pd.isna(d.loc["bottom-30", "close"])
        assert d.loc["bottom", "date"] == events.iloc[0]["bottom_date"]

    def test_macro_columns_in_table(self):
        df = _prepared()
        events = ev.find_bottoms(df, "cycle")
        d = dos.dossier(df, events, 0)
        for col in dos.MACRO_COLUMNS:
            assert col in d.columns
        for col in ("mvrv_z", "fgi_value", "real_yield", "baa10y", "net_liquidity"):
            assert col in d.columns

    def test_nan_signal_stays_nan(self):
        df = _prepared()
        df.loc[:, "fgi_value"] = np.nan  # FGI missing entirely
        events = ev.find_bottoms(df, "cycle")
        d = dos.dossier(df, events, 0)
        assert pd.isna(d.loc["bottom", "fgi"])
        assert pd.isna(d.loc["bottom", "fgi_fire"])

    def test_deterministic(self):
        df = _prepared(n=500)
        events = ev.find_bottoms(df, "cycle")
        a = dos.dossier(df, events, 0)
        b = dos.dossier(df, events, 0)
        pd.testing.assert_frame_equal(a, b)


class TestCurrentReading:
    def test_counts_and_days_on_synthetic(self):
        df = _prepared()
        reading = dos.current_reading(df)
        assert reading["as_of"] == df.index[-1]
        sig = reading["signals"]
        assert set(sig.index) == set(dos.SIGNAL_NAMES)
        # dd_ath fires at the end: drawdown from the 300 ATH... the final leg
        # rises to 300 so dd_ath == 0 and dd_ath_fire is False; rsi/fire etc.
        # depend on the path -- assert structural contract instead of values.
        assert set(sig.columns) >= {"on", "days_on"}
        macro = reading["macro"]
        assert set(macro.index) == set(dos.MACRO_COLUMNS)
        assert reading["counts"]["signals_on"] == int(sig["on"].fillna(False).sum())
        assert reading["counts"]["macro_on"] == int(macro["on"].fillna(False).sum())
        assert reading["counts"]["signals_total"] == 19
        assert reading["counts"]["macro_total"] == 6

    def test_days_on_counts_trailing_run(self):
        df = _prepared()
        # Make M5 true only for the last 10 rows.
        df.loc[df.index[-10] :, "mvrv_z"] = -0.5
        reading = dos.current_reading(df)
        assert bool(reading["macro"].loc["M5_valuation_low", "on"]) is True
        assert reading["macro"].loc["M5_valuation_low", "days_on"] == 10

    def test_not_on_gives_zero_days(self):
        df = _prepared()
        reading = dos.current_reading(df)
        m2 = reading["macro"].loc["M2_dollar_easing"]
        assert bool(m2["on"]) is False and m2["days_on"] == 0

    def test_deterministic(self):
        df = _prepared(n=450)
        a = dos.current_reading(df)
        b = dos.current_reading(df)
        pd.testing.assert_frame_equal(a["signals"], b["signals"])
        pd.testing.assert_frame_equal(a["macro"], b["macro"])


class TestFirstFireAfter:
    def test_first_fire_after_a_date(self):
        df = _synth()
        df.loc[df.index[-20] :, "fgi_value"] = 10.0  # fgi_fire only in the tail
        ff = dos.first_fire_after(df, df.index[-30])
        assert ff.loc["fgi"] == df.index[-20]
        assert pd.isna(ff.loc["dd_ath"]) or isinstance(ff.loc["dd_ath"], pd.Timestamp)


@pytest.mark.skipif(not _REAL_CACHE.exists(), reason="frozen frame cache not present")
class TestRealFrame:
    def test_dossier_dates_on_frozen_frame(self):
        from src.research.btc_bottoms import macro_overlay

        frame = macro_overlay.prepare_macro_frame(build_frame(refresh=False))
        events = ev.find_bottoms(frame, "cycle")
        assert len(events) == 5
        d2018 = dos.dossier(frame, events, 1)
        assert d2018.loc["bottom", "date"] == pd.Timestamp("2018-12-15")
        assert d2018.loc["confirm", "date"] == pd.Timestamp("2019-04-02")
        d2026 = dos.dossier(frame, events, 4)
        assert d2026.loc["bottom", "date"] == pd.Timestamp("2026-06-30")

    def test_conditions_match_g1_on_whole_frozen_history(self):
        """Every row of the real frame: zero value and NaN-pattern drift."""
        from src.research.btc_bottoms import macro_overlay

        prepared = macro_overlay.prepare_macro_frame(build_frame(refresh=False))
        mine = dos.macro_conditions(prepared)
        theirs = macro_overlay.macro_conditions(prepared)
        for mine_col, g1_col in dos.MACRO_TO_G1.items():
            assert mine[mine_col].astype("float").equals(theirs[g1_col]), mine_col
        # The plan rule the defect was about: warm-up is NA, not False.
        # diff(21) conditions: 21 warm-up rows; rolling(21) (M3a): 20.
        assert mine["M1_real_yield_easing"].iloc[:21].isna().all()
        assert mine["M3b_credit_easing"].iloc[:21].isna().all()
        assert mine["M3a_vix_fade"].iloc[:20].isna().all()

    def test_false_confirm_counts_match_events_module(self):
        from src.research.btc_bottoms import macro_overlay

        frame = macro_overlay.prepare_macro_frame(build_frame(refresh=False))
        events = ev.find_bottoms(frame, "cycle")
        for _i, row in events.iterrows():
            tl = dos.false_confirm_timeline(frame, row)
            assert len(tl) == int(row["false_confirms"])
