"""T6: yield-curve API honesty + manual trigger.

The endpoints must explain themselves when there is no data (additive
fields -- existing consumers keep working) and expose a manual refresh.
Offline: history and status are monkeypatched; no DB, no network.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api.routers.yield_curve as ycr


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(ycr.router)
    return TestClient(app)


def _stub_rows(n=2):
    rows = []
    for _i in range(n):
        rows.append(SimpleNamespace(
            date=date(2026, 9, 25),
            curve={"2y": 3.4, "10y": 4.05},
            spreads={"2s10s": 65.0, "3m10y": 105.0, "5s30s": 55.0, "2s30s": 95.0},
            shape="NORMAL",
            shape_trend="STEEPENING",
            recession_prob_nyfed=0.30,
            spread_2s10s_delta_5d=2.0,
            spread_2s10s_delta_30d=8.0,
            zscore_2s10s_90d=0.4,
        ))
    return rows


class _StubHistory:
    def __init__(self, rows):
        self._rows = rows

    def get_history(self, days=90):
        return self._rows


def _patch(monkeypatch, rows, status):
    monkeypatch.setattr(ycr, "_get_history", lambda: (_StubHistory(rows), _NullSession()))
    monkeypatch.setattr(ycr, "_load_status", lambda: status)


class _NullSession:
    def close(self):
        pass


class TestCurrentEndpoint:
    def test_with_data_no_reasons(self, client, monkeypatch):
        _patch(monkeypatch, _stub_rows(), None)
        r = client.get("/api/yield-curve/current")
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["data"]["spreads"]["2s10s"] == 65.0
        assert body["no_data"] is None
        assert body["last_error"] is None

    def test_no_data_never_run(self, client, monkeypatch):
        _patch(monkeypatch, [], None)
        r = client.get("/api/yield-curve/current")
        body = r.json()
        assert body["success"] is True
        assert body["data"] is None
        assert body["no_data"] == "pipeline has not run"
        assert body["last_error"] is None

    def test_no_data_with_error_surfaces_last_error(self, client, monkeypatch):
        _patch(monkeypatch, [], {"last_error": "FRED_API_KEY not set", "last_error_at": "2026-09-28T09:00:00"})
        r = client.get("/api/yield-curve/current")
        body = r.json()
        assert body["data"] is None
        assert body["no_data"] == "pipeline has not run"
        assert "FRED_API_KEY not set" in body["last_error"]


class TestHistoryEndpoint:
    def test_history_no_data_explains(self, client, monkeypatch):
        _patch(monkeypatch, [], None)
        r = client.get("/api/yield-curve/history")
        body = r.json()
        assert body["data"]["snapshots"] == []
        assert body["no_data"] == "pipeline has not run"

    def test_history_with_data(self, client, monkeypatch):
        _patch(monkeypatch, _stub_rows(), None)
        r = client.get("/api/yield-curve/history")
        body = r.json()
        assert len(body["data"]["snapshots"]) == 2
        assert body["no_data"] is None


class TestManualTrigger:
    def test_refresh_runs_pipeline_and_reports(self, client, monkeypatch):
        called = {}

        async def _fake_pipeline(**kw):
            called.update(kw)
            return {"saved": 1, "date": "2026-09-28", "error": None}

        import src.scheduler.yield_curve_job as job_mod
        monkeypatch.setattr(job_mod, "run_yield_curve_pipeline", _fake_pipeline)
        r = client.post("/api/yield-curve/refresh")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["success"] is True
        assert body["data"]["saved"] == 1
