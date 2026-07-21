"""Daily yield-curve pipeline: fetch -> compute -> persist -> evaluate alerts.

Registered into MarketScheduler via _register_jobs() in Task 8.
"""
from __future__ import annotations

from datetime import date
from loguru import logger

from src.yield_curve.config import TENORS, get_config
from src.yield_curve.curves import (
    classify_shape,
    classify_trend,
    compute_spreads,
    nyfed_recession_prob,
)
from src.yield_curve.fetcher import FredCurveFetcher
from src.yield_curve.history import SnapshotData, YieldCurveHistory


async def run_yield_curve_pipeline() -> None:
    """One-shot daily pipeline. Safe to call from APScheduler."""
    cfg = get_config()
    today = date.today()

    try:
        from src.core.database import DatabaseManager
        from src.core.config import get_settings
        db = DatabaseManager(get_settings().database_url)
        session = db.get_session()
    except Exception as exc:
        logger.error(f"yield_curve: cannot get DB session: {exc}")
        return

    history = YieldCurveHistory(session)

    # Skip if today's snapshot already exists (unless force-refresh).
    if not cfg.force_refresh and history.get_snapshot(today) is not None:
        logger.info(f"yield_curve: snapshot for {today} already exists; skipping")
        session.close()
        return

    # 1. Fetch all 8 tenors for today.
    fetcher = FredCurveFetcher(cache_dir=cfg.cache_dir)
    fetched = fetcher.fetch_tenors(list(TENORS.keys()), today, today)
    if not fetched:
        logger.warning(f"yield_curve: no tenors fetched for {today}; aborting")
        session.close()
        return

    # 2. Build today's curve dict (use latest value for each tenor).
    curve: dict[str, float] = {}
    for tenor, df in fetched.items():
        if not df.empty:
            curve[tenor] = float(df.iloc[-1]["close"])

    spreads = compute_spreads(curve)
    shape = classify_shape(curve)

    # 3. Trend vs 5-day baseline.
    history_rows = history.get_history(days=30)
    baseline_curve = history_rows[0].curve if history_rows else curve
    trend = classify_trend(curve, baseline_curve)

    # 4. Recession prob from 3m10y.
    s_3m10y = spreads.get("3m10y")
    recession_prob = nyfed_recession_prob(s_3m10y) if s_3m10y is not None else None

    snap = SnapshotData(
        date=today,
        curve=curve,
        spreads=spreads,
        shape=shape.value,
        shape_trend=trend,
        recession_prob_nyfed=recession_prob,
    )

    # 5. Compute deltas + z-score from history.
    deltas = history.compute_deltas(today)
    snap.spread_2s10s_delta_5d = deltas["spread_2s10s_delta_5d"]
    snap.spread_2s10s_delta_30d = deltas["spread_2s10s_delta_30d"]
    snap.zscore_2s10s_90d = deltas["zscore_2s10s_90d"]

    # 6. Persist.
    history.save_snapshot(snap)
    logger.info(f"yield_curve: saved snapshot for {today} (shape={shape.value}, 2s10s={spreads.get('2s10s')})")

    # 7. Evaluate alerts (Task 9 provides YieldCurveAlerts).
    try:
        from src.yield_curve.alerts import YieldCurveAlerts
        alerts = YieldCurveAlerts(session, cfg)
        await alerts.evaluate(snap, history_rows)
    except Exception as exc:
        logger.error(f"yield_curve: alert evaluation failed: {exc}")

    session.close()
