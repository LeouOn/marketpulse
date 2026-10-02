"""Offline coverage for src/api/routers/symbols.py (cycle 11).

Four GET endpoints under ``/api/market/symbols`` wrapping ``YahooFinanceClient``
(imported in-function, so the class is faked at its source module): ```` (list),
``/search``, ``/{symbol}`` (profile), ``/{symbol}/stats``, ``/{symbol}/52w-range``.

Bugs pinned here (each fix's test fails on the pre-change module):

* ``/search`` hardcoded ``asset_type: "other"`` for macro matches while the
  list endpoint classifies crypto/index/forex/futures — the same symbol showed
  a different type depending on the endpoint;
* a whitespace-only search query returned 200 with empty results instead of a
  clear refusal;
* a partial ``get_52w_range`` dict (missing ``high_52w``) surfaced as a cryptic
  ``'high_52w'`` KeyError error;
* an inf stat flowed through as a bare ``Infinity`` (invalid strict JSON) in
  ``/stats`` and ``/52w-range`` instead of ``null``.
"""

from __future__ import annotations

import math

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routers.symbols import router as symbols_router


class _FakeYahoo:
    def __init__(self, settings):
        pass

    market_symbols = ["SPY", "QQQ"]
    macro_symbols = {
        "BTC": "BTC-USD",
        "VIX": "^VIX",
        "ES": "ES=F",
        "EURUSD": "EURUSD=X",
        "DXY": "DX-Y.NYB",
        "GOLD": "GLD",
    }
    range_data = {
        "high_52w": 100.0,
        "low_52w": 80.0,
        "pct_from_high": -5.0,
        "pct_from_low": 10.0,
        "current_price": 95.0,
    }
    info = {"name": "Fake"}
    price = {"price": 95.0}

    def get_52w_range(self, symbol):
        return type(self).range_data

    def get_symbol_info(self, symbol):
        return type(self).info

    def get_single_symbol_data(self, symbol):
        return type(self).price


@pytest.fixture
def client(monkeypatch):
    import src.api.yahoo_client as ym

    monkeypatch.setattr(ym, "YahooFinanceClient", _FakeYahoo)
    app = FastAPI()
    app.include_router(symbols_router)
    return TestClient(app, raise_server_exceptions=False)


def _reset_fake(**overrides):
    for key, value in overrides.items():
        setattr(_FakeYahoo, key, value)


# ---------------------------------------------------------------------------
# GET /api/market/symbols
# ---------------------------------------------------------------------------


def test_list_symbols_classifies_asset_types(client):
    body = client.get("/api/market/symbols").json()
    assert body["success"] is True
    by_symbol = {s["symbol"]: s for s in body["data"]["symbols"]}
    assert by_symbol["SPY"]["asset_type"] == "equity"
    assert by_symbol["BTC"]["asset_type"] == "crypto"
    assert by_symbol["VIX"]["asset_type"] == "index"
    assert by_symbol["ES"]["asset_type"] == "futures"
    assert by_symbol["EURUSD"]["asset_type"] == "forex"
    # DX-Y.NYB matches no suffix heuristic; the current default bucket is "etf".
    assert by_symbol["DXY"]["asset_type"] == "etf"
    assert by_symbol["GOLD"]["asset_type"] == "etf"
    assert body["data"]["total"] == len(by_symbol)


def test_list_symbols_client_failure_is_an_error(client, monkeypatch):
    class Boom:
        def __init__(self, settings):
            raise RuntimeError("yahoo down")

    import src.api.yahoo_client as ym

    monkeypatch.setattr(ym, "YahooFinanceClient", Boom)
    body = client.get("/api/market/symbols").json()
    assert body["success"] is False
    assert "yahoo down" in body["error"]


# ---------------------------------------------------------------------------
# GET /api/market/symbols/search
# ---------------------------------------------------------------------------


def test_search_matches_equities_and_macro(client):
    body = client.get("/api/market/symbols/search?q=QQ").json()
    assert body["success"] is True
    assert body["data"]["query"] == "QQ"
    assert [m["symbol"] for m in body["data"]["results"]] == ["QQQ"]

    body = client.get("/api/market/symbols/search?q=btc").json()
    assert [m["symbol"] for m in body["data"]["results"]] == ["BTC"]


def test_search_macro_asset_types_match_the_list_endpoint(client):
    body = client.get("/api/market/symbols/search?q=BTC").json()
    listed = {s["symbol"]: s for s in client.get("/api/market/symbols").json()["data"]["symbols"]}
    for match in body["data"]["results"]:
        assert match["asset_type"] == listed[match["symbol"]]["asset_type"], (
            f"{match['symbol']} is {match['asset_type']!r} in search but "
            f"{listed[match['symbol']]['asset_type']!r} in the list"
        )


def test_search_no_match(client):
    body = client.get("/api/market/symbols/search?q=ZZZZZ").json()
    assert body["success"] is True
    assert body["data"]["results"] == []


def test_search_caps_at_ten_results(client, monkeypatch):
    class ManyEquities(_FakeYahoo):
        market_symbols = [f"S{i}" for i in range(20)]

    import src.api.yahoo_client as ym

    monkeypatch.setattr(ym, "YahooFinanceClient", ManyEquities)
    body = client.get("/api/market/symbols/search?q=S").json()
    assert len(body["data"]["results"]) == 10


def test_search_whitespace_only_query_is_refused(client):
    body = client.get("/api/market/symbols/search?q=%20%20%20").json()
    assert body["success"] is False, "a whitespace-only query must be refused, not silently return nothing"
    assert "query" in body["error"]


# ---------------------------------------------------------------------------
# GET /api/market/symbols/{symbol}
# ---------------------------------------------------------------------------


def test_profile_maps_macro_alias(client):
    body = client.get("/api/market/symbols/btc").json()
    assert body["success"] is True
    data = body["data"]
    assert data["symbol"] == "btc"
    assert data["yahoo_symbol"] == "BTC-USD"
    assert data["info"] == {"name": "Fake"}
    assert data["range_52w"]["current_price"] == 95.0
    assert data["current_price"] == {"price": 95.0}
    assert data["timestamp"]


def test_profile_client_failure_is_an_error(client, monkeypatch):
    class Boom(_FakeYahoo):
        def get_symbol_info(self, symbol):
            raise RuntimeError("info boom")

    import src.api.yahoo_client as ym

    monkeypatch.setattr(ym, "YahooFinanceClient", Boom)
    body = client.get("/api/market/symbols/SPY").json()
    assert body["success"] is False
    assert "info boom" in body["error"]


# ---------------------------------------------------------------------------
# GET /api/market/symbols/{symbol}/stats and /52w-range
# ---------------------------------------------------------------------------


def test_stats_happy_path(client):
    body = client.get("/api/market/symbols/SPY/stats").json()
    assert body["success"] is True
    data = body["data"]
    assert data["high_52w"] == 100.0
    assert data["low_52w"] == 80.0
    assert data["pct_from_high"] == -5.0
    assert data["pct_from_low"] == 10.0
    assert data["current_price"] == 95.0


def test_stats_no_range_data_is_an_error(client):
    _reset_fake(range_data=None)
    try:
        body = client.get("/api/market/symbols/SPY/stats").json()
        assert body["success"] is False
        assert "Could not fetch stats" in body["error"]
    finally:
        _reset_fake(
            range_data={
                "high_52w": 100.0,
                "low_52w": 80.0,
                "pct_from_high": -5.0,
                "pct_from_low": 10.0,
                "current_price": 95.0,
            }
        )


def test_stats_partial_range_data_degrades_to_nulls(client):
    _reset_fake(range_data={"low_52w": 80.0, "current_price": 95.0})
    try:
        body = client.get("/api/market/symbols/SPY/stats").json()
        assert body["success"] is True, f"old code turns a missing key into a cryptic error: {body.get('error')}"
        data = body["data"]
        assert data["high_52w"] is None
        assert data["pct_from_high"] is None
        assert data["low_52w"] == 80.0
        assert data["current_price"] == 95.0
    finally:
        _reset_fake(
            range_data={
                "high_52w": 100.0,
                "low_52w": 80.0,
                "pct_from_high": -5.0,
                "pct_from_low": 10.0,
                "current_price": 95.0,
            }
        )


@pytest.mark.parametrize("field", ["high_52w", "pct_from_high"])
def test_stats_non_finite_values_serialize_as_null(client, field):
    rng = {"high_52w": 100.0, "low_52w": 80.0, "pct_from_high": -5.0, "pct_from_low": 10.0, "current_price": 95.0}
    rng[field] = math.inf
    _reset_fake(range_data=rng)
    try:
        body = client.get("/api/market/symbols/SPY/stats").json()
        assert body["success"] is True
        assert body["data"][field] is None, f"{field}={math.inf} must serialize as null, not Infinity"
    finally:
        _reset_fake(
            range_data={
                "high_52w": 100.0,
                "low_52w": 80.0,
                "pct_from_high": -5.0,
                "pct_from_low": 10.0,
                "current_price": 95.0,
            }
        )


def test_52w_range_happy_path(client):
    body = client.get("/api/market/symbols/ES/52w-range").json()
    assert body["success"] is True
    assert body["data"]["yahoo_symbol"] if "yahoo_symbol" in body["data"] else True
    assert body["data"]["high_52w"] == 100.0


def test_52w_range_no_data_is_an_error(client):
    _reset_fake(range_data=None)
    try:
        body = client.get("/api/market/symbols/SPY/52w-range").json()
        assert body["success"] is False
        assert "Could not fetch 52w range" in body["error"]
    finally:
        _reset_fake(
            range_data={
                "high_52w": 100.0,
                "low_52w": 80.0,
                "pct_from_high": -5.0,
                "pct_from_low": 10.0,
                "current_price": 95.0,
            }
        )


def test_52w_range_non_finite_serializes_as_null(client):
    rng = {
        "high_52w": float("nan"),
        "low_52w": 80.0,
        "pct_from_high": -5.0,
        "pct_from_low": 10.0,
        "current_price": 95.0,
    }
    _reset_fake(range_data=rng)
    try:
        body = client.get("/api/market/symbols/SPY/52w-range").json()
        assert body["success"] is True
        assert body["data"]["high_52w"] is None
    finally:
        _reset_fake(
            range_data={
                "high_52w": 100.0,
                "low_52w": 80.0,
                "pct_from_high": -5.0,
                "pct_from_low": 10.0,
                "current_price": 95.0,
            }
        )
