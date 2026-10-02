"""Offline tests for src/api/routers/websocket.py.

The app mounts only the websocket router. The data feed (deps.collector) and
the analysis orchestrator are faked; asyncio.sleep inside the module is
replaced with a tiny real sleep so the 30s push loop runs fast. No network,
no external sockets.
"""

from __future__ import annotations

import asyncio
import json
import math
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routers import deps
from src.api.routers import websocket as ws_mod


def _reject_constant(token):
    raise ValueError(f"non-strict JSON token: {token}")


def strict_json(text: str):
    """Parse JSON the way a browser would: NaN/Infinity tokens are invalid."""
    return json.loads(text, parse_constant=_reject_constant)


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(ws_mod.router)
    return TestClient(app)


@pytest.fixture
def fast_loop(monkeypatch):
    """Replace the module's asyncio with one whose sleep is ~instant."""
    real_sleep = asyncio.sleep
    monkeypatch.setattr(ws_mod, "asyncio", SimpleNamespace(sleep=lambda *_: real_sleep(0.001)))


class _FakeCollector:
    def __init__(self, internals=None, raises=None):
        self._internals = internals
        self._raises = raises
        self.calls = 0

    async def collect_market_internals(self):
        self.calls += 1
        if self._raises:
            raise self._raises
        return self._internals


@pytest.fixture(autouse=True)
def _no_collector(monkeypatch):
    monkeypatch.setattr(deps, "collector", None)


# ---------------------------------------------------------------------------
# /ws/test (echo)
# ---------------------------------------------------------------------------


def test_ws_test_echoes_json(client):
    with client.websocket_connect("/ws/test") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "test_connection"
        assert hello["message"] == "Test WebSocket is working!"

        ws.send_json({"hello": 1})
        echo = ws.receive_json()
        assert echo["type"] == "echo"
        assert echo["received"] == {"hello": 1}
        assert echo["timestamp"]


def test_ws_test_closes_on_bad_json(client):
    from starlette.websockets import WebSocketDisconnect

    with client.websocket_connect("/ws/test") as ws:
        ws.receive_json()  # greeting
        ws.send_text("not json{")
        # The server closes the socket explicitly after the parse error.
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


# ---------------------------------------------------------------------------
# /ws/market (push loop)
# ---------------------------------------------------------------------------


def test_ws_market_streams_updates(client, fast_loop, monkeypatch):
    collector = _FakeCollector(internals={"advance": 10, "decline": 5, "ratio": 2.0})
    monkeypatch.setattr(deps, "collector", collector)

    with client.websocket_connect("/ws/market") as ws:
        established = ws.receive_json()
        assert established["type"] == "connection_established"

        first = ws.receive_json()
        assert first["type"] == "market_update"
        assert first["data"] == {"advance": 10, "decline": 5, "ratio": 2.0}
        assert first["message_id"] == 0

        second = ws.receive_json()
        assert second["type"] == "market_update"
        assert second["message_id"] == 1

    assert collector.calls >= 2


def test_ws_market_reports_missing_collector(client, fast_loop):
    with client.websocket_connect("/ws/market") as ws:
        assert ws.receive_json()["type"] == "connection_established"
        status = ws.receive_json()
        assert status["type"] == "status"
        assert status["message"] == "Collector not initialized"


def test_ws_market_survives_collector_errors(client, fast_loop, monkeypatch):
    monkeypatch.setattr(deps, "collector", _FakeCollector(raises=RuntimeError("feed down")))

    with client.websocket_connect("/ws/market") as ws:
        ws.receive_json()  # connection_established
        error = ws.receive_json()
        assert error["type"] == "error"
        assert "feed down" in error["message"]
        # The loop keeps running rather than dropping the connection.
        another = ws.receive_json()
        assert another["type"] == "error"


def test_ws_market_none_internals_is_null_data(client, fast_loop, monkeypatch):
    monkeypatch.setattr(deps, "collector", _FakeCollector(internals=None))

    with client.websocket_connect("/ws/market") as ws:
        ws.receive_json()
        update = ws.receive_json()
        assert update["type"] == "market_update"
        assert update["data"] is None


def test_ws_market_nan_internals_are_strict_json(client, fast_loop, monkeypatch):
    """NaN/inf in the feed must arrive as null, not as bare NaN/Infinity."""
    monkeypatch.setattr(
        deps, "collector", _FakeCollector(internals={"breadth": math.nan, "ratio": math.inf, "ok": 1.5})
    )

    with client.websocket_connect("/ws/market") as ws:
        ws.receive_json()
        raw = ws.receive_text()
        parsed = strict_json(raw)  # raises on NaN/Infinity tokens
        assert "market_update" in raw
        assert parsed["data"] == {"breadth": None, "ratio": None, "ok": 1.5}


def test_ws_market_fans_out_to_several_clients(client, fast_loop, monkeypatch):
    monkeypatch.setattr(deps, "collector", _FakeCollector(internals={"advance": 7}))

    with client.websocket_connect("/ws/market") as ws_a, client.websocket_connect("/ws/market") as ws_b:
        ws_a.receive_json()  # a: established
        ws_b.receive_json()  # b: established
        update_a = ws_a.receive_json()
        update_b = ws_b.receive_json()
        assert update_a["type"] == update_b["type"] == "market_update"
        assert update_a["data"] == update_b["data"] == {"advance": 7}


# ---------------------------------------------------------------------------
# /ws/stream-analysis
# ---------------------------------------------------------------------------


class _FakeOrchestrator:
    events = []
    raises = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def analyze_streaming(self, query, symbols, include_breadth):
        if _FakeOrchestrator.raises:
            raise _FakeOrchestrator.raises
        for event in _FakeOrchestrator.events:
            yield event


@pytest.fixture
def fake_orchestrator(monkeypatch):
    import src.llm.agents.orchestrator as orch_mod

    _FakeOrchestrator.events = []
    _FakeOrchestrator.raises = None
    monkeypatch.setattr(orch_mod, "MarketAnalysisOrchestrator", _FakeOrchestrator)
    return _FakeOrchestrator


def test_stream_analysis_streams_phases(client, fake_orchestrator):
    fake_orchestrator.events = [
        SimpleNamespace(phase="plan", agent_name=None, content="planning", tools_used=[], data={"steps": 2}),
        SimpleNamespace(
            phase="agent_done", agent_name="Macro", content="macro view", tools_used=["get_breadth"], data={}
        ),
    ]

    with client.websocket_connect("/ws/stream-analysis") as ws:
        ws.send_json({"query": "Is SPY healthy?", "symbols": ["SPY"], "include_breadth": False})

        accepted = ws.receive_json()
        assert accepted["phase"] == "accepted"
        assert accepted["data"] == {"query": "Is SPY healthy?", "symbols": ["SPY"]}

        plan = ws.receive_json()
        assert plan["phase"] == "plan"
        assert plan["data"] == {"steps": 2}

        agent_done = ws.receive_json()
        assert agent_done["phase"] == "agent_done"
        assert agent_done["agent_name"] == "Macro"
        assert agent_done["tools_used"] == ["get_breadth"]

        complete = ws.receive_json()
        assert complete["phase"] == "complete"


def test_stream_analysis_missing_query_is_rejected(client, fake_orchestrator):
    with client.websocket_connect("/ws/stream-analysis") as ws:
        ws.send_json({"symbols": ["SPY"]})

        error = ws.receive_json()
        assert error["phase"] == "error"
        assert "Missing 'query'" in error["content"]


def test_stream_analysis_non_dict_request_gets_guidance(client, fake_orchestrator):
    with client.websocket_connect("/ws/stream-analysis") as ws:
        ws.send_json([1, 2, 3])

        error = ws.receive_json()
        assert error["phase"] == "error"
        assert "Invalid request format" in error["content"]


def test_stream_analysis_defaults_symbols_and_breadth(client, fake_orchestrator, monkeypatch):
    captured: dict = {}

    async def _stream(self, query, symbols, include_breadth):
        captured.update(query=query, symbols=symbols, include_breadth=include_breadth)
        return
        yield  # pragma: no cover - makes this an async generator

    monkeypatch.setattr(_FakeOrchestrator, "analyze_streaming", _stream)

    with client.websocket_connect("/ws/stream-analysis") as ws:
        ws.send_json({"query": "quick check"})

        accepted = ws.receive_json()
        assert accepted["phase"] == "accepted"
        assert ws.receive_json()["phase"] == "complete"

    assert captured == {"query": "quick check", "symbols": ["SPY"], "include_breadth": True}


def test_stream_analysis_pipeline_error_surfaces(client, fake_orchestrator):
    fake_orchestrator.raises = RuntimeError("agent blew up")

    with client.websocket_connect("/ws/stream-analysis") as ws:
        ws.send_json({"query": "anything"})

        assert ws.receive_json()["phase"] == "accepted"
        error = ws.receive_json()
        assert error["phase"] == "error"
        assert "agent blew up" in error["content"]


def test_stream_analysis_event_data_is_strict_json(client, fake_orchestrator):
    fake_orchestrator.events = [
        SimpleNamespace(
            phase="agent_done",
            agent_name="Data",
            content="fetched",
            tools_used=[],
            data={"metric": math.nan},
        )
    ]

    with client.websocket_connect("/ws/stream-analysis") as ws:
        ws.send_json({"query": "q"})
        ws.receive_json()  # accepted
        parsed = strict_json(ws.receive_text())
        assert parsed["data"] == {"metric": None}
        assert ws.receive_json()["phase"] == "complete"
