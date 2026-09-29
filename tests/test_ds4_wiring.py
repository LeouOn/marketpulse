"""T4: ``ds4`` local LLM provider wiring (config, client, router, status).

Modeled on ``tests/test_minimax_wiring.py`` and
``tests/test_openrouter_health.py``: offline, fake-session based,
independent of the local ``config/credentials.yaml``.

ds4 = the owner's local DeepSeek V4 Flash server (antirez build):
OpenAI-compatible, no auth, native tool_calls, SSE streaming,
``reasoning_content`` in responses, health via ``GET /v1/models``.
MiniMax stays the default primary provider; nothing here may change
default behavior when no ds4 config is present.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.config import Settings
from src.llm.model_router import ModelRouter


# ---------------------------------------------------------------------------
# Fakes (session-level, no real HTTP)
# ---------------------------------------------------------------------------


class _FakeContent:
    def __init__(self, chunks: list[bytes]):
        self._chunks = chunks

    async def iter_chunked(self, n):
        for c in self._chunks:
            yield c


class _FakeResponse:
    def __init__(self, status=200, content_type="application/json", json_body=None, sse_chunks=None):
        self.status = status
        self.headers = {"Content-Type": content_type}
        self._json = json_body
        self.content = _FakeContent(sse_chunks or [])

    async def json(self):
        return self._json

    async def text(self):
        return str(self._json)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    closed = False

    def __init__(self, responses: list[_FakeResponse]):
        self._responses = list(responses)
        self.requests: list[tuple[str, dict]] = []

    def _next(self, url, kwargs):
        self.requests.append((url, kwargs))
        return self._responses.pop(0) if self._responses else _FakeResponse(500)

    def get(self, url, **kw):
        return self._next(url, {"method": "GET"})

    def post(self, url, **kw):
        return self._next(url, kw)


def _completion_body(reasoning="thinking hard", content="ds4 says hi"):
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": content,
                    "reasoning_content": reasoning,
                }
            }
        ]
    }


def _apply(obj_settings: Settings, overrides: dict) -> Settings:
    for path, value in overrides.items():
        obj = obj_settings
        parts = path.split(".")
        for p in parts[:-1]:
            obj = getattr(obj, p)
        setattr(obj, parts[-1], value)
    return obj_settings


@pytest.fixture
def fresh_settings(tmp_path, monkeypatch) -> Settings:
    """Settings built with NO .env and NO config/credentials.yaml in scope.

    chdir into an empty tmp dir so both files (read relative to the CWD)
    are invisible -- keeps these tests independent of the owner's real
    credentials, as the task requires.
    """
    monkeypatch.chdir(tmp_path)
    return Settings()


# ---------------------------------------------------------------------------
# 1. Config
# ---------------------------------------------------------------------------


class TestDS4Config:
    def test_defaults(self, fresh_settings):
        s = fresh_settings
        assert s.llm.ds4.base_url == "http://127.0.0.1:8001/v1", (
            "default port must not be 8000 (the API's own port)"
        )
        assert s.llm.ds4.model == "deepseek-v4-flash"
        assert s.llm.ds4.api_key == "not-needed"
        assert s.llm.ds4.timeout > 0

    def test_minimax_stays_default_primary(self, fresh_settings):
        s = fresh_settings
        assert s.llm.model_routing.primary_provider == "minimax"

    def test_yaml_loads_ds4_block(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "credentials.yaml").write_text(
            "llm:\n"
            "  ds4:\n"
            "    base_url: http://127.0.0.1:9999/v1\n"
            "    model: my-local-model\n"
        )
        s = Settings()
        assert s.llm.ds4.base_url == "http://127.0.0.1:9999/v1"
        assert s.llm.ds4.model == "my-local-model"


# ---------------------------------------------------------------------------
# 2. Client
# ---------------------------------------------------------------------------


class TestDS4Client:
    def _client(self, fresh_settings, settings=None):
        from src.llm.ds4_client import DS4Client

        return DS4Client(settings or fresh_settings)

    def test_uses_ds4_config_not_cloud_deepseek(self, fresh_settings):
        client = self._client(fresh_settings)
        assert client.base_url == "http://127.0.0.1:8001/v1"
        assert client.model_pro == "deepseek-v4-flash"

    def test_health_ok_on_200_json(self, fresh_settings):
        client = self._client(fresh_settings)
        client.session = _FakeSession([_FakeResponse(200, "application/json", {"data": []})])
        assert asyncio.run(client.check_health()) is True
        assert client.session.requests[0][0].endswith("/models")

    def test_health_false_on_non_200_or_html(self, fresh_settings):
        client = self._client(fresh_settings)
        client.session = _FakeSession([_FakeResponse(500, "application/json", {})])
        assert asyncio.run(client.check_health()) is False
        client.session = _FakeSession([_FakeResponse(200, "text/html", "<html>")])
        assert asyncio.run(client.check_health()) is False

    def test_unreachable_server_is_false_not_exception(self, fresh_settings):
        s = fresh_settings
        s.llm.ds4.base_url = "http://127.0.0.1:1/v1"  # port 1: refused
        client = self._client(s)
        assert asyncio.run(client.check_health()) is False

    def test_completion_preserves_reasoning_content(self, fresh_settings):
        client = self._client(fresh_settings)
        client.session = _FakeSession(
            [_FakeResponse(200, "application/json", _completion_body())]
        )
        out = asyncio.run(
            client.generate_completion(messages=[{"role": "user", "content": "hi"}])
        )
        msg = out["choices"][0]["message"]
        assert msg["content"] == "ds4 says hi"
        assert msg["reasoning_content"] == "thinking hard"

    def test_streaming_yields_tokens(self, fresh_settings):
        client = self._client(fresh_settings)
        sse = [
            b'data: {"choices": [{"delta": {"content": "hel"}}]}\n\n',
            b'data: {"choices": [{"delta": {"content": "lo"}}]}\n\n',
            b"data: [DONE]\n\n",
        ]
        client.session = _FakeSession([_FakeResponse(200, "text/event-stream", None, sse)])

        async def _drain():
            return [chunk async for chunk in client.stream_completion(
                messages=[{"role": "user", "content": "hi"}]
            )]

        chunks = asyncio.run(_drain())
        tokens = [c["token"] for c in chunks]
        assert "hel" in tokens and "lo" in tokens
        assert chunks[-1]["done"] is True


# ---------------------------------------------------------------------------
# 3. Router
# ---------------------------------------------------------------------------


def _ds4_primary_settings(fresh_settings) -> Settings:
    return _apply(fresh_settings, {
        "llm.model_routing.primary_provider": "ds4",
        "llm.model_routing.reasoning": "ds4/deepseek-v4-flash",
        "llm.model_routing.fast": "ds4/deepseek-v4-flash",
        "llm.model_routing.standard": "ds4/deepseek-v4-flash",
        "llm.model_routing.structured_output": "ds4/deepseek-v4-flash",
        "llm.model_routing.fallback_providers": "minimax,deepseek,lm_studio,openrouter",
    })


class TestRouterDS4:
    def test_ds4_registered_as_provider(self, fresh_settings):
        s = _ds4_primary_settings(fresh_settings)
        s.llm.ds4.base_url = "http://127.0.0.1:1/v1"  # refuse fast

        async def _run_router():
            async with ModelRouter(s) as router:
                return list(router._providers)

        assert "ds4" in asyncio.run(_run_router())

    def test_provider_for_model_prefixed_id(self, fresh_settings):
        router = ModelRouter(_ds4_primary_settings(fresh_settings))
        assert router._provider_for_model("ds4/deepseek-v4-flash", "minimax") == "ds4"

    def test_provider_for_model_ds4_model_with_ds4_primary(self, fresh_settings):
        router = ModelRouter(_ds4_primary_settings(fresh_settings))
        assert router._provider_for_model("deepseek-v4-flash", "ds4") == "ds4"

    def test_provider_for_model_deepseek_substring_still_cloud(self, fresh_settings):
        router = ModelRouter(fresh_settings)  # primary minimax
        assert router._provider_for_model("deepseek-v4-pro", "minimax") == "deepseek"

    def test_capability_map_strips_provider_prefix(self, fresh_settings):
        router = ModelRouter(_ds4_primary_settings(fresh_settings))
        assert router._capability_map["standard"] == ("ds4", "deepseek-v4-flash")

    def test_unknown_capability_routes_to_primary_model(self, fresh_settings):
        s = fresh_settings  # minimax primary
        router = ModelRouter(s)
        assert router._capability_map.get("fallback") is not None
        # route() with unknown capability: default comes from primary provider config
        provider, model = router._capability_map["fallback"]
        assert provider == "minimax" and model == s.llm.minimax.model

    def test_fallback_to_minimax_when_ds4_down(self, fresh_settings, monkeypatch):
        s = _ds4_primary_settings(fresh_settings)
        s.llm.ds4.base_url = "http://127.0.0.1:1/v1"

        from src.llm.minimax_client import MiniMaxClient

        async def _healthy(self):
            return True

        monkeypatch.setattr(MiniMaxClient, "check_health", _healthy)

        async def _route():
            async with ModelRouter(s) as router:
                client, model = await router.route("standard")
                return type(client).__name__, model

        name, model = asyncio.run(_route())
        assert name == "MiniMaxClient"
        assert model == "MiniMax-M3"

    def test_completion_through_router_with_ds4_primary(self, fresh_settings):
        from src.llm.ds4_client import DS4Client

        s = _ds4_primary_settings(fresh_settings)
        fake_client = DS4Client(s)
        fake_client.session = _FakeSession(
            [_FakeResponse(200, "application/json", _completion_body())]
        )

        async def _generate():
            async with ModelRouter(s) as router:
                router._providers["ds4"].client = fake_client
                router._providers["ds4"].healthy = True
                return await router.generate(
                    [{"role": "user", "content": "hi"}], capability="standard"
                )

        out = asyncio.run(_generate())
        assert out["choices"][0]["message"]["reasoning_content"] == "thinking hard"
        url, kwargs = fake_client.session.requests[0]
        assert url.endswith("/chat/completions")
        assert kwargs["json"]["model"] == "deepseek-v4-flash"

    def test_list_available_models_includes_ds4(self, fresh_settings):
        router = ModelRouter(fresh_settings)
        models = router.list_available_models()
        ds4_entries = [m for m in models if m["provider"] == "ds4"]
        assert ds4_entries, "ds4 must appear in the model list"
        assert ds4_entries[0]["id"] == "deepseek-v4-flash"


# ---------------------------------------------------------------------------
# 4. Status surfaces
# ---------------------------------------------------------------------------


class TestStatusSurfaces:
    def test_get_status_lists_ds4(self, fresh_settings, monkeypatch):
        import src.llm.llm_client as llm_client_mod
        from src.llm.llm_client import LLMManager

        monkeypatch.setattr(llm_client_mod, "get_settings", lambda: fresh_settings)
        status = LLMManager().get_status()
        assert "ds4" in status
        assert status["ds4"]["endpoint"] == "http://127.0.0.1:8001/v1"
        assert status["ds4"]["model"] == "deepseek-v4-flash"

    def test_placeholder_or_unresolved_key_is_not_available(self, fresh_settings, monkeypatch):
        import src.llm.llm_client as llm_client_mod
        from src.llm.llm_client import LLMManager

        fresh_settings.llm.minimax.api_key = "${api_keys:minimax:api_key}"
        monkeypatch.setattr(llm_client_mod, "get_settings", lambda: fresh_settings)
        assert LLMManager().get_status()["minimax"]["available"] is False

    def test_model_status_endpoint_lists_all_providers(self, monkeypatch):
        import src.api.routers.llm as llm_router_mod

        async def _fake_probe(url, timeout):
            return False

        monkeypatch.setattr(llm_router_mod, "_probe_url_json", _fake_probe)

        app = FastAPI()
        app.include_router(llm_router_mod.router)
        client = TestClient(app)

        r = client.get("/api/llm/model-status")
        assert r.status_code == 200, r.text
        providers = r.json()["data"]["providers"]
        for name in ("deepseek", "lm_studio", "minimax", "openrouter", "ds4"):
            assert name in providers, f"{name} missing from model-status"
        assert providers["ds4"]["endpoint"]
        assert "routing" in r.json()["data"]
