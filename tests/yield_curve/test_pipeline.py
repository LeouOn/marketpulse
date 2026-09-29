"""T6: yield-curve pipeline self-start, idempotency, failure recording.

All offline: a fake curve fetcher and in-memory SQLite. The pipeline job
takes injected dependencies (session / fetcher / status store) so no
network and no real DATABASE_URL are needed.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.core.database import Base, YieldCurveSnapshot
from src.scheduler.yield_curve_job import (
    ensure_yield_curve_populated,
    run_yield_curve_pipeline,
)
from src.yield_curve.history import YieldCurveHistory
from src.yield_curve.status import PipelineStatusStore


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        execution_options={"schema_translate_map": {"market_data": None, "analysis": None}},
    )
    Base.metadata.create_all(engine, tables=[YieldCurveSnapshot.__table__])
    with Session(engine) as s:
        yield s
        s.close()


# Yield levels (percent) per tenor: an upward-sloping curve with a mild
# daily drift so deltas / z-scores are defined.
_LEVELS = {
    "3mo": 3.00, "1y": 3.20, "2y": 3.40, "5y": 3.80,
    "7y": 3.95, "10y": 4.05, "20y": 4.25, "30y": 4.35,
}


class FakeCurveFetcher:
    """Returns one business-day frame per tenor over any requested range."""

    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.calls: list[tuple[list[str], date, date]] = []

    def fetch_tenors(self, tenors, start, end):
        self.calls.append((list(tenors), start, end))
        if self.fail:
            return {}
        out = {}
        days = pd.bdate_range(start, end)
        for t in tenors:
            base = _LEVELS.get(t, 4.0)
            out[t] = pd.DataFrame({
                "ts": days,
                "open": [base + 0.001 * i for i in range(len(days))],
                "high": [base + 0.001 * i for i in range(len(days))],
                "low": [base + 0.001 * i for i in range(len(days))],
                "close": [base + 0.001 * i for i in range(len(days))],
                "volume": [float("nan")] * len(days),
                "source": ["fred"] * len(days),
            })
        return out


class TestPipelineRun:
    def test_successful_run_persists_today_snapshot(self, session, tmp_path):
        store = PipelineStatusStore(tmp_path / "status.json")
        res = asyncio.run(run_yield_curve_pipeline(
            session=session, fetcher=FakeCurveFetcher(), status_store=store
        ))
        today = date.today()
        snap = YieldCurveHistory(session).get_snapshot(today)
        assert snap is not None, res
        assert set(snap.curve) == set(_LEVELS)
        assert snap.spreads["2s10s"] == pytest.approx(65.0, abs=1.0)  # (4.05-3.40)*100
        assert snap.shape  # classified
        status = store.load()
        assert status["last_error"] is None
        assert status["last_snapshot_date"] == today.isoformat()

    def test_second_run_same_date_is_idempotent(self, session, tmp_path):
        store = PipelineStatusStore(tmp_path / "status.json")
        asyncio.run(run_yield_curve_pipeline(session=session, fetcher=FakeCurveFetcher(), status_store=store))
        asyncio.run(run_yield_curve_pipeline(session=session, fetcher=FakeCurveFetcher(), status_store=store))
        rows = session.query(YieldCurveSnapshot).count()
        assert rows == 1
        # The fetcher was consulted once; the second run skipped (snapshot exists).
        assert len(store.load()["runs"]) >= 2

    def test_fred_failure_is_recorded_and_surfaced(self, session, tmp_path):
        store = PipelineStatusStore(tmp_path / "status.json")
        res = asyncio.run(run_yield_curve_pipeline(
            session=session, fetcher=FakeCurveFetcher(fail=True), status_store=store
        ))
        assert res["saved"] == 0
        assert res["error"]
        status = store.load()
        assert status["last_error"] == res["error"]
        assert status["last_error_at"]
        assert YieldCurveHistory(session).get_snapshot(date.today()) is None


class TestBackfill:
    def test_backfill_populates_business_days_with_deltas(self, session, tmp_path):
        store = PipelineStatusStore(tmp_path / "status.json")
        res = asyncio.run(run_yield_curve_pipeline(
            session=session,
            fetcher=FakeCurveFetcher(),
            status_store=store,
            backfill_days=10,
        ))
        # backfill_days is *calendar* days back: [today-10d, today] business days.
        days = pd.bdate_range(date.today() - timedelta(days=10), date.today())
        assert res["saved"] == len(days)
        assert session.query(YieldCurveSnapshot).count() == len(days)
        latest = YieldCurveHistory(session).get_snapshot(date.today())
        assert latest is not None
        assert latest.spread_2s10s_delta_5d is not None, "deltas need backfilled history"
        assert latest.shape_trend

    def test_leading_days_without_data_do_not_shift_later_snapshots(self, session, tmp_path):
        """Regression: `curves` skipped empty days but `dates` did not, so zip() paired each
        date with a *later* date's curve and saved every snapshot under the wrong date.

        FRED has no observation before the window's first published day (e.g. a leading
        holiday), so the first business days of a backfill legitimately have no curve.
        """
        today = date.today()
        days = [d.date() for d in pd.bdate_range(today - timedelta(days=10), today)]
        first_obs = days[2]  # two leading business days with no data yet
        ref = first_obs.toordinal()

        class LateStartFetcher:
            def fetch_tenors(self, tenors, start, end):
                idx = pd.bdate_range(first_obs, end)
                out = {}
                for t in tenors:
                    close = [_LEVELS.get(t, 4.0) + 0.001 * (d.toordinal() - ref) for d in idx.date]
                    out[t] = pd.DataFrame({
                        "ts": idx, "open": close, "high": close, "low": close,
                        "close": close, "volume": [float("nan")] * len(idx), "source": ["fred"] * len(idx),
                    })
                return out

        store = PipelineStatusStore(tmp_path / "status.json")
        res = asyncio.run(run_yield_curve_pipeline(
            session=session, fetcher=LateStartFetcher(), status_store=store, backfill_days=10
        ))

        expected_days = days[2:]
        assert res["saved"] == len(expected_days), res
        saved_dates = sorted(row.date for row in session.query(YieldCurveSnapshot).all())
        assert saved_dates == expected_days, "snapshots must carry the date their curve belongs to"
        history = YieldCurveHistory(session)
        for d in expected_days:
            snap = history.get_snapshot(d)
            assert snap is not None
            assert snap.curve["2y"] == pytest.approx(_LEVELS["2y"] + 0.001 * (d.toordinal() - ref)), d
        assert history.get_snapshot(days[0]) is None and history.get_snapshot(days[1]) is None

    def test_ensure_populated_noop_when_data_exists(self, session, tmp_path):
        store = PipelineStatusStore(tmp_path / "status.json")
        fetcher = FakeCurveFetcher()
        asyncio.run(ensure_yield_curve_populated(
            session=session, fetcher=fetcher, status_store=store, backfill_days=10
        ))
        assert fetcher.calls, "empty DB must trigger a backfill"
        fetcher2 = FakeCurveFetcher()
        ran = asyncio.run(ensure_yield_curve_populated(
            session=session, fetcher=fetcher2, status_store=store, backfill_days=10
        ))
        assert ran is False
        assert fetcher2.calls == [], "populated DB must not re-fetch"
