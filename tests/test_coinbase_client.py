"""Offline tests for ``src/api/coinbase_client.py``.

The aiohttp layer is fully faked (no sockets): canned responses are replayed
and every request recorded, so request signing, header hygiene, response
parsing and error handling are all tested with obviously fake credentials.
Only read paths exist in this module; nothing here places orders.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
from types import SimpleNamespace

import pytest

from src.api.coinbase_client import CoinbaseClient, get_coinbase_client

FAKE_KEY = "fake-cb-key-not-real"
FAKE_PASSPHRASE = "fake-cb-passphrase-not-real"
FAKE_SECRET_B64 = base64.b64encode(b"fake-cb-secret-bytes-not-real").decode()


def _fake_settings():
    return SimpleNamespace(
        api_keys=SimpleNamespace(
            coinbase=SimpleNamespace(api_key=FAKE_KEY, api_secret=FAKE_SECRET_B64, passphrase=FAKE_PASSPHRASE)
        )
    )


class _FakeResponse:
    def __init__(self, status: int, payload):
        self.status = status
        self._payload = payload

    async def json(self):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    """Records GETs; replays canned responses in order."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.gets: list[dict] = []

    def get(self, url, headers=None, params=None):
        self.gets.append({"url": url, "headers": headers, "params": params})
        return self._responses.pop(0)


def _client_with(responses) -> tuple[CoinbaseClient, _FakeSession]:
    client = CoinbaseClient(settings=_fake_settings())
    session = _FakeSession(responses)
    client.session = session
    return client, session


def _expected_signature(timestamp: str, method: str, path: str, body: str = "") -> str:
    message = f"{timestamp}{method}{path}{body}".encode()
    digest = hmac.new(base64.b64decode(FAKE_SECRET_B64), message, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


# ---------------------------------------------------------------------------
# Request signing (fake credentials only)
# ---------------------------------------------------------------------------


async def test_get_request_is_signed_with_all_cb_access_headers():
    client, session = _client_with([_FakeResponse(200, {"data": {"amount": "45000.5"}})])

    await client.get_price("BTC-USD")

    (request,) = session.gets
    assert request["url"] == "https://api.coinbase.com/v2/prices/BTC-USD/spot"
    headers = request["headers"]
    assert headers["CB-ACCESS-KEY"] == FAKE_KEY
    assert headers["CB-ACCESS-PASSPHRASE"] == FAKE_PASSPHRASE
    timestamp = headers["CB-ACCESS-TIMESTAMP"]
    assert timestamp.isdigit()
    assert headers["CB-ACCESS-SIGN"] == _expected_signature(timestamp, "GET", "/v2/prices/BTC-USD/spot")


async def test_post_request_signature_covers_the_serialized_body():
    client, session = _client_with([_FakeResponse(200, {"ok": True})])
    posted = []

    class _PostSession(_FakeSession):
        def post(self, url, headers=None, json=None):
            posted.append({"url": url, "headers": headers, "json": json})
            return self._responses.pop(0)

    client.session = _PostSession([_FakeResponse(200, {"ok": True})])
    data = {"product_id": "BTC-USD"}

    await client._post("/v2/test", data)

    (request,) = posted
    body = json.dumps(data)  # the exact body the signature must cover
    assert request["headers"]["CB-ACCESS-SIGN"] == _expected_signature(
        request["headers"]["CB-ACCESS-TIMESTAMP"], "POST", "/v2/test", body
    )


# ---------------------------------------------------------------------------
# Response parsing: happy paths
# ---------------------------------------------------------------------------


async def test_get_price_parses_amount():
    client, _ = _client_with([_FakeResponse(200, {"data": {"amount": "45000.5"}})])

    result = await client.get_price("BTC-USD")

    assert result["symbol"] == "BTC-USD"
    assert result["price"] == 45000.5
    assert result["timestamp"]


async def test_get_prices_aggregates_only_successful_symbols():
    responses = [
        _FakeResponse(200, {"data": {"amount": "45000.5"}}),  # BTC ok
        _FakeResponse(500, {}),  # ETH fails -> skipped, not fatal
    ]
    client, _ = _client_with(responses)

    result = await client.get_prices(["BTC-USD", "ETH-USD"])

    assert set(result.keys()) == {"BTC-USD"}
    assert result["BTC-USD"]["price"] == 45000.5


async def test_get_candles_parses_ohlcv_rows():
    rows = [
        [1700000000, "44900", "45100", "45000", "45050", "123.5"],
        [1700003600, "45050", "45200", "45050", "45150", "99"],
    ]
    client, _ = _client_with([_FakeResponse(200, rows)])

    candles = await client.get_candles("BTC-USD", granularity=3600)

    assert len(candles) == 2
    first = candles[0]
    assert first["timestamp"] == 1700000000
    assert first["open"] == 45000.0 and first["close"] == 45050.0
    assert first["low"] == 44900.0 and first["high"] == 45100.0
    assert first["volume"] == 123.5


async def test_get_ticker_parses_quote_fields():
    payload = {
        "data": {
            "price": "45000.5",
            "bid": "45000.0",
            "ask": "45001.0",
            "volume": "1234.5",
            "time": "2026-01-05T09:30:00Z",
        }
    }
    client, _ = _client_with([_FakeResponse(200, payload)])

    ticker = await client.get_ticker("BTC-USD")

    assert ticker == {
        "symbol": "BTC-USD",
        "price": 45000.5,
        "bid": 45000.0,
        "ask": 45001.0,
        "volume": 1234.5,
        "timestamp": "2026-01-05T09:30:00Z",
    }


async def test_get_market_data_builds_internals_entries():
    payload = {"data": {"price": "45000.5", "bid": "45000.0", "ask": "45001.0", "volume": "1234.5", "time": "t"}}
    client, _ = _client_with([_FakeResponse(200, payload), _FakeResponse(401, {})])

    internals = await client.get_market_data(["BTC-USD", "ETH-USD"])

    assert set(internals.keys()) == {"BTC-USD"}
    entry = internals["BTC-USD"]
    assert entry["price"] == 45000.5
    assert entry["volume"] == 1234  # int per the internals contract
    assert entry["change"] == 0 and entry["change_pct"] == 0  # documented placeholder


# ---------------------------------------------------------------------------
# Error statuses and network failures -> None, never a crash
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", [401, 429, 500, 404])
async def test_error_statuses_return_none(status):
    client, _ = _client_with([_FakeResponse(status, {})])

    assert await client.get_price("BTC-USD") is None


async def test_network_exception_returns_none():
    class _BoomSession(_FakeSession):
        def get(self, url, headers=None, params=None):
            raise OSError("connection reset by fake")

    client = CoinbaseClient(settings=_fake_settings())
    client.session = _BoomSession([])

    assert await client.get_price("BTC-USD") is None


async def test_none_session_degrades_to_none():
    client = CoinbaseClient(settings=_fake_settings())
    client.session = None

    assert await client.get_price("BTC-USD") is None


async def test_is_available_true_on_200_false_on_error():
    up, _ = _client_with([_FakeResponse(200, {"data": {"iso": "now"}})])
    assert await up.is_available() is True

    down, _ = _client_with([_FakeResponse(500, {})])
    assert await down.is_available() is False


async def test_is_available_does_not_swallow_cancellation():
    """A bare ``except:`` would eat asyncio.CancelledError -- cancellation
    must propagate."""
    client = CoinbaseClient(settings=_fake_settings())

    async def _cancelled_get(endpoint, params=None):
        raise asyncio.CancelledError()

    client._get = _cancelled_get

    with pytest.raises(asyncio.CancelledError):
        await client.is_available()


# ---------------------------------------------------------------------------
# Malformed payloads: bad input, None and NaN paths
# ---------------------------------------------------------------------------


async def test_get_price_with_missing_or_non_numeric_amount_returns_none():
    for bad_payload in [
        {"data": {}},  # amount missing entirely
        {"data": {"amount": None}},  # null amount
        {"data": {"amount": "not-a-number"}},  # garbage
        {},  # no data envelope
        {"data": "unexpected shape"},
    ]:
        client, _ = _client_with([_FakeResponse(200, bad_payload)])
        assert await client.get_price("BTC-USD") is None, f"payload {bad_payload} should degrade to None"


async def test_get_price_passes_through_nan_amount_as_nan():
    """'NaN' is a parseable float -- documented passthrough, no crash."""
    client, _ = _client_with([_FakeResponse(200, {"data": {"amount": "NaN"}})])

    result = await client.get_price("BTC-USD")

    assert result["price"] != result["price"]  # NaN


async def test_get_ticker_with_missing_quote_fields_returns_none():
    payload = {"data": {"price": "45000.5", "ask": "45001.0", "volume": "1"}}  # no bid
    client, _ = _client_with([_FakeResponse(200, payload)])

    assert await client.get_ticker("BTC-USD") is None


async def test_get_ticker_with_none_fields_returns_none():
    payload = {"data": {"price": None, "bid": "1", "ask": "2", "volume": "3"}}
    client, _ = _client_with([_FakeResponse(200, payload)])

    assert await client.get_ticker("BTC-USD") is None


async def test_get_candles_with_malformed_row_returns_none():
    rows = [[1700000000, "44900", "45100"]]  # truncated row: no open/close/volume
    client, _ = _client_with([_FakeResponse(200, rows)])

    assert await client.get_candles("BTC-USD") is None


async def test_get_candles_with_empty_or_non_list_payload_returns_none():
    for payload in [[], {"unexpected": "shape"}, None]:
        client, _ = _client_with([_FakeResponse(200, payload)])
        assert await client.get_candles("BTC-USD") is None


async def test_get_candles_request_carries_granularity_and_window():
    from datetime import datetime

    client, session = _client_with([_FakeResponse(200, [])])

    await client.get_candles(
        "BTC-USD", granularity=900, start=datetime(2026, 1, 5, 9, 30), end=datetime(2026, 1, 5, 10, 30)
    )

    params = session.gets[0]["params"]
    assert params["granularity"] == 900
    assert params["start"] == "2026-01-05T09:30:00Z"
    assert params["end"] == "2026-01-05T10:30:00Z"


# ---------------------------------------------------------------------------
# Secret hygiene
# ---------------------------------------------------------------------------


async def test_secrets_never_appear_in_logs_or_errors(capsys):
    client, _ = _client_with([_FakeResponse(401, {})])

    assert await client.get_price("BTC-USD") is None  # 401 path logs an error

    captured = capsys.readouterr()
    assert FAKE_KEY not in captured.out + captured.err
    assert FAKE_SECRET_B64 not in captured.out + captured.err
    assert FAKE_PASSPHRASE not in captured.out + captured.err


# ---------------------------------------------------------------------------
# Context manager + factory
# ---------------------------------------------------------------------------


async def test_context_manager_opens_and_closes_a_session():
    client = CoinbaseClient(settings=_fake_settings())

    async with client as entered:
        assert entered is client
        assert client.session is not None

    assert client.session is None or client.session.closed


async def test_get_coinbase_client_returns_a_client():
    client = await get_coinbase_client()

    assert isinstance(client, CoinbaseClient)
    assert client.base_url == "https://api.coinbase.com"
