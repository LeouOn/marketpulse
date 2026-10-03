"""Central response boundaries, exercised without lifespan or live providers."""

import json

import numpy as np
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.routers.deps import MarketResponse


@pytest.fixture
def client():
    original_routes = list(app.router.routes)

    @app.get("/__json_probe/model", response_model=MarketResponse)
    def model_payload():
        return MarketResponse(
            success=True,
            data={"flag": np.bool_(True), "count": np.int64(7), "values": np.array([1.0, np.nan, np.inf])},
            timestamp="now",
        )

    @app.get("/__json_probe/dict")
    def dict_payload():
        return {"value": float("nan")}

    @app.get("/__json_probe/crash")
    def crash():
        raise ValueError("private database password at /srv/internal")

    @app.get("/__json_probe/http/{status_code}")
    def http_error(status_code: int):
        raise HTTPException(status_code, detail="private upstream error", headers={"X-Test": "kept"})

    @app.get("/__json_probe/helper")
    def helper_error():
        from src.api.safe_json import internal_http_error

        try:
            raise RuntimeError("private helper exception")
        except RuntimeError as exc:
            raise internal_http_error(exc) from exc

    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.router.routes[:] = original_routes


def test_market_response_normalizes_before_pydantic_serializes(client):
    response = client.get("/__json_probe/model")
    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {"flag": True, "count": 7, "values": [1.0, None, None]},
        "error": None,
        "timestamp": "now",
    }


def test_manual_market_response_dump_is_safe():
    model = MarketResponse(success=True, data={"x": np.int64(4), "nan": np.nan}, timestamp="now")
    assert model.model_dump()["data"] == {"x": 4, "nan": None}
    assert json.loads(model.model_dump_json())["data"] == {"x": 4, "nan": None}


def test_plain_dict_uses_safe_app_default(client):
    response = client.get("/__json_probe/dict")
    assert response.status_code == 200
    assert response.json() == {"value": None}


def test_unexpected_value_error_is_generic_and_logged_with_id(client):
    from loguru import logger

    messages = []
    sink = logger.add(lambda message: messages.append(str(message)))
    try:
        response = client.get("/__json_probe/crash")
    finally:
        logger.remove(sink)
    assert response.status_code == 500
    body = response.json()
    assert body["success"] is False
    assert body["error"] == body["detail"] == "Internal server error"
    assert len(body["error_id"]) == 12
    assert "private" not in response.text
    assert any(body["error_id"] in message and "private database" in message for message in messages)


def test_http_500_is_masked_and_preserves_headers(client):
    response = client.get("/__json_probe/http/503")
    assert response.status_code == 503
    assert response.headers["X-Test"] == "kept"
    assert response.json()["detail"] == "Internal server error"
    assert response.json()["error_id"]
    assert "private upstream" not in response.text


def test_deliberate_4xx_keeps_existing_shape(client):
    response = client.get("/__json_probe/http/400")
    assert response.status_code == 400
    assert response.headers["X-Test"] == "kept"
    assert response.json() == {"detail": "private upstream error"}


def test_router_http_helper_keeps_one_correlation_id(client):
    response = client.get("/__json_probe/helper")
    assert response.status_code == 500
    assert response.json()["error_id"] == response.headers["X-Error-ID"]
    assert "private helper" not in response.text


def test_soft_fail_helper_is_generic_even_for_value_error():
    from src.api.routers.deps import unexpected_response

    response = unexpected_response(ValueError("private upstream URL"))
    body = json.loads(response.model_dump_json())
    assert body["success"] is False
    assert body["error"] == "Internal server error"
    assert body["error_id"]
    assert "private upstream" not in response.model_dump_json()


def test_market_response_keeps_data_schema_and_excludes_unused_error_id():
    schema = MarketResponse.model_json_schema()
    assert schema["properties"]["data"] == {
        "anyOf": [{"additionalProperties": True, "type": "object"}, {"type": "null"}],
        "default": None,
        "title": "Data",
    }
    assert "error_id" not in MarketResponse(success=False, error="Expected validation", timestamp="now").model_dump()
