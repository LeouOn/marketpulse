"""Daily yield-curve pipeline: fetch -> compute -> persist -> evaluate alerts.

Registered into MarketScheduler via _register_jobs() (16:30 ET, after
FRED publishes) and started by the app lifespan (T6). The lifespan also
calls :func:`ensure_yield_curve_populated` once at startup so a fresh
deployment backfills instead of serving ``data: null``.

Manual trigger::

    python -m src.scheduler.yield_curve_job             # today only
    python -m src.scheduler.yield_curve_job --backfill 130

or ``POST /api/yield-curve/refresh``.

Every run is recorded in the pipeline status file (see
:mod:`src.yield_curve.status`) so the API can explain empty responses.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

import pandas as pd
from loguru import logger

from src.yield_curve.config import TENORS, get_config
from src.yield_curve.curves import (
    classify_shape,
    classify_trend,
    compute_spreads,
    nyfed_recession_prob,
)
from src.yield_curve.history import SnapshotData, YieldCurveHistory
from src.yield_curve.status import PipelineStatusStore, default_status_path


def _own_session():
    """Open a DB session (caller owns + closes it)."""
    from src.core.config import get_settings
    from src.core.database import DatabaseManager

    db = DatabaseManager(get_settings().database_url)
    return db.get_session()


def _business_days(start: date, end: date) -> list[date]:
    return [d.date() for d in pd.bdate_range(start, end)]


def _asof_value(df: pd.DataFrame, d: date) -> float | None:
    """Value at-or-before ``d`` (FRED series have gaps on holidays)."""
    ts = pd.to_datetime(df["ts"])
    mask = ts.dt.date <= d
    if not mask.any():
        return None
    return float(df.loc[mask, "close"].iloc[-1])


def _delta_fields(
    dates: list[date], spread_by_date: dict[date, float | None], i: int
) -> dict[str, float | None]:
    """2s10s deltas + 90d z-score for ``dates[i]`` from the in-window series."""
    d = dates[i]
    s_now = spread_by_date.get(d)

    def _delta(steps_back: int) -> float | None:
        j = i - steps_back
        if s_now is None or j < 0:
            return None
        s_prev = spread_by_date.get(dates[j])
        return None if s_prev is None else s_now - s_prev

    window = [
        spread_by_date.get(dates[j])
        for j in range(max(0, i - 90), i + 1)
        if spread_by_date.get(dates[j]) is not None
    ]
    zscore = None
    if s_now is not None and len(window) >= 30:
        s = pd.Series(window[:-1] or window)
        std = s.std()
        if std and std > 0:
            zscore = float((s_now - s.mean()) / std)

    return {
        "spread_2s10s_delta_5d": _delta(5),
        "spread_2s10s_delta_30d": _delta(30),
        "zscore_2s10s_90d": zscore,
    }


async def run_yield_curve_pipeline(
    session=None,
    fetcher=None,
    status_store: PipelineStatusStore | None = None,
    backfill_days: int = 0,
    force: bool = False,
) -> dict:
    """One-shot pipeline. Safe to call from APScheduler.

    Args:
        session: injected DB session (tests). A fresh one is opened when
            omitted, and only then closed here.
        fetcher: injected tenor fetcher (tests). Defaults to the real
            :class:`FredCurveFetcher`.
        status_store: injected status store (tests).
        backfill_days: when > 0, build snapshots for every business day in
            ``[today - backfill_days, today]`` (deltas/z-scores need the
            history). Default 0 = today only.
        force: recompute today's snapshot even if it exists.

    Returns a summary dict ``{"saved": n, "date": ..., "error": ...}`` so
    the manual-trigger endpoint can report what happened.
    """
    cfg = get_config()
    store = status_store or PipelineStatusStore(default_status_path())
    own_session = session is None
    if session is None:
        try:
            session = _own_session()
        except Exception as exc:
            logger.error(f"yield_curve: cannot get DB session: {exc}")
            store.record_run(ok=False, error=f"DB unavailable: {exc}")
            return {"saved": 0, "error": str(exc)}
    if fetcher is None:
        from src.yield_curve.fetcher import FredCurveFetcher

        fetcher = FredCurveFetcher(cache_dir=cfg.cache_dir)

    today = date.today()
    force = force or cfg.force_refresh
    history = YieldCurveHistory(session)

    try:
        if backfill_days <= 0 and not force and history.get_snapshot(today) is not None:
            logger.info(f"yield_curve: snapshot for {today} already exists; skipping")
            store.record_run(ok=True, saved=0, snapshot_date=today)
            return {"saved": 0, "date": today.isoformat(), "error": None}

        window_start = today - timedelta(days=backfill_days) if backfill_days > 0 else today
        dates = _business_days(window_start, today)
        if not dates:
            dates = [today]

        # 1. One range fetch per tenor (8 requests regardless of window).
        fetched = fetcher.fetch_tenors(list(TENORS.keys()), window_start, today)
        fetched = {t: df for t, df in (fetched or {}).items() if df is not None and not df.empty}
        if not fetched:
            msg = f"no tenor data fetched for [{window_start} .. {today}]"
            logger.warning(f"yield_curve: {msg}")
            store.record_run(ok=False, error=msg)
            return {"saved": 0, "error": msg}

        # 2. Per-day curve / spreads / shape over the window.
        curves: list[dict[str, float]] = []
        for d in dates:
            curve = {
                tenor: v
                for tenor, df in fetched.items()
                if (v := _asof_value(df, d)) is not None
            }
            if curve:
                curves.append(curve)

        spread_by_date = {
            d: compute_spreads(c).get("2s10s") for d, c in zip(dates, curves)
        }

        saved = 0
        latest_snap: SnapshotData | None = None
        for i, (d, curve) in enumerate(zip(dates, curves)):
            spreads = compute_spreads(curve)
            baseline = curves[i - 5] if i >= 5 else curve
            snap = SnapshotData(
                date=d,
                curve=curve,
                spreads=spreads,
                shape=classify_shape(curve).value,
                shape_trend=classify_trend(curve, baseline),
                recession_prob_nyfed=(
                    nyfed_recession_prob(spreads["3m10y"])
                    if spreads.get("3m10y") is not None
                    else None
                ),
            )
            snap.spread_2s10s_delta_5d, snap.spread_2s10s_delta_30d, snap.zscore_2s10s_90d = (
                _delta_fields(dates, spread_by_date, i).values()
            )
            history.save_snapshot(snap)
            saved += 1
            latest_snap = snap

        logger.info(
            f"yield_curve: saved {saved} snapshot(s) through {today} "
            f"(shape={latest_snap.shape if latest_snap else '?'}, "
            f"2s10s={spread_by_date.get(today)})"
        )
        store.record_run(ok=True, saved=saved, snapshot_date=today)

        # 3. Evaluate alerts on the latest snapshot.
        if latest_snap is not None:
            try:
                from src.yield_curve.alerts import YieldCurveAlerts

                await YieldCurveAlerts(session, cfg).evaluate(
                    latest_snap, history.get_history(days=90)
                )
            except Exception as exc:
                logger.error(f"yield_curve: alert evaluation failed: {exc}")

        return {"saved": saved, "date": today.isoformat(), "error": None}
    except Exception as exc:
        logger.error(f"yield_curve: pipeline failed: {exc}")
        store.record_run(ok=False, error=str(exc))
        return {"saved": 0, "error": str(exc)}
    finally:
        if own_session:
            session.close()


async def ensure_yield_curve_populated(
    session=None,
    fetcher=None,
    status_store: PipelineStatusStore | None = None,
    backfill_days: int = 130,
) -> bool:
    """Backfill once if (and only if) the snapshot table is empty.

    Called from the app lifespan (non-blocking) so a fresh deployment
    serves real history immediately; subsequent refreshes are the
    scheduler's job (daily, 16:30 ET). Returns True if a backfill ran.
    """
    own_session = session is None
    if session is None:
        try:
            session = _own_session()
        except Exception as exc:
            logger.error(f"yield_curve: cannot get DB session: {exc}")
            return False
    try:
        from src.core.database import YieldCurveSnapshot

        has_rows = session.query(YieldCurveSnapshot).first() is not None
        if has_rows:
            logger.info("yield_curve: snapshots already present; skipping startup backfill")
            return False
    finally:
        if own_session:
            session.close()

    logger.info(f"yield_curve: empty table; backfilling ~{backfill_days} days")
    result = await run_yield_curve_pipeline(
        session=session,
        fetcher=fetcher,
        status_store=status_store,
        backfill_days=backfill_days,
    )
    return result.get("saved", 0) > 0


if __name__ == "__main__":  # manual trigger: python -m src.scheduler.yield_curve_job
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Run the yield-curve pipeline once")
    parser.add_argument(
        "--backfill",
        type=int,
        default=0,
        help="backfill N calendar days of business-day snapshots (default: today only)",
    )
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run_yield_curve_pipeline(backfill_days=args.backfill)), indent=2))
