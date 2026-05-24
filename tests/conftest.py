from unittest.mock import Mock

import pytest


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
