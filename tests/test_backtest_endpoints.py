"""Offline tests for src/api/backtest_endpoints.py.

The BacktestEngine is faked at the endpoints module's instance (deterministic
BacktestResults/Trade objects built with the real dataclasses); the regime
classifier is faked at the module namespace. The /position-size pipeline
(calculate_performance_stats + PositionScaler) runs for real -- it is pure
math. No network, no live data; every wait is bounded (plain TestClient
requests).
"""

from __future__ import annotations

import math
from datetime import datetime
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api.backtest_endpoints as be
from src.backtesting.backtest_engine import BacktestResults, Trade

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


def _trade(win: bool, pnl: float) -> Trade:
    return Trade(
        entry_time=datetime(2024, 1, 2, 9, 30),
        exit_time=datetime(2024, 1, 2, 10, 15),
        entry_price=100.0,
        exit_price=105.0 if win else 95.0,
        direction="LONG",
        contracts=1,
        pnl=pnl,
        pnl_percent=pnl / 100.0,
        duration_minutes=45,
        setup_type="FVG" if win else "Divergence",
        win=win,
    )


def _results(**overrides) -> BacktestResults:
    base = dict(
        total_trades=2,
        winning_trades=1,
        losing_trades=1,
        win_rate=50.0,
        total_pnl=250.0,
        total_pnl_percent=2.5,
        average_winner=400.0,
        average_loser=-150.0,
        largest_winner=400.0,
        largest_loser=-150.0,
        profit_factor=2.67,
        max_drawdown=-120.0,
        max_drawdown_percent=-1.2,
        sharpe_ratio=1.23,
        sortino_ratio=1.45,
        average_trade_duration=45.0,
        average_trade_pnl=125.0,
        expectancy=125.0,
        fvg_success_rate=60.0,
        divergence_success_rate=50.0,
        best_hour_of_day=9,
        worst_hour_of_day=14,
        best_day_of_week=2,
        # The real engine builds these with np.mean / trade datetimes.
        performance_by_setup={
            "FVG": {"count": 1, "win_rate": 100.0, "total_pnl": np.float64(400.0), "avg_pnl": np.float64(400.0)}
        },
        trades=[_trade(True, 400.0), _trade(False, -150.0)],
        equity_curve=pd.DataFrame(
            {"timestamp": [datetime(2024, 1, 2, 10, 15), datetime(2024, 1, 3, 11, 0)], "balance": [10400.0, 10250.0]}
        ),
    )
    return BacktestResults(**{**base, **overrides})


class _FakeEngine:
    def __init__(self):
        self.kwargs = None
        self.result = _results()
        self.raises = None

    def run_backtest(self, **kwargs):
        self.kwargs = kwargs
        if self.raises:
            raise self.raises
        return self.result


@pytest.fixture
def engine(monkeypatch):
    fake = _FakeEngine()
    monkeypatch.setattr(be, "backtest_engine", fake)
    return fake


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(be.backtest_router)
    return TestClient(app, raise_server_exceptions=False)


def _regime_analysis(**overrides) -> SimpleNamespace:
    base = dict(
        regime="RRENDING_PLACEHOLDER",
        confidence=61.25,
        recommended_bias="neutral",
        optimal_strategy="fade extremes",
        key_support=19800.5,
        key_resistance=20100.25,
        reasoning="offline reasoning",
        timestamp=datetime(2024, 6, 1, 12, 0),
    )
    return SimpleNamespace(**{**base, **overrides})


@pytest.fixture
def regime(monkeypatch):
    holder: dict = {"analysis": _regime_analysis(regime="RANGE_BOUND")}

    async def _fake_classify(symbol="NQ"):
        return holder["analysis"]

    monkeypatch.setattr(be, "classify_current_regime", _fake_classify)
    return holder


# ---------------------------------------------------------------------------
# POST /run + GET /run/{symbol}
# ---------------------------------------------------------------------------


def test_post_run_returns_metrics_and_survives_serialization(client, engine):
    """Realistic results (np.float64 setup stats, datetime equity stamps)."""
    response = client.post("/api/backtest/run", json={"symbol": "NQ"})

    assert response.status_code == 200
    data = response.json()["data"]

    assert data["basic_metrics"] == {"total_trades": 2, "winning_trades": 1, "losing_trades": 1, "win_rate": 50.0}
    assert data["pnl_metrics"]["profit_factor"] == 2.67
    assert data["risk_metrics"]["sharpe_ratio"] == 1.23
    assert data["trade_metrics"]["expectancy"] == 125.0
    assert data["strategy_metrics"]["best_hour_of_day"] == 9

    # Equity curve stamps must serialize as ISO strings, not datetime objects.
    assert data["equity_curve"][0]["timestamp"].startswith("2024-01-02T10:15")
    assert data["equity_curve"][1]["balance"] == 10250.0

    # Setup stats arrive as plain floats (np.float64 breaks JSONResponse).
    assert data["performance_by_setup"]["FVG"]["total_pnl"] == 400.0

    # Sample trades are the first 10, with ISO times and rounding.
    first = data["sample_trades"][0]
    assert first["entry_time"] == "2024-01-02T09:30:00"
    assert first["win"] is True
    assert first["setup_type"] == "FVG"


def test_post_run_sanitises_nan_and_inf_metrics(client, engine):
    engine.result = _results(sharpe_ratio=math.nan, profit_factor=math.inf)

    response = client.post("/api/backtest/run", json={"symbol": "NQ"})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["risk_metrics"]["sharpe_ratio"] is None
    assert data["pnl_metrics"]["profit_factor"] is None
    assert data["pnl_metrics"]["total_pnl"] == 250.0  # others unaffected


def test_post_run_empty_results(client, engine):
    engine.result = _results(
        total_trades=0,
        winning_trades=0,
        losing_trades=0,
        win_rate=0.0,
        trades=[],
        equity_curve=pd.DataFrame(),
        performance_by_setup={},
    )

    response = client.post("/api/backtest/run", json={"symbol": "EMPTY"})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["basic_metrics"]["total_trades"] == 0
    assert data["equity_curve"] == []
    assert data["sample_trades"] == []


def test_post_run_forwards_request_fields_and_defaults(client, engine):
    response = client.post(
        "/api/backtest/run",
        json={"symbol": "ES", "start_date": "2024-02-01", "end_date": "2024-03-01", "contracts": 3},
    )

    assert response.status_code == 200
    assert engine.kwargs == {
        "symbol": "ES",
        "start_date": "2024-02-01",
        "end_date": "2024-03-01",
        "initial_capital": 10000,
        "contracts": 3,
        "interval": "5m",
    }


def test_post_run_engine_failure_is_a_500_envelope(client, engine):
    engine.raises = RuntimeError("no historical data")

    response = client.post("/api/backtest/run", json={"symbol": "BAD"})

    assert response.status_code == 500
    assert "no historical data" in response.json()["detail"]


def test_post_run_validation_error_is_422(client):
    response = client.post("/api/backtest/run", json={"symbol": "X", "initial_capital": "not-a-number"})

    assert response.status_code == 422


def test_get_run_simple_delegates_to_the_post_handler(client, engine):
    response = client.get("/api/backtest/run/NQ?start_date=2024-05-01&end_date=2024-06-01&contracts=2")

    assert response.status_code == 200
    assert response.json()["data"]["basic_metrics"]["total_trades"] == 2
    assert engine.kwargs == {
        "symbol": "NQ",
        "start_date": "2024-05-01",
        "end_date": "2024-06-01",
        "initial_capital": 10000,
        "contracts": 2,
        "interval": "5m",
    }


def test_get_run_simple_rejects_non_numeric_contracts(client):
    response = client.get("/api/backtest/run/NQ?contracts=abc")

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /position-size (real stats + real scaler)
# ---------------------------------------------------------------------------


def _trade_dict(win: bool, pnl: float) -> dict:
    return {
        "entry_time": "2024-01-02T09:30:00",
        "exit_time": "2024-01-02T10:15:00",
        "entry_price": 100.0,
        "exit_price": 105.0 if win else 95.0,
        "direction": "LONG",
        "pnl": pnl,
        "win": win,
    }


def test_position_size_runs_the_real_pipeline(client):
    response = client.post(
        "/api/backtest/position-size",
        json={
            "recent_trades": [_trade_dict(True, 400.0), _trade_dict(True, 250.0), _trade_dict(True, 100.0)],
            "signal_strength": 85.0,
            "account_balance": 25000,
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    for key in ("contracts", "base_size", "strength_multiplier", "confidence", "kelly_fraction", "reason"):
        assert key in data, f"missing {key}"
    assert data["consecutive_wins"] == 3
    assert data["consecutive_losses"] == 0
    assert isinstance(data["contracts"], int)


def test_position_size_empty_history_still_recommends_base(client):
    response = client.post("/api/backtest/position-size", json={"recent_trades": []})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["consecutive_wins"] == 0
    assert data["contracts"] >= 1  # base size, never zero


def test_position_size_malformed_trade_is_a_500_envelope(client):
    bad = _trade_dict(True, 100.0)
    del bad["pnl"]

    response = client.post("/api/backtest/position-size", json={"recent_trades": [bad]})

    assert response.status_code == 500
    assert "pnl" in response.json()["detail"]


def test_position_size_invalid_timestamp_is_a_500_envelope(client):
    bad = _trade_dict(True, 100.0)
    bad["entry_time"] = "not-a-date"

    response = client.post("/api/backtest/position-size", json={"recent_trades": [bad]})

    assert response.status_code == 500


def test_position_size_validation_error_is_422(client):
    response = client.post("/api/backtest/position-size", json={"recent_trades": "not-a-list"})

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /regime + GET /
# ---------------------------------------------------------------------------


def test_regime_maps_the_analysis_fields(client, regime):
    response = client.get("/api/backtest/regime?symbol=NQ")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["regime"] == "RANGE_BOUND"
    assert data["confidence"] == 61.2  # rounded to 1 decimal
    assert data["recommended_bias"] == "neutral"
    assert data["key_support"] == 19800.5
    assert data["key_resistance"] == 20100.25
    assert data["reasoning"] == "offline reasoning"
    assert data["timestamp"].startswith("2024-06-01T12:00")


def test_regime_none_levels_map_to_null(client, regime):
    regime["analysis"] = _regime_analysis(regime="CHOPPY_AVOID", key_support=None, key_resistance=None)

    response = client.get("/api/backtest/regime")

    data = response.json()["data"]
    assert data["key_support"] is None
    assert data["key_resistance"] is None


def test_regime_classifier_failure_is_a_500_envelope(client, monkeypatch):
    async def _boom(symbol="NQ"):
        raise RuntimeError("classifier down")

    monkeypatch.setattr(be, "classify_current_regime", _boom)

    response = client.get("/api/backtest/regime?symbol=NQ")

    assert response.status_code == 500
    assert "classifier down" in response.json()["detail"]


def test_backtest_home_serves_html(client):
    response = client.get("/api/backtest/")

    assert response.status_code == 200
    assert "Backtesting & Optimization" in response.text
    assert "/api/backtest/run/NQ" in response.text
