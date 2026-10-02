"""Edge-case offline tests for ``src/api/market_data_collector.py``.

The existing tests (test_marketpulse/test_deps_state/test_market_macro_provenance)
only touch the collector through full mocks; this file exercises the module's
own logic with fake clients swapped into its attributes: failed per-symbol
fetches, None/NaN/zero prices, partial data, the data_source key, cache
staleness, and initialize/collect idempotency. No sockets anywhere; every
fake returns immediately.
"""

from __future__ import annotations

import math
from datetime import datetime

import src.api.market_data_collector as mdc
from src.api.market_data_collector import MarketDataCollector, get_collector

# ---------------------------------------------------------------------------
# Fakes for the module's own client attributes
# ---------------------------------------------------------------------------


class _FakeAlpaca:
    def __init__(self, market_data=None, bars=None, error=None, available=True):
        self._market_data = market_data
        self._bars = bars
        self._error = error
        self._available = available
        self.calls: list = []

    async def is_available(self):
        return self._available

    async def get_market_data(self, symbols):
        self.calls.append(("market_data", symbols))
        if self._error:
            raise self._error
        return self._market_data

    async def get_bars(self, symbol, timeframe, limit=None):
        self.calls.append(("bars", symbol, timeframe, limit))
        if self._error:
            raise self._error
        return self._bars


class _FakeRithmic:
    def __init__(self, futures=None, ohlc=None, error=None, available=True):
        self._futures = futures
        self._ohlc = ohlc
        self._error = error
        self._available = available
        self.calls: list = []

    async def is_available(self):
        return self._available

    async def get_futures_data(self, symbols):
        self.calls.append(("futures", symbols))
        if self._error:
            raise self._error
        return self._futures

    async def get_ohlc(self, symbol, timeframe, limit=None):
        self.calls.append(("ohlc", symbol, timeframe, limit))
        if self._error:
            raise self._error
        return self._ohlc


class _FakeCoinbase:
    def __init__(self, market_data=None, candles=None, error=None, available=True):
        self._market_data = market_data
        self._candles = candles
        self._error = error
        self._available = available
        self.calls: list = []

    async def is_available(self):
        return self._available

    async def get_market_data(self, symbols):
        self.calls.append(("market_data", symbols))
        if self._error:
            raise self._error
        return self._market_data

    async def get_candles(self, symbol, granularity=3600, start=None, end=None):
        # Real CoinbaseClient.get_candles signature: no limit kwarg.
        self.calls.append(("candles", symbol, granularity))
        if self._error:
            raise self._error
        return self._candles


class _FakeYahoo:
    def __init__(self, internals=None, error=None):
        self._internals = internals
        self._error = error
        self.calls: list = []

    def get_market_internals(self, symbols):
        self.calls.append(("internals", symbols))
        if self._error:
            raise self._error
        return self._internals


class _FakeCache:
    def __init__(self, cached=None, ohlc_cached=None):
        self._cached = cached
        self._ohlc_cached = ohlc_cached
        self.gets: list = []
        self.sets: list = []
        self.ohlc_gets: list = []
        self.ohlc_sets: list = []
        self.is_connected = True

    async def get(self, key):
        self.gets.append(key)
        return self._cached

    async def set(self, key, value, ttl_seconds=None):
        self.sets.append((key, value, ttl_seconds))

    async def get_ohlc(self, symbol, timeframe):
        self.ohlc_gets.append((symbol, timeframe))
        return self._ohlc_cached

    async def set_ohlc(self, symbol, timeframe, data):
        self.ohlc_sets.append((symbol, timeframe, data))


def _collector(**clients) -> MarketDataCollector:
    c = MarketDataCollector()
    c.alpaca = clients.get("alpaca")
    c.rithmic = clients.get("rithmic")
    c.coinbase = clients.get("coinbase")
    c.yahoo = clients.get("yahoo")
    c.cache = clients.get("cache")
    return c


# ---------------------------------------------------------------------------
# get_all_market_data: sourcing, partial data, data_source key
# ---------------------------------------------------------------------------


async def test_all_sources_contribute_and_data_source_lists_them():
    alpaca = _FakeAlpaca(market_data={"SPY": {"price": 500.0}, "QQQ": {"price": 480.0}, "IWM": {"price": 210.0}})
    rithmic = _FakeRithmic(futures={"NQ=F": {"price": 21000.0}})
    coinbase = _FakeCoinbase(market_data={"BTC-USD": {"price": 45000.0}, "ETH-USD": {"price": 3000.0}})
    yahoo = _FakeYahoo()
    collector = _collector(alpaca=alpaca, rithmic=rithmic, coinbase=coinbase, yahoo=yahoo)

    internals = await collector.get_all_market_data(use_cache=False)

    assert internals["SPY"]["price"] == 500.0
    assert internals["NQ=F"]["price"] == 21000.0
    assert internals["BTC-USD"]["price"] == 45000.0
    assert internals["data_source"] == "alpaca,rithmic,coinbase"
    # Yahoo is NOT consulted when externals deliver.
    assert yahoo.calls == []
    datetime.fromisoformat(internals["timestamp"])


async def test_partial_external_data_triggers_yahoo_fallback():
    alpaca = _FakeAlpaca(market_data={"SPY": {"price": 500.0}})  # only 1 symbol
    yahoo = _FakeYahoo(internals={"SPY": {"price": 501.0}, "QQQ": {"price": 480.0}, "IWM": {"price": 210.0}})
    collector = _collector(alpaca=alpaca, yahoo=yahoo)

    internals = await collector.get_all_market_data(use_cache=False)

    assert internals["data_source"] == "alpaca,yahoo"
    assert internals["QQQ"]["price"] == 480.0  # yahoo filled the gap
    assert yahoo.calls == [("internals", collector.all_symbols)]


async def test_failed_source_is_skipped_and_yahoo_used(monkeypatch):
    monkeypatch.delenv("MARKETPULSE_ALLOW_MOCK", raising=False)
    alpaca = _FakeAlpaca(error=OSError("alpaca down (fake)"))
    yahoo = _FakeYahoo(internals={"SPY": {"price": 500.0}, "QQQ": {"price": 1.0}, "IWM": {"price": 2.0}})
    collector = _collector(alpaca=alpaca, yahoo=yahoo)

    internals = await collector.get_all_market_data(use_cache=False)

    assert internals["data_source"] == "yahoo"
    assert internals["SPY"]["price"] == 500.0


async def test_all_sources_failed_without_mock_returns_none_sentinel(monkeypatch):
    monkeypatch.delenv("MARKETPULSE_ALLOW_MOCK", raising=False)
    collector = _collector()  # no clients at all, no yahoo

    internals = await collector.get_all_market_data(use_cache=False)

    assert internals["data_source"] == "none"
    assert "timestamp" in internals
    # No symbol keys leaked in.
    assert set(internals.keys()) == {"data_source", "timestamp"}


async def test_all_sources_failed_with_mock_opt_in_uses_mock(monkeypatch):
    monkeypatch.setenv("MARKETPULSE_ALLOW_MOCK", "1")
    collector = _collector()

    internals = await collector.get_all_market_data(use_cache=False)

    assert internals["data_source"] == "mock"
    assert len(internals) > 2  # actual mock symbol data present


async def test_none_and_nan_priced_symbols_flow_through(monkeypatch):
    monkeypatch.delenv("MARKETPULSE_ALLOW_MOCK", raising=False)
    alpaca = _FakeAlpaca(
        market_data={"SPY": {"price": None}, "QQQ": {"price": math.nan}, "IWM": {"price": 0.0}, "BAD": None}
    )
    yahoo = _FakeYahoo()
    collector = _collector(alpaca=alpaca, yahoo=yahoo)

    internals = await collector.get_all_market_data(use_cache=False)

    # Four entries is >= 3, so no yahoo fallback fires: the collector passes
    # provider dicts through verbatim (filtering is the consumer's job).
    assert internals["data_source"] == "alpaca"
    assert internals["SPY"]["price"] is None
    assert math.isnan(internals["QQQ"]["price"])
    assert internals["IWM"]["price"] == 0.0
    assert internals["BAD"] is None
    assert yahoo.calls == []


# ---------------------------------------------------------------------------
# get_all_market_data: cache behaviour
# ---------------------------------------------------------------------------


async def test_cache_hit_short_circuits_all_sources():
    alpaca = _FakeAlpaca(market_data={"SPY": {"price": 1.0}})
    cache = _FakeCache(cached={"SPY": {"price": 999.0}, "data_source": "cached", "timestamp": "t"})
    collector = _collector(alpaca=alpaca, cache=cache)

    internals = await collector.get_all_market_data(use_cache=True)

    assert internals == {"SPY": {"price": 999.0}, "data_source": "cached", "timestamp": "t"}
    assert cache.gets == ["all_market_data"]
    assert alpaca.calls == []  # never touched the source


async def test_cache_miss_fetches_and_writes_with_ttl_30():
    alpaca = _FakeAlpaca(market_data={"SPY": {"price": 1.0}, "QQQ": {"price": 2.0}, "IWM": {"price": 3.0}})
    cache = _FakeCache()
    collector = _collector(alpaca=alpaca, cache=cache)

    await collector.get_all_market_data(use_cache=True)

    ((key, value, ttl),) = cache.sets
    assert key == "all_market_data"
    assert ttl == 30
    assert value["data_source"] == "alpaca"


async def test_failed_fetch_sentinel_is_also_cached(monkeypatch):
    """Current behaviour (negative caching, reported in cycle report): the
    data_source='none' envelope is cached for 30s like any result."""
    monkeypatch.delenv("MARKETPULSE_ALLOW_MOCK", raising=False)
    cache = _FakeCache()
    collector = _collector(cache=cache)

    await collector.get_all_market_data(use_cache=True)

    assert cache.sets and cache.sets[0][1]["data_source"] == "none"


# ---------------------------------------------------------------------------
# get_ohlc_data: routing + failure paths
# ---------------------------------------------------------------------------


async def test_ohlc_stocks_route_to_alpaca_and_cache():
    alpaca = _FakeAlpaca(bars=[{"close": 100.0}])
    cache = _FakeCache()
    collector = _collector(alpaca=alpaca, cache=cache)

    bars = await collector.get_ohlc_data("SPY", "1Min", use_cache=True)

    assert bars == [{"close": 100.0}]
    assert alpaca.calls == [("bars", "SPY", "1Min", 100)]
    assert cache.ohlc_sets == [("SPY", "1Min", bars)]


async def test_ohlc_cache_hit_skips_sources():
    alpaca = _FakeAlpaca(bars=[{"close": 1.0}])
    cache = _FakeCache(ohlc_cached=[{"close": 42.0}])
    collector = _collector(alpaca=alpaca, cache=cache)

    bars = await collector.get_ohlc_data("SPY", "1Min", use_cache=True)

    assert bars == [{"close": 42.0}]
    assert alpaca.calls == []


async def test_ohlc_futures_symbol_translated_for_rithmic():
    rithmic = _FakeRithmic(ohlc=[{"close": 21000.0}])
    collector = _collector(rithmic=rithmic)

    bars = await collector.get_ohlc_data("NQ=F", "1Min", use_cache=False)

    assert bars == [{"close": 21000.0}]
    assert rithmic.calls == [("ohlc", "NQ", "1Min", 100)]


async def test_ohlc_crypto_routes_to_coinbase():
    coinbase = _FakeCoinbase(candles=[{"close": 45000.0}])
    collector = _collector(coinbase=coinbase)

    bars = await collector.get_ohlc_data("BTC-USD", "1Min", use_cache=False)

    assert bars == [{"close": 45000.0}]
    assert coinbase.calls == [("candles", "BTC-USD", 60)]


async def test_ohlc_unknown_symbol_or_missing_client_returns_none():
    collector = _collector(alpaca=_FakeAlpaca(bars=[{"close": 1.0}]))

    assert await collector.get_ohlc_data("UNKNOWN", use_cache=False) is None

    empty = _collector()
    assert await empty.get_ohlc_data("SPY", use_cache=False) is None


async def test_ohlc_failing_source_returns_none_not_an_exception():
    """A raising client used to propagate out of get_ohlc_data; the method's
    contract (list | None) demands degradation to None."""
    collector = _collector(alpaca=_FakeAlpaca(error=OSError("alpaca bars failed (fake)")))

    assert await collector.get_ohlc_data("SPY", use_cache=False) is None


# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------


async def test_health_check_reports_all_down_when_uninitialized():
    collector = _collector()

    health = await collector.health_check()

    assert health == {"alpaca": False, "rithmic": False, "coinbase": False, "cache": False}


async def test_health_check_reports_per_source_availability():
    collector = _collector(
        alpaca=_FakeAlpaca(available=True),
        rithmic=_FakeRithmic(available=False),
        coinbase=_FakeCoinbase(available=True),
        cache=_FakeCache(),
    )

    health = await collector.health_check()

    assert health == {"alpaca": True, "rithmic": False, "coinbase": True, "cache": True}


async def test_health_check_survives_a_raising_source():
    """One broken source must not crash the whole health report."""

    class _Exploding:
        async def is_available(self):
            raise OSError("cannot reach (fake)")

    collector = _collector(alpaca=_Exploding(), coinbase=_FakeCoinbase(available=True))

    health = await collector.health_check()

    assert health["alpaca"] is False
    assert health["coinbase"] is True


# ---------------------------------------------------------------------------
# initialize + singleton
# ---------------------------------------------------------------------------


async def test_initialize_survives_total_failure_and_is_idempotent(monkeypatch):
    init_calls = {"cache": 0, "alpaca": 0, "rithmic": 0, "coinbase": 0}

    async def _failing_cache():
        init_calls["cache"] += 1
        raise OSError("no redis (fake)")

    class _Unavailable:
        def __init__(self):
            init_calls.setdefault("n", 0)

        async def is_available(self):
            return False

    async def _alpaca_factory():
        init_calls["alpaca"] += 1
        return _Unavailable()

    async def _rithmic_factory():
        init_calls["rithmic"] += 1
        return _Unavailable()

    async def _coinbase_factory():
        init_calls["coinbase"] += 1
        return _Unavailable()

    monkeypatch.setattr(mdc, "get_cache", _failing_cache)
    monkeypatch.setattr(mdc, "get_alpaca_client", _alpaca_factory)
    monkeypatch.setattr(mdc, "get_rithmic_client", _rithmic_factory)
    monkeypatch.setattr(mdc, "get_coinbase_client", _coinbase_factory)

    collector = MarketDataCollector()

    assert await collector.initialize() is True
    assert collector.alpaca is None and collector.rithmic is None
    assert collector.coinbase is None and collector.cache is None
    assert collector.yahoo is not None  # yahoo has no availability gate

    # Second run: same outcome, every factory consulted again.
    assert await collector.initialize() is True
    assert init_counts_all(init_calls, times=2)


def init_counts_all(calls, times):
    return (
        calls["cache"] == times
        and calls["alpaca"] == times
        and calls["rithmic"] == times
        and calls["coinbase"] == times
    )


async def test_get_collector_memoizes_the_singleton(monkeypatch):
    monkeypatch.setattr(mdc, "_collector_instance", None)
    made = []

    async def _fake_initialize(self):
        made.append(self)
        return True

    monkeypatch.setattr(MarketDataCollector, "initialize", _fake_initialize)

    first = await get_collector()
    second = await get_collector()

    assert first is second
    assert made == [first]  # initialize ran exactly once

    monkeypatch.setattr(mdc, "_collector_instance", None)
