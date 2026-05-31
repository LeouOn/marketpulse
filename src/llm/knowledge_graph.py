"""Knowledge Graph — Entity-relationship graph for trading concepts.

Builds a directed graph from the trading knowledge base where:
- Nodes are concepts, symbols, indicators, hypotheses
- Edges represent relationships: correlated_with, inverse_to, affects, confirms

Used by EmbeddingRAG to enrich retrieval with graph neighbors.

Builds at startup, ~100 nodes, ~200 edges. In-memory via networkx.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import networkx as nx
from loguru import logger


# ---------------------------------------------------------------------------
# Pre-defined market structure relationships
# ---------------------------------------------------------------------------

_MARKET_STRUCTURE_EDGES: list[tuple[str, str, str]] = [
    # Equity index correlations
    ("SPY", "correlated_with", "QQQ"),
    ("SPY", "correlated_with", "ES_F"),
    ("QQQ", "correlated_with", "NQ_F"),
    ("IWM", "correlated_with", "SPY"),
    ("DIA", "correlated_with", "SPY"),

    # Inverse relationships
    ("VIX", "inverse_to", "SPY"),
    ("VIX", "inverse_to", "QQQ"),
    ("DXY", "inverse_to", "GLD"),
    ("DXY", "inverse_to", "BTC-USD"),
    ("TNX", "inverse_to", "TLT"),
    ("TNX", "inverse_to", "SPY"),

    # Volatility / fear
    ("VIX", "indicates", "fear"),
    ("VIX", "indicates", "complacency"),
    ("put_call_ratio", "confirms", "VIX"),
    ("VOLD", "confirms", "volume"),
    ("TICK", "confirms", "momentum"),

    # Breadth components
    ("advance_decline", "component_of", "breadth"),
    ("mcclellan_oscillator", "component_of", "breadth"),
    ("new_highs_lows", "component_of", "breadth"),
    ("breadth", "confirms", "SPY"),
    ("breadth", "confirms", "QQQ"),

    # ICT / Smart Money concepts
    ("FVG", "type_of", "imbalance"),
    ("order_block", "type_of", "support_resistance"),
    ("liquidity_sweep", "precedes", "reversal"),
    ("CVD", "confirms", "order_flow"),
    ("OTE", "type_of", "retracement"),

    # Crypto-specific
    ("BTC-USD", "correlated_with", "ETH-USD"),
    ("BTC-USD", "correlated_with", "SOL-USD"),
    ("funding_rate", "affects", "BTC-PERP"),
    ("funding_rate", "affects", "ETH-PERP"),
    ("open_interest", "confirms", "trend"),
    ("liquidation_cascade", "affects", "BTC-USD"),
    ("overnight_margin", "triggers", "liquidation_cascade"),

    # Macro intermarket
    ("crude_oil", "affects", "XLE"),
    ("crude_oil", "correlated_with", "USD_CAD"),
    ("gold", "inverse_to", "real_yields"),
    ("yield_curve", "indicates", "recession_risk"),
    ("fed_funds", "affects", "SPY"),
    ("fed_funds", "affects", "BTC-USD"),

    # Technical indicators
    ("RSI", "indicates", "overbought_oversold"),
    ("MACD", "indicates", "momentum_shift"),
    ("ATR", "measures", "volatility"),
    ("sma_20", "type_of", "moving_average"),
    ("sma_50", "type_of", "moving_average"),
    ("sma_200", "type_of", "moving_average"),
    ("volume_profile", "identifies", "support_resistance"),
]


class KnowledgeGraph:
    """Entity-relationship graph for trading concept enrichment.

    Usage::

        kg = KnowledgeGraph()
        neighbors = kg.traverse("VIX", depth=1)
        # → ["SPY", "QQQ", "fear", "complacency", "put_call_ratio"]
    """

    def __init__(self, knowledge_dir: str = "trading_knowledge"):
        self.knowledge_dir = Path(knowledge_dir)
        self.graph = nx.DiGraph()
        self._built = False
        self._build()

    # -- build ------------------------------------------------------------

    def _build(self) -> None:
        """Construct the graph from all knowledge sources."""
        # 1. Glossary terms → concept nodes
        glossary_path = self.knowledge_dir / "trading_glossary.json"
        if glossary_path.exists():
            try:
                glossary = json.loads(glossary_path.read_text(encoding="utf-8"))
                for term in glossary:
                    node_id = term.lower().replace(" ", "_").replace("-", "_")
                    self.graph.add_node(
                        node_id, type="concept", label=term, source="glossary"
                    )
                logger.debug(f"KG: added {len(glossary)} glossary nodes")
            except Exception as e:
                logger.warning(f"KG glossary load error: {e}")

        # 2. Market structure edges (hardcoded)
        for src, rel, dst in _MARKET_STRUCTURE_EDGES:
            src_id = src.lower().replace(" ", "_").replace("-", "_")
            dst_id = dst.lower().replace(" ", "_").replace("-", "_")
            # Ensure nodes exist
            for nid in (src_id, dst_id):
                if nid not in self.graph:
                    self.graph.add_node(nid, type="entity", label=nid)
            self.graph.add_edge(src_id, dst_id, relation=rel)

        logger.debug(
            f"KG: {len(_MARKET_STRUCTURE_EDGES)} market structure edges added"
        )

        # 3. Hypothesis docs → extract mentioned entities
        hy_dir = self.knowledge_dir / "hypotheses" / "active"
        if hy_dir.exists():
            for md_file in hy_dir.glob("*.md"):
                try:
                    content = md_file.read_text(encoding="utf-8").lower()
                    # Simple extraction: look for known symbols/concepts
                    self._link_document_to_graph(md_file.stem, content)
                except Exception as e:
                    logger.warning(f"KG hypothesis load error {md_file}: {e}")

        # 4. Concept docs
        concepts_dir = self.knowledge_dir / "core_concepts"
        if concepts_dir.exists():
            for md_file in concepts_dir.glob("*.md"):
                try:
                    content = md_file.read_text(encoding="utf-8").lower()
                    self._link_document_to_graph(md_file.stem, content)
                except Exception as e:
                    logger.warning(f"KG concept load error {md_file}: {e}")

        self._built = True
        logger.info(
            f"KnowledgeGraph: {self.graph.number_of_nodes()} nodes, "
            f"{self.graph.number_of_edges()} edges"
        )

    def _link_document_to_graph(self, doc_name: str, content: str) -> None:
        """Scan document content for known graph entities and link them."""
        doc_id = doc_name.lower().replace(" ", "_").replace("-", "_")
        if doc_id not in self.graph:
            self.graph.add_node(doc_id, type="document", label=doc_name)

        # Find mentions of existing graph nodes in the document
        for node_id in list(self.graph.nodes()):
            if node_id == doc_id:
                continue
            # Match node_id or its label in content
            node_data = self.graph.nodes[node_id]
            label = node_data.get("label", node_id).lower()
            if node_id in content or label in content:
                if not self.graph.has_edge(doc_id, node_id):
                    self.graph.add_edge(doc_id, node_id, relation="mentions")

    # -- traversal --------------------------------------------------------

    def traverse(
        self, entity: str, depth: int = 1, max_results: int = 20
    ) -> list[dict[str, Any]]:
        """Return neighbors of an entity up to `depth` hops away.

        Args:
            entity: Entity name or ID (case-insensitive).
            depth: How many hops to traverse (1 = direct neighbors).
            max_results: Max neighbors to return.

        Returns:
            List of {id, label, type, relation, distance} dicts.
        """
        if not self._built:
            return []

        entity_id = entity.lower().replace(" ", "_").replace("-", "_")

        # Try exact match first, then fuzzy
        if entity_id not in self.graph:
            # Try matching against labels
            for nid, data in self.graph.nodes(data=True):
                label = data.get("label", "").lower()
                if entity_id in label or label in entity_id:
                    entity_id = nid
                    break
            else:
                return []  # Not found

        neighbors: list[dict[str, Any]] = []
        seen: set[str] = {entity_id}

        # BFS
        frontier = [entity_id]
        for d in range(depth):
            next_frontier: list[str] = []
            for node in frontier:
                for neighbor in self.graph.neighbors(node):
                    if neighbor in seen:
                        continue
                    seen.add(neighbor)
                    edge_data = self.graph.get_edge_data(node, neighbor) or {}
                    node_data = self.graph.nodes[neighbor]
                    neighbors.append({
                        "id": neighbor,
                        "label": node_data.get("label", neighbor),
                        "type": node_data.get("type", "entity"),
                        "relation": edge_data.get("relation", "related"),
                        "distance": d + 1,
                    })
                    next_frontier.append(neighbor)
            frontier = next_frontier
            if len(neighbors) >= max_results:
                break

        return neighbors[:max_results]

    def get_related_concepts(self, query: str, max_results: int = 5) -> list[str]:
        """Convenience: return concept labels related to a query."""
        results = self.traverse(query, depth=1, max_results=max_results)
        return [r["label"] for r in results if r["type"] == "concept"]
