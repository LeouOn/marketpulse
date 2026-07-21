"""Warsh-framework alert rule engine.

7 rules: 2 inversion events, 1 shape-transition, 2 spread-delta, 2 recession-prob.
Dispatches via existing AlertManager. Persists audit log to yield_curve_alerts.
Anti-spam: same rule_name suppressed within antispam_hours.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from loguru import logger
from sqlalchemy.orm import Session

from src.yield_curve.config import YieldCurveConfig
from src.yield_curve.history import SnapshotData


# Unfavorable shape transitions (curve flattening/inverting) — HIGH priority.
_UNFAVORABLE_SHAPES = {"FLAT", "INVERTED", "INVERTED_HUMPED"}
_FAVORABLE_SHAPES = {"NORMAL", "HUMPED"}


@dataclass
class AlertEvent:
    rule_name: str
    priority: str
    message: str
    trigger_value: Optional[float]
    prior_value: Optional[float]
    delta: Optional[float]
    zscore: Optional[float]


class YieldCurveAlerts:
    """Rule engine over (today, prior) snapshots."""

    def __init__(self, session: Session, cfg: YieldCurveConfig):
        self.session = session
        self.cfg = cfg

    async def evaluate(
        self,
        today: SnapshotData,
        history: list[SnapshotData],
    ) -> list[AlertEvent]:
        """Evaluate all rules. Returns list of fired (non-suppressed) AlertEvents."""
        prior = history[0] if history else None
        if prior is None:
            logger.info("yield_curve alerts: no prior snapshot; skipping evaluation")
            return []

        events = await self._evaluate_rules(today, prior)

        # Persist + dispatch each event.
        for ev in events:
            await self._persist_and_dispatch(ev, today)

        return events

    async def _evaluate_rules(
        self,
        today: SnapshotData,
        prior: SnapshotData,
    ) -> list[AlertEvent]:
        fired: list[AlertEvent] = []
        s_now = today.spreads.get("2s10s")
        s_prev = prior.spreads.get("2s10s")

        # 1. inversion_2s10s_start
        if s_prev is not None and s_now is not None and s_prev >= 0 and s_now < 0:
            self._maybe_append(fired, "inversion_2s10s_start", "CRITICAL",
                today, prior, s_now, s_prev)

        # 2. inversion_2s10s_end
        if s_prev is not None and s_now is not None and s_prev < 0 and s_now >= 0:
            self._maybe_append(fired, "inversion_2s10s_end", "HIGH",
                today, prior, s_now, s_prev)

        # 3. shape_transition (priority by direction)
        if today.shape != prior.shape:
            direction_unfavorable = (
                today.shape in _UNFAVORABLE_SHAPES and prior.shape in _FAVORABLE_SHAPES
            )
            prio = "HIGH" if direction_unfavorable else "MEDIUM"
            self._maybe_append(fired, "shape_transition", prio,
                today, prior, None, None, extra=f"{prior.shape} -> {today.shape}")

        # 4. rapid_steepening
        if today.spread_2s10s_delta_5d is not None and today.spread_2s10s_delta_5d > self.cfg.steepen_bps_5d:
            self._maybe_append(fired, "rapid_steepening", "HIGH",
                today, prior, today.spread_2s10s_delta_5d, 0.0)

        # 5. rapid_flattening
        if today.spread_2s10s_delta_5d is not None and today.spread_2s10s_delta_5d < self.cfg.flatten_bps_5d:
            self._maybe_append(fired, "rapid_flattening", "HIGH",
                today, prior, today.spread_2s10s_delta_5d, 0.0)

        # 6. recession_prob_critical
        p_now = today.recession_prob_nyfed
        p_prev = prior.recession_prob_nyfed
        if p_now is not None and p_prev is not None and p_prev < self.cfg.recession_prob_high <= p_now:
            self._maybe_append(fired, "recession_prob_critical", "CRITICAL",
                today, prior, p_now, p_prev)

        # 7. recession_prob_warning
        if p_now is not None and p_prev is not None and p_prev < self.cfg.recession_prob_low <= p_now:
            self._maybe_append(fired, "recession_prob_warning", "HIGH",
                today, prior, p_now, p_prev)

        return fired

    # -- helpers ------------------------------------------------------------

    def _maybe_append(
        self,
        fired: list[AlertEvent],
        rule_name: str,
        priority: str,
        today: SnapshotData,
        prior: SnapshotData,
        trigger_value: Optional[float],
        prior_value: Optional[float],
        extra: str = "",
    ) -> None:
        """Append unless anti-spam suppresses."""
        if self._is_suppressed(rule_name):
            logger.debug(f"yield_curve alert: {rule_name} suppressed by anti-spam")
            return
        delta = (trigger_value - prior_value) if (trigger_value is not None and prior_value is not None) else None
        msg = self._format_message(rule_name, priority, today, prior, trigger_value, prior_value, delta, extra)
        fired.append(AlertEvent(
            rule_name=rule_name,
            priority=priority,
            message=msg,
            trigger_value=trigger_value,
            prior_value=prior_value,
            delta=delta,
            zscore=today.zscore_2s10s_90d,
        ))

    def _is_suppressed(self, rule_name: str) -> bool:
        last = self._last_fired(rule_name)
        if last is None:
            return False
        try:
            return (datetime.now(timezone.utc).replace(tzinfo=None) - last) < timedelta(hours=self.cfg.antispam_hours)
        except TypeError:
            # last was not a real datetime (e.g. mock in tests or unparseable row).
            # Fail open — allow firing.
            return False

    def _last_fired(self, rule_name: str) -> Optional[datetime]:
        """Query the most recent triggered_at for rule_name. None if never fired."""
        try:
            from src.core.database import YieldCurveAlert
            row = (
                self.session.query(YieldCurveAlert)
                .filter_by(rule_name=rule_name)
                .order_by(YieldCurveAlert.triggered_at.desc())
                .first()
            )
            return row.triggered_at.replace(tzinfo=None) if row else None
        except Exception as exc:
            logger.warning(f"yield_curve alert: cannot query last_fired for {rule_name}: {exc}")
            return None

    @staticmethod
    def _format_message(
        rule_name: str,
        priority: str,
        today: SnapshotData,
        prior: SnapshotData,
        trigger_value: Optional[float],
        prior_value: Optional[float],
        delta: Optional[float],
        extra: str,
    ) -> str:
        s2s10s = today.spreads.get("2s10s")
        z = today.zscore_2s10s_90d
        lines = [
            f"[{priority}] {rule_name}",
            f"2s10s spread: {s2s10s:+.1f} bps (prior: {prior.spreads.get('2s10s', float('nan')):+.1f})",
            f"Shape: {prior.shape} -> {today.shape} | Trend: {today.shape_trend}",
        ]
        if trigger_value is not None:
            lines.append(f"Trigger: {trigger_value:+.2f} (prior {prior_value:+.2f}, delta {delta:+.2f})" if delta is not None else f"Trigger: {trigger_value:+.2f}")
        if z is not None:
            lines.append(f"Z-score (90d): {z:+.2f}σ")
        if extra:
            lines.append(f"Note: {extra}")
        lines.append(f"Date: {today.date}")
        return "\n".join(lines)

    async def _persist_and_dispatch(self, ev: AlertEvent, today: SnapshotData) -> None:
        """Insert into yield_curve_alerts and fire via AlertManager."""
        # 1. Persist
        try:
            from src.core.database import YieldCurveAlert
            row = YieldCurveAlert(
                rule_name=ev.rule_name,
                priority=ev.priority,
                snapshot_date=today.date,
                trigger_value=ev.trigger_value,
                prior_value=ev.prior_value,
                delta=ev.delta,
                zscore=ev.zscore,
                message=ev.message,
                channels_attempted=[],
                channels_succeeded=[],
            )
            self.session.add(row)
            self.session.commit()
        except Exception as exc:
            logger.error(f"yield_curve alert: persist failed for {ev.rule_name}: {exc}")
            self.session.rollback()

        # 2. Dispatch
        try:
            from src.alerts.alert_manager import AlertManager, AlertPriority
            mgr = AlertManager()
            prio_map = {
                "LOW": AlertPriority.LOW,
                "MEDIUM": AlertPriority.MEDIUM,
                "HIGH": AlertPriority.HIGH,
                "CRITICAL": AlertPriority.CRITICAL,
            }
            await mgr.send_alert(
                title=f"Yield Curve: {ev.rule_name}",
                message=ev.message,
                priority=prio_map.get(ev.priority, AlertPriority.MEDIUM),
                data={
                    "rule": ev.rule_name,
                    "snapshot_date": today.date.isoformat(),
                    "trigger_value": ev.trigger_value,
                    "prior_value": ev.prior_value,
                    "delta": ev.delta,
                    "zscore": ev.zscore,
                },
            )
        except Exception as exc:
            logger.error(f"yield_curve alert: dispatch failed for {ev.rule_name}: {exc}")
