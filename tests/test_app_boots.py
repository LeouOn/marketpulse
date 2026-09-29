"""Startup guard (T10 step 3): the app must boot with every router mounted.

``src.api.main`` mounts routers in guarded try/except blocks that log
``Could not load ... endpoints`` and continue on failure -- a broken
import used to degrade the API silently. This test pins the contract
the CI ``import src.api.main`` step can't check on its own: every route
in the snapshot fixture (one line per ``METHOD /path``) must exist on
the booted app, so any router group that fails to load fails CI here.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.api.main import app
from src.api.route_utils import route_entries

_SNAPSHOT = Path(__file__).parent / "fixtures" / "route_snapshot.json"


def _method_map() -> dict[str, set[str]]:
    """Aggregate methods per path (a path can carry GET *and* POST routes)."""
    agg: dict[str, set[str]] = {}
    for path, methods in route_entries(app):
        agg.setdefault(path, set()).update(methods)
    return agg


def test_app_boots_with_all_snapshot_routes():
    snapshot = json.loads(_SNAPSHOT.read_text(encoding="utf-8"))["routes"]

    entries = _method_map()

    missing = []
    for route in snapshot:
        method, path = route.split(" ", 1)
        if path not in entries:
            missing.append(route)
        elif method == "WS":  # snapshot notation; route_entries uses "WebSocket"
            if "WebSocket" not in entries[path]:
                missing.append(route)
        elif method not in entries[path]:
            missing.append(route)

    assert not missing, (
        f"{len(missing)} snapshot route(s) missing -- a router group "
        f"failed to load at import time: {sorted(missing)[:10]}"
    )


def test_app_route_count_at_least_snapshot():
    snapshot = json.loads(_SNAPSHOT.read_text(encoding="utf-8"))["routes"]
    assert len(route_entries(app)) >= len(snapshot)
