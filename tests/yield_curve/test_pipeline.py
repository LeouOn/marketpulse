"""T6: yield-curve pipeline self-start, idempotency, failure recording.

All offline: a fake curve fetcher and in-memory SQLite. The pipeline job
takes injected dependencies (session / fetcher / status store) so no
network and no real DATABASE_URL are needed.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

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
    "3mo": 3.00,
    "1y": 3.20,
    "2y": 3.40,
    "5y": 3.80,
    "7y": 3.95,
    "10y": 4.05,
    "20y": 4.25,
    "30y": 4.35,
}


class LagFaithfulFetcher:
    """FRED-faithful fake for the observation-driven pipeline.

    Models the publication behaviour verified against the real FRED API on
    2026-10-03: observations exist only on business days that are not in
    ``holidays`` (weekends never; bond-market closures passed explicitly),
    and the newest observation *visible* when the wall clock reads T is
    dated the last business day strictly before the last business day <= T
    (one-business-day lag; over a weekend the newest is Thursday's).
    ``first_obs`` drops earlier observations (late series start).
    """

    def __init__(self, *, holidays=frozenset(), fail=False, first_obs=None):
        self.holidays = frozenset(holidays)
        self.fail = fail
        self.first_obs = first_obs
        self.calls: list[tuple[list[str], date, date]] = []

    def _visible_limit(self, end: date) -> date:
        bdays = pd.bdate_range(end - timedelta(days=14), end)
        b_anchor = bdays[-1].date()  # last business day <= end
        strictly_before = pd.bdate_range(b_anchor - timedelta(days=14), b_anchor)[:-1]
        return strictly_before[-1].date()

    def fetch_tenors(self, tenors, start, end):
        self.calls.append((list(tenors), start, end))
        if self.fail:
            return {}
        limit = self._visible_limit(end)
        days = [d.date() for d in pd.bdate_range(start, end)]
        days = [d for d in days if d <= limit and d not in self.holidays]
        if self.first_obs is not None:
            days = [d for d in days if d >= self.first_obs]
        if not days:
            return {}
        out = {}
        for t in tenors:
            base = _LEVELS.get(t, 4.0)
            close = [base + 0.001 * (d.toordinal() - date(2026, 1, 5).toordinal()) for d in days]
            out[t] = pd.DataFrame(
                {
                    "ts": days,
                    "open": close,
                    "high": close,
                    "low": close,
                    "close": close,
                    "volume": [float("nan")] * len(days),
                    "source": ["fred"] * len(days),
                }
            )
        return out


def _freeze_today(monkeypatch, d: date):
    """Freeze the pipeline's wall clock (inject `today` via the module's
    `date` reference) so the tests are day-of-week independent."""
    import src.scheduler.yield_curve_job as yj

    class FrozenDate(date):
        @classmethod
        def today(cls):
            return d

    monkeypatch.setattr(yj, "date", FrozenDate)


#: (label, frozen wall clock, holidays, expected latest visible observation)
_ClockCase = [
    ("tuesday_evening", date(2026, 10, 6), frozenset(), date(2026, 10, 5)),  # Mon
    ("wednesday_morning", date(2026, 10, 7), frozenset(), date(2026, 10, 6)),  # Tue
    ("saturday", date(2026, 10, 3), frozenset(), date(2026, 10, 1)),  # Thu
    ("sunday", date(2026, 10, 4), frozenset(), date(2026, 10, 1)),  # Thu
    ("monday_after_mlk", date(2026, 1, 20), frozenset({date(2026, 1, 19)}), date(2026, 1, 16)),  # Fri
    ("good_friday_weekend", date(2026, 4, 4), frozenset({date(2026, 4, 3)}), date(2026, 4, 2)),  # Thu
]


class TestPipelineRun:
    @pytest.mark.parametrize(
        ("case", "frozen", "holidays", "latest"),
        _ClockCase,
        ids=[c[0] for c in _ClockCase],
    )
    def test_daily_run_snapshots_latest_visible_observation(
        self, session, tmp_path, monkeypatch, case, frozen, holidays, latest
    ):
        """On any clock (weekday 16:30, weekend, post-holiday, Good Friday)
        the daily run succeeds and snapshots exactly the newest observation
        FRED has published — never the wall-clock day, never a holiday."""
        _freeze_today(monkeypatch, frozen)
        store = PipelineStatusStore(tmp_path / "status.json")
        res = asyncio.run(
            run_yield_curve_pipeline(session=session, fetcher=LagFaithfulFetcher(holidays=holidays), status_store=store)
        )
        assert res["error"] is None, (case, res)
        assert res["saved"] == 1, (case, res)
        assert res["date"] == latest.isoformat(), (case, res)
        history = YieldCurveHistory(session)
        snap = history.get_snapshot(latest)
        assert snap is not None, (case, latest, res)
        assert set(snap.curve) == set(_LEVELS)
        assert snap.spreads["2s10s"] == pytest.approx(65.0, abs=1.0)  # (4.05-3.40)*100
        assert snap.shape  # classified
        # nothing newer than the latest visible observation, nothing on a holiday
        saved_dates = sorted(row.date for row in session.query(YieldCurveSnapshot).all())
        assert saved_dates == [latest], (case, saved_dates)
        status = store.load()
        assert status["last_error"] is None
        assert status["last_snapshot_date"] == latest.isoformat()

    def test_second_run_is_idempotent_success(self, session, tmp_path, monkeypatch):
        """A DB already holding the latest observation L turns the run into a
        recorded no-op (the window is still fetched — cheap via the parquet
        cache — but nothing is re-saved)."""
        _freeze_today(monkeypatch, date(2026, 10, 3))  # Saturday; L = Thursday
        store = PipelineStatusStore(tmp_path / "status.json")
        res1 = asyncio.run(run_yield_curve_pipeline(session=session, fetcher=LagFaithfulFetcher(), status_store=store))
        res2 = asyncio.run(run_yield_curve_pipeline(session=session, fetcher=LagFaithfulFetcher(), status_store=store))
        assert res1["saved"] == 1 and res2["saved"] == 0
        assert res2["error"] is None and res2["date"] == "2026-10-01"
        assert session.query(YieldCurveSnapshot).count() == 1
        status = store.load()
        assert status["last_error"] is None
        assert status["last_snapshot_date"] == "2026-10-01"

    def test_fetch_with_no_usable_observation_is_the_only_failure(self, session, tmp_path, monkeypatch):
        """ok=False happens only when the trailing window holds no usable
        observation at all (broken fetch / no data for ~10 days)."""
        _freeze_today(monkeypatch, date(2026, 10, 3))  # Saturday
        store = PipelineStatusStore(tmp_path / "status.json")
        res = asyncio.run(
            run_yield_curve_pipeline(session=session, fetcher=LagFaithfulFetcher(fail=True), status_store=store)
        )
        assert res["saved"] == 0
        assert res["error"] and "no tenor observations" in res["error"]
        status = store.load()
        assert status["last_error"] == res["error"]
        assert status["last_error_at"]
        assert YieldCurveHistory(session).get_snapshot(date(2026, 10, 1)) is None


class TestBackfill:
    def test_backfill_snapshots_every_observation_date_with_deltas(self, session, tmp_path, monkeypatch):
        _freeze_today(monkeypatch, date(2026, 10, 3))  # Saturday
        store = PipelineStatusStore(tmp_path / "status.json")
        res = asyncio.run(
            run_yield_curve_pipeline(
                session=session,
                fetcher=LagFaithfulFetcher(),
                status_store=store,
                backfill_days=10,
            )
        )
        # Window [2026-09-23 .. 2026-10-03]; visible observations end Thursday.
        expected = [
            date(2026, 9, 23),
            date(2026, 9, 24),
            date(2026, 9, 25),
            date(2026, 9, 28),
            date(2026, 9, 29),
            date(2026, 9, 30),
            date(2026, 10, 1),
        ]
        assert res["saved"] == len(expected)
        saved = sorted(row.date for row in session.query(YieldCurveSnapshot).all())
        assert saved == expected
        latest = YieldCurveHistory(session).get_snapshot(date(2026, 10, 1))
        assert latest is not None
        assert latest.spread_2s10s_delta_5d is not None, "deltas need backfilled history"
        assert latest.shape_trend

    def test_backfill_never_saves_holiday_dated_snapshots(self, session, tmp_path, monkeypatch):
        """As-of semantics: a window containing the observed Independence Day
        (Fri 2026-07-03) produces no 2026-07-03 snapshot carrying 2026-07-02
        values — FRED has no observation that day, and the pipeline dates
        snapshots from the data, not from a calendar."""
        _freeze_today(monkeypatch, date(2026, 7, 6))  # Monday after July 4th
        store = PipelineStatusStore(tmp_path / "status.json")
        res = asyncio.run(
            run_yield_curve_pipeline(
                session=session,
                fetcher=LagFaithfulFetcher(holidays=frozenset({date(2026, 7, 3)})),
                status_store=store,
                backfill_days=8,
            )
        )
        saved = sorted(row.date for row in session.query(YieldCurveSnapshot).all())
        assert saved == [date(2026, 6, 29), date(2026, 6, 30), date(2026, 7, 1), date(2026, 7, 2)]
        assert date(2026, 7, 3) not in saved
        assert res["error"] is None

    def test_leading_days_without_data_do_not_shift_later_snapshots(self, session, tmp_path, monkeypatch):
        """Regression (T6): empty leading days must not shift later snapshots
        onto the wrong dates. Snapshot dates come from the observations the
        fetcher actually returns, so a series that starts mid-window simply
        produces no snapshots for the missing days."""
        frozen = date(2026, 10, 7)  # ordinary Wednesday
        _freeze_today(monkeypatch, frozen)
        window_bdays = [d.date() for d in pd.bdate_range(frozen - timedelta(days=10), frozen)]
        first_obs = window_bdays[2]  # two leading business days with no data yet
        ref = date(2026, 1, 5).toordinal()  # LagFaithfulFetcher's drift epoch

        store = PipelineStatusStore(tmp_path / "status.json")
        res = asyncio.run(
            run_yield_curve_pipeline(
                session=session,
                fetcher=LagFaithfulFetcher(first_obs=first_obs),
                status_store=store,
                backfill_days=10,
            )
        )

        # Visible observations end Tuesday (FRED's 1-business-day lag),
        # and the series only exists from first_obs onwards.
        expected_days = [d for d in window_bdays if d >= first_obs and d <= date(2026, 10, 6)]
        assert res["saved"] == len(expected_days), res
        saved_dates = sorted(row.date for row in session.query(YieldCurveSnapshot).all())
        assert saved_dates == expected_days, "snapshots must carry the date their curve belongs to"
        history = YieldCurveHistory(session)
        for d in expected_days:
            snap = history.get_snapshot(d)
            assert snap is not None
            assert snap.curve["2y"] == pytest.approx(_LEVELS["2y"] + 0.001 * (d.toordinal() - ref)), d
        assert history.get_snapshot(window_bdays[0]) is None and history.get_snapshot(window_bdays[1]) is None

    def test_ensure_populated_noop_when_data_exists(self, session, tmp_path):
        store = PipelineStatusStore(tmp_path / "status.json")
        fetcher = LagFaithfulFetcher()
        asyncio.run(
            ensure_yield_curve_populated(session=session, fetcher=fetcher, status_store=store, backfill_days=10)
        )
        assert fetcher.calls, "empty DB must trigger a backfill"
        fetcher2 = LagFaithfulFetcher()
        ran = asyncio.run(
            ensure_yield_curve_populated(session=session, fetcher=fetcher2, status_store=store, backfill_days=10)
        )
        assert ran is False
        assert fetcher2.calls == [], "populated DB must not re-fetch"
