"""Tests for ``YahooProvider`` (W2 T7).

Covers the DataProvider-ABC-compliant wrapper around ``yfinance.download``
with parquet caching, TTL expiry, rate-limit retry, NaN-row dropping, and
column mapping (``Close`` -> ``close``, NOT ``Adj Close``).

The ``macro_symbols`` dict is lifted from ``src/api/yahoo_client.py`` (kept
in place for back-compat) into ``YahooProvider.MACRO_SYMBOLS``.
"""

from __future__ import annotations

import os
import time
from datetime import date
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from src.research.data import DataPipelineError, DataProvider
from src.research.data.yahoo import YahooProvider

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _instant_retries(monkeypatch):
    """Make tenacity retries instant.

    ``tenacity.sleep`` resolves ``time.sleep`` at call time, so patching the
    ``time.sleep`` name makes the ``wait_exponential_jitter`` backoff a no-op.
    This keeps the retry-path tests fast (sub-millisecond) while still
    exercising the real retry counter.
    """
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)


def _fake_yf_df(rows: list[tuple]) -> pd.DataFrame:
    """Build a DataFrame shaped like ``yfinance.download(auto_adjust=False)``.

    Each row is ``(date_str, open, high, low, close, adj_close, volume)``.
    Columns are the flat capitalized names yfinance uses when
    ``multi_level_index=False``; the provider also handles the MultiIndex
    shape but the flat shape is what the spec documents and what we assert
    against here.
    """
    idx = pd.DatetimeIndex(pd.to_datetime([r[0] for r in rows]), name="Date")
    return pd.DataFrame(
        {
            "Open": [r[1] for r in rows],
            "High": [r[2] for r in rows],
            "Low": [r[3] for r in rows],
            "Close": [r[4] for r in rows],
            "Adj Close": [r[5] for r in rows],
            "Volume": [r[6] for r in rows],
        },
        index=idx,
    )


def _multiindex_yf_df(rows: list[tuple], ticker: str = "GLD") -> pd.DataFrame:
    """Build a MultiIndex-column DataFrame like ``yfinance.download`` (default).

    yfinance 1.x returns columns ``[("Open", ticker), ("High", ticker), ...]``
    even for a single ticker when ``multi_level_index=True`` (the default).
    """
    flat = _fake_yf_df(rows)
    flat.columns = pd.MultiIndex.from_product([flat.columns, [ticker]])
    return flat


# ---------------------------------------------------------------------------
# Structural / ABC
# ---------------------------------------------------------------------------


def test_yahoo_provider_is_a_data_provider():
    assert issubclass(YahooProvider, DataProvider)


def test_trading_days_per_year_is_252_nyse(tmp_path):
    provider = YahooProvider(cache_dir=tmp_path)
    assert provider.trading_days_per_year == 252


def test_constructor_creates_cache_dir(tmp_path):
    cache = tmp_path / "nested" / "yahoo_cache"
    YahooProvider(cache_dir=cache)
    assert cache.exists() and cache.is_dir()


# ---------------------------------------------------------------------------
# Test 1: happy path -> Metis-contract DataFrame
# ---------------------------------------------------------------------------


def test_fetch_returns_metis_contract_dataframe(tmp_path):
    rows = [
        ("2024-01-02", 190.0, 192.0, 189.0, 191.0, 191.0, 1_000_000),
        ("2024-01-03", 191.0, 193.0, 190.5, 192.5, 192.5, 1_100_000),
        ("2024-01-04", 192.5, 194.0, 192.0, 193.5, 193.5, 900_000),
    ]
    provider = YahooProvider(cache_dir=tmp_path)
    with patch("src.research.data.yahoo.yfinance.download", return_value=_fake_yf_df(rows)):
        df = provider.fetch("GLD", date(2024, 1, 1), date(2024, 1, 5))

    assert list(df.columns) == ["ts", "open", "high", "low", "close", "volume", "source"]
    assert len(df) == 3
    assert (df["source"] == "yahoo:GLD").all()
    assert pd.api.types.is_datetime64_any_dtype(df["ts"])
    # OHLC preserved
    assert df["close"].iloc[0] == 191.0
    assert df["open"].iloc[0] == 190.0


# ---------------------------------------------------------------------------
# Test 8: column mapping -- Close (NOT Adj Close) -> close
# ---------------------------------------------------------------------------


def test_close_column_uses_close_not_adj_close(tmp_path):
    """Decision (documented): the ``close`` field maps to yfinance's ``Close``
    (raw, unadjusted), NOT ``Adj Close``. This matches the existing
    ``YahooFinanceClient.get_macro_data`` behavior which reads ``Close``.
    For dividend-paying equities the caller can request adjusted data
    upstream; GLD (the default ticker) has negligible dividend impact.
    Here ``Close=191`` and ``Adj Close=200`` so we can distinguish them.
    """
    rows = [("2024-01-02", 190.0, 192.0, 189.0, 191.0, 200.0, 1_000_000)]
    provider = YahooProvider(cache_dir=tmp_path)
    with patch("src.research.data.yahoo.yfinance.download", return_value=_fake_yf_df(rows)):
        df = provider.fetch("GLD", date(2024, 1, 1), date(2024, 1, 5))
    assert df["close"].iloc[0] == 191.0
    assert "Adj Close" not in df.columns and "adj close" not in df.columns


def test_fetch_handles_multiindex_columns(tmp_path):
    """yfinance 1.x default returns MultiIndex columns even for one ticker."""
    rows = [
        ("2024-01-02", 190.0, 192.0, 189.0, 191.0, 191.0, 1_000_000),
        ("2024-01-03", 191.0, 193.0, 190.5, 192.5, 192.5, 1_100_000),
    ]
    provider = YahooProvider(cache_dir=tmp_path)
    with patch(
        "src.research.data.yahoo.yfinance.download",
        return_value=_multiindex_yf_df(rows, "GLD"),
    ):
        df = provider.fetch("GLD", date(2024, 1, 1), date(2024, 1, 5))
    assert list(df.columns) == ["ts", "open", "high", "low", "close", "volume", "source"]
    assert len(df) == 2
    assert df["close"].iloc[0] == 191.0


# ---------------------------------------------------------------------------
# Test 2: cache hit -> no yfinance call
# ---------------------------------------------------------------------------


def test_cache_hit_skips_yfinance_call(tmp_path):
    rows = [
        ("2024-01-02", 190.0, 192.0, 189.0, 191.0, 191.0, 1_000_000),
        ("2024-01-03", 191.0, 193.0, 190.5, 192.5, 192.5, 1_100_000),
        ("2024-01-04", 192.5, 194.0, 192.0, 193.5, 193.5, 900_000),
    ]
    provider = YahooProvider(cache_dir=tmp_path, cache_ttl_days=7)
    target = "src.research.data.yahoo.yfinance.download"
    with patch(target, return_value=_fake_yf_df(rows)) as m:
        provider.fetch("GLD", date(2024, 1, 1), date(2024, 1, 5))
        assert m.call_count == 1
        # Second call, same range, within TTL -> served from cache
        df = provider.fetch("GLD", date(2024, 1, 1), date(2024, 1, 5))
        assert m.call_count == 1  # unchanged -> no new network call
    assert len(df) == 3


# ---------------------------------------------------------------------------
# Test 3: cache TTL expired -> refetch
# ---------------------------------------------------------------------------


def test_cache_ttl_expired_triggers_refetch(tmp_path):
    rows = [
        ("2024-01-02", 190.0, 192.0, 189.0, 191.0, 191.0, 1_000_000),
        ("2024-01-03", 191.0, 193.0, 190.5, 192.5, 192.5, 1_100_000),
    ]
    provider = YahooProvider(cache_dir=tmp_path, cache_ttl_days=1)
    target = "src.research.data.yahoo.yfinance.download"
    with patch(target, return_value=_fake_yf_df(rows)):
        provider.fetch("GLD", date(2024, 1, 1), date(2024, 1, 5))

    # Age the cache file beyond the 1-day TTL.
    cache_file = tmp_path / "GLD.parquet"
    assert cache_file.exists()
    old = time.time() - (3 * 86400)
    os.utime(cache_file, (old, old))

    with patch(target, return_value=_fake_yf_df(rows)) as m:
        provider.fetch("GLD", date(2024, 1, 1), date(2024, 1, 5))
        assert m.call_count == 1  # stale cache -> refetched


def test_cache_outside_coverage_triggers_refetch(tmp_path):
    """Requesting a range the cache never fetched -> refetch even if TTL fresh."""
    rows = [
        ("2024-01-02", 190.0, 192.0, 189.0, 191.0, 191.0, 1_000_000),
        ("2024-01-03", 191.0, 193.0, 190.5, 192.5, 192.5, 1_100_000),
    ]
    provider = YahooProvider(cache_dir=tmp_path, cache_ttl_days=30)
    target = "src.research.data.yahoo.yfinance.download"
    with patch(target, return_value=_fake_yf_df(rows)):
        provider.fetch("GLD", date(2024, 1, 1), date(2024, 1, 5))
    # Now ask for a much later window the cache doesn't cover.
    later_rows = [
        ("2024-06-03", 200.0, 202.0, 199.0, 201.0, 201.0, 1_000_000),
    ]
    with patch(target, return_value=_fake_yf_df(later_rows)) as m:
        provider.fetch("GLD", date(2024, 6, 1), date(2024, 6, 7))
        assert m.call_count == 1


# ---------------------------------------------------------------------------
# Test 6: NaN close rows dropped
# ---------------------------------------------------------------------------


def test_nan_close_rows_are_dropped(tmp_path):
    rows = [
        ("2024-01-02", 190.0, 192.0, 189.0, 191.0, 191.0, 1_000_000),
        # holiday / non-trading day -> yfinance returns NaN row
        ("2024-01-03", np.nan, np.nan, np.nan, np.nan, np.nan, 0),
        ("2024-01-04", 192.0, 194.0, 191.0, 193.0, 193.0, 1_000_000),
    ]
    provider = YahooProvider(cache_dir=tmp_path)
    with patch("src.research.data.yahoo.yfinance.download", return_value=_fake_yf_df(rows)):
        df = provider.fetch("GLD", date(2024, 1, 1), date(2024, 1, 5))
    assert len(df) == 2
    assert not df["close"].isna().any()
    # surviving rows are the non-NaN ones
    assert list(df["close"]) == [191.0, 193.0]


# ---------------------------------------------------------------------------
# Test 4: rate-limit retry then success (2 failures then success)
# ---------------------------------------------------------------------------


def test_rate_limit_retry_then_success(tmp_path):
    rows = [("2024-01-02", 190.0, 192.0, 189.0, 191.0, 191.0, 1_000_000)]
    provider = YahooProvider(cache_dir=tmp_path)
    side_effects = [
        RuntimeError("429 Too Many Requests"),
        RuntimeError("rate limited"),
        _fake_yf_df(rows),  # third attempt succeeds
    ]
    target = "src.research.data.yahoo.yfinance.download"
    with patch(target, side_effect=side_effects) as m:
        df = provider.fetch("GLD", date(2024, 1, 1), date(2024, 1, 5))
    assert m.call_count == 3
    assert len(df) == 1
    assert df["close"].iloc[0] == 191.0


# ---------------------------------------------------------------------------
# Test 5: rate-limit exhaustion -> DataPipelineError
# ---------------------------------------------------------------------------


def test_rate_limit_exhaustion_raises_data_pipeline_error(tmp_path):
    provider = YahooProvider(cache_dir=tmp_path)
    target = "src.research.data.yahoo.yfinance.download"
    with (
        patch(target, side_effect=RuntimeError("rate limited")),
        pytest.raises(DataPipelineError, match="Yahoo Finance rate-limited or unreachable"),
    ):
        provider.fetch("GLD", date(2024, 1, 1), date(2024, 1, 5))


def test_data_pipeline_error_message_mentions_fred_alternative(tmp_path):
    """The helpful message must point users to FredProvider for bulk data."""
    provider = YahooProvider(cache_dir=tmp_path)
    target = "src.research.data.yahoo.yfinance.download"
    with patch(target, side_effect=RuntimeError("nope")), pytest.raises(DataPipelineError) as exc_info:
        provider.fetch("CL=F", date(2024, 1, 1), date(2024, 1, 5))
    msg = str(exc_info.value)
    assert "CL=F" in msg
    assert "FredProvider" in msg


# ---------------------------------------------------------------------------
# Test 7: MACRO_SYMBOLS matches src/api/yahoo_client.py
# ---------------------------------------------------------------------------


def test_macro_symbols_matches_yahoo_client():
    """The lifted dict must equal the live dict in yahoo_client.py (back-compat copy).

    We import from the source of truth and compare, so any future edit to
    one without the other is caught.
    """
    from src.api.yahoo_client import YahooFinanceClient

    client = YahooFinanceClient()
    assert client.macro_symbols == YahooProvider.MACRO_SYMBOLS
    assert len(YahooProvider.MACRO_SYMBOLS) == len(client.macro_symbols) > 0


def test_macro_symbols_is_class_level_constant():
    """MACRO_SYMBOLS must be a class attribute, shared across instances."""
    a = YahooProvider.MACRO_SYMBOLS
    b = YahooProvider.MACRO_SYMBOLS
    assert a is b
    assert isinstance(a, dict)


def test_macro_symbols_contains_gld_and_clf():
    """Spot-check the two symbols the plan depends on (T11 oil term structure)."""
    assert YahooProvider.MACRO_SYMBOLS["GC"] == "GLD"
    assert YahooProvider.MACRO_SYMBOLS["CL"] == "CL=F"


# ---------------------------------------------------------------------------
# load_daily dispatch + ticker config
# ---------------------------------------------------------------------------


def test_load_daily_uses_default_ticker_gld(tmp_path):
    rows = [("2024-01-02", 190.0, 192.0, 189.0, 191.0, 191.0, 1_000_000)]
    provider = YahooProvider(cache_dir=tmp_path)  # default ticker = GLD
    with patch("src.research.data.yahoo.yfinance.download", return_value=_fake_yf_df(rows)) as m:
        df = provider.load_daily(date(2024, 1, 1), date(2024, 1, 5))
    assert m.call_count == 1
    assert (df["source"] == "yahoo:GLD").all()


def test_load_daily_uses_custom_ticker(tmp_path):
    rows = [("2024-01-02", 70.0, 71.0, 69.0, 70.5, 70.5, 1_000_000)]
    provider = YahooProvider(cache_dir=tmp_path, ticker="CL=F")
    with patch("src.research.data.yahoo.yfinance.download", return_value=_fake_yf_df(rows)):
        df = provider.load_daily(date(2024, 1, 1), date(2024, 1, 5))
    assert (df["source"] == "yahoo:CL=F").all()


def test_fetch_writes_parquet_cache(tmp_path):
    rows = [("2024-01-02", 190.0, 192.0, 189.0, 191.0, 191.0, 1_000_000)]
    provider = YahooProvider(cache_dir=tmp_path)
    with patch("src.research.data.yahoo.yfinance.download", return_value=_fake_yf_df(rows)):
        provider.fetch("GLD", date(2024, 1, 1), date(2024, 1, 5))
    assert (tmp_path / "GLD.parquet").exists()
