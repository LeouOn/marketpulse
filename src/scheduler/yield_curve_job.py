"""Daily yield-curve pipeline: fetch -> compute -> persist -> evaluate alerts.

Registered into MarketScheduler via _register_jobs() (16:30 ET) and
started by the app lifespan (T6). The lifespan also calls
:func:`ensure_yield_curve_populated` once at startup so a fresh deployment
backfills instead of serving ``data: null``.

**Observation-driven policy (why snapshot dates come from the data).**
FRED publishes the daily treasury (DGS*) series with a **one-business-day
lag**: Tuesday's value first becomes visible on Wednesday, and over a
weekend the newest visible observation is Thursday's (a three-calendar-
day lag). A same-day fetch window is therefore always empty — the daily
16:30 run used to ask for ``[today .. today]`` and record a failure on
every single day. Instead, every run fetches a trailing window
(``_OBSERVATION_LOOKBACK_DAYS`` calendar days; the fetcher's parquet
cache makes repeat windows cheap) and dates its snapshots by the
**observation dates actually present in the fetched data**:

- a daily run snapshots the latest observation date with a full-curve
  day (see ``_observation_dates``), skipping idempotently when that
  snapshot already exists — so weekend, holiday and 16:30-weekday runs
  are all successful no-ops or one-day catch-ups;
- a backfill snapshots every observation date in its window, which also
  means no snapshot is ever saved under a date FRED published nothing
  (weekends, federal holidays *and* bond-market closures like Good
  Friday — no calendar needs to be modelled);
- ``ok=False`` is recorded only when the window contains no usable
  observation at all (genuinely broken fetch / no data for ~10 days).

Manual trigger::

    python -m src.scheduler.yield_curve_job             # latest observation
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


#: Trailing calendar days a daily run fetches. FRED publishes the daily
#: treasury (DGS*) series one business day late (Tuesday's value first
#: appears Wednesday; over a weekend the lag is three calendar days), so a
#: same-day window is always empty and the run must look back far enough
#: to contain the latest *available* observation. Ten calendar days covers
#: any weekend-plus-holiday stretch with margin.
_OBSERVATION_LOOKBACK_DAYS = 10


def _observation_dates(fetched: dict[str, pd.DataFrame]) -> list[date]:
    """Sorted dates on which EVERY tenor has an exact observation.

    Usability rule for a snapshot date: the full ``TENORS`` curve must be
    present — spreads (2s10s/3m10y/2s30s), shape classification and the
    NY Fed recession model each read several tenors, so a partial curve
    would produce misleading derived fields. FRED's DGS family publishes
    as a block, so the intersection costs nothing in practice; a single
    tenor hiccup drops only that one day and never misdates anything.
    """
    if not fetched:
        return []
    date_sets = [set(pd.to_datetime(df["ts"]).dt.date) for df in fetched.values()]
    return sorted(set.intersection(*date_sets))


def _exact_value(df: pd.DataFrame, d: date) -> float | None:
    """Exact observation for ``d`` (no as-of carry-forward)."""
    ts = pd.to_datetime(df["ts"])
    rows = df.loc[ts.dt.date == d, "close"]
    return float(rows.iloc[-1]) if len(rows) else None


def _exact_value(df: pd.DataFrame, d: date) -> float | None:
    """Exact observation for ``d`` (no as-of carry-forward)."""
    ts = pd.to_datetime(df["ts"])
    rows = df.loc[ts.dt.date == d, "close"]
    return float(rows.iloc[-1]) if len(rows) else None


def _delta_fields(dates: list[date], spread_by_date: dict[date, float | None], i: int) -> dict[str, float | None]:
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
        spread_by_date.get(dates[j]) for j in range(max(0, i - 90), i + 1) if spread_by_date.get(dates[j]) is not None
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
            history from ``today - backfill_days``; snapshot dates are the
            observation dates found in the data (deltas/z-scores need the
            history). Default 0 = the latest available observation only.
        force: recompute existing snapshots for those observation dates.

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
    # Observation-driven policy (see module docstring): FRED publishes the
    # daily treasury series one business day late, so the run fetches a
    # trailing window and dates snapshots by the observation dates actually
    # present in the data — never by the wall clock and never by a calendar
    # (bond-market closures like Good Friday are handled for free).
    force = force or cfg.force_refresh
    history = YieldCurveHistory(session)

    try:
        span = backfill_days if backfill_days > 0 else _OBSERVATION_LOOKBACK_DAYS
        window_start = today - timedelta(days=span)

        # 1. One range fetch per tenor (8 requests regardless of window).
        fetched = fetcher.fetch_tenors(list(TENORS.keys()), window_start, today)
        fetched = {t: df for t, df in (fetched or {}).items() if df is not None and not df.empty}

        # 2. Snapshot dates are the observation dates present in the data.
        obs_dates = _observation_dates(fetched)
        if not obs_dates:
            msg = f"no tenor observations with full coverage in [{window_start} .. {today}]"
            logger.warning(f"yield_curve: {msg}")
            store.record_run(ok=False, error=msg)
            return {"saved": 0, "error": msg}

        latest_obs = obs_dates[-1]
        # Daily run: snapshot only the latest observation. Backfill: every
        # observation date in the window. Existing snapshots are skipped
        # (idempotent success) unless force is set.
        dates = obs_dates if backfill_days > 0 else [latest_obs]
        if not force:
            missing = [d for d in dates if history.get_snapshot(d) is None]
        else:
            missing = dates
        if not missing:
            logger.info(f"yield_curve: snapshots through {latest_obs} already exist; skipping")
            store.record_run(ok=True, saved=0, snapshot_date=latest_obs)
            return {"saved": 0, "date": latest_obs.isoformat(), "error": None}
        dates = missing

        dated_curves: list[tuple[date, dict[str, float]]] = [
            (d, {tenor: v for tenor, df in fetched.items() if (v := _exact_value(df, d)) is not None}) for d in dates
        ]
        dates = [d for d, _ in dated_curves]
        curves = [c for _, c in dated_curves]

        spread_by_date = {d: compute_spreads(c).get("2s10s") for d, c in zip(dates, curves, strict=True)}

        saved = 0
        latest_snap: SnapshotData | None = None
        for i, (d, curve) in enumerate(zip(dates, curves, strict=True)):
            spreads = compute_spreads(curve)
            baseline = curves[i - 5] if i >= 5 else curve
            snap = SnapshotData(
                date=d,
                curve=curve,
                spreads=spreads,
                shape=classify_shape(curve).value,
                shape_trend=classify_trend(curve, baseline),
                recession_prob_nyfed=(
                    nyfed_recession_prob(spreads["3m10y"]) if spreads.get("3m10y") is not None else None
                ),
            )
            snap.spread_2s10s_delta_5d, snap.spread_2s10s_delta_30d, snap.zscore_2s10s_90d = _delta_fields(
                dates, spread_by_date, i
            ).values()
            history.save_snapshot(snap)
            saved += 1
            latest_snap = snap

        logger.info(
            f"yield_curve: saved {saved} snapshot(s) through {latest_snap.date if latest_snap else latest_obs} "
            f"(shape={latest_snap.shape if latest_snap else '?'}, "
            f"2s10s={spread_by_date.get(latest_obs)})"
        )
        store.record_run(ok=True, saved=saved, snapshot_date=latest_snap.date if latest_snap else latest_obs)

        # 3. Evaluate alerts on the latest snapshot.
        if latest_snap is not None:
            try:
                from src.yield_curve.alerts import YieldCurveAlerts

                await YieldCurveAlerts(session, cfg).evaluate(latest_snap, history.get_history(days=90))
            except Exception as exc:
                logger.error(f"yield_curve: alert evaluation failed: {exc}")

        return {"saved": saved, "date": (latest_snap.date if latest_snap else latest_obs).isoformat(), "error": None}
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
        help="snapshot the latest FRED observation (backfill N days of observation-dated snapshots)",
    )
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run_yield_curve_pipeline(backfill_days=args.backfill)), indent=2))
