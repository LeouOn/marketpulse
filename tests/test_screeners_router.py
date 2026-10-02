"""Offline coverage for src/api/routers/screeners.py.

Two GET endpoints over the Yahoo screener client:
``/{screener_type}``` (gainers/losers/most_active, Redis-cached for 300s) and
``/{screener_type}/history`` (documented placeholder returning the latest
cached snapshot + "coming soon").

Everything is faked at the seam the router itself uses: it imports
``src.api.yahoo_client.YahooFinanceClient`` inside the handler, so the class
attribute on that module is monkeypatched. ``get_screener_data`` is sync
(matching the real client), ``_get_cache``/``cache.get``/``cache.set`` are
async. No network, no keys.

Tests marked ``test_bug_*`` fail on the pre-fix module (proven against a HEAD
copy in the cycle-10 report); the rest pin existing behaviour and pass on
both versions.
"""

from __future__ import annotations

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routers.screeners import router as screeners_router

VALID = ["gainers", "losers", "most_active"]


class _FakeCache:
    def __init__(self, preset=None, get_error=None):
        self.store = dict(preset or {})
        self.get_error = get_error
        self.set_calls: list[tuple] = []

    async def get(self, key):
        if self.get_error:
            raise self.get_error
        return self.store.get(key)

    async def set(self, key, value, ttl=None):
        self.set_calls.append((key, value, ttl))
        self.store[key] = value


def _install_fake(monkeypatch, *, results=None, error=None, cache=None):
    """Patch YahooFinanceClient on its module; returns a call recorder."""
    calls = {"screener_types": [], "inits": 0}

    class _FakeClient:
        def __init__(self, settings):
            calls["inits"] += 1

        async def _get_cache(self):
            return cache

        def get_screener_data(self, screener_type):
            calls["screener_types"].append(screener_type)
            if error:
                raise error
            return results

    import src.api.yahoo_client as yahoo_mod

    monkeypatch.setattr(yahoo_mod, "YahooFinanceClient", _FakeClient)
    return calls


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(screeners_router)
    return TestClient(app)


def _ok(body):
    assert body["success"] is True, body
    return body["data"]


# ---------------------------------------------------------------------------
# GET /{screener_type}
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("screener_type", VALID)
def test_valid_screener_types_return_results_and_cache(client, monkeypatch, screener_type):
    cache = _FakeCache()
    rows = [{"symbol": "AAPL", "price": 190.5, "change_pct": 2.1}]
    _install_fake(monkeypatch, results=rows, cache=cache)

    r = client.get(f"/api/market/screeners/{screener_type}")

    assert r.status_code == 200, r.text
    data = _ok(r.json())
    assert data["screener_type"] == screener_type
    assert data["results"] == rows
    # cache miss -> upstream called once, then cached with a 300s ttl
    assert cache.set_calls == [(f"screener:{screener_type}", rows, 300)]


def test_cache_hit_skips_upstream_and_set(client, monkeypatch):
    cached_rows = [{"symbol": "TSLA", "price": 250.0}]
    cache = _FakeCache(preset={"screener:gainers": cached_rows})
    calls = _install_fake(monkeypatch, results=[], cache=cache)

    r = client.get("/api/market/screeners/gainers")

    assert r.status_code == 200
    assert _ok(r.json())["results"] == cached_rows
    assert calls["screener_types"] == []  # upstream never touched
    assert cache.set_calls == []


def test_invalid_screener_type_rejected(client, monkeypatch):
    calls = _install_fake(monkeypatch, results=[])
    r = client.get("/api/market/screeners/not_a_type")
    assert r.status_code == 200  # MarketResponse convention: success flag, not status
    body = r.json()
    assert body["success"] is False
    assert "Invalid screener type" in body["error"]
    assert calls["inits"] == 0  # rejected before any client work


def test_empty_results_not_cached(client, monkeypatch):
    cache = _FakeCache()
    _install_fake(monkeypatch, results=[], cache=cache)
    r = client.get("/api/market/screeners/losers")
    assert r.status_code == 200
    assert _ok(r.json())["results"] == []
    assert cache.set_calls == []


def test_no_cache_still_returns_results(client, monkeypatch):
    _install_fake(monkeypatch, results=[{"symbol": "X"}], cache=None)
    r = client.get("/api/market/screeners/most_active")
    assert r.status_code == 200
    assert _ok(r.json())["results"] == [{"symbol": "X"}]


def test_upstream_exception_becomes_error_response(client, monkeypatch):
    _install_fake(monkeypatch, error=RuntimeError("yahoo down"), cache=_FakeCache())
    r = client.get("/api/market/screeners/gainers")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert "yahoo down" in body["error"]


def test_cache_get_exception_becomes_error_response(client, monkeypatch):
    cache = _FakeCache(get_error=RuntimeError("redis down"))
    _install_fake(monkeypatch, results=[], cache=cache)
    r = client.get("/api/market/screeners/gainers")
    assert r.status_code == 200
    assert r.json()["success"] is False


def test_nan_values_do_not_break_the_response(client, monkeypatch):
    _install_fake(monkeypatch, results=[{"symbol": "X", "change_pct": float("nan")}], cache=_FakeCache())
    r = client.get("/api/market/screeners/gainers")
    assert r.status_code == 200
    assert r.json()["success"] is True  # NaN serializes to null in this stack


def test_bug_numpy_scalars_in_results_return_200_not_500(client, monkeypatch):
    # yfinance/pandas paths hand back numpy scalars; pydantic cannot serialize
    # them (PydanticSerializationError -> HTTP 500). The router must sanitize.
    rows = [{"symbol": "X", "price": np.float64(190.5), "b": np.bool_(True)}]
    _install_fake(monkeypatch, results=rows, cache=_FakeCache())
    r = client.get("/api/market/screeners/gainers")
    assert r.status_code == 200, r.text
    results = _ok(r.json())["results"]
    assert results[0]["price"] == 190.5
    assert results[0]["b"] is True


def test_bug_numpy_scalars_on_cache_hit_return_200_not_500(client, monkeypatch):
    cached_rows = [{"symbol": "Y", "price": np.float64(12.25), "v": np.int64(7)}]
    _install_fake(monkeypatch, cache=_FakeCache(preset={"screener:losers": cached_rows}))
    r = client.get("/api/market/screeners/losers")
    assert r.status_code == 200, r.text
    results = _ok(r.json())["results"]
    assert results[0]["price"] == 12.25
    assert results[0]["v"] == 7


# ---------------------------------------------------------------------------
# GET /{screener_type}/history — documented placeholder, pinned as-is
# ---------------------------------------------------------------------------


def test_history_placeholder_returns_latest_cached(client, monkeypatch):
    latest = [{"symbol": "AAPL"}]
    _install_fake(monkeypatch, cache=_FakeCache(preset={"screener:gainers": latest}))
    r = client.get("/api/market/screeners/gainers/history")
    assert r.status_code == 200
    data = _ok(r.json())
    assert data["screener_type"] == "gainers"
    assert data["message"] == "Historical data coming soon"
    assert data["latest"] == latest


def test_history_placeholder_without_cache(client, monkeypatch):
    _install_fake(monkeypatch, cache=None)
    r = client.get("/api/market/screeners/losers/history")
    assert r.status_code == 200
    data = _ok(r.json())
    assert data["latest"] is None
    assert data["message"] == "Historical data coming soon"


def test_history_invalid_type_rejected(client, monkeypatch):
    _install_fake(monkeypatch)
    r = client.get("/api/market/screeners/bogus/history")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert "Invalid screener type" in body["error"]


def test_history_cache_error_becomes_error_response(client, monkeypatch):
    _install_fake(monkeypatch, cache=_FakeCache(get_error=RuntimeError("redis down")))
    r = client.get("/api/market/screeners/gainers/history")
    assert r.status_code == 200
    assert r.json()["success"] is False
