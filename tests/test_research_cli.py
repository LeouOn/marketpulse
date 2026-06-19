"""Tests for the research CLI (B9).

The CLI is just a thin wrapper around the underlying tools; we test that
each subcommand runs without error and produces the expected JSON shape.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.research import cli as research_cli
from src.research import data as data_mod
from src.research import tools as tools_mod


@pytest.fixture
def seeded_data(tmp_path, monkeypatch):
    monkeypatch.setattr(data_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(data_mod, "DAILY_CSV", tmp_path / "daily.csv")
    monkeypatch.setattr(tools_mod, "REPORTS_DIR", tmp_path / "reports")
    # Disable network
    monkeypatch.setattr(data_mod, "fetch_daily_yahoo", lambda *a, **kw: pd.DataFrame())
    monkeypatch.setattr(data_mod, "fetch_hourly_cryptocompare", lambda *a, **kw: pd.DataFrame())
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
    return df


# ---------------------------------------------------------------------------
# Subcommand smoke tests
# ---------------------------------------------------------------------------


def test_cli_list_strategies(capsys):
    rc = research_cli.main(["list-strategies"])
    assert rc == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert any(s["name"] == "BuyAndHold" for s in parsed)


def test_cli_list_scaling(capsys):
    rc = research_cli.main(["list-scaling"])
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert any(s["name"] == "KellyCriterion" for s in parsed)


def test_cli_data_summary(seeded_data, capsys):
    rc = research_cli.main(["data-summary", "--start", "2024-01-15", "--end", "2024-04-01"])
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert "cagr_pct" in parsed
    assert parsed["rows"] > 0


def test_cli_backtest(seeded_data, capsys):
    rc = research_cli.main(
        [
            "backtest",
            "--strategy", "BuyAndHold",
            "--start", "2024-01-15",
            "--end", "2024-04-01",
        ]
    )
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert "metrics" in parsed
    assert "report_id" in parsed
    assert parsed["strategy"] == "BuyAndHold"


def test_cli_backtest_with_strategy_params(seeded_data, capsys):
    rc = research_cli.main(
        [
            "backtest",
            "--strategy", "DCAFixedAmount",
            "--strategy-params", '{"amount_usd": 50, "every_n_bars": 3}',
            "--start", "2024-01-15",
            "--end", "2024-04-01",
        ]
    )
    assert rc == 0


def test_cli_compare(seeded_data, capsys):
    # W4 T21: compare is now multi-ASSET (was multi-strategy). The
    # seeded_data fixture only seeds BTC, so we compare BTC against BTC
    # here purely to exercise the new --assets parsing + JSON shape.
    # Cross-asset compare is covered by test_research_cli_multiasset.py.
    rc = research_cli.main(
        [
            "compare",
            "--assets", "BTC",
            "--strategy", "BuyAndHold",
            "--start", "2024-01-15",
            "--end", "2024-04-01",
        ]
    )
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert "series" in parsed
    assert "BTC" in parsed["series"]
    assert parsed["series"]["BTC"][0]["normalized_return"] == 100.0


def test_cli_montecarlo_gbm(seeded_data, capsys):
    rc = research_cli.main(
        [
            "montecarlo",
            "--method", "gbm",
            "--n-paths", "100",
            "--n-steps", "50",
            "--mu", "0.3",
            "--sigma", "0.5",
            "--starting-value", "10000",
            "--seed", "0",
        ]
    )
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert "terminal_median" in parsed


def test_cli_montecarlo_block_bootstrap(seeded_data, capsys):
    rc = research_cli.main(
        [
            "montecarlo",
            "--method", "block_bootstrap",
            "--n-paths", "50",
            "--n-steps", "100",
            "--start", "2024-01-15",
            "--end", "2024-04-01",
        ]
    )
    assert rc == 0


def test_cli_list_reports_empty(seeded_data, capsys):
    rc = research_cli.main(["list-reports"])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "[]"


def test_cli_list_reports_after_backtest(seeded_data, capsys):
    # Run a backtest to create a report
    research_cli.main(["backtest", "--strategy", "BuyAndHold", "--start", "2024-01-15", "--end", "2024-04-01"])
    capsys.readouterr()  # discard
    rc = research_cli.main(["list-reports"])
    assert rc == 0
    reports = json.loads(capsys.readouterr().out)
    assert len(reports) == 1
    assert reports[0]["kind"] == "backtest"


def test_cli_no_args_prints_help():
    """No subcommand -> help message, non-zero exit."""
    with pytest.raises(SystemExit):
        research_cli.main([])
