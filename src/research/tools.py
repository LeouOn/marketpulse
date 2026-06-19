"""LLM-callable tool registry for the multi-asset research lab.

Each tool is a thin Python function that the LLM can call during a chat. The
registry exposes tools in OpenAI function-calling format and provides a simple
``execute(name, arguments, asset)`` dispatch.

This is the *agent's surface area* for research. New tools should:
- be registered in ``_TOOLS`` below
- have a clear docstring (used as the LLM tool description)
- return a structured ``ToolResult`` (success/data/error/report_id)
- be fast (<5s) and side-effect free (backtests and MC are pure-compute)
- accept an ``asset: str = "BTC"`` parameter that resolves to an
  :data:`src.research.data.AssetRegistry` entry (W4 T20)

Back-compat: ``asset`` defaults to ``"BTC"`` so existing callers
(``execute(name, args)`` with no asset context) keep working unchanged.
"""

from __future__ import annotations

import base64
import io
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from . import data as data_mod
from .backtest import run_backtest_from_names
from .data import AssetRegistry, AssetConfig
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


# ---------------------------------------------------------------------------
# Asset resolution helpers (W4 T20)
# ---------------------------------------------------------------------------


def _resolve_asset(asset: str) -> AssetConfig:
    """Resolve an asset alias to its :class:`AssetConfig`.

    Raises ``ValueError`` (not ``KeyError``) when the alias is unknown so
    callers can surface the supported set in a friendly error message.
    The router layer turns this into an HTTP 404.
    """
    cfg = AssetRegistry.get(asset)
    if cfg is None:
        raise ValueError(
            f"Unknown asset: {asset}. Supported: {sorted(AssetRegistry)}"
        )
    return cfg


def _parse_iso_date(value: str | None, default: date) -> date:
    """Parse an ISO date string; return ``default`` for ``None``/empty."""
    if not value:
        return default
    try:
        return pd.Timestamp(value).date()
    except (ValueError, TypeError):
        return default


def _load_asset_df(
    asset: str,
    start: str | None,
    end: str | None,
    timeframe: str = "daily",
) -> pd.DataFrame:
    """Load OHLCV data for ``asset`` via its registered provider.

    Uses ``cfg.data_provider().load_daily(start, end)`` (the multi-asset
    contract) for all assets, including BTC -- ``BtcProvider`` delegates
    back to the legacy :func:`src.research.data.load_daily` so the existing
    BTC CSV cache and test fixtures keep working unchanged.
    """
    cfg = _resolve_asset(asset)
    provider = cfg.data_provider()
    start_d = _parse_iso_date(start, date(1990, 1, 1))
    end_d = _parse_iso_date(end, date.today())
    if timeframe == "hourly":
        df = provider.load_intraday(start_d, end_d)
        if df is None:
            return pd.DataFrame()
        return df
    return provider.load_daily(start_d, end_d)


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


def tool_list_strategies(args: dict, asset: str = "BTC") -> ToolResult:
    return ToolResult(success=True, data=list_strategies())


def tool_describe_strategy(args: dict, asset: str = "BTC") -> ToolResult:
    name = args.get("name", "")
    if not name:
        return ToolResult(success=False, error="Missing 'name'")
    try:
        return ToolResult(success=True, data=describe_strategy(name))
    except KeyError as e:
        return ToolResult(success=False, error=str(e))


def tool_list_scaling_models(args: dict, asset: str = "BTC") -> ToolResult:
    return ToolResult(success=True, data=list_scaling_models())


def tool_describe_scaling_model(args: dict, asset: str = "BTC") -> ToolResult:
    name = args.get("name", "")
    if not name:
        return ToolResult(success=False, error="Missing 'name'")
    try:
        return ToolResult(success=True, data=describe_scaling(name))
    except KeyError as e:
        return ToolResult(success=False, error=str(e))


def tool_get_data_summary(args: dict, asset: str = "BTC") -> ToolResult:
    start = args.get("start")
    end = args.get("end")
    timeframe = args.get("timeframe", "daily")
    try:
        cfg = _resolve_asset(asset)
    except ValueError as e:
        return ToolResult(success=False, error=str(e))
    try:
        df = _load_asset_df(asset, start, end, timeframe)
    except Exception as e:
        return ToolResult(success=False, error=f"Failed to load {asset} data: {e}")
    if df.empty:
        return ToolResult(
            success=False,
            error=f"No {timeframe} {asset} data in range [{start}, {end}]",
        )
    return ToolResult(
        success=True,
        data=data_mod.data_summary(df, trading_days_per_year=cfg.trading_days_per_year),
    )


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


def tool_run_backtest(args: dict, asset: str = "BTC") -> ToolResult:
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
        cfg = _resolve_asset(asset)
    except ValueError as e:
        return ToolResult(success=False, error=str(e))

    try:
        df = _load_asset_df(asset, start, end, timeframe)
    except Exception as e:
        return ToolResult(success=False, error=f"{asset} data load failed: {e}")

    if df.empty:
        return ToolResult(
            success=False,
            error=f"No {timeframe} {asset} data in range [{start}, {end}]",
        )

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
            "asset": asset,
            "asset_class": cfg.asset_class,
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
            "asset": asset,
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


def tool_run_montecarlo(args: dict, asset: str = "BTC") -> ToolResult:
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
            try:
                df = _load_asset_df(asset, start, end, timeframe)
            except ValueError as e:
                return ToolResult(success=False, error=str(e))
            except Exception as e:
                return ToolResult(
                    success=False, error=f"{asset} data load failed: {e}"
                )
            if df.empty:
                return ToolResult(
                    success=False,
                    error=f"No {timeframe} {asset} data in range [{start}, {end}]",
                )
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
        params={
            "asset": asset,
            "method": method,
            "n_paths": n_paths,
            "n_steps": n_steps,
            **sim.params,
        },
        metrics=sim.summary,
        artifacts={},  # paths are large; skip PNG for MC in v1
    )
    return ToolResult(
        success=True,
        data={"asset": asset, **sim.summary},
        report_id=report_id,
    )


def tool_compare_strategies(args: dict, asset: str = "BTC") -> ToolResult:
    strategies = args.get("strategies", [])
    scaling = args.get("scaling")
    start = args.get("start")
    end = args.get("end")
    starting_equity = float(args.get("starting_equity", 10_000.0))
    timeframe = args.get("timeframe", "daily")

    if not strategies or not isinstance(strategies, list):
        return ToolResult(success=False, error="'strategies' must be a non-empty list")

    try:
        df = _load_asset_df(asset, start, end, timeframe)
    except ValueError as e:
        return ToolResult(success=False, error=str(e))
    except Exception as e:
        return ToolResult(success=False, error=f"{asset} data load failed: {e}")
    if df.empty:
        return ToolResult(
            success=False,
            error=f"No {timeframe} {asset} data in range [{start}, {end}]",
        )

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
                    "asset": asset,
                    "strategy": name,
                    "params": params,
                    "scaling": scaling,
                    "metrics": r.metrics,
                    "ending_equity": r.ending_equity,
                }
            )
        except Exception as e:
            results.append({"asset": asset, "strategy": name, "error": str(e)})

    return ToolResult(success=True, data={"results": results, "count": len(results)})


def tool_explain_metric(args: dict, asset: str = "BTC") -> ToolResult:
    """Return a one-paragraph explanation of a metric.

    Volatility text is asset-aware: the legacy ``"For BTC, 50-100% is typical."``
    line is replaced with an asset-specific pointer so non-BTC assets don't
    get a misleading numerical range (Metis finding).
    """
    name = (args.get("name") or "").lower()
    vol_text = (
        f"Annualized volatility: standard deviation of returns * sqrt(trading_days_per_year). "
        f"For {asset}, see asset_config for typical ranges."
    )
    explanations = {
        "cagr": "Compound Annual Growth Rate: the smoothed annual return that would take you from start to end equity. (end/start)^(1/years) - 1.",
        "sharpe": "Sharpe ratio: mean excess return / vol. Annualized. Higher is better; >1 is good, >2 is great.",
        "sortino": "Sortino ratio: like Sharpe but uses only downside volatility. Higher is better.",
        "calmar": "Calmar ratio: CAGR / |max drawdown|. Measures return per unit of pain.",
        "max_drawdown": "Max drawdown: largest peak-to-trough decline. Returned as a negative percentage (e.g. -83%).",
        "profit_factor": "Profit factor: gross wins / gross losses. >1.5 is good, >2 is great.",
        "hit_rate": "Hit rate: fraction of closed trades that were profitable. Doesn't tell you about magnitude.",
        "volatility": vol_text,
    }
    text = explanations.get(name)
    if text is None:
        return ToolResult(
            success=False,
            error=f"No explanation for '{name}'. Known: {sorted(explanations)}",
        )
    return ToolResult(success=True, data={"name": name, "explanation": text})


# ---------------------------------------------------------------------------
# Multi-asset comparison (W4 T20, Metis SC2)
# ---------------------------------------------------------------------------


def tool_compare_assets(args: dict, asset: str = "BTC") -> ToolResult:
    """Compare one strategy across multiple assets on a normalized basis.

    Per Metis SC2: returns per-asset **normalized total return series only** --
    no correlation matrix, no risk-adjusted metrics. Each asset's close series
    is rebased to 1.0 at the first timestamp so cross-asset magnitude is
    directly comparable regardless of asset scale (BTC at $40k vs GOLD at $2k).

    The ``asset`` parameter is accepted for signature symmetry with the other
    tools but ignored -- the assets under comparison come from ``args['assets']``.
    """
    assets = args.get("assets") or []
    strategy_name = args.get("strategy")
    start = args.get("start")
    end = args.get("end")

    if not assets or not isinstance(assets, list):
        return ToolResult(success=False, error="'assets' must be a non-empty list")
    if not strategy_name:
        return ToolResult(success=False, error="Missing 'strategy'")

    per_asset: dict[str, dict] = {}
    for a in assets:
        try:
            df = _load_asset_df(a, start, end, timeframe="daily")
        except ValueError as e:
            per_asset[a] = {"error": str(e)}
            continue
        except Exception as e:
            per_asset[a] = {"error": f"{a} data load failed: {e}"}
            continue
        if df.empty:
            per_asset[a] = {"error": f"No {a} data in range [{start}, {end}]"}
            continue
        try:
            r = run_backtest_from_names(
                df,
                strategy_name=strategy_name,
                strategy_params={},
                starting_equity=10_000.0,
            )
            # Normalize equity curve so first value == 1.0; return as
            # total_return series (cumulative return fraction from start).
            eq = r.equity_curve.astype(float)
            if eq.empty or eq.iloc[0] == 0:
                normalized = eq.tolist()
            else:
                normalized = (eq / eq.iloc[0]).tolist()
            per_asset[a] = {
                "normalized_total_return": normalized,
                "index": [str(t) for t in eq.index.tolist()],
                "total_return_pct": float(
                    (eq.iloc[-1] / eq.iloc[0] - 1.0) * 100.0 if eq.iloc[0] else 0.0
                ),
            }
        except Exception as e:
            per_asset[a] = {"error": f"{a} backtest failed: {e}"}

    return ToolResult(
        success=True,
        data={
            "strategy": strategy_name,
            "start": start,
            "end": end,
            "assets": per_asset,
        },
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_TOOLS: dict[str, Callable[..., ToolResult]] = {
    "list_strategies": tool_list_strategies,
    "describe_strategy": tool_describe_strategy,
    "list_scaling_models": tool_list_scaling_models,
    "describe_scaling_model": tool_describe_scaling_model,
    "get_data_summary": tool_get_data_summary,
    "run_backtest": tool_run_backtest,
    "run_montecarlo": tool_run_montecarlo,
    "compare_strategies": tool_compare_strategies,
    "compare_assets": tool_compare_assets,
    "explain_metric": tool_explain_metric,
}


def tool_descriptions() -> list[dict]:
    """Return tool definitions in OpenAI function-calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": "list_strategies",
                "description": "List all available buy/sell strategies for the multi-asset research lab.",
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
                    "Summarize the price series for an asset in a date range: rows, first/last close, "
                    "total return, CAGR, realized vol, max drawdown, best/worst day. Use to "
                    "characterize the data before designing a study. Pass 'asset' to pick the "
                    "AssetRegistry entry (BTC, GOLD, OIL, EQUITIES, HOUSING); defaults to BTC."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "start": {"type": "string", "description": "ISO date (e.g. 2018-01-01)"},
                        "end": {"type": "string", "description": "ISO date (e.g. 2024-12-31)"},
                        "timeframe": {"type": "string", "enum": ["daily", "hourly"]},
                        "asset": {
                            "type": "string",
                            "description": "Asset alias (BTC, GOLD, OIL, EQUITIES, HOUSING)",
                            "default": "BTC",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_backtest",
                "description": (
                    "Run a backtest of a strategy (+ optional scaling model) on an asset over a "
                    "date range. Returns metrics, equity curve, drawdown, and a report_id. "
                    "The agent can chain multiple backtests to compare strategies. Pass 'asset' "
                    "to pick the AssetRegistry entry; defaults to BTC."
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
                        "asset": {
                            "type": "string",
                            "description": "Asset alias (BTC, GOLD, OIL, EQUITIES, HOUSING)",
                            "default": "BTC",
                        },
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
        {
            "type": "function",
            "function": {
                "name": "compare_assets",
                "description": (
                    "Compare one strategy across multiple assets on a normalized basis "
                    "(each asset's equity curve rebased to 1.0 at the start). Returns "
                    "per-asset normalized total return series only -- no correlation "
                    "matrix or risk-adjusted metrics."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "assets": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Asset aliases (e.g. [\"BTC\", \"GOLD\", \"EQUITIES\"])",
                        },
                        "strategy": {"type": "string"},
                        "start": {"type": "string"},
                        "end": {"type": "string"},
                    },
                    "required": ["assets", "strategy"],
                },
            },
        },
    ]


def execute(
    name: str, arguments: dict | None = None, asset: str = "BTC"
) -> ToolResult:
    """Dispatch a tool call by name. Returns a ``ToolResult``.

    The ``asset`` argument threads the AssetRegistry context into tools that
    need it (``run_backtest``, ``get_data_summary``, ...). It defaults to
    ``"BTC"`` so legacy callers (``execute(name, args)``) keep working.
    """
    if name not in _TOOLS:
        return ToolResult(success=False, error=f"Unknown tool '{name}'")
    try:
        return _TOOLS[name](arguments or {}, asset=asset)
    except TypeError:
        # Tool doesn't accept ``asset`` -- fall back to the legacy signature.
        try:
            return _TOOLS[name](arguments or {})
        except Exception as e:  # last-resort safety net
            return ToolResult(success=False, error=f"Tool '{name}' crashed: {e}")
    except Exception as e:  # last-resort safety net
        return ToolResult(success=False, error=f"Tool '{name}' crashed: {e}")


def list_tools() -> list[str]:
    return sorted(_TOOLS)
