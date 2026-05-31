"""Tool Registry -- central dispatch for LLM-callable tools.

Collects all tool definitions from the tools/ sub-packages and provides
a single ``dispatch(name, args)`` entry point for the function-calling loop.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from .data_tools import DATA_TOOL_DEFINITIONS, DATA_TOOL_HANDLERS
from .hypothesis_tools import HYPOTHESIS_TOOL_DEFINITIONS, HYPOTHESIS_TOOL_HANDLERS
from .knowledge_tools import KNOWLEDGE_TOOL_DEFINITIONS, KNOWLEDGE_TOOL_HANDLERS
from .technical_tools import TECHNICAL_TOOL_DEFINITIONS, TECHNICAL_TOOL_HANDLERS
from .backtest_tools import BACKTEST_TOOL_DEFINITIONS, BACKTEST_TOOL_HANDLERS
from .upstream_tools import UPSTREAM_TOOL_DEFINITIONS, UPSTREAM_TOOL_HANDLERS


class ToolRegistry:
    """Registers all tool definitions and dispatches tool calls.

    Usage::

        registry = ToolRegistry()
        defs = registry.list_definitions()        # → list[dict] for LLM
        result = await registry.dispatch("get_ohlcv", {"symbol": "SPY"})
    """

    def __init__(self) -> None:
        self._definitions: list[dict[str, Any]] = []
        self._handlers: dict[str, Any] = {}
        self._register_all()

    # -- registration -----------------------------------------------------

    def _register_all(self) -> None:
        """Collect every tool from all sub-modules."""
        modules: list[tuple[list[dict], dict[str, Any]]] = [
            (DATA_TOOL_DEFINITIONS, DATA_TOOL_HANDLERS),
            (TECHNICAL_TOOL_DEFINITIONS, TECHNICAL_TOOL_HANDLERS),
            (KNOWLEDGE_TOOL_DEFINITIONS, KNOWLEDGE_TOOL_HANDLERS),
            (HYPOTHESIS_TOOL_DEFINITIONS, HYPOTHESIS_TOOL_HANDLERS),
            (UPSTREAM_TOOL_DEFINITIONS, UPSTREAM_TOOL_HANDLERS),
            (BACKTEST_TOOL_DEFINITIONS, BACKTEST_TOOL_HANDLERS),
        ]

        seen: set[str] = set()
        for defs, handlers in modules:
            for tool_def in defs:
                name = tool_def["function"]["name"]
                if name in seen:
                    logger.warning(f"Duplicate tool name '{name}' -- skipping")
                    continue
                seen.add(name)
                self._definitions.append(tool_def)
                if name in handlers:
                    self._handlers[name] = handlers[name]

        logger.info(
            f"ToolRegistry: {len(self._definitions)} tools registered "
            f"({', '.join(sorted(seen))})"
        )

    # -- public API -------------------------------------------------------

    def list_definitions(self, subset: list[str] | None = None) -> list[dict[str, Any]]:
        """Return the full list of tool definitions (OpenAI-compatible).

        If ``subset`` is provided, only return definitions for those tool names.
        """
        if subset is None:
            return list(self._definitions)
        subset_set = set(subset)
        return [d for d in self._definitions if d["function"]["name"] in subset_set]

    def get_tool_names(self) -> list[str]:
        """Return all registered tool names."""
        return sorted(self._handlers.keys())

    async def dispatch(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool by name with the given arguments.

        Returns the tool's result dict or ``{"error": "..."}`` on failure.
        """
        handler = self._handlers.get(name)
        if handler is None:
            return {"error": f"Unknown tool: '{name}'. Available: {self.get_tool_names()}"}

        try:
            result = await handler(**args)
            return result if isinstance(result, dict) else {"result": result}
        except TypeError as e:
            logger.warning(f"Tool '{name}' called with wrong args {args}: {e}")
            return {"error": f"Invalid arguments for '{name}': {e}"}
        except Exception as e:
            logger.error(f"Tool '{name}' execution error: {e}")
            return {"error": f"Tool '{name}' failed: {e}"}
