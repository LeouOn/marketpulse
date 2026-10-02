"""Offline tests for ``src/llm/knowledge_graph.py``.

Storage points at tmp_path (glossary JSON, hypothesis/concept markdown are
written per test); no LLM, no embeddings, no network. The hardcoded market
structure edges make the graph non-empty even with an empty knowledge dir.
"""

from __future__ import annotations

import json

import pytest

from src.llm.knowledge_graph import _MARKET_STRUCTURE_EDGES, KnowledgeGraph


def _write_glossary(tmp_path, payload) -> None:
    (tmp_path / "trading_glossary.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_doc(tmp_path, subdir, name, content) -> None:
    d = tmp_path / subdir
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.md").write_text(content, encoding="utf-8")


GLOSSARY = {
    "VIX": "Volatility index.",
    "Order Flow": "Buy/sell pressure.",
    "Fair Value Gap": "An imbalance in price.",
}


@pytest.fixture
def kg(tmp_path) -> KnowledgeGraph:
    _write_glossary(tmp_path, GLOSSARY)
    return KnowledgeGraph(knowledge_dir=str(tmp_path))


# ---------------------------------------------------------------------------
# Build: structure edges, glossary, documents
# ---------------------------------------------------------------------------


def test_structure_edges_exist_even_with_empty_knowledge_dir(tmp_path):
    graph = KnowledgeGraph(knowledge_dir=str(tmp_path / "does_not_exist"))

    assert graph.graph.number_of_edges() >= len(_MARKET_STRUCTURE_EDGES)
    neighbors = graph.traverse("VIX", depth=1)
    ids = {n["id"] for n in neighbors}
    assert {"spy", "qqq", "fear", "complacency"} <= ids


def test_glossary_dict_creates_concept_nodes(kg):
    for term in GLOSSARY:
        node_id = term.lower().replace(" ", "_").replace("-", "_")
        assert node_id in kg.graph
        assert kg.graph.nodes[node_id]["type"] == "concept"
        assert kg.graph.nodes[node_id]["label"] == term
        assert kg.graph.nodes[node_id]["source"] == "glossary"


def test_glossary_list_of_terms_also_supported(tmp_path):
    _write_glossary(tmp_path, ["RSI", "MACD"])
    graph = KnowledgeGraph(knowledge_dir=str(tmp_path))

    assert "rsi" in graph.graph and graph.graph.nodes["rsi"]["type"] == "concept"


def test_corrupt_glossary_degrades_to_structure_only(tmp_path):
    (tmp_path / "trading_glossary.json").write_text("{not valid json", encoding="utf-8")

    graph = KnowledgeGraph(knowledge_dir=str(tmp_path))

    # No concepts, but the graph is still built and traversable.
    assert graph.traverse("VIX") != []
    assert all(n["type"] != "concept" for n in graph.traverse("VIX"))
    assert graph.get_related_concepts("VIX") == []


def test_one_bad_glossary_entry_stops_processing_at_that_entry(tmp_path):
    """Pinned current behaviour (reported): the try wraps the whole loop, so a
    single non-string entry aborts the glossary mid-way -- entries already
    processed persist, the rest are lost."""
    _write_glossary(tmp_path, ["AAA_TERM", 12345, "ZZZ_TERM"])

    graph = KnowledgeGraph(knowledge_dir=str(tmp_path))

    assert "aaa_term" in graph.graph  # processed before the bad entry
    assert "zzz_term" not in graph.graph  # lost after the crash


def test_documents_are_linked_via_mentions(tmp_path):
    _write_glossary(tmp_path, GLOSSARY)
    _write_doc(tmp_path, "hypotheses/active", "vix_study", "We study VIX and SPY behaviour.")
    _write_doc(tmp_path, "core_concepts", "macro_notes", "Notes on QQQ and breadth.")

    graph = KnowledgeGraph(knowledge_dir=str(tmp_path))

    assert graph.graph.nodes["vix_study"]["type"] == "document"
    assert graph.graph["vix_study"]["vix"]["relation"] == "mentions"
    assert graph.graph["vix_study"]["spy"]["relation"] == "mentions"
    assert graph.graph["macro_notes"]["qqq"]["relation"] == "mentions"


def test_document_named_like_an_entity_does_not_duplicate(tmp_path):
    _write_glossary(tmp_path, GLOSSARY)
    _write_doc(tmp_path, "core_concepts", "vix", "All about VIX spikes.")

    graph = KnowledgeGraph(knowledge_dir=str(tmp_path))

    # Single node, glossary typing wins, and the self-mention is skipped.
    assert graph.graph.nodes["vix"]["type"] == "concept"
    assert not graph.graph.has_edge("vix", "vix")


def test_duplicate_builds_are_independent(tmp_path, kg):
    again = KnowledgeGraph(knowledge_dir=str(tmp_path))

    assert again is not kg
    assert again.graph.number_of_nodes() == kg.graph.number_of_nodes()


# ---------------------------------------------------------------------------
# traverse: neighbours, direction, casing, limits
# ---------------------------------------------------------------------------


def test_traverse_returns_rich_neighbor_records(kg):
    neighbors = kg.traverse("VIX", depth=1)

    by_id = {n["id"]: n for n in neighbors}
    assert by_id["spy"]["relation"] == "inverse_to"
    assert by_id["spy"]["distance"] == 1
    assert by_id["spy"]["type"] in ("entity", "concept")
    assert by_id["fear"]["relation"] == "indicates"


def test_traverse_is_case_and_separator_insensitive(kg):
    for spelling in ("VIX", "vix", "BTC-USD", "btc_usd", "btc usd"):
        assert kg.traverse(spelling, depth=1) != [], spelling


def test_traverse_depth_two_marks_distance(kg):
    neighbors = kg.traverse("VIX", depth=2)

    distances = {n["distance"] for n in neighbors}
    assert 1 in distances and 2 in distances


def test_traverse_depth_zero_and_max_results_zero(kg):
    assert kg.traverse("VIX", depth=0) == []
    assert kg.traverse("VIX", depth=1, max_results=0) == []


def test_traverse_respects_max_results(kg):
    neighbors = kg.traverse("VIX", depth=2, max_results=3)

    assert len(neighbors) == 3


def test_traverse_follows_out_edges_only(kg):
    """Pinned current behaviour (reported): successor edges only, so QQQ does
    not see SPY even though SPY->QQQ exists (asymmetric relation data)."""
    qqq_neighbors = {n["id"] for n in kg.traverse("QQQ", depth=1)}

    assert "spy" not in qqq_neighbors  # SPY -> QQQ is an IN-edge of QQQ
    assert "nq_f" in qqq_neighbors  # QQQ -> NQ_F is an OUT-edge


def test_traverse_unknown_entity_returns_empty(kg):
    assert kg.traverse("nonexistent_entity", depth=3) == []


def test_traverse_fuzzy_label_match(kg):
    # "qq" is not a node id, but the entity label "qqq" contains it, and qqq
    # has an out-edge to nq_f.
    neighbors = kg.traverse("qq", depth=1)

    assert "nq_f" in {n["id"] for n in neighbors}


def test_traverse_empty_none_and_whitespace_entities_return_empty(kg):
    """An empty/None/blank entity used to crash (AttributeError on None) or
    fuzzy-match an arbitrary node ('' in label is always true)."""
    assert kg.traverse("") == []
    assert kg.traverse(None) == []
    assert kg.traverse("   ") == []


# ---------------------------------------------------------------------------
# get_related_concepts
# ---------------------------------------------------------------------------


def test_get_related_concepts_returns_only_concept_labels(kg):
    related = kg.get_related_concepts("VIX", max_results=10)

    # Glossary VIX node is a concept; structure neighbours are entities.
    assert isinstance(related, list)
    assert all(r in GLOSSARY for r in related)  # only glossary labels can appear


def test_get_related_concepts_with_no_glossary(tmp_path):
    graph = KnowledgeGraph(knowledge_dir=str(tmp_path))

    assert graph.get_related_concepts("VIX") == []


def test_graph_is_serializable_via_networkx(tmp_path, kg):
    """No persistence API exists in the module (reported), but the graph must
    at least round-trip through networkx's standard node-link format."""
    from networkx.readwrite import json_graph

    data = json_graph.node_link_data(kg.graph)
    restored = json_graph.node_link_graph(data)

    assert restored.number_of_nodes() == kg.graph.number_of_nodes()
    assert restored.number_of_edges() == kg.graph.number_of_edges()
    assert set(restored.nodes()) == set(kg.graph.nodes())
