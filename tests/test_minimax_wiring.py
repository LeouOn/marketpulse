"""Tests for the MiniMax LLM provider wiring.

After the 2026-06-10 spec change, MiniMax is the DEFAULT primary LLM provider,
targeting https://api.minimax.io/v1 with the MiniMax-M3 model. These tests verify:

1. The config defaults to the new endpoint + model.
2. ModelRouter registers MiniMax as a provider and picks it first when healthy.
3. ModelRouter._provider_for_model routes M3 model ids to minimax.
4. The LLMManager status includes the minimax entry with the new endpoint.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from src.core.config import LLMSettings, get_settings, interpolate_env_vars
from src.llm.llm_client import LLMManager
from src.llm.minimax_client import MiniMaxClient
from src.llm.model_router import ModelRouter

# ---------------------------------------------------------------------------
# Config defaults
# ---------------------------------------------------------------------------


def test_minimax_config_uses_minimax_io():
    """Config must default to the api.minimax.io API host (minimax.io itself is the website)."""
    s = get_settings()
    assert s.llm.minimax.base_url == "https://api.minimax.io/v1"
    assert s.llm.minimax.model == "MiniMax-M3"


def test_minimax_api_keys_config_uses_minimax_io():
    """The api_keys.minimax block (used by .env interpolation) must match."""
    s = get_settings()
    assert s.api_keys.minimax.base_url == "https://api.minimax.io/v1"


def test_minimax_is_default_primary_provider():
    """Code defaults (not the local credentials.yaml) must route to minimax first."""
    routing = LLMSettings().model_routing
    assert routing.primary_provider == "minimax"
    assert "MiniMax-M3" in routing.reasoning
    assert "MiniMax-M3" in routing.fast
    assert "MiniMax-M3" in routing.standard
    assert "MiniMax-M3" in routing.structured_output


def test_minimax_fallback_chain_includes_legacy_providers():
    """DeepSeek, LM Studio, and OpenRouter must remain in the fallback chain."""
    s = get_settings()
    fallbacks = s.llm.model_routing.fallback_providers
    for provider in ("deepseek", "lm_studio", "openrouter"):
        assert provider in fallbacks, f"{provider} missing from fallback chain"


# ---------------------------------------------------------------------------
# MiniMax client
# ---------------------------------------------------------------------------


def test_minimax_client_uses_configured_endpoint():
    """MiniMaxClient must read endpoint + model from the (new) config."""
    s = get_settings()
    client = MiniMaxClient(s)
    assert client.base_url == "https://api.minimax.io/v1"
    assert client.model == "MiniMax-M3"


def test_minimax_client_reports_unhealthy_with_default_key():
    """With the placeholder api_key, check_health must return False."""
    s = get_settings()
    s.llm.minimax.api_key = "your_minimax_api_key"
    client = MiniMaxClient(s)
    assert asyncio.run(client.check_health()) is False


def test_minimax_client_reports_healthy_with_real_key():
    """With a non-default api_key and no live session, health is True."""
    s = get_settings()
    s.llm.minimax.api_key = "sk-real-key-123"
    client = MiniMaxClient(s)
    assert asyncio.run(client.check_health()) is True


def test_minimax_client_reports_unhealthy_with_unresolved_placeholder():
    """A ${...} YAML placeholder that never resolved must not count as a key."""
    s = get_settings()
    s.llm.minimax.api_key = "${api_keys:minimax:api_key}"
    client = MiniMaxClient(s)
    assert asyncio.run(client.check_health()) is False


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

    def get(self, url):
        return self._response


def _probe(status, content_type):
    s = get_settings()
    s.llm.minimax.api_key = "sk-real-key-123"
    client = MiniMaxClient(s)
    client.session = _FakeSession(_FakeResponse(status, content_type))
    return asyncio.run(client.check_health())


def test_minimax_probe_rejects_html_200():
    """A wrong base_url can redirect to the marketing site (200 text/html)."""
    assert _probe(200, "text/html; charset=utf-8") is False


def test_minimax_probe_accepts_json_200_and_rejects_401():
    assert _probe(200, "application/json") is True
    assert _probe(401, "application/json") is False


# ---------------------------------------------------------------------------
# Env interpolation of the YAML ${...} placeholders
# ---------------------------------------------------------------------------


def test_interpolation_falls_back_to_section_less_env_name():
    """${api_keys:minimax:api_key} must find MINIMAX_API_KEY, as .env.example names it."""
    assert interpolate_env_vars("${api_keys:minimax:api_key}", {"MINIMAX_API_KEY": "abc"}) == "abc"


def test_interpolation_prefers_full_path_name_and_leaves_unresolved():
    env = {"API_KEYS_MINIMAX_API_KEY": "full", "MINIMAX_API_KEY": "short"}
    assert interpolate_env_vars("${api_keys:minimax:api_key}", env) == "full"
    assert interpolate_env_vars("${api_keys:minimax:api_key}", {}) == "${api_keys:minimax:api_key}"


# ---------------------------------------------------------------------------
# Model router
# ---------------------------------------------------------------------------


def test_provider_for_model_routes_m3_to_minimax():
    """_provider_for_model must return 'minimax' for MiniMax-M3 / minimax ids."""
    s = get_settings()
    router = ModelRouter(s)
    assert router._provider_for_model("MiniMax-M3", "minimax") == "minimax"
    assert router._provider_for_model("minimax-text-01", "minimax") == "minimax"
    # Existing heuristic for other models is preserved
    assert router._provider_for_model("deepseek-v4-pro", "minimax") == "deepseek"
    assert router._provider_for_model("gpt-4o", "minimax") == "openrouter"


def test_fallback_model_for_minimax_returns_m3():
    s = get_settings()
    router = ModelRouter(s)
    assert router._fallback_model_for("minimax", "reasoning") == "MiniMax-M3"
    assert router._fallback_model_for("minimax", "fast") == "MiniMax-M3"
    assert router._fallback_model_for("minimax", "standard") == "MiniMax-M3"


def test_list_available_models_includes_minimax_first():
    s = get_settings()
    router = ModelRouter(s)
    models = router.list_available_models()
    assert models[0]["provider"] == "minimax"
    assert models[0]["id"] == "MiniMax-M3"
    assert models[0]["recommended"] is True


def test_model_router_registers_minimax_provider():
    """After __aenter__, the providers dict must include 'minimax' with priority 0."""
    async def _check():
        s = get_settings()
        # Force a valid-looking key so the provider isn't filtered as unhealthy
        s.llm.minimax.api_key = "sk-test"
        # Stub out aiohttp.ClientSession in the MiniMax client to avoid real I/O
        with patch("aiohttp.ClientSession"):
            router = ModelRouter(s)
            async with router:
                assert "minimax" in router._providers
                assert router._providers["minimax"].priority == 0  # highest
                assert "deepseek" in router._providers
                assert "lm_studio" in router._providers
                assert "openrouter" in router._providers

    asyncio.run(_check())


# ---------------------------------------------------------------------------
# LLMManager status
# ---------------------------------------------------------------------------


def test_llm_manager_status_uses_new_minimax_endpoint(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s.llm.minimax, "api_key", "sk-test-123")
    monkeypatch.setattr(s.llm.model_routing, "primary_provider", "minimax")
    mgr = LLMManager()
    status = mgr.get_status()
    assert status["minimax"]["endpoint"] == "https://api.minimax.io/v1"
    assert status["minimax"]["model"] == "MiniMax-M3"
    assert status["routing"]["primary"] == "minimax"
