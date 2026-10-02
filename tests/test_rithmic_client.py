"""Offline coverage for src/api/rithmic_client.py.

RithmicClient is the futures-data REST client (login → Bearer GETs for
quotes/bars/health). Every network touch is faked: ``aiohttp.ClientSession``
is monkeypatched on the client's module with a fake whose ``post``/``get``
return canned async-context-manager responses — no sockets, no waits.
Credentials are obviously fake (``test-user`` / ``SUPER-FAKE-PASS-123``) and
a dedicated test pins that they never appear in logs or error paths.

Pinned contract: connect success/failure (bad credentials, network error,
missing session), not-connected guards, quote/bars parsing and shaping,
multi-symbol behaviour, futures-internals shaping, health check, and the
``get_rithmic_client`` convenience constructor.

Tests marked ``test_bug_*`` fail on the pre-fix module (proven against a
HEAD copy in the cycle-13 report): ``get_quote`` crashed on JSON null /
non-numeric fields and ``get_ohlc`` crashed on malformed bars.
"""

from __future__ import annotations

import asyncio
import math
from types import SimpleNamespace

import pytest

from src.api import rithmic_client as rc


def _run(coro):
    return asyncio.run(coro)


def _settings(username="test-user", password="SUPER-FAKE-PASS-123"):
    rithmic = SimpleNamespace(username=username, password=password, system_name="TEST_SYS", login_prefix="test")
    return SimpleNamespace(api_keys=SimpleNamespace(rithmic=rithmic))


class _FakeResp:
    def __init__(self, status, payload):
        self.status = status
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self):
        return self._payload


class _FakeSession:
    """Canned aiohttp.ClientSession stand-in (async-CM responses)."""

    def __init__(self, *, post_result=None, post_error=None, routes=None, default_get=(200, {})):
        self.post_result = post_result or (200, {"token": "tok-123"})
        self.post_error = post_error
        self.routes = routes or {}
        self.default_get = default_get
        self.posts: list[tuple[str, dict]] = []
        self.gets: list[tuple[str, dict, dict]] = []
        self.closed = False

    def post(self, url, json=None, **kw):
        # aiohttp's post() is a plain method returning an async context manager.
        self.posts.append((url, json))
        if self.post_error:
            raise self.post_error
        return _FakeResp(*self.post_result)

    def get(self, url, headers=None, params=None):
        self.gets.append((url, headers, params))
        status, payload = self.routes.get(url, self.default_get)
        return _FakeResp(status, payload)

    async def close(self):
        self.closed = True


@pytest.fixture
def error_logs():
    from loguru import logger

    msgs: list[str] = []
    hid = logger.add(lambda m: msgs.append(str(m)), level="DEBUG")
    yield msgs
    logger.remove(hid)


def _client(session=None):
    client = rc.RithmicClient(settings=_settings())
    if session is not None:
        client.session = session
    return client


def _connected(session=None):
    client = _client(session)
    client._connected = True
    client._token = "tok-123"
    return client


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_init_reads_settings():
    c = _client()
    assert c.username == "test-user"
    assert c.system_name == "TEST_SYS"
    assert c.login_prefix == "test"
    assert c.base_url == "https://api.rithmic.com"
    assert c._connected is False
    assert c.session is None


# ---------------------------------------------------------------------------
# connect()
# ---------------------------------------------------------------------------


def test_connect_success_stores_token():
    s = _FakeSession(post_result=(200, {"token": "tok-abc"}))
    c = _client(s)
    assert _run(c.connect()) is True
    assert c._connected is True
    assert c._token == "tok-abc"
    url, payload = s.posts[0]
    assert url == "https://api.rithmic.com/auth/login"
    assert payload["user"] == "test-user"
    assert payload["system"] == "TEST_SYS"
    assert payload["login_prefix"] == "test"


def test_connect_bad_credentials_returns_false_and_leaks_nothing(error_logs):
    s = _FakeSession(post_result=(401, {"error": "bad credentials"}))
    c = _client(s)
    assert _run(c.connect()) is False
    assert c._connected is False
    joined = "\n".join(error_logs)
    assert "auth failed" in joined
    assert "SUPER-FAKE-PASS-123" not in joined  # secret never logged
    assert "test-user" not in joined


def test_connect_network_error_returns_false(error_logs):
    s = _FakeSession(post_error=RuntimeError("connection refused"))
    c = _client(s)
    assert _run(c.connect()) is False
    assert c._connected is False
    assert any("connection error" in m for m in error_logs)


def test_connect_without_session_returns_false(error_logs):
    c = _client()  # no __aenter__: session is None
    assert _run(c.connect()) is False  # not-connected path, no crash


# ---------------------------------------------------------------------------
# Not-connected guards
# ---------------------------------------------------------------------------


def test_get_quote_not_connected_returns_none():
    c = _client(_FakeSession())
    assert _run(c.get_quote("NQ=F")) is None


def test_is_available_not_connected_false():
    assert _run(_client().is_available()) is False


# ---------------------------------------------------------------------------
# get_quote / get_quotes
# ---------------------------------------------------------------------------


def _quote_session(payload):
    return _FakeSession(routes={"https://api.rithmic.com/quotes/NQ=F": (200, payload)})


def test_get_quote_shapes_fields():
    c = _connected(
        _quote_session(
            {"bid": "15001.25", "ask": 15002.0, "last": 15001.5, "volume": "123", "timestamp": "2026-10-02T10:00:00"}
        )
    )
    q = _run(c.get_quote("NQ=F"))
    assert q["symbol"] == "NQ=F"
    assert q["bid"] == 15001.25 and q["ask"] == 15002.0 and q["last"] == 15001.5
    assert q["volume"] == 123
    assert q["timestamp"] == "2026-10-02T10:00:00"


def test_get_quote_defaults_missing_fields_and_timestamp():
    # Non-empty JSON object without quote fields: numeric defaults kick in.
    # (A fully empty {} response short-circuits to None via the `if data:` gate —
    # pinned separately below.)
    c = _connected(_quote_session({"symbol": "NQ=F"}))
    q = _run(c.get_quote("NQ=F"))
    assert q["bid"] == 0.0 and q["ask"] == 0.0 and q["last"] == 0.0 and q["volume"] == 0
    assert q["timestamp"]  # now() fallback


def test_get_quote_empty_object_returns_none():
    c = _connected(_quote_session({}))
    assert _run(c.get_quote("NQ=F")) is None


def test_get_quote_non_200_returns_none():
    c = _connected(_FakeSession(default_get=(500, {})))
    assert _run(c.get_quote("NQ=F")) is None


def test_get_quote_nan_bid_passes_through_as_nan():
    # NaN is valid float input — it flows through (callers validate), no crash.
    c = _connected(_quote_session({"bid": float("nan"), "ask": 1.0, "last": 1.0}))
    q = _run(c.get_quote("NQ=F"))
    assert math.isnan(q["bid"])


def test_bug_get_quote_null_fields_do_not_crash():
    # A REST API returning JSON nulls crashed float(None) -> TypeError.
    c = _connected(_quote_session({"bid": None, "ask": None, "last": None, "volume": None}))
    q = _run(c.get_quote("NQ=F"))
    assert q["bid"] == 0.0 and q["volume"] == 0


def test_bug_get_quote_non_numeric_fields_do_not_crash():
    c = _connected(_quote_session({"bid": "N/A", "ask": "delayed", "last": "", "volume": "—"}))
    q = _run(c.get_quote("NQ=F"))
    assert q["bid"] == 0.0 and q["ask"] == 0.0 and q["last"] == 0.0 and q["volume"] == 0


def test_get_quotes_multi_and_missing_skipped():
    s = _FakeSession(
        routes={
            "https://api.rithmic.com/quotes/ES=F": (200, {"bid": 1.0, "ask": 1.5, "last": 1.25}),
            "https://api.rithmic.com/quotes/NQ=F": (404, {}),
        }
    )
    c = _connected(s)
    out = _run(c.get_quotes(["ES=F", "NQ=F"]))
    assert set(out) == {"ES=F"}
    assert _run(c.get_quotes([])) == {}


# ---------------------------------------------------------------------------
# get_ohlc()
# ---------------------------------------------------------------------------


def _bars_session(bars):
    return _FakeSession(routes={"https://api.rithmic.com/bars": (200, {"bars": bars})})


_GOOD_BAR = {"t": "2026-10-02T10:00:00", "o": "100.5", "h": 101.0, "l": 100.0, "c": 100.75, "v": "42"}


def test_get_ohlc_maps_and_coerces_bars():
    c = _connected(_bars_session([_GOOD_BAR]))
    bars = _run(c.get_ohlc("NQ=F", limit=5))
    assert bars == [
        {
            "timestamp": "2026-10-02T10:00:00",
            "open": 100.5,
            "high": 101.0,
            "low": 100.0,
            "close": 100.75,
            "volume": 42,
        }
    ]
    _, _, params = c.session.gets[0]
    assert params["symbol"] == "NQ=F" and params["timeframe"] == "1min" and params["limit"] == 5


def test_get_ohlc_start_end_params():
    from datetime import datetime

    c = _connected(_bars_session([]))
    _run(c.get_ohlc("NQ=F", start=datetime(2026, 10, 1), end=datetime(2026, 10, 2)))
    _, _, params = c.session.gets[0]
    assert params["start"] == "2026-10-01T00:00:00"
    assert params["end"] == "2026-10-02T00:00:00"


def test_get_ohlc_no_bars_key_or_none_data():
    c = _connected(_FakeSession(routes={"https://api.rithmic.com/bars": (200, {"nope": 1})}))
    assert _run(c.get_ohlc("NQ=F")) is None
    c2 = _connected(_FakeSession(default_get=(500, {})))
    assert _run(c2.get_ohlc("NQ=F")) is None


def test_bug_get_ohlc_skips_malformed_bars():
    bars = [
        _GOOD_BAR,
        {"t": "2026-10-02T10:01:00", "o": None, "h": 1, "l": 1, "c": 1, "v": 1},  # null field
        {"t": "2026-10-02T10:02:00", "o": 1, "h": 1, "l": 1, "c": 1},  # missing volume
    ]
    c = _connected(_bars_session(bars))
    out = _run(c.get_ohlc("NQ=F"))
    assert out == [
        {
            "timestamp": "2026-10-02T10:00:00",
            "open": 100.5,
            "high": 101.0,
            "low": 100.0,
            "close": 100.75,
            "volume": 42,
        }
    ]  # malformed bars skipped, no crash


# ---------------------------------------------------------------------------
# get_futures_data / is_available / get_rithmic_client
# ---------------------------------------------------------------------------


def test_get_futures_data_shapes_and_survives_failures(monkeypatch):
    s = _FakeSession(
        routes={
            "https://api.rithmic.com/quotes/ES=F": (200, {"bid": 1, "ask": 1, "last": 5500.25, "volume": 10}),
            "https://api.rithmic.com/quotes/BAD=F": (404, {}),
        }
    )
    c = _connected(s)

    real_quote = c.get_quote

    async def exploding_quote(symbol):
        if symbol == "BOOM=F":
            raise RuntimeError("upstream hiccup")
        return await real_quote(symbol)

    monkeypatch.setattr(c, "get_quote", exploding_quote)
    out = _run(c.get_futures_data(["ES=F", "BAD=F", "BOOM=F"]))
    assert set(out) == {"ES=F"}
    assert out["ES=F"]["price"] == 5500.25
    assert out["ES=F"]["change"] == 0 and out["ES=F"]["change_pct"] == 0


def test_is_available_health_paths():
    healthy = _connected(_FakeSession(routes={"https://api.rithmic.com/health": (200, {"ok": True})}))
    assert _run(healthy.is_available()) is True
    sick = _connected(_FakeSession(routes={"https://api.rithmic.com/health": (503, {})}))
    assert _run(sick.is_available()) is False


def test_get_rithmic_client_convenience(monkeypatch):
    captured = {}

    class _Client(rc.RithmicClient):
        async def connect(self):
            captured["connected"] = True
            self._connected = True
            return True

    monkeypatch.setattr(rc, "get_settings", lambda: _settings())
    monkeypatch.setattr(rc, "RithmicClient", _Client)
    client = _run(rc.get_rithmic_client())
    assert captured["connected"] is True
    assert client._connected is True


def test_context_manager_closes_session():
    s = _FakeSession()
    c = _client()

    async def flow():
        async with c:
            c.session = s  # swapped in; aexit must disconnect and close it
            return True

    _run(flow())
    assert s.closed is True
    assert c._connected is False
