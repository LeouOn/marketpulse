"""MarketAnalysisOrchestrator -- Multi-Agent Pipeline for Market Analysis

Orchestrates 5 specialised agents through a 6-phase pipeline:
  1. Plan → 2. DataAgent → 3. [Technical + Macro + Risk + Hypothesis] ∥
  → 4. Draft Synthesis → 5. Critique → 6. Final Synthesis

Also supports streaming via ``analyze_streaming()`` which yields
``PhaseEvent`` dicts for WebSocket push.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncGenerator

from loguru import logger

from .base import AgentResult, MarketAgent
from .alert_agent import AlertAgent
from .critique_agent import CritiqueAgent
from .data_agent import DataAgent
from .hypothesis_agent import HypothesisAgent
from .ict_agent import ICTSmartMoneyAgent
from .macro_agent import MacroAgent
from .multi_tf_agent import MultiTFAgent
from .options_agent import OptionsFlowAgent
from .risk_agent import RiskAgent
from .risk_quant_agent import RiskQuantAgent
from .strategy_agent import StrategyProposalAgent
from .technical_agent import TechnicalAgent


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class OrchestratorResult:
    """Complete analysis result from the orchestrator."""

    query: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    plan: dict[str, Any] = field(default_factory=dict)
    data_result: AgentResult | None = None
    technical_result: AgentResult | None = None
    macro_result: AgentResult | None = None
    risk_result: AgentResult | None = None
    hypothesis_result: AgentResult | None = None
    ict_result: AgentResult | None = None
    options_result: AgentResult | None = None
    risk_quant_result: AgentResult | None = None
    strategy_result: AgentResult | None = None
    multi_tf_result: AgentResult | None = None
    alert_result: AgentResult | None = None
    draft_synthesis: str = ""
    critique: str = ""
    synthesis: str = ""
    success: bool = True
    error: str | None = None

    @property
    def all_agent_results(self) -> dict[str, AgentResult | None]:
        return {
            "data": self.data_result,
            "technical": self.technical_result,
            "macro": self.macro_result,
            "risk": self.risk_result,
            "hypothesis": self.hypothesis_result,
            "ict": self.ict_result,
            "options": self.options_result,
            "risk_quant": self.risk_quant_result,
            "strategy": self.strategy_result,
            "multi_tf": self.multi_tf_result,
            "alert": self.alert_result,
        }


@dataclass
class PhaseEvent:
    """Emitted during streaming analysis for progressive UI updates."""
    phase: str          # "plan" | "data_fetching" | "data_complete" |
                        # "agents_running" | "agent_done" |
                        # "draft_ready" | "critiquing" | "final_ready"
    content: str = ""
    agent_name: str = ""
    tools_used: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class MarketAnalysisOrchestrator:
    """Multi-agent market analysis orchestrator with 5 specialised agents."""

    DRAFT_SYNTHESIS_PROMPT = """You are the synthesis engine for a multi-agent market analysis system.

Below are the outputs of EIGHT specialised agents:

{agent_sections}

Your task: synthesise these into ONE coherent market analysis (DRAFT).
Cover:
1. **Market Snapshot** -- Key levels, current bias, volatility regime
2. **Technical Picture** -- Trend structure, support/resistance, patterns
3. **Macro Regime** -- Breadth, sector rotation, intermarket signals
4. **Risk Assessment** -- Stop levels, correlation risk, tail risks
5. **Hypothesis Check** -- Any active patterns firing?
6. **Actionable Takeaways** -- What a trader should watch/do

Be concise (400-500 words). Reference specific price levels. State
confidence where appropriate. This is a DRAFT that will be critiqued."""

    FINAL_SYNTHESIS_PROMPT = """You are the synthesis engine for a trading analysis system.

Below is your DRAFT analysis followed by a CRITIQUE from a review agent.
Incorporate the critique to produce the FINAL, improved analysis.

--- DRAFT ANALYSIS ---
{draft}

--- CRITIQUE ---
{critique}

Your task: produce the FINAL analysis that addresses every valid point
in the critique. Where the critique identifies missing data, acknowledge
the limitation clearly. Where it identifies weak assumptions, strengthen
them or qualify your confidence.

Maintain a clear structure with sections for: Market Snapshot, Technical
Picture, Macro Regime, Risk Assessment, Hypothesis Check, and Actionable
Takeaways.

Aim for 400-500 words. Be specific, honest about uncertainty, and
trading-actionable."""

    # Ordered list of (attr_name, AgentClass, label) for parallel dispatch
    # Wave 1: lightweight agents that run first (read-only data)
    AGENTS_WAVE_1: list[tuple[str, type[MarketAgent], str]] = [
        ("technical_result", TechnicalAgent, "Technical"),
        ("macro_result", MacroAgent, "Macro"),
        ("multi_tf_result", MultiTFAgent, "MultiTF"),
    ]

    # Wave 2: agents that benefit from Wave 1 context (regime + technicals)
    AGENTS_WAVE_2: list[tuple[str, type[MarketAgent], str]] = [
        ("risk_result", RiskAgent, "Risk"),
        ("hypothesis_result", HypothesisAgent, "Hypothesis"),
        ("ict_result", ICTSmartMoneyAgent, "ICT"),
        ("options_result", OptionsFlowAgent, "Options"),
        ("risk_quant_result", RiskQuantAgent, "RiskQuant"),
        ("strategy_result", StrategyProposalAgent, "Strategy"),
        ("alert_result", AlertAgent, "Alert"),
    ]

    @property
    def all_agents(self) -> list[tuple[str, type[MarketAgent], str]]:
        return self.AGENTS_WAVE_1 + self.AGENTS_WAVE_2

    def __init__(self, settings=None):
        from ...core.config import get_settings

        self.settings = settings or get_settings()
        self._router = None
        self._entered = False

    # -- context manager --------------------------------------------------

    async def __aenter__(self):
        from ..model_router import ModelRouter

        self._router = ModelRouter(self.settings)
        await self._router.__aenter__()
        self._entered = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._router:
            await self._router.__aexit__(exc_type, exc_val, exc_tb)
            self._router = None
        self._entered = False

    # -- main entry point -------------------------------------------------

    async def analyze(
        self,
        query: str,
        symbols: list[str] | None = None,
        include_breadth: bool = True,
    ) -> OrchestratorResult:
        """Run the full 5-agent analysis pipeline.

        Args:
            query: Natural-language analysis question.
            symbols: Symbols to focus on (default: ["SPY"]).
            include_breadth: Whether to fetch breadth indicators.

        Returns:
            OrchestratorResult with all agent outputs and synthesis.
        """
        if not self._entered:
            raise RuntimeError("Orchestrator not entered -- use 'async with'")

        symbols = symbols or ["SPY"]
        logger.info(
            f"Orchestrator: query='{query[:80]}...' symbols={symbols}"
        )

        result = OrchestratorResult(query=query)

        # -- Phase 1: Plan -------------------------------------------------
        result.plan = {
            "symbols": symbols,
            "include_breadth": include_breadth,
            "agents": ["Data"] + [a[2] for a in self.all_agents] + ["Critique"],
            "steps": [
                "Fetch market internals + OHLCV",
                "Wave 1: Technical + Macro (roundtable)",
                "Wave 2: Risk + Hypothesis + ICT + Options + RiskQuant + Strategy",
                "Draft synthesis from all agents",
                "Critique + final synthesis",
            ],
        }

        # -- Phase 2: Data Agent -------------------------------------------
        data_task = self._build_data_task(query, symbols, include_breadth)
        logger.info("Orchestrator: dispatching DataAgent...")

        try:
            async with DataAgent(settings=self.settings) as agent:
                result.data_result = await agent.execute(data_task)
                logger.info(
                    f"DataAgent: {len(result.data_result.content)} chars, "
                    f"tools={result.data_result.tool_calls_made}"
                )
        except Exception as e:
            logger.error(f"DataAgent failed: {e}")
            result.data_result = AgentResult(
                agent_name="data_agent",
                content=f"Data fetch failed: {e}",
                success=False, error=str(e),
            )

        # -- Phase 3: Parallel agent dispatch ------------------------------
        data_ok = (
            result.data_result
            and (result.data_result.success
                 or len(result.data_result.tool_calls_made) > 0)
        )
        if data_ok:
            data_context = result.data_result.content or ""
            await self._dispatch_agents(result, query, symbols, data_context)
        else:
            for attr, _, _ in self.all_agents:
                setattr(result, attr, AgentResult(
                    agent_name=attr,
                    content="Skipped -- DataAgent did not return valid data.",
                    success=False, error="No data available",
                ))

        # -- Phase 4: Draft synthesis --------------------------------------
        result.draft_synthesis = await self._synthesise_draft(result)
        logger.info(
            f"Orchestrator: draft synthesis {len(result.draft_synthesis)} chars"
        )

        # -- Phase 5: Critique ---------------------------------------------
        try:
            async with CritiqueAgent(settings=self.settings) as critic:
                crit_task = (
                    f"Critique this draft market analysis:\n\n"
                    f"{result.draft_synthesis}"
                )
                crit_result = await critic.execute(crit_task)
                result.critique = crit_result.content
                logger.info(f"CritiqueAgent: {len(result.critique)} chars")
        except Exception as e:
            logger.warning(f"CritiqueAgent failed: {e}")
            result.critique = f"[Critique unavailable: {e}]"

        # -- Phase 6: Final synthesis --------------------------------------
        if result.critique and len(result.critique) > 20:
            result.synthesis = await self._synthesise_final(result)
        else:
            result.synthesis = result.draft_synthesis

        logger.info(
            f"Orchestrator: final synthesis {len(result.synthesis)} chars"
        )
        return result

    # -- streaming entry point --------------------------------------------

    async def analyze_streaming(
        self,
        query: str,
        symbols: list[str] | None = None,
        include_breadth: bool = True,
    ) -> AsyncGenerator[PhaseEvent, None]:
        """Run the pipeline yielding PhaseEvents for WebSocket push.

        Usage::

            async for event in orch.analyze_streaming(query, symbols):
                await websocket.send_json(event.__dict__)
        """
        if not self._entered:
            raise RuntimeError("Orchestrator not entered -- use 'async with'")

        symbols = symbols or ["SPY"]

        # Yield plan
        yield PhaseEvent(phase="plan", data={
            "symbols": symbols,
            "agents": ["Data"] + [a[2] for a in self.all_agents] + ["Critique"],
        })

        # Data Agent
        yield PhaseEvent(phase="data_fetching", agent_name="data_agent")
        data_task = self._build_data_task(query, symbols, include_breadth)

        result = OrchestratorResult(query=query)
        try:
            async with DataAgent(settings=self.settings) as agent:
                result.data_result = await agent.execute(data_task)
        except Exception as e:
            result.data_result = AgentResult(
                agent_name="data_agent", content=f"Error: {e}",
                success=False, error=str(e),
            )

        yield PhaseEvent(
            phase="data_complete", agent_name="data_agent",
            content=result.data_result.content[:500] if result.data_result else "",
            tools_used=result.data_result.tool_calls_made if result.data_result else [],
        )

        # Parallel agents
        data_ok = result.data_result and (
            result.data_result.success or len(result.data_result.tool_calls_made) > 0
        )
        if data_ok:
            data_context = result.data_result.content or ""
            yield PhaseEvent(phase="agents_running", data={
                "agents": [a[2] for a in self.all_agents],
            })

            # Run in parallel, yielding as each completes
            tasks = []
            for attr, agent_cls, label in self.all_agents:
                task = self._build_agent_task(query, symbols, data_context, attr)
                tasks.append((attr, label, self._run_agent(agent_cls, attr, task)))

            for attr, label, coro in tasks:
                agent_result = await coro
                setattr(result, attr, agent_result)
                yield PhaseEvent(
                    phase="agent_done", agent_name=label,
                    content=(agent_result.content or "")[:300],
                    tools_used=agent_result.tool_calls_made,
                )
        else:
            for attr, _, label in self.all_agents:
                setattr(result, attr, AgentResult(
                    agent_name=attr,
                    content="Skipped -- no data available.",
                    success=False,
                ))
                yield PhaseEvent(
                    phase="agent_done", agent_name=label,
                    content="Skipped -- no data available.",
                )

        # Draft synthesis
        result.draft_synthesis = await self._synthesise_draft(result)
        yield PhaseEvent(
            phase="draft_ready",
            content=result.draft_synthesis[:800],
        )

        # Critique
        yield PhaseEvent(phase="critiquing", agent_name="critique_agent")
        try:
            async with CritiqueAgent(settings=self.settings) as critic:
                crit_result = await critic.execute(
                    f"Critique this draft market analysis:\n\n{result.draft_synthesis}"
                )
                result.critique = crit_result.content
        except Exception as e:
            result.critique = f"[Critique unavailable: {e}]"

        # Final synthesis
        if result.critique and len(result.critique) > 20:
            result.synthesis = await self._synthesise_final(result)
        else:
            result.synthesis = result.draft_synthesis

        yield PhaseEvent(
            phase="final_ready",
            content=result.synthesis[:1000],
            data={"draft_len": len(result.draft_synthesis),
                   "critique_len": len(result.critique),
                   "final_len": len(result.synthesis)},
        )

    # -- agent dispatch ---------------------------------------------------

    async def _dispatch_agents(
        self, result: OrchestratorResult,
        query: str, symbols: list[str], data_context: str,
    ) -> None:
        """Run agents in 2-wave roundtable with context injection."""
        logger.info(
            f"Orchestrator: Wave 1 — {len(self.AGENTS_WAVE_1)} agents..."
        )

        async def _run(attr: str, agent_cls: type, task: str) -> None:
            try:
                async with agent_cls(settings=self.settings) as agent:
                    r = await agent.execute(task)
                    setattr(result, attr, r)
                    logger.info(
                        f"{agent.AGENT_NAME}: {len(r.content)} chars, "
                        f"tools={r.tool_calls_made}"
                    )
            except Exception as e:
                logger.error(f"{attr} failed: {e}")
                setattr(result, attr, AgentResult(
                    agent_name=attr, content=f"Error: {e}",
                    success=False, error=str(e),
                ))

        # -- Wave 1 -------------------------------------------------------
        wave1_tasks = []
        for attr, agent_cls, _ in self.AGENTS_WAVE_1:
            task = self._build_agent_task(query, symbols, data_context, attr)
            wave1_tasks.append(_run(attr, agent_cls, task))
        await asyncio.gather(*wave1_tasks)

        # -- Build roundtable context from Wave 1 -------------------------
        rt_context = self._build_roundtable_context(result)

        # -- Wave 2 (with context) ----------------------------------------
        logger.info(
            f"Orchestrator: Wave 2 — {len(self.AGENTS_WAVE_2)} agents "
            f"(with roundtable context)"
        )
        wave2_tasks = []
        for attr, agent_cls, _ in self.AGENTS_WAVE_2:
            task = self._build_agent_task(
                query, symbols, data_context, attr, roundtable_context=rt_context,
            )
            wave2_tasks.append(_run(attr, agent_cls, task))
        await asyncio.gather(*wave2_tasks)

    def _build_roundtable_context(self, result: OrchestratorResult) -> str:
        """Build context string from Wave 1 agent outputs for Wave 2 agents."""
        parts: list[str] = []

        tech = result.technical_result
        if tech and tech.content:
            parts.append(f"TECHNICAL CONTEXT:\n{tech.content[:800]}\n")

        macro = result.macro_result
        if macro and macro.content:
            parts.append(f"MACRO/REGIME CONTEXT:\n{macro.content[:800]}\n")

        if not parts:
            return ""

        header = (
            "=== ROUNDTABLE CONTEXT (from Wave 1 agents) ===\n"
            "Use this context to inform your analysis. "
            "The Technical Agent has identified key levels and trends. "
            "The Macro Agent has assessed the market regime. "
            "Incorporate these findings into your own analysis.\n\n"
        )
        return header + "\n".join(parts)

    async def _run_agent(
        self, agent_cls: type, attr: str, task: str,
    ) -> AgentResult:
        """Run a single agent and return its result."""
        try:
            async with agent_cls(settings=self.settings) as agent:
                return await agent.execute(task)
        except Exception as e:
            logger.error(f"{attr} failed: {e}")
            return AgentResult(
                agent_name=attr, content=f"Error: {e}",
                success=False, error=str(e),
            )

    # -- task builders ----------------------------------------------------

    def _build_data_task(
        self, query: str, symbols: list[str], include_breadth: bool,
    ) -> str:
        sym_list = ", ".join(symbols)
        task = (
            f"Fetch market data for: {query}\n\n"
            f"SYMBOLS: {sym_list}\n\n"
            f"INSTRUCTIONS:\n"
            f"1. Call get_market_internals for the macro picture.\n"
        )
        step = 2
        if include_breadth:
            task += f"{step}. Call get_breadth for advance/decline data.\n"
            step += 1
        for sym in symbols:
            task += (
                f"{step}. Call get_ohlcv for {sym} (period=1mo, interval=1d) "
                f"AND get_symbol_52w_stats for {sym}.\n"
            )
            step += 1
        task += (
            f"\nAfter all fetches, summarise key data points "
            f"(prices, changes, volume, breadth) in 2-3 sentences."
        )
        return task

    def _build_agent_task(
        self, query: str, symbols: list[str], data_context: str, agent_attr: str,
        roundtable_context: str = "",
    ) -> str:
        """Build a task prompt for a specific agent type."""
        sym_list = ", ".join(symbols)
        rt_prefix = f"{roundtable_context}\n\n" if roundtable_context else ""

        if "technical" in agent_attr:
            return (
                f"{rt_prefix}"
                f"Run technical analysis for: {query}\n\n"
                f"SYMBOLS: {sym_list}\n\n"
                f"DATA AGENT OUTPUT:\n{data_context}\n\n"
                f"INSTRUCTIONS:\n"
                f"1. Use analyze_symbol_technicals for each symbol.\n"
                f"2. Use find_support_resistance for precise S/R levels.\n"
                f"3. Provide: trend assessment, key levels, patterns, risk zones."
            )
        elif "macro" in agent_attr:
            return (
                f"{rt_prefix}"
                f"Assess the macro regime for: {query}\n\n"
                f"SYMBOLS: {sym_list}\n\n"
                f"DATA AGENT OUTPUT:\n{data_context}\n\n"
                f"INSTRUCTIONS:\n"
                f"1. Use get_market_internals and get_breadth.\n"
                f"2. Report: risk posture, breadth, intermarket signals, VIX regime."
            )
        elif "risk" in agent_attr:
            return (
                f"{rt_prefix}"
                f"Assess risk for: {query}\n\n"
                f"SYMBOLS: {sym_list}\n\n"
                f"DATA AGENT OUTPUT:\n{data_context}\n\n"
                f"INSTRUCTIONS:\n"
                f"1. Use get_ohlcv and get_symbol_52w_stats.\n"
                f"2. Report: key risk levels, stop placement, correlation risk, tail risk."
            )
        elif "hypothesis" in agent_attr:
            return (
                f"{rt_prefix}"
                f"Test active hypotheses for: {query}\n\n"
                f"SYMBOLS: {sym_list}\n\n"
                f"DATA AGENT OUTPUT:\n{data_context}\n\n"
                f"INSTRUCTIONS:\n"
                f"1. Call list_active_hypotheses to see what's tracked.\n"
                f"2. For each, call get_hypothesis_detail and test.\n"
                f"3. Report: FIRING/DORMANT/INSUFFICIENT_DATA with confidence."
            )
        elif "ict" in agent_attr:
            return (
                f"{rt_prefix}"
                f"Analyze ICT/SMC signals for: {query}\n\n"
                f"SYMBOLS: {sym_list}\n\n"
                f"DATA AGENT OUTPUT:\n{data_context}\n\n"
                f"INSTRUCTIONS:\n"
                f"1. Call generate_ict_signals, analyze_order_flow, detect_divergences.\n"
                f"2. Synthesize: do signals agree? Report entry/stop/targets with confidence."
            )
        elif "options" in agent_attr:
            return (
                f"{rt_prefix}"
                f"Screen options flow for: {query}\n\n"
                f"SYMBOLS: {sym_list}\n\n"
                f"DATA AGENT OUTPUT:\n{data_context}\n\n"
                f"INSTRUCTIONS:\n"
                f"1. Call screen_options_flow and compute_indicators.\n"
                f"2. Report unusual activity and alignment with technicals."
            )
        elif "risk_quant" in agent_attr:
            return (
                f"{rt_prefix}"
                f"Quantify risk for: {query}\n\n"
                f"SYMBOLS: {sym_list}\n\n"
                f"DATA AGENT OUTPUT:\n{data_context}\n\n"
                f"INSTRUCTIONS:\n"
                f"1. Call classify_regime and calculate_risk_metrics.\n"
                f"2. Report: regime, position sizing, risk level."
            )
        elif "strategy" in agent_attr:
            return (
                f"{rt_prefix}"
                f"Propose and backtest a strategy for: {query}\n\n"
                f"SYMBOLS: {sym_list}\n\n"
                f"DATA AGENT OUTPUT:\n{data_context}\n\n"
                f"INSTRUCTIONS:\n"
                f"1. Review ICT signals and divergences from context.\n"
                f"2. Propose a concrete strategy with entry/exit/stop rules.\n"
                f"3. Call run_backtest to validate the strategy.\n"
                f"4. Report: VIABLE / NEEDS_REFINEMENT / NOT_VIABLE with metrics."
            )
        elif "multi_tf" in agent_attr:
            return (
                f"{rt_prefix}"
                f"Multi-timeframe analysis for: {query}\n\n"
                f"SYMBOLS: {sym_list}\n\n"
                f"DATA AGENT OUTPUT:\n{data_context}\n\n"
                f"INSTRUCTIONS:\n"
                f"1. Call get_ohlcv for 4H, 1D, and 1W timeframes.\n"
                f"2. Call analyze_symbol_technicals on each timeframe's data.\n"
                f"3. Build a confluence matrix: where do timeframes agree/diverge?\n"
                f"4. Report: STRONG (3/3), PARTIAL (2/3), or DIVERGENCE with specific levels."
            )
        elif "alert" in agent_attr:
            return (
                f"{rt_prefix}"
                f"Set alerts based on analysis for: {query}\n\n"
                f"SYMBOLS: {sym_list}\n\n"
                f"DATA AGENT OUTPUT:\n{data_context}\n\n"
                f"INSTRUCTIONS:\n"
                f"1. Review key levels from other agents in the roundtable context.\n"
                f"2. Call create_alert for 2-3 high-priority conditions.\n"
                f"3. Call check_alerts to see which are currently firing.\n"
                f"4. Report: alerts created, priority levels, trigger conditions."
            )
        return f"{rt_prefix}Analyze: {query}\n\nData:\n{data_context}"

    # -- synthesis --------------------------------------------------------

    def _build_agent_sections(self, result: OrchestratorResult) -> str:
        """Build formatted agent output sections for the synthesis prompt."""
        sections: list[str] = []
        labels = {
            "data": "DATA AGENT",
            "technical": "TECHNICAL AGENT",
            "macro": "MACRO AGENT",
            "risk": "RISK AGENT",
            "hypothesis": "HYPOTHESIS AGENT",
            "ict": "ICT SMART MONEY AGENT",
            "options": "OPTIONS FLOW AGENT",
            "risk_quant": "RISK QUANT AGENT",
            "strategy": "STRATEGY AGENT",
            "multi_tf": "MULTI-TF AGENT",
            "alert": "ALERT AGENT",
        }
        for key, label in labels.items():
            agent_result = result.all_agent_results.get(key)
            content = agent_result.content if agent_result else "(no output)"
            if not content:
                content = "(no output)"
            sections.append(f"--- {label} ---\n{content}\n")
        return "\n".join(sections)

    async def _synthesise_draft(self, result: OrchestratorResult) -> str:
        """Produce the draft synthesis from all 5 agent outputs."""
        prompt = self.DRAFT_SYNTHESIS_PROMPT.format(
            agent_sections=self._build_agent_sections(result),
        )

        try:
            client, model_id = await self._router.route("reasoning")
            response = await client.generate_completion(
                messages=[{"role": "user", "content": prompt}],
                model=model_id or None,
                max_tokens=1500,
                temperature=0.4,
            )

            if response and "choices" in response:
                msg = response["choices"][0]["message"]
                return msg.get("content") or msg.get("reasoning_content") or ""

            return "Draft synthesis failed -- no model response."

        except Exception as e:
            logger.error(f"Draft synthesis error: {e}")
            return f"Draft synthesis failed: {e}"

    async def _synthesise_final(self, result: OrchestratorResult) -> str:
        """Produce the final synthesis incorporating critique."""
        prompt = self.FINAL_SYNTHESIS_PROMPT.format(
            draft=result.draft_synthesis,
            critique=result.critique,
        )

        try:
            client, model_id = await self._router.route("reasoning")
            response = await client.generate_completion(
                messages=[{"role": "user", "content": prompt}],
                model=model_id or None,
                max_tokens=1600,
                temperature=0.4,
            )

            if response and "choices" in response:
                msg = response["choices"][0]["message"]
                return msg.get("content") or msg.get("reasoning_content") or ""

            return "Synthesis failed -- no model response."

        except Exception as e:
            logger.error(f"Synthesis error: {e}")
            return f"Synthesis failed: {e}"


# ---------------------------------------------------------------------------
# Demo / smoke test
# ---------------------------------------------------------------------------

async def _demo():
    """Quick smoke test -- requires DEEPSEEK_API_KEY set."""
    print("=" * 60)
    print("MarketAnalysisOrchestrator - 9-Agent Smoke Test")
    print("=" * 60)

    orchestrator = MarketAnalysisOrchestrator()
    async with orchestrator:
        result = await orchestrator.analyze(
            query="Is SPY in a healthy uptrend or showing warning signs?",
            symbols=["SPY"],
            include_breadth=True,
        )

    def _safe(text: str | None, n: int = 400) -> str:
        if not text:
            return "(empty)"
        return text[:n].encode("ascii", errors="replace").decode("ascii")

    print(f"\nPlan: {json.dumps(result.plan, indent=2)}")

    for key, label in [
        ("data_result", "DATA AGENT"),
        ("technical_result", "TECHNICAL AGENT"),
        ("macro_result", "MACRO AGENT"),
        ("risk_result", "RISK AGENT"),
        ("hypothesis_result", "HYPOTHESIS AGENT"),
        ("ict_result", "ICT AGENT"),
        ("options_result", "OPTIONS AGENT"),
        ("risk_quant_result", "RISK QUANT AGENT"),
    ]:
        ar = getattr(result, key, None)
        if ar:
            tag = "OK" if ar.success else "FAIL"
            print(f"\n--- {label} ({tag}) ---")
            print(_safe(ar.content))
            print(f"Tools: {ar.tool_calls_made}")

    print(f"\n--- DRAFT SYNTHESIS ---")
    print(_safe(result.draft_synthesis, 600))
    if result.critique:
        print(f"\n--- CRITIQUE ---")
        print(_safe(result.critique, 400))
    print(f"\n--- FINAL SYNTHESIS ---")
    print(_safe(result.synthesis, 800))
    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(_demo())
