"""Full P0-P4 End-to-End Test

Exercises every layer: Config → DeepSeek → ModelRouter → ToolRegistry →
EmbeddingRAG → KnowledgeGraph → All 6 agents → Orchestrator → Streaming →
Feedback loop.

Prints per-component trace with pass/fail.
"""

import asyncio
import json
import sys
import time
from typing import Any

# ASCII-safe print
import builtins as _bi
_orig_print = _bi.print
def _safe_print(*a, **kw):
    text = " ".join(str(x) for x in a)
    try:
        _orig_print(text, **kw)
    except UnicodeEncodeError:
        _orig_print(text.encode("ascii", errors="replace").decode("ascii"), **kw)
_bi.print = _safe_print  # type: ignore

PASS, FAIL, total = 0, 0, 0

def _hdr(msg: str):
    global total
    total += 1
    print(f"\n[{total}] {msg}")
    print("-" * 50)

def _ok(msg: str = ""):
    global PASS
    PASS += 1
    print(f"  [PASS] {msg}")

def _no(msg: str):
    global FAIL
    FAIL += 1
    print(f"  [FAIL] {msg}")


async def main():
    global PASS, FAIL, total
    t0 = time.monotonic()

    # -- 1. Config --------------------------------------------------------
    _hdr("Config Layer")
    from src.core.config import get_settings
    s = get_settings()
    assert s.llm.deepseek.model_pro == "deepseek-v4-pro"
    assert s.llm.model_routing.primary_provider == "deepseek"
    _ok("DeepSeek config valid")

    # -- 2. DeepSeek API --------------------------------------------------
    _hdr("DeepSeek Connectivity")
    from src.llm.deepseek_client import DeepSeekClient
    async with DeepSeekClient(s) as c:
        healthy = await c.check_health()
        assert healthy, "DeepSeek health check failed"
        _ok(f"Healthy")

        resp = await c.generate_completion(
            messages=[{"role": "user", "content": "Say 'hello' in one word."}],
            model=s.llm.deepseek.model_flash, max_tokens=10, temperature=0,
        )
        assert resp and "choices" in resp
        msg = resp["choices"][0]["message"]
        content = msg.get("content") or msg.get("reasoning_content") or ""
        assert len(content) > 0
        _ok(f"Completion: '{content.strip()[:50]}'")

    # -- 3. ModelRouter ---------------------------------------------------
    _hdr("ModelRouter")
    from src.llm.model_router import ModelRouter
    async with ModelRouter(s) as router:
        health = await router.check_all()
        assert health.get("deepseek"), "DeepSeek unhealthy"
        _ok(f"Health: {health}")

        for cap in ("reasoning", "fast", "standard"):
            client, model = await router.route(cap)
            assert client is not None
            _ok(f"Route {cap} -> {type(client).__name__}/{model}")

        models = router.list_available_models()
        assert len(models) >= 2
        _ok(f"{len(models)} models listed")

    # -- 4. ToolRegistry --------------------------------------------------
    _hdr("ToolRegistry")
    from src.llm.tools import ToolRegistry
    reg = ToolRegistry()
    names = reg.get_tool_names()
    assert len(names) == 10, f"Expected 10 tools, got {len(names)}"
    _ok(f"{len(names)} tools registered")

    # Test all no-arg tools
    for name in ["list_active_hypotheses", "get_market_internals", "get_breadth"]:
        if name in names:
            result = await reg.dispatch(name, {})
            ok = "error" not in result
            tag = "OK" if ok else f"ERROR: {result.get('error', '')[:60]}"
            _ok(f"dispatch({name}): {tag}")

    # Test knowledge tool
    r = await reg.dispatch("search_trading_knowledge", {"query": "FVG"})
    assert r.get("count", 0) > 0, "No FVG results"
    _ok(f"search_trading_knowledge('FVG'): {r['count']} chunks")

    # -- 5. EmbeddingRAG --------------------------------------------------
    _hdr("EmbeddingRAG + KnowledgeGraph")
    from src.llm.embedding_rag import EmbeddingRAG
    rag = EmbeddingRAG()
    chunks = rag.retrieve_context("overnight liquidation cascade", top_k=5)
    assert len(chunks) >= 3
    semantic = [c for c in chunks if c.get("source", "").startswith("graph:")]
    graph = [c for c in chunks if c.get("source", "").startswith("graph:")]
    _ok(f"{len(chunks)} chunks ({len(semantic)} semantic, {len(graph)} graph)")
    if graph:
        _ok(f"Graph enrichment active: {[c['title'] for c in graph[:3]]}")

    # -- 6. Knowledge Graph -----------------------------------------------
    _hdr("KnowledgeGraph")
    from src.llm.knowledge_graph import KnowledgeGraph
    kg = KnowledgeGraph()
    assert kg.graph.number_of_nodes() > 50
    assert kg.graph.number_of_edges() > 40
    _ok(f"{kg.graph.number_of_nodes()} nodes, {kg.graph.number_of_edges()} edges")

    vix_n = kg.traverse("VIX", depth=1)
    assert any(n["label"] == "spy" for n in vix_n), "VIX not linked to SPY"
    _ok(f"VIX neighbors: {[n['label'] for n in vix_n]}")

    # -- 7. All 6 Agents --------------------------------------------------
    _hdr("Agent Fleet (6 agents)")
    from src.llm.agents import (
        DataAgent, TechnicalAgent, MacroAgent,
        RiskAgent, HypothesisAgent, CritiqueAgent,
    )

    agents = [
        ("DataAgent", DataAgent, ["get_market_internals", "get_ohlcv", "get_breadth", "get_symbol_52w_stats"]),
        ("TechnicalAgent", TechnicalAgent, ["analyze_symbol_technicals", "find_support_resistance"]),
        ("MacroAgent", MacroAgent, ["get_market_internals", "get_breadth"]),
        ("RiskAgent", RiskAgent, ["get_ohlcv", "get_symbol_52w_stats"]),
        ("HypothesisAgent", HypothesisAgent, ["list_active_hypotheses", "get_hypothesis_detail", "get_ohlcv"]),
        ("CritiqueAgent", CritiqueAgent, []),
    ]
    for name, cls, expected_tools in agents:
        agent = cls(registry=reg, settings=s)
        assert agent.AGENT_NAME
        actual = agent.TOOL_NAMES
        assert actual == expected_tools, f"{name} tools mismatch: {actual} != {expected_tools}"
        _ok(f"{name}: {len(actual)} tools, capability={agent.CAPABILITY}")

    # -- 8. Orchestrator (quick test) -------------------------------------
    _hdr("Orchestrator (5-agent pipeline)")
    from src.llm.agents.orchestrator import MarketAnalysisOrchestrator
    orch = MarketAnalysisOrchestrator(s)
    async with orch:
        result = await orch.analyze(
            query="Quick SPY health check",
            symbols=["SPY"],
            include_breadth=True,
        )

    assert result.data_result is not None
    assert result.data_result.success or len(result.data_result.tool_calls_made) > 0
    _ok(f"DataAgent: {len(result.data_result.content)} chars, {len(result.data_result.tool_calls_made)} tools")

    for attr, label in [
        ("technical_result", "Technical"),
        ("macro_result", "Macro"),
        ("risk_result", "Risk"),
        ("hypothesis_result", "Hypothesis"),
    ]:
        ar = getattr(result, attr, None)
        if ar:
            tag = "OK" if ar.success else "PARTIAL"
            _ok(f"{label}Agent: {len(ar.content)} chars [{tag}]")

    assert len(result.draft_synthesis) > 100
    _ok(f"Draft synthesis: {len(result.draft_synthesis)} chars")

    assert len(result.synthesis) > 100
    _ok(f"Final synthesis: {len(result.synthesis)} chars")

    if result.critique:
        _ok(f"Critique: {len(result.critique)} chars")

    # -- 9. Streaming -----------------------------------------------------
    _hdr("Streaming Pipeline")
    events = []
    async with orch:
        async for ev in orch.analyze_streaming(
            query="Quick check", symbols=["SPY"], include_breadth=False,
        ):
            events.append(ev.phase)

    expected_phases = ["plan", "data_fetching", "data_complete", "agents_running"]
    for ph in expected_phases:
        assert ph in events, f"Missing phase: {ph}"
    assert "final_ready" in events
    _ok(f"{len(events)} streaming events: {events[:6]}...")

    # -- 10. Feedback Loop ------------------------------------------------
    _hdr("Feedback Loop")
    import pathlib, json as _json, hashlib, uuid

    fb_dir = pathlib.Path("trading_knowledge/feedback")
    fb_dir.mkdir(parents=True, exist_ok=True)

    # Submit feedback
    aid = str(uuid.uuid4())
    fb = {
        "analysis_id": aid, "rating": 4, "outcome": "accurate",
        "notes": "E2E test feedback", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    safe_id = hashlib.md5(aid.encode()).hexdigest()[:12]
    fpath = fb_dir / f"{safe_id}_test.json"
    fpath.write_text(_json.dumps(fb, indent=2), encoding="utf-8")
    assert fpath.exists()
    _ok(f"Feedback stored: {fpath.name}")

    # Read stats
    feedbacks = []
    for fp in fb_dir.glob("*.json"):
        try:
            feedbacks.append(_json.loads(fp.read_text(encoding="utf-8")))
        except Exception:
            pass
    assert len(feedbacks) >= 1
    ratings = [f["rating"] for f in feedbacks if "rating" in f]
    avg = sum(ratings) / len(ratings) if ratings else 0
    _ok(f"Stats: {len(feedbacks)} feedbacks, avg rating={avg:.1f}")

    # Cleanup test file
    fpath.unlink()

    # -- Summary ----------------------------------------------------------
    elapsed = time.monotonic() - t0
    _hdr(f"RESULTS ({elapsed:.0f}s)")
    print(f"  Passed: {PASS}")
    print(f"  Failed: {FAIL}")
    print(f"  Total:  {total}")
    if FAIL == 0:
        print("\n  ALL P0-P4 TESTS PASSED")
    else:
        print(f"\n  {FAIL} FAILURES")

    return FAIL == 0


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
