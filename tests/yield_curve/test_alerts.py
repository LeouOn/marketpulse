"""Alert rule engine tests."""
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.yield_curve.alerts import AlertEvent, YieldCurveAlerts
from src.yield_curve.config import YieldCurveConfig
from src.yield_curve.curves import CurveShape
from src.yield_curve.history import SnapshotData


def _snap(d: date, s2s10s: float, shape: str = "NORMAL", recession_prob: float = 0.10) -> SnapshotData:
    return SnapshotData(
        date=d,
        curve={"2y": 4.5, "10y": 4.5 + s2s10s / 100.0},
        spreads={"2s10s": s2s10s, "3m10y": -50.0, "5s30s": 30.0, "2s30s": 20.0},
        shape=shape,
        shape_trend="STABLE",
        recession_prob_nyfed=recession_prob,
        spread_2s10s_delta_5d=0.0,
    )


@pytest.mark.asyncio
async def test_inversion_start_fires_critical():
    cfg = YieldCurveConfig()
    session = MagicMock()
    alerts = YieldCurveAlerts(session, cfg)
    today = _snap(date(2026, 6, 23), s2s10s=-5.0)
    prior = _snap(date(2026, 6, 22), s2s10s=+5.0)
    fired = await alerts._evaluate_rules(today, prior)
    names = [e.rule_name for e in fired]
    assert "inversion_2s10s_start" in names
    crit = [e for e in fired if e.rule_name == "inversion_2s10s_start"][0]
    assert crit.priority == "CRITICAL"


@pytest.mark.asyncio
async def test_inversion_end_fires_high():
    cfg = YieldCurveConfig()
    alerts = YieldCurveAlerts(MagicMock(), cfg)
    today = _snap(date(2026, 6, 23), s2s10s=+5.0)
    prior = _snap(date(2026, 6, 22), s2s10s=-5.0)
    fired = await alerts._evaluate_rules(today, prior)
    assert any(e.rule_name == "inversion_2s10s_end" and e.priority == "HIGH" for e in fired)


@pytest.mark.asyncio
async def test_shape_transition_unfavorable_is_high():
    cfg = YieldCurveConfig()
    alerts = YieldCurveAlerts(MagicMock(), cfg)
    today = _snap(date(2026, 6, 23), s2s10s=-5.0, shape="INVERTED")
    prior = _snap(date(2026, 6, 22), s2s10s=+5.0, shape="NORMAL")
    fired = await alerts._evaluate_rules(today, prior)
    shape_alert = [e for e in fired if e.rule_name == "shape_transition"][0]
    assert shape_alert.priority == "HIGH"


@pytest.mark.asyncio
async def test_shape_transition_favorable_is_medium():
    cfg = YieldCurveConfig()
    alerts = YieldCurveAlerts(MagicMock(), cfg)
    today = _snap(date(2026, 6, 23), s2s10s=+5.0, shape="NORMAL")
    prior = _snap(date(2026, 6, 22), s2s10s=-5.0, shape="INVERTED")
    fired = await alerts._evaluate_rules(today, prior)
    shape_alert = [e for e in fired if e.rule_name == "shape_transition"][0]
    assert shape_alert.priority == "MEDIUM"


@pytest.mark.asyncio
async def test_rapid_steepening_threshold():
    cfg = YieldCurveConfig(steepen_bps_5d=20)
    alerts = YieldCurveAlerts(MagicMock(), cfg)
    today = _snap(date(2026, 6, 23), s2s10s=+30.0)
    today.spread_2s10s_delta_5d = 25.0  # > 20 threshold
    prior = _snap(date(2026, 6, 22), s2s10s=+5.0)
    fired = await alerts._evaluate_rules(today, prior)
    assert any(e.rule_name == "rapid_steepening" and e.priority == "HIGH" for e in fired)


@pytest.mark.asyncio
async def test_rapid_flattening_threshold():
    cfg = YieldCurveConfig(flatten_bps_5d=-20)
    alerts = YieldCurveAlerts(MagicMock(), cfg)
    today = _snap(date(2026, 6, 23), s2s10s=+5.0)
    today.spread_2s10s_delta_5d = -25.0  # < -20 threshold
    prior = _snap(date(2026, 6, 22), s2s10s=+30.0)
    fired = await alerts._evaluate_rules(today, prior)
    assert any(e.rule_name == "rapid_flattening" and e.priority == "HIGH" for e in fired)


@pytest.mark.asyncio
async def test_recession_prob_critical_crossing():
    cfg = YieldCurveConfig(recession_prob_high=0.50)
    alerts = YieldCurveAlerts(MagicMock(), cfg)
    today = _snap(date(2026, 6, 23), s2s10s=-30.0, recession_prob=0.55)
    prior = _snap(date(2026, 6, 22), s2s10s=-25.0, recession_prob=0.45)
    fired = await alerts._evaluate_rules(today, prior)
    assert any(e.rule_name == "recession_prob_critical" and e.priority == "CRITICAL" for e in fired)


@pytest.mark.asyncio
async def test_recession_prob_warning_crossing():
    cfg = YieldCurveConfig(recession_prob_low=0.25)
    alerts = YieldCurveAlerts(MagicMock(), cfg)
    today = _snap(date(2026, 6, 23), s2s10s=-15.0, recession_prob=0.30)
    prior = _snap(date(2026, 6, 22), s2s10s=-10.0, recession_prob=0.20)
    fired = await alerts._evaluate_rules(today, prior)
    assert any(e.rule_name == "recession_prob_warning" and e.priority == "HIGH" for e in fired)


@pytest.mark.asyncio
async def test_antispam_suppresses_recent_same_rule(monkeypatch):
    """If a rule fired within antispam_hours, suppress."""
    cfg = YieldCurveConfig(antispam_hours=6)
    session = MagicMock()
    alerts = YieldCurveAlerts(session, cfg)

    # Pretend inversion_2s10s_start fired 1 hour ago.
    from datetime import datetime, timedelta, timezone
    recent = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
    alerts._last_fired = lambda rule_name: recent if rule_name == "inversion_2s10s_start" else None

    today = _snap(date(2026, 6, 23), s2s10s=-5.0)
    prior = _snap(date(2026, 6, 22), s2s10s=+5.0)
    fired = await alerts._evaluate_rules(today, prior)
    # Inversion start should be suppressed.
    assert "inversion_2s10s_start" not in [e.rule_name for e in fired]
