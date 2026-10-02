"""Knowledge Tools -- Trading knowledge retrieval functions callable by LLM agents.

Wraps ``TradingKnowledgeRAG`` for semantic concept lookup.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

# ---------------------------------------------------------------------------
# Tool: search_trading_knowledge
# ---------------------------------------------------------------------------

SEARCH_TRADING_KNOWLEDGE_DEF: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search_trading_knowledge",
        "description": (
            "Search the trading knowledge base for concepts, strategies, "
            "and market microstructure information. Use this when you need "
            "definitions of trading terms (FVG, ICT concepts, order blocks, "
            "CVD, funding rates, etc.) or context about trading patterns."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language query, e.g. 'fair value gap crypto' or 'overnight margin mechanics'",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Max number of knowledge chunks to return (default 3).",
                },
            },
            "required": ["query"],
        },
    },
}


async def search_trading_knowledge(query: str, max_results: int = 3) -> dict[str, Any]:
    """Search the trading knowledge base."""
    try:
        # An empty query or a non-positive limit used to be forwarded to the
        # retriever and silently read as "no knowledge found".
        cleaned = (query or "").strip()
        if not cleaned:
            return {"error": "query must be a non-empty string"}
        if max_results < 1:
            return {"error": f"max_results must be >= 1, got {max_results}"}

        from src.llm.trading_knowledge_rag import get_trading_rag

        rag = get_trading_rag()
        chunks = rag.retrieve_context(cleaned, max_results=max_results)

        if not chunks:
            return {"query": cleaned, "results": [], "count": 0}

        results = []
        for chunk in chunks:
            content = chunk.get("content")
            if not isinstance(content, str):  # covers missing AND present-but-None
                content = str(chunk)
            # Truncate long content for LLM context
            if len(content) > 500:
                content = content[:500] + "..."
            results.append(
                {
                    "title": chunk.get("title") or chunk.get("file") or "",
                    "type": chunk.get("type") or "unknown",
                    "content": content,
                }
            )

        return {"query": cleaned, "results": results, "count": len(results)}

    except Exception as e:
        logger.error(f"search_trading_knowledge error: {e}")
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Tool: get_glossary_term
# ---------------------------------------------------------------------------

GET_GLOSSARY_TERM_DEF: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "get_glossary_term",
        "description": (
            "Look up a specific trading term in the glossary. "
            "Returns the definition. Use for precise definitions of "
            "terms like FVG, CVD, ICT, OTE, order block, liquidity sweep, etc."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "term": {
                    "type": "string",
                    "description": "The exact trading term to look up, e.g. 'FVG', 'CVD', 'Order Block'",
                },
            },
            "required": ["term"],
        },
    },
}


async def get_glossary_term(term: str) -> dict[str, Any]:
    """Look up a glossary term."""
    try:
        # Trim so a padded term ("  FVG  ") still resolves against the glossary.
        cleaned = (term or "").strip()

        from src.llm.trading_knowledge_rag import get_trading_rag

        rag = get_trading_rag()
        definition = rag.get_glossary_term(cleaned)

        if definition:
            return {"term": cleaned, "definition": definition, "found": True}
        else:
            return {
                "term": cleaned,
                "definition": None,
                "found": False,
                "hint": f"No definition found for '{cleaned}'. Try search_trading_knowledge instead.",
            }

    except Exception as e:
        logger.error(f"get_glossary_term error: {e}")
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Aggregate exports
# ---------------------------------------------------------------------------

KNOWLEDGE_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    SEARCH_TRADING_KNOWLEDGE_DEF,
    GET_GLOSSARY_TERM_DEF,
]

KNOWLEDGE_TOOL_HANDLERS: dict[str, Any] = {
    "search_trading_knowledge": search_trading_knowledge,
    "get_glossary_term": get_glossary_term,
}
