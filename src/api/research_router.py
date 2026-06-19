"""Research lab router (B7 + W4 T20 multi-asset).

Exposes the multi-asset research tools over HTTP:

- ``GET  /api/research/strategies``          : list strategies
- ``GET  /api/research/strategies/{name}``   : describe a strategy
- ``GET  /api/research/scaling``             : list scaling models
- ``GET  /api/research/scaling/{name}``      : describe a scaling model
- ``POST /api/research/backtest``            : run a single backtest (BTC default)
- ``POST /api/research/montecarlo``          : run a Monte Carlo (BTC default)
- ``POST /api/research/compare``             : compare strategies OR assets
- ``POST /api/research/explain-metric``      : explain a metric
- ``POST /api/research/chat``                : full agentic chat loop (BTC default)
- ``GET  /api/research/reports``             : list saved reports
- ``GET  /api/research/reports/{id}``        : fetch one report
- ``GET  /api/research/data/summary``        : summarize data in a range

Multi-asset routes (W4 T20):

- ``GET  /api/research/assets``              : list AssetRegistry keys
- ``GET  /api/research/{asset}/data``        : cached OHLCV for an asset
- ``POST /api/research/{asset}/backtest``    : backtest with asset context
- ``POST /api/research/{asset}/montecarlo``  : MC with asset context
- ``GET  /api/research/{asset}/regime``      : current regime + narrative
- ``GET  /api/research/regimes``             : regime tape over a date range
- ``POST /api/research/chat/{asset}``        : asset-scoped chat

Existing BTC routes are preserved verbatim -- the multi-asset routes default
to ``asset='BTC'`` so legacy callers see no change.

The chat endpoint streams NDJSON events: ``{type, ...}`` where ``type`` is one
of ``token`` (LLM output), ``tool_call``, ``tool_result``, ``final``,
``error``. The frontend renders these as a chat with mini tool cards.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field

from ..research import tools as research_tools
from ..research.data import AssetRegistry, AssetConfig
from ..research.strategies import _REGISTRY

router = APIRouter(prefix="/api/research", tags=["research"])


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------


class BacktestRequest(BaseModel):
    strategy: str
    strategy_params: dict[str, Any] | None = None
    scaling: str | None = None
    scaling_params: dict[str, Any] | None = None
    start: str | None = None
    end: str | None = None
    timeframe: str = "daily"
    starting_equity: float = 10_000.0
    fee_bps: float = 10.0
    slippage_bps: float = 5.0
    # W4 T20: multi-asset + regime gating hooks.
    asset: str = "BTC"
    regime_gating: bool = False
    regime_alpha: float = 1.0


class MonteCarloRequest(BaseModel):
    method: str = "gbm"
    n_paths: int = 5_000
    n_steps: int = 365
    starting_value: float = 10_000.0
    mu: float | None = None
    sigma: float | None = None
    block_size: int = 21
    start: str | None = None
    end: str | None = None
    timeframe: str = "daily"
    seed: int = 42
    # W4 T20: asset context for bootstrap methods.
    asset: str = "BTC"


class CompareRequest(BaseModel):
    """Polymorphic compare: pass ``strategies`` for legacy single-asset
    strategy comparison, OR pass ``assets`` + ``strategy`` for multi-asset
    comparison (Metis SC2: normalized total return only).

    The router dispatches based on which field is set.
    """

    # Legacy strategies-comparison mode (back-compat).
    strategies: list[Any] | None = None  # list of names or {name, params}
    scaling: str | None = None
    timeframe: str = "daily"
    starting_equity: float = 10_000.0
    # New multi-asset mode (W4 T20).
    assets: list[str] | None = None
    strategy: str | None = None
    # Common.
    start: str | None = None
    end: str | None = None


class MultiAssetCompareRequest(BaseModel):
    """Explicit multi-asset compare body (Metis SC2).

    Mirrors the ``assets`` / ``strategy`` branch of :class:`CompareRequest`
    but as its own model for callers that prefer an unambiguous schema.
    """

    assets: list[str]
    strategy: str
    start: str | None = None
    end: str | None = None


class ExplainMetricRequest(BaseModel):
    name: str


class ChatMessage(BaseModel):
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str
    name: str | None = None  # tool name, when role=="tool"
    tool_call_id: str | None = None


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    max_tool_calls: int = 5
    model: str | None = None  # if None, use default (MiniMax-M3 via ModelRouter)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_asset(asset: str) -> AssetConfig:
    """Resolve ``asset`` against the :data:`AssetRegistry` or HTTP 404.

    Used by every ``/{asset}/...`` route so the validation is in one place.
    """
    cfg = AssetRegistry.get(asset)
    if cfg is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Unknown asset: {asset}. "
                f"Supported: {sorted(AssetRegistry)}"
            ),
        )
    return cfg


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/strategies")
async def list_strategies():
    return research_tools.tool_list_strategies({}).to_dict()


@router.get("/strategies/{name}")
async def describe_strategy(name: str):
    r = research_tools.tool_describe_strategy({"name": name})
    if not r.success:
        raise HTTPException(status_code=404, detail=r.error)
    return r.to_dict()


@router.get("/scaling")
async def list_scaling():
    return research_tools.tool_list_scaling_models({}).to_dict()


@router.get("/scaling/{name}")
async def describe_scaling(name: str):
    r = research_tools.tool_describe_scaling_model({"name": name})
    if not r.success:
        raise HTTPException(status_code=404, detail=r.error)
    return r.to_dict()


@router.get("/data/summary")
async def data_summary(start: str | None = None, end: str | None = None, timeframe: str = "daily"):
    r = research_tools.tool_get_data_summary({"start": start, "end": end, "timeframe": timeframe})
    if not r.success:
        raise HTTPException(status_code=400, detail=r.error)
    return r.to_dict()


@router.post("/backtest")
async def backtest(req: BacktestRequest):
    """Legacy single-asset backtest. ``asset`` defaults to BTC (back-compat)."""
    r = research_tools.tool_run_backtest(
        req.model_dump(exclude_none=True), asset=req.asset
    )
    if not r.success:
        raise HTTPException(status_code=400, detail=r.error)
    return r.to_dict()


@router.post("/montecarlo")
async def montecarlo(req: MonteCarloRequest):
    """Legacy Monte Carlo. ``asset`` defaults to BTC (back-compat)."""
    r = research_tools.tool_run_montecarlo(
        req.model_dump(exclude_none=True), asset=req.asset
    )
    if not r.success:
        raise HTTPException(status_code=400, detail=r.error)
    return r.to_dict()


@router.post("/compare")
async def compare(req: CompareRequest):
    """Polymorphic compare: strategies (legacy) OR assets (multi-asset).

    The presence of ``assets`` in the body selects the multi-asset path;
    otherwise we fall through to the legacy strategies-comparison path so
    existing callers see no change.
    """
    if req.assets:
        # Multi-asset compare (Metis SC2: normalized total return only).
        if not req.strategy:
            raise HTTPException(
                status_code=400,
                detail="'strategy' is required when 'assets' is provided",
            )
        # Validate every asset up front so a typo 404s before any work.
        for a in req.assets:
            _require_asset(a)
        r = research_tools.tool_compare_assets(
            {
                "assets": req.assets,
                "strategy": req.strategy,
                "start": req.start,
                "end": req.end,
            }
        )
        if not r.success:
            raise HTTPException(status_code=400, detail=r.error)
        return r.to_dict()

    # Legacy strategies-comparison path.
    if not req.strategies:
        raise HTTPException(
            status_code=400,
            detail="Provide either 'strategies' (legacy) or 'assets' + 'strategy' (multi-asset)",
        )
    r = research_tools.execute(
        "compare_strategies", req.model_dump(exclude_none=True)
    )
    if not r.success:
        raise HTTPException(status_code=400, detail=r.error)
    return r.to_dict()


@router.post("/explain-metric")
async def explain_metric(req: ExplainMetricRequest):
    r = research_tools.tool_explain_metric({"name": req.name})
    if not r.success:
        raise HTTPException(status_code=404, detail=r.error)
    return r.to_dict()


@router.get("/reports")
async def list_reports(kind: str | None = None, limit: int = 50):
    """List saved reports, newest first. Optional filter by kind."""
    from ..research import tools as _tools

    root = _tools.REPORTS_DIR
    if not root.exists():
        return {"reports": []}
    reports = []
    kinds = [kind] if kind else [p.name for p in root.iterdir() if p.is_dir()]
    for k in kinds:
        d = root / k
        if not d.exists():
            continue
        for f in sorted(d.glob("*.json"), reverse=True)[:limit]:
            try:
                meta = json.loads(f.read_text())
                reports.append(
                    {
                        "id": meta["id"],
                        "kind": meta["kind"],
                        "created_at": meta.get("created_at"),
                        "params": meta.get("params", {}),
                        "metrics_summary": _summarize_metrics(meta.get("metrics", {})),
                    }
                )
            except Exception:
                continue
    reports.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return {"reports": reports[:limit]}


def _summarize_metrics(metrics: dict) -> dict:
    """Pick a few key metrics for the list view."""
    if not metrics:
        return {}
    return {
        k: metrics[k]
        for k in (
            "total_return_pct",
            "cagr_pct",
            "sharpe",
            "max_drawdown_pct",
            "num_trades",
            "terminal_median",
            "prob_profit_pct",
        )
        if k in metrics
    }


@router.get("/reports/{report_id}")
async def get_report(report_id: str):
    """Fetch a single report (JSON metadata + small metrics)."""
    from ..research import tools as _tools

    root = _tools.REPORTS_DIR
    if not root.exists():
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    for kind_dir in root.iterdir():
        f = kind_dir / f"{report_id}.json"
        if f.exists():
            return json.loads(f.read_text())
    raise HTTPException(status_code=404, detail=f"Report {report_id} not found")


@router.get("/reports/{report_id}/image/{kind}")
async def get_report_image(report_id: str, kind: str):
    """Fetch a chart PNG for a report. ``kind`` is ``equity_png`` or ``drawdown_png``."""
    from ..research import tools as _tools

    root = _tools.REPORTS_DIR
    if not root.exists():
        raise HTTPException(status_code=404, detail=f"Image {kind} for {report_id} not found")
    for kind_dir in root.iterdir():
        f = kind_dir / f"{report_id}.{kind}.png"
        if f.exists():
            from fastapi.responses import FileResponse

            return FileResponse(f, media_type="image/png")
    raise HTTPException(status_code=404, detail=f"Image {kind} for {report_id} not found")


# ---------------------------------------------------------------------------
# Chat endpoint
# ---------------------------------------------------------------------------


def system_prompt(asset: str = "BTC") -> str:
    """Asset-parameterized system prompt for research chat.

    Metis MUST NOT (W4): the prompt must NOT be a module-level constant for
    multi-asset use -- it must be a function parameterized by ``asset`` so
    the chat agent's identity, calendar, and available strategies reflect
    the asset the user is researching.

    Unknown assets fall back gracefully: the literal asset key is interpolated
    into the prompt (no exception) so an operator typo doesn't crash the chat.

    The prompt body (tools list, "Always:" rules, risk caveat) is preserved
    verbatim from the original BTC-only prompt; only the asset-specific
    opening sentences are parameterized.
    """
    cfg = AssetRegistry.get(asset)
    if cfg is not None:
        asset_name = cfg.display_name
        asset_class = cfg.asset_class
        calendar = cfg.calendar
    else:
        # Graceful fallback for unknown assets -- don't crash the chat.
        asset_name = asset
        asset_class = "unknown"
        calendar = "unknown"

    return f"""You are a {asset_name} long-term research analyst. You help the user explore \
strategies, position-sizing models, and Monte Carlo outcomes for {asset_name} over multi-year horizons.

Asset context: asset_class={asset_class}, calendar={calendar}. \
Strategies available: {sorted(_REGISTRY.keys()) if _REGISTRY else 'loading...'}.

You have tools to:
- List and describe strategies and scaling models
- Get a summary of the {asset_name} price series
- Run backtests and compare strategies
- Run Monte Carlo simulations
- Explain finance metrics

Always:
1. If the user asks an open question, use tools to ground your answer in actual data.
2. After running a backtest, summarize the key metrics in plain language.
3. When comparing strategies, present a table.
4. Add a brief risk caveat: past performance does not guarantee future results; this is not \
financial advice.

When you call a tool, the result is appended to the conversation. Use it to inform your next \
step. Aim to answer the user's question in <= {{max_tool_calls}} tool calls."""


# Back-compat: any code that imported the legacy ``_SYSTEM_PROMPT`` constant
# gets the BTC default. New code should call ``system_prompt(asset)`` directly.
# (Metis MUST NOT was about NOT using a constant for multi-asset -- keeping a
# BTC-only alias for back-compat is explicitly allowed by the task spec.)
_SYSTEM_PROMPT: str = system_prompt("BTC")


async def _stream_ndjson(req: ChatRequest, asset: str = "BTC"):
    """Yield NDJSON events for the chat endpoint.

    ``asset`` selects the AssetRegistry entry whose context is injected into
    the system prompt; defaults to BTC for back-compat with ``/chat``.
    """
    try:
        from ..llm.model_router import ModelRouter
    except ImportError:
        # Fall back: just return an error
        yield _ndjson(
            {"type": "error", "error": "LLM runtime not available. Install llm dependencies."}
        )
        return

    # 1. Build the system prompt + tool list
    tools = research_tools.tool_descriptions()
    # Note: system_prompt() returns a template with {max_tool_calls} placeholder.
    prompt_template = system_prompt(asset)
    system_content = prompt_template.format(max_tool_calls=req.max_tool_calls)
    messages: list[dict] = [{"role": "system", "content": system_content}]
    for m in req.messages:
        messages.append({"role": m.role, "content": m.content})

    # 2. Loop: call LLM -> maybe tool call -> execute -> repeat
    try:
        async with ModelRouter() as router:
            for turn in range(req.max_tool_calls + 1):
                yield _ndjson(
                    {
                        "type": "turn_start",
                        "turn": turn,
                        "messages_so_far": len(messages),
                    }
                )

                # Call the model
                try:
                    response = await router.generate(
                        messages=messages,
                        capability="structured_output",
                        max_tokens=800,
                        temperature=0.3,
                        tools=tools,
                    )
                except Exception as e:
                    logger.exception("LLM call failed")
                    yield _ndjson({"type": "error", "error": f"LLM call failed: {e}"})
                    return

                if not response:
                    yield _ndjson({"type": "error", "error": "LLM returned no response"})
                    return

                choice = response.get("choices", [{}])[0]
                msg = choice.get("message", {})
                content = msg.get("content", "") or ""
                tool_calls = msg.get("tool_calls") or []

                # Stream the assistant's text content
                if content:
                    yield _ndjson({"type": "token", "content": content})

                # No tool calls -> we're done
                if not tool_calls:
                    messages.append({"role": "assistant", "content": content})
                    yield _ndjson({"type": "final", "content": content, "messages": len(messages)})
                    return

                # Append assistant message
                messages.append(
                    {
                        "role": "assistant",
                        "content": content,
                        "tool_calls": tool_calls,
                    }
                )

                # Execute each tool call
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    name = fn.get("name")
                    args_raw = fn.get("arguments", "{}")
                    try:
                        args = json.loads(args_raw) if isinstance(args_raw, str) else (args_raw or {})
                    except json.JSONDecodeError:
                        args = {}
                    yield _ndjson(
                        {
                            "type": "tool_call",
                            "name": name,
                            "arguments": args,
                            "id": tc.get("id"),
                        }
                    )
                    result = research_tools.execute(name, args)
                    yield _ndjson(
                        {
                            "type": "tool_result",
                            "name": name,
                            "success": result.success,
                            "data": result.data if result.success else None,
                            "error": result.error,
                            "report_id": result.report_id,
                        }
                    )
                    # Append tool result to the message history
                    messages.append(
                        {
                            "role": "tool",
                            "name": name,
                            "content": json.dumps(
                                {
                                    "success": result.success,
                                    "data": result.data,
                                    "error": result.error,
                                    "report_id": result.report_id,
                                },
                                default=str,
                            ),
                            "tool_call_id": tc.get("id"),
                        }
                    )

            # If we hit the cap without a final answer, force a final synthesis
            yield _ndjson(
                {"type": "warning", "message": f"Hit max_tool_calls={req.max_tool_calls}; forcing final answer."}
            )
            response = await router.generate(
                messages=messages + [{"role": "user", "content": "Please summarize your findings now."}],
                capability="standard",
                max_tokens=600,
                temperature=0.3,
            )
            if response:
                content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
                yield _ndjson({"type": "final", "content": content, "messages": len(messages)})
    except Exception as e:
        logger.exception("Chat loop failed")
        yield _ndjson({"type": "error", "error": f"Chat loop failed: {e}"})


def _ndjson(obj: dict) -> str:
    return json.dumps(obj, default=str) + "\n"


@router.post("/chat")
async def chat(req: ChatRequest):
    """Stream an agentic chat loop as NDJSON. BTC default (back-compat)."""
    return StreamingResponse(
        _stream_ndjson(req, asset="BTC"),
        media_type="application/x-ndjson",
    )


# ---------------------------------------------------------------------------
# Multi-asset routes (W4 T20)
# ---------------------------------------------------------------------------
#
# These routes expose the AssetRegistry-backed multi-asset surface. Each
# ``/{asset}/...`` route validates the asset up front via :func:`_require_asset`
# (404 on unknown alias) before delegating to the underlying tool. Existing
# BTC routes (``/backtest``, ``/chat``, ...) keep working unchanged -- they
# dispatch with ``asset='BTC'`` implicitly.
#
# Route ordering note: literal routes (``/assets``, ``/regimes``) are declared
# before the ``/{asset}/...`` patterns so FastAPI matches them first. The
# 2-segment ``/{asset}/data`` cannot shadow the 2-segment ``/data/summary``
# because the second literal segment differs.


@router.get("/assets")
async def list_assets():
    """List every asset in the :data:`AssetRegistry` with its display name."""
    assets = [
        {
            "key": key,
            "display_name": cfg.display_name,
            "asset_class": cfg.asset_class,
            "calendar": cfg.calendar,
            "ticker": cfg.ticker,
            "tradeable": cfg.tradeable,
        }
        for key, cfg in AssetRegistry.items()
    ]
    return {
        "success": True,
        "data": {
            "assets": assets,
            "count": len(assets),
        },
    }


@router.get("/regimes")
async def regimes_tape(start: str | None = None, end: str | None = None):
    """Return the regime tape (dominant regime per day) over a date range.

    Backed by the rules-based classifier (deterministic). If the macro factor
    frame cannot be loaded (e.g. FRED key missing in dev), returns HTTP 503
    with a clear message rather than crashing.
    """
    try:
        from src.research.macro.factors import MacroFactorProvider
        from src.research.macro.regimes import RulesBasedClassifier, generate_regime_tape
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Macro layer unavailable: {e}",
        )

    try:
        provider = MacroFactorProvider()
        factor_df = provider.load_frame(start=start, end=end)
    except Exception as e:
        logger.warning(f"regimes tape: factor load failed: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Macro factor data unavailable: {e}",
        )

    if factor_df is None or factor_df.empty:
        raise HTTPException(
            status_code=503,
            detail="No macro factor data in the requested range.",
        )

    tape = generate_regime_tape(factor_df, classifier=RulesBasedClassifier())
    # Serialize: index -> iso date, dominant_regime column + regime probs.
    records = []
    for ts, row in tape.iterrows():
        if isinstance(ts, pd.Timestamp):
            date_str = ts.date().isoformat()
        else:
            date_str = str(ts)
        rec = {"date": date_str, "dominant_regime": row["dominant_regime"]}
        for col in ("RISK_ON", "DEFLATION_SCARE", "INFLATION_ACCEL", "REAL_YIELD_SHOCK", "RECESSION"):
            if col in row:
                rec[col] = float(row[col])
        records.append(rec)
    return {
        "success": True,
        "data": {
            "regimes": records,
            "count": len(records),
            "start": records[0]["date"] if records else None,
            "end": records[-1]["date"] if records else None,
        },
    }


def pd_timestamp_to_date(ts: Any) -> Any:
    """Coerce a pandas Timestamp to a date string; tolerate plain dates.

    Kept for back-compat with any external callers; the ``/regimes`` route
    above now inlines this logic to avoid an extra function call in the loop.
    """
    if isinstance(ts, pd.Timestamp):
        return ts.date().isoformat()
    return str(ts)


@router.get("/{asset}/data")
async def get_asset_data(
    asset: str,
    start: str | None = None,
    end: str | None = None,
    timeframe: str = "daily",
    limit: int = 1000,
):
    """Return cached OHLCV for ``asset`` as JSON."""
    _require_asset(asset)
    r = research_tools.tool_get_data_summary(
        {"start": start, "end": end, "timeframe": timeframe}, asset=asset
    )
    if not r.success:
        raise HTTPException(status_code=400, detail=r.error)
    # Also return the raw OHLCV rows (capped at ``limit``) for charting.
    try:
        df = research_tools._load_asset_df(asset, start, end, timeframe)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"{asset} data load failed: {e}")

    if df.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No {timeframe} {asset} data in range [{start}, {end}]",
        )

    # Cap rows: if more than ``limit``, take evenly-spaced samples for chart fidelity.
    if len(df) > limit:
        step = max(1, len(df) // limit)
        df_sampled = df.iloc[::step].head(limit)
    else:
        df_sampled = df

    ohlcv_rows = []
    for _, row in df_sampled.iterrows():
        ohlcv_rows.append(
            {
                "ts": str(row["ts"]),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row.get("volume", 0.0)) if "volume" in row else None,
            }
        )

    return {
        "success": True,
        "data": {
            "asset": asset,
            "timeframe": timeframe,
            "rows": int(len(df)),
            "returned": len(ohlcv_rows),
            "start": str(df["ts"].min()),
            "end": str(df["ts"].max()),
            "summary": r.data,
            "ohlcv": ohlcv_rows,
        },
    }


@router.post("/{asset}/backtest")
async def asset_backtest(asset: str, req: BacktestRequest):
    """Run a backtest scoped to ``asset`` (overrides any ``asset`` in the body)."""
    _require_asset(asset)
    payload = req.model_dump(exclude_none=True)
    payload["asset"] = asset  # path param wins
    r = research_tools.tool_run_backtest(payload, asset=asset)
    if not r.success:
        raise HTTPException(status_code=400, detail=r.error)
    return r.to_dict()


@router.post("/{asset}/montecarlo")
async def asset_montecarlo(asset: str, req: MonteCarloRequest):
    """Run a Monte Carlo scoped to ``asset`` (overrides any ``asset`` in the body)."""
    _require_asset(asset)
    payload = req.model_dump(exclude_none=True)
    payload["asset"] = asset
    r = research_tools.tool_run_montecarlo(payload, asset=asset)
    if not r.success:
        raise HTTPException(status_code=400, detail=r.error)
    return r.to_dict()


@router.get("/{asset}/regime")
async def asset_regime(asset: str, date: str | None = None):
    """Current (or as-of ``date``) macro regime + narrative for ``asset``.

    Rules-only by default (deterministic, backtest-safe). Returns HTTP 503
    if the macro factor frame cannot be loaded.
    """
    _require_asset(asset)
    try:
        from src.research.macro.factors import MacroFactorProvider
        from src.research.macro.model import MacroRegimeModel
        from src.research.macro.regimes import RulesBasedClassifier
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Macro layer unavailable: {e}",
        )

    try:
        provider = MacroFactorProvider()
        factor_df = provider.load_frame()
    except Exception as e:
        logger.warning(f"asset_regime: factor load failed: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Macro factor data unavailable: {e}",
        )

    if factor_df is None or factor_df.empty:
        raise HTTPException(
            status_code=503,
            detail="No macro factor data available.",
        )

    model = MacroRegimeModel(rules=RulesBasedClassifier(), judge=None)
    asof = datetime.fromisoformat(date) if date else None
    try:
        result = await model.classify(
            factor_df=factor_df,
            alpha=1.0,  # rules-only
            use_llm=False,
            timestamp=asof,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "success": True,
        "data": {
            "asset": asset,
            "regime": result.regime.value,
            "probs": {r.value: float(p) for r, p in result.probs.items()},
            "source": result.source,
            "narrative": result.narrative,
            "timestamp": str(result.timestamp) if result.timestamp else None,
        },
    }


@router.post("/chat/{asset}")
async def chat_asset(asset: str, req: ChatRequest):
    """Asset-scoped agentic chat. Threads ``asset`` into the system prompt."""
    _require_asset(asset)
    return StreamingResponse(
        _stream_ndjson(req, asset=asset),
        media_type="application/x-ndjson",
    )
