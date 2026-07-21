"""Hybrid fusion: exact glossary term matches must surface even when the
semantic path returns unrelated chunks, and vice versa."""

import sys
import types

import numpy as np
import pytest


class _FakeModel:
    def get_sentence_embedding_dimension(self):
        return 4

    def encode(self, texts, show_progress_bar=False):
        # Everything orthogonal-ish: semantic scores ~uniform, so keyword signal must win
        # for exact-term queries.
        rng = np.random.default_rng(42)
        return rng.random((len(texts), 4))


@pytest.fixture()
def kb(tmp_path, monkeypatch):
    module = types.ModuleType("sentence_transformers")
    module.SentenceTransformer = lambda *a, **kw: _FakeModel()
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    d = tmp_path / "kb"
    (d / "core_concepts").mkdir(parents=True)
    (d / "core_concepts" / "structure.md").write_text(
        "Fair value gaps and order blocks explained in depth.", encoding="utf-8"
    )
    (d / "trading_glossary.json").write_text('{"FVG": "Fair Value Gap - a three-candle imbalance"}', encoding="utf-8")
    return d


def test_exact_glossary_term_boosted(tmp_path, kb, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from src.llm.trading_knowledge_rag import TradingKnowledgeRAG

    rag = TradingKnowledgeRAG(str(kb))
    results = rag.retrieve_context("what is FVG?", max_results=3)
    assert results, "expected results"
    top = results[0]
    assert top.get("type") == "glossary", f"exact glossary term should rank first, got {top}"
    assert "retrieval" in top


def test_semantic_results_still_integrated(tmp_path, kb, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from src.llm.trading_knowledge_rag import TradingKnowledgeRAG

    rag = TradingKnowledgeRAG(str(kb))
    results = rag.retrieve_context("order blocks", max_results=5)
    assert any(r.get("type") == "concept" for r in results)
