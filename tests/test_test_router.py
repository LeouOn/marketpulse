"""Offline tests for ``src/api/routers/test.py`` (the /api/test debug router).

No sockets, no live data pulls: MarketPulseCollector is replaced by a fake
whose initialize()/collect_market_internals() are immediate canned calls, and
the /status globals are driven via monkeypatch. Every test fails fast -- all
fakes are synchronous returns.
"""

from __future__ import annotations

import math
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routers import deps
from src.api.routers import test as test_router_module
from src.api.routers.test import router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class _FakeCollector:
    """Stands in for MarketPulseCollector; records calls, returns canned data."""

    next_internals: dict = {}
    init_error: Exception | None = None
    collect_error: Exception | None = None
    instances: list["_FakeCollector"] = []

    def __init__(self, *args, **kwargs):
        self.initialized = False
        self.collected = False
        _FakeCollector.instances.append(self)

    async def initialize(self):
        if _FakeCollector.init_error:
            raise _FakeCollector.init_error
        self.initialized = True

    async def collect_market_internals(self):
        if _FakeCollector.collect_error:
            raise _FakeCollector.collect_error
        self.collected = True
        return _FakeCollector.next_internals

    @classmethod
    def reset(cls, internals=None, init_error=None, collect_error=None):
        cls.next_internals = internals or {}
        cls.init_error = init_error
        cls.collect_error = collect_error
        cls.instances = []


@pytest.fixture
def fake_collector(monkeypatch):
    _FakeCollector.reset()
    monkeypatch.setattr(test_router_module, "MarketPulseCollector", _FakeCollector)
    return _FakeCollector


GOOD_INTERNALS = {
    "data_source": "yahoo-fake",
    "spy": {"price": 500.25, "change": 1.5, "change_pct": 0.3, "volume": 1000, "timestamp": "t"},
    "qqq": {"price": 480.0, "change": -1.0, "change_pct": -0.2, "volume": 500, "timestamp": "t"},
    "flat": {"price": 0, "change": 0, "change_pct": 0, "volume": 0, "timestamp": "t"},
}


# ---------------------------------------------------------------------------
# GET /api/test/status -- pure read of module globals
# ---------------------------------------------------------------------------


def test_status_reports_uninitialized_state(client, monkeypatch):
    monkeypatch.setattr(deps, "collector", None)
    monkeypatch.setattr(deps, "ohlc_analyzer", None)

    response = client.get("/api/test/status")

    assert response.status_code == 200
    body = response.json()
    assert body["collector_status"] is False
    assert body["collector_type"] is None
    assert body["ohlc_analyzer_status"] is False
    datetime.fromisoformat(body["timestamp"])  # parseable


def test_status_reports_initialized_state(client, monkeypatch):
    class _Marker:
        pass

    marker = _Marker()
    monkeypatch.setattr(deps, "collector", marker)
    monkeypatch.setattr(deps, "ohlc_analyzer", object())

    body = client.get("/api/test/status").json()

    assert body["collector_status"] is True
    assert "_Marker" in body["collector_type"]  # the type is named
    assert body["ohlc_analyzer_status"] is True


# ---------------------------------------------------------------------------
# PUT /api/test/data-source
# ---------------------------------------------------------------------------


def test_data_source_happy_path(client, fake_collector):
    _FakeCollector.reset(internals=dict(GOOD_INTERNALS))

    body = client.put("/api/test/data-source", json={"symbols": ["ignored anyway"]}).json()

    # The collector was constructed, initialized and used -- nothing else.
    (instance,) = _FakeCollector.instances
    assert instance.initialized and instance.collected

    assert body["success"] is True
    assert body["data_source"] == "yahoo-fake"
    # Only positive-priced symbols count as valid; zero-priced "flat" skipped.
    assert sorted(body["valid_symbols"]) == ["qqq", "spy"]
    assert body["symbols_with_prices"] == 2
    assert body["market_data"]["spy"]["price"] == 500.25
    # Sample data is bounded to 3 keys / 200 chars.
    assert len(body["sample_data"]) == 3
    assert all(len(str(v)) <= 200 for v in body["sample_data"].values())
    datetime.fromisoformat(body["timestamp"])


def test_data_source_skips_nan_priced_symbols(client, fake_collector):
    internals = {"data_source": "fake", "nan_sym": {"price": math.nan}}
    _FakeCollector.reset(internals=internals)

    body = client.put("/api/test/data-source", json={}).json()

    assert body["success"] is True
    assert body["valid_symbols"] == []


def test_data_source_none_priced_symbol_is_skipped_not_fatal(client, fake_collector):
    """A None price used to raise TypeError inside the loop and fail the whole
    request; it must just be skipped like any other invalid symbol."""
    internals = {
        "data_source": "fake",
        "spy": {"price": 500.25},
        "broken": {"price": None},
        "empty": {},
    }
    _FakeCollector.reset(internals=internals)

    body = client.put("/api/test/data-source", json={}).json()

    assert body["success"] is True
    assert body["valid_symbols"] == ["spy"]


def test_data_source_initialization_failure_returns_error_envelope(client, fake_collector):
    _FakeCollector.reset(init_error=RuntimeError("no data source configured"))

    response = client.put("/api/test/data-source", json={})

    assert response.status_code == 200  # debug endpoint: error envelope, not a 5xx
    body = response.json()
    assert body["success"] is False
    assert "no data source configured" in body["error"]
    datetime.fromisoformat(body["timestamp"])


def test_data_source_collect_failure_returns_error_envelope(client, fake_collector):
    _FakeCollector.reset(collect_error=OSError("network down (fake)"))

    body = client.put("/api/test/data-source", json={}).json()

    assert body["success"] is False
    assert "network down (fake)" in body["error"]


def test_data_source_empty_internals(client, fake_collector):
    _FakeCollector.reset(internals={})

    body = client.put("/api/test/data-source", json={}).json()

    assert body["success"] is True
    assert body["valid_symbols"] == []
    assert body["symbols_with_prices"] == 0
    assert body["sample_data"] == {}


# ---------------------------------------------------------------------------
# PUT /api/test/yahoo-finance
# ---------------------------------------------------------------------------


def test_yahoo_finance_reports_each_hardcoded_symbol(client, fake_collector):
    internals = {
        "data_source": "yahoo-fake",
        "spy": {"price": 500.0, "change": 1.0, "change_pct": 0.2, "volume": 10, "timestamp": "t1"},
        "qqq": {"price": 480.0},
        "aapl": {"price": 230.0},
        "btc-usd": {"price": 45000.0},
        "eth-usd": {"price": 3000.0},
    }
    _FakeCollector.reset(internals=internals)

    body = client.put("/api/test/yahoo-finance").json()

    assert body["success"] is True
    assert body["data_source"] == "yahoo-fake"
    results = body["yahoo_finance_results"]
    assert set(results.keys()) == {"SPY", "QQQ", "AAPL", "BTC-USD", "ETH-USD"}
    assert results["SPY"] == {
        "success": True,
        "price": 500.0,
        "change": 1.0,
        "change_pct": 0.2,
        "volume": 10,
        "timestamp": "t1",
        "raw_keys": ["price", "change", "change_pct", "volume", "timestamp"],
    }
    # Partial entries degrade to Nones, not crashes.
    assert results["QQQ"]["price"] == 480.0
    assert results["QQQ"]["change"] is None
    assert body["all_keys"] == list(internals.keys())
    datetime.fromisoformat(body["timestamp"])


def test_yahoo_finance_missing_symbol_is_reported_not_raised(client, fake_collector):
    _FakeCollector.reset(internals={"data_source": "yahoo-fake", "spy": {"price": 500.0}})

    body = client.put("/api/test/yahoo-finance").json()

    results = body["yahoo_finance_results"]
    assert results["SPY"]["success"] is True
    for missing in ("QQQ", "AAPL", "BTC-USD", "ETH-USD"):
        assert results[missing]["success"] is False
        assert "spy" in results[missing]["error"]  # available keys listed


def test_yahoo_finance_failure_returns_error_envelope(client, fake_collector):
    _FakeCollector.reset(init_error=RuntimeError("collector unavailable"))

    body = client.put("/api/test/yahoo-finance").json()

    assert body["success"] is False
    assert "collector unavailable" in body["error"]


# ---------------------------------------------------------------------------
# No outbound traffic: the real collector class is never touched
# ---------------------------------------------------------------------------


def test_real_collector_class_is_never_instantiated(client, fake_collector):
    _FakeCollector.reset(internals=GOOD_INTERNALS)

    client.put("/api/test/data-source", json={})
    client.put("/api/test/yahoo-finance")
    client.get("/api/test/status")

    # Every instance created during the requests was the fake.
    assert all(isinstance(i, _FakeCollector) for i in _FakeCollector.instances)
    assert _FakeCollector.instances  # and the fakes were actually used
