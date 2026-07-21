# tests/rag/test_embedding_cache.py
import sys
import types

import numpy as np
import pytest


class _FakeModel:
    def __init__(self, *a, **kw):
        self.encode_calls = 0

    def get_sentence_embedding_dimension(self):
        return 4

    def encode(self, texts, show_progress_bar=False):
        self.encode_calls += 1
        return np.array([[float(len(t)), 1.0, 0.0, 0.0] for t in texts])


@pytest.fixture()
def fake_st(monkeypatch):
    module = types.ModuleType("sentence_transformers")
    model = _FakeModel()
    module.SentenceTransformer = lambda *a, **kw: model
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    return model


def _make_kb(tmp_path):
    kb = tmp_path / "kb"
    (kb / "core_concepts").mkdir(parents=True)
    (kb / "core_concepts" / "alpha.md").write_text("alpha content about gaps", encoding="utf-8")
    (kb / "trading_glossary.json").write_text('{"FVG": "fair value gap"}', encoding="utf-8")
    return kb


def test_second_instance_uses_cache(tmp_path, fake_st):
    from src.llm.embedding_rag import EmbeddingRAG

    kb = _make_kb(tmp_path)
    cache = tmp_path / "cache"

    rag1 = EmbeddingRAG(str(kb), cache_dir=str(cache))
    chunks1 = rag1.retrieve_context("gaps", top_k=2)
    assert chunks1, "expected retrieval results"
    calls_after_first = fake_st.encode_calls
    assert calls_after_first >= 1

    rag2 = EmbeddingRAG(str(kb), cache_dir=str(cache))
    chunks2 = rag2.retrieve_context("gaps", top_k=2)
    assert fake_st.encode_calls == calls_after_first, "unchanged docs must not be re-embedded"
    assert [c["content"] for c in chunks1] == [c["content"] for c in chunks2]


def test_changed_file_reembeds_only_changed(tmp_path, fake_st):
    from src.llm.embedding_rag import EmbeddingRAG

    kb = _make_kb(tmp_path)
    cache = tmp_path / "cache"
    EmbeddingRAG(str(kb), cache_dir=str(cache)).retrieve_context("gaps")
    baseline = fake_st.encode_calls

    (kb / "trading_glossary.json").write_text('{"FVG": "CHANGED definition"}', encoding="utf-8")
    rag = EmbeddingRAG(str(kb), cache_dir=str(cache))
    rag.retrieve_context("FVG")
    assert fake_st.encode_calls > baseline, "changed doc must trigger re-embed"
