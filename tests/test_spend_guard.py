"""Spend guard: the test suite must never reach paid/keyed services by accident.

The repo's ``.env`` holds real keys (a paid MiniMax key among them). Two leak
paths exist if the guard is missing:

(a) import-time ``load_dotenv()`` (``src/research/data/_fred_key.py``) exports
    real ``.env`` values into ``os.environ`` before any per-test fixture runs;
(b) ``src/core/config.py`` reads the ``.env`` **file** directly (pydantic
    ``env_file`` and ``dotenv_values`` for YAML interpolation), which deleting
    the env vars does not stop.

``tests/conftest.py`` therefore blanks (sets ``""``, which beats both file
reads and stops ``load_dotenv(override=False)``) every sensitive key at import
time, and sets ``MARKETPULSE_KEYS_ENV_ONLY=1`` so ``src.core.keys`` never
consults the ``.env`` file either.

Every assertion here is booleanized before ``assert`` so a failure can never
print a real key value.

Known limits of this guard (documented for reviewers; none are silent
un-guards):

* Running pytest with ``-p no:conftest`` bypasses the guard entirely --
  ``tests/conftest.py`` is what blanks the keys at import time.
* The per-node ``live_credentials`` marker alone does not lift the
  import-time guard: the blanking happens at conftest import, before any
  marker is consulted; the marker only matters to the fixture that decides
  whether real keys are restored for that node.
* Under ``pytest-xdist`` the worker processes may not see the
  ``--live-credentials`` argv opt-in (each worker has its own argv), so an
  opt-in can silently not propagate -- that direction only *adds* guarding
  (workers stay guarded); it never silently un-guards.
"""

from __future__ import annotations

import os
import sys

import pytest

# Imported for its side effect: its import-time ``load_dotenv()`` runs during
# collection, before any per-test fixture, so it exercises gap (a) directly.
import src.research.data._fred_key  # noqa: F401
from src.core import config as config_mod
from src.core.keys import get_macro_key

GUARDED_KEYS = [
    "MINIMAX_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "DEEPSEEK_API_KEY",
    "FRED_API_KEY",
    "EIA_API_KEY",
]

# Captured at collection time (after the load_dotenv import above): if the
# conftest guard is missing, real .env values are visible here.
_ENV_AT_IMPORT: dict[str, str] = {name: os.environ.get(name, "") for name in GUARDED_KEYS}

_LIVE_OPT_IN = (
    "--live-credentials" in sys.argv
    or os.environ.get("MARKETPULSE_USE_REAL_CREDENTIALS") == "1"
    or os.environ.get("RUN_LIVE_TESTS") == "1"
)

pytestmark = pytest.mark.skipif(
    _LIVE_OPT_IN,
    reason="spend guard is deliberately disabled for live runs "
    "(--live-credentials / MARKETPULSE_USE_REAL_CREDENTIALS=1 / RUN_LIVE_TESTS=1)",
)


def _is_unusable(value: object) -> bool:
    """True for values that cannot be a working key: empty, placeholder, or unexpanded ``${...}``."""
    if not isinstance(value, str):
        return True
    v = value.strip()
    return v == "" or v.startswith(("your_", "YOUR_", "${"))


def test_keys_are_blank_at_collection_time():
    """Gap (a): the import-time ``load_dotenv()`` must not resurrect real keys."""
    not_blank = sorted(name for name, val in _ENV_AT_IMPORT.items() if val != "")
    assert not not_blank, f"real .env values visible at import time for: {not_blank}"


def test_keys_are_blank_during_tests():
    """The per-test fixture keeps every guarded key blank."""
    not_blank = sorted(name for name in GUARDED_KEYS if os.environ.get(name, "") != "")
    assert not not_blank, f"non-blank guarded keys during test: {not_blank}"


def test_keys_module_is_env_only():
    """``src.core.keys`` must not fall through to the .env/credentials.yaml files."""
    env_only = os.environ.get("MARKETPULSE_KEYS_ENV_ONLY", "").lower() in ("1", "true", "yes")
    assert env_only


def test_get_macro_key_returns_nothing_for_fred():
    """Gap (b) for keys.py: without the guard the real .env file supplies a usable key."""
    fred_usable = bool(get_macro_key("FRED_API_KEY"))
    assert not fred_usable


def test_fresh_settings_expose_no_real_keys():
    """Gap (b) for Settings: a fresh instance must not surface real keys via the .env file."""
    config_mod._settings_instance = None
    s = config_mod.get_settings()
    candidates = {
        "llm.minimax.api_key": s.llm.minimax.api_key,
        "api_keys.minimax.api_key": s.api_keys.minimax.api_key,
        "llm.fallback.api_key (openrouter)": s.llm.fallback.api_key,
        "api_keys.openrouter.api_key": s.api_keys.openrouter.api_key,
        "llm.deepseek.api_key": s.llm.deepseek.api_key,
    }
    bad = sorted(loc for loc, v in candidates.items() if not _is_unusable(v))
    assert not bad, f"Settings exposes potentially real keys at: {bad}"


def test_settings_ignores_a_cwd_env_file(tmp_path, monkeypatch):
    """Env-beats-file proof using an obviously fake .env + credentials.yaml.

    Without the guard, ``os.environ`` has no value for these names, so the fake
    ``.env`` file wins the YAML interpolation and Settings shows the fake value.
    With the guard, the blank env var overrides the file and only the
    unexpanded ``${...}`` placeholder remains.
    """
    fake = "sk-fake-not-real"
    (tmp_path / ".env").write_text("\n".join(f"{name}={fake}" for name in GUARDED_KEYS) + "\n", encoding="utf-8")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "credentials.yaml").write_text(
        "\n".join(
            [
                "api_keys:",
                "  minimax:",
                "    api_key: ${MINIMAX_API_KEY}",
                "  openrouter:",
                "    api_key: ${OPENROUTER_API_KEY}",
                "llm:",
                "  minimax:",
                "    api_key: ${MINIMAX_API_KEY}",
                "  deepseek:",
                "    api_key: ${DEEPSEEK_API_KEY}",
                "  fallback:",
                "    api_key: ${OPENROUTER_API_KEY}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    config_mod._settings_instance = None
    s = config_mod.get_settings()
    candidates = {
        "llm.minimax.api_key": s.llm.minimax.api_key,
        "api_keys.minimax.api_key": s.api_keys.minimax.api_key,
        "llm.fallback.api_key": s.llm.fallback.api_key,
        "api_keys.openrouter.api_key": s.api_keys.openrouter.api_key,
        "llm.deepseek.api_key": s.llm.deepseek.api_key,
    }
    leaked = sorted(loc for loc, v in candidates.items() if isinstance(v, str) and fake in v)
    assert not leaked, f"values from the fake .env file leaked into Settings at: {leaked}"
    bad = sorted(loc for loc, v in candidates.items() if not _is_unusable(v))
    assert not bad, f"Settings exposes potentially real keys at: {bad}"
