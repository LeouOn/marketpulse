"""Tests for the research router (B7).

We exercise the REST endpoints (which are the deterministic surface) and
verify the chat endpoint produces an NDJSON stream. LLM-backed chat is
tested with a mock ModelRouter.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api.research_router import router as research_router


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Build a TestClient and redirect data/reports dirs to tmp_path."""
    from src.research import data as data_mod
    from src.research import tools as tools_mod

    # Seed a tiny daily cache so load_daily hits it without network
    monkeypatch.setattr(data_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(data_mod, "DAILY_CSV", tmp_path / "daily.csv")
    df = pd.DataFrame(
        {
            "ts": pd.date_range("2024-01-01", periods=120, freq="D"),
            "open": [40000.0 + i * 50.0 for i in range(120)],
            "high": [40000.0 + i * 50.0 + 100 for i in range(120)],
            "low": [40000.0 + i * 50.0 - 100 for i in range(120)],
            "close": [40000.0 + i * 50.0 for i in range(120)],
            "volume": [1.0] * 120,
            "source": "test",
        }
    )
    df.to_csv(tmp_path / "daily.csv", index=False)
    # Block network fetches
    monkeypatch.setattr(data_mod, "fetch_daily_yahoo", lambda *a, **kw: pd.DataFrame())
    monkeypatch.setattr(data_mod, "fetch_hourly_cryptocompare", lambda *a, **kw: pd.DataFrame())

    # Redirect reports dir
    monkeypatch.setattr(tools_mod, "REPORTS_DIR", tmp_path / "reports")

    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(research_router)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Strategy / scaling endpoints
# ---------------------------------------------------------------------------


def test_list_strategies(client):
    r = client.get("/api/research/strategies")
    assert r.status_code == 200
    body = r.json()
    assert body["success"]
    names = {s["name"] for s in body["data"]}
    assert "BuyAndHold" in names
    assert "DCAFixedAmount" in names


def test_describe_strategy_known(client):
    r = client.get("/api/research/strategies/DCAFixedAmount")
    assert r.status_code == 200
    assert r.json()["data"]["name"] == "DCAFixedAmount"


def test_describe_strategy_unknown(client):
    r = client.get("/api/research/strategies/Nope")
    assert r.status_code == 404


def test_list_scaling(client):
    r = client.get("/api/research/scaling")
    assert r.status_code == 200
    names = {s["name"] for s in r.json()["data"]}
    assert "KellyCriterion" in names


def test_describe_scaling_known(client):
    r = client.get("/api/research/scaling/KellyCriterion")
    assert r.status_code == 200


def test_describe_scaling_unknown(client):
    r = client.get("/api/research/scaling/Nope")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Data summary
# ---------------------------------------------------------------------------


def test_data_summary(client):
    r = client.get("/api/research/data/summary?timeframe=daily")
    assert r.status_code == 200
    body = r.json()
    assert body["success"]
    assert body["data"]["rows"] == 120


def test_data_summary_with_range(client):
    r = client.get(
        "/api/research/data/summary?start=2024-02-01&end=2024-03-01&timeframe=daily"
    )
    assert r.status_code == 200
    assert r.json()["data"]["rows"] < 120


# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------


def test_backtest(client):
    r = client.post(
        "/api/research/backtest",
        json={
            "strategy": "BuyAndHold",
            "start": "2024-01-15",
            "end": "2024-04-01",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"]
    assert "metrics" in body["data"]
    assert body["data"]["strategy"] == "BuyAndHold"
    assert body["report_id"]


def test_backtest_unknown_strategy(client):
    r = client.post("/api/research/backtest", json={"strategy": "NotAReal"})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Monte Carlo
# ---------------------------------------------------------------------------


def test_montecarlo_gbm(client):
    r = client.post(
        "/api/research/montecarlo",
        json={"method": "gbm", "n_paths": 50, "n_steps": 30, "mu": 0.2, "sigma": 0.5, "seed": 0},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"]
    assert "terminal_median" in body["data"]


def test_montecarlo_block_bootstrap(client):
    r = client.post(
        "/api/research/montecarlo",
        json={
            "method": "block_bootstrap",
            "n_paths": 50,
            "n_steps": 100,
            "start": "2024-01-15",
            "end": "2024-04-01",
        },
    )
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# Compare
# ---------------------------------------------------------------------------


def test_compare(client):
    r = client.post(
        "/api/research/compare",
        json={
            "strategies": ["BuyAndHold", "DCAFixedAmount"],
            "start": "2024-01-15",
            "end": "2024-04-01",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"]
    assert body["data"]["count"] == 2


def test_compare_empty(client):
    r = client.post("/api/research/compare", json={"strategies": []})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Explain metric
# ---------------------------------------------------------------------------


def test_explain_metric(client):
    r = client.post("/api/research/explain-metric", json={"name": "sharpe"})
    assert r.status_code == 200
    assert "Sharpe" in r.json()["data"]["explanation"]


def test_explain_metric_unknown(client):
    r = client.post("/api/research/explain-metric", json={"name": "made_up_term"})
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


def test_list_reports_empty(client):
    r = client.get("/api/research/reports")
    assert r.status_code == 200
    assert r.json() == {"reports": []}


def test_list_reports_after_backtest(client):
    # Run a backtest to create a report
    bt = client.post(
        "/api/research/backtest",
        json={"strategy": "BuyAndHold", "start": "2024-01-15", "end": "2024-04-01"},
    )
    assert bt.status_code == 200
    rid = bt.json()["report_id"]
    # Now list
    r = client.get("/api/research/reports")
    assert r.status_code == 200
    ids = [x["id"] for x in r.json()["reports"]]
    assert rid in ids


def test_get_report(client):
    bt = client.post(
        "/api/research/backtest",
        json={"strategy": "BuyAndHold", "start": "2024-01-15", "end": "2024-04-01"},
    )
    rid = bt.json()["report_id"]
    r = client.get(f"/api/research/reports/{rid}")
    assert r.status_code == 200
    assert r.json()["id"] == rid


def test_get_report_unknown(client):
    r = client.get("/api/research/reports/does_not_exist")
    assert r.status_code == 404


def test_get_report_image(client):
    bt = client.post(
        "/api/research/backtest",
        json={"strategy": "BuyAndHold", "start": "2024-01-15", "end": "2024-04-01"},
    )
    rid = bt.json()["report_id"]
    r = client.get(f"/api/research/reports/{rid}/image/equity_png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"


# ---------------------------------------------------------------------------
# Chat endpoint (mocked LLM)
# ---------------------------------------------------------------------------


def test_chat_streams_ndjson_with_tool_call(client):
    """Mock ModelRouter to return one tool call, then a final answer."""
    from src.llm import model_router as router_mod

    # First call: LLM returns a tool_call
    tool_call_response = {
        "choices": [
            {
                "message": {
                    "content": "Let me look up strategies.",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {
                                "name": "list_strategies",
                                "arguments": "{}",
                            },
                        }
                    ],
                }
            }
        ]
    }
    # Second call: LLM returns the final answer
    final_response = {
        "choices": [{"message": {"content": "There are 7 strategies. BuyAndHold, NoTrade, ..."}}]
    }

    call_count = {"n": 0}

    class _Router:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def generate(self, *a, **kw):
            call_count["n"] += 1
            return tool_call_response if call_count["n"] == 1 else final_response

    with patch.object(router_mod, "ModelRouter", _Router):
        r = client.post(
            "/api/research/chat",
            json={"messages": [{"role": "user", "content": "What strategies are available?"}]},
        )
        assert r.status_code == 200
        events = []
        for line in r.text.splitlines():
            if line.strip():
                events.append(json.loads(line))

    types = [e["type"] for e in events]
    assert "tool_call" in types
    assert "tool_result" in types
    assert "final" in types
    final = next(e for e in events if e["type"] == "final")
    assert "strategies" in final["content"]


def test_chat_handles_llm_error(client):
    """If ModelRouter fails, the chat stream should emit an error event."""
    from src.llm import model_router as router_mod

    class _Router:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def generate(self, *a, **kw):
            raise RuntimeError("LLM down")

    with patch.object(router_mod, "ModelRouter", _Router):
        r = client.post(
            "/api/research/chat",
            json={"messages": [{"role": "user", "content": "Hello?"}]},
        )
        assert r.status_code == 200
        events = [json.loads(line) for line in r.text.splitlines() if line.strip()]
    assert any(e.get("type") == "error" for e in events)
