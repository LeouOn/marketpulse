"""MarketAgent -- Base class for LLM agents with tool access.

Each agent has a focused system prompt, a curated tool subset, and a model
preference.  The ``execute()`` method runs the function-calling loop via
``ModelRouter`` and returns structured results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loguru import logger


@dataclass
class AgentResult:
    """Structured result from an agent execution."""

    agent_name: str
    content: str                           # Final text response
    tool_calls_made: list[str] = field(default_factory=list)  # Names of tools invoked
    raw_response: dict[str, Any] | None = None  # Raw API response
    success: bool = True
    error: str | None = None


class MarketAgent:
    """Base agent with system prompt, tool access, and model routing.

    Subclass and set::

        AGENT_NAME: str
        SYSTEM_PROMPT: str
        TOOL_NAMES: list[str]        # subset of ToolRegistry tool names
        CAPABILITY: str              # "reasoning" | "fast" | "standard"
        MAX_TURNS: int               # max function-calling turns
        MAX_TOKENS: int
        TEMPERATURE: float

    Usage::

        agent = DataAgent(registry)
        async with agent:
            result = await agent.execute("Fetch SPY market data")
    """

    # -- override in subclasses -------------------------------------------
    AGENT_NAME: str = "base"
    SYSTEM_PROMPT: str = "You are a helpful assistant."
    TOOL_NAMES: list[str] = []
    CAPABILITY: str = "standard"
    MAX_TURNS: int = 5
    MAX_TOKENS: int = 800
    TEMPERATURE: float = 0.3

    # -- init -------------------------------------------------------------

    def __init__(self, registry=None, settings=None):
        from ...core.config import get_settings
        from ..tools import ToolRegistry

        self.settings = settings or get_settings()
        self.registry: ToolRegistry = registry or ToolRegistry()
        self._router = None
        self._entered = False

        # Filter tools to this agent's subset
        self._tools = self.registry.list_definitions(self.TOOL_NAMES)

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

    # -- execution --------------------------------------------------------

    async def execute(self, task: str, context: dict[str, Any] | None = None) -> AgentResult:
        """Run the agent loop: model ←→ tools until completion.

        Args:
            task: The user's request / question for this agent.
            context: Optional extra data injected into the system prompt.

        Returns:
            AgentResult with the final text + metadata.
        """
        if not self._entered:
            raise RuntimeError(f"{self.AGENT_NAME} not entered -- use 'async with'")

        # Build system prompt with optional context
        system = self.SYSTEM_PROMPT
        if context:
            system += f"\n\nADDITIONAL CONTEXT:\n{_fmt(context)}"

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": task},
        ]

        tool_calls_made: list[str] = []

        # Route to the right model
        client, model_id = await self._router.route(self.CAPABILITY)

        if not hasattr(client, "generate_with_tools"):
            # Fallback: plain completion (no function calling)
            logger.warning(
                f"{self.AGENT_NAME}: client {type(client).__name__} "
                f"lacks generate_with_tools -- using plain completion"
            )
            response = await client.generate_completion(
                messages=messages,
                model=model_id or None,
                max_tokens=self.MAX_TOKENS,
                temperature=self.TEMPERATURE,
            )
            if response and "choices" in response:
                msg = response["choices"][0]["message"]
                content = msg.get("content") or msg.get("reasoning_content") or ""
                return AgentResult(
                    agent_name=self.AGENT_NAME,
                    content=content,
                    raw_response=response,
                )
            return AgentResult(
                agent_name=self.AGENT_NAME,
                content="",
                success=False,
                error="No response from model",
            )

        # Function-calling loop
        async def _handler(name: str, args: dict) -> dict:
            tool_calls_made.append(name)
            return await self.registry.dispatch(name, args)

        try:
            response = await client.generate_with_tools(
                messages=messages,
                tools=self._tools,
                tool_handler=_handler,
                model=model_id,
                max_turns=self.MAX_TURNS,
                max_tokens=self.MAX_TOKENS,
                temperature=self.TEMPERATURE,
            )
        except Exception as e:
            logger.error(f"{self.AGENT_NAME} execution error: {e}")
            return AgentResult(
                agent_name=self.AGENT_NAME,
                content="",
                success=False,
                error=str(e),
                tool_calls_made=tool_calls_made,
            )

        if response and "choices" in response:
            msg = response["choices"][0]["message"]
            # DeepSeek reasoning models may put output in reasoning_content
            content = msg.get("content") or msg.get("reasoning_content") or ""
            if not content and msg.get("tool_calls"):
                content = f"[Agent invoked tools: {', '.join(tool_calls_made)} but produced no final text]"

            return AgentResult(
                agent_name=self.AGENT_NAME,
                content=content,
                tool_calls_made=tool_calls_made,
                raw_response=response,
            )

        return AgentResult(
            agent_name=self.AGENT_NAME,
            content="",
            success=False,
            error="No response from model after tool loop",
            tool_calls_made=tool_calls_made,
        )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _fmt(obj: Any) -> str:
    """Compact formatting for context injection."""
    import json

    if isinstance(obj, str):
        return obj
    try:
        return json.dumps(obj, indent=2, default=str)
    except Exception:
        return str(obj)
