"""route_entries must see routes in included routers on every FastAPI version."""

from fastapi import APIRouter, FastAPI

from src.api.route_utils import route_entries


def _app() -> FastAPI:
    app = FastAPI()
    inner = APIRouter()

    @inner.get("/things")
    async def things():
        return []

    @inner.post("/things")
    async def add_thing():
        return {}

    @inner.websocket("/live")
    async def live(ws):
        await ws.close()

    app.include_router(inner, prefix="/api/v1")
    plain = APIRouter()

    @plain.get("/ping")
    async def ping():
        return "pong"

    app.include_router(plain)
    return app


def _methods_by_path(app: FastAPI) -> dict[str, set[str]]:
    merged: dict[str, set[str]] = {}
    for path, methods in route_entries(app):
        merged.setdefault(path, set()).update(methods)
    return merged


def test_nested_router_routes_get_their_include_prefix():
    merged = _methods_by_path(_app())
    assert {"GET", "POST"} <= merged["/api/v1/things"]
    assert "/ping" in merged


def test_websocket_routes_are_reported():
    assert _methods_by_path(_app())["/api/v1/live"] == {"WebSocket"}


def test_docs_routes_are_included():
    paths = [p for p, _ in route_entries(_app())]
    assert "/openapi.json" in paths and "/docs" in paths
