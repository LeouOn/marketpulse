"""End-to-end smoke test of the research lab.

Seeds a synthetic 2000-day daily series, then exercises:
  1. get_data_summary
  2. run_backtest (DCA)
  3. run_montecarlo (GBM)
  4. compare_strategies
  5. reports on disk

Run: python -m pytest tests/test_research_smoke.py -v -s
"""

from __future__ import annotations

import os
import pathlib
import sys

import pandas as pd
import pytest

# Ensure repo root is importable
sys.path.insert(0, ".")

from src.research import data as data_mod
from src.research import tools as tools_mod
from src.research.tools import execute


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    monkeypatch.setattr(data_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(data_mod, "DAILY_CSV", tmp_path / "daily.csv")
    monkeypatch.setattr(tools_mod, "REPORTS_DIR", tmp_path / "reports")
    # No network
    monkeypatch.setattr(data_mod, "fetch_daily_yahoo", lambda *a, **kw: pd.DataFrame())
    monkeypatch.setattr(data_mod, "fetch_hourly_cryptocompare", lambda *a, **kw: pd.DataFrame())
    # Seed 2000 days of synthetic BTC
    n = 2000
    df = pd.DataFrame(
        {
            "ts": pd.date_range("2018-01-01", periods=n, freq="D"),
            "open": [3000.0 + i * 5.0 for i in range(n)],
            "high": [3000.0 + i * 5.0 + 50.0 for i in range(n)],
            "low": [3000.0 + i * 5.0 - 50.0 for i in range(n)],
            "close": [3000.0 + i * 5.0 for i in range(n)],
            "volume": [1.0] * n,
            "source": "smoke",
        }
    )
    df.to_csv(tmp_path / "daily.csv", index=False)
    return tmp_path


def test_end_to_end_pipeline(seeded):
    # 1. data summary
    r = execute("get_data_summary", {"timeframe": "daily", "start": "2018-01-01", "end": "2023-06-01"})
    assert r.success, r.error
    assert r.data["rows"] >= 1900  # roughly 2000 minus a few days
    assert "cagr_pct" in r.data

    # 2. backtest
    r = execute(
        "run_backtest",
        {
            "strategy": "DCAFixedAmount",
            "strategy_params": {"amount_usd": 100, "every_n_bars": 7},
            "scaling": "FixedDollar",
            "scaling_params": {"amount_usd": 100},
            "start": "2018-01-01",
            "end": "2023-06-01",
        },
    )
    assert r.success, r.error
    assert "metrics" in r.data
    assert r.data["metrics"]["num_buys"] >= 100
    assert r.report_id is not None

    # 3. monte carlo
    r = execute(
        "run_montecarlo",
        {
            "method": "gbm",
            "n_paths": 1000,
            "n_steps": 365,
            "mu": 0.5,
            "sigma": 0.8,
            "seed": 42,
            "starting_value": 10000,
        },
    )
    assert r.success, r.error
    assert r.data["terminal_median"] > 0

    # 4. compare
    r = execute(
        "compare_strategies",
        {
            "strategies": ["BuyAndHold", "DCAFixedAmount", "MomentumTrend"],
            "scaling": "FixedDollar",
            "scaling_params": {"amount_usd": 100},
            "start": "2019-01-01",
            "end": "2023-06-01",
        },
    )
    assert r.success, r.error
    assert r.data["count"] == 3

    # 5. reports on disk
    reports_dir = seeded / "reports"
    assert reports_dir.exists()
    backtests = list((reports_dir / "backtest").glob("*.json"))
    assert len(backtests) >= 1
    monte_carlos = list((reports_dir / "montecarlo").glob("*.json"))
    assert len(monte_carlos) >= 1
