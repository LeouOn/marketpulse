import os
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


def pytest_addoption(parser):
    parser.addoption(
        "--run-e2e",
        action="store_true",
        default=False,
        help="Run end-to-end smoke tests (requires API + frontend servers running)",
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
