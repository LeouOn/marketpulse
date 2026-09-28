import os
from pathlib import Path
from unittest.mock import Mock

import pytest

# ---------------------------------------------------------------------------
# E2E smoke-test opt-in (W5 T25, Metis SC6)
# ---------------------------------------------------------------------------
#
# E2E tests require BOTH the FastAPI backend (default http://localhost:8000)
# AND the Next.js frontend (default http://localhost:3000) to be running.
# They are skipped by default; opt in via EITHER:
#   - CLI flag:   `pytest --run-e2e`
#   - Env var:    `RUN_E2E=1 pytest ...`
#
# The hook below attaches a skip marker to every `@pytest.mark.e2e` test
# unless one of those opt-ins is active. Non-e2e tests are untouched.


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "real_data_paths: skip the autouse redirect of src.research.data path constants "
        "(for tests that verify the real cache layout and isolate themselves via chdir(tmp_path))",
    )


def pytest_addoption(parser):
    parser.addoption(
        "--run-e2e",
        action="store_true",
        default=False,
        help="Run end-to-end smoke tests (requires API + frontend servers running)",
    )
    parser.addoption(
        "--live-credentials",
        action="store_true",
        default=False,
        help="Allow tests to load real credentials.yaml / private API keys",
    )


def _e2e_enabled(config) -> bool:
    """True iff the user opted into e2e via --run-e2e flag OR RUN_E2E=1 env."""
    if config.getoption("--run-e2e", default=False):
        return True
    return os.getenv("RUN_E2E", "") == "1"


def pytest_collection_modifyitems(config, items):
    """Skip `@pytest.mark.e2e` tests unless --run-e2e or RUN_E2E=1."""
    if _e2e_enabled(config):
        return
    skip_e2e = pytest.mark.skip(
        reason="End-to-end smoke test; run with --run-e2e or RUN_E2E=1 (requires API + frontend servers running)",
    )
    for item in items:
        if "e2e" in item.keywords:
            item.add_marker(skip_e2e)


# ---------------------------------------------------------------------------
# Tracked file dirtiness check at session finish (T9 hermetic guard)
# ---------------------------------------------------------------------------

_INITIAL_TRACKED_STATUS: str = ""


def pytest_sessionstart(session):
    global _INITIAL_TRACKED_STATUS
    import subprocess

    try:
        res = subprocess.run(
            ["git", "status", "--porcelain", "-uno"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        _INITIAL_TRACKED_STATUS = res.stdout.strip()
    except Exception:
        _INITIAL_TRACKED_STATUS = ""


def pytest_sessionfinish(session, exitstatus):
    import subprocess
    import sys
    import warnings

    try:
        res = subprocess.run(
            ["git", "status", "--porcelain", "-uno"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        current = res.stdout.strip()
        if current != _INITIAL_TRACKED_STATUS:
            msg = (
                f"\n[DIRTY TREE GUARD] Tracked files were modified during the test session!\n"
                f"Status diff:\n{current}\n"
            )
            warnings.warn(msg, UserWarning)
            sys.stderr.write(msg)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Autouse hermetic test isolation fixture (T9)
# ---------------------------------------------------------------------------

# Resolved so that a worktree's symlinked config/credentials.yaml maps to the owner's real file.
_REAL_CREDENTIALS = (Path(__file__).resolve().parent.parent / "config" / "credentials.yaml").resolve()

_SENSITIVE_ENV_KEYS = [
    "OPENROUTER_API_KEY",
    "MINIMAX_API_KEY",
    "DEEPSEEK_API_KEY",
    "ANTHROPIC_API_KEY",
    "FRED_API_KEY",
    "EIA_API_KEY",
    "ALPACA_KEY_ID",
    "ALPACA_SECRET_KEY",
    "COINBASE_API_KEY",
    "COINBASE_API_SECRET",
    "RITHMIC_USERNAME",
    "RITHMIC_PASSWORD",
]


@pytest.fixture(autouse=True)
def isolate_test_environment(monkeypatch, tmp_path, request):
    """Ensure every test runs in an isolated hermetic environment.

    1. Points research reports and on-chain cache files to tmp_path.
    2. Copies daily.csv into tmp_path so existing reads succeed but writes stay isolated.
    3. Prevents loading private credentials.yaml and sensitive env vars unless opted in.
    """
    import shutil
    from pathlib import Path

    # 1. Isolate research reports directory
    tmp_reports = tmp_path / "reports"
    tmp_reports.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("src.research.tools.REPORTS_DIR", tmp_reports, raising=False)

    # 2. Isolate research data directory and caches (unless the test verifies the real path
    #    constants itself, e.g. the cache-layout tests, which isolate via chdir(tmp_path))
    if request.node.get_closest_marker("real_data_paths") is None:
        tmp_data_dir = tmp_path / "data_btc"
        tmp_data_dir.mkdir(parents=True, exist_ok=True)

        tracked_daily = Path("data/btc/daily.csv")
        if tracked_daily.exists():
            shutil.copy(tracked_daily, tmp_data_dir / "daily.csv")

        monkeypatch.setattr("src.research.data.DATA_DIR", tmp_data_dir, raising=False)
        monkeypatch.setattr("src.research.data.DAILY_CSV", tmp_data_dir / "daily.csv", raising=False)
        monkeypatch.setattr("src.research.data.HOURLY_CSV", tmp_data_dir / "hourly.csv", raising=False)

        monkeypatch.setattr("src.research.data.on_chain.DATA_DIR", tmp_data_dir, raising=False)
        monkeypatch.setattr("src.research.data.on_chain.MVRV_CSV", tmp_data_dir / "mvrv.csv", raising=False)
        monkeypatch.setattr("src.research.data.on_chain.PUELL_CSV", tmp_data_dir / "puell.csv", raising=False)

    # 3. Neutralize real credentials unless explicitly opted in
    allow_real_keys = (
        request.config.getoption("--live-credentials", default=False)
        or os.getenv("MARKETPULSE_USE_REAL_CREDENTIALS") == "1"
        or request.node.get_closest_marker("live_credentials") is not None
    )

    if not allow_real_keys:
        # Strip live API keys from environment
        for key in _SENSITIVE_ENV_KEYS:
            monkeypatch.delenv(key, raising=False)

        # Force Settings to load credentials.example.yaml rather than developer credentials.yaml.
        # Only the developer's real file is hidden: a test that chdir()s into tmp_path and writes its
        # own config/credentials.yaml must still see it, so compare resolved locations, not names.
        real_exists = Path.exists
        real_credentials = _REAL_CREDENTIALS

        def _isolated_path_exists(path_self):
            try:
                if Path(path_self).resolve() == real_credentials:
                    return False
            except OSError:
                pass
            return real_exists(path_self)

        monkeypatch.setattr(Path, "exists", _isolated_path_exists)

    # Reset cached singleton settings at end of test to prevent cross-contamination
    yield

    try:
        from src.core import config as config_mod

        config_mod._settings_instance = None
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Existing fixtures (preserved verbatim)
# ---------------------------------------------------------------------------


class MockSettings:
    def __init__(self):
        self.database_url = "sqlite:///:memory:"

        self.api_keys = Mock()
        self.api_keys.alpaca = Mock()
        self.api_keys.alpaca.key_id = "test_key"
        self.api_keys.alpaca.secret_key = "test_secret"
        self.api_keys.alpaca.base_url = "https://paper-api.alpaca.markets"

        self.api_keys.rithmic = Mock()
        self.api_keys.rithmic.username = "test_user"
        self.api_keys.rithmic.password = "test_pass"

        self.api_keys.coinbase = Mock()
        self.api_keys.coinbase.api_key = "test_cb_key"
        self.api_keys.coinbase.api_secret = "test_cb_secret"

        self.api_keys.openrouter = Mock()
        self.api_keys.openrouter.api_key = "test_or_key"

        self.llm = Mock()
        self.llm.primary = Mock()
        self.llm.primary.base_url = "http://localhost:1234/v1"
        self.llm.primary.api_key = "not-needed"
        self.llm.primary.timeout = 30

        self.llm.fallback = Mock()
        self.llm.fallback.base_url = "https://openrouter.ai/api/v1"
        self.llm.fallback.api_key = "test_fallback"
        self.llm.fallback.timeout = 60

        self.nq_symbol = "NQ=F"
        self.btc_symbol = "BTC-USD"
        self.eth_symbol = "ETH-USD"

        self.internals_interval = 60
        self.llm_analysis_interval = 300


@pytest.fixture
def mock_settings():
    return MockSettings()


@pytest.fixture
def mock_internals_data():
    return {
        "spy": {
            "price": 450.25,
            "change": 1.25,
            "change_pct": 0.28,
            "volume": 50000000,
            "timestamp": "2025-11-02T21:00:00Z",
        },
        "qqq": {
            "price": 180.50,
            "change": 2.15,
            "change_pct": 1.21,
            "volume": 30000000,
            "timestamp": "2025-11-02T21:00:00Z",
        },
        "vix": {
            "price": 18.50,
            "change": -0.50,
            "change_pct": -2.63,
            "volume": 1000000,
            "timestamp": "2025-11-02T21:00:00Z",
        },
        "volume_flow": {"total_volume_60min": 85000000, "symbols_tracked": 3, "timestamp": "2025-11-02T21:00:00Z"},
    }
