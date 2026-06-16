"""Tests for the LLM tool registry."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from src.research import tools as t
from src.research.tools import (
    REPORTS_DIR,
    ToolResult,
    execute,
    list_tools,
    tool_descriptions,
    tool_describe_scaling_model,
    tool_describe_strategy,
    tool_explain_metric,
    tool_get_data_summary,
    tool_list_scaling_models,
    tool_list_strategies,
    tool_run_backtest,
    tool_run_montecarlo,
)


@pytest.fixture
def tmp_reports(monkeypatch, tmp_path):
    """Redirect REPORTS_DIR to a temp dir so tests don't pollute the real one."""
    monkeypatch.setattr(t, "REPORTS_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def sample_daily(tmp_path, monkeypatch):
    """Seed a tiny daily cache so load_daily hits it without network."""
    from src.research import data as data_mod

    monkeypatch.setattr(data_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(data_mod, "DAILY_CSV", tmp_path / "daily.csv")
    df = pd.DataFrame(
        {
            "ts": pd.date_range("2024-01-01", periods=120, freq="D"),
            "open": [40000.0 + i * 50.0 for i in range(120)],
            "high": [40000.0 + i * 50.0 + 100 for i in range(120)],
            "low": [40000.0 + i * 50.0 - 100 for i in range(120)],
            "close": [40000.0 + i * 50.0 for i in range(120)],
            "volume": [1.0] * 120,
            "source": "test",
        }
    )
    df.to_csv(tmp_path / "daily.csv", index=False)
    # Also disable auto-refresh: if load_daily sees a stale cache it will try
    # to fetch from Yahoo, which we don't want in tests.
    monkeypatch.setattr(data_mod, "fetch_daily_yahoo", lambda *a, **kw: pd.DataFrame())
    monkeypatch.setattr(data_mod, "fetch_hourly_cryptocompare", lambda *a, **kw: pd.DataFrame())
    return df


# ---------------------------------------------------------------------------
# Registry sanity
# ---------------------------------------------------------------------------


def test_list_tools_returns_all_known():
    names = list_tools()
    expected = {
        "list_strategies",
        "describe_strategy",
        "list_scaling_models",
        "describe_scaling_model",
        "get_data_summary",
        "run_backtest",
        "run_montecarlo",
        "compare_strategies",
        "explain_metric",
    }
    assert set(names) == expected


def test_tool_descriptions_have_unique_names():
    descs = tool_descriptions()
    names = [d["function"]["name"] for d in descs]
    assert len(names) == len(set(names))
    # All descriptions are non-empty
    for d in descs:
        assert d["function"]["description"]
        # OpenAI function-calling format
        assert d["type"] == "function"
        assert "parameters" in d["function"]


def test_execute_unknown_tool_returns_error():
    r = execute("NotATool", {})
    assert r.success is False
    assert "Unknown" in r.error


# ---------------------------------------------------------------------------
# Listing / describing tools
# ---------------------------------------------------------------------------


def test_tool_list_strategies():
    r = tool_list_strategies({})
    assert r.success
    assert any(s["name"] == "DCAFixedAmount" for s in r.data)


def test_tool_list_scaling_models():
    r = tool_list_scaling_models({})
    assert r.success
    assert any(s["name"] == "KellyCriterion" for s in r.data)


def test_tool_describe_strategy_known():
    r = tool_describe_strategy({"name": "DCAFixedAmount"})
    assert r.success
    assert r.data["name"] == "DCAFixedAmount"


def test_tool_describe_strategy_unknown():
    r = tool_describe_strategy({"name": "NoSuchStrategy"})
    assert not r.success
    assert "NoSuchStrategy" in r.error


def test_tool_describe_strategy_missing_name():
    r = tool_describe_strategy({})
    assert not r.success


def test_tool_describe_scaling_known():
    r = tool_describe_scaling_model({"name": "KellyCriterion"})
    assert r.success


def test_tool_describe_scaling_unknown():
    r = tool_describe_scaling_model({"name": "Nope"})
    assert not r.success


# ---------------------------------------------------------------------------
# get_data_summary
# ---------------------------------------------------------------------------


def test_tool_get_data_summary_returns_metrics(sample_daily):
    r = tool_get_data_summary({"timeframe": "daily"})
    assert r.success
    assert r.data["rows"] == 120
    assert "cagr_pct" in r.data
    assert "max_drawdown_pct" in r.data


def test_tool_get_data_summary_filters_by_range(sample_daily):
    r = tool_get_data_summary({"start": "2024-02-01", "end": "2024-03-01", "timeframe": "daily"})
    assert r.success
    # Should be fewer rows than the full 120
    assert r.data["rows"] < 120


# ---------------------------------------------------------------------------
# run_backtest
# ---------------------------------------------------------------------------


def test_tool_run_backtest_dca(sample_daily, tmp_reports):
    r = tool_run_backtest(
        {
            "strategy": "DCAFixedAmount",
            "strategy_params": {"amount_usd": 100.0, "every_n_bars": 7},
            "start": "2024-01-01",
            "end": "2024-04-01",
        }
    )
    assert r.success, r.error
    assert "metrics" in r.data
    assert r.data["strategy"] == "DCAFixedAmount"
    assert r.report_id is not None
    # Report file should be on disk
    report_path = tmp_reports / "backtest" / f"{r.report_id}.json"
    assert report_path.exists()
    meta = json.loads(report_path.read_text())
    assert meta["kind"] == "backtest"
    assert meta["params"]["strategy"] == "DCAFixedAmount"


def test_tool_run_backtest_unknown_strategy(sample_daily, tmp_reports):
    r = tool_run_backtest({"strategy": "DoesNotExist"})
    assert not r.success
    assert "DoesNotExist" in r.error


def test_tool_run_backtest_missing_data(tmp_reports, monkeypatch):
    """When no data is in range, the tool returns a clean error."""
    from src.research import data as data_mod

    monkeypatch.setattr(data_mod, "DATA_DIR", tmp_reports)
    monkeypatch.setattr(data_mod, "DAILY_CSV", tmp_reports / "daily.csv")
    (tmp_reports / "daily.csv").write_text(
        "ts,open,high,low,close,volume,source\n2020-01-01,1,1,1,1,1,test\n"
    )
    # Prevent auto-refresh: simulate "no network"
    monkeypatch.setattr(data_mod, "fetch_daily_yahoo", lambda *a, **kw: pd.DataFrame())
    monkeypatch.setattr(data_mod, "fetch_hourly_cryptocompare", lambda *a, **kw: pd.DataFrame())
    r = tool_run_backtest({"strategy": "BuyAndHold", "start": "2024-01-01", "end": "2024-02-01"})
    assert not r.success
    assert "No" in r.error or "no" in r.error


# ---------------------------------------------------------------------------
# run_montecarlo
# ---------------------------------------------------------------------------


def test_tool_run_montecarlo_gbm(tmp_reports):
    r = tool_run_montecarlo(
        {
            "method": "gbm",
            "n_paths": 100,
            "n_steps": 50,
            "starting_value": 10_000.0,
            "mu": 0.5,
            "sigma": 0.5,
            "seed": 0,
        }
    )
    assert r.success, r.error
    assert "terminal_median" in r.data
    assert r.report_id is not None
    # Report should be saved
    report_path = tmp_reports / "montecarlo" / f"{r.report_id}.json"
    assert report_path.exists()


def test_tool_run_montecarlo_unknown_method(tmp_reports):
    r = tool_run_montecarlo({"method": "totally_made_up"})
    assert not r.success


def test_tool_run_montecarlo_block_bootstrap(sample_daily, tmp_reports):
    r = tool_run_montecarlo(
        {
            "method": "block_bootstrap",
            "n_paths": 50,
            "n_steps": 100,
            "block_size": 10,
            "start": "2024-01-01",
            "end": "2024-04-01",
            "seed": 0,
        }
    )
    assert r.success, r.error
    assert "terminal_median" in r.data


def test_tool_run_montecarlo_regime_switching(sample_daily, tmp_reports):
    r = tool_run_montecarlo(
        {
            "method": "regime_switching",
            "n_paths": 50,
            "n_steps": 100,
            "start": "2024-01-01",
            "end": "2024-04-01",
            "seed": 0,
        }
    )
    assert r.success, r.error


# ---------------------------------------------------------------------------
# compare_strategies
# ---------------------------------------------------------------------------


def test_tool_compare_strategies_runs_all(sample_daily, tmp_reports):
    r = execute(
        "compare_strategies",
        {
            "strategies": ["BuyAndHold", "DCAFixedAmount", {"name": "MomentumTrend", "params": {"sma_period": 30}}],
            "start": "2024-01-15",
            "end": "2024-04-01",
        },
    )
    assert r.success
    assert r.data["count"] == 3
    names = [x["strategy"] for x in r.data["results"]]
    assert "BuyAndHold" in names
    assert "DCAFixedAmount" in names
    assert "MomentumTrend" in names


def test_tool_compare_strategies_empty_list(sample_daily, tmp_reports):
    r = execute("compare_strategies", {"strategies": []})
    assert not r.success


# ---------------------------------------------------------------------------
# explain_metric
# ---------------------------------------------------------------------------


def test_tool_explain_metric_known():
    r = tool_explain_metric({"name": "sharpe"})
    assert r.success
    assert "Sharpe" in r.data["explanation"] or "sharpe" in r.data["explanation"].lower()


def test_tool_explain_metric_unknown():
    r = tool_explain_metric({"name": "hedge_ratio"})
    assert not r.success


# ---------------------------------------------------------------------------
# Report persistence
# ---------------------------------------------------------------------------


def test_report_persistence_creates_files(tmp_reports):
    """Saved report should have a JSON metadata file + artifact files."""
    r = tool_run_montecarlo(
        {
            "method": "gbm",
            "n_paths": 10,
            "n_steps": 20,
            "mu": 0.1,
            "sigma": 0.2,
            "seed": 0,
        }
    )
    assert r.success
    report_id = r.report_id
    meta_file = tmp_reports / "montecarlo" / f"{report_id}.json"
    assert meta_file.exists()
    meta = json.loads(meta_file.read_text())
    assert meta["id"] == report_id
    assert meta["kind"] == "montecarlo"


def test_backtest_report_includes_artifacts(tmp_reports, sample_daily):
    r = tool_run_backtest({"strategy": "BuyAndHold", "start": "2024-01-01", "end": "2024-04-01"})
    assert r.success
    rid = r.report_id
    artifacts_dir = tmp_reports / "backtest"
    # The artifact files should exist (placeholder PNGs or matplotlib PNGs)
    assert (artifacts_dir / f"{rid}.equity_png.png").exists()
    assert (artifacts_dir / f"{rid}.drawdown_png.png").exists()


def test_run_backtest_tool_accepts_inflows(sample_daily, tmp_reports):
    """The run_backtest tool should accept and pass through the inflows parameter."""
    r = tool_run_backtest(
        {
            "strategy": "NoTrade",
            "start": "2024-01-01",
            "end": "2024-04-01",
            "starting_equity": 0,
            "fee_bps": 0,
            "slippage_bps": 0,
            "inflows": [{"every_n_bars": 30, "amount_usd": 500.0, "source": "salary"}],
        }
    )
    assert r.success, r.error
    assert r.data["metrics"]["total_deposited"] > 0
    assert r.data["metrics"]["num_deposits"] > 0


def test_run_backtest_tool_accepts_loan(sample_daily, tmp_reports):
    """The run_backtest tool should accept an opaque loan object, pass it
    through to run_backtest_from_names (so loan metrics appear in the
    result), and persist loan metadata in the saved report."""
    from src.research.loans import FixedRateLoan

    loan = FixedRateLoan(
        principal=5_000.0,
        apr=0.08,
        start_date=pd.Timestamp("2024-01-01"),
    )
    r = tool_run_backtest(
        {
            "strategy": "NoTrade",
            "start": "2024-01-01",
            "end": "2024-04-01",
            "starting_equity": 10_000.0,
            "fee_bps": 0,
            "slippage_bps": 0,
            "loan": loan,
        }
    )
    assert r.success, r.error
    # Loan metrics must flow through from the backtest engine.
    metrics = r.data["metrics"]
    assert "debt_balance" in metrics
    assert "total_interest_paid" in metrics
    assert "loan_to_equity_ratio" in metrics
    assert metrics["total_interest_paid"] > 0.0
    # FixedRateLoan is interest-only, so principal is unchanged.
    assert metrics["debt_balance"] == pytest.approx(5_000.0, rel=1e-9)
    # Loan metadata is also persisted in the saved report's params dict.
    report_path = tmp_reports / "backtest" / f"{r.report_id}.json"
    meta = json.loads(report_path.read_text())
    loan_meta = meta["params"]["loan"]
    assert loan_meta is not None
    assert loan_meta["class"] == "FixedRateLoan"
    assert loan_meta["name"] == "FixedRateLoan"
    assert loan_meta["principal"] == 5_000.0
    assert loan_meta["apr"] == 0.08
