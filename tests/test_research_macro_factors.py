"""Tests for ``src/research/macro/factors.py`` (MacroFactorProvider, T11).

Covers the 9 required scenarios from the W3/T11 spec + 1 live Sahm
validation test:

  1. Happy path -- mocked Fred/Yahoo providers return canned data;
     ``load_factors`` returns a frame with exactly the 12 canonical
     factor columns.
  2. Cache hit -- pre-populated ``factors.parquet`` covers the range;
     no Fred/Yahoo calls are made.
  3. Cache miss -- partial or absent cache triggers underlying fetches.
  4. Forward-fill monthly -> daily -- a monthly CPI publication date
     carries its ``cpi_yoy`` value forward to non-publication days.
  5. Missing factor leaves NaN -- a series the (mocked) provider does
     not return stays NaN; no imputation is performed.
  6. Sahm rule -- synthetic unemployment data with a recession-style
     jump triggers the Sahm flag at the expected month.
  7. ``cpi_yoy`` -- 12-month pct change of CPIAUCSL level matches the
     hand-computed value.
  8. ``oil_term_structure`` -- CL1 close minus CL12 close.
  9. ``compute_zscores`` -- rolling z-score math is correct.
 10. ``@pytest.mark.live`` -- real FRED UNRATE 2005-2024 fires Sahm in
     both 2008 (GFC) and 2020 (COVID).

All unit tests use stub providers; only the ``live`` test hits the
network. Live tests are skipped by default -- set ``RUN_LIVE_TESTS=1``
to opt in.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Module under test. Importing at module scope produces the expected
# ModuleNotFoundError during the RED phase (before factors.py exists).
from src.research.macro.factors import (  # noqa: E402
    FACTOR_COLUMNS,
    MacroFactorProvider,
)


# ---------------------------------------------------------------------------
# Live-test opt-in
# ---------------------------------------------------------------------------

_LIVE_ENABLED = os.getenv("RUN_LIVE_TESTS", "") == "1"
_SKIP_LIVE = pytest.mark.skipif(
    not _LIVE_ENABLED,
    reason="Set RUN_LIVE_TESTS=1 to run live FRED validation (requires FRED_API_KEY).",
)


# ---------------------------------------------------------------------------
# Stub providers -- in-memory, call-recorded, configurable per series/ticker
# ---------------------------------------------------------------------------


def _metis(ts_list: list[str], values: list[float], source: str) -> pd.DataFrame:
    """Build a minimal Metis-contract frame (only ``ts`` + ``close`` needed)."""
    n = len(ts_list)
    return pd.DataFrame(
        {
            "ts": pd.to_datetime(ts_list),
            "open": values,
            "high": values,
            "low": values,
            "close": values,
            "volume": [float("nan")] * n,
            "source": [source] * n,
        }
    )


class StubFred:
    """In-memory Fred replacement. Records every ``fetch`` call."""

    def __init__(self, responses: dict[str, pd.DataFrame] | None = None) -> None:
        self.responses: dict[str, pd.DataFrame] = responses or {}
        self.calls: list[tuple[str, date, date]] = []

    def fetch(self, series_id: str, start: date, end: date) -> pd.DataFrame:
        self.calls.append((series_id, start, end))
        if series_id not in self.responses:
            return _metis([], [], f"fred:{series_id}")
        df = self.responses[series_id].copy()
        # Apply a coarse date filter (the stub does not need to be exact).
        mask = (df["ts"].dt.date >= start) & (df["ts"].dt.date <= end)
        return df.loc[mask].reset_index(drop=True)


class StubYahoo:
    """In-memory Yahoo replacement. Records every ``fetch`` call."""

    def __init__(self, responses: dict[str, pd.DataFrame] | None = None) -> None:
        self.responses: dict[str, pd.DataFrame] = responses or {}
        self.calls: list[tuple[str, date, date]] = []

    def fetch(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        self.calls.append((ticker, start, end))
        if ticker not in self.responses:
            return _metis([], [], f"yahoo:{ticker}")
        df = self.responses[ticker].copy()
        mask = (df["ts"].dt.date >= start) & (df["ts"].dt.date <= end)
        return df.loc[mask].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Synthetic data helpers
# ---------------------------------------------------------------------------


def _daily_series(series_id: str, start: str, periods: int, base: float = 1.0) -> pd.DataFrame:
    """Daily FRED stub frame with a constant value."""
    dates = pd.date_range(start, periods=periods, freq="D")
    values = [base] * periods
    return _metis([d.strftime("%Y-%m-%d") for d in dates], values, f"fred:{series_id}")


def _monthly_series(series_id: str, year: int, values: list[float]) -> pd.DataFrame:
    """Monthly FRED stub frame (one row per month start)."""
    dates = pd.date_range(f"{year}-01-01", periods=len(values), freq="MS")
    return _metis([d.strftime("%Y-%m-%d") for d in dates], values, f"fred:{series_id}")


def _full_fred_response() -> dict[str, pd.DataFrame]:
    """Return a Fred response map that populates ALL 9 FRED-derived factors."""
    return {
        "DFII10": _daily_series("DFII10", "2020-01-01", 400, 0.5),
        "DGS10": _daily_series("DGS10", "2020-01-01", 400, 1.5),
        "T10YIE": _daily_series("T10YIE", "2020-01-01", 400, 2.0),
        "DTWEXBGS": _daily_series("DTWEXBGS", "2020-01-01", 400, 110.0),
        "VIXCLS": _daily_series("VIXCLS", "2020-01-01", 400, 18.0),
        "DFF": _daily_series("DFF", "2020-01-01", 400, 0.15),
        "MORTGAGE30US": _daily_series("MORTGAGE30US", "2020-01-01", 400, 3.5),
        "UNRATE": _monthly_series("UNRATE", 2020, [5.0] * 24),
        "CPIAUCSL": _monthly_series(
            "CPIAUCSL",
            2019,
            # 24 months at 100 + i: lets cpi_yoy be hand-computed
            [100.0 + i for i in range(24)],
        ),
        "ISM_MANUFACTURING": _monthly_series("ISM_MANUFACTURING", 2020, [50.0] * 24),
    }


def _full_yahoo_response() -> dict[str, pd.DataFrame]:
    return {
        "CL=F": _metis(
            [f"2020-01-{d:02d}" for d in range(1, 32)], [80.0] * 31, "yahoo:CL=F"
        ),
        # CL12 (12-month forward) proxy -- spec uses ticker chosen by impl.
        # Tests don't hard-code it; they read OIL_BACK_TICKER from the impl.
    }


# ---------------------------------------------------------------------------
# Test 1: Happy path -- 12 columns
# ---------------------------------------------------------------------------


class TestHappyPath:
    """``load_factors`` joins 12 factors into one frame on a daily index."""

    def test_load_factors_returns_all_12_canonical_columns(self, tmp_path: Path):
        fred = StubFred(_full_fred_response())
        yahoo = StubYahoo(_full_yahoo_response())

        provider = MacroFactorProvider(fred=fred, yahoo=yahoo, cache_dir=tmp_path)
        df = provider.load_factors(date(2020, 1, 1), date(2020, 1, 31))

        assert list(df.columns) == list(FACTOR_COLUMNS)
        assert len(FACTOR_COLUMNS) == 12

    def test_load_factors_has_daily_index(self, tmp_path: Path):
        fred = StubFred(_full_fred_response())
        yahoo = StubYahoo(_full_yahoo_response())

        provider = MacroFactorProvider(fred=fred, yahoo=yahoo, cache_dir=tmp_path)
        df = provider.load_factors(date(2020, 1, 1), date(2020, 1, 31))

        # Daily DatetimeIndex spanning the requested range.
        assert isinstance(df.index, pd.DatetimeIndex)
        assert df.index.min() >= pd.Timestamp("2020-01-01")
        assert df.index.max() <= pd.Timestamp("2020-01-31")

    def test_load_factors_uses_all_fred_series(self, tmp_path: Path):
        fred = StubFred(_full_fred_response())
        yahoo = StubYahoo(_full_yahoo_response())

        provider = MacroFactorProvider(fred=fred, yahoo=yahoo, cache_dir=tmp_path)
        provider.load_factors(date(2020, 1, 1), date(2020, 1, 31))

        fetched_ids = {call[0] for call in fred.calls}
        assert "DFII10" in fetched_ids
        assert "DGS10" in fetched_ids
        assert "T10YIE" in fetched_ids
        assert "DTWEXBGS" in fetched_ids
        assert "VIXCLS" in fetched_ids
        assert "DFF" in fetched_ids
        assert "MORTGAGE30US" in fetched_ids
        assert "UNRATE" in fetched_ids
        assert "CPIAUCSL" in fetched_ids
        assert "ISM_MANUFACTURING" in fetched_ids


# ---------------------------------------------------------------------------
# Test 2 + 3: Cache hit / miss
# ---------------------------------------------------------------------------


class TestCache:
    """``factors.parquet`` short-circuits fetches when it covers the range."""

    def test_cache_hit_skips_all_fetches(self, tmp_path: Path):
        # 1. Prime the cache by running load_factors once with full data.
        fred = StubFred(_full_fred_response())
        yahoo = StubYahoo(_full_yahoo_response())
        provider = MacroFactorProvider(fred=fred, yahoo=yahoo, cache_dir=tmp_path)
        provider.load_factors(date(2020, 1, 1), date(2020, 1, 31))

        assert (tmp_path / "factors.parquet").exists()

        # 2. Fresh stubs with NO responses -- cache must serve.
        fred2 = StubFred({})
        yahoo2 = StubYahoo({})
        provider2 = MacroFactorProvider(fred=fred2, yahoo=yahoo2, cache_dir=tmp_path)
        df = provider2.load_factors(date(2020, 1, 10), date(2020, 1, 20))

        assert fred2.calls == [], "Fred should not be hit on cache hit"
        assert yahoo2.calls == [], "Yahoo should not be hit on cache hit"
        assert list(df.columns) == list(FACTOR_COLUMNS)
        assert len(df) > 0

    def test_cache_miss_triggers_fetches(self, tmp_path: Path):
        fred = StubFred(_full_fred_response())
        yahoo = StubYahoo(_full_yahoo_response())

        provider = MacroFactorProvider(fred=fred, yahoo=yahoo, cache_dir=tmp_path)
        provider.load_factors(date(2020, 1, 1), date(2020, 1, 31))

        assert len(fred.calls) > 0
        assert len(yahoo.calls) > 0


# ---------------------------------------------------------------------------
# Test 4: Forward-fill monthly -> daily
# ---------------------------------------------------------------------------


class TestForwardFill:
    """Monthly publications carry forward to non-publication days."""

    def test_monthly_cpi_carries_forward_to_daily(self, tmp_path: Path):
        fred = StubFred(_full_fred_response())
        yahoo = StubYahoo(_full_yahoo_response())
        provider = MacroFactorProvider(fred=fred, yahoo=yahoo, cache_dir=tmp_path)

        df = provider.load_factors(date(2020, 1, 1), date(2020, 6, 30))

        # cpi_yoy is published monthly. After ffill, every business day
        # between publications should carry the most-recent value (no NaN).
        cpi_yoy = df["cpi_yoy"].dropna()
        assert len(cpi_yoy) > 30, "cpi_yoy should be forward-filled onto daily rows"
        # The first daily row of 2020-02 should already have a value
        # carried forward from the 2020-01 publication.
        assert df.loc["2020-02-15", "cpi_yoy"] == pytest.approx(
            df.loc["2020-01-15", "cpi_yoy"], nan_ok=True
        ) or not pd.isna(df.loc["2020-02-15", "cpi_yoy"])

    def test_monthly_unemployment_carries_forward(self, tmp_path: Path):
        fred = StubFred(_full_fred_response())
        yahoo = StubYahoo(_full_yahoo_response())
        provider = MacroFactorProvider(fred=fred, yahoo=yahoo, cache_dir=tmp_path)

        df = provider.load_factors(date(2020, 1, 1), date(2020, 3, 31))

        # Unemployment is monthly; after ffill every day in Feb has Jan's value.
        feb_unemp = df.loc["2020-02-10", "unemployment"]
        assert not pd.isna(feb_unemp), "monthly unemployment must ffill to daily"


# ---------------------------------------------------------------------------
# Test 5: Missing factor leaves NaN (no imputation)
# ---------------------------------------------------------------------------


class TestMissingFactor:
    """A series the provider doesn't return stays NaN -- no imputation."""

    def test_missing_factor_leaves_nan(self, tmp_path: Path):
        # Drop VIX from the response -> vix column should be all-NaN.
        responses = _full_fred_response()
        del responses["VIXCLS"]
        fred = StubFred(responses)
        yahoo = StubYahoo(_full_yahoo_response())

        provider = MacroFactorProvider(fred=fred, yahoo=yahoo, cache_dir=tmp_path)
        df = provider.load_factors(date(2020, 1, 1), date(2020, 1, 31))

        assert "vix" in df.columns
        assert df["vix"].isna().all(), "vix must remain NaN -- no imputation"

    def test_other_factors_still_populated(self, tmp_path: Path):
        responses = _full_fred_response()
        del responses["VIXCLS"]
        fred = StubFred(responses)
        yahoo = StubYahoo(_full_yahoo_response())

        provider = MacroFactorProvider(fred=fred, yahoo=yahoo, cache_dir=tmp_path)
        df = provider.load_factors(date(2020, 1, 1), date(2020, 1, 31))

        assert not df["fed_funds"].isna().all(), "fed_funds must still populate"


# ---------------------------------------------------------------------------
# Test 6: Sahm rule -- synthetic unemployment path triggers the flag
# ---------------------------------------------------------------------------


class TestSahmRule:
    """Sahm: 3mo MA of unemployment rises >=0.5pp above its 12mo low."""

    def test_sahm_triggers_after_a_sharp_rise(self, tmp_path: Path):
        # 18 months: flat 5.0% for 12, then 6.5% for 6.
        # 3mo MA at month 14 = (5+5+6.5+6.5+6.5...)[11,12,13] -- let me
        # build a clean series where the Sahm trigger is unambiguous.
        # Months 0..11: unemployment=5.0
        # Month 12 onward: unemployment=6.5
        # At month 14: 3mo MA = (5.0, 6.5, 6.5)/3 = 6.0; 12mo low = 5.0;
        # diff = 1.0 -> Sahm fires.
        unemployment_values = [5.0] * 12 + [6.5] * 8
        dates = pd.date_range("2020-01-01", periods=20, freq="MS")
        unrate_frame = _metis(
            [d.strftime("%Y-%m-%d") for d in dates], unemployment_values, "fred:UNRATE"
        )

        responses = _full_fred_response()
        responses["UNRATE"] = unrate_frame
        fred = StubFred(responses)
        yahoo = StubYahoo(_full_yahoo_response())
        provider = MacroFactorProvider(fred=fred, yahoo=yahoo, cache_dir=tmp_path)

        df = provider.load_factors(date(2020, 1, 1), date(2021, 8, 31))

        sahm = df["sahm_recession"].dropna()
        assert sahm.dtype == bool
        # Sahm should fire sometime between month 13 and month 16.
        # Convertion: index month 1 == 2020-01.
        # Month 14 == 2021-02; month 16 == 2021-04.
        fired_window = sahm.loc["2021-02":"2021-05"]
        assert fired_window.any(), "Sahm should trigger after the unemployment jump"

    def test_sahm_does_not_fire_in_steady_state(self, tmp_path: Path):
        # 24 months of flat 5.0% -- never triggers.
        responses = _full_fred_response()
        provider = MacroFactorProvider(
            fred=StubFred(responses), yahoo=StubYahoo(_full_yahoo_response()),
            cache_dir=tmp_path,
        )
        df = provider.load_factors(date(2020, 1, 1), date(2021, 12, 31))

        sahm = df["sahm_recession"].dropna()
        if len(sahm):
            assert not sahm.any(), "Sahm must not fire when unemployment is flat"


# ---------------------------------------------------------------------------
# Test 7: cpi_yoy computation
# ---------------------------------------------------------------------------


class TestCpiYearOverYear:
    """``cpi_yoy`` is the 12-month pct change of CPIAUCSL level."""

    def test_cpi_yoy_matches_hand_computed_value(self, tmp_path: Path):
        # CPI level: 100.0 + i for i in 0..23 (24 months starting 2019-01).
        # cpi_yoy[2020-01] = (CPI[2020-01] - CPI[2019-01]) / CPI[2019-01]
        #                  = (112 - 100) / 100 = 0.12
        responses = _full_fred_response()
        fred = StubFred(responses)
        yahoo = StubYahoo(_full_yahoo_response())
        provider = MacroFactorProvider(fred=fred, yahoo=yahoo, cache_dir=tmp_path)

        df = provider.load_factors(date(2020, 1, 1), date(2020, 12, 31))

        # Hand-computed YoY at each 2020 publication date.
        # CPI[2019-m] = 100+(m-1); CPI[2020-m] = 100+(12+m-1) = 111+m
        # yoy[m] = (111+m - (99+m)) / (99+m) = 12 / (99+m)
        jan_yoy = df.loc["2020-01-15", "cpi_yoy"]
        assert jan_yoy == pytest.approx(12.0 / 100.0, abs=1e-9)

        feb_yoy = df.loc["2020-02-15", "cpi_yoy"]
        assert feb_yoy == pytest.approx(12.0 / 101.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Test 8: oil_term_structure -- CL1 - CL12
# ---------------------------------------------------------------------------


class TestOilTermStructure:
    """``oil_term_structure = CL1.close - CL12.close`` (front minus back)."""

    def test_term_structure_is_front_minus_back(self, tmp_path: Path):
        from src.research.macro.factors import OIL_BACK_TICKER

        fred = StubFred(_full_fred_response())
        yahoo = StubYahoo(
            {
                "CL=F": _metis(
                    [f"2020-01-{d:02d}" for d in range(1, 32)],
                    [80.0] * 31,
                    "yahoo:CL=F",
                ),
                OIL_BACK_TICKER: _metis(
                    [f"2020-01-{d:02d}" for d in range(1, 32)],
                    [85.0] * 31,
                    f"yahoo:{OIL_BACK_TICKER}",
                ),
            }
        )
        provider = MacroFactorProvider(fred=fred, yahoo=yahoo, cache_dir=tmp_path)
        df = provider.load_factors(date(2020, 1, 1), date(2020, 1, 31))

        ts = df["oil_term_structure"].dropna()
        assert len(ts) > 0
        # 80.0 - 85.0 = -5.0 (contango). Exact arithmetic, no float drift.
        assert (ts == -5.0).all()

    def test_term_structure_is_nan_if_back_missing(self, tmp_path: Path):
        # No CL12 in the yahoo responses -> oil_term_structure all NaN,
        # no exception raised (graceful).
        fred = StubFred(_full_fred_response())
        yahoo = StubYahoo(_full_yahoo_response())
        provider = MacroFactorProvider(fred=fred, yahoo=yahoo, cache_dir=tmp_path)
        df = provider.load_factors(date(2020, 1, 1), date(2020, 1, 31))

        assert df["oil_term_structure"].isna().all()


# ---------------------------------------------------------------------------
# Test 9: compute_zscores
# ---------------------------------------------------------------------------


class TestComputeZscores:
    """``compute_zscores`` produces a rolling (value - mean) / std."""

    def test_zscores_constant_column_is_nan(self, tmp_path: Path):
        # std=0 -> z-score is NaN (avoid division by zero).
        idx = pd.date_range("2020-01-01", periods=200, freq="D")
        factor_df = pd.DataFrame({"x": [1.0] * 200}, index=idx)

        provider = MacroFactorProvider(
            fred=StubFred({}), yahoo=StubYahoo({}), cache_dir=tmp_path
        )
        z = provider.compute_zscores(factor_df, window_days=60)

        assert z["x"].isna().all(), "constant column -> undefined z-score -> NaN"

    def test_zscores_known_series(self, tmp_path: Path):
        # A linear ramp: z-score within a 60-day window is well-defined.
        idx = pd.date_range("2020-01-01", periods=200, freq="D")
        factor_df = pd.DataFrame({"x": np.arange(200, dtype=float)}, index=idx)

        provider = MacroFactorProvider(
            fred=StubFred({}), yahoo=StubYahoo({}), cache_dir=tmp_path
        )
        z = provider.compute_zscores(factor_df, window_days=60)

        # Hand-check: at the last index, the rolling 60-day window covers
        # values 140..199 (mean=169.5, std~=17.6), value=199 -> z ~= 1.67.
        last_z = z["x"].iloc[-1]
        rolling = factor_df["x"].rolling(f"60D")
        expected = (factor_df["x"] - rolling.mean()) / rolling.std()
        assert last_z == pytest.approx(expected.iloc[-1], nan_ok=True, abs=1e-9)

    def test_zscores_preserves_index_and_columns(self, tmp_path: Path):
        idx = pd.date_range("2020-01-01", periods=100, freq="D")
        factor_df = pd.DataFrame(
            {"a": np.arange(100.0), "b": np.arange(100.0) * 2}, index=idx
        )
        provider = MacroFactorProvider(
            fred=StubFred({}), yahoo=StubYahoo({}), cache_dir=tmp_path
        )
        z = provider.compute_zscores(factor_df, window_days=30)

        assert list(z.columns) == ["a", "b"]
        assert z.index.equals(factor_df.index)


# ---------------------------------------------------------------------------
# Test 10 (LIVE): Sahm validation against real FRED UNRATE
# ---------------------------------------------------------------------------


@_SKIP_LIVE
@pytest.mark.live
class TestSahmRuleLiveValidation:
    """Validate Sahm against real FRED UNRATE 2005-2024.

    Acceptance: Sahm fires within 2008-04 to 2009-06 (GFC) AND
    within 2020-04 to 2020-10 (COVID).
    """

    def test_sahm_fires_in_gfc_and_covid(self):
        from src.research.data.fred import FredProvider

        fred = FredProvider()
        unrate = fred.fetch("UNRATE", date(2004, 1, 1), date(2024, 12, 31))

        assert not unrate.empty, "Real FRED UNRATE fetch returned no rows"

        provider = MacroFactorProvider(
            fred=fred, yahoo=StubYahoo({}), cache_dir=Path("data/macro")
        )
        sahm = provider._compute_sahm(
            unrate.set_index("ts")["close"]
        )

        # GFC window: 2008-04 to 2009-06
        gfc_window = sahm.loc["2008-04":"2009-06"]
        assert gfc_window.any(), "Sahm must fire in the GFC window (2008-04 to 2009-06)"

        # COVID window: 2020-04 to 2020-10
        covid_window = sahm.loc["2020-04":"2020-10"]
        assert covid_window.any(), "Sahm must fire in the COVID window (2020-04 to 2020-10)"


# ---------------------------------------------------------------------------
# Contract sanity checks
# ---------------------------------------------------------------------------


class TestFactorColumnsContract:
    """The 12-column canonical contract is locked."""

    EXPECTED = [
        "real_yield_10y",
        "nominal_10y",
        "breakeven_10y",
        "dxy",
        "vix",
        "fed_funds",
        "ism_pmi",
        "unemployment",
        "cpi_yoy",
        "sahm_recession",
        "oil_term_structure",
        "mortgage_30y",
    ]

    def test_factor_columns_constant_matches_spec(self):
        assert list(FACTOR_COLUMNS) == self.EXPECTED
        assert len(FACTOR_COLUMNS) == 12
        assert len(set(FACTOR_COLUMNS)) == 12  # no dups
