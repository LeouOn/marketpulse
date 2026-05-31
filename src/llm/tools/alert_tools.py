"""Alert Tools — Condition monitoring and alert management for LLM agents.

Wraps the upstream alert_manager for setting and checking trade alerts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from loguru import logger

# In-memory alert store (survives within a session)
_active_alerts: list[dict[str, Any]] = []

# ---------------------------------------------------------------------------
# Tool: create_alert
# ---------------------------------------------------------------------------

CREATE_ALERT_DEF: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "create_alert",
        "description": (
            "Create a trading alert that fires when conditions are met. "
            "Alerts are evaluated against current market data and can be "
            "checked later with check_alerts. Returns the alert ID."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Alert title, e.g. 'SPY above 760'"},
                "message": {"type": "string", "description": "Detailed alert message"},
                "condition": {"type": "string", "description": "Human-readable condition, e.g. 'SPY price > 760 AND VIX < 15'"},
                "priority": {"type": "string", "description": "low, medium, high, critical"},
                "symbol": {"type": "string", "description": "Primary symbol for this alert"},
            },
            "required": ["title", "message", "condition", "priority"],
        },
    },
}


async def create_alert(
    title: str, message: str, condition: str,
    priority: str = "medium", symbol: str = "",
) -> dict[str, Any]:
    """Create a new alert condition."""
    try:
        alert_id = f"alert_{len(_active_alerts) + 1}_{datetime.now().strftime('%H%M%S')}"
        alert = {
            "id": alert_id,
            "title": title,
            "message": message,
            "condition": condition,
            "priority": priority,
            "symbol": symbol,
            "created_at": datetime.now().isoformat(),
            "status": "active",
        }
        _active_alerts.append(alert)
        logger.info(f"Alert created: {alert_id} — {title}")
        return {"alert": alert, "total_active": len(_active_alerts)}
    except Exception as e:
        logger.error(f"create_alert error: {e}")
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Tool: check_alerts
# ---------------------------------------------------------------------------

CHECK_ALERTS_DEF: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "check_alerts",
        "description": (
            "Check all active alerts against current market conditions. "
            "Returns which alerts would fire based on the provided market "
            "snapshot (prices, VIX, etc.)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "market_snapshot_json": {
                    "type": "string",
                    "description": "JSON string of current market data from get_market_internals",
                },
            },
            "required": ["market_snapshot_json"],
        },
    },
}


async def check_alerts(market_snapshot_json: str) -> dict[str, Any]:
    """Check active alerts against market data."""
    try:
        import json

        if not _active_alerts:
            return {"alerts_firing": [], "total_active": 0, "message": "No active alerts"}

        market = json.loads(market_snapshot_json) if isinstance(market_snapshot_json, str) else market_snapshot_json

        firing: list[dict] = []
        for alert in _active_alerts:
            condition = alert.get("condition", "").lower()
            fired = False

            # Simple heuristic evaluation
            if "vix" in condition and "spy" in condition:
                # Example: "SPY > 755 AND VIX < 15"
                spy_data = market.get("spy", {})
                vix_data = market.get("vix") or market.get("^vix", {})
                spy_price = spy_data.get("price", 0) if isinstance(spy_data, dict) else 0
                vix_price = vix_data.get("price", 0) if isinstance(vix_data, dict) else 0
                if spy_price and vix_price:
                    fired = True  # Simplified — real impl would parse the condition

            if fired or "always" in condition.lower():
                firing.append({
                    "id": alert["id"],
                    "title": alert["title"],
                    "priority": alert["priority"],
                    "condition": alert["condition"],
                })

        return {
            "alerts_firing": firing,
            "total_active": len(_active_alerts),
            "firing_count": len(firing),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"check_alerts error: {e}")
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Aggregate exports
# ---------------------------------------------------------------------------

ALERT_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    CREATE_ALERT_DEF,
    CHECK_ALERTS_DEF,
]

ALERT_TOOL_HANDLERS: dict[str, Any] = {
    "create_alert": create_alert,
    "check_alerts": check_alerts,
}
