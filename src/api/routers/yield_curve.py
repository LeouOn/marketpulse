"""Yield curve REST endpoints."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

from fastapi import APIRouter
from loguru import logger
from pydantic import BaseModel

from src.yield_curve.config import get_config

router = APIRouter(prefix="/api/yield-curve", tags=["yield-curve"])


# --- response envelopes ----------------------------------------------------

class _Envelope(BaseModel):
    success: bool
    data: Optional[Any] = None
    timestamp: Optional[str] = None


# --- session / DAO helpers -------------------------------------------------

def _get_history():
    """Build a YieldCurveHistory bound to a fresh session. Caller closes."""
    from src.core.config import get_settings
    from src.core.database import DatabaseManager
    from src.yield_curve.history import YieldCurveHistory
    db = DatabaseManager(get_settings().database_url)
    session = db.get_session()
    return YieldCurveHistory(session), session


def _get_alerts():
    from src.core.config import get_settings
    from src.core.database import DatabaseManager
    db = DatabaseManager(get_settings().database_url)
    return db.get_session()


def _compute_staleness(latest_date: Optional[date]) -> tuple[bool, int]:
    """Return (stale, days_since_update)."""
    if latest_date is None:
        return True, -1
    days = (date.today() - latest_date).days
    cfg = get_config()
    return days > cfg.stale_days, days


# --- endpoints -------------------------------------------------------------

@router.get("/current", response_model=_Envelope)
async def get_current():
    try:
        history, session = _get_history()
        try:
            rows = history.get_history(days=1)
            if not rows:
                return _Envelope(success=True, data=None)
            snap = rows[0]
            stale, days_since = _compute_staleness(snap.date)
            return _Envelope(success=True, data={
                "date": snap.date.isoformat(),
                "curve": snap.curve,
                "spreads": snap.spreads,
                "shape": snap.shape,
                "shape_trend": snap.shape_trend,
                "recession_prob_nyfed": snap.recession_prob_nyfed,
                "deltas": {
                    "spread_2s10s_delta_5d": snap.spread_2s10s_delta_5d,
                    "spread_2s10s_delta_30d": snap.spread_2s10s_delta_30d,
                },
                "zscore_2s10s_90d": snap.zscore_2s10s_90d,
                "stale": stale,
                "days_since_update": days_since,
            })
        finally:
            session.close()
    except Exception as exc:
        logger.error(f"yield-curve /current failed: {exc}")
        return _Envelope(success=False, data=None)


@router.get("/history", response_model=_Envelope)
async def get_history(days: int = 90):
    try:
        history, session = _get_history()
        try:
            rows = history.get_history(days=days)
            return _Envelope(success=True, data={
                "snapshots": [{
                    "date": r.date.isoformat(),
                    "spread_2s10s": r.spreads.get("2s10s"),
                    "shape": r.shape,
                    "shape_trend": r.shape_trend,
                    "recession_prob_nyfed": r.recession_prob_nyfed,
                    "deltas": {
                        "spread_2s10s_delta_5d": r.spread_2s10s_delta_5d,
                        "spread_2s10s_delta_30d": r.spread_2s10s_delta_30d,
                    },
                } for r in rows]
            })
        finally:
            session.close()
    except Exception as exc:
        logger.error(f"yield-curve /history failed: {exc}")
        return _Envelope(success=False, data=None)


@router.get("/alerts", response_model=_Envelope)
async def get_alerts(days: int = 30):
    try:
        session = _get_alerts()
        try:
            from src.core.database import YieldCurveAlert
            cutoff = date.today() - timedelta(days=days)
            rows = (
                session.query(YieldCurveAlert)
                .filter(YieldCurveAlert.triggered_at >= cutoff)
                .order_by(YieldCurveAlert.triggered_at.desc())
                .limit(100)
                .all()
            )
            return _Envelope(success=True, data={
                "alerts": [{
                    "triggered_at": r.triggered_at.isoformat() if r.triggered_at else None,
                    "rule_name": r.rule_name,
                    "priority": r.priority,
                    "message": r.message,
                    "trigger_value": float(r.trigger_value) if r.trigger_value is not None else None,
                    "prior_value": float(r.prior_value) if r.prior_value is not None else None,
                    "delta": float(r.delta) if r.delta is not None else None,
                    "zscore": float(r.zscore) if r.zscore is not None else None,
                } for r in rows]
            })
        finally:
            session.close()
    except Exception as exc:
        logger.error(f"yield-curve /alerts failed: {exc}")
        return _Envelope(success=False, data=None)


@router.get("/config", response_model=_Envelope)
async def get_config_endpoint():
    cfg = get_config()
    return _Envelope(success=True, data={
        "thresholds": {
            "steepen_bps_5d": cfg.steepen_bps_5d,
            "flatten_bps_5d": cfg.flatten_bps_5d,
            "recession_prob_high": cfg.recession_prob_high,
            "recession_prob_low": cfg.recession_prob_low,
            "antispam_hours": cfg.antispam_hours,
            "stale_days": cfg.stale_days,
        }
    })