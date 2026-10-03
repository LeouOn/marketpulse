"""Tests for the causal BTC bottom-signal library (wave 1, g4).

Three layers, matching the shared contract:

1. **Synthetic-path unit tests** - each signal is fed a hand-built
   frame where the intended behaviour is known exactly (drawdown depth,
   streak counts, warm-up lengths, fire directions, gap semantics).
2. **Prefix-invariance property tests** - for EVERY output column,
   computing on ``df[:t]`` must equal the first ``t`` rows of computing
   on ``df`` (causality; contract hard requirement 1).
3. **Real-cache smoke** (skipif the cache file is absent) - the
   registry must run on the real cached daily frame without error and
   produce sane coverage; the numeric read-outs live in the wave-1
   report, not in assertions (no fabricated expectations).

All offline: no network, no keys, no LLM endpoints.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.research.btc_bottoms.signals import (
    DEFAULT_PARAMS,
    FIRE_DIRECTIONS,
    SIGNAL_REGISTRY,
    compute_signals,
    fire,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def daily_frame(
    n: int,
    close: np.ndarray | pd.Series | None = None,
    volume: np.ndarray | None = None,
    fgi: np.ndarray | None = None,
    start: str = "2020-01-01",
) -> pd.DataFrame:
    """Build a contract-shaped daily frame: calendar-day DatetimeIndex."""
    idx = pd.date_range(start, periods=n, freq="D", name="ts")
    df = pd.DataFrame(index=idx)
    df["close"] = close if close is not None else np.full(n, 100.0)
    df["volume"] = volume if volume is not None else np.full(n, 1_000.0)
    df["open"] = df["close"]
    df["high"] = df["close"]
    df["low"] = df["close"]
    if fgi is not None:
        df["fgi_value"] = fgi
    return df


def _col(out: pd.DataFrame, name: str) -> pd.Series:
    return out[name]


def _true_dates(out: pd.DataFrame, name: str) -> set:
    """Dates where a boolean column is True (ignores NA)."""
    s = out[name]
    return set(s.index[s.fillna(False).astype(bool)])


# ---------------------------------------------------------------------------
# Registry consistency
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_fire_directions_match_continuous_signals(self):
        continuous = {n for n, (k, _, _) in SIGNAL_REGISTRY.items() if k == "continuous"}
        assert set(FIRE_DIRECTIONS) == continuous

    def test_grids_are_non_empty_lists(self):
        for name, (_kind, _thr, grid) in SIGNAL_REGISTRY.items():
            assert grid, f"{name} has an empty grid"
            for key, values in grid.items():
                assert isinstance(values, list) and values, f"{name}.{key} grid empty"
                assert all(np.isfinite(v) for v in values), f"{name}.{key} has non-finite values"

    def test_default_params_inside_grid(self):
        for name, eff in DEFAULT_PARAMS.items():
            grid = SIGNAL_REGISTRY[name][2]
            for key, value in eff.items():
                assert value in grid[key], f"default {name}.{key}={value} is outside its sweep grid {grid[key]}"

    def test_boolean_signals_have_no_fire_direction_and_vice_versa(self):
        for name, (kind, thr, _grid) in SIGNAL_REGISTRY.items():
            if kind == "boolean":
                assert name not in FIRE_DIRECTIONS
                assert thr is None, "multi-parameter compounds take defaults from DEFAULT_PARAMS"
            else:
                assert name in FIRE_DIRECTIONS
                assert thr is not None

    def test_output_columns_match_registry(self):
        out = compute_signals(daily_frame(400))
        expected = set(SIGNAL_REGISTRY)
        expected |= {f"{n}_fire" for n, (k, _, _) in SIGNAL_REGISTRY.items() if k == "continuous"}
        assert set(out.columns) == expected


# ---------------------------------------------------------------------------
# Synthetic-path unit tests, per signal
# ---------------------------------------------------------------------------


class TestDrawdownFromAth:
    def test_depth_and_days_since_ath(self):
        closes = np.concatenate(
            [
                np.linspace(100.0, 200.0, 100),  # rise to ATH=200 at day 99
                np.linspace(200.0, 100.0, 50),  # -50% crash
            ]
        )
        out = compute_signals(daily_frame(150, close=closes))
        # On the last day: close=100, ATH=200 -> dd = -0.5, 50 days since ATH
        assert out["dd_ath"].iloc[-1] == pytest.approx(-0.5)
        assert out["days_since_ath"].iloc[-1] == 50
        # No warm-up: defined from row 0 (running max from frame start)
        assert out["dd_ath"].notna().all()
        # During the rise, every new high resets days_since_ath to 0
        assert out["days_since_ath"].iloc[50] == 0
        assert out["dd_ath"].iloc[50] == pytest.approx(0.0)
        # Fire column: deep drawdown fires (direction le)
        assert bool(out["dd_ath_fire"].iloc[-1]) is True
        assert bool(out["dd_ath_fire"].iloc[50]) is False

    def test_fire_respects_threshold_param(self):
        closes = np.concatenate([np.full(50, 100.0), np.full(50, 60.0)])  # -40%
        df = daily_frame(100, close=closes)
        default = compute_signals(df)  # threshold -0.50: -40% does not fire
        loose = compute_signals(df, params={"dd_ath": {"threshold": -0.35}})
        assert bool(default["dd_ath_fire"].iloc[-1]) is False
        assert bool(loose["dd_ath_fire"].iloc[-1]) is True


class TestTrailingDrawdown:
    def test_dd_90d_uses_trailing_high_only(self):
        closes = np.full(200, 100.0)
        closes[50] = 150.0  # spike inside 90d of day 100? day 100-50=50 -> outside window
        closes[150] = 140.0  # inside trailing 90d of day 199
        closes[199] = 105.0
        out = compute_signals(daily_frame(200, close=closes))
        # Warm-up: first 89 rows NaN (90-day high needs a full window)
        assert out["dd_90d"].iloc[:89].isna().all()
        assert out["dd_90d"].notna().iloc[89]
        # Day 199: trailing 90d high = 140 (day 150); 105/140-1 = -0.25
        assert out["dd_90d"].iloc[199] == pytest.approx(105.0 / 140.0 - 1.0)


class TestMovingAverages:
    def test_mayer_matches_manual_sma200(self):
        rng = np.random.default_rng(7)
        closes = 100 + np.cumsum(rng.normal(0, 1, 300))
        out = compute_signals(daily_frame(300, close=closes))
        s = pd.Series(closes)
        manual = s / s.rolling(200).mean()
        assert out["mayer_multiple"].iloc[:199].isna().all()
        np.testing.assert_allclose(out["mayer_multiple"].to_numpy()[199:], manual.to_numpy()[199:])

    def test_sma200w_warmup_and_flat_price(self):
        out = compute_signals(daily_frame(1500))  # flat close=100
        assert out["close_vs_sma200w"].iloc[:1399].isna().all()
        assert out["close_vs_sma200w"].iloc[1399] == pytest.approx(1.0)

    def test_200w_window_is_1400_calendar_days(self):
        # 700 days at 50 then 700 at 150: the only full 1400-day window
        # covers the whole frame, whose mean (100) equals the mean of
        # the 200 weekly closes -> close/MA = 150/100 = 1.5.
        closes = np.concatenate([np.full(700, 50.0), np.full(700, 150.0)])
        out = compute_signals(daily_frame(1400, close=closes))
        assert out["close_vs_sma200w"].iloc[-1] == pytest.approx(1.5)


class TestRsi:
    def test_daily_rsi_reuses_wilder_helper(self):
        from src.research.backtest.indicators import compute_rsi

        rng = np.random.default_rng(3)
        closes = 100 + np.cumsum(rng.normal(-0.2, 1.5, 200))
        out = compute_signals(daily_frame(200, close=closes))
        expected = compute_rsi(pd.Series(closes, index=out.index), 14)
        pd.testing.assert_series_equal(out["rsi_14"], expected, check_names=False)

    def test_oversold_fires_low_not_high(self):
        rng = np.random.default_rng(3)
        crash = 100 + np.cumsum(rng.normal(-3.0, 1.0, 60))  # relentless decline
        out = compute_signals(daily_frame(60, close=crash))
        fired = out["rsi_14_fire"].fillna(False).astype(bool)
        assert fired.iloc[20:].mean() > 0.5  # mostly oversold during the crash

    def test_weekly_rsi_uses_completed_weeks_only(self):
        # 30 weeks of decline, then one huge up day mid-week: the current
        # (in-progress) week must NOT be read before it completes.
        n = 30 * 7 + 3  # 213 days, ends on a Wednesday
        closes = np.full(n, 100.0)
        closes[1:] = 100 - np.arange(1, n) * 0.5  # steady decline
        closes[-1] = closes[-2] * 2  # Wednesday moon
        out = compute_signals(daily_frame(n, close=closes, start="2020-01-06"))
        # Sunday before the moon vs Wednesday of the moon: the current
        # (in-progress) week is never read, so Wednesday's weekly RSI
        # still shows the last COMPLETED week.
        assert out.index[-1].day_name() == "Wednesday"
        # Wednesday reads the last COMPLETED week (Sunday), so its
        # weekly RSI equals Tuesday's read: the moon is invisible.
        assert out["rsi_14w"].iloc[-1] == pytest.approx(out["rsi_14w"].iloc[-2])
        assert not pd.isna(out["rsi_14w"].iloc[-1])
        # Stronger: mutating the moon day must not change earlier weekly reads.
        closes2 = closes.copy()
        closes2[-1] = closes2[-2]
        out2 = compute_signals(daily_frame(n, close=closes2, start="2020-01-06"))
        pd.testing.assert_series_equal(out["rsi_14w"].iloc[:-1], out2["rsi_14w"].iloc[:-1], check_names=False)


class TestVolume:
    def test_vol_z_spike_and_capitulation(self):
        n = 200
        volume = np.full(n, 1000.0)
        volume[150] = 4000.0  # 4x spike on a big down day
        closes = np.full(n, 100.0)
        closes[150] = 92.0  # -8% day
        out = compute_signals(daily_frame(n, close=closes, volume=volume))
        assert out["vol_z_90"].iloc[:90].isna().all()
        z = out["vol_z_90"].iloc[150]
        assert z > 3.0
        assert bool(out["capitulation_vol"].iloc[150]) is True
        assert bool(out["capitulation_vol"].iloc[149]) is False
        # A 4x volume spike on a FLAT day must not fire capitulation
        volume2 = volume.copy()
        closes2 = closes.copy()
        closes2[150] = closes2[149]
        out2 = compute_signals(daily_frame(n, close=closes2, volume=volume2))
        assert bool(out2["capitulation_vol"].iloc[150]) is False

    def test_vol_exhaustion_after_decline(self):
        n = 200
        closes = np.full(n, 100.0)
        closes[100:] = np.linspace(100.0, 60.0, 100)  # 30d return clearly < 0
        volume = np.full(n, 1000.0)
        volume[180:] = 400.0  # dries up below the 0.6 ratio
        out = compute_signals(daily_frame(n, close=closes, volume=volume))
        assert out["vol_ratio_90"].iloc[180] == pytest.approx(0.4, rel=0.35)
        assert bool(out["vol_exhaustion"].iloc[190]) is True
        assert bool(out["vol_exhaustion"].iloc[150]) is False

    def test_missing_volume_column_yields_nan_not_crash(self):
        df = daily_frame(200)
        df = df.drop(columns=["volume"])
        out = compute_signals(df)
        assert out["vol_z_90"].isna().all()
        assert out["vol_ratio_90"].isna().all()
        # Kleene semantics (module docstring decision 2): the volume leg
        # is unknown, the price leg is definitively off (flat day) ->
        # the compound reads False, not NA; on day 0 the price leg is
        # also unknown -> NA.
        assert pd.isna(out["capitulation_vol"].iloc[0])
        assert bool(out["capitulation_vol"].iloc[5]) is False


class TestRealisedVol:
    def test_percentile_rises_with_burst_then_falls(self):
        rng = np.random.default_rng(11)
        n = 2000
        rets = rng.normal(0, 0.01, n)
        rets[800:860] = rng.normal(0, 0.12, 60)  # violent burst, after warm-up
        rets[860:] = rng.normal(0, 0.002, n - 860)  # calmer than the old regime
        closes = 100 * np.exp(np.cumsum(rets))
        out = compute_signals(daily_frame(n, close=closes))
        pct = out["rvol_pct_2y"]
        # Warm-up: row 0 has no return, rv needs 30, the rank needs 730
        # more -> first valid row is 759.
        assert pct.iloc[:759].isna().all()
        assert pct.notna().iloc[759]
        assert pct.iloc[860] > 0.9  # burst day reads near the top of its 2y window
        # After the burst, vol settles below the OLD regime while the
        # old regime (and the burst) are still inside the rank window
        # -> the percentile drops low.
        assert pct.iloc[905] < 0.3
        # And it never returns to the burst peak once calm resumes
        assert pct.iloc[-1] < pct.iloc[860]

    def test_compress_after_spike_fires_only_after_calm_returns(self):
        rng = np.random.default_rng(12)
        n = 2000
        rets = rng.normal(0, 0.01, n)
        rets[900:960] = rng.normal(0, 0.15, 60)
        closes = 100 * np.exp(np.cumsum(rets))
        out = compute_signals(daily_frame(n, close=closes))
        s = out["rvol_compress_after_spike"]
        assert s.iloc[:759].isna().all()  # rvol warm-up is NA, not False
        fired = _true_dates(out, "rvol_compress_after_spike")
        # Nothing fires during the burst itself (still high vol)
        assert not any(out.index[900] <= d <= out.index[960] for d in fired)
        # The calm tail after the burst has fired days
        assert any(d > out.index[960] for d in fired)


class TestStreaksAndLows:
    def test_downstreak_counts_exact(self):
        closes = np.full(20, 100.0)
        down_days = [3, 4, 5, 10, 11]  # close falls on these indices
        for d in down_days:
            closes[d] = closes[d - 1] - 1.0
        out = compute_signals(daily_frame(20, close=closes))
        assert out["downstreak"].iloc[0] != out["downstreak"].iloc[0]  # NaN, no prior close
        assert out["downstreak"].iloc[5] == 3.0
        assert out["downstreak"].iloc[6] == 0.0
        assert out["downstreak"].iloc[11] == 2.0

    def test_days_since_low_90(self):
        closes = np.full(300, 100.0)
        closes[120] = 50.0  # deep one-day low, then recovery
        out = compute_signals(daily_frame(300, close=closes))
        dsl = out["days_since_low_90"]
        assert dsl.iloc[:120].isna().all()  # no strict new 90d low before day 120
        assert dsl.iloc[120] == 0.0
        assert dsl.iloc[130] == 10.0
        assert dsl.iloc[205] == 85.0
        # The recovery never breaks below the low again: the counter
        # keeps counting (a turn, not a reset)
        assert dsl.iloc[220] == 100.0


class TestFearGreed:
    def test_absent_fgi_is_all_nan(self):
        out = compute_signals(daily_frame(300))
        for col in ("fgi", "fgi_extreme_streak", "fgi_mean_30", "washout_stabilise"):
            assert out[col].isna().all(), col
            fire_col = f"{col}_fire"
            if fire_col in out.columns:
                assert out[fire_col].isna().all(), fire_col

    def test_extreme_level_and_streak(self):
        n = 200
        fgi = np.full(n, 60.0)
        fgi[100:108] = 12.0  # 8 extreme-fear days
        fgi[150] = 20.0  # isolated
        out = compute_signals(daily_frame(n, fgi=fgi))
        assert out["fgi"].iloc[100] == 12.0
        assert bool(out["fgi_fire"].iloc[100]) is True  # <= 25
        assert out["fgi_extreme_streak"].iloc[107] == 8.0
        assert out["fgi_extreme_streak"].iloc[108] == 0.0
        assert out["fgi_extreme_streak"].iloc[150] == 1.0
        # default fgi_thresh=25 -> the isolated 20 also counts
        assert out["fgi_extreme_streak"].iloc[151] == 0.0

    def test_streak_param_changes_threshold(self):
        n = 100
        fgi = np.full(n, 60.0)
        fgi[30:35] = 18.0  # <= 20 but > 15
        default = compute_signals(daily_frame(n, fgi=fgi))
        tight = compute_signals(daily_frame(n, fgi=fgi), params={"fgi_extreme_streak": {"fgi_thresh": 15}})
        assert default["fgi_extreme_streak"].iloc[34] == 5.0
        assert tight["fgi_extreme_streak"].iloc[34] == 0.0

    def test_mean_30_requires_30_non_null(self):
        n = 120
        fgi = np.full(n, 40.0)
        fgi[:70] = np.nan  # fgi starts at day 70
        out = compute_signals(daily_frame(n, fgi=fgi))
        # FGI present from day 70: the first 30-non-null window completes
        # exactly on day 99 (70..99 inclusive).
        assert pd.isna(out["fgi_mean_30"].iloc[98])
        assert out["fgi_mean_30"].iloc[99] == pytest.approx(40.0)

    def test_gap_breaks_streak_with_nan(self):
        n = 100
        fgi = np.full(n, 60.0)
        fgi[20:25] = 10.0
        fgi[40] = np.nan  # gap inside a later extreme run
        fgi[41:45] = 10.0
        out = compute_signals(daily_frame(n, fgi=fgi))
        assert out["fgi_extreme_streak"].iloc[40] != out["fgi_extreme_streak"].iloc[40]  # NaN
        assert out["fgi_extreme_streak"].iloc[44] == 4.0  # restarts after the gap

    def test_washout_stabilise_compound(self):
        # 200 days; deep 90d low at day 100; extreme fear days 95-105;
        # no new lows afterwards; stabilise_days=10, lookback=10.
        n = 250
        rng = np.random.default_rng(5)
        closes = 100 + np.cumsum(rng.normal(0.0, 0.05, n))
        closes[100] = closes[:100].min() - 10.0  # new deep low
        fgi = np.full(n, 60.0)
        fgi[95:106] = 10.0
        out = compute_signals(daily_frame(n, close=closes, fgi=fgi))
        ws = out["washout_stabilise"]
        # Before day 110: either NA (warm-up) or False (low too recent)
        assert not any(bool(v) for v in ws.iloc[:110].dropna())
        # Day 110-115: fear was extreme within 10 days and 10+ days
        # since the low -> fires
        fired = _true_dates(out, "washout_stabilise")
        assert any(out.index[110] <= d <= out.index[115] for d in fired)
        # Well after both windows: no fire
        assert out.index[130] not in fired


class TestParams:
    def test_unknown_signal_rejected(self):
        with pytest.raises(ValueError, match="unknown signals"):
            compute_signals(daily_frame(50), params={"nope": {"threshold": 1}})

    def test_unknown_param_key_rejected(self):
        with pytest.raises(ValueError, match="unknown params"):
            compute_signals(daily_frame(50), params={"rsi_14": {"threshhold": 1}})

    def test_threshold_override_changes_fire(self):
        closes = np.full(120, 100.0)
        closes[100:] = 70.0  # -30% from the trailing 90d high
        df = daily_frame(120, close=closes)
        default = compute_signals(df)  # -0.25 threshold: fires
        strict = compute_signals(df, params={"dd_90d": {"threshold": -0.35}})  # -0.30: no
        assert bool(default["dd_90d_fire"].iloc[-1]) is True
        assert bool(strict["dd_90d_fire"].iloc[-1]) is False

    def test_fire_helper_rethresholds_without_recompute(self):
        closes = np.concatenate([np.full(60, 100.0), np.full(60, 80.0)])
        out = compute_signals(daily_frame(120, close=closes))
        loose = fire(out, "dd_ath", threshold=-0.10)
        strict = fire(out, "dd_ath", threshold=-0.30)
        assert bool(loose.iloc[-1]) is True
        assert bool(strict.iloc[-1]) is False


# ---------------------------------------------------------------------------
# Prefix invariance (contract hard requirement 1) - EVERY signal
# ---------------------------------------------------------------------------

BOOLEAN_COLUMNS = {n for n, (k, _, _) in SIGNAL_REGISTRY.items() if k == "boolean"} | {
    f"{n}_fire" for n, (k, _, _) in SIGNAL_REGISTRY.items() if k == "continuous"
}


@pytest.mark.parametrize("column", sorted(set(SIGNAL_REGISTRY) | BOOLEAN_COLUMNS))
def test_prefix_invariance(column):
    """compute(df[:t]) == compute(df)[:t] for every output column."""
    rng = np.random.default_rng(42)
    n = 400
    rets = rng.normal(-0.0005, 0.04, n)
    closes = 100 * np.exp(np.cumsum(rets))
    volume = 1000 * np.exp(rng.normal(0, 0.3, n))
    fgi = np.clip(50 + np.cumsum(rng.normal(0, 4, n)), 0, 100)
    fgi[rng.choice(n, 8, replace=False)] = np.nan  # realistic gaps
    df = daily_frame(n, close=closes, volume=volume, fgi=fgi)

    full = compute_signals(df)
    for t in (1, 15, 91, 150, 201, 350, n):
        part = compute_signals(df.iloc[:t])
        pd.testing.assert_series_equal(
            part[column].rename("x"),
            full[column].iloc[:t].rename("x"),
            check_names=False,
            check_freq=False,
        )


def test_prefix_invariance_with_params():
    rng = np.random.default_rng(43)
    n = 300
    closes = 100 * np.exp(np.cumsum(rng.normal(-0.001, 0.03, n)))
    fgi = np.clip(50 + np.cumsum(rng.normal(0, 5, n)), 0, 100)
    df = daily_frame(n, close=closes, fgi=fgi)
    params = {
        "washout_stabilise": {"stabilise_days": 5, "washout_lookback": 20},
        "fgi_extreme_streak": {"fgi_thresh": 20},
        "capitulation_vol": {"vol_z": 1.5},
    }
    full = compute_signals(df, params=params)
    part = compute_signals(df.iloc[:200], params=params)
    for col in full.columns:
        pd.testing.assert_series_equal(
            part[col].rename("x"),
            full[col].iloc[:200].rename("x"),
            check_names=False,
            check_freq=False,
        )


# ---------------------------------------------------------------------------
# Frame-contract edge cases
# ---------------------------------------------------------------------------


def test_short_history_yields_nan_not_zeros():
    out = compute_signals(daily_frame(30))  # shorter than every warm-up
    for col in ("mayer_multiple", "close_vs_sma200w", "vol_z_90", "rvol_pct_2y", "fgi_mean_30"):
        assert out[col].isna().all(), col
    # dd_ath IS defined on short frames (running max, no warm-up)
    assert out["dd_ath"].notna().all()


def test_output_index_preserved_and_sorted():
    idx = pd.date_range("2020-01-01", periods=100, freq="D", name="ts")
    df = pd.DataFrame({"close": np.linspace(100, 90, 100), "volume": np.full(100, 1e3)}, index=idx).iloc[
        ::-1
    ]  # reverse order on purpose
    out = compute_signals(df)
    assert out.index.equals(idx)
    assert out.index.is_monotonic_increasing


# ---------------------------------------------------------------------------
# Real cached data (skipif absent: hermetic CI has no data/cache)
# ---------------------------------------------------------------------------

CACHE = Path(__file__).resolve().parents[2] / "data" / "cache" / "btc" / "daily.csv"
FGI_CACHE = Path(__file__).resolve().parents[2] / "data" / "cache" / "btc" / "fear_greed.csv"


@pytest.mark.skipif(not CACHE.exists(), reason="cached BTC daily data not present (hermetic run)")
def test_real_cache_smoke():
    df = pd.read_csv(CACHE, parse_dates=["ts"]).set_index("ts")
    if FGI_CACHE.exists():
        fgi = pd.read_csv(FGI_CACHE, parse_dates=["ts"]).set_index("ts")[["fgi_value"]]
        df = df.join(fgi, how="left")
    out = compute_signals(df)
    assert out.index.equals(df.index)
    assert len(out) == len(df)
    # Every boolean column has at least one non-NA value on the real
    # frame, and no continuous column is entirely NaN (fgi columns may
    # be partial: FGI starts 2018-02).
    for name, (kind, _thr, _grid) in SIGNAL_REGISTRY.items():
        if kind == "boolean":
            assert out[name].notna().any(), f"{name} is all-NA on the real frame"
        else:
            assert out[name].notna().any(), f"{name} is all-NaN on the real frame"
