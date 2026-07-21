# tests/test_llm_rag_endpoints.py
import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.routers import llm as llm_router

client = TestClient(app)


class _FakeEnhanced:
    async def analyze_with_knowledge(self, query, market_data=None, prompt_type="trading_analyst", max_tokens=400):
        return f"analysis of: {query}"

    async def test_hypothesis(self, hypothesis_name, market_data=None):
        return {"hypothesis": hypothesis_name, "verdict": "inconclusive", "confidence": 0.5}

    def get_related_knowledge(self, query, max_results=3):
        return []


@pytest.fixture(autouse=True)
def fake_enhanced(monkeypatch):
    async def _get():
        return _FakeEnhanced()

    monkeypatch.setattr(llm_router, "_get_enhanced_client", _get)


def test_enhanced_analysis():
    r = client.post("/api/llm/enhanced-analysis", json={"query": "is NQ extended?"})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert "analysis" in body["data"]


def test_test_hypothesis():
    r = client.post("/api/llm/test-hypothesis", json={"hypothesis_name": "overnight_margin_cascade"})
    assert r.status_code == 200
    assert r.json()["data"]["hypothesis"] == "overnight_margin_cascade"


def test_knowledge_term_found():
    r = client.get("/api/llm/knowledge/FVG")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["definition"]


def test_knowledge_term_missing():
    r = client.get("/api/llm/knowledge/nonexistent_term_xyz")
    assert r.status_code == 200
    assert r.json()["success"] is False


def test_retrieve_context():
    r = client.post("/api/llm/retrieve-context", json={"query": "fair value gap", "max_results": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["chunks"]
    assert "retrieval_mode" in body["data"]
