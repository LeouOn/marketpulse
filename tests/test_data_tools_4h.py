"""Offline tests for the get_ohlcv 4h path (src/llm/tools/data_tools.py).

yfinance has no native "4h" interval, yet GET_OHLCV declares it valid and
multi_tf_agent prompts it. The tool must therefore fetch "1h" bars from the
client and fold them into 4h candles. All tests fake YahooFinanceClient at
its source module (the tool imports it lazily); no network.
"""

from __future__ import annotations

import asyncio
import math
from typing import Any

import pandas as pd
import pytest

from src.llm.tools.data_tools import get_ohlcv

COLS = ["open", "high", "low", "close", "volume"]


class _RecordingYahoo:
    frame: pd.DataFrame | None = None
    calls: list[tuple[str, str, str]] = []

    def get_bars(self, symbol, period, interval):
        type(self).calls.append((symbol, period, interval))
        return type(self).frame


@pytest.fixture
def yahoo(monkeypatch):
    _RecordingYahoo.calls = []
    _RecordingYahoo.frame = None
    monkeypatch.setattr("src.api.yahoo_client.YahooFinanceClient", _RecordingYahoo)
    return _RecordingYahoo


def _hourly(rows: list[list], start: str = "2024-01-01 00:00:00") -> pd.DataFrame:
    """rows of [open, high, low, close, volume] at consecutive hours."""
    return pd.DataFrame(rows, columns=COLS, index=pd.date_range(start, periods=len(rows), freq="1h"))


def _run(coro):
    return asyncio.run(coro)


def _candle(result: dict, i: int) -> dict[str, Any]:
    return result["candles"][i]


# ---------------------------------------------------------------------------
# 4h happy path
# ---------------------------------------------------------------------------


async def test_4h_fetches_1h_and_resamples_two_full_buckets(yahoo):
    yahoo.frame = _hourly(
        [
            [10.0, 12.0, 9.0, 11.0, 100.0],
            [20.0, 22.0, 19.0, 21.0, 200.0],
            [30.0, 32.0, 29.0, 31.0, 300.0],
            [40.0, 42.0, 39.0, 41.0, 400.0],
            [50.0, 52.0, 49.0, 51.0, 500.0],
            [60.0, 62.0, 59.0, 61.0, 600.0],
            [70.0, 72.0, 69.0, 71.0, 700.0],
            [80.0, 82.0, 79.0, 81.0, 800.0],
        ]
    )

    result = await get_ohlcv("SPY", period="5d", interval="4h")

    # The client saw 1h, never 4h.
    assert [c[2] for c in yahoo.calls] == ["1h"]
    assert yahoo.calls[0][:2] == ("SPY", "5d")

    assert "error" not in result
    assert result["interval"] == "4h"
    assert result["count"] == 2

    first = _candle(result, 0)
    assert first["time"].startswith("2024-01-01 00:00")  # left-labelled bucket
    assert first["open"] == 10.0  # first bar's open
    assert first["high"] == 42.0  # max of highs
    assert first["low"] == 9.0  # min of lows
    assert first["close"] == 41.0  # last bar's close
    assert first["volume"] == 1000  # sum

    second = _candle(result, 1)
    assert second["time"].startswith("2024-01-01 04:00")
    assert (second["open"], second["high"], second["low"], second["close"], second["volume"]) == (
        50.0,
        82.0,
        49.0,
        81.0,
        2600.0,
    )
    assert result["latest_close"] == 81.0


async def test_4h_drops_trailing_partial_bucket(yahoo):
    """Data ending mid-window must not emit a candle built from 2 of 4 bars."""
    yahoo.frame = _hourly(
        [
            [10.0, 12.0, 9.0, 11.0, 100.0],
            [20.0, 22.0, 19.0, 21.0, 200.0],
            [30.0, 32.0, 29.0, 31.0, 300.0],
            [40.0, 42.0, 39.0, 41.0, 400.0],
            [50.0, 52.0, 49.0, 51.0, 500.0],
            [60.0, 62.0, 59.0, 61.0, 600.0],
        ]
    )

    result = await get_ohlcv("SPY", interval="4h")

    assert result["count"] == 1
    assert _candle(result, 0)["close"] == 41.0  # the partial 04:00 bucket is gone


async def test_4h_drops_all_nan_gap_buckets(yahoo):
    """A 4-hour hole must not produce a NaN candle in the middle."""
    rows = [[10.0 + i, 12.0 + i, 9.0 + i, 11.0 + i, 100.0] for i in range(4)]
    gap_rows = [[50.0 + i, 52.0 + i, 49.0 + i, 51.0 + i, 500.0] for i in range(4)]
    yahoo.frame = _hourly(rows)
    yahoo.frame = pd.concat([yahoo.frame, _hourly(gap_rows, start="2024-01-01 08:00:00")])

    result = await get_ohlcv("SPY", interval="4h")

    assert result["count"] == 2
    times = [c["time"] for c in result["candles"]]
    assert times[0].startswith("2024-01-01 00:00")
    assert times[1].startswith("2024-01-01 08:00")  # the 04:00 hole is skipped


async def test_4h_skips_nan_cells_inside_a_bucket(yahoo):
    yahoo.frame = _hourly(
        [
            [10.0, 12.0, 9.0, 11.0, 100.0],
            [20.0, 22.0, 19.0, 21.0, 200.0],
            [30.0, 32.0, 29.0, 31.0, 300.0],
            [40.0, math.nan, 39.0, 41.0, 400.0],  # NaN high: max skips it
        ]
    )

    result = await get_ohlcv("SPY", interval="4h")

    assert result["count"] == 1
    assert _candle(result, 0)["high"] == 32.0


# ---------------------------------------------------------------------------
# 4h bad / minimal inputs
# ---------------------------------------------------------------------------


async def test_4h_with_too_few_bars_is_a_clear_error(yahoo):
    yahoo.frame = _hourly([[10.0, 12.0, 9.0, 11.0, 100.0]] * 3)

    result = await get_ohlcv("SPY", interval="4h")

    assert "error" in result
    assert "at least 4 x 1h bars" in result["error"]


async def test_4h_with_only_two_bars_hits_the_count_guard(yahoo):
    """Two bars cannot form any 4h candle: clear error in the tool's style."""
    yahoo.frame = _hourly([[10.0, 12.0, 9.0, 11.0, 100.0], [20.0, 22.0, 19.0, 21.0, 200.0]])

    result = await get_ohlcv("SPY", interval="4h")

    assert "error" in result
    assert "at least 4 x 1h bars" in result["error"]


async def test_4h_with_exactly_one_full_window_yields_one_candle(yahoo):
    """Four bars inside one window: a complete candle, kept."""
    yahoo.frame = _hourly(
        [
            [10.0, 12.0, 9.0, 11.0, 100.0],
            [20.0, 22.0, 19.0, 21.0, 200.0],
            [30.0, 32.0, 29.0, 31.0, 300.0],
            [40.0, 42.0, 39.0, 41.0, 400.0],
        ],
        start="2024-01-01 04:00:00",
    )

    result = await get_ohlcv("SPY", interval="4h")

    assert result["count"] == 1
    assert _candle(result, 0)["time"].startswith("2024-01-01 04:00")
    assert result["latest_close"] == 41.0


async def test_4h_empty_1h_frame_uses_the_existing_error_style(yahoo):
    yahoo.frame = pd.DataFrame()

    result = await get_ohlcv("SPY", period="1mo", interval="4h")

    assert "No OHLCV data returned for SPY" in result["error"]
    assert "(1mo/4h)" in result["error"]


# ---------------------------------------------------------------------------
# Non-4h intervals are unchanged
# ---------------------------------------------------------------------------


async def test_daily_interval_passes_through_unchanged(yahoo):
    yahoo.frame = pd.DataFrame(
        [[99.9, 100.5, 99.5, 100.0, 1000.0]] * 5,
        columns=COLS,
        index=pd.date_range("2026-01-05", periods=5, freq="1D"),
    )

    result = await get_ohlcv("SPY", interval="1d")

    assert [c[2] for c in yahoo.calls] == ["1d"]
    assert result["interval"] == "1d"
    assert result["count"] == 5
    assert _candle(result, 0)["open"] == 99.9
    assert result["latest_close"] == 100.0


async def test_hourly_interval_is_not_resampled(yahoo):
    yahoo.frame = _hourly([[10.0, 12.0, 9.0, 11.0, 100.0]] * 6)

    result = await get_ohlcv("SPY", interval="1h")

    assert [c[2] for c in yahoo.calls] == ["1h"]
    assert result["interval"] == "1h"
    assert result["count"] == 6  # raw 1h bars, no folding
