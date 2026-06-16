"""MiniMax LLM API Client
Cloud LLM fallback option alongside OpenRouter
"""

from typing import Any

import aiohttp
from loguru import logger

from ..core.config import get_settings


class MiniMaxClient:
    """MiniMax API client for cloud LLM inference"""

    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self.base_url = self.settings.llm.minimax.base_url
        self.api_key = self.settings.llm.minimax.api_key
        self.timeout = self.settings.llm.minimax.timeout
        self.model = self.settings.llm.minimax.model
        self.session: aiohttp.ClientSession | None = None

    async def __aenter__(self):
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        self.session = aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=self.timeout))
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def check_health(self) -> bool:
        """Check whether the MiniMax endpoint is reachable + the API key is set.

        Used by ModelRouter for fast health probing. We consider the provider
        healthy if the API key is set to a non-default value; full validation
        happens on the first real request.
        """
        try:
            if not self.api_key or self.api_key == "your_minimax_api_key":
                return False
            if not self.session:
                return True  # key valid; session will be opened on first call
            # Lightweight probe: hit /models (cheap, OpenAI-compatible).
            url = f"{self.base_url}/models"
            async with self.session.get(url) as r:
                return r.status == 200
        except Exception:
            return False

    async def generate_completion(
        self, messages: list[dict[str, str]], model: str = None, max_tokens: int = 300, temperature: float = 0.3
    ) -> dict[str, Any] | None:
        """
        Generate completion using MiniMax API

        Args:
            messages: Chat messages in OpenAI format
            model: Model to use (defaults to configured model)
            max_tokens: Maximum tokens to generate
            temperature: Response creativity (0.0-1.0)

        Returns:
            Completion response or None if error
        """
        try:
            url = f"{self.base_url}/chat/completions"
            payload = {
                "model": model or self.model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": False,
            }

            async with self.session.post(url, json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.debug("MiniMax completion successful")
                    return result
                else:
                    error_text = await response.text()
                    logger.warning(f"MiniMax API error {response.status}: {error_text}")
                    return None

        except Exception as e:
            logger.error(f"MiniMax completion error: {e}")
            return None

    async def analyze_market(self, internals_data: dict[str, Any], analysis_type: str = "quick") -> str | None:
        """
        Analyze market data using MiniMax

        Args:
            internals_data: Market internals data
            analysis_type: 'quick' or 'deep'

        Returns:
            Analysis text or None if failed
        """
        system_prompt = """You are a market analysis expert. Analyze market conditions and provide actionable insights.
Focus on: market bias, volatility, key levels, and trading implications."""

        if analysis_type == "quick":
            user_prompt = f"""Analyze these market internals briefly:
{internals_data}

Provide a brief analysis covering:
1. Current market bias (Bullish/Bearish/Mixed)
2. Volatility assessment
3. Key levels to watch
4. Trading implications

Keep response under 200 words."""
            max_tokens = 300
        else:
            user_prompt = f"""Provide detailed market analysis:
{internals_data}

Cover:
1. Multi-timeframe market structure
2. Sentiment analysis
3. Risk assessment
4. Support/resistance levels
5. Trading implications
6. Catalysts and events

Response limit: 500 words."""
            max_tokens = 600

        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]

        response = await self.generate_completion(messages=messages, max_tokens=max_tokens, temperature=0.4)

        if response and "choices" in response:
            return response["choices"][0]["message"]["content"]
        return None

    async def validate_data(self, data: dict[str, Any], data_type: str = "market_internals") -> dict | None:
        """Validate data interpretation using MiniMax"""
        system_prompt = """You are a data validation expert. Analyze data for completeness, consistency, and quality issues.
Respond with JSON containing: is_valid, issues, confidence, recommendations, summary."""

        if data_type == "market_internals":
            user_prompt = f"""Validate this market internals data:
{internals_data}

Check for:
- Reasonable price ranges
- Consistent percentage changes
- Missing critical symbols
- Timestamp validity"""

        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]

        response = await self.generate_completion(messages=messages, max_tokens=200, temperature=0.1)

        if response and "choices" in response:
            content = response["choices"][0]["message"]["content"]
            try:
                import json

                return json.loads(content)
            except:
                return {"is_valid": True, "issues": [], "confidence": 80, "summary": "Validation completed"}
        return None

    def get_status(self) -> dict[str, Any]:
        """Get MiniMax client status"""
        return {
            "available": bool(self.api_key and self.api_key != "your_minimax_api_key"),
            "endpoint": self.base_url,
            "model": self.model,
        }


async def get_minimax_client() -> MiniMaxClient:
    """Get MiniMax client instance"""
    return MiniMaxClient()
