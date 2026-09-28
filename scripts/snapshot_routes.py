"""Snapshot the app's route table (method+path set) to tests/fixtures/route_snapshot.json."""

import json
import sys
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
from pathlib import Path

from src.api.main import app
from src.api.route_utils import route_entries


def route_set() -> list[str]:
    entries = set()
    for path, methods in route_entries(app):
        if methods == ["WebSocket"]:  # websocket routes have no .methods
            entries.add(f"WS {path}")
        else:
            for m in methods:
                if m not in ("HEAD", "OPTIONS"):
                    entries.add(f"{m} {path}")
    return sorted(entries)


if __name__ == "__main__":
    out = Path("tests/fixtures/route_snapshot.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    routes = route_set()
    out.write_text(json.dumps({"routes": routes}, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(routes)} routes to {out}")
