"""Yield curve API smoke tests using FastAPI TestClient with monkeypatched history."""
from datetime import date
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.yield_curve.history import SnapshotData


def _mock_snap(d: date, s2s10s: float = 10.0) -> SnapshotData:
    return SnapshotData(
        date=d,
        curve={"3mo": 5.0, "2y": 4.5, "10y": 4.6, "30y": 4.8},
        spreads={"2s10s": s2s10s, "3m10y": -40.0, "5s30s": 20.0, "2s30s": 30.0},
        shape="NORMAL",
        shape_trend="STEEPENING",
        recession_prob_nyfed=0.15,
        spread_2s10s_delta_5d=5.0,
        spread_2s10s_delta_30d=20.0,
        zscore_2s10s_90d=0.5,
    )


@pytest.fixture
def client():
    from src.api.main import app
    return TestClient(app)


def test_current_endpoint_returns_latest(client):
    with patch("src.api.routers.yield_curve._get_history") as mock_h, \
         patch("src.api.routers.yield_curve._compute_staleness", return_value=(False, 0)):
        h = MagicMock()
        h.get_history.return_value = [_mock_snap(date(2026, 6, 23))]
        mock_h.return_value = (h, MagicMock())
        r = client.get("/api/yield-curve/current")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["shape"] == "NORMAL"
    assert body["data"]["spreads"]["2s10s"] == 10.0
    assert body["data"]["stale"] is False


def test_history_endpoint_returns_list(client):
    with patch("src.api.routers.yield_curve._get_history") as mock_h:
        h = MagicMock()
        h.get_history.return_value = [_mock_snap(date(2026, 6, 23) - timedelta(days=i)) for i in range(5)]
        mock_h.return_value = (h, MagicMock())
        r = client.get("/api/yield-curve/history?days=5")
    assert r.status_code == 200
    body = r.json()
    assert "snapshots" in body["data"]
    assert len(body["data"]["snapshots"]) == 5


def test_alerts_endpoint_returns_list(client):
    with patch("src.api.routers.yield_curve._get_alerts") as mock_a:
        session = MagicMock()
        row = MagicMock()
        row.triggered_at = date(2026, 6, 23)
        row.rule_name = "rapid_steepening"
        row.priority = "HIGH"
        row.message = "test"
        row.trigger_value = None
        row.prior_value = None
        row.delta = None
        row.zscore = None
        query_chain = MagicMock()
        query_chain.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [row]
        session.query.return_value = query_chain
        mock_a.return_value = session
        r = client.get("/api/yield-curve/alerts?days=30")
    assert r.status_code == 200
    body = r.json()
    assert "alerts" in body["data"]
    assert len(body["data"]["alerts"]) == 1


def test_config_endpoint_returns_thresholds(client):
    r = client.get("/api/yield-curve/config")
    assert r.status_code == 200
    body = r.json()
    assert "thresholds" in body["data"]
    assert "steepen_bps_5d" in body["data"]["thresholds"]