"""Offline tests for the point-in-time BTC + macro frame (wave 1, g1).

All fetchers are fakes -- no network, no keys, no LLM calls (contract rule 4).
The tests pin the honesty properties of the frame: lag-table honouring,
point-in-time (no lookahead), no silent forward-fill, schema, idempotence,
and honest degradation when a source is absent.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.research.btc_bottoms.fetch_onchain import aggregate_funding_hourly
from src.research.btc_bottoms.frame import (
    DERIVED_COLUMNS,
    FRAME_COLUMNS,
    LAG_TABLE,
    LagSpec,
    build_frame,
    coverage_report,
)

# ---------------------------------------------------------------------------
# Fake sources: a small, fully controlled world (2026-01-01 .. 2026-02-15)
# ---------------------------------------------------------------------------

CAL_START = "2025-08-01"
CAL_END = "2026-02-15"
DAYS = pd.date_range(CAL_START, CAL_END, freq="D", name="ts")


def _fake_btc() -> pd.DataFrame:
    n = len(DAYS)
    close = np.linspace(60_000.0, 70_000.0, n)
    return pd.DataFrame(
        {
            "ts": DAYS,
            "open": close * 0.99,
            "high": close * 1.02,
            "low": close * 0.97,
            "close": close,
            "volume": np.full(n, 1_000.0),
        }
    )


def _fake_fgi() -> pd.DataFrame:
    # every other day only, to exercise NaN-on-missing (no ffill policy)
    idx = DAYS[::2]
    return pd.DataFrame({"ts": idx, "fgi_value": np.linspace(10.0, 90.0, len(idx))})


def _fake_fred_daily() -> dict[str, pd.Series]:
    idx = pd.date_range("2025-09-01", "2026-02-14", freq="B", name="ts")  # business days
    out: dict[str, pd.Series] = {}
    for col in ("dgs10", "dfii10", "t10yie", "dgs2", "vix", "hy_oas", "dxy", "rrp_onday"):
        out[col] = pd.Series(np.arange(1.0, 1.0 + len(idx)), index=idx, name=col)
    return out


def _fake_fred_weekly() -> dict[str, pd.Series]:
    # Wednesday observations (WALCL / WTREGEN convention); first obs 2026-01-07
    idx = pd.date_range("2026-01-07", "2026-02-11", freq="W-WED", name="ts")
    return {
        "walcl": pd.Series(np.arange(7_000.0, 7_000.0 + 10 * len(idx), 10), index=idx, name="walcl"),
        "wtregen": pd.Series(np.arange(800.0, 800.0 + 5 * len(idx), 5), index=idx, name="wtregen"),
    }


def _fake_yahoo_risk() -> dict[str, pd.Series]:
    idx = pd.date_range("2025-12-26", "2026-02-13", freq="B", name="ts")
    return {
        "spx": pd.Series(np.linspace(5_000.0, 5_500.0, len(idx)), index=idx, name="spx"),
        "gold": pd.Series(np.linspace(2_000.0, 2_200.0, len(idx)), index=idx, name="gold"),
        "dxy_ice": pd.Series(np.linspace(100.0, 105.0, len(idx)), index=idx, name="dxy_ice"),
    }


def _fake_onchain() -> dict[str, pd.Series]:
    # long enough for the 365-day expanding window of mvrv_z
    idx = pd.date_range("2024-06-01", "2026-02-14", freq="D", name="ts")
    mcap = pd.Series(np.linspace(1.0e12, 1.5e12, len(idx)), index=idx, name="mcap_usd")
    mvrv = pd.Series(np.linspace(1.2, 2.0, len(idx)), index=idx, name="mvrv")
    return {"mcap_usd": mcap, "mvrv": mvrv}


def _fake_funding_daily() -> pd.Series:
    idx = pd.date_range("2025-12-15", "2026-02-14", freq="D", name="ts")
    return pd.Series(np.full(len(idx), 1.0e-4), index=idx, name="funding_rate")


class FakeSources:
    """Injection bundle mirroring the real fetcher seams of frame.py."""

    def __init__(self, **overrides):
        self.btc_daily = overrides.get("btc_daily", _fake_btc)
        self.fgi = overrides.get("fgi", _fake_fgi)
        self.fred_daily = overrides.get("fred_daily", _fake_fred_daily)
        self.fred_weekly = overrides.get("fred_weekly", _fake_fred_weekly)
        self.yahoo_risk = overrides.get("yahoo_risk", _fake_yahoo_risk)
        self.onchain = overrides.get("onchain", _fake_onchain)
        self.funding = overrides.get("funding", _fake_funding_daily)
        self.today = overrides.get("today", lambda: pd.Timestamp("2026-02-16"))


@pytest.fixture()
def built(tmp_path, monkeypatch):
    """build_frame against a temp cache dir with fake sources; returns the frame."""
    monkeypatch.setenv("MARKETPULSE_DATA_DIR", str(tmp_path))
    df = build_frame(refresh=True, sources=FakeSources())
    return df


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class TestSchema:
    def test_exact_columns_and_order(self, built):
        assert list(built.columns) == FRAME_COLUMNS

    def test_index_is_sorted_unique_midnight_naive_named_ts(self, built):
        idx = built.index
        assert isinstance(idx, pd.DatetimeIndex)
        assert idx.is_monotonic_increasing
        assert idx.is_unique
        assert idx.name == "ts"
        assert str(idx.tz) == "None"
        assert (idx == idx.normalize()).all()

    def test_all_value_columns_float64(self, built):
        for col in built.columns:
            assert built[col].dtype == np.float64, col

    def test_calendar_covers_btc_range_including_missing_days(self, tmp_path, monkeypatch):
        # drop one BTC day from the source: the calendar row must survive (NaN OHLCV)
        btc = _fake_btc()
        holed = btc[btc["ts"] != pd.Timestamp("2026-01-20")]
        monkeypatch.setenv("MARKETPULSE_DATA_DIR", str(tmp_path))
        df = build_frame(refresh=True, sources=FakeSources(btc_daily=lambda: holed))
        assert pd.Timestamp("2026-01-20") in df.index
        assert np.isnan(df.loc[pd.Timestamp("2026-01-20"), "close"])
        assert df.loc[pd.Timestamp("2026-01-21"), "close"] > 0


# ---------------------------------------------------------------------------
# Lag table honouring (point-in-time placement)
# ---------------------------------------------------------------------------


class TestLagHonoured:
    def test_daily_fred_value_dated_d_appears_at_row_d_plus_1(self, built):
        # 2026-01-05 is a Monday (business day): value must be in row 01-06, not 01-05
        assert np.isnan(built.loc[pd.Timestamp("2026-01-05"), "dgs10"])
        assert (
            built.loc[pd.Timestamp("2026-01-06"), "dgs10"]
            == _fake_fred_daily()["dgs10"].loc[pd.Timestamp("2026-01-05")]
        )

    def test_weekly_obs_dated_w_appears_at_row_w_plus_2(self, built):
        w = pd.Timestamp("2026-01-07")  # Wednesday
        assert np.isnan(built.loc[w, "walcl"])
        assert np.isnan(built.loc[pd.Timestamp("2026-01-08"), "walcl"])
        assert built.loc[pd.Timestamp("2026-01-09"), "walcl"] == _fake_fred_weekly()["walcl"].loc[w]

    def test_btc_and_fgi_same_day_no_shift(self, built):
        btc = _fake_btc()
        assert (
            built.loc[pd.Timestamp("2026-01-05"), "close"]
            == btc.set_index("ts").loc[pd.Timestamp("2026-01-05"), "close"]
        )
        fgi = _fake_fgi()
        d_present = fgi["ts"].iloc[3]
        d_gap = d_present + pd.Timedelta(days=1)  # every-other-day fake
        assert built.loc[d_present, "fgi_value"] == fgi["fgi_value"].iloc[3]
        # the in-between day must be NaN (no ffill)
        assert np.isnan(built.loc[d_gap, "fgi_value"])

    def test_onchain_shifted_plus_one(self, built):
        oc = _fake_onchain()
        d = pd.Timestamp("2026-01-10")
        assert built.loc[d, "mvrv"] == oc["mvrv"].loc[d - pd.Timedelta(days=1)]

    def test_every_non_derived_column_has_lag_spec(self):
        for col in FRAME_COLUMNS:
            if col in DERIVED_COLUMNS:
                continue
            if col.endswith("_age"):
                base = col.removesuffix("_age")
                assert base in LAG_TABLE, col
                continue
            assert col in LAG_TABLE, col

    def test_lag_shifts_non_negative_ints(self):
        for col, spec in LAG_TABLE.items():
            assert isinstance(spec, LagSpec), col
            assert isinstance(spec.shift_days, int) and spec.shift_days >= 0, col
            assert spec.source and spec.freq


# ---------------------------------------------------------------------------
# Forward-fill policy: only weeklies, with an age column
# ---------------------------------------------------------------------------


class TestFillPolicy:
    def test_weekly_ffilled_with_aging_days(self, built):
        # obs W=2026-01-07 (shift 2): rows 01-09..01-15 hold it (next obs 01-14 -> row 01-16)
        for day, expected_age in [
            ("2026-01-09", 2),
            ("2026-01-12", 5),
            ("2026-01-15", 8),
        ]:
            assert built.loc[pd.Timestamp(day), "walcl_age"] == expected_age
        # next obs 2026-01-14 lands 01-16 with age 2
        assert built.loc[pd.Timestamp("2026-01-16"), "walcl_age"] == 2

    def test_daily_macro_not_ffilled(self, built):
        # Under calendar shift +1: Saturday 01-03 carries Friday's value (PIT-correct),
        # but Sunday 01-04 has no prior publication within the lag -> NaN, no ffill.
        assert np.isnan(built.loc[pd.Timestamp("2026-01-04"), "dgs10"])
        assert np.isnan(built.loc[pd.Timestamp("2026-01-04"), "vix"])
        # and Monday 01-05 is NaN too (nothing dated Sunday 01-04 was published)
        assert np.isnan(built.loc[pd.Timestamp("2026-01-05"), "dgs10"])

    def test_age_nan_where_value_nan(self, built):
        # first weekly obs 2026-01-07 -> placement 01-09: rows 01-01..01-08 are NaN with NaN age
        head = built.loc[: pd.Timestamp("2026-01-08"), "wtregen"]
        ages = built.loc[: pd.Timestamp("2026-01-08"), "wtregen_age"]
        assert head.isna().all() and ages.isna().all()


# ---------------------------------------------------------------------------
# Point-in-time / no-lookahead property
# ---------------------------------------------------------------------------


def _series_with(series: pd.Series, date: pd.Timestamp, value: float) -> pd.Series:
    s = series.copy()
    s.loc[date] = value
    return s


class TestPointInTime:
    def test_changing_a_daily_value_dated_d_never_changes_rows_le_d(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MARKETPULSE_DATA_DIR", str(tmp_path))
        d = pd.Timestamp("2026-01-19")
        base = build_frame(refresh=True, sources=FakeSources())
        mutated_daily = {**_fake_fred_daily(), "dgs10": _series_with(_fake_fred_daily()["dgs10"], d, 99.0)}
        changed = build_frame(refresh=True, sources=FakeSources(fred_daily=lambda: mutated_daily))
        # rows <= d must be byte-identical
        pd.testing.assert_frame_equal(base.loc[:d], changed.loc[:d])
        # the changed value shows up only after d
        assert changed.loc[d + pd.Timedelta(days=1), "dgs10"] == 99.0

    def test_changing_a_weekly_obs_never_changes_rows_before_placement(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MARKETPULSE_DATA_DIR", str(tmp_path))
        w = pd.Timestamp("2026-01-21")  # Wednesday
        base = build_frame(refresh=True, sources=FakeSources())
        mutated_weekly = {**_fake_fred_weekly(), "walcl": _series_with(_fake_fred_weekly()["walcl"], w, 12345.0)}
        changed = build_frame(refresh=True, sources=FakeSources(fred_weekly=lambda: mutated_weekly))
        placement = w + pd.Timedelta(days=2)
        pd.testing.assert_frame_equal(
            base.loc[: placement - pd.Timedelta(days=1)], changed.loc[: placement - pd.Timedelta(days=1)]
        )
        assert changed.loc[placement, "walcl"] == 12345.0

    def test_changing_future_mcap_leaves_mvrv_z_rows_unchanged(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MARKETPULSE_DATA_DIR", str(tmp_path))
        d = pd.Timestamp("2026-01-15")
        base = build_frame(refresh=True, sources=FakeSources())
        oc = _fake_onchain()
        mutated = {"mvrv": oc["mvrv"], "mcap_usd": _series_with(oc["mcap_usd"], pd.Timestamp("2026-01-20"), 9.9e12)}
        changed = build_frame(refresh=True, sources=FakeSources(onchain=lambda: mutated))
        pd.testing.assert_frame_equal(base.loc[:d], changed.loc[:d])

    def test_mvrv_z_formula_on_toy_data(self, built):
        oc = _fake_onchain()
        mcap = oc["mcap_usd"]
        mvrv = oc["mvrv"]
        realized = mcap / mvrv
        expanding_std = mcap.expanding(min_periods=365).std()
        expected = (mcap - realized) / expanding_std
        d = pd.Timestamp("2026-02-14")  # last fake day; row holds value dated d-1
        s = expected.loc[d - pd.Timedelta(days=1)]
        assert built.loc[d, "mvrv_z"] == pytest.approx(s, rel=1e-9)

    def test_derived_changes_are_causal(self, built):
        d = pd.Timestamp("2026-01-31")
        expected = built.loc[d, "close"] / built.loc[d - pd.Timedelta(days=21), "close"] - 1
        assert built.loc[d, "close_chg_21d"] == pytest.approx(expected, rel=1e-12)
        e = pd.Timestamp("2026-02-05")
        exp63 = built.loc[e, "dfii10"] - built.loc[e - pd.Timedelta(days=63), "dfii10"]
        assert built.loc[e, "dfii10_chg_63d"] == pytest.approx(exp63, rel=1e-9, nan_ok=True)


# ---------------------------------------------------------------------------
# Idempotence and caching
# ---------------------------------------------------------------------------


class TestIdempotence:
    def test_refresh_twice_identical(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MARKETPULSE_DATA_DIR", str(tmp_path))
        a = build_frame(refresh=True, sources=FakeSources())
        b = build_frame(refresh=True, sources=FakeSources())
        pd.testing.assert_frame_equal(a, b, check_freq=False)

    def test_cache_read_equals_refresh_build(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MARKETPULSE_DATA_DIR", str(tmp_path))
        a = build_frame(refresh=True, sources=FakeSources())
        b = build_frame(refresh=False, sources=FakeSources())  # must serve from parquet
        pd.testing.assert_frame_equal(a, b, check_freq=False)


# ---------------------------------------------------------------------------
# Honest degradation
# ---------------------------------------------------------------------------


class TestDegradation:
    def test_missing_fred_yields_nan_columns_not_error(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MARKETPULSE_DATA_DIR", str(tmp_path))
        df = build_frame(
            refresh=True,
            sources=FakeSources(
                fred_daily=lambda: {},
                fred_weekly=lambda: {},
                yahoo_risk=lambda: {},
                onchain=lambda: {},
                funding=lambda: pd.Series(dtype=float, name="funding_rate"),
            ),
        )
        for col in ("dgs10", "walcl", "spx", "mvrv", "funding_rate"):
            assert col in df.columns
            assert df[col].isna().all(), col

    def test_incomplete_btc_today_is_dropped(self, tmp_path, monkeypatch):
        # fake "today" 2026-02-16; a source row on 02-16 (partial day) must not appear
        monkeypatch.setenv("MARKETPULSE_DATA_DIR", str(tmp_path))
        btc = _fake_btc()
        extra = btc.iloc[[-1]].copy()
        extra["ts"] = [pd.Timestamp("2026-02-16")]
        extended = pd.concat([btc, extra], ignore_index=True)
        df = build_frame(refresh=True, sources=FakeSources(btc_daily=lambda: extended))
        assert pd.Timestamp("2026-02-16") not in df.index
        assert df.index.max() == pd.Timestamp("2026-02-15")


# ---------------------------------------------------------------------------
# Coverage report (CLI backing)
# ---------------------------------------------------------------------------


class TestCoverageReport:
    def test_counts_and_bounds(self, built):
        rep = coverage_report(built)
        row = rep.loc["close"]
        assert row["first_valid"] == pd.Timestamp(CAL_START)
        assert row["last_valid"] == pd.Timestamp(CAL_END)
        assert row["non_nan"] == len(DAYS)
        assert row["pct_non_nan"] == 100.0
        fgi_row = rep.loc["fgi_value"]
        assert fgi_row["non_nan"] == len(DAYS[::2])

    def test_all_columns_present(self, built):
        assert set(coverage_report(built).index) == set(FRAME_COLUMNS)


# ---------------------------------------------------------------------------
# Funding aggregation (fetch seam)
# ---------------------------------------------------------------------------


class TestFundingAggregation:
    def test_hourly_events_summed_per_utc_day(self):
        idx = pd.to_datetime(["2026-01-01 00:00", "2026-01-01 06:00", "2026-01-01 12:00", "2026-01-02 00:00"], utc=True)
        rates = pd.Series([1e-4, 2e-4, 3e-4, 4e-4], index=idx, name="relativeFundingRate")
        daily = aggregate_funding_hourly(rates)
        assert daily.loc[pd.Timestamp("2026-01-01")] == pytest.approx(6e-4)
        assert daily.loc[pd.Timestamp("2026-01-02")] == pytest.approx(4e-4)

    def test_empty_input_gives_empty_series(self):
        daily = aggregate_funding_hourly(pd.Series(dtype=float, index=pd.DatetimeIndex([], tz="UTC")))
        assert daily.empty
