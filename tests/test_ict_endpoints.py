"""Offline coverage for src/api/ict_endpoints.py (cycle 8).

The module had no dedicated tests (only route-snapshot references). All three
endpoints (``POST /api/ict/analyze``, ``POST /api/ict/signals``,
``GET /api/ict/quick-scan/{symbol}``) are exercised with ``bars_frame`` faked
at the module seam — no network, deterministic frames.

Bugs pinned here (each fix's test fails on the pre-change module):

* ``lookback=0`` returned **all** candles (``iloc[-0:]`` is the whole frame)
  and negative lookback silently dropped the *first* rows instead;
* an unknown ``timeframe`` (e.g. ``"42h"``) silently fell back to the 5m/5d
  fetch while echoing the bogus value back in the response;
* non-finite candle data (NaN/inf in open/high/low/close/volume) produced
  ``success: true`` with ``null`` prices (pydantic maps NaN to null) or a
  cryptic ``"Maximum allowed size exceeded"`` — now a clear refusal.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api.ict_endpoints as ict_mod

COLS = ["open", "high", "low", "close", "volume"]


def _frame(closes, volumes=None) -> pd.DataFrame:
    closes = list(closes)
    n = len(closes)
    return pd.DataFrame(
        {
            "open": [c - 0.1 for c in closes],
            "high": [c + 0.5 for c in closes],
            "low": [c - 0.5 for c in closes],
            "close": closes,
            "volume": volumes if volumes is not None else [100.0] * n,
        },
        index=pd.date_range("2026-01-05 09:30", periods=n, freq="1min"),
    )


def _trend_frame(n: int = 60) -> pd.DataFrame:
    return _frame([100.0 + i * 0.2 for i in range(n)])


class _FrameSource:
    """Deterministic bars_frame replacement; can also raise."""

    def __init__(self, frame):
        self.frame = frame
        self.calls: list[tuple] = []

    def __call__(self, client, symbol, period, interval):
        self.calls.append((symbol, period, interval))
        if isinstance(self.frame, Exception):
            raise self.frame
        return self.frame


@pytest.fixture
def mount(monkeypatch):
    """Return a helper that mounts the router with a given frame source."""

    def _mount(frame) -> TestClient:
        source = _FrameSource(frame)
        monkeypatch.setattr(ict_mod, "bars_frame", source)
        monkeypatch.setattr(ict_mod, "YahooFinanceClient", lambda: object())
        app = FastAPI()
        app.include_router(ict_mod.ict_router)
        return TestClient(app, raise_server_exceptions=False)

    return _mount


# ---------------------------------------------------------------------------
# POST /api/ict/analyze
# ---------------------------------------------------------------------------


def test_analyze_happy_path(mount):
    client = mount(_trend_frame(60))
    r = client.post("/api/ict/analyze", json={"symbol": "NQ=F", "lookback": 50})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    data = body["data"]
    assert data["symbol"] == "NQ=F"
    assert data["timeframe"] == "5m"
    assert data["candles_analyzed"] == 50
    for key in ("fair_value_gaps", "order_blocks", "liquidity_pools", "market_structure", "volume_profile"):
        assert key in data
    assert math.isfinite(data["current_price"])


def test_analyze_lookback_larger_than_frame_returns_everything(mount):
    client = mount(_trend_frame(30))
    r = client.post("/api/ict/analyze", json={"symbol": "NQ=F", "lookback": 500})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["candles_analyzed"] == 30


def test_analyze_empty_data(mount):
    client = mount(pd.DataFrame(columns=COLS))
    r = client.post("/api/ict/analyze", json={"symbol": "NQ=F"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is False
    assert "no data" in body["error"].lower()


def test_analyze_fetch_failure_is_reported_not_raised(mount):
    client = mount(RuntimeError("boom"))
    r = client.post("/api/ict/analyze", json={"symbol": "NQ=F"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is False
    assert "boom" in body["error"]


@pytest.mark.parametrize("bad_lookback", [0, -5])
def test_analyze_rejects_non_positive_lookback(mount, bad_lookback):
    client = mount(_trend_frame(60))
    r = client.post("/api/ict/analyze", json={"symbol": "NQ=F", "lookback": bad_lookback})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is False, f"lookback={bad_lookback} must be refused, got success=true"
    assert "lookback" in body["error"]


def test_analyze_rejects_unknown_timeframe(mount):
    client = mount(_trend_frame(60))
    r = client.post("/api/ict/analyze", json={"symbol": "NQ=F", "timeframe": "42h"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is False, "unknown timeframe must be refused, not silently fetched as 5m"
    assert "timeframe" in body["error"]


@pytest.mark.parametrize("column", ["open", "high", "low", "close", "volume"])
def test_analyze_rejects_non_finite_candles(mount, column):
    frame = _trend_frame(60)
    frame.iloc[3, frame.columns.get_loc(column)] = float("nan")
    client = mount(frame)
    r = client.post("/api/ict/analyze", json={"symbol": "NQ=F"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is False, f"NaN in {column} must be refused, got success=true"
    assert "non-finite" in body["error"]


def test_analyze_rejects_infinite_candles(mount):
    frame = _trend_frame(60)
    frame.iloc[-1, frame.columns.get_loc("close")] = math.inf
    client = mount(frame)
    r = client.post("/api/ict/analyze", json={"symbol": "NQ=F"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is False
    assert "non-finite" in body["error"]


def test_analyze_short_frame_does_not_crash(mount):
    client = mount(_frame([100.0]))
    r = client.post("/api/ict/analyze", json={"symbol": "NQ=F"})
    assert r.status_code == 200, r.text
    assert isinstance(r.json()["success"], bool)


# ---------------------------------------------------------------------------
# POST /api/ict/signals
# ---------------------------------------------------------------------------


def test_signals_happy_path_shape(mount):
    client = mount(_trend_frame(60))
    r = client.post("/api/ict/signals", json={"symbol": "NQ=F"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    data = body["data"]
    assert data["signals_count"] == len(data["signals"])
    if data["signals"]:
        first = data["signals"][0]
        for key in ("type", "confidence", "entry_price", "stop_loss", "take_profit", "risk_reward_ratio"):
            assert key in first
        assert data["top_signal"]["confidence"] == max(s["confidence"] for s in data["signals"])
    else:
        assert data["top_signal"] is None


def test_signals_empty_data(mount):
    client = mount(pd.DataFrame(columns=COLS))
    r = client.post("/api/ict/signals", json={"symbol": "NQ=F"})
    assert r.status_code == 200, r.text
    assert r.json()["success"] is False


def test_signals_rejects_non_positive_lookback(mount):
    client = mount(_trend_frame(60))
    r = client.post("/api/ict/signals", json={"symbol": "NQ=F", "lookback": 0})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is False
    assert "lookback" in body["error"]


def test_signals_rejects_unknown_timeframe(mount):
    client = mount(_trend_frame(60))
    r = client.post("/api/ict/signals", json={"symbol": "NQ=F", "timeframe": "7h"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is False
    assert "timeframe" in body["error"]


def test_signals_rejects_non_finite_candles(mount):
    frame = _trend_frame(60)
    frame.iloc[10, frame.columns.get_loc("high")] = float("nan")
    client = mount(frame)
    r = client.post("/api/ict/signals", json={"symbol": "NQ=F"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is False
    assert "non-finite" in body["error"]


# ---------------------------------------------------------------------------
# GET /api/ict/quick-scan/{symbol}
# ---------------------------------------------------------------------------


def test_quick_scan_happy_path(mount):
    client = mount(_trend_frame(60))
    r = client.get("/api/ict/quick-scan/NQ%3DF")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    data = body["data"]
    assert data["symbol"] == "NQ=F"
    assert data["quick_bias"] in ("bullish", "bearish", "neutral")
    for key in ("active_fvgs_count", "active_obs_count", "unswept_liquidity_count"):
        assert isinstance(data[key], int) and data[key] >= 0
    assert math.isfinite(data["current_price"])
    assert math.isfinite(data["poc"])


def test_quick_scan_empty_data(mount):
    client = mount(pd.DataFrame(columns=COLS))
    r = client.get("/api/ict/quick-scan/NQ%3DF")
    assert r.status_code == 200, r.text
    assert r.json()["success"] is False


def test_quick_scan_short_frame_does_not_crash(mount):
    client = mount(_frame([100.0] * 10))
    r = client.get("/api/ict/quick-scan/NQ%3DF")
    assert r.status_code == 200, r.text
    assert isinstance(r.json()["success"], bool)


def test_quick_scan_rejects_non_finite_candles(mount):
    frame = _trend_frame(60)
    frame.iloc[-1, frame.columns.get_loc("close")] = float("nan")
    client = mount(frame)
    r = client.get("/api/ict/quick-scan/NQ%3DF")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is False, "NaN close must be refused, not reported as current_price null"
    assert "non-finite" in body["error"]


def test_quick_scan_fetch_failure_is_reported_not_raised(mount):
    client = mount(RuntimeError("network down"))
    r = client.get("/api/ict/quick-scan/NQ%3DF")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is False
    assert "network down" in body["error"]
