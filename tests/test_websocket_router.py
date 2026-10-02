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
import queue
import threading
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


RECEIVE_TIMEOUT_SECONDS = 5.0


def _receive_frame(ws, method_name: str, *args):
    """A WebSocketTestSession receive that FAILS FAST instead of hanging.

    ``WebSocketTestSession.receive*`` blocks forever when the server stops
    sending frames without closing the socket (e.g. a regression in the
    endpoint). The blocking call runs in a daemon thread; on timeout the
    test fails with a clear message instead of hanging the whole run.
    """
    outcome: queue.Queue = queue.Queue()

    def _worker():
        try:
            outcome.put(("ok", getattr(ws, method_name)(*args)))
        except BaseException as exc:  # WebSocketDisconnect et al. -- re-raised below
            outcome.put(("err", exc))

    threading.Thread(target=_worker, daemon=True, name=f"ws-{method_name}-guard").start()
    try:
        status, payload = outcome.get(timeout=RECEIVE_TIMEOUT_SECONDS)
    except queue.Empty:
        pytest.fail(
            f"{method_name} produced no frame within {RECEIVE_TIMEOUT_SECONDS:.0f}s -- "
            "the server stopped sending without closing the socket (regression?)"
        )
    if status == "err":
        raise payload
    return payload


def recv_json(ws):
    return _receive_frame(ws, "receive_json")


def recv_text(ws):
    return _receive_frame(ws, "receive_text")


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
        hello = recv_json(ws)
        assert hello["type"] == "test_connection"
        assert hello["message"] == "Test WebSocket is working!"

        ws.send_json({"hello": 1})
        echo = recv_json(ws)
        assert echo["type"] == "echo"
        assert echo["received"] == {"hello": 1}
        assert echo["timestamp"]


def test_ws_test_closes_on_bad_json(client):
    from starlette.websockets import WebSocketDisconnect

    with client.websocket_connect("/ws/test") as ws:
        recv_json(ws)  # greeting
        ws.send_text("not json{")
        # The server closes the socket explicitly after the parse error.
        with pytest.raises(WebSocketDisconnect):
            recv_json(ws)


# ---------------------------------------------------------------------------
# /ws/market (push loop)
# ---------------------------------------------------------------------------


def test_ws_market_streams_updates(client, fast_loop, monkeypatch):
    collector = _FakeCollector(internals={"advance": 10, "decline": 5, "ratio": 2.0})
    monkeypatch.setattr(deps, "collector", collector)

    with client.websocket_connect("/ws/market") as ws:
        established = recv_json(ws)
        assert established["type"] == "connection_established"

        first = recv_json(ws)
        assert first["type"] == "market_update"
        assert first["data"] == {"advance": 10, "decline": 5, "ratio": 2.0}
        assert first["message_id"] == 0

        second = recv_json(ws)
        assert second["type"] == "market_update"
        assert second["message_id"] == 1

    assert collector.calls >= 2


def test_ws_market_reports_missing_collector(client, fast_loop):
    with client.websocket_connect("/ws/market") as ws:
        assert recv_json(ws)["type"] == "connection_established"
        status = recv_json(ws)
        assert status["type"] == "status"
        assert status["message"] == "Collector not initialized"


def test_ws_market_survives_collector_errors(client, fast_loop, monkeypatch):
    monkeypatch.setattr(deps, "collector", _FakeCollector(raises=RuntimeError("feed down")))

    with client.websocket_connect("/ws/market") as ws:
        recv_json(ws)  # connection_established
        error = recv_json(ws)
        assert error["type"] == "error"
        assert "feed down" in error["message"]
        # The loop keeps running rather than dropping the connection.
        another = recv_json(ws)
        assert another["type"] == "error"


def test_ws_market_none_internals_is_null_data(client, fast_loop, monkeypatch):
    monkeypatch.setattr(deps, "collector", _FakeCollector(internals=None))

    with client.websocket_connect("/ws/market") as ws:
        recv_json(ws)
        update = recv_json(ws)
        assert update["type"] == "market_update"
        assert update["data"] is None


def test_ws_market_nan_internals_are_strict_json(client, fast_loop, monkeypatch):
    """NaN/inf in the feed must arrive as null, not as bare NaN/Infinity."""
    monkeypatch.setattr(
        deps, "collector", _FakeCollector(internals={"breadth": math.nan, "ratio": math.inf, "ok": 1.5})
    )

    with client.websocket_connect("/ws/market") as ws:
        recv_json(ws)
        raw = recv_text(ws)
        parsed = strict_json(raw)  # raises on NaN/Infinity tokens
        assert "market_update" in raw
        assert parsed["data"] == {"breadth": None, "ratio": None, "ok": 1.5}


def test_ws_market_fans_out_to_several_clients(client, fast_loop, monkeypatch):
    monkeypatch.setattr(deps, "collector", _FakeCollector(internals={"advance": 7}))

    with client.websocket_connect("/ws/market") as ws_a, client.websocket_connect("/ws/market") as ws_b:
        recv_json(ws_a)  # a: established
        recv_json(ws_b)  # b: established
        update_a = recv_json(ws_a)
        update_b = recv_json(ws_b)
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

        accepted = recv_json(ws)
        assert accepted["phase"] == "accepted"
        assert accepted["data"] == {"query": "Is SPY healthy?", "symbols": ["SPY"]}

        plan = recv_json(ws)
        assert plan["phase"] == "plan"
        assert plan["data"] == {"steps": 2}

        agent_done = recv_json(ws)
        assert agent_done["phase"] == "agent_done"
        assert agent_done["agent_name"] == "Macro"
        assert agent_done["tools_used"] == ["get_breadth"]

        complete = recv_json(ws)
        assert complete["phase"] == "complete"


def test_stream_analysis_missing_query_is_rejected(client, fake_orchestrator):
    with client.websocket_connect("/ws/stream-analysis") as ws:
        ws.send_json({"symbols": ["SPY"]})

        error = recv_json(ws)
        assert error["phase"] == "error"
        assert "Missing 'query'" in error["content"]


def test_stream_analysis_non_dict_request_gets_guidance(client, fake_orchestrator):
    with client.websocket_connect("/ws/stream-analysis") as ws:
        ws.send_json([1, 2, 3])

        error = recv_json(ws)
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

        accepted = recv_json(ws)
        assert accepted["phase"] == "accepted"
        assert recv_json(ws)["phase"] == "complete"

    assert captured == {"query": "quick check", "symbols": ["SPY"], "include_breadth": True}


def test_stream_analysis_pipeline_error_surfaces(client, fake_orchestrator):
    fake_orchestrator.raises = RuntimeError("agent blew up")

    with client.websocket_connect("/ws/stream-analysis") as ws:
        ws.send_json({"query": "anything"})

        assert recv_json(ws)["phase"] == "accepted"
        error = recv_json(ws)
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
        recv_json(ws)  # accepted
        parsed = strict_json(recv_text(ws))
        assert parsed["data"] == {"metric": None}
        assert recv_json(ws)["phase"] == "complete"
