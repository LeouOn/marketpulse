"""One-shot backfill: fetch 90 days of Treasury yields and write snapshots.

Run once after the migration is applied:
    python scripts/backfill_yield_curve.py
"""
from __future__ import annotations

import asyncio
from datetime import date, timedelta
from loguru import logger

from src.yield_curve.config import TENORS
from src.yield_curve.curves import (
    classify_shape, classify_trend, compute_spreads, nyfed_recession_prob,
)
from src.yield_curve.fetcher import FredCurveFetcher
from src.yield_curve.history import SnapshotData, YieldCurveHistory


def main(days: int = 90) -> None:
    today = date.today()
    start = today - timedelta(days=days)

    from src.core.config import get_settings
    from src.core.database import DatabaseManager
    db = DatabaseManager(get_settings().database_url)
    session = db.get_session()
    history = YieldCurveHistory(session)
    fetcher = FredCurveFetcher()

    # Fetch all 90 days in one call per tenor (cache covers it).
    fetched = fetcher.fetch_tenors(list(TENORS.keys()), start, today)
    if not fetched:
        logger.error("Backfill: no data fetched; aborting")
        return

    # Pivot: {date: {tenor: yield}}
    by_date: dict[date, dict[str, float]] = {}
    for tenor, df in fetched.items():
        for _, row in df.iterrows():
            d = row["ts"].date()
            by_date.setdefault(d, {})[tenor] = float(row["close"])

    saved = 0
    all_dates = sorted(by_date.keys())
    for i, d in enumerate(all_dates):
        curve = by_date[d]
        if len(curve) < 4:
            continue  # not enough tenors for meaningful snapshot
        spreads = compute_spreads(curve)
        shape = classify_shape(curve)
        # baseline: 5 trading days earlier in our list
        baseline_idx = max(0, i - 5)
        baseline_curve = by_date.get(all_dates[baseline_idx], curve)
        trend = classify_trend(curve, baseline_curve)
        s_3m10y = spreads.get("3m10y")
        recession_prob = nyfed_recession_prob(s_3m10y) if s_3m10y is not None else None

        snap = SnapshotData(
            date=d,
            curve=curve,
            spreads=spreads,
            shape=shape.value,
            shape_trend=trend,
            recession_prob_nyfed=recession_prob,
        )
        deltas = history.compute_deltas(d)
        snap.spread_2s10s_delta_5d = deltas["spread_2s10s_delta_5d"]
        snap.spread_2s10s_delta_30d = deltas["spread_2s10s_delta_30d"]
        snap.zscore_2s10s_90d = deltas["zscore_2s10s_90d"]
        history.save_snapshot(snap)
        saved += 1

    session.close()
    logger.info(f"Backfill complete: {saved} snapshots over {days} days")


if __name__ == "__main__":
    main()