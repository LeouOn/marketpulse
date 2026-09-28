"""Tests for the research router (B7).

We exercise the REST endpoints (which are the deterministic surface) and
verify the chat endpoint produces an NDJSON stream. LLM-backed chat is
tested with a mock ModelRouter.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
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


# ---------------------------------------------------------------------------
# Macro regimes endpoints (T3a)
#
# Offline coverage for GET /api/research/regimes and
# GET /api/research/{asset}/regime. The handlers import
# MacroFactorProvider *inside* the function, so we patch the attribute on
# src.research.macro.factors -- no network, no FRED key needed.
# ---------------------------------------------------------------------------

_REGIME_NAMES = {
    "RISK_ON",
    "DEFLATION_SCARE",
    "INFLATION_ACCEL",
    "REAL_YIELD_SHOCK",
    "RECESSION",
}

#: Fetch-window padding the router must apply so the rules classifier's
#: 5-year trailing z-score window has history (mirrors cli._build_regime_tape).
_REGIME_PAD_DAYS = 365 * 6


def _fake_factor_frame() -> pd.DataFrame:
    """A realistic MacroFactorProvider.load_factors return value.

    Daily index spanning ~9 years up to tomorrow, all 12 canonical factor
    columns, mild slopes so rolling z-scores are defined.
    """
    from src.research.macro.factors import FACTOR_COLUMNS

    end = date.today() + timedelta(days=1)
    start = end - timedelta(days=365 * 9)
    idx = pd.date_range(start, end, freq="D", name="date")
    n = len(idx)
    data = {}
    for i, col in enumerate(FACTOR_COLUMNS):
        if col == "sahm_recession":
            data[col] = [False] * n
        else:
            base = 50.0 + 10.0 * i
            data[col] = [base + 0.01 * j for j in range(n)]
    return pd.DataFrame(data, index=idx)


class _FakeMacroProvider:
    """Offline MacroFactorProvider stand-in; records load_factors calls."""

    def __init__(self, error: Exception | None = None):
        self.frame = _fake_factor_frame()
        self.error = error
        self.calls: list[tuple[date, date]] = []

    def load_factors(self, start: date, end: date) -> pd.DataFrame:
        self.calls.append((start, end))
        if self.error is not None:
            raise self.error
        mask = (self.frame.index.date >= start) & (self.frame.index.date <= end)
        return self.frame.loc[mask].copy()


def _patch_macro_provider(monkeypatch, fake: _FakeMacroProvider) -> None:
    import src.research.macro.factors as factors_mod

    monkeypatch.setattr(factors_mod, "MacroFactorProvider", lambda: fake)


def test_regimes_endpoint_returns_tape_with_fake_provider(client, monkeypatch):
    fake = _FakeMacroProvider()
    _patch_macro_provider(monkeypatch, fake)

    r = client.get("/api/research/regimes?start=2024-01-01&end=2024-01-31")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    records = body["data"]["regimes"]
    assert body["data"]["count"] == len(records) > 0
    assert body["data"]["start"] == "2024-01-01"
    assert body["data"]["end"] == "2024-01-31"
    for rec in records:
        assert "2024-01-01" <= rec["date"] <= "2024-01-31"
        assert rec["dominant_regime"] in _REGIME_NAMES
        assert sum(rec[name] for name in _REGIME_NAMES) == pytest.approx(1.0)
    # The fetch must be padded so the 5y trailing z-score window has history.
    assert fake.calls == [
        (date(2024, 1, 1) - timedelta(days=_REGIME_PAD_DAYS), date(2024, 1, 31))
    ]


def test_regimes_endpoint_default_window(client, monkeypatch):
    fake = _FakeMacroProvider()
    _patch_macro_provider(monkeypatch, fake)

    r = client.get("/api/research/regimes")

    assert r.status_code == 200, r.text
    assert r.json()["data"]["count"] > 0
    # Defaults: end=today, start=today - 2y, fetch padded by 6 more years.
    assert len(fake.calls) == 1
    fetch_start, fetch_end = fake.calls[0]
    assert fetch_end == date.today()
    assert fetch_start == date.today() - timedelta(days=365 * 8)


def test_regimes_endpoint_rejects_malformed_start(client):
    r = client.get("/api/research/regimes?start=not-a-date")
    assert r.status_code == 400
    assert "start" in r.json()["detail"]


def test_regimes_endpoint_surfaces_provider_error_as_503(client, monkeypatch):
    fake = _FakeMacroProvider(error=RuntimeError("FRED_API_KEY not set"))
    _patch_macro_provider(monkeypatch, fake)

    r = client.get("/api/research/regimes")

    assert r.status_code == 503
    detail = r.json()["detail"]
    assert "Macro factor data unavailable" in detail
    assert "FRED_API_KEY not set" in detail


def test_asset_regime_endpoint_returns_current_regime(client, monkeypatch):
    fake = _FakeMacroProvider()
    _patch_macro_provider(monkeypatch, fake)

    r = client.get("/api/research/BTC/regime")

    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["asset"] == "BTC"
    assert data["regime"] in _REGIME_NAMES
    assert set(data["probs"]) == _REGIME_NAMES
    assert sum(data["probs"].values()) == pytest.approx(1.0)
    assert data["source"] == "rules"
    assert data["timestamp"]
    # One padded fetch ending today.
    assert len(fake.calls) == 1
    fetch_start, fetch_end = fake.calls[0]
    assert fetch_end == date.today()
    assert fetch_start == date.today() - timedelta(days=_REGIME_PAD_DAYS)


def test_asset_regime_endpoint_asof_date(client, monkeypatch):
    fake = _FakeMacroProvider()
    _patch_macro_provider(monkeypatch, fake)

    r = client.get("/api/research/BTC/regime?date=2024-06-15")

    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["timestamp"].startswith("2024-06-15")
    fetch_start, fetch_end = fake.calls[0]
    assert fetch_end == date(2024, 6, 15)
    assert fetch_start == date(2024, 6, 15) - timedelta(days=_REGIME_PAD_DAYS)


def test_asset_regime_endpoint_rejects_malformed_date(client):
    r = client.get("/api/research/BTC/regime?date=oops")
    assert r.status_code == 400
    assert "date" in r.json()["detail"]
