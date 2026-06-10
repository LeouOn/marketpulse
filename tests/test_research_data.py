"""Tests for the BTC data pipeline (without making real network calls).

Network-dependent fetchers are mocked so these tests run offline.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.research import data as data_mod
from src.research.data import (
    DAILY_CSV,
    HOURLY_CSV,
    _max_drawdown,
    _merge,
    data_summary,
    load_daily,
    load_hourly,
    update_cache,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch):
    """Redirect DATA_DIR to a temp dir so tests don't touch real data/btc."""
    monkeypatch.setattr(data_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(data_mod, "DAILY_CSV", tmp_path / "daily.csv")
    monkeypatch.setattr(data_mod, "HOURLY_CSV", tmp_path / "hourly.csv")
    return tmp_path


@pytest.fixture
def sample_daily() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts": pd.to_datetime(
                ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]
            ),
            "open": [42000.0, 42500.0, 43000.0, 42800.0],
            "high": [42600.0, 43200.0, 43500.0, 43100.0],
            "low": [41800.0, 42400.0, 42700.0, 42500.0],
            "close": [42500.0, 43000.0, 42800.0, 43050.0],
            "volume": [1000.0, 1100.0, 1200.0, 1150.0],
            "source": "yahoo",
        }
    )


# ---------------------------------------------------------------------------
# Cache merge helper
# ---------------------------------------------------------------------------


def test_merge_preserves_dedup_and_sort():
    new = pd.DataFrame(
        {
            "ts": pd.to_datetime(["2024-01-03", "2024-01-05"]),
            "open": [43000.0, 43300.0],
            "high": [43500.0, 43600.0],
            "low": [42700.0, 43200.0],
            "close": [42800.0, 43400.0],
            "volume": [1200.0, 1250.0],
            "source": "yahoo",
        }
    )
    existing = pd.DataFrame(
        {
            "ts": pd.to_datetime(["2024-01-01", "2024-01-03", "2024-01-04"]),
            "open": [42000.0, 43000.0, 42800.0],
            "high": [42600.0, 43500.0, 43100.0],
            "low": [41800.0, 42700.0, 42500.0],
            "close": [42500.0, 42800.0, 43050.0],
            "volume": [1000.0, 1200.0, 1150.0],
            "source": "yahoo",
        }
    )
    merged = _merge(new, existing)
    assert len(merged) == 4  # 2024-01-03 is deduped
    assert list(merged["ts"]) == sorted(merged["ts"].tolist())
    # The new row for 2024-01-05 should be present
    assert (merged["ts"] == pd.Timestamp("2024-01-05")).any()
    # The 2024-01-03 row from "new" (the last write) should win
    assert merged.loc[merged["ts"] == pd.Timestamp("2024-01-03"), "close"].iloc[0] == 42800.0


def test_merge_with_empty_existing_returns_new():
    new = pd.DataFrame({"ts": pd.to_datetime(["2024-01-01"]), "close": [1.0]})
    out = _merge(new, pd.DataFrame())
    assert len(out) == 1


def test_merge_with_empty_new_returns_existing():
    existing = pd.DataFrame({"ts": pd.to_datetime(["2024-01-01"]), "close": [1.0]})
    out = _merge(pd.DataFrame(), existing)
    assert len(out) == 1


# ---------------------------------------------------------------------------
# data_summary
# ---------------------------------------------------------------------------


def test_data_summary_on_flat_series_is_zero():
    df = pd.DataFrame(
        {
            "ts": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
            "close": [100.0, 100.0, 100.0],
        }
    )
    summary = data_summary(df)
    assert summary["rows"] == 3
    assert summary["total_return_pct"] == 0.0
    assert summary["realized_vol_annual_pct"] == 0.0
    assert summary["max_drawdown_pct"] == 0.0


def test_data_summary_on_growing_series(sample_daily):
    summary = data_summary(sample_daily)
    assert summary["rows"] == 4
    assert summary["first_close"] == 42500.0
    assert summary["last_close"] == 43050.0
    # total return = 43050/42500 - 1 = ~1.29%
    assert 1.0 < summary["total_return_pct"] < 2.0
    # CAGR over 3 days should be a huge annualized number (short window)
    assert summary["cagr_pct"] > 0


def test_data_summary_on_empty():
    assert data_summary(pd.DataFrame()) == {"rows": 0}


# ---------------------------------------------------------------------------
# max_drawdown helper
# ---------------------------------------------------------------------------


def test_max_drawdown_known_series():
    # 100 -> 50 -> 75 -> 60 -> 100
    s = pd.Series([100.0, 50.0, 75.0, 60.0, 100.0])
    # Drawdown of -50% at the trough
    assert _max_drawdown(s) == pytest.approx(-0.5, abs=1e-9)


def test_max_drawdown_no_drawdown():
    s = pd.Series([100.0, 110.0, 120.0, 130.0])
    assert _max_drawdown(s) == 0.0


def test_max_drawdown_empty():
    assert _max_drawdown(pd.Series([], dtype=float)) == 0.0


# ---------------------------------------------------------------------------
# Cache loaders (offline)
# ---------------------------------------------------------------------------


def test_load_daily_returns_cache_when_present(tmp_data_dir, sample_daily, monkeypatch):
    """If the cache exists and is fresh, load_daily should not call Yahoo."""
    sample_daily.to_csv(tmp_data_dir / "daily.csv", index=False)

    def _boom(*_a, **_k):
        raise RuntimeError("network should not be called when cache is fresh")

    monkeypatch.setattr(data_mod, "fetch_daily_yahoo", _boom)
    out = load_daily()
    assert len(out) == 4
    assert out["close"].iloc[-1] == 43050.0


def test_load_daily_fetches_when_no_cache(tmp_data_dir, sample_daily, monkeypatch):
    """If no cache exists, the loader must call fetch_daily_yahoo."""
    monkeypatch.setattr(data_mod, "fetch_daily_yahoo", lambda: sample_daily)
    out = load_daily()
    assert (tmp_data_dir / "daily.csv").exists()
    assert len(out) == 4


def test_load_daily_filters_by_start_end(tmp_data_dir, sample_daily, monkeypatch):
    sample_daily.to_csv(tmp_data_dir / "daily.csv", index=False)
    monkeypatch.setattr(data_mod, "fetch_daily_yahoo", lambda: sample_daily)
    out = load_daily(start="2024-01-02", end="2024-01-03")
    assert len(out) == 2
    assert out["ts"].iloc[0] == pd.Timestamp("2024-01-02")
    assert out["ts"].iloc[-1] == pd.Timestamp("2024-01-03")


def test_load_hourly_fetches_when_no_cache(tmp_data_dir, sample_daily, monkeypatch):
    hourly = sample_daily.rename(columns={"ts": "ts"}).head(2)
    monkeypatch.setattr(data_mod, "fetch_hourly_cryptocompare", lambda **kw: hourly)
    out = load_hourly()
    assert (tmp_data_dir / "hourly.csv").exists()
    assert len(out) == 2


# ---------------------------------------------------------------------------
# update_cache
# ---------------------------------------------------------------------------


def test_update_cache_writes_both_and_reports_counts(tmp_data_dir, sample_daily, monkeypatch):
    # Seed an empty cache
    pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume", "source"]).to_csv(
        tmp_data_dir / "daily.csv", index=False
    )
    monkeypatch.setattr(data_mod, "fetch_daily_yahoo", lambda: sample_daily)
    monkeypatch.setattr(data_mod, "fetch_hourly_cryptocompare", lambda **kw: sample_daily.head(2))
    result = update_cache()
    assert result["daily_total"] == 4
    assert result["hourly_total"] == 2
    assert (tmp_data_dir / "daily.csv").exists()
    assert (tmp_data_dir / "hourly.csv").exists()
