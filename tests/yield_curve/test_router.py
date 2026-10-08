"""T6: yield-curve API honesty + manual trigger.

The endpoints must explain themselves when there is no data (additive
fields -- existing consumers keep working) and expose a manual refresh.
Offline: history and status are monkeypatched; no DB, no network.
"""

from __future__ import annotations

from datetime import date, timedelta
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
        rows.append(
            SimpleNamespace(
                date=date(2026, 9, 25),
                curve={"2y": 3.4, "10y": 4.05},
                spreads={"2s10s": 65.0, "3m10y": 105.0, "5s30s": 55.0, "2s30s": 95.0},
                shape="NORMAL",
                shape_trend="STEEPENING",
                recession_prob_nyfed=0.30,
                spread_2s10s_delta_5d=2.0,
                spread_2s10s_delta_30d=8.0,
                zscore_2s10s_90d=0.4,
            )
        )
    return rows


class _StubHistory:
    def __init__(self, rows):
        self._rows = rows

    def get_history(self, days=90):
        """Mirrors the real DAO: wall-clock cutoff of ``today - days``."""
        cutoff = date.today() - timedelta(days=days)
        return [r for r in self._rows if r.date >= cutoff]

    def get_latest(self):
        """Newest row by date, no wall-clock floor (mirrors the real DAO)."""
        return self._rows[0] if self._rows else None


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


class TestCurrentServesLatestSnapshot:
    """Round 3: /current must serve the newest stored snapshot with NO date
    floor — FRED's one-business-day lag makes honestly-dated snapshots 1-6+
    calendar days old on a healthy pipeline. Fails on a days=1 cutoff."""

    @pytest.mark.parametrize("age_days", [1, 2, 4, 6])
    def test_serves_snapshot_regardless_of_age(self, client, monkeypatch, age_days):
        rows = _stub_rows(n=1)
        rows[0].date = date.today() - timedelta(days=age_days)
        _patch(monkeypatch, rows, None)
        body = client.get("/api/yield-curve/current").json()
        assert body["data"] is not None, body
        assert body["data"]["date"] == rows[0].date.isoformat()
        assert body["no_data"] is None

    def test_no_data_only_when_table_truly_empty(self, client, monkeypatch):
        _patch(monkeypatch, [], None)
        body = client.get("/api/yield-curve/current").json()
        assert body["data"] is None
        assert body["no_data"]


class TestStalenessInBusinessDays:
    """'stale' means behind the expected newest observation (the last US
    business day strictly before today, per FRED's one-day lag), counted in
    missing business days (plain weekdays; a holiday adds one day of slack).
    Healthy weekends/Mondays must NOT be stale; a week behind IS."""

    @pytest.mark.parametrize(
        ("case", "frozen", "snap_date", "stale", "behind"),
        [
            ("saturday_healthy", date(2026, 10, 3), date(2026, 10, 1), False, 1),
            ("sunday_healthy", date(2026, 10, 4), date(2026, 10, 1), False, 1),
            ("monday_morning_healthy", date(2026, 10, 5), date(2026, 10, 1), False, 1),
            ("tuesday_after_holiday_healthy", date(2026, 1, 20), date(2026, 1, 16), False, 1),
            ("week_behind_is_stale", date(2026, 10, 3), date(2026, 9, 24), True, 6),
        ],
        ids=[
            "saturday_healthy",
            "sunday_healthy",
            "monday_morning_healthy",
            "tuesday_after_holiday_healthy",
            "week_behind_is_stale",
        ],
    )
    def test_stale_flag_counts_missing_business_days(self, client, monkeypatch, case, frozen, snap_date, stale, behind):
        class FrozenDate(date):
            @classmethod
            def today(cls):
                return frozen

        monkeypatch.setattr(ycr, "date", FrozenDate)
        rows = _stub_rows(n=1)
        rows[0].date = snap_date
        _patch(monkeypatch, rows, None)
        body = client.get("/api/yield-curve/current").json()
        assert body["data"]["stale"] is stale, (case, body["data"])
        assert body["data"]["business_days_behind"] == behind, (case, body["data"])
        assert body["data"]["days_since_update"] == (frozen - snap_date).days

    def test_stale_days_env_var_threshold(self, client, monkeypatch):
        """YIELD_CURVE_STALE_DAYS keeps its name; new meaning = allowed missing
        business days behind the expected newest observation."""

        class FrozenDate(date):
            @classmethod
            def today(cls):
                return date(2026, 10, 3)  # Saturday

        monkeypatch.setattr(ycr, "date", FrozenDate)
        monkeypatch.setenv("YIELD_CURVE_STALE_DAYS", "0")
        rows = _stub_rows(n=1)
        rows[0].date = date(2026, 10, 1)  # healthy Thursday snapshot, 1 bday behind
        _patch(monkeypatch, rows, None)
        body = client.get("/api/yield-curve/current").json()
        assert body["data"]["business_days_behind"] == 1
        assert body["data"]["stale"] is True  # threshold 0

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
