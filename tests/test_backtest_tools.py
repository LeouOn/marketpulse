"""Offline tests for src/llm/tools/backtest_tools.py (the run_backtest agent tool).

The BacktestEngine is faked at its source module (the tool imports it lazily),
so no historical data is loaded and no network is touched. The fakes return
result objects shaped exactly like BacktestResults.
"""

from __future__ import annotations

import json
import math
from types import SimpleNamespace

import numpy as np
import pytest

from src.llm.tools.backtest_tools import (
    BACKTEST_TOOL_DEFINITIONS,
    BACKTEST_TOOL_HANDLERS,
    run_backtest,
)

METRIC_FIELDS = (
    "total_trades",
    "winning_trades",
    "losing_trades",
    "win_rate",
    "total_pnl",
    "total_pnl_percent",
    "profit_factor",
    "max_drawdown",
    "max_drawdown_percent",
    "sharpe_ratio",
    "average_winner",
    "average_loser",
    "expectancy",
    "fvg_success_rate",
    "divergence_success_rate",
)


def _results(**overrides) -> SimpleNamespace:
    base = {
        "total_trades": 12,
        "winning_trades": 7,
        "losing_trades": 5,
        "win_rate": 58.333,
        "total_pnl": 1234.5678,
        "total_pnl_percent": 12.34568,
        "profit_factor": 1.876,
        "max_drawdown": -310.12,
        "max_drawdown_percent": -3.1012,
        "sharpe_ratio": 1.23456,
        "average_winner": 310.11,
        "average_loser": -188.77,
        "expectancy": 102.88,
        "fvg_success_rate": 64.4,
        "divergence_success_rate": 57.1,
    }
    return SimpleNamespace(**{**base, **overrides})


@pytest.fixture
def fake_engine(monkeypatch):
    """Patch BacktestEngine at its source module; records the call kwargs."""
    import src.backtesting.backtest_engine as engine_mod

    holder: dict = {"kwargs": None, "result": _results(), "raises": None}

    class _FakeEngine:
        def run_backtest(self, **kwargs):
            holder["kwargs"] = kwargs
            if holder["raises"]:
                raise holder["raises"]
            return holder["result"]

    monkeypatch.setattr(engine_mod, "BacktestEngine", _FakeEngine)
    return holder


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


async def test_run_backtest_maps_metrics(fake_engine):
    result = await run_backtest("NQ=F", "2024-01-01", "2024-06-30", initial_capital=25_000, interval="15m")

    assert "error" not in result
    assert result["symbol"] == "NQ=F"
    assert result["period"] == "2024-01-01 to 2024-06-30"
    assert result["interval"] == "15m"
    assert result["initial_capital"] == 25_000
    metrics = result["metrics"]
    for field in METRIC_FIELDS:
        assert field in metrics, f"missing metric: {field}"
    assert metrics["win_rate"] == 58.33  # rounded to 2 decimals
    assert metrics["total_pnl"] == 1234.57
    assert metrics["total_trades"] == 12
    assert result["timestamp"]


async def test_run_backtest_forwards_kwargs_and_defaults(fake_engine):
    await run_backtest("SPY", "2024-01-01", "2024-12-31")

    kwargs = fake_engine["kwargs"]
    assert kwargs == {
        "symbol": "SPY",
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "initial_capital": 10_000,
        "interval": "5m",
    }


async def test_run_backtest_zero_result_maps_zeros(fake_engine):
    fake_engine["result"] = SimpleNamespace(**{f: (0 if "trades" in f else 0.0) for f in METRIC_FIELDS})

    result = await run_backtest("X", "2024-01-01", "2024-02-01")

    assert "error" not in result
    assert result["metrics"]["total_trades"] == 0
    assert result["metrics"]["win_rate"] == 0.0


async def test_run_backtest_engine_error_surfaces(fake_engine):
    fake_engine["raises"] = RuntimeError("no data for symbol")

    result = await run_backtest("BAD", "2024-01-01", "2024-02-01")

    assert result == {"error": "no data for symbol"}


# ---------------------------------------------------------------------------
# Value hygiene (agent-facing JSON)
# ---------------------------------------------------------------------------


async def test_run_backtest_sanitises_nan_and_inf_metrics(fake_engine):
    """Sharpe can be NaN (zero variance); profit_factor inf (no losers)."""
    fake_engine["result"] = _results(sharpe_ratio=math.nan, profit_factor=math.inf)

    result = await run_backtest("X", "2024-01-01", "2024-02-01")

    assert result["metrics"]["sharpe_ratio"] is None
    assert result["metrics"]["profit_factor"] is None
    # Other metrics unaffected.
    assert result["metrics"]["win_rate"] == 58.33


async def test_run_backtest_metrics_are_json_serialisable(fake_engine):
    """The engine computes over pandas: metrics can arrive as numpy scalars."""
    fake_engine["result"] = _results(
        total_trades=np.int64(12),
        winning_trades=np.int64(7),
        losing_trades=np.int64(5),
        win_rate=np.float64(58.333),
        sharpe_ratio=np.float64(1.23456),
    )

    result = await run_backtest("X", "2024-01-01", "2024-02-01")

    metrics = result["metrics"]
    assert isinstance(metrics["total_trades"], int)
    assert isinstance(metrics["win_rate"], float)
    # The whole payload must survive a strict JSON round-trip.
    assert json.loads(json.dumps(result))["metrics"]["total_trades"] == 12


async def test_run_backtest_tolerates_missing_metric_fields(fake_engine):
    """Engine version skew (a renamed field) must not kill the whole tool."""
    base = {f: 0 for f in METRIC_FIELDS}
    del base["expectancy"]  # simulate an older/newer engine without it
    fake_engine["result"] = SimpleNamespace(**base)

    result = await run_backtest("X", "2024-01-01", "2024-02-01")

    assert "error" not in result
    assert result["metrics"]["expectancy"] is None
    assert result["metrics"]["total_trades"] == 0


# ---------------------------------------------------------------------------
# Registry shape
# ---------------------------------------------------------------------------


def test_definitions_and_handlers_align():
    def_names = {d["function"]["name"] for d in BACKTEST_TOOL_DEFINITIONS}

    assert def_names == set(BACKTEST_TOOL_HANDLERS) == {"run_backtest"}
    (definition,) = BACKTEST_TOOL_DEFINITIONS
    fn = definition["function"]
    assert definition["type"] == "function"
    assert fn["description"]
    assert set(fn["parameters"]["required"]) == {"symbol", "start_date", "end_date"}
    assert fn["parameters"]["type"] == "object"
