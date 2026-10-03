"""Tests for on-chain data module (MVRV + Puell fetchers).

All network calls are mocked so tests run offline.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.research.data.on_chain import (
    _read_mvrv_cache,
    _read_puell_cache,
    _synthetic_mvrv,
    _synthetic_puell,
    fetch_mvrv,
    fetch_puell,
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
    monkeypatch.setattr(mod, "PUELL_CSV", tmp_path / "puell.csv")
    return tmp_path


def _mock_glassnode_response(values: list[tuple[int, float]]) -> MagicMock:
    """Build a mock requests.Response returning Glassnode-format JSON."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = [{"t": ts, "v": val} for ts, val in values]
    return mock_resp


# ---------------------------------------------------------------------------
# MVRV tests
# ---------------------------------------------------------------------------


def test_fetch_mvrv_returns_dataframe_with_columns(tmp_data_dir, monkeypatch):
    """fetch_mvrv returns a DataFrame with ts and mvrv_z columns."""
    import requests

    ts = 1700000000
    mock_resp = _mock_glassnode_response(
        [
            (ts, 1.5),
            (ts + 86400, 2.0),
        ]
    )
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

    # Pre-populate cache (legacy format: no source column, real-looking values)
    df_cache = pd.DataFrame(
        {
            "ts": [pd.Timestamp("2024-01-01")],
            "mvrv_z": [1.2],
        }
    )
    df_cache.to_csv(mod.MVRV_CSV, index=False)

    # requests.get should NOT be called
    monkeypatch.setattr(requests, "get", MagicMock(side_effect=AssertionError("should not call API")))

    df = fetch_mvrv(force=False)
    assert len(df) == 1
    assert df["mvrv_z"].iloc[0] == 1.2
    assert df["source"].iloc[0] == "real"  # legacy real file: honest provenance, never "cache"


def test_fetch_mvrv_network_error_returns_empty(tmp_data_dir, monkeypatch):
    """No key + no cache + network failure -> EMPTY frame (never synthetic).

    Contract (2026-10-03): synthetic data is available only through the
    explicit ``allow_synthetic=True`` opt-in and is never persisted.
    """
    import requests

    monkeypatch.setattr(
        requests,
        "get",
        MagicMock(side_effect=requests.ConnectionError("offline")),
    )

    df = fetch_mvrv(force=True)
    assert isinstance(df, pd.DataFrame)
    assert df.empty
    assert list(df.columns) == ["ts", "mvrv_z", "source"]
    assert not (tmp_data_dir / "mvrv.csv").exists()  # nothing laundered to disk


def test_fetch_mvrv_api_error_returns_empty(tmp_data_dir, monkeypatch):
    """When the API returns an error dict, return the empty frame."""
    import requests

    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"error": "API key missing"}
    monkeypatch.setattr(requests, "get", lambda *a, **kw: mock_resp)

    df = fetch_mvrv(force=True)
    assert df.empty
    assert list(df.columns) == ["ts", "mvrv_z", "source"]
    assert not (tmp_data_dir / "mvrv.csv").exists()


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


def test_fetch_puell_network_error_returns_empty(tmp_data_dir, monkeypatch):
    """On network failure with no cache, return the empty frame."""
    import requests

    monkeypatch.setattr(
        requests,
        "get",
        MagicMock(side_effect=requests.ConnectionError("offline")),
    )

    df = fetch_puell(force=True)
    assert isinstance(df, pd.DataFrame)
    assert df.empty
    assert list(df.columns) == ["ts", "puell", "source"]
    assert not (tmp_data_dir / "puell.csv").exists()


# ---------------------------------------------------------------------------
# Provenance contract (regression: synthetic must never be laundered as "cache")
# ---------------------------------------------------------------------------


def test_synthetic_mvrv_never_persisted_even_with_optin(tmp_data_dir, monkeypatch):
    """allow_synthetic=True returns tagged rows but NEVER writes the cache.

    This is the regression test for the laundering bug: the old code wrote
    the synthetic series to MVRV_CSV without a source column, so the next
    call served it as source="cache".
    """
    import requests

    import src.research.data.on_chain as oc

    monkeypatch.setattr(oc, "MVRV_CSV", tmp_data_dir / "mvrv.csv")
    monkeypatch.setattr(
        requests,
        "get",
        MagicMock(side_effect=requests.ConnectionError("offline")),
    )

    # Opt-in call: synthetic in memory, nothing on disk
    df1 = fetch_mvrv(force=True, allow_synthetic=True)
    assert len(df1) > 0
    assert (df1["source"] == "synthetic").all()
    assert not (tmp_data_dir / "mvrv.csv").exists()

    # Second call without the opt-in: still empty (no laundered cache to read)
    df2 = fetch_mvrv(force=False)
    assert df2.empty


def test_synthetic_puell_never_persisted_even_with_optin(tmp_data_dir, monkeypatch):
    """Same laundering regression for Puell."""
    import requests

    import src.research.data.on_chain as oc

    monkeypatch.setattr(oc, "PUELL_CSV", tmp_data_dir / "puell.csv")
    monkeypatch.setattr(
        requests,
        "get",
        MagicMock(side_effect=requests.ConnectionError("offline")),
    )

    df1 = fetch_puell(force=True, allow_synthetic=True)
    assert (df1["source"] == "synthetic").all()
    assert not (tmp_data_dir / "puell.csv").exists()

    df2 = fetch_puell(force=False)
    assert df2.empty


def test_legacy_synthetic_mvrv_file_ignored_by_default(tmp_data_dir, monkeypatch):
    """Follow-up contract: by default a legacy laundered (all-synthetic)
    file is IGNORED — empty frame, loud log — not merely served tagged.
    Fails on the branch tip that only tagged the rows."""
    import src.research.data.on_chain as oc

    legacy = oc._synthetic_mvrv(500)
    legacy.to_csv(oc.MVRV_CSV, index=False)  # no source column — legacy format

    df = fetch_mvrv(force=False)
    assert df.empty
    assert list(df.columns) == ["ts", "mvrv_z", "source"]
    assert oc.MVRV_CSV.exists()  # the owner's file is left in place


def test_legacy_synthetic_mvrv_file_optin_returns_tagged(tmp_data_dir, monkeypatch):
    """Same legacy file with allow_synthetic=True: rows are served tagged."""
    import src.research.data.on_chain as oc

    legacy = oc._synthetic_mvrv(500)
    legacy.to_csv(oc.MVRV_CSV, index=False)

    df = fetch_mvrv(force=False, allow_synthetic=True)
    assert len(df) == 500
    assert (df["source"] == "synthetic").all()


def test_legacy_synthetic_puell_file_ignored_by_default(tmp_data_dir, monkeypatch):
    """Puell follow-up contract: all-synthetic legacy file ignored by default."""
    import src.research.data.on_chain as oc

    legacy = oc._synthetic_puell(400)
    legacy.to_csv(oc.PUELL_CSV, index=False)

    df = fetch_puell(force=False)
    assert df.empty
    assert list(df.columns) == ["ts", "puell", "source"]
    assert oc.PUELL_CSV.exists()


def test_legacy_synthetic_puell_file_optin_returns_tagged(tmp_data_dir, monkeypatch):
    """Same legacy Puell file with allow_synthetic=True: served tagged."""
    import src.research.data.on_chain as oc

    legacy = oc._synthetic_puell(400)
    legacy.to_csv(oc.PUELL_CSV, index=False)

    df = fetch_puell(force=False, allow_synthetic=True)
    assert len(df) == 400
    assert (df["source"] == "synthetic").all()


def test_mixed_cache_real_rows_kept_synthetic_dropped_by_default(tmp_data_dir, monkeypatch):
    """A cache mixing real and synthetic rows keeps only the real ones by
    default (synthetic dropped, loudly), and everything with the opt-in."""
    import src.research.data.on_chain as oc

    mixed = pd.DataFrame(
        {
            "ts": [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-02")],
            "mvrv_z": [1.0, 2.0],
            "source": ["real", "synthetic"],
        }
    )
    mixed.to_csv(oc.MVRV_CSV, index=False)

    df = fetch_mvrv(force=False)
    assert len(df) == 1
    assert df["mvrv_z"].iloc[0] == 1.0
    assert (df["source"] == "real").all()

    df_optin = fetch_mvrv(force=False, allow_synthetic=True)
    assert len(df_optin) == 2


def test_legacy_real_mvrv_file_served_as_real(tmp_data_dir, monkeypatch):
    """A legacy file with values that do NOT match the generator is real data
    (best-effort: written before the source column existed)."""
    import src.research.data.on_chain as oc

    legacy = pd.DataFrame(
        {
            "ts": pd.date_range("2024-01-01", periods=50, freq="D"),
            "mvrv_z": [0.5 + 0.01 * i for i in range(50)],
        }
    )
    legacy.to_csv(oc.MVRV_CSV, index=False)

    df = fetch_mvrv(force=False)
    assert len(df) == 50
    assert (df["source"] == "real").all()


def test_real_fetch_roundtrip_preserves_source(tmp_data_dir, monkeypatch):
    """Provenance survives a disk round trip: a real fetch persists
    source="real" and the next call serves those rows still tagged real."""
    import requests

    import src.research.data.on_chain as oc

    ts = 1_700_000_000
    mock_resp = _mock_glassnode_response([(ts, 1.5), (ts + 86_400, 2.0)])
    monkeypatch.setattr(requests, "get", lambda *a, **kw: mock_resp)

    df1 = fetch_mvrv(force=True)
    assert (df1["source"] == "real").all()

    on_disk = pd.read_csv(oc.MVRV_CSV)
    assert "source" in on_disk.columns  # persisted provenance

    monkeypatch.setattr(requests, "get", MagicMock(side_effect=requests.ConnectionError("offline")))
    df2 = fetch_mvrv(force=False)
    assert len(df2) == 2
    assert (df2["source"] == "real").all()  # NOT relabelled "cache"


# ---------------------------------------------------------------------------
# IndicatorProvider integration: synthetic rows must not feed backtests
# ---------------------------------------------------------------------------


def _indicator_df() -> pd.DataFrame:
    import numpy as np

    return pd.DataFrame({"close": np.linspace(100.0, 200.0, 250)})


def test_indicator_lookup_skips_synthetic_rows(monkeypatch):
    """mvrv_lookup must contain only real-provenance dates."""
    from src.research.backtest.indicators import IndicatorProvider

    mixed = pd.DataFrame(
        {
            "ts": [
                pd.Timestamp("2024-01-01"),
                pd.Timestamp("2024-01-02"),
                pd.Timestamp("2024-01-03"),
                pd.Timestamp("2024-01-04"),
            ],
            "mvrv_z": [1.0, 2.0, 3.0, 4.0],
            "source": ["real", "synthetic", "synthetic", "real"],
        }
    )
    monkeypatch.setattr("src.research.data.on_chain.fetch_mvrv", lambda: mixed)

    result = IndicatorProvider().compute(_indicator_df())
    assert set(result["mvrv_lookup"]) == {"2024-01-01", "2024-01-04"}
    assert result["mvrv_lookup"]["2024-01-01"] == 1.0
    assert result["mvrv_lookup"]["2024-01-04"] == 4.0


def test_indicator_lookup_all_synthetic_is_empty_and_logs(monkeypatch):
    """A fully synthetic series produces an EMPTY lookup and one loud log."""
    from loguru import logger

    from src.research.backtest.indicators import IndicatorProvider

    synthetic = pd.DataFrame(
        {
            "ts": pd.date_range("2024-01-01", periods=10, freq="D"),
            "mvrv_z": [1.0] * 10,
            "source": ["synthetic"] * 10,
        }
    )
    monkeypatch.setattr("src.research.data.on_chain.fetch_mvrv", lambda: synthetic)

    messages: list[str] = []
    sink = logger.add(lambda m: messages.append(str(m)))
    try:
        result = IndicatorProvider().compute(_indicator_df())
    finally:
        logger.remove(sink)

    assert result["mvrv_lookup"] == {}
    assert any("synthetic" in m and "MVRV" in m for m in messages)


def test_indicator_lookup_without_source_column_kept(monkeypatch):
    """Backward compatibility: rows with no source column (legacy mocks,
    hand-built frames) are treated as real, not dropped."""
    from src.research.backtest.indicators import IndicatorProvider

    no_source = pd.DataFrame(
        {
            "ts": [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-02")],
            "mvrv_z": [1.5, 2.0],
        }
    )
    monkeypatch.setattr("src.research.data.on_chain.fetch_mvrv", lambda: no_source)

    result = IndicatorProvider().compute(_indicator_df())
    assert set(result["mvrv_lookup"]) == {"2024-01-01", "2024-01-02"}


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
