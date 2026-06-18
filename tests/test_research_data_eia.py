"""TDD tests for ``EiaProvider`` (W2 T9 — oil fundamentals via EIA v2 API).

These tests exercise the provider with mocked ``requests.get`` so they run
without ``EIA_API_KEY`` or network access.

EIA v2 response shape (per https://www.eia.gov/opendata/v2/)::

    {
      "response": {
        "total": <int>,
        "frequency": "daily" | "weekly" | ...,
        "data": [
          {"period": "YYYY-MM-DD", "series": [...], "value": <float|null>, ...},
          ...
        ]
      }
    }
"""

from __future__ import annotations

import os
import time
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import pytest
import requests

from src.research.data import DataPipelineError
from src.research.data._eia_key import get_eia_api_key
from src.research.data.eia import EiaProvider


# ---------------------------------------------------------------------------
# EIA v2 response builders
# ---------------------------------------------------------------------------


def _eia_response(rows: list[dict]) -> dict:
    """Wrap row list in the EIA v2 ``{"response": {"data": [...]}}`` envelope."""
    return {"response": {"total": len(rows), "frequency": "daily", "data": rows}}


def _wti_rows() -> list[dict]:
    """Three valid daily WTI spot rows."""
    return [
        {"period": "2024-01-02", "series": ["PET.RWTC.D"], "value": 75.21, "units": "dollars per barrel"},
        {"period": "2024-01-03", "series": ["PET.RWTC.D"], "value": 76.12, "units": "dollars per barrel"},
        {"period": "2024-01-04", "series": ["PET.RWTC.D"], "value": 77.50, "units": "dollars per barrel"},
    ]


def _mock_ok(payload: dict) -> Mock:
    """A mocked 2xx ``requests.Response`` returning ``payload`` as JSON."""
    r = Mock(spec=requests.Response)
    r.status_code = 200
    r.json.return_value = payload
    r.raise_for_status.return_value = None
    return r


def _mock_http_error(status: int = 503) -> Mock:
    """A mocked ``requests.Response`` whose ``raise_for_status`` raises HTTPError."""
    r = Mock(spec=requests.Response)
    r.status_code = status
    err = requests.HTTPError(f"{status} error", response=r)
    r.raise_for_status.side_effect = err
    return r


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def provider(tmp_path: Path) -> EiaProvider:
    """An ``EiaProvider`` with a fake key, cache under ``tmp_path``, instant retries."""
    return EiaProvider(
        api_key="test_key",
        cache_dir=tmp_path,
        max_staleness_days=7,
        retry_attempts=4,
        retry_initial_wait=0.0,
        retry_max_wait=0.0,
    )


# ---------------------------------------------------------------------------
# Test 1 — Happy path
# ---------------------------------------------------------------------------


def test_fetch_happy_path_returns_metis_contract_dataframe(provider: EiaProvider) -> None:
    """Mocked EIA JSON is parsed into the OHLCV-source contract DataFrame."""
    payload = _eia_response(_wti_rows())
    with patch("src.research.data.eia.requests.get", return_value=_mock_ok(payload)) as mock_get:
        df = provider.fetch("PET.RWTC.D", date(2024, 1, 1), date(2024, 1, 31))

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 3
    # Metis column contract
    expected_cols = {"ts", "open", "high", "low", "close", "volume", "source"}
    assert set(df.columns) == expected_cols
    # EIA single-value-per-timestamp → open=high=low=close=value
    assert df["open"].iloc[0] == pytest.approx(75.21)
    assert df["high"].iloc[0] == pytest.approx(75.21)
    assert df["low"].iloc[0] == pytest.approx(75.21)
    assert df["close"].iloc[0] == pytest.approx(75.21)
    # volume NaN, source labelled f"eia:{series_id}"
    assert pd.isna(df["volume"].iloc[0])
    assert df["source"].iloc[0] == "eia:PET.RWTC.D"
    # period parsed into ts
    assert df["ts"].iloc[0] == pd.Timestamp("2024-01-02")
    # rows sorted ascending by ts
    assert df["ts"].is_monotonic_increasing
    assert mock_get.called


# ---------------------------------------------------------------------------
# Test 2 — Cache hit (fresh cache, no network call)
# ---------------------------------------------------------------------------


def test_cache_hit_skips_network(provider: EiaProvider, tmp_path: Path) -> None:
    """Fresh cache file is served without touching the network."""
    cache_path = tmp_path / "PET.RWTC.D.parquet"
    df_cached = pd.DataFrame(
        {
            "ts": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "open": [75.0, 76.0],
            "high": [75.0, 76.0],
            "low": [75.0, 76.0],
            "close": [75.0, 76.0],
            "volume": [float("nan"), float("nan")],
            "source": ["eia:PET.RWTC.D", "eia:PET.RWTC.D"],
        }
    )
    df_cached.to_parquet(cache_path)  # just-written → mtime is now → fresh

    with patch("src.research.data.eia.requests.get") as mock_get:
        df = provider.fetch("PET.RWTC.D", date(2024, 1, 2), date(2024, 1, 3))

    assert not mock_get.called
    assert len(df) == 2
    assert df["close"].iloc[0] == 75.0


# ---------------------------------------------------------------------------
# Test 3 — Cache miss triggers fetch and writes cache
# ---------------------------------------------------------------------------


def test_cache_miss_triggers_fetch_and_writes_cache(provider: EiaProvider, tmp_path: Path) -> None:
    cache_path = tmp_path / "PET.RWTC.D.parquet"
    assert not cache_path.exists()

    payload = _eia_response(_wti_rows())
    with patch("src.research.data.eia.requests.get", return_value=_mock_ok(payload)):
        df = provider.fetch("PET.RWTC.D", date(2024, 1, 1), date(2024, 1, 31))

    assert len(df) == 3
    assert cache_path.exists(), "fetch should have persisted the cache parquet"
    # cache is loadable and round-trips the contract columns
    on_disk = pd.read_parquet(cache_path)
    assert {"ts", "open", "high", "low", "close", "volume", "source"} <= set(on_disk.columns)


# ---------------------------------------------------------------------------
# Test 4 — Unsupported series raises ValueError
# ---------------------------------------------------------------------------


def test_unsupported_series_raises_value_error(provider: EiaProvider) -> None:
    with pytest.raises(ValueError, match="Unsupported"):
        provider.fetch("INVALID.SERIES.D", date(2024, 1, 1), date(2024, 1, 31))


def test_supported_series_whitelist_has_five_oil_series() -> None:
    """Metis SC4 lock-down: whitelist contains exactly the 5 oil fundamentals."""
    assert isinstance(EiaProvider.SUPPORTED_SERIES, frozenset)
    assert EiaProvider.SUPPORTED_SERIES == frozenset(
        {
            "PET.RWTC.D",  # WTI spot daily
            "PET.RBRTE.D",  # Brent spot daily
            "PET.WGFUPUS2.W",  # Weekly crude oil inventory
            "PET.WPULEUS3.W",  # Weekly gasoline inventory
            "PET.WPUP_NUS-Z1_2.W",  # Weekly distillate inventory
        }
    )


# ---------------------------------------------------------------------------
# Test 5 — Missing EIA_API_KEY raises RuntimeError (fail-fast)
# ---------------------------------------------------------------------------


def test_missing_api_key_raises_runtime_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("EIA_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="EIA_API_KEY not set"):
        EiaProvider(cache_dir=tmp_path)


def test_get_eia_api_key_helper_includes_registration_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EIA_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="eia.gov/opendata/register"):
        get_eia_api_key()


# ---------------------------------------------------------------------------
# Test 6 — Stale cache + fetch failure → DataPipelineError (strict freshness)
# ---------------------------------------------------------------------------


def test_stale_cache_with_fetch_failure_raises_data_pipeline_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_path = tmp_path / "PET.RWTC.D.parquet"
    df_stale = pd.DataFrame(
        {
            "ts": pd.to_datetime(["2024-01-02"]),
            "open": [70.0], "high": [70.0], "low": [70.0], "close": [70.0],
            "volume": [float("nan")],
            "source": ["eia:PET.RWTC.D"],
        }
    )
    df_stale.to_parquet(cache_path)
    # Push mtime 30 days into the past → staleness (30d) > max_staleness_days (7d)
    old = time.time() - 30 * 86400
    os.utime(cache_path, (old, old))

    provider = EiaProvider(
        api_key="test_key",
        cache_dir=tmp_path,
        max_staleness_days=7,
        retry_attempts=2,
        retry_initial_wait=0.0,
        retry_max_wait=0.0,
    )

    with patch("src.research.data.eia.requests.get", return_value=_mock_http_error(503)):
        with pytest.raises(DataPipelineError):
            provider.fetch("PET.RWTC.D", date(2024, 1, 1), date(2024, 1, 31))


# ---------------------------------------------------------------------------
# Test 7 — HTTP error retry then success
# ---------------------------------------------------------------------------


def test_http_error_retry_then_success(provider: EiaProvider) -> None:
    payload = _eia_response(_wti_rows())
    side_effects = [_mock_http_error(503), _mock_http_error(503), _mock_ok(payload)]

    with patch("src.research.data.eia.requests.get", side_effect=side_effects) as mock_get:
        df = provider.fetch("PET.RWTC.D", date(2024, 1, 1), date(2024, 1, 31))

    assert mock_get.call_count == 3, "should retry twice then succeed on the 3rd call"
    assert len(df) == 3
    assert df["close"].iloc[0] == pytest.approx(75.21)


# ---------------------------------------------------------------------------
# Test 8 — EIA JSON parsing handles missing/null values
# ---------------------------------------------------------------------------


def test_parsing_drops_rows_with_null_or_missing_value(provider: EiaProvider) -> None:
    rows = [
        {"period": "2024-01-02", "series": ["PET.RWTC.D"], "value": 75.21},
        {"period": "2024-01-03", "series": ["PET.RWTC.D"], "value": None},  # explicit null
        {"period": "2024-01-04", "series": ["PET.RWTC.D"]},  # field missing entirely
        {"period": "2024-01-05", "series": ["PET.RWTC.D"], "value": 77.50},
    ]
    payload = _eia_response(rows)

    with patch("src.research.data.eia.requests.get", return_value=_mock_ok(payload)):
        df = provider.fetch("PET.RWTC.D", date(2024, 1, 1), date(2024, 1, 31))

    # Null + missing-value rows dropped; only the 2 valid rows remain
    assert len(df) == 2
    assert list(df["close"]) == [pytest.approx(75.21), pytest.approx(77.50)]
    assert df["ts"].iloc[0] == pd.Timestamp("2024-01-02")
    assert df["ts"].iloc[1] == pd.Timestamp("2024-01-05")


# ---------------------------------------------------------------------------
# Bonus — DataProvider ABC contract compliance
# ---------------------------------------------------------------------------


def test_eia_provider_is_a_dataprovider_subclass() -> None:
    from src.research.data import DataProvider

    assert issubclass(EiaProvider, DataProvider)


def test_eia_provider_trading_days_per_year_is_252(provider: EiaProvider) -> None:
    assert provider.trading_days_per_year == 252.0


def test_load_daily_dispatches_to_default_series(provider: EiaProvider) -> None:
    """``load_daily`` calls ``fetch`` with the provider's default series (WTI)."""
    payload = _eia_response(_wti_rows())
    with patch.object(provider, "fetch", wraps=provider.fetch) as spy:
        with patch("src.research.data.eia.requests.get", return_value=_mock_ok(payload)):
            df = provider.load_daily(date(2024, 1, 1), date(2024, 1, 31))

    assert spy.call_count == 1
    called_series_id = spy.call_args.args[0]
    assert called_series_id == "PET.RWTC.D"
    assert len(df) == 3
