"""Offline coverage for macro symbol mapping, 52-week consistency, and mock flagging.

Live Yahoo check is ``@pytest.mark.live`` and skipped unless ``RUN_LIVE_TESTS=1``.
"""

from __future__ import annotations

import os

import pandas as pd
import pytest

LAST_PRICES = {
    "DX-Y.NYB": 101.2,
    "GC=F": 4152.1,
    "^TNX": 5.24,
    "CL=F": 92.93,
    "BTC-USD": 94000.0,
}

RANGES = {
    "DX-Y.NYB": {"fiftyTwoWeekHigh": 101.8, "fiftyTwoWeekLow": 95.55, "regularMarketPrice": 101.2},
    "GC=F": {"fiftyTwoWeekHigh": 5586.2, "fiftyTwoWeekLow": 3785.5, "regularMarketPrice": 4152.1},
    "^TNX": {"fiftyTwoWeekHigh": 5.274, "fiftyTwoWeekLow": 3.947, "regularMarketPrice": 5.24},
    "BTC-USD": {"fiftyTwoWeekHigh": 120000.0, "fiftyTwoWeekLow": 50000.0, "regularMarketPrice": 94000.0},
}


class _FakeTicker:
    def __init__(self, symbol: str):
        self.symbol = symbol

    @property
    def info(self) -> dict:
        base = RANGES.get(
            self.symbol,
            {"fiftyTwoWeekHigh": 11.0, "fiftyTwoWeekLow": 9.0, "regularMarketPrice": 10.0},
        )
        return dict(base)


class _YahooFake:
    def __init__(self):
        self.empty = False
        self.download_calls: list = []
        self.ticker_calls: list[str] = []

    def reset(self) -> None:
        self.empty = False
        self.download_calls.clear()
        self.ticker_calls.clear()

    def download(self, tickers, **kwargs):
        self.download_calls.append(tickers)
        if self.empty:
            return pd.DataFrame()
        if isinstance(tickers, str):
            return _flat_frame(tickers)
        symbols = list(tickers)
        if len(symbols) == 1:
            return _flat_frame(symbols[0])
        return _multi_frame(symbols)

    def ticker(self, symbol: str) -> _FakeTicker:
        self.ticker_calls.append(symbol)
        return _FakeTicker(symbol)


_FAKE = _YahooFake()


def _flat_frame(symbol: str) -> pd.DataFrame:
    last = LAST_PRICES.get(symbol, 10.0)
    idx = pd.to_datetime(["2026-09-25", "2026-09-26"])
    return pd.DataFrame(
        {
            "Open": [last - 1, last],
            "High": [last - 1, last],
            "Low": [last - 1, last],
            "Close": [last - 1, last],
            "Volume": [1000, 1100],
        },
        index=idx,
    )


def _multi_frame(symbols: list[str]) -> pd.DataFrame:
    idx = pd.to_datetime(["2026-09-25", "2026-09-26"])
    columns = pd.MultiIndex.from_tuples(
        (field, symbol) for field in ("Open", "High", "Low", "Close", "Volume") for symbol in symbols
    )
    frame = pd.DataFrame(index=idx, columns=columns, dtype=float)
    for symbol in symbols:
        last = LAST_PRICES.get(symbol, 10.0)
        for field in ("Open", "High", "Low", "Close"):
            frame[(field, symbol)] = [last - 1, last]
        frame[("Volume", symbol)] = [1000, 1100]
    return frame


@pytest.fixture
def yahoo_fake(monkeypatch):
    _FAKE.reset()
    monkeypatch.setattr("yfinance.download", _FAKE.download)
    monkeypatch.setattr("yfinance.Ticker", _FAKE.ticker)
    monkeypatch.delenv("MARKETPULSE_ALLOW_MOCK", raising=False)
    return _FAKE


def test_macro_map_uses_listed_instruments_in_both_places(yahoo_fake):
    from src.api.mock_market import FALLBACK_MACRO, macro_yahoo_map
    from src.api.yahoo_client import MACRO_CATALOG, YahooFinanceClient

    client = YahooFinanceClient()
    assert client.macro_symbols == {name: meta["symbol"] for name, meta in MACRO_CATALOG.items()}
    assert client.macro_symbols == macro_yahoo_map()
    assert set(FALLBACK_MACRO) == set(MACRO_CATALOG)
    assert client.macro_symbols["DXY"] == "DX-Y.NYB"
    assert client.macro_symbols["GC"] == "GC=F"
    assert client.macro_symbols["TNX"] == "^TNX"
    assert client.macro_symbols["CL"] == "CL=F"
    assert "UUP" not in client.macro_symbols.values()
    assert "GLD" not in client.macro_symbols.values()
    assert MACRO_CATALOG["DXY"]["is_proxy"] is False
    assert MACRO_CATALOG["GC"]["is_proxy"] is False


def test_get_bars_downloads_the_mapped_symbol(yahoo_fake):
    from src.api.yahoo_client import YahooFinanceClient

    client = YahooFinanceClient()
    dxy = client.get_bars("DXY", period="5d", interval="1d")
    gold = client.get_bars("GC", period="5d", interval="1d")

    assert dxy is not None and gold is not None
    assert yahoo_fake.download_calls[0] == "DX-Y.NYB"
    assert yahoo_fake.download_calls[1] == "GC=F"
    assert float(dxy["close"].iloc[-1]) == 101.2
    assert float(gold["close"].iloc[-1]) == 4152.1


@pytest.mark.asyncio
async def test_macro_endpoint_provenance_and_52w_use_the_same_symbol(yahoo_fake):
    from src.api.routers.market import get_macro_data

    response = await get_macro_data()

    assert response.success is True
    data = response.data
    dxy = data["DXY"]
    gold = data["GC"]

    assert dxy["price"] == 101.2
    assert dxy["symbol"] == "DX-Y.NYB"
    assert dxy["instrument"] == "ICE US Dollar Index"
    assert dxy["is_proxy"] is False
    assert dxy["source"] == "yahoo"
    assert dxy["high_52w"] == 101.8
    assert dxy["low_52w"] == 95.55
    assert dxy["range_symbol"] == "DX-Y.NYB"
    assert dxy["pct_from_52w_high"] == round(((101.2 - 101.8) / 101.8) * 100, 2)

    assert gold["price"] == 4152.1
    assert gold["symbol"] == "GC=F"
    assert gold["is_proxy"] is False
    assert gold["source"] == "yahoo"
    assert gold["high_52w"] == 5586.2
    assert gold["range_symbol"] == "GC=F"

    assert "DX-Y.NYB" in yahoo_fake.ticker_calls
    assert "GC=F" in yahoo_fake.ticker_calls
    assert "UUP" not in yahoo_fake.ticker_calls
    assert "GLD" not in yahoo_fake.ticker_calls

    assert data["market_session_basis"] == "local_clock"
    assert data["market_session"] in {"US Regular", "US After Hours", "Asian Session", "European Session"}
    assert data["field_sources"] == {"market_session": "derived"}
    assert "economic_sentiment" not in data
    assert "risk_appetite" not in data
    assert "sector_performance" not in data
    assert data.get("source") != "mock"


@pytest.mark.asyncio
async def test_fabricated_macro_fields_appear_only_when_mock_is_allowed(yahoo_fake, monkeypatch):
    from src.api.routers.market import get_macro_data

    monkeypatch.setenv("MARKETPULSE_ALLOW_MOCK", "1")
    response = await get_macro_data()

    assert response.success is True
    data = response.data
    assert data["DXY"]["source"] == "yahoo"
    assert data["DXY"]["symbol"] == "DX-Y.NYB"
    assert data["field_sources"]["economic_sentiment"] == "mock"
    assert data["field_sources"]["risk_appetite"] == "mock"
    assert data["field_sources"]["sector_performance"] == "mock"
    assert isinstance(data["economic_sentiment"], str)
    assert isinstance(data["sector_performance"], dict)
    assert all(isinstance(value, float) for value in data["sector_performance"].values())


@pytest.mark.asyncio
async def test_yahoo_outage_omits_mock_unless_opted_in(yahoo_fake, monkeypatch):
    from src.api.routers.market import get_macro_data

    yahoo_fake.empty = True
    blocked = await get_macro_data()
    assert blocked.success is False
    assert blocked.data is None
    assert "MARKETPULSE_ALLOW_MOCK" in (blocked.error or "")

    monkeypatch.setenv("MARKETPULSE_ALLOW_MOCK", "1")
    allowed = await get_macro_data()
    assert allowed.success is True
    assert allowed.data["source"] == "mock"
    assert allowed.data["DXY"]["source"] == "mock"
    assert allowed.data["DXY"]["symbol"] == "DX-Y.NYB"
    assert allowed.data["GC"]["symbol"] == "GC=F"
    assert allowed.data["field_sources"]["sector_performance"] == "mock"


def test_breadth_honors_an_explicit_mock_source():
    from src.api.routers.market import _annotate_breadth

    flagged = _annotate_breadth(
        {"source": "mock", "nyse_advancing": 1, "nyse_declining": 0, "nyse_unchanged": 0}
    )
    assert flagged["source"] == "mock"
    assert flagged["classification"] == "mock"


@pytest.mark.asyncio
async def test_collector_skips_mock_internals_unless_opted_in(monkeypatch):
    monkeypatch.delenv("MARKETPULSE_ALLOW_MOCK", raising=False)
    monkeypatch.setattr("yfinance.download", lambda *args, **kwargs: pd.DataFrame())

    class _EmptyFeed:
        async def get_all_market_data(self, use_cache=True):
            return {}

    from src.data.market_collector import MarketPulseCollector

    collector = MarketPulseCollector.__new__(MarketPulseCollector)
    collector.collector = _EmptyFeed()
    collector.symbols = {"SPY": "SPY", "QQQ": "QQQ", "VIX": "^VIX"}
    collector.db_manager = None

    with pytest.raises(ValueError, match="MARKETPULSE_ALLOW_MOCK"):
        await collector.collect_market_internals()

    monkeypatch.setenv("MARKETPULSE_ALLOW_MOCK", "1")

    async def _labelled_mock():
        quote = {"price": 500.0, "change": 1.0, "change_pct": 0.2, "volume": 1_000, "data_age_seconds": 5}
        return {
            "spy": dict(quote),
            "qqq": dict(quote, price=450.0),
            "vix": dict(quote, price=16.0, volume=0),
        }

    import src.api.mock_market as mock_market

    monkeypatch.setattr(mock_market.mock_provider, "get_market_internals", _labelled_mock)
    result = await collector.collect_market_internals()
    assert result["data_source"] == "mock"
    assert result["synthetic"] is True
    assert result["spy"]["price"] == 500.0


def test_freshness_uses_spy_age_when_the_collector_dropped_the_flag():
    from src.api.routers.market import _freshness_status

    assert _freshness_status({"spy": {"data_age_seconds": 30}}) == "fresh"
    assert _freshness_status({"spy": {"data_age_seconds": 901}}) == "stale"
    assert _freshness_status({"spy": {}}) == "unknown"
    assert _freshness_status({"freshness_status": "stale", "spy": {"data_age_seconds": 5}}) == "stale"


@pytest.mark.asyncio
async def test_data_quality_does_not_invent_a_running_scheduler(monkeypatch):
    from src.api.yahoo_client import YahooFinanceClient

    async def no_cache(self):
        return None

    monkeypatch.setattr(YahooFinanceClient, "_get_cache", no_cache)
    monkeypatch.setattr(
        YahooFinanceClient,
        "get_single_symbol_data",
        lambda self, symbol: {"price": 101.2, "timestamp": "2026-09-28T13:00:00"} if symbol == "DX-Y.NYB" else None,
    )

    from src.api.routers.data_quality import get_data_quality_summary, get_symbol_data_quality

    summary = await get_data_quality_summary()
    assert summary.success is True
    assert summary.data["scheduler_running"] is False
    assert "MarketScheduler" in summary.data["scheduler_reason"]
    assert summary.data["cache_status"] == "redis_unavailable"

    dxy = await get_symbol_data_quality("DXY")
    assert dxy.data["yahoo_symbol"] == "DX-Y.NYB"
    assert dxy.data["has_data"] is True
    assert dxy.data["source"] == "yahoo"
    assert dxy.data["bar_timestamp"] == "2026-09-28T13:00:00"

    missing = await get_symbol_data_quality("NOPE")
    assert missing.data["has_data"] is False
    assert missing.data["source"] == "unavailable"
    assert missing.data["bar_timestamp"] is None


def test_breadth_sample_is_labelled_and_hardcoded_fallback_is_mock():
    from src.api.routers.market import _annotate_breadth, _breadth_mock_blocked, _ohlc_fetch_symbol

    derived = _annotate_breadth({"nyse_advancing": 6, "nyse_declining": 3, "nyse_unchanged": 1, "tick_value": 2})
    assert derived["classification"] == "derived"
    assert derived["source"] == "yahoo"
    assert derived["universe"] == "etf_sample"
    assert derived["nyse_symbols"][0] == "SPY"
    assert len(derived["nyse_symbols"]) == 10
    assert "listed issues" in derived["note"]
    assert _breadth_mock_blocked(derived) is False

    fabricated = _annotate_breadth(
        {"nyse_advancing": 1520, "nyse_declining": 1380, "nyse_unchanged": 100, "nasdaq_advancing": 1840}
    )
    assert fabricated["source"] == "mock"
    assert fabricated["classification"] == "mock"
    assert _breadth_mock_blocked(fabricated) is True

    assert _ohlc_fetch_symbol("VIX") == "^VIX"
    assert _ohlc_fetch_symbol("vix") == "^VIX"
    assert _ohlc_fetch_symbol("SPY") == "SPY"
    assert _ohlc_fetch_symbol("BTC") == "BTC"


@pytest.mark.live
@pytest.mark.skipif(os.getenv("RUN_LIVE_TESTS", "") != "1", reason="Set RUN_LIVE_TESTS=1 to hit Yahoo")
def test_live_dxy_and_gold_are_plausible():
    from src.api.yahoo_client import YahooFinanceClient

    data = YahooFinanceClient().get_macro_data()
    dxy = data["DXY"]
    gold = data["GC"]
    assert dxy["symbol"] == "DX-Y.NYB"
    assert dxy["is_proxy"] is False
    assert 90 <= dxy["price"] <= 110
    assert gold["symbol"] == "GC=F"
    assert gold["is_proxy"] is False
    assert gold["price"] > 1000
