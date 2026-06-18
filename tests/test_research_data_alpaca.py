"""TDD coverage for AlpacaProvider (W2 T8).

Thin wrapper around the existing ``src/api/alpaca_client.py:AlpacaClient``
that implements the ``DataProvider`` ABC for equity OHLCV (SPY, QQQ, ...).

All tests are mocked — the real smoke test is run manually and gated on
Alpaca credentials being present in ``config/credentials.yaml``:

    python -c "from src.research.data.alpaca import AlpacaProvider; \
p = AlpacaProvider(); df = p.fetch('SPY', '2024-01-01', '2024-06-01'); \
assert len(df) > 100; print('OK')"

Spec: ``.omo/plans/multi-asset-macro-research-lab.md`` lines 1194-1238.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

from src.research.data import DataProvider
from src.research.data.alpaca import AlpacaProvider


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


def _sample_bars(n: int = 5, start: str = "2024-01-02") -> list[dict]:
    """Return ``n`` sample bar dicts matching ``AlpacaClient.get_bars`` output.

    Default 5 daily bars starting 2024-01-02 (first trading day of 2024),
    spanning through 2024-01-08 (skipping the weekend).
    """
    base = pd.Timestamp(start, tz="UTC")
    bars: list[dict] = []
    for i in range(n):
        ts = (base + pd.Timedelta(days=i)).isoformat()
        bars.append(
            {
                "timestamp": ts,
                "open": 400.0 + i,
                "high": 405.0 + i,
                "low": 399.0 + i,
                "close": 404.0 + i,
                "volume": 1_000_000 + i * 1000,
                "trade_count": 100 + i,
            }
        )
    return bars


# Sentinel so callers can explicitly ask for a None return_value (AlpacaClient
# signals API failure by returning None) without being confused with "default".
_UNSET = object()


def _make_mock_client(bars=_UNSET) -> AsyncMock:
    """Build a mock ``AlpacaClient`` usable as an async context manager.

    ``AlpacaClient`` is an aiohttp async-context-manager: ``__aenter__``
    creates the session (returns self), ``__aexit__`` closes it. The mock
    replicates that shape so ``async with self._client as c: await c.get_bars(...)``
    works inside ``AlpacaProvider._fetch_from_client``.

    ``bars``: the list (or None) returned by ``get_bars``. Defaults to a
    fresh :func:`_sample_bars`. Pass ``bars=None`` explicitly to simulate
    an AlpacaClient API-failure return.
    """
    mock = AsyncMock()
    # async with mock as c: --> c is mock itself
    mock.__aenter__.return_value = mock
    mock.__aexit__.return_value = None
    mock.get_bars.return_value = _sample_bars() if bars is _UNSET else bars
    # Real clients expose .key_id after __init__; tests pass a client so the
    # placeholder-cred guard never trips. Give it a non-placeholder value.
    mock.key_id = "TESTKEY"
    return mock


# ---------------------------------------------------------------------------
# Contract / shape tests
# ---------------------------------------------------------------------------


def test_alpacaprovider_is_a_dataprovider_subclass(tmp_path):
    """AlpacaProvider must inherit from the DataProvider ABC."""
    provider = AlpacaProvider(client=_make_mock_client(), cache_dir=tmp_path)
    assert isinstance(provider, DataProvider)


def test_trading_days_per_year_is_252_nyse(tmp_path):
    """Equities annualise on the 252-day NYSE calendar."""
    provider = AlpacaProvider(client=_make_mock_client(), cache_dir=tmp_path)
    assert provider.trading_days_per_year == 252


def test_default_symbol_is_spy(tmp_path):
    """``load_daily`` dispatches to ``self.symbol`` which defaults to SPY."""
    provider = AlpacaProvider(client=_make_mock_client(), cache_dir=tmp_path)
    assert provider.symbol == "SPY"


# ---------------------------------------------------------------------------
# Test 1: Happy path — fetch returns Metis-contract DataFrame
# ---------------------------------------------------------------------------


def test_fetch_returns_metis_contract_dataframe(tmp_path):
    """Mocked client.get_bars -> fetch() returns a DataFrame with the
    exact Metis columns: ts, open, high, low, close, volume, source."""
    client = _make_mock_client()
    provider = AlpacaProvider(client=client, cache_dir=tmp_path, symbol="SPY")

    df = provider.fetch("SPY", date(2024, 1, 1), date(2024, 1, 31))

    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    # Exact column contract — no extras (trade_count dropped), no missing.
    assert list(df.columns) == ["ts", "open", "high", "low", "close", "volume", "source"]
    # 5 sample bars from _sample_bars().
    assert len(df) == 5
    # source column is namespaced by symbol.
    assert (df["source"] == "alpaca:SPY").all()
    # ts is a datetime (tz-naive UTC, matching the BTC pipeline convention).
    assert pd.api.types.is_datetime64_any_dtype(df["ts"])
    # OHLCV values survive the round-trip from the mocked bar shape.
    assert df["close"].iloc[0] == 404.0
    assert df["volume"].iloc[0] == 1_000_000


# ---------------------------------------------------------------------------
# Test 2: Cache hit — second identical fetch does NOT call the client
# ---------------------------------------------------------------------------


def test_cache_hit_skips_client_call(tmp_path):
    """A second fetch whose range is fully covered by cache must not
    invoke ``client.get_bars`` at all."""
    client = _make_mock_client()
    provider = AlpacaProvider(client=client, cache_dir=tmp_path, symbol="SPY")

    # 5 sample bars span 2024-01-02..2024-01-06; fetch exactly that range so
    # the second identical request is fully covered by the cache.
    provider.fetch("SPY", date(2024, 1, 2), date(2024, 1, 6))
    assert client.get_bars.call_count == 1
    assert (tmp_path / "SPY_1Day.parquet").exists()

    # Second call: range fully covered -> client must NOT be called again.
    client.get_bars.reset_mock()
    df = provider.fetch("SPY", date(2024, 1, 2), date(2024, 1, 6))

    assert client.get_bars.call_count == 0
    assert len(df) == 5  # same data served from cache


# ---------------------------------------------------------------------------
# Test 3: Cache miss triggers a client call
# ---------------------------------------------------------------------------


def test_cache_miss_triggers_client_call(tmp_path):
    """Empty cache -> provider must call client.get_bars to populate it."""
    client = _make_mock_client()
    provider = AlpacaProvider(client=client, cache_dir=tmp_path, symbol="SPY")

    assert not (tmp_path / "SPY_1Day.parquet").exists()

    df = provider.fetch("SPY", date(2024, 1, 1), date(2024, 1, 31))

    assert client.get_bars.call_count == 1
    assert len(df) == 5
    assert (tmp_path / "SPY_1Day.parquet").exists()


# ---------------------------------------------------------------------------
# Test 4: Different timeframe -> different cache file + passed to client
# ---------------------------------------------------------------------------


def test_different_timeframe_uses_separate_cache_file(tmp_path):
    """``timeframe`` is part of the cache key, so 1Hour and 1Day don't
    collide, and the value is forwarded to the wrapped client."""
    client = _make_mock_client()
    provider = AlpacaProvider(client=client, cache_dir=tmp_path, symbol="SPY")

    provider.fetch("SPY", date(2024, 1, 1), date(2024, 1, 31), timeframe="1Hour")

    assert (tmp_path / "SPY_1Hour.parquet").exists()
    assert not (tmp_path / "SPY_1Day.parquet").exists()

    # The timeframe kwarg is forwarded to AlpacaClient.get_bars.
    call_kwargs = client.get_bars.call_args.kwargs
    assert call_kwargs.get("timeframe") == "1Hour"


# ---------------------------------------------------------------------------
# Test 5: Missing creds raises an appropriate error on construction
# ---------------------------------------------------------------------------


def test_missing_creds_raises_on_init(tmp_path):
    """When ``client is None`` and ``AlpacaClient()`` itself raises (e.g.
    creds missing / misconfigured), the error must propagate out of
    ``AlpacaProvider.__init__`` — not be swallowed."""
    with patch("src.research.data.alpaca.AlpacaClient") as mock_cls:
        mock_cls.side_effect = RuntimeError("Alpaca credentials not configured")
        with pytest.raises(RuntimeError, match="Alpaca credentials not configured"):
            AlpacaProvider(client=None, cache_dir=tmp_path)


def test_placeholder_creds_raise_clear_error(tmp_path):
    """Real-world guard: if the client was constructed with the literal
    placeholder key_id from ``config.example.yaml``, fail fast with a
    message that names the config file (mirrors the T1 FRED pattern)."""
    client = _make_mock_client()
    client.key_id = "your_alpaca_key_here"  # exact placeholder
    with pytest.raises(RuntimeError, match="(?i)alpaca"):
        AlpacaProvider(client=client, cache_dir=tmp_path)


# ---------------------------------------------------------------------------
# load_daily dispatch + partial-cache behaviour
# ---------------------------------------------------------------------------


def test_load_daily_dispatches_to_configured_symbol(tmp_path):
    """``load_daily(start, end)`` calls ``fetch(self.symbol, ...)`` with
    the 1Day timeframe — so a provider built with symbol="QQQ" fetches
    QQQ, not SPY."""
    client = _make_mock_client()
    provider = AlpacaProvider(client=client, cache_dir=tmp_path, symbol="QQQ")

    df = provider.load_daily(date(2024, 1, 1), date(2024, 1, 31))

    assert (df["source"] == "alpaca:QQQ").all()
    call_kwargs = client.get_bars.call_args.kwargs
    assert call_kwargs.get("symbol") == "QQQ"
    assert call_kwargs.get("timeframe") == "1Day"


def test_partial_cache_range_triggers_refetch_and_merges(tmp_path):
    """If the cache covers part of the requested range but not all of it,
    the provider refetches and merges new data into the existing cache
    (no rows lost, no duplicates on ts)."""
    # Seed the cache with the first 2 days only.
    seed_bars = _sample_bars(n=2, start="2024-01-02")
    seed_df = AlpacaProvider(client=_make_mock_client(seed_bars), cache_dir=tmp_path).fetch(
        "SPY", date(2024, 1, 1), date(2024, 1, 3)
    )
    assert len(seed_df) == 2

    # Now build a fresh provider whose client returns the full 5 bars.
    client = _make_mock_client(_sample_bars(n=5, start="2024-01-02"))
    provider = AlpacaProvider(client=client, cache_dir=tmp_path, symbol="SPY")

    # Request the wider range — cache (2 rows) doesn't cover through Jan 31,
    # so the client must be called and the result merged with the cache.
    df = provider.fetch("SPY", date(2024, 1, 1), date(2024, 1, 31))

    assert client.get_bars.call_count == 1
    assert len(df) == 5  # merged: no dupes
    # No duplicate timestamps after merge.
    assert df["ts"].is_unique


def test_fetch_returns_empty_when_client_returns_none(tmp_path):
    """When the wrapped client returns ``None`` (AlpacaClient signals API
    failure this way) and there's no cache, ``fetch`` returns an empty
    Metis-shaped DataFrame rather than raising."""
    client = _make_mock_client(bars=None)
    provider = AlpacaProvider(client=client, cache_dir=tmp_path, symbol="SPY")

    df = provider.fetch("SPY", date(2024, 1, 1), date(2024, 1, 31))

    assert df.empty
    assert list(df.columns) == ["ts", "open", "high", "low", "close", "volume", "source"]
    # A failed fetch must NOT poison the cache with an empty file.
    assert not (tmp_path / "SPY_1Day.parquet").exists()


# ---------------------------------------------------------------------------
# Smoke-test skip guard (the real network test runs manually, not in CI)
# ---------------------------------------------------------------------------


def test_alpacaprovider_module_imports_cleanly():
    """Bare import smoke test — catches typo / circular-import regressions."""
    from src.research.data.alpaca import AlpacaProvider  # noqa: F401

    assert AlpacaProvider.__name__ == "AlpacaProvider"
