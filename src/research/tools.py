"""LLM-callable tool registry for the BTC research lab.

Each tool is a thin Python function that the LLM can call during a chat. The
registry exposes tools in OpenAI function-calling format and provides a simple
``execute(name, arguments)`` dispatch.

This is the *agent's surface area* for research. New tools should:
- be registered in ``_TOOLS`` below
- have a clear docstring (used as the LLM tool description)
- return a structured ``ToolResult`` (success/data/error/report_id)
- be fast (<5s) and side-effect free (backtests and MC are pure-compute)
"""

from __future__ import annotations

import base64
import io
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from . import data as data_mod
from .backtest import run_backtest_from_names
from .montecarlo import simulate_block_bootstrap, simulate_gbm, simulate_regime_switching
from .scaling import describe_scaling, list_scaling_models
from .strategies import describe_strategy, list_strategies


# ---------------------------------------------------------------------------
# Report persistence
# ---------------------------------------------------------------------------

REPORTS_DIR = Path("reports")


@dataclass
class ToolResult:
    success: bool
    data: Any = None
    error: str | None = None
    report_id: str | None = None
    artifacts: dict[str, str] = field(default_factory=dict)  # name -> base64

    def to_dict(self) -> dict:
        out = {"success": self.success, "data": self.data, "error": self.error}
        if self.report_id is not None:
            out["report_id"] = self.report_id
        if self.artifacts:
            out["artifacts"] = list(self.artifacts.keys())
        return out


def _save_report(kind: str, params: dict, metrics: dict, artifacts: dict[str, bytes]) -> str:
    """Persist a report to reports/<kind>/<id>.json + <id>.<ext> for each artifact."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_id = f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
    out_dir = REPORTS_DIR / kind
    out_dir.mkdir(parents=True, exist_ok=True)
    # Save JSON metadata
    meta = {
        "id": report_id,
        "kind": kind,
        "created_at": pd.Timestamp.now("UTC").isoformat(),
        "params": params,
        "metrics": metrics,
    }
    (out_dir / f"{report_id}.json").write_text(json.dumps(meta, indent=2, default=str))
    # Save artifacts
    for name, content in artifacts.items():
        ext = "png" if name.endswith("png") else "csv" if name.endswith("csv") else "bin"
        (out_dir / f"{report_id}.{name}.{ext}").write_bytes(content)
    return report_id


def _equity_curve_png(equity: pd.Series, title: str = "Equity Curve") -> bytes:
    """Render a minimal PNG of an equity curve without matplotlib.

    We use a tiny built-in PNG writer (no external deps). If matplotlib is
    available we prefer it, but it's not in requirements-lite.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(8, 4))
        ax.plot(equity.index, equity.values, color="#10b981", linewidth=1.5)
        ax.set_title(title)
        ax.set_xlabel("Date")
        ax.set_ylabel("Equity (USD)")
        ax.grid(True, alpha=0.3)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
        plt.close(fig)
        return buf.getvalue()
    except ImportError:
        # No matplotlib -> return a tiny placeholder PNG
        return _placeholder_png()


def _drawdown_png(dd: pd.Series, title: str = "Drawdown") -> bytes:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(8, 4))
        ax.fill_between(dd.index, dd.values * 100.0, 0, color="#ef4444", alpha=0.6)
        ax.set_title(title)
        ax.set_xlabel("Date")
        ax.set_ylabel("Drawdown (%)")
        ax.grid(True, alpha=0.3)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
        plt.close(fig)
        return buf.getvalue()
    except ImportError:
        return _placeholder_png()


def _placeholder_png() -> bytes:
    """A 1x1 transparent PNG so the API contract is preserved even without matplotlib."""
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    )


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def tool_list_strategies(args: dict) -> ToolResult:
    return ToolResult(success=True, data=list_strategies())


def tool_describe_strategy(args: dict) -> ToolResult:
    name = args.get("name", "")
    if not name:
        return ToolResult(success=False, error="Missing 'name'")
    try:
        return ToolResult(success=True, data=describe_strategy(name))
    except KeyError as e:
        return ToolResult(success=False, error=str(e))


def tool_list_scaling_models(args: dict) -> ToolResult:
    return ToolResult(success=True, data=list_scaling_models())


def tool_describe_scaling_model(args: dict) -> ToolResult:
    name = args.get("name", "")
    if not name:
        return ToolResult(success=False, error="Missing 'name'")
    try:
        return ToolResult(success=True, data=describe_scaling(name))
    except KeyError as e:
        return ToolResult(success=False, error=str(e))


def tool_get_data_summary(args: dict) -> ToolResult:
    start = args.get("start")
    end = args.get("end")
    timeframe = args.get("timeframe", "daily")
    try:
        if timeframe == "hourly":
            df = data_mod.load_hourly(start=start, end=end)
        else:
            df = data_mod.load_daily(start=start, end=end)
    except Exception as e:
        return ToolResult(success=False, error=f"Failed to load data: {e}")
    if df.empty:
        return ToolResult(success=False, error="No data in range")
    return ToolResult(success=True, data=data_mod.data_summary(df))


def _loan_metadata(loan: object | None) -> dict | None:
    """Reduce an opaque Loan object to a JSON-safe metadata dict.

    The tool layer never constructs or imports Loan classes; it only forwards
    caller-supplied instances. We persist a small metadata snapshot so reports
    stay self-describing without coupling the tool layer to the loans module.
    """
    if loan is None:
        return None
    metadata: dict = {"class": type(loan).__name__}
    for attr in ("name", "principal", "apr", "start_date"):
        value = getattr(loan, attr, None)
        if value is not None:
            metadata[attr] = str(value) if attr == "start_date" else value
    return metadata


def tool_run_backtest(args: dict) -> ToolResult:
    strategy_name = args.get("strategy")
    if not strategy_name:
        return ToolResult(success=False, error="Missing 'strategy'")
    scaling_name = args.get("scaling")  # may be None
    strategy_params = args.get("strategy_params", {}) or {}
    scaling_params = args.get("scaling_params", {}) or {}
    start = args.get("start")
    end = args.get("end")
    starting_equity = float(args.get("starting_equity", 10_000.0))
    fee_bps = float(args.get("fee_bps", 10.0))
    slippage_bps = float(args.get("slippage_bps", 5.0))
    timeframe = args.get("timeframe", "daily")
    inflows = args.get("inflows")  # optional list of deposit schedules
    loan = args.get("loan")  # optional Loan instance (opaque to the tool layer)

    try:
        if timeframe == "hourly":
            df = data_mod.load_hourly(start=start, end=end)
        else:
            df = data_mod.load_daily(start=start, end=end)
    except Exception as e:
        return ToolResult(success=False, error=f"Data load failed: {e}")

    if df.empty:
        return ToolResult(success=False, error=f"No {timeframe} BTC data in range [{start}, {end}]")

    try:
        result = run_backtest_from_names(
            df,
            strategy_name=strategy_name,
            strategy_params=strategy_params,
            scaling_name=scaling_name,
            scaling_params=scaling_params,
            starting_equity=starting_equity,
            fee_bps=fee_bps,
            slippage_bps=slippage_bps,
            inflows=inflows,
            loan=loan,
        )
    except KeyError as e:
        return ToolResult(success=False, error=f"Unknown strategy or scaling: {e}")
    except Exception as e:
        return ToolResult(success=False, error=f"Backtest failed: {e}")

    # Render artifacts
    equity_png = _equity_curve_png(result.equity_curve, title=f"{strategy_name} equity")
    dd_png = _drawdown_png(result.drawdown_curve, title=f"{strategy_name} drawdown")
    artifacts = {"equity_png": equity_png, "drawdown_png": dd_png}

    report_id = _save_report(
        kind="backtest",
        params={
            "strategy": strategy_name,
            "strategy_params": strategy_params,
            "scaling": scaling_name,
            "scaling_params": scaling_params,
            "start": start,
            "end": end,
            "timeframe": timeframe,
            "starting_equity": starting_equity,
            "fee_bps": fee_bps,
            "slippage_bps": slippage_bps,
            "inflows": inflows,
            "loan": _loan_metadata(loan),
        },
        metrics=result.metrics,
        artifacts=artifacts,
    )

    return ToolResult(
        success=True,
        data={
            "metrics": result.metrics,
            "strategy": strategy_name,
            "scaling": scaling_name or "None",
            "start": result.start_date,
            "end": result.end_date,
            "starting_equity": result.starting_equity,
            "ending_equity": result.ending_equity,
            "num_trades": result.metrics["num_trades"],
        },
        report_id=report_id,
        artifacts={"equity_png": "[base64]", "drawdown_png": "[base64]"},
    )


def tool_run_montecarlo(args: dict) -> ToolResult:
    method = args.get("method", "gbm")
    n_paths = int(args.get("n_paths", 5_000))
    n_steps = int(args.get("n_steps", 365))
    starting_value = float(args.get("starting_value", 10_000.0))
    seed = args.get("seed", 42)

    try:
        if method == "gbm":
            mu = float(args.get("mu", 0.5))
            sigma = float(args.get("sigma", 0.8))
            sim = simulate_gbm(
                mu=mu,
                sigma=sigma,
                s0=starting_value,
                n_steps=n_steps,
                n_paths=n_paths,
                seed=seed,
            )
        elif method in ("block_bootstrap", "regime_switching"):
            start = args.get("start")
            end = args.get("end")
            timeframe = args.get("timeframe", "daily")
            if timeframe == "hourly":
                df = data_mod.load_hourly(start=start, end=end)
            else:
                df = data_mod.load_daily(start=start, end=end)
            if df.empty:
                return ToolResult(success=False, error=f"No {timeframe} data in range")
            returns = df["close"].pct_change().dropna()
            if method == "block_bootstrap":
                block_size = int(args.get("block_size", 21))
                sim = simulate_block_bootstrap(
                    returns=returns,
                    starting_value=starting_value,
                    n_paths=n_paths,
                    n_steps=n_steps,
                    block_size=block_size,
                    seed=seed,
                )
            else:
                sim = simulate_regime_switching(
                    returns=returns,
                    starting_value=starting_value,
                    n_paths=n_paths,
                    n_steps=n_steps,
                    seed=seed,
                )
        else:
            return ToolResult(success=False, error=f"Unknown method '{method}'")
    except Exception as e:
        return ToolResult(success=False, error=f"Simulation failed: {e}")

    report_id = _save_report(
        kind="montecarlo",
        params={"method": method, "n_paths": n_paths, "n_steps": n_steps, **sim.params},
        metrics=sim.summary,
        artifacts={},  # paths are large; skip PNG for MC in v1
    )
    return ToolResult(
        success=True,
        data=sim.summary,
        report_id=report_id,
    )


def tool_compare_strategies(args: dict) -> ToolResult:
    strategies = args.get("strategies", [])
    scaling = args.get("scaling")
    start = args.get("start")
    end = args.get("end")
    starting_equity = float(args.get("starting_equity", 10_000.0))
    timeframe = args.get("timeframe", "daily")

    if not strategies or not isinstance(strategies, list):
        return ToolResult(success=False, error="'strategies' must be a non-empty list")

    try:
        if timeframe == "hourly":
            df = data_mod.load_hourly(start=start, end=end)
        else:
            df = data_mod.load_daily(start=start, end=end)
    except Exception as e:
        return ToolResult(success=False, error=f"Data load failed: {e}")
    if df.empty:
        return ToolResult(success=False, error=f"No {timeframe} data in range")

    results = []
    for strat_spec in strategies:
        if isinstance(strat_spec, str):
            name, params = strat_spec, {}
        else:
            name = strat_spec.get("name")
            params = strat_spec.get("params", {})
        try:
            r = run_backtest_from_names(
                df,
                strategy_name=name,
                strategy_params=params,
                scaling_name=scaling,
                starting_equity=starting_equity,
            )
            results.append(
                {
                    "strategy": name,
                    "params": params,
                    "scaling": scaling,
                    "metrics": r.metrics,
                    "ending_equity": r.ending_equity,
                }
            )
        except Exception as e:
            results.append({"strategy": name, "error": str(e)})

    return ToolResult(success=True, data={"results": results, "count": len(results)})


def tool_explain_metric(args: dict) -> ToolResult:
    """Return a one-paragraph explanation of a metric."""
    name = (args.get("name") or "").lower()
    explanations = {
        "cagr": "Compound Annual Growth Rate: the smoothed annual return that would take you from start to end equity. (end/start)^(1/years) - 1.",
        "sharpe": "Sharpe ratio: mean excess return / vol. Annualized. Higher is better; >1 is good, >2 is great.",
        "sortino": "Sortino ratio: like Sharpe but uses only downside volatility. Higher is better.",
        "calmar": "Calmar ratio: CAGR / |max drawdown|. Measures return per unit of pain.",
        "max_drawdown": "Max drawdown: largest peak-to-trough decline. Returned as a negative percentage (e.g. -83%).",
        "profit_factor": "Profit factor: gross wins / gross losses. >1.5 is good, >2 is great.",
        "hit_rate": "Hit rate: fraction of closed trades that were profitable. Doesn't tell you about magnitude.",
        "volatility": "Annualized volatility: standard deviation of returns * sqrt(365). For BTC, 50-100% is typical.",
    }
    text = explanations.get(name)
    if text is None:
        return ToolResult(
            success=False,
            error=f"No explanation for '{name}'. Known: {sorted(explanations)}",
        )
    return ToolResult(success=True, data={"name": name, "explanation": text})


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_TOOLS: dict[str, Callable[[dict], ToolResult]] = {
    "list_strategies": tool_list_strategies,
    "describe_strategy": tool_describe_strategy,
    "list_scaling_models": tool_list_scaling_models,
    "describe_scaling_model": tool_describe_scaling_model,
    "get_data_summary": tool_get_data_summary,
    "run_backtest": tool_run_backtest,
    "run_montecarlo": tool_run_montecarlo,
    "compare_strategies": tool_compare_strategies,
    "explain_metric": tool_explain_metric,
}


def tool_descriptions() -> list[dict]:
    """Return tool definitions in OpenAI function-calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": "list_strategies",
                "description": "List all available buy/sell strategies for BTC research.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "describe_strategy",
                "description": "Describe a single strategy in detail (parameters, defaults, example).",
                "parameters": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_scaling_models",
                "description": "List all available position-sizing models (Kelly, fixed-fractional, vol-targeted, etc.).",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "describe_scaling_model",
                "description": "Describe one scaling model in detail.",
                "parameters": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_data_summary",
                "description": (
                    "Summarize the BTC price series in a date range: rows, first/last close, "
                    "total return, CAGR, realized vol, max drawdown, best/worst day. Use to "
                    "characterize the data before designing a study."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "start": {"type": "string", "description": "ISO date (e.g. 2018-01-01)"},
                        "end": {"type": "string", "description": "ISO date (e.g. 2024-12-31)"},
                        "timeframe": {"type": "string", "enum": ["daily", "hourly"]},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_backtest",
                "description": (
                    "Run a backtest of a strategy (+ optional scaling model) on BTC-USD over a "
                    "date range. Returns metrics, equity curve, drawdown, and a report_id. "
                    "The agent can chain multiple backtests to compare strategies."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "strategy": {"type": "string", "description": "Strategy name (e.g. DCAFixedAmount)"},
                        "strategy_params": {"type": "object"},
                        "scaling": {"type": "string", "description": "Scaling model name (optional)"},
                        "scaling_params": {"type": "object"},
                        "start": {"type": "string"},
                        "end": {"type": "string"},
                        "timeframe": {"type": "string", "enum": ["daily", "hourly"]},
                        "starting_equity": {"type": "number", "default": 10000.0},
                        "fee_bps": {"type": "number", "default": 10.0},
                        "slippage_bps": {"type": "number", "default": 5.0},
                    },
                    "required": ["strategy"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_montecarlo",
                "description": (
                    "Run a Monte Carlo simulation. Three methods: gbm (parametric), "
                    "block_bootstrap (preserves autocorrelation), regime_switching "
                    "(two-state calm/stressed). Returns distribution of terminal values and "
                    "max drawdowns, plus ruin probability."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "method": {"type": "string", "enum": ["gbm", "block_bootstrap", "regime_switching"]},
                        "n_paths": {"type": "integer", "default": 5000},
                        "n_steps": {"type": "integer", "default": 365},
                        "starting_value": {"type": "number", "default": 10000.0},
                        "mu": {"type": "number", "description": "annualized drift for GBM"},
                        "sigma": {"type": "number", "description": "annualized vol for GBM"},
                        "block_size": {"type": "integer", "description": "block size for bootstrap"},
                        "start": {"type": "string", "description": "ISO date for bootstrap data window"},
                        "end": {"type": "string"},
                        "timeframe": {"type": "string", "enum": ["daily", "hourly"]},
                        "seed": {"type": "integer", "default": 42},
                    },
                    "required": ["method"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "compare_strategies",
                "description": "Run multiple strategies over the same period and return a comparison table.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "strategies": {
                            "type": "array",
                            "items": {
                                "oneOf": [
                                    {"type": "string"},
                                    {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "params": {"type": "object"},
                                        },
                                    },
                                ]
                            },
                        },
                        "scaling": {"type": "string"},
                        "start": {"type": "string"},
                        "end": {"type": "string"},
                        "timeframe": {"type": "string", "enum": ["daily", "hourly"]},
                        "starting_equity": {"type": "number", "default": 10000.0},
                    },
                    "required": ["strategies"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "explain_metric",
                "description": "Return a short explanation of a finance/metrics term (CAGR, Sharpe, max drawdown, ...).",
                "parameters": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            },
        },
    ]


def execute(name: str, arguments: dict | None = None) -> ToolResult:
    """Dispatch a tool call by name. Returns a ``ToolResult``."""
    if name not in _TOOLS:
        return ToolResult(success=False, error=f"Unknown tool '{name}'")
    try:
        return _TOOLS[name](arguments or {})
    except Exception as e:  # last-resort safety net
        return ToolResult(success=False, error=f"Tool '{name}' crashed: {e}")


def list_tools() -> list[str]:
    return sorted(_TOOLS)
