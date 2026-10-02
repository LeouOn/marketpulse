"""GET /api/ai/status must not claim the provider key is configured when it is
an unresolved settings interpolation token such as ``${api_keys:minimax:api_key}``
(or empty/whitespace, or a ``your_`` placeholder).

Regression tests for the misleading-status bug recorded in docs/STATUS.md
(AI analyst section, "Open bug (misleading status)"): with no ``.env`` at all,
``_resolve_provider()`` only rejected values containing ``your_``, so the raw
``${...}`` token was accepted as a real key and the status endpoint reported
``provider_api_configured: true`` while real queries failed with a provider 401.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.ai.massive_analyst import MassiveAIAnalyst, _resolve_provider, _usable_provider_key

UNRESOLVED_TOKEN = "${api_keys:minimax:api_key}"


@pytest.fixture(autouse=True)
def _no_ambient_keys(monkeypatch):
    """Keep ambient env from making an unconfigured provider look configured."""
    for var in ("MASSIVE_API_KEY", "ANTHROPIC_API_KEY", "MINIMAX_API_KEY"):
        monkeypatch.delenv(var, raising=False)


def _settings_with_key(api_key: str):
    """Pin the cached settings singleton to minimax with the given key.

    The endpoint and the analyst both read the same cached ``get_settings()``
    instance (the conftest resets the singleton after each test), so mutating
    it here is deterministic for the code under test.
    """
    from src.core.config import get_settings

    settings = get_settings()
    settings.llm.model_routing.primary_provider = "minimax"
    settings.llm.minimax.api_key = api_key
    return settings


@pytest.fixture
def status_client(monkeypatch):
    """A client for the AI router with the analyst singleton reset.

    monkeypatch (not plain assignment) so the previous value is restored at
    teardown and no cached analyst leaks into later test modules.
    """
    from src.api import ai_endpoints

    monkeypatch.setattr(ai_endpoints, "analyst", None)
    app = FastAPI()
    app.include_router(ai_endpoints.ai_router)
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# _resolve_provider: placeholder keys must be rejected, not used
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_key", [UNRESOLVED_TOKEN, "  ", "", "your_minimax_api_key", "YOUR_MINIMAX_API_KEY"])
def test_resolve_provider_rejects_placeholder_keys(bad_key):
    """An unresolved/empty/your_-placeholder key must raise, naming the env var."""
    settings = _settings_with_key(bad_key)

    with pytest.raises(ValueError, match="minimax API key required.*MINIMAX_API_KEY"):
        _resolve_provider(settings)


def test_resolve_provider_accepts_a_real_looking_key():
    """A real-looking key still resolves and is carried on the spec."""
    settings = _settings_with_key("real-minimax-key-123")

    spec = _resolve_provider(settings)

    assert spec.name == "minimax"
    assert spec.api_key == "real-minimax-key-123"


def test_analyst_construction_fails_clearly_on_unresolved_token():
    """The query path must fail up front instead of sending the token as a key."""
    settings = _settings_with_key(UNRESOLVED_TOKEN)

    with pytest.raises(ValueError, match="minimax API key required"):
        MassiveAIAnalyst(settings=settings)


# ---------------------------------------------------------------------------
# GET /api/ai/status: provider_api_configured must tell the truth
# ---------------------------------------------------------------------------


def test_status_reports_unresolved_token_as_not_configured(status_client):
    """The exact bug from docs/STATUS.md: ``${...}`` key must not read as configured."""
    _settings_with_key(UNRESOLVED_TOKEN)

    response = status_client.get("/api/ai/status")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["provider_api_configured"] is False
    assert data["provider"] == "minimax"
    # The response should say why, not just flip the flag silently.
    message = str(data.get("message", ""))
    assert "MINIMAX_API_KEY" in message


def test_status_reports_whitespace_key_as_not_configured(status_client):
    _settings_with_key("   ")

    response = status_client.get("/api/ai/status")

    assert response.status_code == 200
    assert response.json()["data"]["provider_api_configured"] is False


def test_status_reports_your_placeholder_as_not_configured(status_client):
    _settings_with_key("your_minimax_api_key")

    response = status_client.get("/api/ai/status")

    assert response.status_code == 200
    assert response.json()["data"]["provider_api_configured"] is False


def test_status_reports_real_key_as_configured(status_client):
    _settings_with_key("real-minimax-key-123")

    response = status_client.get("/api/ai/status")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["provider_api_configured"] is True
    assert data["provider"] == "minimax"


def test_query_endpoint_fails_with_clear_message_on_unresolved_token(status_client):
    """A real query must surface the key problem, not a provider 401."""
    _settings_with_key(UNRESOLVED_TOKEN)

    response = status_client.post("/api/ai/query", json={"question": "What is a stop loss?"})

    assert response.status_code == 500
    assert "minimax API key required" in response.json()["detail"]


# ---------------------------------------------------------------------------
# _usable_provider_key: anchored placeholder match, not a substring hunt
# ---------------------------------------------------------------------------


def test_usable_provider_key_allows_mid_string_your_():
    """A key that merely CONTAINS "your_" mid-string is a real, usable key.

    The old substring check (``"your_" in key.lower()``) wrongly rejected
    keys like "sk-abc-your_xyz"; the anchored rule matches keys.py and only
    rejects keys that START with a placeholder marker.
    """
    assert _usable_provider_key("sk-abc-your_xyz") is True


@pytest.mark.parametrize("bad_key", ["your_key_here", UNRESOLVED_TOKEN, "  ", ""])
def test_usable_provider_key_rejects_placeholder_keys(bad_key):
    assert _usable_provider_key(bad_key) is False
