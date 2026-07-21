"""Persistence + deltas for yield curve snapshots.

DAO over market_data.yield_curve_snapshots. Pure DB I/O — no FRED, no alerting.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from loguru import logger
from sqlalchemy.orm import Session

from src.core.database import YieldCurveSnapshot


@dataclass
class SnapshotData:
    """In-memory representation of a daily curve snapshot."""
    date: date
    curve: dict[str, float]              # tenor -> yield in %
    spreads: dict[str, Optional[float]]  # spread name -> bps
    shape: str
    shape_trend: str
    recession_prob_nyfed: Optional[float] = None
    spread_2s10s_delta_5d: Optional[float] = None
    spread_2s10s_delta_30d: Optional[float] = None
    zscore_2s10s_90d: Optional[float] = None


# Map tenor name -> DB column
_TENOR_COLS: dict[str, str] = {
    "3mo": "dgs3mo", "1y": "dgs1", "2y": "dgs2", "5y": "dgs5",
    "7y": "dgs7", "10y": "dgs10", "20y": "dgs20", "30y": "dgs30",
}


class YieldCurveHistory:
    """DAO for yield_curve_snapshots."""

    def __init__(self, session: Session):
        self.session = session

    def save_snapshot(self, snap: SnapshotData) -> None:
        """Upsert (insert or replace) a snapshot for its date."""
        existing = self.session.get(YieldCurveSnapshot, snap.date)
        if existing is None:
            row = YieldCurveSnapshot(date=snap.date)
            self.session.add(row)
        else:
            row = existing

        for tenor, col in _TENOR_COLS.items():
            setattr(row, col, snap.curve.get(tenor))

        row.spread_2s10s = snap.spreads.get("2s10s")
        row.spread_3m10y = snap.spreads.get("3m10y")
        row.spread_5s30s = snap.spreads.get("5s30s")
        row.spread_2s30s = snap.spreads.get("2s30s")
        row.shape = snap.shape
        row.shape_trend = snap.shape_trend
        row.recession_prob_nyfed = snap.recession_prob_nyfed
        row.spread_2s10s_delta_5d = snap.spread_2s10s_delta_5d
        row.spread_2s10s_delta_30d = snap.spread_2s10s_delta_30d
        row.zscore_2s10s_90d = snap.zscore_2s10s_90d

        self.session.commit()

    def get_snapshot(self, d: date) -> Optional[SnapshotData]:
        row = self.session.query(YieldCurveSnapshot).filter_by(date=d).one_or_none()
        return self._row_to_data(row) if row else None

    def get_history(self, days: int = 90) -> list[SnapshotData]:
        cutoff = date.today() - timedelta(days=days)
        rows = (
            self.session.query(YieldCurveSnapshot)
            .filter(YieldCurveSnapshot.date >= cutoff)
            .order_by(YieldCurveSnapshot.date.desc())
            .limit(days)
            .all()
        )
        return [self._row_to_data(r) for r in rows]

    def compute_deltas(self, target_date: date) -> dict[str, Optional[float]]:
        """Compute 5d/30d deltas and 90d z-score of 2s10s for `target_date`."""
        target = self.get_snapshot(target_date)
        if not target:
            return {
                "spread_2s10s_delta_5d": None,
                "spread_2s10s_delta_30d": None,
                "zscore_2s10s_90d": None,
            }

        def _spread_on(d: Optional[date]) -> Optional[float]:
            if d is None:
                return None
            row = self.get_snapshot(d)
            return row.spreads.get("2s10s") if row else None

        s_5d = _spread_on(target_date - timedelta(days=5))
        s_30d = _spread_on(target_date - timedelta(days=30))

        delta_5d = (target.spreads["2s10s"] - s_5d) if (s_5d is not None and target.spreads.get("2s10s") is not None) else None
        delta_30d = (target.spreads["2s10s"] - s_30d) if (s_30d is not None and target.spreads.get("2s10s") is not None) else None

        # 90d z-score
        history = self.get_history(days=90)
        values = [h.spreads.get("2s10s") for h in history if h.spreads.get("2s10s") is not None]
        if len(values) >= 5:
            mean = sum(values) / len(values)
            var = sum((v - mean) ** 2 for v in values) / len(values)
            std = var ** 0.5
            z = (target.spreads["2s10s"] - mean) / std if std > 0 else 0.0
        else:
            z = None

        return {
            "spread_2s10s_delta_5d": round(delta_5d, 4) if delta_5d is not None else None,
            "spread_2s10s_delta_30d": round(delta_30d, 4) if delta_30d is not None else None,
            "zscore_2s10s_90d": round(z, 4) if z is not None else None,
        }

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _row_to_data(row: YieldCurveSnapshot) -> SnapshotData:
        curve = {tenor: float(getattr(row, col))
                 for tenor, col in _TENOR_COLS.items()
                 if getattr(row, col) is not None}
        spreads = {
            "2s10s": float(row.spread_2s10s) if row.spread_2s10s is not None else None,
            "3m10y": float(row.spread_3m10y) if row.spread_3m10y is not None else None,
            "5s30s": float(row.spread_5s30s) if row.spread_5s30s is not None else None,
            "2s30s": float(row.spread_2s30s) if row.spread_2s30s is not None else None,
        }
        return SnapshotData(
            date=row.date,
            curve=curve,
            spreads=spreads,
            shape=row.shape,
            shape_trend=row.shape_trend,
            recession_prob_nyfed=float(row.recession_prob_nyfed)
                if row.recession_prob_nyfed is not None else None,
            spread_2s10s_delta_5d=float(row.spread_2s10s_delta_5d)
                if row.spread_2s10s_delta_5d is not None else None,
            spread_2s10s_delta_30d=float(row.spread_2s10s_delta_30d)
                if row.spread_2s10s_delta_30d is not None else None,
            zscore_2s10s_90d=float(row.zscore_2s10s_90d)
                if row.zscore_2s10s_90d is not None else None,
        )
