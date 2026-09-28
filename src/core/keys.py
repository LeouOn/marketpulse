"""Resolve third-party data-API keys (FRED, EIA, ...) with one documented precedence.

Lookup order for ``get_macro_key("FRED_API_KEY")``:

1. the process environment (``FRED_API_KEY``)
2. ``.env`` then ``config/.env`` (later file wins, like ``Settings``) -- read with
   ``dotenv_values``, so ``os.environ`` is **not** modified
3. ``config/credentials.yaml`` under ``macro_data:`` (``FRED_API_KEY`` -> ``fred_api_key``)

Empty values and obvious placeholders (``your_key_here``, an unresolved ``${...}``) are skipped, so
a placeholder in a higher-priority source never hides a real key below it.

Set ``MARKETPULSE_KEYS_ENV_ONLY=1`` to consult only the process environment. Tests use it so
"missing key" assertions do not pick up a developer's real ``.env``/``credentials.yaml``.

Paths are relative to the working directory, matching ``src/core/config.py``.
"""

import os
import re
from collections.abc import Sequence
from pathlib import Path

import yaml
from dotenv import dotenv_values

ENV_ONLY_SWITCH = "MARKETPULSE_KEYS_ENV_ONLY"

DEFAULT_ENV_FILES: tuple[str, ...] = (".env", "config/.env")
DEFAULT_YAML_PATH = "config/credentials.yaml"

REGISTER_URLS: dict[str, str] = {
    "FRED_API_KEY": "https://fredaccount.stlouisfed.org/apikeys",
    "EIA_API_KEY": "https://www.eia.gov/opendata/register",
}

_PLACEHOLDER = re.compile(r"^(your_|\$\{)", re.IGNORECASE)


def _usable(value: object) -> str | None:
    """Return the stripped string, or ``None`` for empty/placeholder values."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or _PLACEHOLDER.match(value):
        return None
    return value


def _from_env_files(name: str, env_files: Sequence[str | Path]) -> str | None:
    found: str | None = None
    for env_file in env_files:  # later files override earlier ones
        path = Path(env_file)
        if path.is_file():
            value = _usable(dotenv_values(path).get(name))
            if value:
                found = value
    return found


def _from_yaml(name: str, yaml_path: str | Path) -> str | None:
    path = Path(yaml_path)
    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return None
    macro = data.get("macro_data") if isinstance(data, dict) else None
    if not isinstance(macro, dict):
        return None
    return _usable(macro.get(name.lower()))


def get_macro_key(
    name: str,
    *,
    env_files: Sequence[str | Path] = DEFAULT_ENV_FILES,
    yaml_path: str | Path = DEFAULT_YAML_PATH,
) -> str | None:
    """Return the key for ``name`` (for example ``"FRED_API_KEY"``), or ``None`` if not configured."""
    value = _usable(os.environ.get(name))
    if value:
        return value
    if os.environ.get(ENV_ONLY_SWITCH, "").lower() in ("1", "true", "yes"):
        return None
    return _from_env_files(name, env_files) or _from_yaml(name, yaml_path)


def require_macro_key(name: str, register_url: str | None = None) -> str:
    """Like :func:`get_macro_key` but raise ``RuntimeError`` with setup instructions when missing."""
    key = get_macro_key(name)
    if key:
        return key
    url = register_url or REGISTER_URLS.get(name, "the provider's website")
    raise RuntimeError(
        f"{name} not set. Register free at {url}. "
        f"Set it in the environment, in .env, or in config/credentials.yaml (macro_data.{name.lower()})."
    )
