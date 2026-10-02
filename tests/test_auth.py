"""Offline tests for ``src/api/auth.py`` (X-API-Key middleware).

No network: the dependency is driven through a FastAPI TestClient with fake
secrets only, and directly as a coroutine for the None/empty paths. Special
care is taken that failure paths DENY, that no secret is ever logged or
echoed, and that the no-key-configured behaviour is explicit.
"""

from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from src.api.auth import optional_api_key, validate_api_key

FAKE_KEY = "sk-test-fake-key-not-real"
FAKE_OTHER = "sk-test-other-fake-key"


@pytest.fixture
def settings():
    from src.core.config import get_settings

    s = get_settings()
    s.api_keys_list = ""  # explicit open mode unless a test overrides
    return s


@pytest.fixture
def strict_client(settings):
    app = FastAPI()

    @app.get("/protected")
    async def protected(key: str = Depends(validate_api_key)):
        return {"principal": key, "anonymous": key == "no-auth-required"}

    return TestClient(app)


@pytest.fixture
def optional_client(settings):
    app = FastAPI()

    @app.get("/maybe")
    async def maybe(key: str | None = Depends(optional_api_key)):
        return {"principal": key}

    return TestClient(app)


# ---------------------------------------------------------------------------
# Open mode (no keys configured) -- explicit and tested
# ---------------------------------------------------------------------------


def test_no_keys_configured_missing_header_is_open(strict_client, settings):
    response = strict_client.get("/protected")

    assert response.status_code == 200
    assert response.json() == {"principal": "no-auth-required", "anonymous": True}


def test_no_keys_configured_any_provided_key_is_accepted(strict_client, settings):
    """Open mode honors a provided key verbatim (validation is a no-op then)."""
    settings.api_keys_list = ""

    response = strict_client.get("/protected", headers={"X-API-Key": FAKE_KEY})

    assert response.status_code == 200
    assert response.json() == {"principal": FAKE_KEY, "anonymous": False}


# ---------------------------------------------------------------------------
# Strict dependency: failure paths must deny
# ---------------------------------------------------------------------------


def test_missing_header_with_keys_configured_is_401(strict_client, settings):
    settings.api_keys_list = FAKE_KEY

    response = strict_client.get("/protected")

    assert response.status_code == 401
    assert "X-API-Key" in response.json()["detail"]


def test_empty_header_value_is_treated_as_missing(strict_client, settings):
    settings.api_keys_list = FAKE_KEY

    response = strict_client.get("/protected", headers={"X-API-Key": ""})

    assert response.status_code == 401


def test_valid_key_is_accepted_and_returned(strict_client, settings):
    settings.api_keys_list = FAKE_KEY

    response = strict_client.get("/protected", headers={"X-API-Key": FAKE_KEY})

    assert response.status_code == 200
    assert response.json()["principal"] == FAKE_KEY


def test_any_key_in_the_comma_list_is_accepted(strict_client, settings):
    settings.api_keys_list = f" {FAKE_OTHER} , {FAKE_KEY} "  # list parsing strips

    response = strict_client.get("/protected", headers={"X-API-Key": FAKE_KEY})

    assert response.status_code == 200


def test_wrong_key_is_403(strict_client, settings):
    settings.api_keys_list = FAKE_KEY

    response = strict_client.get("/protected", headers={"X-API-Key": FAKE_OTHER})

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid API key."


def test_wrong_case_key_is_denied(strict_client, settings):
    """Secrets compare case-sensitively."""
    settings.api_keys_list = FAKE_KEY

    response = strict_client.get("/protected", headers={"X-API-Key": FAKE_KEY.upper()})

    assert response.status_code == 403


def test_whitespace_padded_key_is_denied(strict_client, settings):
    """Current behaviour: the incoming key is NOT stripped. Pinned here and
    flagged in the report -- stripping would loosen who is allowed in."""
    settings.api_keys_list = FAKE_KEY

    padded = strict_client.get("/protected", headers={"X-API-Key": f" {FAKE_KEY} "})
    suffixed = strict_client.get("/protected", headers={"X-API-Key": f"{FAKE_KEY}\t"})

    assert padded.status_code == 403
    assert suffixed.status_code == 403


def test_empty_configured_list_entry_cannot_be_matched_by_a_client(strict_client, settings):
    """api_keys_list=',' parses to empty-string entries; an empty header is
    treated as MISSING (401), so the empty entry is unreachable."""
    settings.api_keys_list = ","

    missing = strict_client.get("/protected")
    empty = strict_client.get("/protected", headers={"X-API-Key": ""})
    junk = strict_client.get("/protected", headers={"X-API-Key": "junk"})

    assert missing.status_code == 401
    assert empty.status_code == 401
    assert junk.status_code == 403


def test_unicode_and_very_long_keys_are_denied_not_crashing(strict_client, settings):
    settings.api_keys_list = FAKE_KEY

    for weird in ["x" * 10000, "%00", "NaN", "inf", "-1", "0x00"]:
        response = strict_client.get("/protected", headers={"X-API-Key": weird})
        assert response.status_code == 403, f"{weird[:10]!r} was not denied"


# ---------------------------------------------------------------------------
# Direct coroutine paths (None handling)
# ---------------------------------------------------------------------------


async def test_validate_api_key_direct_none_denies_when_configured(settings):
    settings.api_keys_list = FAKE_KEY

    with pytest.raises(Exception) as exc_info:
        await validate_api_key(None)
    assert getattr(exc_info.value, "status_code", None) == 401


async def test_validate_api_key_direct_none_open_mode(settings):
    settings.api_keys_list = ""

    assert await validate_api_key(None) == "no-auth-required"


async def test_optional_api_key_direct_paths(settings):
    settings.api_keys_list = FAKE_KEY

    assert await optional_api_key(None) is None
    assert await optional_api_key("") is None
    assert await optional_api_key(FAKE_KEY) == FAKE_KEY
    assert await optional_api_key(FAKE_OTHER) is None


# ---------------------------------------------------------------------------
# Optional dependency over HTTP
# ---------------------------------------------------------------------------


def test_optional_dependency_over_http(optional_client, settings):
    settings.api_keys_list = FAKE_KEY

    assert optional_client.get("/maybe").json() == {"principal": None}
    assert optional_client.get("/maybe", headers={"X-API-Key": ""}).json() == {"principal": None}
    assert optional_client.get("/maybe", headers={"X-API-Key": FAKE_KEY}).json() == {"principal": FAKE_KEY}
    assert optional_client.get("/maybe", headers={"X-API-Key": FAKE_OTHER}).json() == {"principal": None}
    # Every variant answers 200 -- optional never rejects.
    assert all(
        optional_client.get("/maybe", headers=h).status_code == 200
        for h in [{}, {"X-API-Key": FAKE_KEY}, {"X-API-Key": FAKE_OTHER}]
    )


# ---------------------------------------------------------------------------
# Secret hygiene: nothing logged, nothing echoed
# ---------------------------------------------------------------------------


def test_no_secret_in_responses_or_logs(strict_client, settings, capsys):
    settings.api_keys_list = FAKE_KEY

    # Capture stdout+stderr (loguru's default sink) across accept and reject.
    strict_client.get("/protected", headers={"X-API-Key": FAKE_KEY})
    rejected = strict_client.get("/protected", headers={"X-API-Key": FAKE_OTHER})
    missing = strict_client.get("/protected")

    captured = capsys.readouterr()
    everything = captured.out + captured.err + rejected.text + missing.text

    assert FAKE_OTHER not in everything
    assert FAKE_KEY not in everything
