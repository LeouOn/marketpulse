"""DeepSeek API Client
OpenAI-compatible client with native function calling and streaming support.
Primary reasoning engine for MarketPulse agentic workflows.
"""

import json
from typing import Any

import aiohttp
from loguru import logger

from ..core.config import get_settings


# ---------------------------------------------------------------------------
# Tool / function-calling type aliases
# ---------------------------------------------------------------------------

ToolDefinition = dict[str, Any]  # OpenAI-compatible function definition dict
ToolCall = dict[str, Any]        # A single tool call request from the model
ToolResult = dict[str, Any]      # Result returned to the model after execution


# ---------------------------------------------------------------------------
# DeepSeekClient
# ---------------------------------------------------------------------------

class DeepSeekClient:
    """OpenAI-compatible client for the DeepSeek API.

    Supports:
      - Standard chat completions
      - Function / tool calling with multi-turn agent loop
      - Streaming (stub -- returns async generator when API key present)

    Usage::

        async with DeepSeekClient() as client:
            response = await client.generate_completion(
                messages=[{"role": "user", "content": "Analyze SPY"}],
                model="deepseek-v4-pro",
                max_tokens=800,
            )
    """

    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        ds = self.settings.llm.deepseek
        self.base_url = ds.base_url
        self.api_key = ds.api_key
        self.timeout = ds.timeout
        self.model_pro = ds.model_pro
        self.model_flash = ds.model_flash
        self.session: aiohttp.ClientSession | None = None
        self._health: bool | None = None  # None = unknown

    # -- context manager ---------------------------------------------------

    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=max(self.timeout, 180))
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        self.session = aiohttp.ClientSession(headers=headers, timeout=timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            self.session = None

    # -- health ------------------------------------------------------------

    @property
    def is_healthy(self) -> bool | None:
        """None = unknown, True = last check succeeded, False = last check failed."""
        return self._health

    async def check_health(self) -> bool:
        """Check if DeepSeek API is reachable and the key is valid.

        Uses a minimal auth-only check -- sends a cheap request to verify
        the API key works without consuming meaningful tokens.
        """
        try:
            # DeepSeek doesn't expose a public /models endpoint like OpenAI.
            # Use a minimal chat completion as a health ping (1 token max).
            url = f"{self.base_url}/chat/completions"
            payload = {
                "model": self.model_flash,
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 1,
                "temperature": 0.0,
            }
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15)
            ) as s:
                async with s.post(url, json=payload, headers=headers) as r:
                    self._health = r.status == 200
                    if not self._health:
                        logger.debug(
                            f"DeepSeek health check: HTTP {r.status}"
                        )
                    return self._health
        except Exception as e:
            logger.debug(f"DeepSeek health check failed: {e}")
            self._health = False
            return False

    # -- core completion ---------------------------------------------------

    async def generate_completion(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        max_tokens: int = 800,
        temperature: float = 0.3,
        tools: list[ToolDefinition] | None = None,
        tool_choice: str = "auto",
        **kwargs,
    ) -> dict[str, Any] | None:
        """Single-shot chat completion (OpenAI-compatible).

        Returns the raw API response dict, or ``None`` on error.
        ``response["choices"][0]["message"]`` contains the assistant reply.

        When ``tools`` are provided they are passed as native function
        definitions -- DeepSeek v4 Pro supports them natively.
        """
        if not self.session:
            raise RuntimeError("DeepSeekClient not entered -- use 'async with'")

        url = f"{self.base_url}/chat/completions"
        payload: dict[str, Any] = {
            "model": model or self.model_pro,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
            **kwargs,
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice

        try:
            async with self.session.post(url, json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.debug(
                        f"DeepSeek completion: model={payload['model']} "
                        f"tokens={result.get('usage', {}).get('total_tokens', '?')}"
                    )
                    return result
                else:
                    error_text = await response.text()
                    logger.warning(
                        f"DeepSeek API error {response.status}: {error_text[:500]}"
                    )
                    return None
        except Exception as e:
            logger.error(f"DeepSeek completion error: {e}")
            return None

    # -- function-calling agent loop --------------------------------------

    async def generate_with_tools(
        self,
        messages: list[dict[str, str]],
        tools: list[ToolDefinition],
        tool_handler: callable,
        model: str | None = None,
        max_turns: int = 5,
        max_tokens: int = 800,
        temperature: float = 0.3,
    ) -> dict[str, Any] | None:
        """Multi-turn function-calling loop.

        1. Send ``messages`` + ``tools`` to the model.
        2. If the model returns ``tool_calls``, execute them via
           ``tool_handler(tool_name, tool_args) -> ToolResult``.
        3. Append results to ``messages`` and repeat.
        4. Return the final assistant message (no tool calls).

        ``tool_handler`` signature::

            async def handler(name: str, args: dict) -> dict:
                ...

        Returns the final API response dict or ``None`` on error.
        """
        if not self.session:
            raise RuntimeError("DeepSeekClient not entered -- use 'async with'")

        working_messages = list(messages)  # shallow copy -- we append
        tool_defs: list[dict[str, Any]] = []

        # Normalise tool definitions to the form DeepSeek expects:
        # { "type": "function", "function": { "name": ..., "parameters": ... } }
        for t in tools:
            if "type" in t:
                tool_defs.append(t)
            elif "function" in t:
                tool_defs.append({"type": "function", "function": t["function"]})
            else:
                # Bare function object e.g. {"name": "foo", "parameters": {...}}
                tool_defs.append({"type": "function", "function": t})

        for turn in range(max_turns):
            response = await self.generate_completion(
                messages=working_messages,
                model=model or self.model_pro,
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
                return response

            # If the model wants to call tools …
            tool_calls = message.get("tool_calls", [])
            if not tool_calls:
                return response  # stop reason = 'stop' -- final answer

            # Append the assistant message (with tool_calls) to history.
            working_messages.append(message)

            # Execute each tool call and collect results.
            for tc in tool_calls:
                fn = tc.get("function", {})
                tool_name = fn.get("name", "unknown")
                try:
                    tool_args = json.loads(fn.get("arguments", "{}"))
                except json.JSONDecodeError:
                    tool_args = {}

                logger.info(
                    f"DeepSeek tool call turn={turn+1} "
                    f"tool={tool_name} args={json.dumps(tool_args, default=str)[:200]}"
                )

                try:
                    result = await tool_handler(tool_name, tool_args)
                except Exception as exc:
                    result = {"error": str(exc)}

                working_messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", f"call_{turn}"),
                    "content": json.dumps(result, default=str),
                })

        logger.warning(
            f"DeepSeek tool loop hit max_turns={max_turns} -- returning last response"
        )
        return response

    # -- streaming (stub) -------------------------------------------------

    async def stream_completion(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        max_tokens: int = 800,
        temperature: float = 0.3,
        on_chunk: callable | None = None,
    ):
        """Stream completion tokens as an async generator.

        ``on_chunk(text: str)`` is called for each token if provided.
        Yields ``{"token": str, "done": bool}`` dicts.

        Requires ``stream=True`` support in the DeepSeek API.
        """
        if not self.session:
            raise RuntimeError("DeepSeekClient not entered -- use 'async with'")

        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": model or self.model_pro,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }

        try:
            async with self.session.post(url, json=payload) as response:
                if response.status != 200:
                    text = await response.text()
                    logger.warning(f"DeepSeek stream error {response.status}: {text[:300]}")
                    return

                buffer = ""
                async for chunk_bytes in response.content.iter_chunked(1024):
                    chunk_text = chunk_bytes.decode("utf-8", errors="replace")
                    buffer += chunk_text

                    # SSE lines: "data: {...}\n\n"
                    while "\n\n" in buffer:
                        line, buffer = buffer.split("\n\n", 1)
                        for sub in line.split("\n"):
                            sub = sub.strip()
                            if not sub.startswith("data: "):
                                continue
                            data_str = sub[6:]
                            if data_str == "[DONE]":
                                yield {"token": "", "done": True}
                                return
                            try:
                                data = json.loads(data_str)
                                delta = (
                                    data.get("choices", [{}])[0]
                                    .get("delta", {})
                                    .get("content", "")
                                )
                                if delta:
                                    if on_chunk:
                                        on_chunk(delta)
                                    yield {"token": delta, "done": False}
                            except json.JSONDecodeError:
                                continue

        except Exception as e:
            logger.error(f"DeepSeek stream error: {e}")

    # -- convenience methods -----------------------------------------------

    async def analyze_market(
        self,
        internals_data: dict[str, Any],
        model: str | None = None,
        max_tokens: int = 500,
    ) -> str | None:
        """Quick market internals analysis."""
        prompt = f"""Analyze these market internals and provide actionable insights:

{json.dumps(internals_data, indent=2)}

Cover: market bias, volatility assessment, key levels, trading implications.
Keep response under 250 words. Be precise with levels."""

        response = await self.generate_completion(
            messages=[{"role": "user", "content": prompt}],
            model=model or self.model_pro,
            max_tokens=max_tokens,
            temperature=0.3,
        )

        if response and "choices" in response:
            return response["choices"][0]["message"]["content"]
        return None

    async def deep_analysis(
        self,
        internals_data: dict[str, Any],
        timeframe_analysis: dict[str, Any] | None = None,
        model: str | None = None,
        max_tokens: int = 1000,
    ) -> str | None:
        """Comprehensive multi-timeframe market analysis."""
        data_block = f"""Current Market Internals:
{json.dumps(internals_data, indent=2)}"""

        if timeframe_analysis:
            data_block += f"""

Timeframe Analysis:
{json.dumps(timeframe_analysis, indent=2)}"""

        prompt = f"""{data_block}

Provide detailed market analysis covering:
1. Multi-timeframe market structure
2. Sentiment and positioning assessment
3. Risk and volatility outlook
4. Sector rotation and breadth
5. Key support/resistance levels with reasoning
6. Near-term catalysts
7. Market regime classification
8. Actionable trading implications

Include reasoning for each conclusion. Response limit: 500 words."""

        response = await self.generate_completion(
            messages=[{"role": "user", "content": prompt}],
            model=model or self.model_pro,
            max_tokens=max_tokens,
            temperature=0.5,
        )

        if response and "choices" in response:
            return response["choices"][0]["message"]["content"]
        return None
