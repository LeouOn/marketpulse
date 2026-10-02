"""Offline coverage for src/llm/tools/hypothesis_tools.py.

Two agent tools over ``HypothesisTester`` (which has its own test file and is
NOT modified here): ``list_active_hypotheses`` (list + counts) and
``get_hypothesis_detail`` (full parsed detail by name). Consumers:
``src/llm/agents/hypothesis_agent.py`` (tool names) and
``src/llm/tools/registry.py`` (``HYPOTHESIS_TOOL_DEFINITIONS`` /
``HYPOTHESIS_TOOL_HANDLERS``) — shapes pinned below.

Offline strategy: the tools construct ``HypothesisTester(_StubClient())``
internally on every call, so ``HypothesisTester.__init__`` is patched to
inject a fake knowledge RAG (skipping ``get_trading_rag()``) and point
``hypotheses_dir`` at a tmp_path. No network, no LLM, no repo files read.

Tests marked ``test_bug_*`` fail on the pre-fix module (proven against a
HEAD copy in the cycle-11 report); the rest pin existing behaviour and pass
on both versions. All calls go through ``hypothesis_tools.<fn>`` attribute
access so the HEAD-copy proof can swap ``sys.modules`` entries.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from src.llm.tools import hypothesis_tools

_RICH_MD = """# Overnight Margin Cascade

## Hypothesis Statement
Prices drift up overnight after strong sessions.

## Background
Historical margin behaviour.

## Mechanism
Margin cascade pushes prices.

## What to Look For
- rising overnight gaps
- funding stress

## Testing Criteria
- **Lookback Days:** 90
- **Confidence:** 0.95

### Data Requirements
- **Symbols:** SPY

### Success Metrics
- hit rate above 55%

## Related Concepts
- overnight drift
- margin

## Confounding Factors
- FOMC meetings

## Trading Implications
Long into close on strong days.
"""


class _FakeRAG:
    def retrieve_context(self, query: str, max_results: int = 5):
        return []


@pytest.fixture
def hypotheses_env(tmp_path, monkeypatch):
    """tmp_path-backed hypotheses dir; real RAG never constructed."""
    (tmp_path / "active").mkdir()
    (tmp_path / "tested").mkdir()

    from src.llm import hypothesis_tester as ht

    orig_init = ht.HypothesisTester.__init__

    def patched_init(self, llm_client, knowledge_rag=None):
        orig_init(self, llm_client, knowledge_rag=knowledge_rag or _FakeRAG())
        self.hypotheses_dir = tmp_path

    monkeypatch.setattr(ht.HypothesisTester, "__init__", patched_init)
    return tmp_path


def _run(coro):
    return asyncio.run(coro)


def _write(env, sub, name, content=_RICH_MD):
    (env / sub / f"{name}.md").write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Registry / tool-definition shape (what hypothesis_agent + registry consume)
# ---------------------------------------------------------------------------


def test_tool_definitions_shape():
    defs = hypothesis_tools.HYPOTHESIS_TOOL_DEFINITIONS
    assert isinstance(defs, list) and len(defs) == 2
    names = [d["function"]["name"] for d in defs]
    assert names == ["list_active_hypotheses", "get_hypothesis_detail"]
    for d in defs:
        assert d["type"] == "function"
        fn = d["function"]
        assert fn["description"]
        assert fn["parameters"]["type"] == "object"
        assert isinstance(fn["parameters"]["properties"], dict)
    assert defs[0]["function"]["parameters"]["required"] == []
    assert defs[1]["function"]["parameters"]["required"] == ["hypothesis_name"]


def test_tool_handlers_match_definitions():
    handlers = hypothesis_tools.HYPOTHESIS_TOOL_HANDLERS
    def_names = {d["function"]["name"] for d in hypothesis_tools.HYPOTHESIS_TOOL_DEFINITIONS}
    assert set(handlers) == def_names
    for name, handler in handlers.items():
        assert callable(handler), name
        assert asyncio.iscoroutinefunction(handler), name


# ---------------------------------------------------------------------------
# list_active_hypotheses
# ---------------------------------------------------------------------------


def test_list_empty_env(hypotheses_env):
    out = _run(hypothesis_tools.list_active_hypotheses())
    assert "error" not in out
    assert out["hypotheses"] == []
    assert out["count"] == 0
    assert out["active_count"] == 0
    datetime.fromisoformat(out["timestamp"])


def test_list_active_and_tested_counts(hypotheses_env):
    _write(hypotheses_env, "active", "alpha_one")
    _write(hypotheses_env, "active", "beta-two")
    _write(hypotheses_env, "tested", "gamma_done")
    out = _run(hypothesis_tools.list_active_hypotheses())
    assert out["count"] == 3
    assert out["active_count"] == 2
    by_name = {h["name"]: h["status"] for h in out["hypotheses"]}
    assert by_name == {"alpha_one": "active", "beta-two": "active", "gamma_done": "tested"}


def test_list_missing_dirs_no_crash(tmp_path, monkeypatch):
    # A hypotheses dir that does not exist at all must not raise.
    from src.llm import hypothesis_tester as ht

    orig_init = ht.HypothesisTester.__init__

    def patched_init(self, llm_client, knowledge_rag=None):
        orig_init(self, llm_client, knowledge_rag=knowledge_rag or _FakeRAG())
        self.hypotheses_dir = tmp_path / "does_not_exist"

    monkeypatch.setattr(ht.HypothesisTester, "__init__", patched_init)
    out = _run(hypothesis_tools.list_active_hypotheses())
    assert out["count"] == 0


# ---------------------------------------------------------------------------
# get_hypothesis_detail
# ---------------------------------------------------------------------------


def test_detail_full_parse_from_active(hypotheses_env):
    _write(hypotheses_env, "active", "overnight_margin_cascade")
    out = _run(hypothesis_tools.get_hypothesis_detail("overnight_margin_cascade"))
    assert "error" not in out, out
    assert out["name"] == "overnight_margin_cascade"
    assert out["status"] == "active"
    assert "drift up overnight" in out["description"]
    assert out["mechanism"] == "Margin cascade pushes prices."
    assert out["what_to_look_for"] == ["rising overnight gaps", "funding stress"]
    assert isinstance(out["testing_criteria"], dict) and out["testing_criteria"]
    assert isinstance(out["data_requirements"], dict) and out["data_requirements"]
    assert out["success_metrics"] == ["hit rate above 55%"]
    assert out["confounding_factors"] == ["FOMC meetings"]
    assert out["trading_implications"] == "Long into close on strong days."
    datetime.fromisoformat(out["timestamp"])


def test_detail_from_tested_dir(hypotheses_env):
    _write(hypotheses_env, "tested", "archived_hyp")
    out = _run(hypothesis_tools.get_hypothesis_detail("archived_hyp"))
    assert out["status"] == "tested"


def test_detail_not_found(hypotheses_env):
    out = _run(hypothesis_tools.get_hypothesis_detail("nope"))
    assert "error" in out
    assert "nope" in out["error"]


def test_detail_empty_and_none_names_return_error(hypotheses_env):
    _write(hypotheses_env, "active", "real_one")
    for bad in ("", None):
        out = _run(hypothesis_tools.get_hypothesis_detail(bad))
        assert "error" in out, bad  # 'None.md'/empty never resolves -> not found


def test_detail_bare_markdown_returns_defaults(hypotheses_env):
    _write(hypotheses_env, "active", "skeleton", content="# Just a title\n\nNo sections.\n")
    out = _run(hypothesis_tools.get_hypothesis_detail("skeleton"))
    assert "error" not in out
    assert out["name"] == "skeleton"
    assert out["status"] == "active"
    assert out["mechanism"] == ""
    assert out["what_to_look_for"] == []
    assert out["testing_criteria"] == {}


def test_detail_uses_related_concepts_key(hypotheses_env):
    # The parser's plural field must surface under the same plural key —
    # consumers (hypothesis_agent prompts, registry callers) look for
    # "related_concepts". (Checked against HEAD: the key is correct there;
    # this is a pin, not a bug test.)
    _write(hypotheses_env, "active", "overnight_margin_cascade")
    out = _run(hypothesis_tools.get_hypothesis_detail("overnight_margin_cascade"))
    assert "related_concepts" in out, out.keys()
    assert "related_concept" not in out
    assert out["related_concepts"] == ["overnight drift", "margin"]
