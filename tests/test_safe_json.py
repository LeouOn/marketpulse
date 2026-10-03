"""Tests for src/api/safe_json.py (cycle 20).

SafeJSONResponse must be byte-identical to Starlette's JSONResponse for every
payload that serializes today, never raise for non-finite floats, and handle
datetime/date/Decimal/set/pandas Timestamp/NaT. The end-to-end section proves
that a plain-dict handler fails on NaN with the stock response class, while
pydantic's response-model path already nulls NaN independently.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.background import BackgroundTask
from starlette.responses import JSONResponse

from src.api.safe_json import SafeJSONResponse, new_error_id, public_error_message

# ---------------------------------------------------------------------------
# Byte-identity with Starlette's JSONResponse for ordinary payloads
# ---------------------------------------------------------------------------

ORDINARY_PAYLOADS = [
    {"b": 1, "a": 2},  # insertion order preserved
    [1, 2, 3],
    ["unicode", "café", "日本語", "🦅"],
    {"nested": {"deep": [True, False, None, {"x": "y"}]}},
    None,
    True,
    42,
    3.5,
    -0.0,
    {"large_int": 2**63 + 12345},
    {"empty_dict": {}, "empty_list": []},
    ("tuple", "becomes", "list"),
    {"str_key_num": {"1": "value"}},
]


@pytest.mark.parametrize("payload", ORDINARY_PAYLOADS, ids=lambda p: repr(p)[:40])
def test_byte_identical_to_starlette_for_ordinary_payloads(payload):
    assert SafeJSONResponse(payload).body == JSONResponse(payload).body


def test_body_is_compact_utf8_json():
    body = SafeJSONResponse({"k": "café"}).body
    assert body == b'{"k":"caf\xc3\xa9"}'  # ensure_ascii=False, compact separators


# ---------------------------------------------------------------------------
# Non-finite floats at every depth -> null
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_floats_at_every_depth(bad):
    payload = {
        "top": bad,
        "in_list": [1.0, bad, 2.0],
        "in_tuple": (bad,),
        "nested": {"deeper": [{"deepest": bad}]},
    }
    body = json.loads(SafeJSONResponse(payload).body)
    assert body["top"] is None
    assert body["in_list"] == [1.0, None, 2.0]
    assert body["in_tuple"] == [None]
    assert body["nested"]["deeper"][0]["deepest"] is None


def test_non_finite_float_dict_key_becomes_null_key():
    body = json.loads(SafeJSONResponse({float("nan"): 1}).body)
    assert body == {"null": 1}


def test_plain_starlette_raises_on_nan():
    with pytest.raises(ValueError):
        JSONResponse({"x": float("nan")}).body  # noqa: B018  (render happens in __init__)


# ---------------------------------------------------------------------------
# numpy: scalars, arrays, bool, NaN inside arrays
# ---------------------------------------------------------------------------


def test_numpy_scalars_and_arrays():
    payload = {
        "int64": np.int64(7),
        "float32": np.float32(1.5),
        "bool_": np.bool_(True),
        "array": np.array([1.0, 2.5]),
        "nan_array": np.array([1.0, np.nan, np.inf]),
        "2d": np.array([[1, 2], [3, 4]]),
    }
    body = json.loads(SafeJSONResponse(payload).body)
    assert body["int64"] == 7
    assert body["float32"] == pytest.approx(1.5)
    assert body["bool_"] is True
    assert body["array"] == [1.0, 2.5]
    assert body["nan_array"] == [1.0, None, None]
    assert body["2d"] == [[1, 2], [3, 4]]


def test_numpy_nan_scalar_is_null():
    assert json.loads(SafeJSONResponse(np.float64(np.nan)).body) is None


# ---------------------------------------------------------------------------
# datetime / date / Decimal / set / pandas Timestamp / NaT
# ---------------------------------------------------------------------------


def test_datetime_and_date_isoformat():
    dt = datetime(2026, 10, 2, 12, 34, 56, tzinfo=timezone.utc)
    body = json.loads(SafeJSONResponse({"dt": dt, "d": date(2026, 10, 2)}).body)
    assert body["dt"] == dt.isoformat()
    assert body["d"] == "2026-10-02"


def test_datetime_that_previously_failed_now_serializes():
    with pytest.raises(TypeError):
        json.dumps(datetime(2026, 1, 1))
    assert json.loads(SafeJSONResponse(datetime(2026, 1, 1)).body) == "2026-01-01T00:00:00"


def test_decimal_becomes_float_or_null():
    body = json.loads(
        SafeJSONResponse({"d": Decimal("1.25"), "dnan": Decimal("NaN"), "dinf": Decimal("Infinity")}).body
    )
    assert body["d"] == 1.25
    assert body["dnan"] is None
    assert body["dinf"] is None


def test_set_becomes_list():
    body = json.loads(SafeJSONResponse({"s": {1, 2, 3}}).body)
    assert sorted(body["s"]) == [1, 2, 3]


def test_pandas_timestamp_and_nat():
    ts = pd.Timestamp("2026-10-02T12:00:00")
    body = json.loads(SafeJSONResponse({"ts": ts, "nat": pd.NaT}).body)
    assert body["ts"] == ts.isoformat()
    assert body["nat"] is None


def test_pandas_series_is_not_supported():
    """Documented limitation: Series/DataFrame are left as-is and json fails."""
    with pytest.raises(TypeError):
        SafeJSONResponse({"s": pd.Series([1, 2])}).body  # noqa: B018


# ---------------------------------------------------------------------------
# Response plumbing: status_code / headers / background
# ---------------------------------------------------------------------------


def test_status_headers_and_background_passthrough():
    import anyio

    calls = []

    def record(value):
        calls.append(value)

    response = SafeJSONResponse(
        {"ok": True},
        status_code=201,
        headers={"X-Test": "yes"},
        background=BackgroundTask(record, "ran"),
    )
    assert response.status_code == 201
    assert response.headers["x-test"] == "yes"
    assert response.media_type == "application/json"

    async def send(message):
        pass

    async def receive():
        return {"type": "http.request"}  # pragma: no cover

    scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
    anyio.run(response, scope, receive, send)  # starlette runs background after sending
    assert calls == ["ran"]


# ---------------------------------------------------------------------------
# Deep nesting sanity
# ---------------------------------------------------------------------------


def test_deeply_nested_payload_renders():
    deep = "leaf"
    for _ in range(300):
        deep = {"next": [deep]}
    body = json.loads(SafeJSONResponse(deep).body)
    for _ in range(300):
        body = body["next"][0]
    assert body == "leaf"


# ---------------------------------------------------------------------------
# End-to-end through FastAPI: safe app vs plain app
# ---------------------------------------------------------------------------


class _AnyModel(BaseModel):
    payload: dict = {}


def _build_app(safe: bool) -> FastAPI:
    kwargs = {"default_response_class": SafeJSONResponse} if safe else {}
    app = FastAPI(**kwargs)

    @app.get("/dict-nan")
    async def dict_nan():
        return {"value": float("nan")}

    @app.get("/model-nan", response_model=_AnyModel)
    async def model_nan():
        return _AnyModel(payload={"value": float("nan")})

    @app.get("/explicit")
    async def explicit():
        return SafeJSONResponse({"value": float("nan")})

    return app


@pytest.fixture
def safe_client():
    return TestClient(_build_app(safe=True), raise_server_exceptions=False)


@pytest.fixture
def plain_client():
    return TestClient(_build_app(safe=False), raise_server_exceptions=False)


@pytest.mark.parametrize(
    ("path", "expected"),
    [("/dict-nan", {"value": None}), ("/model-nan", {"payload": {"value": None}}), ("/explicit", {"value": None})],
)
def test_safe_app_returns_null_for_nan(safe_client, path, expected):
    r = safe_client.get(path)
    assert r.status_code == 200, r.text
    assert r.json() == expected


def test_plain_app_500s_where_stock_json_would_raise(plain_client):
    """Proof the tests bite: a bare dict with NaN 500s on the stock response class."""
    r = plain_client.get("/dict-nan")
    assert r.status_code == 500, f"plain app should fail on dict NaN, got {r.status_code}"


def test_plain_app_model_nan_is_already_null_via_pydantic(plain_client):
    """Measured: pydantic's own serialization nulls NaN inside response_model
    fields even on the stock response class — no 500 there. The safe app pins
    the same outcome when SafeJSONResponse is the app default."""
    r = plain_client.get("/model-nan")
    assert r.status_code == 200
    assert r.json() == {"payload": {"value": None}}


def test_plain_app_explicit_safe_response_still_works(plain_client):
    """An explicit SafeJSONResponse works regardless of the app default."""
    r = plain_client.get("/explicit")
    assert r.status_code == 200
    assert r.json() == {"value": None}


# ---------------------------------------------------------------------------
# public_error_message / new_error_id
# ---------------------------------------------------------------------------


def test_expected_exception_text_kept_and_truncated():
    assert public_error_message(ValueError("bad input")) == "bad input"
    long = "x" * 500
    assert public_error_message(ValueError(long)) == "x" * 300


def test_expected_custom_tuple():
    assert public_error_message(KeyError("k"), expected=(KeyError,)) == "'k'"


def test_non_expected_exceptions_are_generic():
    for exc in [
        RuntimeError("boom"),
        KeyError("secret"),
        ZeroDivisionError("division by zero"),
        Exception("anything"),
    ]:
        assert public_error_message(exc) == "Internal server error"


def test_no_path_or_secret_leakage_for_non_expected():
    class Custom(Exception):
        pass

    exc = Custom("Connection to postgresql://user:hunter2@10.0.0.5/db failed at /etc/app/config.yaml")
    message = public_error_message(exc)
    assert message == "Internal server error"
    assert "hunter2" not in message
    assert "/etc/" not in message
    assert "Custom" not in message


def test_subclass_of_expected_is_expected():
    class MyValueError(ValueError):
        pass

    assert public_error_message(MyValueError("client typo")) == "client typo"


def test_new_error_id_shape_and_uniqueness():
    ids = {new_error_id() for _ in range(1000)}
    assert len(ids) == 1000
    for error_id in ids:
        assert len(error_id) == 12
        int(error_id, 16)  # hex


def test_error_id_correlates_generic_message_with_log():
    exc = RuntimeError("db password is hunter2")
    error_id = new_error_id()
    assert public_error_message(exc) == "Internal server error"
    assert len(error_id) == 12  # log carries {error_id}: traceback; client sees the id
