"""Route table must be identical before/after the Phase A1 refactor."""

import json
from pathlib import Path

from scripts.snapshot_routes import route_set

FIXTURE = Path(__file__).parent / "fixtures" / "route_snapshot.json"


def test_route_table_matches_snapshot():
    expected = set(json.loads(FIXTURE.read_text(encoding="utf-8"))["routes"])
    actual = set(route_set())
    missing = expected - actual
    added = actual - expected
    assert not missing, f"Routes LOST in refactor: {sorted(missing)}"
    assert not added, f"Routes ADDED (update fixture if intentional): {sorted(added)}"
