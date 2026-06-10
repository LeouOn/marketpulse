"""MarketPulse LLM Integration
Primary: LM Studio (local models)
Fallback: OpenRouter (cloud APIs)
"""

import json
from typing import Any

from loguru import logger

from ..core.config import get_settings


class LMStudioClient:
    """LM Studio API client for local LLM inference"""

    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self.base_url = self.settings.llm.primary.base_url
        self.timeout = self.settings.llm.primary.timeout
        self.model = getattr(self.settings.llm.primary, "model", None)
        self.session = None
        self._detected_model = None

        # Model capabilities and purposes
        self.model_capabilities = {
            "fast_analysis": {
                "purpose": "Quick market analysis and data validation",
                "max_tokens": 300,
                "temperature": 0.3,
            },
            "deep_analysis": {"purpose": "Comprehensive market analysis", "max_tokens": 800, "temperature": 0.5},
            "trade_review": {"purpose": "Trade setup review and validation", "max_tokens": 400, "temperature": 0.4},
            "data_validation": {
                "purpose": "Sanity checks and data interpretation validation",
                "max_tokens": 150,
                "temperature": 0.2,
            },
        }

    async def __aenter__(self):
        """Async context manager entry"""
        import aiohttp

        timeout = max(self.timeout, 300)
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout))
        if not self._detected_model:
            await self._auto_detect_model()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def _auto_detect_model(self):
        """Query LM Studio for loaded models and pick one."""
        if self._detected_model:
            return
        try:
            import aiohttp

            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
                async with s.get(f"{self.base_url}/models") as r:
                    if r.status == 200:
                        data = await r.json()
                        models = [m["id"] for m in data.get("data", [])]
                        if self.model and self.model in models:
                            self._detected_model = self.model
                        elif models:
                            self._detected_model = models[0]
                            logger.info(f"Auto-detected LM Studio model: {self._detected_model}")
        except Exception as e:
            logger.debug(f"Model auto-detect failed: {e}")

    def get_active_model(self) -> str:
        """Return the model that will actually be used."""
        return self._detected_model or self.model or "unknown"

    async def generate_completion(
        self,
        model: str = "fast_analysis",
        messages: list[dict[str, str]] = None,
        max_tokens: int = 100,
        temperature: float = 0.3,
        system_prompt: str = None,
    ) -> dict[str, Any] | None:
        """
        Generate completion using LM Studio

        Args:
            model: Model capability type ('fast_analysis', 'deep_analysis', 'trade_review', 'data_validation')
            messages: Chat messages in OpenAI format
            max_tokens: Maximum tokens to generate
            temperature: Response creativity (0.0-1.0)
            system_prompt: System prompt for the model

        Returns:
            Completion response or None if error
        """
        try:
            actual_model = self._detected_model or self.model

            # Get model configuration if available
            model_config = self.model_capabilities.get(model, {})
            if model_config:
                max_tokens = model_config.get("max_tokens", max_tokens)
                temperature = model_config.get("temperature", temperature)

            # Prepare messages
            if messages is None:
                messages = []

            # Add system prompt if provided
            if system_prompt and not any(msg.get("role") == "system" for msg in messages):
                messages.insert(0, {"role": "system", "content": system_prompt})

            # LM Studio API request
            url = f"{self.base_url}/chat/completions"
            payload = {
                "model": actual_model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": False,
            }

            async with self.session.post(url, json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.debug(f"LM Studio completion successful: {actual_model}")
                    return result
                else:
                    logger.warning(f"LM Studio API error {response.status}: {await response.text()}")
                    return None

        except Exception as e:
            logger.error(f"LM Studio completion error: {e}")
            return None

    async def analyze_market_internals(self, internals_data: dict[str, Any]) -> str | None:
        """
        Analyze market internals using fast model for quick insights
        """
        system_prompt = """You are a market internals analyst. Analyze market conditions quickly and provide actionable insights.
Focus on: market bias, volatility regime, trading opportunities, and key levels."""

        # Format market data for analysis
        user_prompt = f"""
        Market Internals Data:
        {json.dumps(internals_data, indent=2)}

        Provide a brief analysis covering:
        1. Current market bias (Bullish/Bearish/Mixed)
        2. Volatility assessment
        3. Key levels to watch
        4. Trading implications
        5. Risk considerations

        Keep response under 200 words.
        """

        messages = [{"role": "user", "content": user_prompt}]

        response = await self.generate_completion(
            model="fast_analysis", messages=messages, system_prompt=system_prompt, max_tokens=300, temperature=0.3
        )

        if response and "choices" in response:
            return response["choices"][0]["message"]["content"]
        return None

    async def deep_market_analysis(
        self, internals_data: dict[str, Any], timeframe_analysis: dict[str, Any] = None
    ) -> str | None:
        """
        Deep market analysis using analyst model
        """
        system_prompt = """You are an expert market analyst specializing in market internals and sentiment analysis.
Provide comprehensive analysis with clear reasoning for trading decisions."""

        # Prepare data for deep analysis
        data_summary = f"""
        Current Market Internals:
        {json.dumps(internals_data, indent=2)}

        {f"Timeframe Analysis: {json.dumps(timeframe_analysis, indent=2)}" if timeframe_analysis else ""}
        """

        user_prompt = f"""
        {data_summary}

        Provide detailed analysis covering:
        1. Multi-timeframe market structure
        2. Sentiment analysis (fear/greed, positioning)
        3. Risk assessment and volatility outlook
        4. Sector rotation and breadth analysis
        5. Key support/resistance levels with reasoning
        6. Near-term catalysts and events
        7. Overall market regime classification
        8. Actionable trading implications

        Include reasoning for each conclusion.
        Response limit: 500 words.
        """

        messages = [{"role": "user", "content": user_prompt}]

        response = await self.generate_completion(
            model="deep_analysis", messages=messages, system_prompt=system_prompt, max_tokens=800, temperature=0.5
        )

        if response and "choices" in response:
            return response["choices"][0]["message"]["content"]
        return None

    async def review_trade_setup(self, trade_context: dict[str, Any], market_internals: dict[str, Any]) -> str | None:
        """
        Review trading setup using reviewer model
        """
        system_prompt = """You are a post-trade review specialist. Analyze trading setups objectively,
focusing on risk management, execution quality, and learning opportunities."""

        user_prompt = f"""
        Trade Setup Context:
        {json.dumps(trade_context, indent=2)}

        Market Context at Time:
        {json.dumps(market_internals, indent=2)}

        Review this trading setup focusing on:
        1. Setup quality and market alignment
        2. Risk/reward assessment
        3. Entry and exit timing
        4. Position sizing appropriateness
        5. Market condition suitability
        6. What could be improved
        7. Lessons learned for future setups

        Be objective and educational.
        Response limit: 300 words.
        """

        messages = [{"role": "user", "content": user_prompt}]

        response = await self.generate_completion(
            model="trade_review", messages=messages, system_prompt=system_prompt, max_tokens=400, temperature=0.4
        )

        if response and "choices" in response:
            return response["choices"][0]["message"]["content"]
        return None

    async def validate_data_interpretation(
        self, data: dict[str, Any], data_type: str = "market_internals"
    ) -> dict[str, Any]:
        """
        Perform sanity checks on data interpretation using LLM

        Args:
            data: The data to validate
            data_type: Type of data ('market_internals', 'price_data', 'technical_indicators')

        Returns:
            Dictionary with validation results
        """
        try:
            system_prompt = """You are a data validation expert. Analyze the provided data and verify:
1. Data completeness and structure
2. Reasonable value ranges
3. Logical consistency
4. Potential data quality issues
5. Missing critical information

Respond with a JSON object containing:
- is_valid: boolean
- issues: list of issues found (if any)
- confidence: confidence score (0-100)
- recommendations: suggestions for improvement
- summary: brief summary of data quality"""

            if data_type == "market_internals":
                user_prompt = f"""Validate this market internals data for logical consistency:

{json.dumps(data, indent=2)}

Check for:
- Reasonable price ranges (SPY: $300-600, QQQ: $200-500, VIX: $10-80)
- Reasonable percentage changes (±10% max for most assets)
- Consistent volume figures
- Missing critical symbols (SPY, QQQ, VIX)
- Timestamp validity

Return validation results in JSON format."""

            elif data_type == "price_data":
                user_prompt = f"""Validate this price data for quality issues:

{json.dumps(data, indent=2)}

Check for:
- OHLC consistency (High >= max(Open, Close), Low <= min(Open, Close))
- Reasonable price movements between candles
- Volume consistency
- Missing or null values
- Timestamp ordering

Return validation results in JSON format."""

            else:
                user_prompt = f"""Validate this technical indicator data:

{json.dumps(data, indent=2)}

Check for:
- Reasonable indicator values
- Consistency with price data
- Missing calculations
- Outlier detection

Return validation results in JSON format."""

            messages = [{"role": "user", "content": user_prompt}]

            response = await self.generate_completion(
                model="data_validation", messages=messages, system_prompt=system_prompt, max_tokens=200, temperature=0.1
            )

            if response and "choices" in response:
                content = response["choices"][0]["message"]["content"]
                try:
                    # Try to parse as JSON
                    validation_result = json.loads(content)
                    return validation_result
                except json.JSONDecodeError:
                    # If not JSON, create structured response
                    return {
                        "is_valid": True,
                        "issues": [],
                        "confidence": 80,
                        "recommendations": ["Manual review recommended"],
                        "summary": "Validation completed (non-JSON response)",
                        "raw_response": content,
                    }

            return {
                "is_valid": False,
                "issues": ["No response from LLM"],
                "confidence": 0,
                "recommendations": ["Check LLM connection"],
                "summary": "Validation failed - no LLM response",
            }

        except Exception as e:
            logger.error(f"Data validation error: {e}")
            return {
                "is_valid": False,
                "issues": [f"Validation error: {str(e)}"],
                "confidence": 0,
                "recommendations": ["Retry validation"],
                "summary": f"Validation failed with error: {str(e)}",
            }

    async def interpret_text_chart_data(self, chart_data: dict[str, Any]) -> str | None:
        """
        Interpret text-encoded chart data and provide analysis

        Args:
            chart_data: Dictionary containing chart data in text format
                       {
                           'symbol': 'NQ',
                           'timeframe': '5m',
                           'candles': [
                               {'time': '10:00', 'open': 15000, 'high': 15025, 'low': 14995, 'close': 15020, 'volume': 1250},
                               ...
                           ],
                           'indicators': {
                               'sma_20': 15010,
                               'rsi': 65.5,
                               'volume_ma': 1100
                           }
                       }
        """
        system_prompt = """You are a technical analyst. Interpret the provided chart data and identify:
1. Trend direction and strength
2. Key support/resistance levels
3. Volume patterns
4. Indicator signals
5. Potential trade setups
6. Risk points

Be concise and actionable. Focus on what matters for trading decisions."""

        # Format chart data for analysis
        chart_summary = f"""
Symbol: {chart_data.get("symbol", "Unknown")}
Timeframe: {chart_data.get("timeframe", "Unknown")}
Periods analyzed: {len(chart_data.get("candles", []))}

RECENT PRICE ACTION:
{self._format_recent_candles(chart_data.get("candles", [])[-5:])}

TECHNICAL INDICATORS:
{json.dumps(chart_data.get("indicators", {}), indent=2)}

KEY LEVELS:
- Current Price: {chart_data.get("candles", [])[-1]["close"] if chart_data.get("candles") else "N/A"}
- Period High: {max(c["high"] for c in chart_data.get("candles", [])) if chart_data.get("candles") else "N/A"}
- Period Low: {min(c["low"] for c in chart_data.get("candles", [])) if chart_data.get("candles") else "N/A"}

Provide technical analysis focusing on actionable insights."""

        messages = [{"role": "user", "content": chart_summary}]

        response = await self.generate_completion(
            model="deep_analysis", messages=messages, system_prompt=system_prompt, max_tokens=300, temperature=0.4
        )

        if response and "choices" in response:
            return response["choices"][0]["message"]["content"]
        return None

    def _format_recent_candles(self, candles: list[dict]) -> str:
        """Format recent candles for LLM analysis"""
        if not candles:
            return "No candle data available"

        formatted = []
        for i, candle in enumerate(candles):
            direction = "🟢" if candle["close"] >= candle["open"] else "🔴"
            formatted.append(
                f"  {direction} Candle {i + 1}: O={candle['open']:.2f} H={candle['high']:.2f} L={candle['low']:.2f} C={candle['close']:.2f} V={candle.get('volume', 0)}"
            )

        return "\n".join(formatted)

    def get_model_status(self) -> dict[str, Any]:
        """Get status of available models"""
        active = self._detected_model or self.model or "unknown"
        return {
            "active_model": active,
            "config_model": self.model or "not configured",
            "auto_detected": self._detected_model is not None,
            "capabilities": {
                k: {"purpose": v["purpose"], "max_tokens": v["max_tokens"]} for k, v in self.model_capabilities.items()
            },
        }


class OpenRouterClient:
    """OpenRouter API client for cloud LLM fallback"""

    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self.base_url = self.settings.llm.fallback.base_url
        self.api_key = self.settings.llm.fallback.api_key
        self.timeout = self.settings.llm.fallback.timeout
        self.session = None

    async def __aenter__(self):
        """Async context manager entry"""
        import aiohttp

        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        self.session = aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=self.timeout))
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()

    async def generate_completion(
        self,
        model: str = "openai/gpt-4o-mini",
        messages: list[dict[str, str]] = None,
        max_tokens: int = 100,
        temperature: float = 0.3,
    ) -> dict[str, Any] | None:
        """Generate completion using OpenRouter"""
        try:
            url = f"{self.base_url}/chat/completions"
            payload = {"model": model, "messages": messages or [], "max_tokens": max_tokens, "temperature": temperature}

            async with self.session.post(url, json=payload) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.warning(f"OpenRouter API error {response.status}: {await response.text()}")
                    return None

        except Exception as e:
            logger.error(f"OpenRouter completion error: {e}")
            return None


class LLMManager:
    """Orchestrates LLM operations with ModelRouter-based fallback support.

    Uses ``ModelRouter`` to dispatch to the best available provider:
    DeepSeek → LM Studio → OpenRouter.
    """

    def __init__(self):
        self.settings = get_settings()
        self._router = None

    async def analyze_market(
        self, internals_data: dict[str, Any], analysis_type: str = "quick"
    ) -> str | None:
        """Analyze market using ModelRouter for provider selection.

        Args:
            internals_data: Market internals data
            analysis_type: 'quick', 'deep', or 'review'
        """
        from .model_router import ModelRouter

        try:
            async with ModelRouter(self.settings) as router:
                # Map analysis_type to capability
                capability = {
                    "quick": "fast",
                    "deep": "reasoning",
                    "review": "standard",
                }.get(analysis_type, "standard")

                client, model_id = await router.route(capability)
                provider_name = self._provider_label(client)

                if analysis_type == "quick":
                    if hasattr(client, "analyze_market"):
                        result = await client.analyze_market(
                            internals_data, model=model_id, max_tokens=300
                        )
                    else:
                        result = await self._fallback_analyze(
                            client, model_id, internals_data, "quick"
                        )
                elif analysis_type == "deep":
                    if hasattr(client, "deep_analysis"):
                        result = await client.deep_analysis(
                            internals_data, model=model_id, max_tokens=800
                        )
                    else:
                        result = await self._fallback_analyze(
                            client, model_id, internals_data, "deep"
                        )
                else:
                    result = await self._fallback_analyze(
                        client, model_id, internals_data, analysis_type
                    )

                if result:
                    return f"🤖 {provider_name}:\n{result}"

            logger.error("All LLM services failed")
            return None

        except Exception as e:
            logger.error(f"LLM analysis error: {e}")
            return None

    async def _fallback_analyze(
        self,
        client: Any,
        model_id: str,
        internals_data: dict[str, Any],
        analysis_type: str,
    ) -> str | None:
        """Generic text-completion fallback when client lacks convenience methods."""
        import json as _json

        if analysis_type == "deep":
            prompt = f"Provide detailed market analysis of:\n{_json.dumps(internals_data, indent=2)}"
            max_tokens = 800
        else:
            prompt = f"Analyze these market internals briefly:\n{_json.dumps(internals_data, indent=2)}"
            max_tokens = 300

        response = await client.generate_completion(
            messages=[{"role": "user", "content": prompt}],
            model=model_id or None,
            max_tokens=max_tokens,
            temperature=0.3,
        )

        if response and "choices" in response:
            return response["choices"][0]["message"].get("content")
        return None

    @staticmethod
    def _provider_label(client: Any) -> str:
        """Human-readable provider label for analysis output."""
        name = type(client).__name__
        if "MiniMax" in name:
            return "MiniMax (M3)"
        if "DeepSeek" in name:
            return "DeepSeek"
        if "LMStudio" in name:
            return "LM Studio (Local)"
        if "OpenRouter" in name:
            return "OpenRouter (Cloud)"
        return name

    def get_status(self) -> dict[str, Any]:
        """Get status of all LLM services."""
        return {
            "deepseek": {
                "available": bool(
                    self.settings.llm.deepseek.api_key
                    and self.settings.llm.deepseek.api_key != "your_deepseek_api_key"
                ),
                "endpoint": self.settings.llm.deepseek.base_url,
                "model_pro": self.settings.llm.deepseek.model_pro,
                "model_flash": self.settings.llm.deepseek.model_flash,
            },
            "lm_studio": {
                "available": True,
                "endpoint": self.settings.llm.primary.base_url,
            },
            "openrouter": {
                "available": bool(
                    self.settings.llm.fallback.api_key
                    and self.settings.llm.fallback.api_key != "your_openrouter_api_key"
                ),
                "endpoint": self.settings.llm.fallback.base_url,
            },
            "minimax": {
                "available": bool(
                    self.settings.llm.minimax.api_key
                    and self.settings.llm.minimax.api_key != "your_minimax_api_key"
                ),
                "endpoint": self.settings.llm.minimax.base_url,
                "model": self.settings.llm.minimax.model,
            },
            "routing": {
                "primary": self.settings.llm.model_routing.primary_provider,
                "fallback": self.settings.llm.model_routing.fallback_providers,
            },
        }
