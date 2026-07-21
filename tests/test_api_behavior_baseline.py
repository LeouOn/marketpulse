"""Behavior anchors for Phase A1: must pass identically before and after refactor."""

import json

import pytest
from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


def test_root():
    r = client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, dict)


def test_debug_routes_lists_routes():
    r = client.get("/api/debug/routes")
    assert r.status_code == 200
    body = r.json()
    text = json.dumps(body)
    assert "/api/llm/chat" in text
    assert "/api/market/dashboard" in text


def test_test_status():
    r = client.get("/api/test/status")
    assert r.status_code == 200


def test_llm_models_shape():
    r = client.get("/api/llm/models")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert isinstance(body["data"]["models"], list)


def test_llm_chat_graceful_offline():
    """Anchor pre-refactor offline behavior for the ``market`` keyword branch."""
    r = client.post("/api/llm/chat", json={"message": "hello market"})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert isinstance(body["data"]["response"], str)
    assert len(body["data"]["response"]) > 0


def test_market_dashboard_shape():
    r = client.get("/api/market/dashboard")
    assert r.status_code == 200
    body = r.json()
    assert "success" in body and "timestamp" in body


@pytest.mark.xfail(reason="symbols router not mounted until Task 4", strict=True)
def test_symbols_list():
    r = client.get("/api/market/symbols")
    assert r.status_code == 200
    assert "success" in r.json()
