"""Enumerate every route of a FastAPI app, including those in included routers.

Newer FastAPI (0.14x) keeps ``include_router`` results nested as lazy
``_IncludedRouter`` entries instead of flattening them into ``app.routes``, so a
plain ``for route in app.routes`` only sees a handful of top-level routes. Older
versions flatten, and this walker handles those unchanged.
"""

from collections.abc import Iterator
from typing import Any


def iter_routes(routes: Any, prefix: str = "") -> Iterator[tuple[str, Any]]:
    """Yield ``(full_path, route)`` for every leaf route, descending into nested routers."""
    for route in routes:
        inner = getattr(route, "original_router", None)
        if inner is not None:
            include_prefix = getattr(getattr(route, "include_context", None), "prefix", "") or ""
            yield from iter_routes(inner.routes, prefix + include_prefix)
            continue
        path = getattr(route, "path", None)
        if path:
            yield prefix + path, route


def route_entries(app: Any) -> list[tuple[str, list[str]]]:
    """Sorted ``(path, methods)`` pairs; websocket routes get ``["WebSocket"]``."""
    entries = []
    for path, route in iter_routes(app.routes):
        methods = getattr(route, "methods", None)
        entries.append((path, sorted(methods) if methods else ["WebSocket"]))
    return sorted(entries)
