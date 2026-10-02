"""Offline tests for src/llm/tools/knowledge_tools.py (cycle 10).

The tools wrap ``TradingKnowledgeRAG`` via ``get_trading_rag()``; the singleton
is replaced with a fake (scripted chunks / glossary), so no ``trading_knowledge/``
files are read and no index is built.

Bugs pinned here (each fix's test fails on the pre-change module):

* a chunk whose ``content`` key is present but ``None`` crashed the whole
  search result (``len(None)``); present-but-``None`` ``title``/``type`` leaked
  ``null`` fields;
* ``max_results <= 0`` and an empty/whitespace ``query`` were forwarded to the
  retriever, silently returning "no knowledge found" instead of a clear error;
* a glossary term with surrounding whitespace ("  FVG ") missed although the
  glossary has the term.
"""

from __future__ import annotations

import asyncio
import inspect

import pytest

from src.llm.tools.knowledge_tools import (
    KNOWLEDGE_TOOL_DEFINITIONS,
    KNOWLEDGE_TOOL_HANDLERS,
    get_glossary_term,
    search_trading_knowledge,
)


class _FakeRAG:
    def __init__(self, chunks=None, glossary=None, error=None):
        self._chunks = chunks or []
        self._glossary = glossary or {}
        self._error = error
        self.calls: list[tuple] = []

    def retrieve_context(self, query, max_results=5):
        self.calls.append(("search", query, max_results))
        if self._error:
            raise self._error
        return self._chunks[:max_results]

    def get_glossary_term(self, term):
        self.calls.append(("glossary", term))
        if self._error:
            raise self._error
        # Mirrors the real lookup: exact key, then lowercase.
        return self._glossary.get(term, self._glossary.get(term.lower()))


@pytest.fixture
def rag(monkeypatch):
    holder = {"rag": _FakeRAG()}

    def _install(rag_instance):
        holder["rag"] = rag_instance
        return rag_instance

    monkeypatch.setattr("src.llm.trading_knowledge_rag.get_trading_rag", lambda: holder["rag"])
    return holder


def _run(coro):
    return asyncio.run(coro)


def _chunk(**overrides) -> dict:
    chunk = {"title": "Fair Value Gaps", "type": "concept", "content": "An FVG is a three-candle imbalance."}
    chunk.update(overrides)
    return chunk


# ---------------------------------------------------------------------------
# Registry / tool-definition shape
# ---------------------------------------------------------------------------


def test_definitions_match_handlers_and_are_openai_shaped():
    names = [d["function"]["name"] for d in KNOWLEDGE_TOOL_DEFINITIONS]
    assert sorted(names) == sorted(KNOWLEDGE_TOOL_HANDLERS)
    assert set(names) == {"search_trading_knowledge", "get_glossary_term"}
    for d in KNOWLEDGE_TOOL_DEFINITIONS:
        assert d["type"] == "function"
        assert isinstance(d["function"]["name"], str)
        assert isinstance(d["function"]["description"], str)
        params = d["function"]["parameters"]
        assert params["type"] == "object"
        assert set(params) <= {"type", "properties", "required"}
    for name, handler in KNOWLEDGE_TOOL_HANDLERS.items():
        assert inspect.iscoroutinefunction(handler), name


# ---------------------------------------------------------------------------
# search_trading_knowledge
# ---------------------------------------------------------------------------


def test_search_happy_path(rag):
    rag["rag"] = _FakeRAG(chunks=[_chunk(), _chunk(title="Order Blocks", type="glossary")])
    out = _run(search_trading_knowledge("fair value gap"))
    assert out == {
        "query": "fair value gap",
        "results": [
            {"title": "Fair Value Gaps", "type": "concept", "content": "An FVG is a three-candle imbalance."},
            {"title": "Order Blocks", "type": "glossary", "content": "An FVG is a three-candle imbalance."},
        ],
        "count": 2,
    }
    # max_results is forwarded to the retriever
    assert rag["rag"].calls == [("search", "fair value gap", 3)]


def test_search_respects_max_results(rag):
    rag["rag"] = _FakeRAG(chunks=[_chunk(), _chunk(), _chunk(), _chunk()])
    out = _run(search_trading_knowledge("fvg", max_results=2))
    assert out["count"] == 2
    assert rag["rag"].calls == [("search", "fvg", 2)]


def test_search_truncates_long_content(rag):
    rag["rag"] = _FakeRAG(chunks=[_chunk(content="x" * 800)])
    out = _run(search_trading_knowledge("fvg"))
    content = out["results"][0]["content"]
    assert len(content) == 503  # 500 + "..."
    assert content.endswith("...")


def test_search_missing_content_key_falls_back_to_chunk_repr(rag):
    chunk = {"title": "T", "type": "concept"}  # no content key at all
    rag["rag"] = _FakeRAG(chunks=[chunk])
    out = _run(search_trading_knowledge("fvg"))
    assert out["results"][0]["content"] == str(chunk)


def test_search_none_content_does_not_crash(rag):
    rag["rag"] = _FakeRAG(chunks=[_chunk(content=None)])
    out = _run(search_trading_knowledge("fvg"))
    assert "error" not in out, f"old code crashes: {out.get('error')}"
    assert isinstance(out["results"][0]["content"], str)


def test_search_none_title_falls_back_to_file(rag):
    rag["rag"] = _FakeRAG(chunks=[_chunk(title=None, file="concepts/fvg.md")])
    out = _run(search_trading_knowledge("fvg"))
    assert out["results"][0]["title"] == "concepts/fvg.md"


def test_search_none_type_defaults_to_unknown(rag):
    rag["rag"] = _FakeRAG(chunks=[_chunk(type=None)])
    out = _run(search_trading_knowledge("fvg"))
    assert out["results"][0]["type"] == "unknown"


def test_search_no_results(rag):
    rag["rag"] = _FakeRAG(chunks=[])
    out = _run(search_trading_knowledge("quantum theta"))
    assert out == {"query": "quantum theta", "results": [], "count": 0}


def test_search_retriever_failure_is_an_error(rag):
    rag["rag"] = _FakeRAG(error=RuntimeError("index corrupted"))
    out = _run(search_trading_knowledge("fvg"))
    assert "index corrupted" in out["error"]


@pytest.mark.parametrize("bad_query", ["", "   "])
def test_search_rejects_empty_query(rag, bad_query):
    out = _run(search_trading_knowledge(bad_query))
    assert "error" in out, "an empty query must be refused, not forwarded to the retriever"
    assert "query" in out["error"]
    assert rag["rag"].calls == []  # never reached the retriever


@pytest.mark.parametrize("bad_max", [0, -1])
def test_search_rejects_non_positive_max_results(rag, bad_max):
    rag["rag"] = _FakeRAG(chunks=[_chunk()])
    out = _run(search_trading_knowledge("fvg", max_results=bad_max))
    assert "error" in out, f"max_results={bad_max} must be refused, not silently return zero results"
    assert "max_results" in out["error"]
    assert rag["rag"].calls == []


# ---------------------------------------------------------------------------
# get_glossary_term
# ---------------------------------------------------------------------------


def test_glossary_found(rag):
    rag["rag"] = _FakeRAG(glossary={"FVG": "A three-candle imbalance."})
    out = _run(get_glossary_term("FVG"))
    assert out == {"term": "FVG", "definition": "A three-candle imbalance.", "found": True}


def test_glossary_not_found_has_hint(rag):
    rag["rag"] = _FakeRAG(glossary={"FVG": "..."})
    out = _run(get_glossary_term("omega"))
    assert out["found"] is False
    assert out["definition"] is None
    assert "search_trading_knowledge" in out["hint"]


def test_glossary_whitespace_term_is_trimmed(rag):
    rag["rag"] = _FakeRAG(glossary={"FVG": "A three-candle imbalance."})
    out = _run(get_glossary_term("  FVG  "))
    assert out["found"] is True, "a padded term must still resolve"
    assert out["term"] == "FVG"


def test_glossary_retriever_failure_is_an_error(rag):
    rag["rag"] = _FakeRAG(error=RuntimeError("glossary boom"))
    out = _run(get_glossary_term("FVG"))
    assert "glossary boom" in out["error"]
