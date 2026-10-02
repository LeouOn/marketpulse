"""Offline coverage for src/api/visualization_endpoints.py (cycle 17).

The existing reference (tests/test_api_smoke.py) touches only the heatmap's
404 path; this file covers every endpoint. ``bars_frame`` is faked at the
module seam with deterministic frames (no network); the REAL ChartGenerator
runs (plotly renders offline, deterministically). Assertions are on structure
and non-empty bodies — never pixels.

Bugs pinned here (each fix's test fails on the pre-change module):

* ``GET /volume-profile?bins<=0`` returned 500 (numpy histogram errors) instead
  of a 400 bad-parameter;
* ``POST /candlestick`` with ``height < 10`` returned 500 (plotly rejects it)
  instead of a 400;
* an inf price flowed into ``GET /analysis`` as a bare Infinity and blew up
  JSON serialization (500) — ``_json_float`` caught NaN but not inf.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api.visualization_endpoints as viz_mod


def _frame(closes) -> pd.DataFrame:
    closes = list(closes)
    n = len(closes)

    def adj(c, d):
        return c + d if math.isfinite(c) else c

    return pd.DataFrame(
        {
            "open": [adj(c, -0.1) for c in closes],
            "high": [adj(c, 0.5) for c in closes],
            "low": [adj(c, -0.5) for c in closes],
            "close": closes,
            "volume": [100.0] * n,
        },
        index=pd.date_range("2026-01-05", periods=n, freq="1D"),
    )


def _trend(n: int = 60) -> pd.DataFrame:
    return _frame([100.0 + i * 0.5 for i in range(n)])


class _Source:
    def __init__(self, frame):
        self.frame = frame
        self.calls = []

    def __call__(self, client, symbol, period, interval):
        self.calls.append((symbol, period, interval))
        if isinstance(self.frame, Exception):
            raise self.frame
        return self.frame


@pytest.fixture
def mount(monkeypatch):
    def _mount(frame) -> tuple[TestClient, _Source]:
        source = _Source(frame)
        monkeypatch.setattr(viz_mod, "bars_frame", source)
        app = FastAPI()
        app.include_router(viz_mod.viz_router)
        return TestClient(app, raise_server_exceptions=False), source

    return _mount


# ---------------------------------------------------------------------------
# POST /api/viz/candlestick and GET /api/viz/candlestick/{symbol}
# ---------------------------------------------------------------------------


def test_candlestick_post_happy(mount):
    client, source = mount(_trend(60))
    r = client.post("/api/viz/candlestick", json={"symbol": "SPY", "indicators": ["sma_20"], "height": 500})
    assert r.status_code == 200, r.text[:120]
    assert "text/html" in r.headers["content-type"]
    assert "Plotly.newPlot" in r.text  # real figure serialized
    assert source.calls == [("SPY", "1mo", "1d")]


def test_candlestick_get_parses_indicator_csv(mount):
    client, source = mount(_trend(60))
    r = client.get("/api/viz/candlestick/SPY?indicators=sma_20,rsi&height=400&timeframe=1h&period=3mo")
    assert r.status_code == 200, r.text[:120]
    assert source.calls == [("SPY", "3mo", "1h")]


def test_candlestick_empty_data_404(mount):
    client, _ = mount(pd.DataFrame())
    r = client.post("/api/viz/candlestick", json={"symbol": "SPY"})
    assert r.status_code == 404


def test_candlestick_fetch_failure_500(mount):
    client, _ = mount(RuntimeError("yahoo down"))
    r = client.post("/api/viz/candlestick", json={"symbol": "SPY"})
    assert r.status_code == 500
    assert "yahoo down" in r.text


@pytest.mark.parametrize("bad_height", [0, -5, 9])
def test_candlestick_rejects_tiny_height(mount, bad_height):
    client, _ = mount(_trend(60))
    r = client.post("/api/viz/candlestick", json={"symbol": "SPY", "height": bad_height})
    assert r.status_code == 400, f"height={bad_height} must be a 400, got {r.status_code}: {r.text[:80]}"


def test_candlestick_height_ten_is_accepted(mount):
    client, _ = mount(_trend(60))
    r = client.post("/api/viz/candlestick", json={"symbol": "SPY", "height": 10})
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/viz/indicators/{symbol}
# ---------------------------------------------------------------------------


def test_indicator_panel_happy(mount):
    client, _ = mount(_trend(60))
    r = client.get("/api/viz/indicators/SPY")
    assert r.status_code == 200
    assert "Plotly.newPlot" in r.text


def test_indicator_panel_empty_404(mount):
    client, _ = mount(pd.DataFrame())
    assert client.get("/api/viz/indicators/SPY").status_code == 404


# ---------------------------------------------------------------------------
# GET /api/viz/volume-profile/{symbol}
# ---------------------------------------------------------------------------


def test_volume_profile_happy(mount):
    client, _ = mount(_trend(60))
    r = client.get("/api/viz/volume-profile/SPY?bins=10")
    assert r.status_code == 200
    assert "Plotly.newPlot" in r.text


@pytest.mark.parametrize("bad_bins", [0, -5])
def test_volume_profile_rejects_non_positive_bins(mount, bad_bins):
    client, _ = mount(_trend(60))
    r = client.get(f"/api/viz/volume-profile/SPY?bins={bad_bins}")
    assert r.status_code == 400, f"bins={bad_bins} must be a 400, got {r.status_code}: {r.text[:80]}"


def test_volume_profile_empty_404(mount):
    client, _ = mount(pd.DataFrame())
    assert client.get("/api/viz/volume-profile/SPY").status_code == 404


# ---------------------------------------------------------------------------
# GET /api/viz/market-heatmap
# ---------------------------------------------------------------------------


def test_market_heatmap_sector_happy(mount):
    client, _ = mount(_trend(30))
    r = client.get("/api/viz/market-heatmap?sector=true")
    assert r.status_code == 200
    assert "Plotly.newPlot" in r.text


def test_market_heatmap_indices_branch(mount):
    client, _ = mount(_trend(30))
    r = client.get("/api/viz/market-heatmap?sector=false")
    assert r.status_code == 200


def test_market_heatmap_no_usable_data_404(mount):
    client, _ = mount(RuntimeError("no data"))
    r = client.get("/api/viz/market-heatmap")
    assert r.status_code == 404
    assert "No data available" in r.text


def test_market_heatmap_single_row_frames_are_skipped(mount):
    # Every symbol returns a 1-row frame (len < 2): no performance computable -> 404.
    client, _ = mount(_frame([100.0]))
    r = client.get("/api/viz/market-heatmap")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/viz/analysis/{symbol}
# ---------------------------------------------------------------------------


def test_analysis_happy(mount):
    client, _ = mount(_trend(60))
    r = client.get("/api/viz/analysis/SPY")
    assert r.status_code == 200, r.text[:120]
    body = r.json()
    assert body["success"] is True
    data = body["data"]
    assert data["symbol"] == "SPY"
    assert math.isfinite(data["current_price"])
    assert data["trends"]["sma_trend"] in ("strong_bullish", "bullish", "strong_bearish", "bearish")
    assert isinstance(data["support_resistance"]["support"], list)
    assert set(data["indicators"]) >= {"sma_20", "rsi", "macd"}
    assert data["signals"]["overall"] in ("bullish", "bearish")


def test_analysis_nan_close_serializes_null(mount):
    frame = _frame([100.0 + i * 0.5 for i in range(59)] + [float("nan")])
    client, _ = mount(frame)
    r = client.get("/api/viz/analysis/SPY")
    assert r.status_code == 200
    assert r.json()["data"]["current_price"] is None


def test_analysis_inf_close_serializes_null_not_500(mount):
    frame = _frame([100.0 + i * 0.5 for i in range(59)] + [math.inf])
    client, _ = mount(frame)
    r = client.get("/api/viz/analysis/SPY")
    assert r.status_code == 200, f"old code 500s on inf: {r.text[:80]}"
    assert r.json()["data"]["current_price"] is None


def test_analysis_empty_404(mount):
    client, _ = mount(pd.DataFrame())
    assert client.get("/api/viz/analysis/SPY").status_code == 404


def test_analysis_short_frame_all_null_indicators(mount):
    client, _ = mount(_frame([100.0, 101.0, 102.0]))
    r = client.get("/api/viz/analysis/SPY")
    assert r.status_code == 200
    indicators = r.json()["data"]["indicators"]
    assert indicators["sma_200"] is None  # windows longer than the frame -> null, not crash


# ---------------------------------------------------------------------------
# GET /api/viz/dashboard/{symbol} and /
# ---------------------------------------------------------------------------


def test_dashboard_happy(mount):
    client, _ = mount(_trend(80))
    r = client.get("/api/viz/dashboard/SPY")
    assert r.status_code == 200
    assert "SPY Trading Dashboard" in r.text
    assert len(r.content) > 1000  # non-empty page


def test_dashboard_empty_404(mount):
    client, _ = mount(pd.DataFrame())
    assert client.get("/api/viz/dashboard/SPY").status_code == 404


def test_home_lists_endpoints(mount):
    client, _ = mount(_trend(10))
    r = client.get("/api/viz/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    for fragment in ("candlestick", "volume-profile", "market-heatmap", "dashboard"):
        assert fragment in r.text
