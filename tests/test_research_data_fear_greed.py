"""Tests for src/research/data/fear_greed.py."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.research.data.fear_greed import FGI_CSV, fetch_fear_greed


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FAKE_API_RESPONSE = {
    "data": [
        {
            "value": "25",
            "value_classification": "Extreme Fear",
            "timestamp": "1700000000",
            "time_until_update": "12345",
        },
        {
            "value": "75",
            "value_classification": "Greed",
            "timestamp": "1700086400",
            "time_until_update": "12345",
        },
        {
            "value": "50",
            "value_classification": "Neutral",
            "timestamp": "1700172800",
            "time_until_update": "12345",
        },
    ]
}


@pytest.fixture(autouse=True)
def _tmp_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect data directory to a temp dir so we don't touch real data."""
    import src.research.data.fear_greed as fg_mod

    tmp_data = tmp_path / "data" / "btc"
    tmp_data.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(fg_mod, "DATA_DIR", tmp_data)
    monkeypatch.setattr(fg_mod, "FGI_CSV", tmp_data / "fear_greed.csv")


def _mock_response(json_body: dict, status_code: int = 200) -> MagicMock:
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_body
    mock.raise_for_status.return_value = None
    return mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFetchFearGreed:
    """Tests for fetch_fear_greed()."""

    @patch("src.research.data.fear_greed.requests.get")
    def test_fetch_creates_cache(self, mock_get):
        """Fresh fetch hits the API and writes a CSV cache."""
        mock_get.return_value = _mock_response(FAKE_API_RESPONSE)

        df = fetch_fear_greed(force=True)

        mock_get.assert_called_once()
        assert len(df) == 3
        assert list(df.columns) == ["ts", "fgi_value", "classification"]
        assert df["fgi_value"].iloc[0] == 25
        assert df["classification"].iloc[0] == "Extreme Fear"
        # Verify cache file was written (use module-patched path)
        import src.research.data.fear_greed as fg_mod

        assert fg_mod.FGI_CSV.exists()

    @patch("src.research.data.fear_greed.requests.get")
    def test_cache_returned_without_refetch(self, mock_get):
        """Second call (no force) returns cached data without hitting API."""
        # First call: populate cache
        mock_get.return_value = _mock_response(FAKE_API_RESPONSE)
        fetch_fear_greed(force=True)

        # Second call: should NOT call requests.get
        mock_get.reset_mock()
        df = fetch_fear_greed(force=False)

        mock_get.assert_not_called()
        assert len(df) == 3
        assert df["fgi_value"].iloc[1] == 75

    @patch("src.research.data.fear_greed.requests.get")
    def test_force_refetches(self, mock_get):
        """Calling with force=True hits API even when cache exists."""
        mock_get.return_value = _mock_response(FAKE_API_RESPONSE)
        fetch_fear_greed(force=True)

        mock_get.reset_mock()
        mock_get.return_value = _mock_response(FAKE_API_RESPONSE)
        df = fetch_fear_greed(force=True)

        mock_get.assert_called_once()
        assert len(df) == 3

    @patch("src.research.data.fear_greed.requests.get")
    def test_network_error_returns_empty(self, mock_get):
        """Network error with no cache returns empty DataFrame."""
        mock_get.side_effect = Exception("network down")

        df = fetch_fear_greed(force=True)

        assert df.empty
        assert list(df.columns) == ["ts", "fgi_value", "classification"]

    @patch("src.research.data.fear_greed.requests.get")
    def test_network_error_returns_stale_cache(self, mock_get):
        """Network error when cache exists returns stale cached data."""
        mock_get.return_value = _mock_response(FAKE_API_RESPONSE)
        fetch_fear_greed(force=True)

        # Now simulate network failure
        mock_get.side_effect = Exception("network down")
        df = fetch_fear_greed(force=True)

        assert len(df) == 3

    @patch("src.research.data.fear_greed.requests.get")
    def test_empty_data_list(self, mock_get):
        """API returning empty data list results in empty DataFrame."""
        mock_get.return_value = _mock_response({"data": []})

        df = fetch_fear_greed(force=True)

        assert df.empty

    @patch("src.research.data.fear_greed.requests.get")
    def test_ts_is_datetime(self, mock_get):
        """The ts column is parsed as datetime."""
        mock_get.return_value = _mock_response(FAKE_API_RESPONSE)

        df = fetch_fear_greed(force=True)

        assert pd.api.types.is_datetime64_any_dtype(df["ts"])
