"""OpenRouter health: a missing/placeholder key must not look healthy."""

import asyncio

from src.core.config import get_settings
from src.llm.llm_client import LLMManager, OpenRouterClient


class _FakeResponse:
    def __init__(self, status, content_type):
        self.status = status
        self.headers = {"Content-Type": content_type}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    def __init__(self, response):
        self._response = response
        self.urls = []

    def get(self, url):
        self.urls.append(url)
        return self._response


def _client(monkeypatch, key):
    s = get_settings()
    monkeypatch.setattr(s.llm.fallback, "api_key", key)
    return OpenRouterClient(s)


def test_unhealthy_without_a_real_key(monkeypatch):
    for key in ("", "your_openrouter_api_key", "${api_keys:openrouter:api_key}"):
        assert asyncio.run(_client(monkeypatch, key).check_health()) is False


def test_healthy_with_key_and_no_session(monkeypatch):
    assert asyncio.run(_client(monkeypatch, "sk-or-real").check_health()) is True


def test_probe_uses_auth_key_and_requires_json_200(monkeypatch):
    client = _client(monkeypatch, "sk-or-real")
    client.session = _FakeSession(_FakeResponse(200, "application/json"))
    assert asyncio.run(client.check_health()) is True
    assert client.session.urls == [f"{client.base_url}/auth/key"]

    client.session = _FakeSession(_FakeResponse(401, "application/json"))
    assert asyncio.run(client.check_health()) is False
    client.session = _FakeSession(_FakeResponse(200, "text/html"))
    assert asyncio.run(client.check_health()) is False


def test_status_treats_unresolved_placeholder_as_unavailable(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s.llm.fallback, "api_key", "${api_keys:openrouter:api_key}")
    monkeypatch.setattr(s.llm.minimax, "api_key", "sk-real")
    status = LLMManager().get_status()
    assert status["openrouter"]["available"] is False
    assert status["minimax"]["available"] is True
