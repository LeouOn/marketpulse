"""src.core.keys: one precedence for FRED/EIA keys (env > .env > config/credentials.yaml)."""

import os
from pathlib import Path

import pytest

from src.core.keys import ENV_ONLY_SWITCH, get_macro_key, require_macro_key

NAME = "FRED_API_KEY"


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Start from no key anywhere and run in an empty working directory.

    Other modules call ``load_dotenv()`` at import time, which exports the developer's real
    ``.env`` into ``os.environ``, so every key name used below must be cleared, not just one.
    """
    for var in (NAME, "EIA_API_KEY", ENV_ONLY_SWITCH):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)


def _write_env(path: Path, value: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{NAME}={value}\n", encoding="utf-8")
    return path


def _write_yaml(path: Path, value: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"macro_data:\n  fred_api_key: {value}\n  eia_api_key: eia-yaml\n", encoding="utf-8")
    return path


def test_env_var_beats_dotenv_and_yaml(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(NAME, "from-env")
    env = _write_env(tmp_path / ".env", "from-dotenv")
    yml = _write_yaml(tmp_path / "creds.yaml", "from-yaml")
    assert get_macro_key(NAME, env_files=[env], yaml_path=yml) == "from-env"


def test_dotenv_beats_yaml(tmp_path: Path) -> None:
    env = _write_env(tmp_path / ".env", "from-dotenv")
    yml = _write_yaml(tmp_path / "creds.yaml", "from-yaml")
    assert get_macro_key(NAME, env_files=[env], yaml_path=yml) == "from-dotenv"


def test_later_env_file_wins(tmp_path: Path) -> None:
    first = _write_env(tmp_path / ".env", "root")
    second = _write_env(tmp_path / "config" / ".env", "config-dir")
    assert get_macro_key(NAME, env_files=[first, second], yaml_path=tmp_path / "none.yaml") == "config-dir"


def test_yaml_only_and_name_mapping(tmp_path: Path) -> None:
    yml = _write_yaml(tmp_path / "creds.yaml", "from-yaml")
    assert get_macro_key(NAME, env_files=[], yaml_path=yml) == "from-yaml"
    assert get_macro_key("EIA_API_KEY", env_files=[], yaml_path=yml) == "eia-yaml"


def test_dotenv_key_is_found_without_exporting_it(tmp_path: Path) -> None:
    """The bug this fixes: a key that exists only in .env must be found, and os.environ stays untouched."""
    env = _write_env(tmp_path / ".env", "only-in-dotenv")
    assert get_macro_key(NAME, env_files=[env], yaml_path=tmp_path / "none.yaml") == "only-in-dotenv"
    assert NAME not in os.environ


def test_default_paths_are_relative_to_the_working_directory(tmp_path: Path) -> None:
    _write_env(tmp_path / ".env", "cwd-dotenv")
    assert get_macro_key(NAME) == "cwd-dotenv"


@pytest.mark.parametrize("placeholder", ["", "   ", "your_key_here", "YOUR_FRED_API_KEY", "${api_keys:fred}"])
def test_placeholders_are_skipped_and_fall_through(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, placeholder: str
) -> None:
    monkeypatch.setenv(NAME, placeholder)
    env = _write_env(tmp_path / ".env", placeholder)
    yml = _write_yaml(tmp_path / "creds.yaml", "real-yaml-key")
    assert get_macro_key(NAME, env_files=[env], yaml_path=yml) == "real-yaml-key"


def test_missing_key_returns_none_and_require_raises_with_instructions(tmp_path: Path) -> None:
    assert get_macro_key(NAME, env_files=[], yaml_path=tmp_path / "none.yaml") is None
    with pytest.raises(RuntimeError) as exc:
        require_macro_key(NAME)
    message = str(exc.value)
    assert "FRED_API_KEY not set" in message
    assert "https://fredaccount.stlouisfed.org/apikeys" in message
    assert "macro_data.fred_api_key" in message


def test_require_uses_the_eia_registration_url() -> None:
    with pytest.raises(RuntimeError, match="eia.gov/opendata/register"):
        require_macro_key("EIA_API_KEY")


def test_env_only_switch_ignores_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write_env(tmp_path / ".env", "from-dotenv")
    _write_yaml(tmp_path / "config" / "credentials.yaml", "from-yaml")
    assert get_macro_key(NAME) == "from-dotenv"  # default paths, files consulted

    monkeypatch.setenv(ENV_ONLY_SWITCH, "1")
    assert get_macro_key(NAME) is None  # files ignored
    monkeypatch.setenv(NAME, "from-env")
    assert get_macro_key(NAME) == "from-env"  # the environment still works


def test_malformed_yaml_is_ignored(tmp_path: Path) -> None:
    bad = tmp_path / "creds.yaml"
    bad.write_text("macro_data: [unclosed", encoding="utf-8")
    assert get_macro_key(NAME, env_files=[], yaml_path=bad) is None


def test_yield_curve_fetcher_sees_a_dotenv_only_key(tmp_path: Path) -> None:
    """Regression: fetcher._require_key used os.getenv and never saw the key in .env."""
    from src.yield_curve.fetcher import _require_key

    _write_env(tmp_path / ".env", "fetcher-dotenv-key")
    assert _require_key() == "fetcher-dotenv-key"
