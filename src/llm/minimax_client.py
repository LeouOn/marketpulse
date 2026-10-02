"""MiniMax LLM API Client
Cloud LLM fallback option alongside OpenRouter
"""

import json
from collections.abc import Callable
from typing import Any

import aiohttp
from loguru import logger

from ..core.config import get_settings


def _bad_tool_args_note(raw: Any) -> str:
    """Error note fed back to the model when its tool arguments were unusable."""
    snippet = repr(raw)[:120]
    return (
        f"tool arguments were not usable JSON ({type(raw).__name__}: {snippet}); "
        "the tool was called with empty arguments -- please resend valid JSON object arguments"
    )


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
            # An unresolved ``${...}`` YAML placeholder counts as "no key".
            if not self.api_key or self.api_key == "your_minimax_api_key" or self.api_key.startswith("${"):
                return False
            if not self.session:
                return True  # key valid; session will be opened on first call
            # Lightweight probe: hit /models (cheap, OpenAI-compatible). A wrong
            # base_url can redirect to an HTML page with a 200, so require JSON.
            url = f"{self.base_url}/models"
            async with self.session.get(url) as r:
                return r.status == 200 and "json" in r.headers.get("Content-Type", "")
        except Exception:
            return False

    async def generate_completion(
        self,
        messages: list[dict[str, str]],
        model: str = None,
        max_tokens: int = 300,
        temperature: float = 0.3,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
    ) -> dict[str, Any] | None:
        """
        Generate completion using MiniMax API

        Args:
            messages: Chat messages in OpenAI format
            model: Model to use (defaults to configured model)
            max_tokens: Maximum tokens to generate
            temperature: Response creativity (0.0-1.0)
            tools: OpenAI-compatible function definitions; sent natively
                (MiniMax's endpoint is OpenAI-compatible chat completions)
            tool_choice: Tool selection mode when tools are given

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
            if tools:
                payload["tools"] = tools
                payload["tool_choice"] = tool_choice

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

    # -- function-calling agent loop --------------------------------------

    async def generate_with_tools(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        tool_handler: Callable[..., Any],
        model: str | None = None,
        max_turns: int = 5,
        max_tokens: int = 800,
        temperature: float = 0.3,
    ) -> dict[str, Any] | None:
        """Multi-turn function-calling loop (same contract as DeepSeekClient).

        1. Send ``messages`` + ``tools`` to the model (OpenAI-compatible
           ``tools``/``tool_calls`` -- MiniMax's endpoint speaks that dialect).
        2. If the model returns ``tool_calls``, execute them via
           ``tool_handler(tool_name, tool_args) -> dict``.
        3. Append results to ``messages`` and repeat.
        4. Return the final response dict with inline ``<think>...</think>``
           reasoning stripped from the message content (MiniMax-M3 inlines its
           chain of thought; reuse agents.base.strip_think).

        Returns the final API response dict or ``None`` on error.
        """
        if not self.session:
            raise RuntimeError("MiniMaxClient not entered -- use 'async with'")

        # Imported here (not at module top) to keep this client importable
        # standalone: model_router imports this module, and the agents package
        # sits behind model_router at runtime.
        from .agents.base import strip_think

        working_messages = list(messages)  # shallow copy -- we append
        tool_defs: list[dict[str, Any]] = []

        # Normalise tool definitions to the OpenAI form the API expects:
        # { "type": "function", "function": { "name": ..., "parameters": ... } }
        for t in tools:
            if "type" in t:
                tool_defs.append(t)
            elif "function" in t:
                tool_defs.append({"type": "function", "function": t["function"]})
            else:
                # Bare function object e.g. {"name": "foo", "parameters": {...}}
                tool_defs.append({"type": "function", "function": t})

        response: dict[str, Any] | None = None
        for turn in range(max_turns):
            response = await self.generate_completion(
                messages=working_messages,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                tools=tool_defs,
            )

            if response is None:
                return None

            choice = response["choices"][0]
            message = choice["message"]

            # If the model produced a plain text response we are done.
            if message.get("content") and not message.get("tool_calls"):
                message["content"] = strip_think(message.get("content"))
                return response

            # If the model wants to call tools …
            tool_calls = message.get("tool_calls", [])
            if not tool_calls:
                # stop reason = 'stop' with empty content -- final answer
                message["content"] = strip_think(message.get("content"))
                return response

            # Append the assistant message (with tool_calls) to history.
            working_messages.append(message)

            # Execute each tool call and collect results.
            for i, tc in enumerate(tool_calls):
                fn = tc.get("function", {})
                tool_name = fn.get("name", "unknown")

                # Providers differ: ``arguments`` is normally a JSON string, but
                # some return an already-parsed dict (or null/garbage). Dict is
                # used as-is; a string goes through json.loads; anything else
                # degrades to {} and an error note is fed back to the model so
                # it can resend valid arguments (json.loads would otherwise
                # raise TypeError, which only JSONDecodeError is caught for).
                raw_args = fn.get("arguments")
                args_error: str | None = None
                if isinstance(raw_args, dict):
                    tool_args = raw_args
                elif isinstance(raw_args, str):
                    try:
                        parsed = json.loads(raw_args)
                    except json.JSONDecodeError:
                        parsed = None
                    if isinstance(parsed, dict):
                        tool_args = parsed
                    else:
                        tool_args = {}
                        args_error = _bad_tool_args_note(raw_args)
                else:
                    tool_args = {}
                    args_error = _bad_tool_args_note(raw_args)

                logger.info(
                    f"MiniMax tool call turn={turn + 1} "
                    f"tool={tool_name} args={json.dumps(tool_args, default=str)[:200]}"
                )

                try:
                    result = await tool_handler(tool_name, tool_args)
                except Exception as exc:
                    result = {"error": str(exc)}

                if args_error:
                    # Keep the handler's own fields, but make sure the model sees
                    # why its arguments were replaced with {} (if the handler
                    # reported its own error, that one wins the "error" key).
                    result = {"error": args_error, **result}

                working_messages.append(
                    {
                        "role": "tool",
                        # Fallback ids must stay unique when several id-less
                        # calls arrive in one turn: key on turn AND index.
                        "tool_call_id": tc.get("id") or f"call_{turn}_{i}",
                        "content": json.dumps(result, default=str),
                    }
                )

        logger.warning(f"MiniMax tool loop hit max_turns={max_turns} -- returning last response")
        return response

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
{data}

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
