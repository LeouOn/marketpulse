"""Offline coverage for src/api/risk_endpoints.py (cycle 7).

The module had no dedicated tests (only route-snapshot references). These tests
mount all three routers (risk / journal / alerts) on a fresh FastAPI app with
fresh managers and a fake alert manager, so no state leaks between tests and
nothing touches the network.

Bugs pinned here (each fix's test fails on the pre-change module):

* non-finite prices / NaN pnl passed risk validation and produced NaN payloads
  -> ``JSONResponse`` 500 (``allow_nan=False``);
* ``point_value=0`` in /calculate-position-size -> ZeroDivisionError -> 500;
* unknown direction/side values were silently treated as ``short`` by the
  ``.lower() == "long"`` checks, inverting the trade;
* non-positive contracts / risk_amount produced nonsense approvals;
* an all-winning journal yields ``profit_factor = inf`` -> 500 on
  /api/journal/analyze and /api/journal/by-setup (now ``null`` via ``to_builtin``).
"""

from __future__ import annotations

import json
import math

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.alerts.alert_manager import AlertChannel, AlertPriority
from src.analysis.risk_manager import RiskManager
from src.api import risk_endpoints as re_mod
from src.journal.trade_tracker import TradeJournal
from src.state.position_manager import PositionManager


class _FakeAlertManager:
    """Deterministic stand-in: records calls, never touches D-Bus/network."""

    def __init__(self):
        self.sent: list[tuple] = []

    async def send_alert(self, title, message, priority):
        self.sent.append(("alert", title, priority))
        return {
            AlertChannel.CONSOLE: True,
            AlertChannel.TELEGRAM: False,
            AlertChannel.EMAIL: False,
            AlertChannel.WEBHOOK: False,
            AlertChannel.DESKTOP: False,
        }

    async def send_position_update(self, symbol, action, price, priority=None, pnl=None):
        self.sent.append(("position", symbol, action))
        return None


@pytest.fixture
def client(monkeypatch, tmp_path) -> TestClient:
    fake_alerts = _FakeAlertManager()
    # Isolate PositionManager's on-disk state (it persists to data/state/positions.json
    # relative to CWD, so un-isolated instances share state via the file) and keep
    # every manager fresh per test.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(re_mod, "risk_manager", RiskManager())
    monkeypatch.setattr(re_mod, "position_manager", PositionManager(state_file=str(tmp_path / "positions.json")))
    monkeypatch.setattr(re_mod, "trade_journal", TradeJournal())
    monkeypatch.setattr(re_mod, "alert_manager", fake_alerts)

    app = FastAPI()
    for router in (re_mod.risk_router, re_mod.journal_router, re_mod.alerts_router):
        app.include_router(router)
    # raise_server_exceptions=False so serialization failures surface as real
    # 500 responses (the bug) instead of raising out of the test client.
    return TestClient(app, raise_server_exceptions=False)


def _open_payload(**overrides) -> dict:
    payload = {
        "symbol": "MNQ",
        "side": "long",
        "entry_price": 100.0,
        "stop_loss": 99.0,
        "take_profit": 102.0,
        "contracts": 1,
        "point_value": 2.0,
    }
    payload.update(overrides)
    return payload


def _post_raw_json(client: TestClient, url: str, body: str):
    """POST a raw JSON body the client-side encoder would refuse (NaN/Infinity).

    Python's json.loads accepts the NaN/Infinity literals, and this httpx fork
    refuses to *serialize* them, so non-finite payloads must be sent as text.
    """
    return client.post(url, content=body, headers={"Content-Type": "application/json"})


def _open_and_close(client: TestClient, exit_price: float = 102.0, exit_reason: str = "target_hit") -> dict:
    opened = client.post("/api/risk/positions/open", json=_open_payload()).json()
    assert opened["success"] is True
    closed = client.post(
        "/api/risk/positions/close",
        json={"position_id": opened["data"]["position_id"], "exit_price": exit_price, "exit_reason": exit_reason},
    )
    assert closed.status_code == 200, closed.text
    return closed.json()["data"]


# ---------------------------------------------------------------------------
# POST /api/risk/validate-trade
# ---------------------------------------------------------------------------


def test_validate_trade_approves_valid_long(client):
    r = client.post(
        "/api/risk/validate-trade",
        json={
            "symbol": "MNQ",
            "entry_price": 100.0,
            "stop_loss": 99.0,
            "take_profit": 102.0,
            "direction": "long",
            "contracts": 1,
            "point_value": 2.0,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["approved"] is True
    assert data["risk_metrics"]["total_risk"] == pytest.approx(2.0)  # 1 point x $2 x 1 contract
    # suggested_contracts is None unless the requested size had to be adjusted.
    assert data["suggested_contracts"] is None or data["suggested_contracts"] >= 1


def test_validate_trade_rejects_stop_not_beyond_entry(client):
    r = client.post(
        "/api/risk/validate-trade",
        json={
            "symbol": "MNQ",
            "entry_price": 100.0,
            "stop_loss": 101.0,  # long: stop must be below entry
            "take_profit": 102.0,
            "direction": "long",
            "contracts": 1,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["approved"] is False
    assert "stop" in data["reason"].lower()


@pytest.mark.parametrize("field", ["entry_price", "stop_loss", "take_profit"])
@pytest.mark.parametrize("literal", ["NaN", "Infinity"])
def test_validate_trade_rejects_non_finite_prices(client, field, literal):
    body = (
        '{"symbol": "MNQ", "entry_price": 100.0, "stop_loss": 99.0, '
        '"take_profit": 102.0, "direction": "long", "contracts": 1, '
        f'"{field}": {literal}}}'
    )
    r = _post_raw_json(client, "/api/risk/validate-trade", body)
    assert r.status_code == 400, f"{field}={literal}: expected 400, got {r.status_code}"


def test_validate_trade_rejects_unknown_direction(client):
    payload = {
        "symbol": "MNQ",
        "entry_price": 100.0,
        "stop_loss": 99.0,
        "take_profit": 102.0,
        "direction": "lobg",  # typo must not silently mean "short"
        "contracts": 1,
    }
    r = client.post("/api/risk/validate-trade", json=payload)
    assert r.status_code == 400, r.text


def test_validate_trade_rejects_non_positive_contracts(client):
    payload = {
        "symbol": "MNQ",
        "entry_price": 100.0,
        "stop_loss": 99.0,
        "take_profit": 102.0,
        "direction": "long",
        "contracts": -5,
    }
    r = client.post("/api/risk/validate-trade", json=payload)
    assert r.status_code == 400, r.text


# ---------------------------------------------------------------------------
# POST /api/risk/calculate-position-size
# ---------------------------------------------------------------------------


def test_calculate_position_size_math_is_consistent(client):
    r = client.post(
        "/api/risk/calculate-position-size",
        params={"entry_price": 100.0, "stop_loss": 99.0, "direction": "long", "risk_amount": 200.0, "point_value": 2.0},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert isinstance(data["contracts"], int) and data["contracts"] >= 1
    assert data["risk_points"] == pytest.approx(1.0)
    assert data["risk_per_contract"] == pytest.approx(2.0)
    assert data["total_risk"] == pytest.approx(data["risk_per_contract"] * data["contracts"])


def test_calculate_position_size_rejects_zero_point_value(client):
    r = client.post(
        "/api/risk/calculate-position-size",
        params={"entry_price": 100.0, "stop_loss": 99.0, "direction": "long", "point_value": 0.0},
    )
    assert r.status_code == 400, r.text


def test_calculate_position_size_rejects_nan_entry(client):
    r = client.post(
        "/api/risk/calculate-position-size",
        params={"entry_price": "nan", "stop_loss": 99.0, "direction": "long"},
    )
    assert r.status_code == 400, f"expected 400, got {r.status_code}"


def test_calculate_position_size_rejects_non_positive_risk_amount(client):
    r = client.post(
        "/api/risk/calculate-position-size",
        params={"entry_price": 100.0, "stop_loss": 99.0, "direction": "long", "risk_amount": -10.0},
    )
    assert r.status_code == 400, r.text


# ---------------------------------------------------------------------------
# POST /api/risk/record-trade-result, GET /api/risk/risk-summary, POST /api/risk/reset-daily
# ---------------------------------------------------------------------------


def test_record_trade_result_updates_summary(client):
    r = client.post("/api/risk/record-trade-result", json={"pnl": -50.0})
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["trade_recorded"] is True
    assert data["daily_pnl"] == pytest.approx(-50.0)
    assert data["consecutive_losses"] == 1
    assert data["can_trade"] is True


def test_record_trade_result_rejects_nan_pnl(client):
    r = _post_raw_json(client, "/api/risk/record-trade-result", '{"pnl": NaN}')
    assert r.status_code == 400, f"expected 400, got {r.status_code}"


def test_risk_summary_shape(client):
    r = client.get("/api/risk/risk-summary")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    for key in ("account_size", "daily_pnl", "portfolio_heat", "consecutive_losses", "risk_level", "can_trade"):
        assert key in data
    assert data["can_trade"] is True


def test_reset_daily_clears_state(client):
    client.post("/api/risk/record-trade-result", json={"pnl": -50.0})
    r = client.post("/api/risk/reset-daily")
    assert r.status_code == 200, r.text
    summary = client.get("/api/risk/risk-summary").json()["data"]
    assert summary["daily_pnl"] == pytest.approx(0.0)
    assert summary["daily_trades"] == 0
    # consecutive_losses intentionally survives a *daily* reset (it is a streak counter).
    assert summary["consecutive_losses"] == 1


# ---------------------------------------------------------------------------
# POST /api/risk/positions/open, GET /api/risk/positions/open, /positions/close, /positions/state
# ---------------------------------------------------------------------------


def test_open_position_creates_and_lists(client):
    r = client.post("/api/risk/positions/open", json=_open_payload())
    assert r.status_code == 200, r.text
    opened = r.json()
    assert opened["success"] is True
    assert opened["data"]["position_id"]

    listing = client.get("/api/risk/positions/open").json()["data"]
    assert listing["total_positions"] == 1
    pos = listing["positions"][0]
    assert pos["symbol"] == "MNQ"
    assert pos["side"] == "long"
    assert pos["entry_price"] == pytest.approx(100.0)

    summary = client.get("/api/risk/risk-summary").json()["data"]
    assert summary["open_positions"] == 1


def test_open_position_rejects_non_finite_entry(client):
    body = json.dumps(_open_payload())
    body = body.replace('"entry_price": 100.0', '"entry_price": NaN')
    r = _post_raw_json(client, "/api/risk/positions/open", body)
    assert r.status_code == 400, f"expected 400, got {r.status_code}"
    assert client.get("/api/risk/positions/open").json()["data"]["total_positions"] == 0


def test_open_position_rejects_unknown_side(client):
    r = client.post("/api/risk/positions/open", json=_open_payload(side="lobg"))
    assert r.status_code == 400, r.text
    assert client.get("/api/risk/positions/open").json()["data"]["total_positions"] == 0


def test_open_position_rejects_zero_contracts(client):
    r = client.post("/api/risk/positions/open", json=_open_payload(contracts=0))
    assert r.status_code == 400, r.text


def test_open_position_risk_rejected_returns_success_false(client):
    r = client.post("/api/risk/positions/open", json=_open_payload(stop_loss=101.0))  # invalid for long
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is False
    assert body["error"]
    assert client.get("/api/risk/positions/open").json()["data"]["total_positions"] == 0


def test_close_position_realizes_pnl_and_journals(client):
    closed = _open_and_close(client, exit_price=102.0, exit_reason="target_hit")
    assert closed["realized_pnl"] == pytest.approx(4.0)  # 2 points x $2 x 1 contract
    assert closed["status"] == "target_hit"

    summary = client.get("/api/risk/risk-summary").json()["data"]
    assert summary["daily_pnl"] == pytest.approx(4.0)

    # All-win journal: profit_factor is inf -> must serialize as null, not 500.
    analysis = client.post("/api/journal/analyze", json={})
    assert analysis.status_code == 200, analysis.text
    data = analysis.json()["data"]
    assert data["total_trades"] == 1
    assert data["win_rate"] == "100.00%"
    assert data["profit_factor"] is None  # inf (no losses) serializes as null


def test_close_position_unknown_id_is_404(client):
    r = client.post(
        "/api/risk/positions/close",
        json={"position_id": "does-not-exist", "exit_price": 100.0},
    )
    assert r.status_code == 404, r.text


def test_close_position_unknown_exit_reason_defaults_to_closed(client):
    closed = _open_and_close(client, exit_price=100.5, exit_reason="who-knows")
    assert closed["status"] == "closed"


def test_positions_open_empty(client):
    r = client.get("/api/risk/positions/open")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["total_positions"] == 0
    assert data["positions"] == []
    assert data["total_risk"] == pytest.approx(0.0)


def test_position_state_summary(client):
    r = client.get("/api/risk/positions/state")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert isinstance(body["data"], dict) and body["data"]


# ---------------------------------------------------------------------------
# /api/journal/*
# ---------------------------------------------------------------------------


def test_journal_analyze_empty(client):
    r = client.post("/api/journal/analyze", json={})
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["total_trades"] == 0
    assert data["win_rate"] == "0.00%"
    assert data["sharpe_ratio"] is None


def test_journal_by_setup_all_win_profit_factor_is_null(client):
    _open_and_close(client, exit_price=102.0)
    _open_and_close(client, exit_price=103.0)
    r = client.get("/api/journal/by-setup")
    assert r.status_code == 200, r.text
    setups = r.json()["data"]["setups"]
    assert len(setups) == 1
    assert setups[0]["total_trades"] == 2
    assert setups[0]["win_rate"] == "100.00%"
    assert setups[0]["profit_factor"] is None  # inf (no losses) serializes as null


def test_journal_by_setup_mixed_trades_finite_profit_factor(client):
    _open_and_close(client, exit_price=102.0)  # +4
    _open_and_close(client, exit_price=98.5)  # -3
    r = client.get("/api/journal/by-setup")
    assert r.status_code == 200, r.text
    setups = r.json()["data"]["setups"]
    assert setups[0]["profit_factor"] == pytest.approx(4.0 / 3.0)
    assert math.isfinite(setups[0]["profit_factor"])


def test_journal_by_session_rows(client):
    _open_and_close(client, exit_price=102.0)
    r = client.get("/api/journal/by-session")
    assert r.status_code == 200, r.text
    sessions = r.json()["data"]["sessions"]
    assert len(sessions) >= 1
    assert sessions[0]["total_trades"] >= 1


def test_journal_insights(client):
    r = client.get("/api/journal/insights?days=30")
    assert r.status_code == 200, r.text
    assert isinstance(r.json()["data"], dict)


# ---------------------------------------------------------------------------
# POST /api/alerts/send
# ---------------------------------------------------------------------------


def test_alert_send_reports_channels(client, monkeypatch):
    r = client.post("/api/alerts/send", json={"title": "t", "message": "m", "priority": "high"})
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["sent_to"] == ["console"]
    assert "telegram" in data["failed"]


def test_alert_send_unknown_priority_defaults_to_medium(client):
    r = client.post("/api/alerts/send", json={"title": "t", "message": "m", "priority": "urgent"})
    assert r.status_code == 200, r.text
    fake = re_mod.alert_manager
    assert fake.sent[0][2] is AlertPriority.MEDIUM
