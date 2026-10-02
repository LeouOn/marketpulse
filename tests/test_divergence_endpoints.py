"""Offline tests for src/api/divergence_endpoints.py.

Every external seam is faked: ``bars_frame`` (market data) and
``scan_for_divergences`` (detector) are monkeypatched in the module namespace,
so no network is touched. The real (offline, plotly) ChartGenerator is used for
the chart/dashboard endpoints so the full HTML path is covered.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api.divergence_endpoints as de

# ---------------------------------------------------------------------------
# Fixtures / fakes
# ---------------------------------------------------------------------------


def _frame(rows: int = 40) -> pd.DataFrame:
    """Deterministic OHLCV frame with a DatetimeIndex (no randomness)."""
    idx = pd.date_range("2024-01-01", periods=rows, freq="D")
    base = 100 + pd.Series(range(rows), index=idx) * 0.5
    return pd.DataFrame(
        {
            "open": base,
            "high": base + 1.0,
            "low": base - 1.0,
            "close": base + 0.25,
            "volume": [1_000.0] * rows,
        },
        index=idx,
    )


def _scan_result(frame: pd.DataFrame, with_divergence: bool = True) -> dict:
    """A scan_for_divergences-shaped result, timestamps matching the frame."""
    if not with_divergence:
        return {
            "total_divergences": 0,
            "by_type": {"regular_bullish": 0, "regular_bearish": 0, "hidden_bullish": 0, "hidden_bearish": 0},
            "divergences": [],
            "strongest": None,
            "signal": "NEUTRAL",
        }
    return {
        "total_divergences": 1,
        "by_type": {"regular_bullish": 1, "regular_bearish": 0, "hidden_bullish": 0, "hidden_bearish": 0},
        "divergences": [
            {
                "type": "regular_bullish",
                "indicator": "rsi",
                "strength": 80.0,
                "start_time": frame.index[2].isoformat(),
                "end_time": frame.index[-3].isoformat(),
                "description": "Price lower low, RSI higher low",
            }
        ],
        "strongest": {
            "type": "regular_bullish",
            "indicator": "rsi",
            "strength": 80.0,
            "description": "Price lower low, RSI higher low",
        },
        "signal": "BULLISH",
    }


@pytest.fixture
def bars_calls(monkeypatch):
    """Patch bars_frame; records (symbol, period, interval) and returns a settable frame."""
    state = {"frame": _frame()}
    calls: list[dict] = []

    def fake_bars(client, symbol, period, interval):
        calls.append({"symbol": symbol, "period": period, "interval": interval})
        return state["frame"]

    monkeypatch.setattr(de, "bars_frame", fake_bars)
    return state, calls


@pytest.fixture
def scan_calls(monkeypatch, bars_calls):
    """Patch scan_for_divergences; records min_strength and returns a settable result."""
    state, _ = bars_calls
    scan_state = {"result": _scan_result(state["frame"]), "min_strength": None}

    def fake_scan(df, min_strength=60.0):
        scan_state["min_strength"] = min_strength
        return scan_state["result"]

    monkeypatch.setattr(de, "scan_for_divergences", fake_scan)
    return scan_state


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(de.divergence_router)
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Home + POST /scan
# ---------------------------------------------------------------------------


def test_home_page_serves_html(client):
    response = client.get("/api/divergence/")

    assert response.status_code == 200
    assert "Divergence Detection" in response.text
    assert "/api/divergence/scan/AAPL" in response.text


def test_post_scan_returns_divergences(client, scan_calls):
    response = client.post("/api/divergence/scan", json={"symbol": "TEST"})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    assert data["symbol"] == "TEST"
    assert data["timestamp"]  # added by the endpoint
    assert data["total_divergences"] == 1
    assert data["by_type"]["regular_bullish"] == 1
    assert data["divergences"][0]["indicator"] == "rsi"
    assert data["signal"] == "BULLISH"
    # Default min_strength from the request model is applied.
    assert scan_calls["min_strength"] == 60.0


def test_post_scan_passes_symbol_period_and_timeframe_to_bars(client, scan_calls, bars_calls):
    response = client.post(
        "/api/divergence/scan", json={"symbol": "TEST", "period": "6mo", "timeframe": "1h", "min_strength": 75.0}
    )

    assert response.status_code == 200
    _, calls = bars_calls
    assert calls == [{"symbol": "TEST", "period": "6mo", "interval": "1h"}]
    assert scan_calls["min_strength"] == 75.0


def test_post_scan_empty_data_is_404(client, bars_calls):
    state, _ = bars_calls
    state["frame"] = pd.DataFrame()

    response = client.post("/api/divergence/scan", json={"symbol": "EMPTY"})

    assert response.status_code == 404
    assert "No data found for EMPTY" in response.json()["detail"]


def test_post_scan_detector_crash_is_500_with_detail(client, scan_calls, monkeypatch):
    def exploding_scan(df, min_strength=60.0):
        raise RuntimeError("detector exploded")

    monkeypatch.setattr(de, "scan_for_divergences", exploding_scan)

    response = client.post("/api/divergence/scan", json={"symbol": "TEST"})

    assert response.status_code == 500
    assert "detector exploded" in response.json()["detail"]


def test_post_scan_missing_symbol_is_422(client):
    response = client.post("/api/divergence/scan", json={})

    assert response.status_code == 422


def test_post_scan_sanitises_nan_and_inf_values(client, scan_calls):
    """NaN/inf strengths must serialise as null, not kill the response."""
    result = scan_calls["result"]
    result["divergences"][0]["strength"] = math.nan
    result["strongest"]["strength"] = math.inf

    response = client.post("/api/divergence/scan", json={"symbol": "TEST"})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["divergences"][0]["strength"] is None
    assert data["strongest"]["strength"] is None


# ---------------------------------------------------------------------------
# GET /scan/{symbol}
# ---------------------------------------------------------------------------


def test_get_scan_simple_delegates_to_the_scan_handler(client, scan_calls, bars_calls):
    response = client.get("/api/divergence/scan/TEST?timeframe=1h&period=1mo&min_strength=75")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["symbol"] == "TEST"
    assert data["total_divergences"] == 1
    assert scan_calls["min_strength"] == 75.0
    _, calls = bars_calls
    assert calls == [{"symbol": "TEST", "period": "1mo", "interval": "1h"}]


def test_get_scan_simple_rejects_non_numeric_min_strength(client):
    response = client.get("/api/divergence/scan/TEST?min_strength=abc")

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /chart/{symbol}
# ---------------------------------------------------------------------------


def test_chart_renders_with_divergence_overlays(client, scan_calls):
    response = client.get("/api/divergence/chart/TEST")

    assert response.status_code == 200
    assert "Divergence Analysis" in response.text
    assert "Found 1 divergences" in response.text
    assert "Signal: BULLISH" in response.text
    assert "Strongest: RSI" in response.text


def test_chart_without_divergences_omits_strongest_text(client, scan_calls, bars_calls):
    state, _ = bars_calls
    scan_calls["result"] = _scan_result(state["frame"], with_divergence=False)

    response = client.get("/api/divergence/chart/TEST")

    assert response.status_code == 200
    assert "Found 0 divergences" in response.text
    assert "Strongest:" not in response.text


def test_chart_empty_data_is_404(client, bars_calls):
    state, _ = bars_calls
    state["frame"] = pd.DataFrame()

    response = client.get("/api/divergence/chart/EMPTY")

    assert response.status_code == 404
    assert "No data found for EMPTY" in response.json()["detail"]


def test_chart_indicator_query_values_are_stripped(client, scan_calls, monkeypatch):
    """ "?indicators=sma_20, ema_50" must reach the chart as clean names."""
    captured: dict = {}
    original = de.chart_gen.create_candlestick_chart

    def spy(df, **kwargs):
        captured["indicators"] = kwargs.get("indicators")
        return original(df, **kwargs)

    monkeypatch.setattr(de.chart_gen, "create_candlestick_chart", spy)

    response = client.get("/api/divergence/chart/TEST?indicators=sma_20,%20ema_50,")

    assert response.status_code == 200
    assert captured["indicators"] == ["sma_20", "ema_50"]


# ---------------------------------------------------------------------------
# GET /dashboard/{symbol}
# ---------------------------------------------------------------------------


def test_dashboard_renders_with_divergences(client, scan_calls):
    response = client.get("/api/divergence/dashboard/TEST")

    assert response.status_code == 200
    assert "TEST Divergence Dashboard" in response.text
    assert "Overall Signal: BULLISH" in response.text
    assert "RSI - Regular Bullish" in response.text
    assert "80" in response.text  # strongest strength metric


def test_dashboard_without_divergences_renders_zero_metrics(client, scan_calls, bars_calls):
    state, _ = bars_calls
    scan_calls["result"] = _scan_result(state["frame"], with_divergence=False)

    response = client.get("/api/divergence/dashboard/TEST")

    assert response.status_code == 200
    assert "Overall Signal: NEUTRAL" in response.text
    assert "No divergences detected" in response.text


def test_dashboard_empty_data_is_404_not_500(client, bars_calls):
    state, _ = bars_calls
    state["frame"] = pd.DataFrame()

    response = client.get("/api/divergence/dashboard/EMPTY")

    assert response.status_code == 404
    assert "No data found for EMPTY" in response.json()["detail"]


def test_dashboard_bars_crash_is_500_with_detail(client, bars_calls, monkeypatch):
    def exploding_bars(client_, symbol, period, interval):
        raise RuntimeError("yahoo down")

    monkeypatch.setattr(de, "bars_frame", exploding_bars)

    response = client.get("/api/divergence/dashboard/TEST")

    assert response.status_code == 500
    assert "yahoo down" in response.json()["detail"]
