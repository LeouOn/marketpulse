"""Hypothesis Tools -- Trading hypothesis testing functions callable by LLM agents.

Wraps ``HypothesisTester`` for structured hypothesis evaluation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from loguru import logger

# ---------------------------------------------------------------------------
# Tool: list_active_hypotheses
# ---------------------------------------------------------------------------

LIST_ACTIVE_HYPOTHESES_DEF: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "list_active_hypotheses",
        "description": (
            "List all active trading hypotheses currently tracked by the system. "
            "Each hypothesis has a name, status, and description. "
            "Use this to discover what patterns the system is monitoring."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}


async def list_active_hypotheses() -> dict[str, Any]:
    """List all active and tested hypotheses."""
    try:
        from src.llm.hypothesis_tester import HypothesisTester

        # HypothesisTester needs an LLM client -- use a lightweight stub
        class _StubClient:
            async def generate_completion(self, **kw):
                return None

        tester = HypothesisTester(_StubClient())
        hypotheses = tester.list_hypotheses()

        return {
            "hypotheses": hypotheses,
            "count": len(hypotheses),
            "active_count": sum(1 for h in hypotheses if h.get("status") == "active"),
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"list_active_hypotheses error: {e}")
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Tool: get_hypothesis_detail
# ---------------------------------------------------------------------------

GET_HYPOTHESIS_DETAIL_DEF: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "get_hypothesis_detail",
        "description": (
            "Load the full detail of a specific trading hypothesis, including "
            "its mechanism, testing criteria, success metrics, confounding factors, "
            "and trading implications. Use this to understand what a hypothesis "
            "claims and how it can be tested."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "hypothesis_name": {
                    "type": "string",
                    "description": "Name of the hypothesis file (without .md), e.g. 'overnight_margin_cascade'",
                },
            },
            "required": ["hypothesis_name"],
        },
    },
}


async def get_hypothesis_detail(hypothesis_name: str) -> dict[str, Any]:
    """Load full detail of a hypothesis."""
    try:
        from src.llm.hypothesis_tester import HypothesisTester

        class _StubClient:
            async def generate_completion(self, **kw):
                return None

        tester = HypothesisTester(_StubClient())
        hypothesis = tester.load_hypothesis(hypothesis_name)

        if not hypothesis:
            return {"error": f"Hypothesis '{hypothesis_name}' not found"}

        return {
            "name": hypothesis.get("name", hypothesis_name),
            "status": hypothesis.get("status", "unknown"),
            "description": hypothesis.get("description", ""),
            "mechanism": hypothesis.get("mechanism", ""),
            "what_to_look_for": hypothesis.get("what_to_look_for", []),
            "testing_criteria": hypothesis.get("testing_criteria", {}),
            "confounding_factors": hypothesis.get("confounding_factors", []),
            "trading_implications": hypothesis.get("trading_implications", ""),
            "data_requirements": hypothesis.get("data_requirements", {}),
            "success_metrics": hypothesis.get("success_metrics", []),
            "related_concepts": hypothesis.get("related_concepts", []),
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"get_hypothesis_detail error: {e}")
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Aggregate exports
# ---------------------------------------------------------------------------

HYPOTHESIS_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    LIST_ACTIVE_HYPOTHESES_DEF,
    GET_HYPOTHESIS_DETAIL_DEF,
]

HYPOTHESIS_TOOL_HANDLERS: dict[str, Any] = {
    "list_active_hypotheses": list_active_hypotheses,
    "get_hypothesis_detail": get_hypothesis_detail,
}
