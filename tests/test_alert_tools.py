"""Offline coverage for src/llm/tools/alert_tools.py.

The module is the agent-facing alert wrapper: ``create_alert`` stores
conditions in a module-global session store, ``check_alerts`` evaluates them
against a market-snapshot JSON with a deliberately simplified heuristic
(both "spy" and "vix" keywords in the condition + both prices present =>
firing; "always" in the condition => firing). Consumers:
``src/llm/agents/alert_agent.py`` (tool names) and ``src/llm/tools/registry.py``
(``ALERT_TOOL_DEFINITIONS`` / ``ALERT_TOOL_HANDLERS``) — the
definition/handler shapes they rely on are pinned here.

No network, no LLM: everything is plain dict/JSON logic.

The module-global ``_active_alerts`` store is snapshotted and cleared around
every test so order never matters.

Tests marked ``test_bug_*`` fail on the pre-fix module (proven against a
HEAD copy in the cycle-9 report); the rest pin existing behaviour and pass
on both versions. All calls go through ``alert_tools.<fn>`` attribute access
so the HEAD-copy proof can swap ``sys.modules`` entries.
"""

from __future__ import annotations

import asyncio
import json
import math
from datetime import datetime

import pytest

from src.llm.tools import alert_tools


@pytest.fixture(autouse=True)
def _isolated_alert_store():
    saved = alert_tools._active_alerts[:]
    alert_tools._active_alerts.clear()
    yield
    alert_tools._active_alerts.clear()
    alert_tools._active_alerts.extend(saved)


def _run(coro):
    return asyncio.run(coro)


def _snapshot(spy=None, vix=None, extra=None):
    market = {}
    if spy is not None:
        market["spy"] = spy
    if vix is not None:
        market["vix"] = vix
    market.update(extra or {})
    return json.dumps(market)


# ---------------------------------------------------------------------------
# Registry / tool-definition shape (what alert_agent + registry consume)
# ---------------------------------------------------------------------------


def test_tool_definitions_shape():
    defs = alert_tools.ALERT_TOOL_DEFINITIONS
    assert isinstance(defs, list) and len(defs) == 2
    names = []
    for d in defs:
        assert d["type"] == "function"
        fn = d["function"]
        assert fn["name"] and fn["description"]
        assert fn["parameters"]["type"] == "object"
        for prop in fn["parameters"]["properties"].values():
            assert "type" in prop and "description" in prop
        names.append(fn["name"])
    assert names == ["create_alert", "check_alerts"]
    # create_alert requires its core fields
    assert set(defs[0]["function"]["parameters"]["required"]) == {"title", "message", "condition", "priority"}
    assert defs[1]["function"]["parameters"]["required"] == ["market_snapshot_json"]


def test_tool_handlers_match_definitions():
    handlers = alert_tools.ALERT_TOOL_HANDLERS
    def_names = {d["function"]["name"] for d in alert_tools.ALERT_TOOL_DEFINITIONS}
    assert set(handlers) == def_names
    for name, handler in handlers.items():
        assert callable(handler), name
        assert asyncio.iscoroutinefunction(handler), name


# ---------------------------------------------------------------------------
# create_alert
# ---------------------------------------------------------------------------


def test_create_alert_stores_and_echoes():
    out = _run(
        alert_tools.create_alert(
            title="SPY above 760",
            message="Breakout watch",
            condition="SPY price > 760 AND VIX < 15",
            priority="high",
            symbol="SPY",
        )
    )
    assert "error" not in out
    alert = out["alert"]
    assert alert["id"].startswith("alert_")
    assert alert["title"] == "SPY above 760"
    assert alert["priority"] == "high"
    assert alert["symbol"] == "SPY"
    assert alert["status"] == "active"
    datetime.fromisoformat(alert["created_at"])  # parseable ISO timestamp
    assert out["total_active"] == 1
    assert alert_tools._active_alerts[0] is alert


def test_create_alert_defaults_and_unique_ids():
    a = _run(alert_tools.create_alert(title="t", message="m", condition="SPY > 1 AND VIX < 2"))
    assert a["alert"]["priority"] == "medium"
    assert a["alert"]["symbol"] == ""
    b = _run(alert_tools.create_alert(title="t2", message="m2", condition="always show me"))
    assert b["alert"]["id"] != a["alert"]["id"]
    assert b["total_active"] == 2


def test_create_alert_weird_types_do_not_crash():
    out = _run(alert_tools.create_alert(title=None, message=None, condition="", priority=123))
    assert "error" not in out  # stored as given — validation is the caller's job


# ---------------------------------------------------------------------------
# check_alerts
# ---------------------------------------------------------------------------


def test_check_alerts_no_active():
    out = _run(alert_tools.check_alerts(_snapshot(spy={"price": 450.0})))
    assert out == {"alerts_firing": [], "total_active": 0, "message": "No active alerts"}


def _make_spy_vix_alert(condition="SPY price > 760 AND VIX < 15"):
    return _run(alert_tools.create_alert(title="T", message="M", condition=condition, priority="high"))


def test_check_alerts_spy_vix_condition_fires_with_both_prices():
    _make_spy_vix_alert()
    out = _run(alert_tools.check_alerts(_snapshot(spy={"price": 761.0}, vix={"price": 14.0})))
    assert out["total_active"] == 1
    assert out["firing_count"] == 1
    entry = out["alerts_firing"][0]
    assert set(entry) == {"id", "title", "priority", "condition"}
    datetime.fromisoformat(out["timestamp"])


def test_check_alerts_missing_vix_or_spy_does_not_fire():
    _make_spy_vix_alert()
    only_spy = _run(alert_tools.check_alerts(_snapshot(spy={"price": 761.0})))
    assert only_spy["alerts_firing"] == []
    zero_price = _run(alert_tools.check_alerts(_snapshot(spy={"price": 761.0}, vix={"price": 0})))
    assert zero_price["alerts_firing"] == []


def test_check_alerts_vix_symbol_fallback_and_bad_entries():
    _make_spy_vix_alert()
    caret = _run(alert_tools.check_alerts(_snapshot(spy={"price": 761.0}, extra={"^vix": {"price": 14.0}})))
    assert caret["firing_count"] == 1  # ^vix fallback key works
    non_dict = _run(alert_tools.check_alerts(_snapshot(spy=761.0, vix={"price": 14.0})))
    assert non_dict["alerts_firing"] == []  # non-dict entries read as no price
    null_vix = _run(alert_tools.check_alerts(_snapshot(spy={"price": 1.0}, vix=None)))
    assert null_vix["alerts_firing"] == []


def test_check_alerts_spy_only_condition_never_fires():
    # The heuristic only evaluates conditions mentioning BOTH vix and spy.
    _run(alert_tools.create_alert(title="t", message="m", condition="SPY price > 760"))
    out = _run(alert_tools.check_alerts(_snapshot(spy={"price": 900.0}, vix={"price": 1.0})))
    assert out["alerts_firing"] == []


def test_check_alerts_always_condition_fires_without_market_data():
    _run(alert_tools.create_alert(title="t", message="m", condition="ALWAYS remind me at open"))
    out = _run(alert_tools.check_alerts(_snapshot()))
    assert out["firing_count"] == 1


def test_check_alerts_invalid_json_returns_error_dict():
    _make_spy_vix_alert()
    out = _run(alert_tools.check_alerts("{not json"))
    assert "error" in out


def test_check_alerts_none_snapshot_returns_error_dict():
    _make_spy_vix_alert()
    out = _run(alert_tools.check_alerts(None))
    assert "error" in out


def test_check_alerts_empty_string_snapshot_returns_error_dict():
    _make_spy_vix_alert()
    out = _run(alert_tools.check_alerts(""))
    assert "error" in out


def test_check_alerts_accepts_dict_directly():
    _make_spy_vix_alert()
    out = _run(alert_tools.check_alerts({"spy": {"price": 761.0}, "vix": {"price": 14.0}}))
    assert out["firing_count"] == 1


# ---------------------------------------------------------------------------
# Bugs (fail on old code)
# ---------------------------------------------------------------------------


def test_bug_check_alerts_nan_prices_do_not_fire():
    _make_spy_vix_alert()
    out = _run(alert_tools.check_alerts(_snapshot(spy={"price": math.nan}, vix={"price": math.nan})))
    assert out["alerts_firing"] == []  # NaN is truthy but is not a price


def test_bug_check_alerts_string_prices_do_not_fire():
    _make_spy_vix_alert()
    out = _run(alert_tools.check_alerts(_snapshot(spy={"price": "761"}, vix={"price": "14"})))
    assert out["alerts_firing"] == []


def test_bug_check_alerts_bool_and_negative_prices_do_not_fire():
    _make_spy_vix_alert()
    bools = _run(alert_tools.check_alerts(_snapshot(spy={"price": True}, vix={"price": True})))
    assert bools["alerts_firing"] == []
    negative = _run(alert_tools.check_alerts(_snapshot(spy={"price": -761.0}, vix={"price": -14.0})))
    assert negative["alerts_firing"] == []
