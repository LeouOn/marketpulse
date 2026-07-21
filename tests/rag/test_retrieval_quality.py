"""Retrieval quality gate. Runs with the real knowledge base.

Default (CI) run uses a stub embedder so no model download is needed; the
keyword path must still hit the threshold. With RUN_LIVE_TESTS=1 the real
embedding model is used and hybrid mode is measured.
"""

import json
import os
import sys
import types
from pathlib import Path

import numpy as np
import pytest

GOLDEN = Path(__file__).parent / "golden_queries.json"
KB_DIR = Path("trading_knowledge")

LIVE = os.environ.get("RUN_LIVE_TESTS") == "1"


def _hit(results, expect):
    haystack = " ".join(f"{r.get('title', '')} {r.get('term', '')} {r.get('file', '')}".lower() for r in results)
    return any(e.lower() in haystack for e in expect)


@pytest.fixture(scope="module")
def rag():
    if not LIVE:
        module = types.ModuleType("sentence_transformers")

        class _Stub:
            def get_sentence_embedding_dimension(self):
                return 8

            def encode(self, texts, show_progress_bar=False):
                # Pin to near-zero vectors so keyword dominates in CI and the
                # golden-query hit-rate is deterministic (per brief: do this
                # proactively to avoid random-vector outranking keyword).
                return np.full((len(texts), 8), 1e-6)

        module.SentenceTransformer = lambda *a, **kw: _Stub()
        sys.modules["sentence_transformers"] = module
    from src.llm.trading_knowledge_rag import TradingKnowledgeRAG

    return TradingKnowledgeRAG(str(KB_DIR))


def test_golden_hit_rate(rag, tmp_path, monkeypatch):
    monkeypatch.setattr("src.llm.embedding_rag.EmbeddingRAG.__init__", lambda self, *a, **kw: None, raising=False)
    queries = json.loads(GOLDEN.read_text(encoding="utf-8"))
    hits = 0
    misses = []
    for q in queries:
        results = rag.retrieve_context(q["query"], max_results=5)
        if _hit(results, q["expect"]):
            hits += 1
        else:
            misses.append(
                {
                    "query": q["query"],
                    "expect": q["expect"],
                    "got": [
                        {
                            "type": r.get("type"),
                            "title": r.get("title"),
                            "term": r.get("term"),
                            "file": r.get("file"),
                            "retrieval": r.get("retrieval"),
                        }
                        for r in results
                    ],
                }
            )
    rate = hits / len(queries)
    threshold = 0.8
    assert rate >= threshold, f"hit-rate {rate:.0%} < {threshold:.0%} on golden set; misses={misses}"
