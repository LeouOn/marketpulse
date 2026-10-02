"""Offline tests for src/llm/tools/data_tools.py (cycle 9).

Every upstream client is faked at its source module (the tools import them
lazily at call time): MarketPulseCollector, YahooFinanceClient,
MarketBreadthCollector. No network, no live providers.

Bugs pinned here (each fix's test fails on the pre-change module):

* a NaN volume cell inside the returned window killed the whole get_ohlcv
  result (``int(float("nan"))`` raises), and NaN/None OHLC cells came through
  as ``nan`` floats — which break the agents' JSON serialization downstream;
* get_symbol_52w_stats divided by a zero 52-week low (whole tool dead with a
  cryptic "float division by zero") and emitted ``nan`` stats for a NaN last
  close;
* both symbol tools echoed the raw ``$``-prefixed symbol although the data was
  fetched for the cleaned one.
"""

from __future__ import annotations

import asyncio
import inspect
import math
from typing import Any

import pandas as pd
import pytest

from src.llm.tools.data_tools import (
    DATA_TOOL_DEFINITIONS,
    DATA_TOOL_HANDLERS,
    get_breadth,
    get_market_internals,
    get_ohlcv,
    get_symbol_52w_stats,
)

COLS = ["open", "high", "low", "close", "volume"]


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeCollector:
    internals: dict[str, Any] | Exception = {}
    initialized = 0

    async def initialize(self):
        type(self).initialized += 1

    async def collect_market_internals(self):
        if isinstance(type(self).internals, Exception):
            raise type(self).internals
        return type(self).internals


class _FakeYahoo:
    frame: pd.DataFrame | None | Exception = None

    def get_bars(self, symbol, period, interval):
        if isinstance(type(self).frame, Exception):
            raise type(self).frame
        return type(self).frame


class _FakeBreadth:
    breadth: dict[str, Any] | Exception = {}

    def get_market_internals(self):
        if isinstance(type(self).breadth, Exception):
            raise type(self).breadth
        return type(self).breadth


def _use_yahoo(monkeypatch, frame) -> None:
    _FakeYahoo.frame = frame
    monkeypatch.setattr("src.api.yahoo_client.YahooFinanceClient", _FakeYahoo)


def _frame(rows, columns=None, multiindex=False) -> pd.DataFrame:
    columns = columns or COLS
    df = pd.DataFrame(rows, columns=columns, index=pd.date_range("2026-01-05", periods=len(rows), freq="1D"))
    if multiindex:
        df.columns = pd.MultiIndex.from_tuples([(c, "SPY") for c in columns])
    return df


def _base_rows(n: int = 60) -> list[list]:
    return [[99.9, 100.5, 99.5, 100.0 + i * 0.2, 1000.0] for i in range(n)]


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Registry / tool-definition shape (what the agents consume)
# ---------------------------------------------------------------------------


def test_definitions_match_handlers_and_are_openai_shaped():
    names = [d["function"]["name"] for d in DATA_TOOL_DEFINITIONS]
    assert sorted(names) == sorted(DATA_TOOL_HANDLERS)
    assert set(names) == {"get_market_internals", "get_ohlcv", "get_breadth", "get_symbol_52w_stats"}
    for d in DATA_TOOL_DEFINITIONS:
        assert d["type"] == "function"
        assert isinstance(d["function"]["name"], str)
        assert isinstance(d["function"]["description"], str)
        assert isinstance(d["function"]["parameters"], dict)
        assert d["function"]["parameters"].get("type") == "object"
        assert set(d["function"]["parameters"]) <= {"type", "properties", "required"}
    for name, handler in DATA_TOOL_HANDLERS.items():
        assert inspect.iscoroutinefunction(handler), name


# ---------------------------------------------------------------------------
# get_market_internals
# ---------------------------------------------------------------------------


def test_market_internals_summarises_key_symbols(monkeypatch):
    _FakeCollector.internals = {
        "spy": {"price": 450.0, "change": 1.0, "change_pct": 0.22, "volume": 50},
        "qqq": {"price": 180.0, "change": None, "change_pct": None, "volume": 30},
        "macro": {"dxy": 101.0},
        "data_source": "fake",
        "zzz-unknown": {"price": 1.0},
    }
    monkeypatch.setattr("src.data.market_collector.MarketPulseCollector", _FakeCollector)

    out = _run(get_market_internals())

    assert "error" not in out
    assert out["spy"] == {"price": 450.0, "change": 1.0, "change_pct": 0.22, "volume": 50}
    # None fields degrade to "N/A", not nulls the LLM might misread.
    assert out["qqq"]["change"] == "N/A"
    assert out["macro"] == {"dxy": 101.0}
    assert out["data_source"] == "fake"
    assert "timestamp" in out
    assert "zzz-unknown" not in out


def test_market_internals_empty_is_an_error(monkeypatch):
    _FakeCollector.internals = {}
    monkeypatch.setattr("src.data.market_collector.MarketPulseCollector", _FakeCollector)

    out = _run(get_market_internals())

    assert "error" in out


def test_market_internals_collector_failure_is_an_error(monkeypatch):
    _FakeCollector.internals = RuntimeError("feed down")
    monkeypatch.setattr("src.data.market_collector.MarketPulseCollector", _FakeCollector)

    out = _run(get_market_internals())

    assert "feed down" in out["error"]


# ---------------------------------------------------------------------------
# get_ohlcv
# ---------------------------------------------------------------------------


def test_ohlcv_happy_path(monkeypatch):
    _use_yahoo(monkeypatch, _frame(_base_rows(30)))
    out = _run(get_ohlcv("SPY"))
    assert "error" not in out
    assert out["symbol"] == "SPY"
    assert out["count"] == 30 == len(out["candles"])
    assert out["latest_close"] == pytest.approx(100.0 + 29 * 0.2)
    first = out["candles"][0]
    assert set(first) == {"time", "open", "high", "low", "close", "volume"}
    assert first["volume"] == 1000


def test_ohlcv_caps_at_50_and_takes_the_tail(monkeypatch):
    _use_yahoo(monkeypatch, _frame(_base_rows(60)))
    out = _run(get_ohlcv("SPY"))
    assert out["count"] == 50
    assert out["latest_close"] == pytest.approx(100.0 + 59 * 0.2)


@pytest.mark.parametrize("builder", [lambda: None, lambda: pd.DataFrame(columns=COLS)])
def test_ohlcv_no_data_is_a_helpful_error(monkeypatch, builder):
    _use_yahoo(monkeypatch, builder())
    out = _run(get_ohlcv("SPY"))
    assert "No OHLCV data" in out["error"]


def test_ohlcv_client_failure_is_an_error(monkeypatch):
    _use_yahoo(monkeypatch, RuntimeError("yfinance boom"))
    out = _run(get_ohlcv("SPY"))
    assert "yfinance boom" in out["error"]


@pytest.mark.parametrize("columns_mode", ["multiindex", "uppercase"])
def test_ohlcv_normalises_column_shapes(monkeypatch, columns_mode):
    rows = _base_rows(5)
    if columns_mode == "multiindex":
        _use_yahoo(monkeypatch, _frame(rows, multiindex=True))
    else:
        _use_yahoo(monkeypatch, _frame(rows, columns=[c.upper() for c in COLS]))
    out = _run(get_ohlcv("SPY"))
    assert "error" not in out
    assert out["count"] == 5


def test_ohlcv_nan_volume_does_not_kill_the_result(monkeypatch):
    rows = _base_rows(60)
    rows[30][4] = float("nan")  # inside the tail(50) window
    _use_yahoo(monkeypatch, _frame(rows))
    out = _run(get_ohlcv("SPY"))
    assert "error" not in out, f"old code kills the whole result: {out.get('error')}"
    assert out["candles"][20]["volume"] is None  # null, not a crash
    assert out["candles"][20]["close"] == pytest.approx(100.0 + 30 * 0.2)


def test_ohlcv_nan_and_none_cells_serialize_as_null(monkeypatch):
    rows = _base_rows(60)
    rows[30][0] = None
    rows[31][3] = float("nan")
    _use_yahoo(monkeypatch, _frame(rows))
    out = _run(get_ohlcv("SPY"))
    assert "error" not in out
    assert out["candles"][20]["open"] is None
    assert out["candles"][21]["close"] is None


def test_ohlcv_nan_last_close_latest_close_is_null(monkeypatch):
    rows = _base_rows(60)
    rows[59][3] = float("nan")
    _use_yahoo(monkeypatch, _frame(rows))
    out = _run(get_ohlcv("SPY"))
    assert "error" not in out
    assert out["latest_close"] is None
    assert out["candles"][-1]["close"] is None


def test_ohlcv_strips_dollar_prefix_in_response(monkeypatch):
    _use_yahoo(monkeypatch, _frame(_base_rows(5)))
    out = _run(get_ohlcv("$SPY"))
    assert out["symbol"] == "SPY"


# ---------------------------------------------------------------------------
# get_breadth
# ---------------------------------------------------------------------------


def test_breadth_maps_fields(monkeypatch):
    _FakeBreadth.breadth = {
        "nyse_advancing": 2100,
        "nyse_declining": 900,
        "nyse_ad_ratio": 2.33,
        "tick_avg_30m": 111.0,
        "vold_nyse": -1.2,
    }
    monkeypatch.setattr("src.data.market_breadth.MarketBreadthCollector", _FakeBreadth)

    out = _run(get_breadth())

    assert out["nyse_advancing"] == 2100
    assert out["nyse_ad_ratio"] == 2.33
    assert out["tick_avg"] == 111.0  # renamed from tick_avg_30m
    assert out["vold"] == -1.2  # renamed from vold_nyse
    assert "timestamp" in out


def test_breadth_missing_fields_degrade_to_na(monkeypatch):
    _FakeBreadth.breadth = {"nyse_advancing": 5}
    monkeypatch.setattr("src.data.market_breadth.MarketBreadthCollector", _FakeBreadth)

    out = _run(get_breadth())

    assert out["nyse_advancing"] == 5
    assert out["mcclellan_osc"] == "N/A"


def test_breadth_empty_and_failure_are_errors(monkeypatch):
    _FakeBreadth.breadth = {}
    monkeypatch.setattr("src.data.market_breadth.MarketBreadthCollector", _FakeBreadth)
    assert "error" in _run(get_breadth())

    _FakeBreadth.breadth = RuntimeError("breadth boom")
    monkeypatch.setattr("src.data.market_breadth.MarketBreadthCollector", _FakeBreadth)
    out = _run(get_breadth())
    assert "breadth boom" in out["error"]


# ---------------------------------------------------------------------------
# get_symbol_52w_stats
# ---------------------------------------------------------------------------


def _stats_frame() -> pd.DataFrame:
    # 52w high 120 on day 10, low 80 on day 20, current close 100 on the last day.
    rows = []
    for i in range(30):
        high = 120.0 if i == 10 else 100.0 + i * 0.1
        low = 80.0 if i == 20 else 90.0 + i * 0.1
        close = 100.0 if i == 29 else 95.0 + i * 0.1
        rows.append([close - 1.0, high, low, close, 1000.0])
    return _frame(rows)


def test_52w_stats_happy_path(monkeypatch):
    _use_yahoo(monkeypatch, _stats_frame())
    out = _run(get_symbol_52w_stats("SPY"))
    assert "error" not in out
    assert out["current_price"] == pytest.approx(100.0)
    assert out["high_52w"] == pytest.approx(120.0)
    assert out["low_52w"] == pytest.approx(80.0)
    assert out["pct_from_52w_high"] == pytest.approx(-16.67)
    assert out["pct_from_52w_low"] == pytest.approx(25.0)
    assert "2026-01-15" in out["high_date"]  # day 10 of the index
    assert "2026-01-25" in out["low_date"]  # day 20


def test_52w_stats_zero_low_is_not_a_crash(monkeypatch):
    frame = _stats_frame()
    frame.iloc[20, frame.columns.get_loc("low")] = 0.0
    _use_yahoo(monkeypatch, frame)
    out = _run(get_symbol_52w_stats("SPY"))
    assert "error" not in out, f"old code dies on a zero low: {out.get('error')}"
    assert out["low_52w"] == pytest.approx(0.0)
    assert out["pct_from_52w_low"] is None  # undefined vs a zero reference
    assert out["pct_from_52w_high"] == pytest.approx(-16.67)  # rest of the stats intact


def test_52w_stats_non_finite_close_is_a_clear_error(monkeypatch):
    frame = _stats_frame()
    frame.iloc[-1, frame.columns.get_loc("close")] = float("nan")
    _use_yahoo(monkeypatch, frame)
    out = _run(get_symbol_52w_stats("SPY"))
    assert "error" in out, "old code emits nan stats"
    assert "non-finite" in out["error"]


def test_52w_stats_no_data_and_missing_columns(monkeypatch):
    _use_yahoo(monkeypatch, None)
    assert "No data" in _run(get_symbol_52w_stats("SPY"))["error"]

    _use_yahoo(monkeypatch, _frame([[1.0, 2.0]], columns=["open", "close"]))
    out = _run(get_symbol_52w_stats("SPY"))
    assert "missing columns" in out["error"]


def test_52w_stats_strips_dollar_prefix_in_response(monkeypatch):
    _use_yahoo(monkeypatch, _stats_frame())
    out = _run(get_symbol_52w_stats("$SPY"))
    assert out["symbol"] == "SPY"


def test_52w_stats_all_values_are_json_finite(monkeypatch):
    _use_yahoo(monkeypatch, _stats_frame())
    out = _run(get_symbol_52w_stats("SPY"))
    for key in ("current_price", "high_52w", "low_52w", "pct_from_52w_high", "pct_from_52w_low"):
        assert out[key] is None or math.isfinite(out[key]), key
