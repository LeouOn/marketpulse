"""Enhanced LLM Client with Trading Knowledge Integration.

Combines the ModelRouter with RAG and enhanced prompts. The legacy
``EnhancedLMStudioClient`` (which extended ``LMStudioClient`` directly) has been
removed; ``EnhancedLLMClient`` is the single consolidated entry point and now
accepts an injectable ``ModelRouter`` for testing.
"""

import json
from typing import Any

from loguru import logger

from ..core.config import get_settings
from .system_prompts import build_enhanced_prompt, get_system_prompt
from .trading_knowledge_rag import KeywordKnowledgeRetriever, get_trading_rag


class EnhancedLLMClient:
    """Model-router-backed client with trading knowledge + RAG.

    The client is an async context manager::

        async with EnhancedLLMClient() as client:
            analysis = await client.analyze_with_knowledge(
                query="Is SPY overbought?",
                market_data=internals,
            )

    For tests, an already-entered ``ModelRouter`` (or any duck-typed object
    exposing ``async generate(*, messages, capability, max_tokens, temperature)``)
    can be injected via ``router=``. When a router is injected, the client does
    NOT own its lifecycle (it will not close it on ``__aexit__``).
    """

    def __init__(self, settings=None, router=None):
        self.settings = settings or get_settings()
        self._router = router
        self._owns_router = router is None
        self.knowledge_rag = get_trading_rag()
        self.keyword_retriever = KeywordKnowledgeRetriever()
        self.system_prompt_cache = {}
        logger.info("EnhancedLLMClient initialized (ModelRouter-backed)")

    async def __aenter__(self):
        from .model_router import ModelRouter

        if self._owns_router:
            self._router = ModelRouter(self.settings)
            await self._router.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._owns_router and self._router is not None:
            await self._router.__aexit__(exc_type, exc_val, exc_tb)
            self._router = None
        # Never null out an injected router.

    async def _generate(
        self,
        messages: list[dict[str, str]],
        capability: str = "standard",
        max_tokens: int = 800,
        temperature: float = 0.3,
    ) -> str | None:
        """Route + generate, returning text content or None."""
        if not self._router:
            return None

        response = await self._router.generate(
            messages=messages,
            capability=capability,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        if response and "choices" in response:
            return response["choices"][0]["message"].get("content")
        return None

    async def analyze_with_knowledge(
        self,
        query: str,
        market_data: dict[str, Any] | None = None,
        prompt_type: str = "trading_analyst",
        max_tokens: int = 400,
        temperature: float = 0.3,
    ) -> str | None:
        """Analyze query with trading knowledge context (routed)."""
        try:
            context_chunks = self.knowledge_rag.retrieve_context(query)
            base_prompt = get_system_prompt(prompt_type)
            enhanced_prompt = build_enhanced_prompt(base_prompt, context_chunks, query, market_data)
            return await self._generate(
                [{"role": "user", "content": enhanced_prompt}],
                capability="standard",
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception as e:
            logger.error(f"Enhanced analysis error: {e}")
            return None

    async def test_hypothesis(
        self, hypothesis_name: str, market_data: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """Test a trading hypothesis (routed -- supports structured output)."""
        try:
            from .hypothesis_tester import HypothesisTester

            # HypothesisTester detects generate_with_tools on the router
            # and uses structured output when available.
            tester = HypothesisTester(self._router, self.knowledge_rag)
            result = await tester.test_hypothesis(hypothesis_name, market_data)
            return result.to_dict() if hasattr(result, "to_dict") else result
        except Exception as e:
            logger.error(f"Hypothesis testing error: {e}")
            return None

    async def analyze_market_with_context(
        self, market_internals: dict[str, Any], additional_context: str | None = None
    ) -> str | None:
        """Analyze market internals with trading knowledge context."""
        try:
            query = "Analyze the following market conditions for trading opportunities."
            if additional_context:
                query += f" {additional_context}"
            context_chunks = self.knowledge_rag.retrieve_context("market analysis")
            base_prompt = get_system_prompt("market_analysis")
            enhanced_prompt = build_enhanced_prompt(base_prompt, context_chunks, query, market_internals)
            return await self._generate(
                [{"role": "user", "content": enhanced_prompt}],
                capability="standard",
                max_tokens=500,
                temperature=0.4,
            )
        except Exception as e:
            logger.error(f"Market analysis error: {e}")
            return None

    async def analyze_market_internals(self, internals_data: dict[str, Any]) -> str | None:
        """Quick market internals analysis (routed to 'fast' capability)."""
        try:
            system_prompt = """You are a market internals analyst. Analyze market conditions quickly.
Focus on: market bias, volatility regime, trading opportunities, key levels."""
            user_prompt = f"""Market Internals Data:
{json.dumps(internals_data, indent=2)}

Provide a brief analysis covering:
1. Current market bias (Bullish/Bearish/Mixed)
2. Volatility assessment
3. Key levels to watch
4. Trading implications

Keep response under 200 words."""

            return await self._generate(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                capability="fast",
                max_tokens=300,
                temperature=0.3,
            )
        except Exception as e:
            logger.error(f"Market internals analysis error: {e}")
            return None

    async def deep_market_analysis(
        self,
        internals_data: dict[str, Any],
        timeframe_analysis: dict[str, Any] | None = None,
    ) -> str | None:
        """Deep multi-timeframe market analysis (routed to 'reasoning')."""
        try:
            system_prompt = """You are an expert market analyst specializing in market internals
and sentiment analysis. Provide comprehensive analysis with clear reasoning."""
            data_block = f"""Current Market Internals:
{json.dumps(internals_data, indent=2)}"""
            if timeframe_analysis:
                data_block += f"""

Timeframe Analysis:
{json.dumps(timeframe_analysis, indent=2)}"""

            user_prompt = f"""{data_block}

Provide detailed analysis covering:
1. Multi-timeframe market structure
2. Sentiment analysis (fear/greed, positioning)
3. Risk assessment and volatility outlook
4. Sector rotation and breadth analysis
5. Key support/resistance levels with reasoning
6. Near-term catalysts and events
7. Overall market regime classification
8. Actionable trading implications

Include reasoning for each conclusion. Response limit: 500 words."""

            return await self._generate(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                capability="reasoning",
                max_tokens=1000,
                temperature=0.5,
            )
        except Exception as e:
            logger.error(f"Deep market analysis error: {e}")
            return None

    def get_glossary_term(self, term: str) -> str | None:
        """Get definition for a trading term."""
        return self.knowledge_rag.get_glossary_term(term)

    def get_related_knowledge(self, query: str, max_results: int = 3) -> list[dict[str, Any]]:
        """Get related knowledge for a query."""
        return self.knowledge_rag.retrieve_context(query, max_results)


class EnhancedLLMManager:
    """Enhanced LLM manager with knowledge integration + ModelRouter."""

    def __init__(self):
        self.settings = get_settings()
        self.enhanced_client: EnhancedLLMClient | None = None
        self._router = None

    async def __aenter__(self):
        """Async context manager entry."""
        self.enhanced_client = EnhancedLLMClient(self.settings)
        await self.enhanced_client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.enhanced_client:
            await self.enhanced_client.__aexit__(exc_type, exc_val, exc_tb)
            self.enhanced_client = None

    async def analyze_market(self, internals_data: dict[str, Any], analysis_type: str = "quick") -> str | None:
        """Analyze market with enhanced knowledge (router-backed)."""
        try:
            if not self.enhanced_client:
                return None

            if analysis_type == "quick":
                return await self.enhanced_client.analyze_market_internals(internals_data)
            elif analysis_type == "deep":
                return await self.enhanced_client.deep_market_analysis(internals_data)
            else:
                return await self.enhanced_client.analyze_market_internals(internals_data)
        except Exception as e:
            logger.error(f"Enhanced market analysis error: {e}")
            return None

    async def test_hypothesis(
        self, hypothesis_name: str, market_data: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """Test a trading hypothesis."""
        try:
            if not self.enhanced_client:
                return None
            return await self.enhanced_client.test_hypothesis(hypothesis_name, market_data)
        except Exception as e:
            logger.error(f"Hypothesis testing error: {e}")
            return None
