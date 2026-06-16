"""Research lab router (B7).

Exposes the BTC research tools over HTTP:

- ``GET  /api/research/strategies``          : list strategies
- ``GET  /api/research/strategies/{name}``   : describe a strategy
- ``GET  /api/research/scaling``             : list scaling models
- ``GET  /api/research/scaling/{name}``      : describe a scaling model
- ``POST /api/research/backtest``            : run a single backtest
- ``POST /api/research/montecarlo``          : run a Monte Carlo
- ``POST /api/research/compare``             : compare strategies
- ``POST /api/research/explain-metric``      : explain a metric
- ``POST /api/research/chat``                : full agentic chat loop (NDJSON stream)
- ``GET  /api/research/reports``             : list saved reports
- ``GET  /api/research/reports/{id}``        : fetch one report
- ``GET  /api/research/data/summary``        : summarize data in a range

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

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field

from ..research import tools as research_tools

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


class CompareRequest(BaseModel):
    strategies: list[Any]  # list of names or {name, params}
    scaling: str | None = None
    start: str | None = None
    end: str | None = None
    timeframe: str = "daily"
    starting_equity: float = 10_000.0


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
    r = research_tools.tool_run_backtest(req.model_dump(exclude_none=True))
    if not r.success:
        raise HTTPException(status_code=400, detail=r.error)
    return r.to_dict()


@router.post("/montecarlo")
async def montecarlo(req: MonteCarloRequest):
    r = research_tools.tool_run_montecarlo(req.model_dump(exclude_none=True))
    if not r.success:
        raise HTTPException(status_code=400, detail=r.error)
    return r.to_dict()


@router.post("/compare")
async def compare(req: CompareRequest):
    r = research_tools.execute("compare_strategies", req.model_dump(exclude_none=True))
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


_SYSTEM_PROMPT = """You are a Bitcoin long-term research analyst. You help the user explore \
strategies, position-sizing models, and Monte Carlo outcomes for BTC over multi-year horizons.

You have tools to:
- List and describe strategies and scaling models
- Get a summary of the BTC price series
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
step. Aim to answer the user's question in <= {max_tool_calls} tool calls."""


async def _stream_ndjson(req: ChatRequest):
    """Yield NDJSON events for the chat endpoint."""
    try:
        from ..llm.model_router import ModelRouter
    except ImportError:
        # Fall back: just return an error
        yield _ndjson(
            {"type": "error", "error": "LLM runtime not available. Install llm dependencies."}
        )
        return
        # Fall back: just return an error
        yield _ndjson(
            {"type": "error", "error": "LLM runtime not available. Install llm dependencies."}
        )
        return

    # 1. Build the system prompt + tool list
    tools = research_tools.tool_descriptions()
    system_prompt = _SYSTEM_PROMPT.format(max_tool_calls=req.max_tool_calls)
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
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
    """Stream an agentic chat loop as NDJSON."""
    return StreamingResponse(
        _stream_ndjson(req),
        media_type="application/x-ndjson",
    )
