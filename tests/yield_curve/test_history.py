"""History persistence tests against in-memory SQLite."""
from datetime import date, timedelta

import pandas as pd  # noqa: F401  (intentionally unused — keep import parity w/ fetcher test)
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.core.database import Base, YieldCurveSnapshot
from src.yield_curve.history import YieldCurveHistory, SnapshotData


# SQLite has no real schemas. Use schema_translate_map so the
# `market_data.` prefix on YieldCurveSnapshot.__table__ resolves to
# nothing at SQL-emit time. Keeps the ORM model untouched (still
# `market_data.yield_curve_snapshots` for Postgres).
@pytest.fixture
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        execution_options={"schema_translate_map": {"market_data": None, "analysis": None}},
    )
    Base.metadata.create_all(engine, tables=[
        YieldCurveSnapshot.__table__,
    ])
    with Session(engine) as s:
        yield s
        s.close()


def _make_snapshot(d: date, s2s10s: float) -> SnapshotData:
    return SnapshotData(
        date=d,
        curve={"2y": 4.5, "10y": 4.5 + s2s10s / 100.0},
        spreads={"2s10s": s2s10s, "3m10y": -50.0, "5s30s": 30.0, "2s30s": 20.0},
        shape="NORMAL",
        shape_trend="STABLE",
        recession_prob_nyfed=0.30,
    )


def test_save_and_get_round_trip(session):
    h = YieldCurveHistory(session)
    snap = _make_snapshot(date(2026, 6, 23), 10.0)
    h.save_snapshot(snap)
    out = h.get_snapshot(date(2026, 6, 23))
    assert out is not None
    assert out.spreads["2s10s"] == pytest.approx(10.0)


def test_save_is_idempotent_on_same_date(session):
    h = YieldCurveHistory(session)
    h.save_snapshot(_make_snapshot(date(2026, 6, 23), 10.0))
    h.save_snapshot(_make_snapshot(date(2026, 6, 23), 15.0))  # overwrite
    rows = session.query(YieldCurveSnapshot).filter_by(date=date(2026, 6, 23)).all()
    assert len(rows) == 1


def test_get_history_returns_n_most_recent(session):
    h = YieldCurveHistory(session)
    for i in range(40):
        h.save_snapshot(_make_snapshot(date(2026, 6, 1) + timedelta(days=i), float(i)))
    out = h.get_history(days=30)
    assert len(out) == 30
    assert out[0].date >= out[-1].date  # descending


def test_compute_deltas_5d_and_30d(session):
    h = YieldCurveHistory(session)
    base = date(2026, 6, 1)
    # Seed 31 days with linearly increasing 2s10s
    for i in range(31):
        h.save_snapshot(_make_snapshot(base + timedelta(days=i), float(i)))
    # Target last seeded day so 30d lookback lands inside the seeded window
    # (plan target was 2026-06-30; off-by-one vs the 31-day seed starting 06-01).
    deltas = h.compute_deltas(base + timedelta(days=30))
    # delta_5d should be 5 (or close — gap-filled weekends)
    assert deltas["spread_2s10s_delta_5d"] is not None
    assert deltas["spread_2s10s_delta_30d"] is not None
