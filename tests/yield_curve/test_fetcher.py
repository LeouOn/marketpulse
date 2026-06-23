"""Fetcher tests using monkeypatched HTTP + tmp cache dir."""
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src.yield_curve.fetcher import FredCurveFetcher


def _fake_fred_response(series_id: str, d: date, value: float) -> dict:
    return {
        "observations": [
            {"date": d.isoformat(), "value": str(value)},
        ]
    }


def test_fetcher_returns_series_for_one_tenor(tmp_path, monkeypatch):
    fetched = []

    def fake_get(url, params, *a, **kw):
        fetched.append((url, params))
        series = params["series_id"]
        return type("R", (), {
            "raise_for_status": lambda self: None,
            "json": lambda self: _fake_fred_response(series, date(2026, 6, 23), 4.40),
        })()

    monkeypatch.setattr("src.yield_curve.fetcher.requests.get", fake_get)
    monkeypatch.setenv("FRED_API_KEY", "test-key")

    f = FredCurveFetcher(cache_dir=tmp_path)
    out = f.fetch_tenors(["2y"], date(2026, 6, 23), date(2026, 6, 23))

    assert "2y" in out
    assert isinstance(out["2y"], pd.DataFrame)
    assert len(out["2y"]) == 1
    assert out["2y"].iloc[0]["close"] == pytest.approx(4.40)


def test_fetcher_cache_hit_skips_http(tmp_path, monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "test-key")
    f = FredCurveFetcher(cache_dir=tmp_path)

    # Pre-seed cache with covering data
    cache_path = Path(tmp_path) / "DGS2.parquet"
    seeded = pd.DataFrame({
        "ts": pd.to_datetime(["2026-06-20", "2026-06-23"]),
        "open": [4.41, 4.40],
        "high": [4.41, 4.40],
        "low": [4.41, 4.40],
        "close": [4.41, 4.40],
        "volume": [float("nan"), float("nan")],
        "source": ["fred:DGS2", "fred:DGS2"],
    })
    seeded.to_parquet(cache_path)

    calls = []
    monkeypatch.setattr("src.yield_curve.fetcher.requests.get",
                        lambda *a, **kw: calls.append((a, kw)) or None)

    out = f.fetch_tenors(["2y"], date(2026, 6, 23), date(2026, 6, 23))
    assert calls == []  # no HTTP call — cache hit
    assert out["2y"].iloc[0]["close"] == pytest.approx(4.40)


def test_fetcher_missing_key_fails_fast(monkeypatch, tmp_path):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="FRED_API_KEY"):
        FredCurveFetcher(cache_dir=tmp_path)
