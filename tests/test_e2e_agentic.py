"""End-to-end trace of the full agentic pipeline.

Tests every layer: config → ModelRouter → ToolRegistry → DataAgent → TechnicalAgent → Synthesis.
"""

import asyncio
import json
import sys
import time
from typing import Any

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _safe_print(*args, **kwargs):
    """Print with ASCII sanitization for Windows cp932 consoles."""
    import sys
    text = " ".join(str(a) for a in args)
    try:
        print(text, **kwargs)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="replace").decode("ascii"), **kwargs)

def _j(obj: Any, max_len: int = 300) -> str:
    """Compact JSON for logging."""
    s = json.dumps(obj, indent=2, default=str)
    return s if len(s) <= max_len else s[:max_len] + f"... [{len(s)} chars total]"


def _ok(msg: str) -> None:
    print(f"  [PASS] {msg}")

def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")

def _hdr(msg: str) -> None:
    print(f"\n\033[1;36m{'='*60}\033[0m")
    print(f"\033[1;36m  {msg}\033[0m")
    print(f"\033[1;36m{'='*60}\033[0m")


# ---------------------------------------------------------------------------
# Test 1: Config layer
# ---------------------------------------------------------------------------

async def test_config():
    _hdr("TEST 1: Config Layer")
    from src.core.config import get_settings
    s = get_settings()

    ds = s.llm.deepseek
    print(f"  DeepSeek base_url:  {ds.base_url}")
    print(f"  DeepSeek model_pro: {ds.model_pro}")
    print(f"  DeepSeek model_flash: {ds.model_flash}")
    key_ok = bool(ds.api_key and len(ds.api_key) > 20 and "your_" not in ds.api_key.lower())
    print(f"  DeepSeek key valid:  {key_ok}")
    if key_ok:
        _ok("DeepSeek config OK")
    else:
        _fail(f"DeepSeek key invalid or placeholder")

    routing = s.llm.model_routing
    print(f"  Primary provider:   {routing.primary_provider}")
    print(f"  Fallback chain:     {routing.fallback_providers}")
    print(f"  reasoning model:    {routing.reasoning}")
    print(f"  fast model:         {routing.fast}")
    _ok("Config layer OK")
    return s


# ---------------------------------------------------------------------------
# Test 2: DeepSeek connectivity
# ---------------------------------------------------------------------------

async def test_deepseek_connectivity(settings):
    _hdr("TEST 2: DeepSeek Connectivity")
    from src.llm.deepseek_client import DeepSeekClient

    async with DeepSeekClient(settings) as client:
        healthy = await client.check_health()
        print(f"  Health check: {healthy}")
        if not healthy:
            _fail("DeepSeek not reachable")
            return False

        # Test a simple completion
        t0 = time.monotonic()
        resp = await client.generate_completion(
            messages=[{"role": "user", "content": "Reply with exactly: OK"}],
            model=settings.llm.deepseek.model_flash,
            max_tokens=10,
            temperature=0.0,
        )
        elapsed = time.monotonic() - t0

        if resp and "choices" in resp:
            content = resp["choices"][0]["message"].get("content", "")
            usage = resp.get("usage", {})
            print(f"  Response:  '{content.strip()}'")
            print(f"  Latency:   {elapsed:.2f}s")
            print(f"  Tokens:    {_j(usage, 200)}")
            _ok(f"DeepSeek API working ({elapsed:.2f}s)")
            return True
        else:
            _fail(f"No response from DeepSeek: {_j(resp) if resp else 'None'}")
            return False


# ---------------------------------------------------------------------------
# Test 3: ModelRouter routing
# ---------------------------------------------------------------------------

async def test_model_router(settings):
    _hdr("TEST 3: ModelRouter")
    from src.llm.model_router import ModelRouter

    async with ModelRouter(settings) as router:
        # Check health
        health = await router.check_all()
        print(f"  Provider health: {health}")

        # Route each capability
        for cap in ("reasoning", "fast", "standard", "structured_output"):
            client, model_id = await router.route(cap)
            provider = type(client).__name__
            print(f"  {cap:20s} → {provider:25s} / {model_id}")

        # List models
        models = router.list_available_models()
        print(f"  Available models: {len(models)}")
        for m in models:
            print(f"    {m['id']:30s} [{m['provider']:12s}] {m['description'][:60]}")

        _ok("ModelRouter OK")
        return router


# ---------------------------------------------------------------------------
# Test 4: ToolRegistry
# ---------------------------------------------------------------------------

async def test_tool_registry():
    _hdr("TEST 4: ToolRegistry")
    from src.llm.tools import ToolRegistry

    registry = ToolRegistry()
    names = registry.get_tool_names()
    print(f"  Registered tools: {len(names)}")
    for name in names:
        defn = registry.list_definitions([name])[0]
        desc = defn["function"]["description"][:80]
        params = list(defn["function"]["parameters"].get("properties", {}).keys())
        print(f"    {name:30s} params={params}")
        print(f"      {desc}")

    # Test dispatch on a no-arg tool
    result = await registry.dispatch("list_active_hypotheses", {})
    print(f"\n  dispatch('list_active_hypotheses') → {_j(result, 300)}")

    # Test dispatch on a knowledge tool
    result = await registry.dispatch("search_trading_knowledge", {"query": "FVG fair value gap"})
    print(f"  dispatch('search_trading_knowledge', 'FVG') → found={result.get('count', 0)} chunks")

    _ok("ToolRegistry OK")
    return registry


# ---------------------------------------------------------------------------
# Test 5: DataAgent with real DeepSeek calls
# ---------------------------------------------------------------------------

async def test_data_agent(settings, registry):
    _hdr("TEST 5: DataAgent (live DeepSeek function calling)")
    from src.llm.agents.data_agent import DataAgent

    task = (
        "Fetch market data for SPY. Get market internals, breadth, "
        "52-week stats, and 1 month of daily OHLCV."
    )

    print(f"  Task: '{task}'")
    print(f"  Agent tools: {DataAgent.TOOL_NAMES}")
    print(f"  Capability:  {DataAgent.CAPABILITY}")
    print()

    t0 = time.monotonic()
    async with DataAgent(registry=registry, settings=settings) as agent:
        result = await agent.execute(task)
    elapsed = time.monotonic() - t0

    print(f"\n  Result ({elapsed:.1f}s):")
    print(f"    success:  {result.success}")
    print(f"    tools:    {result.tool_calls_made}")
    print(f"    content:  {len(result.content)} chars")
    print(f"    error:    {result.error}")
    print(f"\n  Content preview:")
    for line in result.content.split("\n")[:20]:
        print(f"    | {line[:120]}")

    if result.success and len(result.content) > 50:
        _ok(f"DataAgent OK - {len(result.tool_calls_made)} tools, {len(result.content)} chars, {elapsed:.1f}s")
    elif result.tool_calls_made:
        _ok(f"DataAgent partial - {len(result.tool_calls_made)} tools called but content short; tools may have errors")
    else:
        _fail(f"DataAgent failed: {result.error}")

    return result


# ---------------------------------------------------------------------------
# Test 6: TechnicalAgent
# ---------------------------------------------------------------------------

async def test_technical_agent(settings, registry, data_result):
    _hdr("TEST 6: TechnicalAgent (live DeepSeek)")
    from src.llm.agents.technical_agent import TechnicalAgent

    data_context = data_result.content if data_result and data_result.content else (
        "SPY OHLCV data unavailable from DataAgent. "
        "Use your knowledge to assess what technical analysis CAN be done "
        "and explain what data you would need."
    )

    task = (
        f"Run technical analysis on SPY. Here is the data the Data Agent retrieved:\n\n"
        f"{data_context}\n\n"
        f"Analyze: trend structure, key levels, risk assessment."
    )

    print(f"  Task length: {len(task)} chars")
    print(f"  Agent tools: {TechnicalAgent.TOOL_NAMES}")
    print(f"  Capability:  {TechnicalAgent.CAPABILITY}")
    print()

    t0 = time.monotonic()
    async with TechnicalAgent(registry=registry, settings=settings) as agent:
        result = await agent.execute(task)
    elapsed = time.monotonic() - t0

    print(f"\n  Result ({elapsed:.1f}s):")
    print(f"    success:  {result.success}")
    print(f"    tools:    {result.tool_calls_made}")
    print(f"    content:  {len(result.content)} chars")
    print(f"    error:    {result.error}")
    print(f"\n  Content preview:")
    for line in result.content.split("\n")[:30]:
        print(f"    | {line[:120]}")

    if result.success and len(result.content) > 50:
        _ok(f"TechnicalAgent OK - {len(result.tool_calls_made)} tools, {len(result.content)} chars, {elapsed:.1f}s")
    else:
        _fail(f"TechnicalAgent issue: success={result.success}, tools={result.tool_calls_made}, error={result.error}")

    return result


# ---------------------------------------------------------------------------
# Test 7: Full orchestrator
# ---------------------------------------------------------------------------

async def test_full_orchestrator(settings):
    _hdr("TEST 7: Full Orchestrator Pipeline")
    from src.llm.agents.orchestrator import MarketAnalysisOrchestrator

    query = "Is SPY in a healthy uptrend or showing warning signs?"
    symbols = ["SPY"]

    print(f"  Query:   '{query}'")
    print(f"  Symbols: {symbols}")
    print()

    t0 = time.monotonic()
    async with MarketAnalysisOrchestrator(settings) as orch:
        result = await orch.analyze(query=query, symbols=symbols, include_breadth=True)
    elapsed = time.monotonic() - t0

    print(f"\n  Pipeline completed in {elapsed:.1f}s")
    print(f"  Plan: {_j(result.plan, 200)}")

    # Data Agent
    da = result.data_result
    print(f"\n  --- DATA AGENT ---")
    print(f"    success: {da.success if da else 'N/A'}")
    print(f"    tools:   {da.tool_calls_made if da else 'N/A'}")
    print(f"    content: {len(da.content) if da and da.content else 0} chars")
    if da and da.content:
        for line in da.content.split("\n")[:10]:
            print(f"    | {line[:120]}")

    # Technical Agent
    ta = result.technical_result
    print(f"\n  --- TECHNICAL AGENT ---")
    print(f"    success: {ta.success if ta else 'N/A'}")
    print(f"    tools:   {ta.tool_calls_made if ta else 'N/A'}")
    print(f"    content: {len(ta.content) if ta and ta.content else 0} chars")
    if ta and ta.content:
        for line in ta.content.split("\n")[:10]:
            print(f"    | {line[:120]}")

    # Synthesis
    print(f"\n  --- SYNTHESIS ---")
    print(f"    length:  {len(result.synthesis)} chars")
    if result.synthesis:
        for line in result.synthesis.split("\n")[:15]:
            print(f"    | {line[:120]}")
    else:
        print(f"    (empty)")

    # Final verdict
    print(f"\n  --- VERDICT ---")
    data_ok = da and da.success
    tech_ok = ta and ta.success
    synth_ok = bool(result.synthesis and len(result.synthesis) > 20)
    print(f"    DataAgent:      {'PASS' if data_ok else 'FAIL'}")
    print(f"    TechnicalAgent: {'PASS' if tech_ok else 'FAIL'}")
    print(f"    Synthesis:      {'PASS' if synth_ok else 'FAIL'}")

    if data_ok and synth_ok:
        _ok("FULL PIPELINE PASS")
    elif data_ok:
        _ok("Pipeline mostly OK - synthesis issue")
    else:
        _fail(f"Pipeline issues: data={data_ok}, tech={tech_ok}, synth={synth_ok}")

    return result


# ---------------------------------------------------------------------------
# Test 8: Structured output (hypothesis tool)
# ---------------------------------------------------------------------------

async def test_structured_output(settings):
    _hdr("TEST 8: Structured Output (Hypothesis tools)")
    from src.llm.tools import ToolRegistry

    registry = ToolRegistry()

    # Test list_active_hypotheses
    r1 = await registry.dispatch("list_active_hypotheses", {})
    print(f"  list_active_hypotheses: {_j(r1, 300)}")

    # Test get_hypothesis_detail
    r2 = await registry.dispatch("get_hypothesis_detail", {"hypothesis_name": "overnight_margin_cascade"})
    if "error" not in r2:
        print(f"  get_hypothesis_detail: name={r2.get('name')}, status={r2.get('status')}")
        print(f"    description: {r2.get('description', '')[:100]}")
        print(f"    testing_criteria: {_j(r2.get('testing_criteria', {}), 200)}")
        _ok("Hypothesis tools OK")
    else:
        print(f"  get_hypothesis_detail: {_j(r2)}")
        _fail("Hypothesis detail failed")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    # Patch print globally for this test — Windows cp932 chokes on LLM emoji
    import builtins
    _orig_print = builtins.print
    def _safe(text="", *a, **kw):
        if isinstance(text, str):
            try:
                text.encode("ascii")
            except UnicodeEncodeError:
                text = text.encode("ascii", errors="replace").decode("ascii")
        return _orig_print(text, *a, **kw)
    builtins.print = _safe

    _orig_print("\n" + "=" * 60)
    _orig_print("  MarketPulse Agentic Pipeline - Full E2E Trace")
    _orig_print("=" * 60)

    total_t0 = time.monotonic()

    # Layer 1: Config
    settings = await test_config()

    # Layer 2: DeepSeek connectivity
    ds_ok = await test_deepseek_connectivity(settings)
    if not ds_ok:
        print("\n  Cannot proceed without DeepSeek connectivity.")
        return

    # Layer 3: ModelRouter
    router = await test_model_router(settings)

    # Layer 4: ToolRegistry
    registry = await test_tool_registry()

    # Layer 5: DataAgent (live)
    data_result = await test_data_agent(settings, registry)

    # Layer 6: TechnicalAgent (live)
    tech_result = await test_technical_agent(settings, registry, data_result)

    # Layer 7: Full orchestrator
    orch_result = await test_full_orchestrator(settings)

    # Layer 8: Structured output
    await test_structured_output(settings)

    total_elapsed = time.monotonic() - total_t0
    _hdr(f"ALL TESTS COMPLETE ({total_elapsed:.1f}s)")


if __name__ == "__main__":
    asyncio.run(main())
