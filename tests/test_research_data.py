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
    """Redirect DATA_DIR to a temp dir so tests don't touch real data/btc.

    Also blocks all real network calls (fetchers are stubbed to return
    empty DataFrames). Tests that need real data should override the
    specific fetcher.
    """
    monkeypatch.setattr(data_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(data_mod, "DAILY_CSV", tmp_path / "daily.csv")
    monkeypatch.setattr(data_mod, "HOURLY_CSV", tmp_path / "hourly.csv")
    # Block all 3 fetchers by default so tests don't hit the network
    monkeypatch.setattr(data_mod, "fetch_daily_yahoo", lambda *a, **kw: pd.DataFrame())
    monkeypatch.setattr(data_mod, "fetch_hourly_cryptocompare", lambda *a, **kw: pd.DataFrame())
    monkeypatch.setattr(data_mod, "fetch_hourly_binance", lambda *a, **kw: pd.DataFrame())
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
    # New tranche-based update_cache passes start= to fetch_daily_yahoo;
    # the mock must accept any kwargs.
    monkeypatch.setattr(data_mod, "fetch_daily_yahoo", lambda *a, **kw: sample_daily)
    monkeypatch.setattr(data_mod, "fetch_hourly_cryptocompare", lambda *a, **kw: sample_daily.head(2))
    monkeypatch.setattr(data_mod, "fetch_hourly_binance", lambda *a, **kw: sample_daily.head(2))
    result = update_cache()
    assert result["daily_total"] == 4
    assert result["hourly_total"] == 2
    assert (tmp_data_dir / "daily.csv").exists()
    assert (tmp_data_dir / "hourly.csv").exists()


# ---------------------------------------------------------------------------
# Multi-tranche loader (B11)
# ---------------------------------------------------------------------------


def _sample_daily_2y() -> pd.DataFrame:
    """2 years of daily data (2020-01-01 -> 2021-12-31) for incremental tests."""
    dates = pd.date_range("2020-01-01", "2021-12-31", freq="D")
    return pd.DataFrame(
        {
            "ts": dates,
            "open": [9000.0 + i * 0.5 for i in range(len(dates))],
            "high": [9050.0 + i * 0.5 for i in range(len(dates))],
            "low": [8950.0 + i * 0.5 for i in range(len(dates))],
            "close": [9020.0 + i * 0.5 for i in range(len(dates))],
            "volume": [1e9] * len(dates),
            "source": "yahoo",
        }
    )


def test_yahoo_btc_earliest_constant():
    """Sanity: the earliest BTC-USD date on Yahoo is 2010-07-16."""
    from src.research.data import YAHOO_BTC_EARLIEST

    assert YAHOO_BTC_EARLIEST == "2010-07-16"


def test_binance_btc_start_constant():
    """Sanity: BTCUSDT trading on Binance started 2017-08-17."""
    from src.research.data import BINANCE_BTC_START

    assert str(BINANCE_BTC_START.date()) == "2017-08-17"


def test_update_cache_runs_all_three_tranches_by_default(tmp_data_dir, monkeypatch):
    """Default update_cache runs T1 + T2 + T3."""
    daily = _sample_daily_2y().iloc[:10]
    hourly_cc = _sample_daily_2y().iloc[:5].rename(columns={"ts": "ts"}).head(5)
    hourly_bn = _sample_daily_2y().iloc[:5]

    monkeypatch.setattr(data_mod, "fetch_daily_yahoo", lambda *a, **kw: daily)
    monkeypatch.setattr(data_mod, "fetch_hourly_cryptocompare", lambda *a, **kw: hourly_cc)
    monkeypatch.setattr(data_mod, "fetch_hourly_binance", lambda *a, **kw: hourly_bn)

    result = update_cache()
    names = [t["name"] for t in result["tranches"]]
    assert names == ["T1", "T2", "T3"]


def test_update_cache_only_daily_when_hourly_false(tmp_data_dir, monkeypatch):
    """Passing daily=True, hourly=False skips T2 and T3."""
    daily = _sample_daily_2y().iloc[:5]
    monkeypatch.setattr(data_mod, "fetch_daily_yahoo", lambda *a, **kw: daily)

    result = update_cache(daily=True, hourly=False)
    names = [t["name"] for t in result["tranches"]]
    assert names == ["T1"]


def test_update_cache_only_t3_for_incremental_update(tmp_data_dir, monkeypatch):
    """``tranches=['t3_hourly_binance']`` runs only T3 (used for hourly auto-refresh)."""
    bn = _sample_daily_2y().iloc[:3]
    monkeypatch.setattr(data_mod, "fetch_hourly_binance", lambda *a, **kw: bn)

    result = update_cache(tranches=["t3_hourly_binance"])
    names = [t["name"] for t in result["tranches"]]
    assert names == ["T3"]


def test_update_cache_incremental_skips_older_bars(tmp_data_dir, monkeypatch):
    """When fetch returns bars older than what's already cached, they are filtered out."""
    # Seed cache with 10 recent bars
    existing = _sample_daily_2y().iloc[-10:].copy()  # 2021-12-22 .. 2021-12-31
    existing.to_csv(tmp_data_dir / "daily.csv", index=False)

    # Fetch returns older bars (from 2020) + same recent bars
    new = _sample_daily_2y()  # full 2020-2021
    monkeypatch.setattr(data_mod, "fetch_daily_yahoo", lambda *a, **kw: new)

    result = update_cache(tranches=["t1_daily_yahoo"])
    t1 = result["tranches"][0]
    # The new fetch returned 731 bars; after filtering to ts > max_existing (2021-12-31),
    # none survive (everything is <= the cached max). So 0 new rows are added.
    assert t1["rows_fetched"] == 0
    assert t1["rows_added"] == 0


def test_update_cache_handles_tranche_failure_gracefully(tmp_data_dir, monkeypatch):
    """A failed tranche should record the error but not stop the other tranches."""

    def boom(*a, **kw):
        raise RuntimeError("simulated network failure")

    monkeypatch.setattr(data_mod, "fetch_daily_yahoo", boom)
    cc = _sample_daily_2y().iloc[:5]
    monkeypatch.setattr(data_mod, "fetch_hourly_cryptocompare", lambda *a, **kw: cc)
    monkeypatch.setattr(data_mod, "fetch_hourly_binance", lambda *a, **kw: pd.DataFrame())

    result = update_cache()
    t1 = result["tranches"][0]
    assert t1["name"] == "T1"
    assert t1["error"] is not None
    assert "simulated network failure" in t1["error"]


def test_yahoo_constant_used_by_fetcher(tmp_data_dir, monkeypatch):
    """fetch_daily_yahoo should be called with YAHOO_BTC_EARLIEST as the start."""
    from src.research.data import YAHOO_BTC_EARLIEST

    captured = {}

    def capture(*a, **kw):
        captured.update(kw)
        return pd.DataFrame()

    monkeypatch.setattr(data_mod, "fetch_daily_yahoo", capture)
    update_cache(tranches=["t1_daily_yahoo"])
    assert captured.get("start") == YAHOO_BTC_EARLIEST


def test_binance_tranche_end_is_now(tmp_data_dir, monkeypatch):
    """T3 (Binance) fetches to 'now' -- end_ms should be set to roughly now."""
    import time as _time

    before = int(_time.time() * 1000)
    captured = {}

    def capture(*a, **kw):
        captured.update(kw)
        return pd.DataFrame()

    monkeypatch.setattr(data_mod, "fetch_hourly_binance", capture)
    update_cache(tranches=["t3_hourly_binance"])
    after = int(_time.time() * 1000)
    end_ms = captured.get("end_ms", 0)
    # T3 wraps the fetcher in a lambda that captures the end_ms at call time.
    # Our capture mock records whatever kwargs the lambda passes.
    assert before - 1000 <= end_ms <= after + 1000, f"end_ms={end_ms} not in [{before-1000}, {after+1000}]"


def test_data_summary_includes_sources_field(tmp_data_dir, sample_daily):
    """data_summary should report which sources are in the cache."""
    summary = data_mod.data_summary(sample_daily)
    assert "sources" in summary
    assert "yahoo" in summary["sources"]


def test_data_summary_includes_multiple_sources(tmp_data_dir):
    """When a frame has bars from multiple sources, all are listed."""
    import pandas as pd

    df = pd.DataFrame(
        {
            "ts": pd.to_datetime(["2024-01-01", "2024-01-02"]),
            "open": [1.0, 2.0],
            "high": [1.0, 2.0],
            "low": [1.0, 2.0],
            "close": [1.0, 2.0],
            "volume": [1.0, 1.0],
            "source": ["yahoo", "binance"],
        }
    )
    summary = data_mod.data_summary(df)
    assert set(summary["sources"]) == {"yahoo", "binance"}


# ---------------------------------------------------------------------------
# tenacity retry on transient HTTP errors
# ---------------------------------------------------------------------------


def test_http_get_json_retries_on_429(monkeypatch):
    """A 429 response should be retried; on 3rd success the call returns."""
    import requests as _req

    call_count = {"n": 0}

    def fake_get(url, params=None, timeout=None):
        call_count["n"] += 1
        if call_count["n"] < 3:
            r = _req.models.Response()
            r.status_code = 429
            raise _req.HTTPError("429 Too Many Requests", response=r)
        # 3rd call: success
        r = _req.models.Response()
        r.status_code = 200
        r._content = b'{"ok": true}'
        r.encoding = "utf-8"
        return r

    monkeypatch.setattr(data_mod.requests, "get", fake_get)
    result = data_mod._http_get_json("http://example.com")
    assert result == {"ok": True}
    assert call_count["n"] == 3


def test_http_get_json_gives_up_after_max_attempts(monkeypatch):
    """If every attempt fails, tenacity re-raises the last error."""
    import requests as _req

    def always_fail(url, params=None, timeout=None):
        r = _req.models.Response()
        r.status_code = 503
        raise _req.HTTPError("503 Service Unavailable", response=r)

    monkeypatch.setattr(data_mod.requests, "get", always_fail)
    with pytest.raises(_req.HTTPError):
        data_mod._http_get_json("http://example.com")


def test_http_get_data_list_handles_cryptocompare_silent_rate_limit(monkeypatch):
    """CryptoCompare returns HTTP 200 with 'rate limit' message; we should raise."""
    import requests as _req

    def fake_get(url, params=None, timeout=None):
        r = _req.models.Response()
        r.status_code = 200
        r._content = b'{"Response": "Error", "Message": "rate limit"}'
        r.encoding = "utf-8"
        return r

    monkeypatch.setattr(data_mod.requests, "get", fake_get)
    with pytest.raises(_req.HTTPError):
        data_mod._http_get_data_list("http://example.com")


def test_http_get_data_list_returns_data_on_success(monkeypatch):
    """Successful response with Response=Success returns the Data list."""
    import requests as _req

    def fake_get(url, params=None, timeout=None):
        r = _req.models.Response()
        r.status_code = 200
        r._content = b'{"Response": "Success", "Data": {"Data": [{"time": 1000, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volumeto": 100}]}}'
        r.encoding = "utf-8"
        return r

    monkeypatch.setattr(data_mod.requests, "get", fake_get)
    data = data_mod._http_get_data_list("http://example.com")
    assert data is not None
    assert len(data) == 1
    assert data[0]["time"] == 1000
