"""Tests for on-chain data module (MVRV + Puell fetchers).

All network calls are mocked so tests run offline.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.research.data.on_chain import (
    MVRV_CSV,
    PELL_CSV,
    fetch_mvrv,
    fetch_puell,
    _read_mvrv_cache,
    _read_puell_cache,
    _synthetic_mvrv,
    _synthetic_puell,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch):
    """Redirect data paths to temp dir so tests don't touch real data/btc."""
    import src.research.data.on_chain as mod
    monkeypatch.setattr(mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(mod, "MVRV_CSV", tmp_path / "mvrv.csv")
    monkeypatch.setattr(mod, "PELL_CSV", tmp_path / "puell.csv")
    return tmp_path


def _mock_glassnode_response(values: list[tuple[int, float]]) -> MagicMock:
    """Build a mock requests.Response returning Glassnode-format JSON."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = [
        {"t": ts, "v": val} for ts, val in values
    ]
    return mock_resp


# ---------------------------------------------------------------------------
# MVRV tests
# ---------------------------------------------------------------------------


def test_fetch_mvrv_returns_dataframe_with_columns(tmp_data_dir, monkeypatch):
    """fetch_mvrv returns a DataFrame with ts and mvrv_z columns."""
    import requests
    ts = 1700000000
    mock_resp = _mock_glassnode_response([
        (ts, 1.5),
        (ts + 86400, 2.0),
    ])
    monkeypatch.setattr(requests, "get", lambda *a, **kw: mock_resp)

    df = fetch_mvrv(force=True)
    assert isinstance(df, pd.DataFrame)
    assert "ts" in df.columns
    assert "mvrv_z" in df.columns
    assert len(df) == 2


def test_fetch_mvrv_creates_csv_cache(tmp_data_dir, monkeypatch):
    """fetch_mvrv writes a CSV cache file on successful fetch."""
    import requests
    ts = 1700000000
    mock_resp = _mock_glassnode_response([(ts, 1.5)])
    monkeypatch.setattr(requests, "get", lambda *a, **kw: mock_resp)

    fetch_mvrv(force=True)
    assert (tmp_data_dir / "mvrv.csv").exists()


def test_fetch_mvrv_returns_cached_when_available(tmp_data_dir, monkeypatch):
    """When cache exists and force=False, return cached data without API call."""
    import requests
    import src.research.data.on_chain as mod

    # Pre-populate cache
    df_cache = pd.DataFrame({
        "ts": [pd.Timestamp("2024-01-01")],
        "mvrv_z": [1.2],
    })
    df_cache.to_csv(mod.MVRV_CSV, index=False)

    # requests.get should NOT be called
    monkeypatch.setattr(requests, "get", MagicMock(side_effect=AssertionError("should not call API")))

    df = fetch_mvrv(force=False)
    assert len(df) == 1
    assert df["mvrv_z"].iloc[0] == 1.2


def test_fetch_mvrv_network_error_returns_synthetic(tmp_data_dir, monkeypatch):
    """On network failure with no cache, return synthetic fallback (not crash)."""
    import requests
    monkeypatch.setattr(
        requests, "get",
        MagicMock(side_effect=requests.ConnectionError("offline")),
    )

    df = fetch_mvrv(force=True)
    assert isinstance(df, pd.DataFrame)
    assert "ts" in df.columns
    assert "mvrv_z" in df.columns
    assert len(df) > 0  # synthetic has 2500 rows


def test_fetch_mvrv_api_error_returns_synthetic(tmp_data_dir, monkeypatch):
    """When API returns an error dict, fall back to synthetic."""
    import requests
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"error": "API key missing"}
    monkeypatch.setattr(requests, "get", lambda *a, **kw: mock_resp)

    df = fetch_mvrv(force=True)
    assert isinstance(df, pd.DataFrame)
    assert "mvrv_z" in df.columns


# ---------------------------------------------------------------------------
# Puell tests
# ---------------------------------------------------------------------------


def test_fetch_puell_creates_csv_cache(tmp_data_dir, monkeypatch):
    """fetch_puell writes a CSV cache file on successful fetch."""
    import requests
    ts = 1700000000
    mock_resp = _mock_glassnode_response([(ts, 1.1)])
    monkeypatch.setattr(requests, "get", lambda *a, **kw: mock_resp)

    fetch_puell(force=True)
    assert (tmp_data_dir / "puell.csv").exists()


def test_fetch_puell_network_error_returns_synthetic(tmp_data_dir, monkeypatch):
    """On network failure with no cache, return synthetic fallback."""
    import requests
    monkeypatch.setattr(
        requests, "get",
        MagicMock(side_effect=requests.ConnectionError("offline")),
    )

    df = fetch_puell(force=True)
    assert isinstance(df, pd.DataFrame)
    assert "puell" in df.columns
    assert len(df) > 0


# ---------------------------------------------------------------------------
# Corrupt cache recovery
# ---------------------------------------------------------------------------


def test_corrupt_mvrv_cache_returns_empty(tmp_path):
    """A corrupt MVRV CSV should return empty DataFrame, not crash."""
    corrupt = tmp_path / "mvrv.csv"
    corrupt.write_text("NOT,VALID,CSV\n\x00\x01\x02")

    df = _read_mvrv_cache(corrupt)
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_corrupt_puell_cache_returns_empty(tmp_path):
    """A corrupt Puell CSV should return empty DataFrame, not crash."""
    corrupt = tmp_path / "puell.csv"
    corrupt.write_text("bad data\n")

    df = _read_puell_cache(corrupt)
    assert isinstance(df, pd.DataFrame)
    assert df.empty


# ---------------------------------------------------------------------------
# Synthetic generators
# ---------------------------------------------------------------------------


def test_synthetic_mvrv_has_expected_shape():
    df = _synthetic_mvrv(100)
    assert len(df) == 100
    assert "ts" in df.columns
    assert "mvrv_z" in df.columns


def test_synthetic_puell_has_expected_shape():
    df = _synthetic_puell(100)
    assert len(df) == 100
    assert "ts" in df.columns
    assert "puell" in df.columns
