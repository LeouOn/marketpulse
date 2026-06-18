"""Tests for src/research/data/fred.py (FredProvider).

Covers the 9 required scenarios from W2 T6:
  1. Happy path (Metis-contract DataFrame)
  2. Cache hit (no client call)
  3. Cache miss -> fetch + persist
  4. Unsupported series raises ValueError
  5. Missing FRED_API_KEY raises RuntimeError
  6. Stale data raises DataPipelineError
  7. Corrupt cache recovers (delete + refetch)
  8. Retry on transient HTTPError
  9. Negative prices (WTI April 2020) pass through

All tests mock the Fred client; no network access required.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest
import requests

from src.research.data import DataPipelineError
from src.research.data.fred import FredProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_series(
    values: list[float],
    start: str = "2020-01-01",
    freq: str = "D",
) -> pd.Series:
    """Build a fake FRED-style Series (DatetimeIndex, float values)."""
    idx = pd.date_range(start, periods=len(values), freq=freq)
    return pd.Series(values, index=idx, dtype=float)


def _mock_client_returns(series: pd.Series) -> MagicMock:
    """Build a mock Fred client whose get_series returns ``series``."""
    m = MagicMock()
    m.get_series.return_value = series
    return m


def _make_provider(
    cache_dir: Path,
    mock_client: MagicMock | None = None,
    *,
    fast_retry: bool = True,
    **kwargs,
) -> FredProvider:
    """Build a FredProvider with an optional mock client and fast retry config.

    ``fast_retry`` zeroes the retry wait so transient-failure tests stay sub-second.
    """
    provider = FredProvider(api_key="test-key", cache_dir=cache_dir, **kwargs)
    if mock_client is not None:
        provider._client = mock_client
    if fast_retry:
        provider.RETRY_ATTEMPTS = 3
        provider.RETRY_INITIAL_WAIT = 0.0
        provider.RETRY_MAX_WAIT = 0.0
        provider.RETRY_JITTER = 0.0
    return provider


# ---------------------------------------------------------------------------
# Test 1: Happy path
# ---------------------------------------------------------------------------


class TestFredProviderHappyPath:
    """Fetch returns a Metis-contract DataFrame."""

    def test_fetch_returns_correct_columns_and_shape(self, tmp_path: Path):
        fake = _make_series([1.0, 2.0, 3.0, 4.0, 5.0])
        client = _mock_client_returns(fake)
        provider = _make_provider(tmp_path, client)

        df = provider.fetch("DFF", date(2020, 1, 1), date(2020, 1, 5))

        assert list(df.columns) == [
            "ts",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "source",
        ]
        assert len(df) == 5
        # FRED is single-value-per-timestamp -> OHLC all equal.
        assert (df["open"] == df["close"]).all()
        assert (df["high"] == df["close"]).all()
        assert (df["low"] == df["close"]).all()
        # Volume is NaN (FRED has no volume).
        assert df["volume"].isna().all()
        # Source label.
        assert (df["source"] == "fred:DFF").all()
        # ts column is datetime.
        assert pd.api.types.is_datetime64_dtype(df["ts"])


# ---------------------------------------------------------------------------
# Test 2: Cache hit
# ---------------------------------------------------------------------------


class TestFredProviderCacheHit:
    """A cache file covering the query range is served without a client call."""

    def test_cache_hit_skips_client(self, tmp_path: Path):
        dates = pd.date_range("2020-01-01", periods=10, freq="D")
        cached = pd.DataFrame(
            {
                "ts": dates,
                "open": [1.0] * 10,
                "high": [1.0] * 10,
                "low": [1.0] * 10,
                "close": [1.0] * 10,
                "volume": [float("nan")] * 10,
                "source": ["fred:DFF"] * 10,
            }
        )
        cached.to_parquet(tmp_path / "DFF.parquet", index=False)

        client = MagicMock()
        provider = _make_provider(tmp_path, client)

        df = provider.fetch("DFF", date(2020, 1, 1), date(2020, 1, 10))

        client.get_series.assert_not_called()
        assert len(df) == 10


# ---------------------------------------------------------------------------
# Test 3: Cache miss -> fetch + persist
# ---------------------------------------------------------------------------


class TestFredProviderCacheMiss:
    """A cache miss triggers a Fred fetch and writes the result to parquet."""

    def test_cache_miss_fetches_and_writes_cache(self, tmp_path: Path):
        fake = _make_series([10.0] * 5)
        client = _mock_client_returns(fake)
        provider = _make_provider(tmp_path, client)

        df = provider.fetch("DFF", date(2020, 1, 1), date(2020, 1, 5))

        client.get_series.assert_called_once()
        assert (tmp_path / "DFF.parquet").exists()
        assert len(df) == 5
        # Verify cached content is readable.
        cached = pd.read_parquet(tmp_path / "DFF.parquet")
        assert len(cached) == 5


# ---------------------------------------------------------------------------
# Test 4: Unsupported series raises ValueError
# ---------------------------------------------------------------------------


class TestFredProviderUnsupportedSeries:
    """Series IDs outside the whitelist are rejected."""

    def test_unsupported_series_raises_valueerror(self, tmp_path: Path):
        provider = _make_provider(tmp_path)

        with pytest.raises(ValueError, match="Unsupported FRED series"):
            provider.fetch("BOGUS_SERIES", date(2020, 1, 1), date(2020, 1, 5))


# ---------------------------------------------------------------------------
# Test 5: Missing FRED_API_KEY raises RuntimeError
# ---------------------------------------------------------------------------


class TestFredProviderMissingKey:
    """Constructor without a key and without FRED_API_KEY env var fails fast."""

    def test_missing_api_key_raises_runtimeerror(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.delenv("FRED_API_KEY", raising=False)

        with pytest.raises(RuntimeError, match="FRED_API_KEY not set"):
            FredProvider(cache_dir=tmp_path)  # no api_key kwarg


# ---------------------------------------------------------------------------
# Test 6: Stale data raises DataPipelineError
# ---------------------------------------------------------------------------


class TestFredProviderStaleData:
    """A current query whose source data is older than max_staleness_days raises."""

    def test_stale_data_raises(self, tmp_path: Path):
        today = date.today()
        old_end = today - timedelta(days=90)
        old_start = old_end - timedelta(days=4)
        fake = _make_series([1.0] * 5, start=str(old_start))
        client = _mock_client_returns(fake)
        provider = _make_provider(tmp_path, client, max_staleness_days=60)

        with pytest.raises(DataPipelineError, match="stale"):
            provider.fetch("DFF", old_start, today)

    def test_historical_query_skips_staleness_check(self, tmp_path: Path):
        """Historical queries (end well in the past) do NOT fire the staleness guard.

        This is intentional: a 2020 backtest fetches 2020 data and that data is
        legitimately old. The staleness guard only protects *current* queries.
        """
        fake = _make_series([1.0] * 5, start="2020-01-01")
        client = _mock_client_returns(fake)
        provider = _make_provider(tmp_path, client, max_staleness_days=60)

        df = provider.fetch("DFF", date(2020, 1, 1), date(2020, 1, 5))

        assert len(df) == 5  # no DataPipelineError raised


# ---------------------------------------------------------------------------
# Test 7: Corrupt cache recovers
# ---------------------------------------------------------------------------


class TestFredProviderCorruptCache:
    """A corrupt parquet cache file is deleted and the data is refetched."""

    def test_corrupt_cache_recovers(self, tmp_path: Path):
        # Write garbage to the cache file.
        (tmp_path / "DFF.parquet").write_bytes(b"NOT A PARQUET FILE")

        fake = _make_series([1.0] * 5)
        client = _mock_client_returns(fake)
        provider = _make_provider(tmp_path, client)

        df = provider.fetch("DFF", date(2020, 1, 1), date(2020, 1, 5))

        assert len(df) == 5
        client.get_series.assert_called_once()
        # A valid parquet file now exists.
        assert (tmp_path / "DFF.parquet").exists()
        pd.read_parquet(tmp_path / "DFF.parquet")  # must not raise


# ---------------------------------------------------------------------------
# Test 8: Retry on transient HTTPError
# ---------------------------------------------------------------------------


class TestFredProviderRetry:
    """Transient HTTP errors are retried; exhaustion re-raises."""

    def test_retry_on_transient_httperror(self, tmp_path: Path):
        fake = _make_series([1.0] * 3)
        client = MagicMock()
        client.get_series.side_effect = [
            requests.HTTPError("503 Service Unavailable"),
            fake,
        ]
        provider = _make_provider(tmp_path, client)

        df = provider.fetch("DFF", date(2020, 1, 1), date(2020, 1, 3))

        assert len(df) == 3
        assert client.get_series.call_count == 2

    def test_retry_exhaustion_reraises(self, tmp_path: Path):
        client = MagicMock()
        client.get_series.side_effect = requests.HTTPError("503 persistent")
        provider = _make_provider(tmp_path, client)

        with pytest.raises(requests.HTTPError):
            provider.fetch("DFF", date(2020, 1, 1), date(2020, 1, 3))

        assert client.get_series.call_count == provider.RETRY_ATTEMPTS


# ---------------------------------------------------------------------------
# Test 9: Negative prices (WTI April 2020) pass through
# ---------------------------------------------------------------------------


class TestFredProviderNegativePrices:
    """Negative observations (e.g. WTI -$37.63 on 2020-04-20) are preserved."""

    def test_negative_prices_pass_through(self, tmp_path: Path):
        fake = _make_series([-37.63, 10.01, 13.49], start="2020-04-20")
        client = _mock_client_returns(fake)
        provider = _make_provider(tmp_path, client)

        df = provider.fetch("DCOILWTICO", date(2020, 4, 20), date(2020, 4, 22))

        assert df["close"].iloc[0] == pytest.approx(-37.63)
        assert df["open"].iloc[0] == pytest.approx(-37.63)
        assert df["low"].iloc[0] == pytest.approx(-37.63)
        assert df["high"].iloc[0] == pytest.approx(-37.63)
        assert len(df) == 3


# ---------------------------------------------------------------------------
# DataProvider ABC contract
# ---------------------------------------------------------------------------


class TestFredProviderContract:
    """Verify FredProvider satisfies the DataProvider ABC contract."""

    def test_trading_days_per_year(self, tmp_path: Path):
        provider = _make_provider(tmp_path)
        assert provider.trading_days_per_year == 365.25

    def test_load_daily_uses_default_series(self, tmp_path: Path):
        fake = _make_series([100.0] * 3, start="2020-01-01")
        client = _mock_client_returns(fake)
        provider = _make_provider(tmp_path, client)

        df = provider.load_daily(date(2020, 1, 1), date(2020, 1, 3))

        assert (df["source"] == "fred:GOLDAMGBD228NLBM").all()  # default series

    def test_load_daily_uses_configured_series(self, tmp_path: Path):
        fake = _make_series([100.0] * 3, start="2020-01-01")
        client = _mock_client_returns(fake)
        provider = _make_provider(tmp_path, client, series_id="VIXCLS")

        df = provider.load_daily(date(2020, 1, 1), date(2020, 1, 3))

        assert (df["source"] == "fred:VIXCLS").all()


# ---------------------------------------------------------------------------
# Whitelist lockdown (Metis SC4)
# ---------------------------------------------------------------------------


class TestFredProviderWhitelist:
    """The SUPPORTED_SERIES frozenset is locked to the approved IDs.

    Originally 13 series (W2/T6); T11 (W3) added ``ISM_MANUFACTURING``
    because the macro-factor table requires an ``ism_pmi`` primitive.
    """

    EXPECTED = frozenset(
        {
            "GOLDAMGBD228NLBM",
            "GOLDPMGBD228NLBM",
            "DCOILWTICO",
            "CSUSHPINSA",
            "DFII10",
            "DGS10",
            "T10YIE",
            "DTWEXBGS",
            "VIXCLS",
            "DFF",
            "UNRATE",
            "CPIAUCSL",
            "MORTGAGE30US",
            "ISM_MANUFACTURING",  # T11/W3 addition (ism_pmi factor)
        }
    )

    def test_supported_series_is_frozenset(self):
        assert isinstance(FredProvider.SUPPORTED_SERIES, frozenset)

    def test_supported_series_contains_exactly_the_approved_ids(self):
        assert FredProvider.SUPPORTED_SERIES == self.EXPECTED
