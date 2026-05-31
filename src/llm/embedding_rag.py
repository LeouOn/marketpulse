"""EmbeddingRAG — Semantic knowledge retrieval via sentence embeddings.

Replaces keyword matching with cosine-similarity search over embedded
document chunks.  Uses ``all-MiniLM-L6-v2`` (~80 MB, runs locally).

Usage::

    rag = EmbeddingRAG()
    chunks = rag.retrieve_context("margin cascade overnight", top_k=3)
    # Returns semantically relevant chunks even without keyword overlap.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from loguru import logger


class EmbeddingRAG:
    """Semantic retrieval over the trading knowledge base.

    Embeds all concept docs, hypothesis docs, and glossary entries at
    init time, then uses cosine similarity for retrieval.
    """

    def __init__(
        self,
        knowledge_dir: str = "trading_knowledge",
        model_name: str = "all-MiniLM-L6-v2",
    ):
        self.knowledge_dir = Path(knowledge_dir)
        self.model_name = model_name
        self._model = None
        self._embeddings: np.ndarray | None = None
        self._chunks: list[dict[str, Any]] = []
        self._initialized = False
        self._kg = None  # KnowledgeGraph — lazy-loaded

    # -- lazy init ---------------------------------------------------------

    def _ensure_initialized(self) -> None:
        """Download model + embed all docs on first use."""
        if self._initialized:
            return

        logger.info(f"EmbeddingRAG: loading model '{self.model_name}' ...")
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
            try:
                dim = self._model.get_embedding_dimension()
            except AttributeError:
                dim = self._model.get_sentence_embedding_dimension()
            logger.info(f"EmbeddingRAG: model loaded ({dim}d)")
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            self._initialized = True  # mark done so we don't retry
            return

        # Collect all documents
        self._chunks = self._collect_documents()
        if not self._chunks:
            logger.warning("EmbeddingRAG: no documents found to embed")
            self._initialized = True
            return

        # Embed them
        texts = [c["content"] for c in self._chunks]
        logger.info(f"EmbeddingRAG: embedding {len(texts)} documents ...")
        self._embeddings = self._model.encode(texts, show_progress_bar=False)
        logger.info(
            f"EmbeddingRAG: {len(self._chunks)} docs embedded "
            f"({self._embeddings.shape[1]}d vectors)"
        )
        self._initialized = True

    # -- document collection -----------------------------------------------

    def _collect_documents(self) -> list[dict[str, Any]]:
        """Collect all knowledge documents into a flat list."""
        chunks: list[dict[str, Any]] = []

        # Concept docs
        concepts_dir = self.knowledge_dir / "core_concepts"
        if concepts_dir.exists():
            for md_file in concepts_dir.glob("*.md"):
                try:
                    content = md_file.read_text(encoding="utf-8")
                    # Split long docs into smaller chunks for better retrieval
                    chunks.extend(self._chunk_document(content, md_file.stem, "concept"))
                except Exception as e:
                    logger.warning(f"Failed to read {md_file}: {e}")

        # Hypothesis docs
        for status_dir_name in ("active", "tested"):
            hy_dir = self.knowledge_dir / "hypotheses" / status_dir_name
            if hy_dir.exists():
                for md_file in hy_dir.glob("*.md"):
                    try:
                        content = md_file.read_text(encoding="utf-8")
                        chunks.extend(
                            self._chunk_document(content, md_file.stem, f"{status_dir_name}_hypothesis")
                        )
                    except Exception as e:
                        logger.warning(f"Failed to read {md_file}: {e}")

        # Glossary terms
        glossary_path = self.knowledge_dir / "trading_glossary.json"
        if glossary_path.exists():
            try:
                glossary = json.loads(glossary_path.read_text(encoding="utf-8"))
                for term, definition in glossary.items():
                    chunks.append({
                        "title": term,
                        "type": "glossary",
                        "content": f"{term}: {definition}",
                    })
            except Exception as e:
                logger.warning(f"Failed to load glossary: {e}")

        return chunks

    @staticmethod
    def _chunk_document(
        content: str, title: str, doc_type: str, max_chunk_chars: int = 600
    ) -> list[dict[str, Any]]:
        """Split a long document into overlapping chunks for fine-grained retrieval."""
        if len(content) <= max_chunk_chars:
            return [{"title": title, "type": doc_type, "content": content}]

        chunks: list[dict[str, Any]] = []
        # Split on paragraph boundaries
        paragraphs = content.split("\n\n")
        current = ""
        for para in paragraphs:
            if len(current) + len(para) < max_chunk_chars:
                current += ("\n\n" if current else "") + para
            else:
                if current:
                    chunks.append({"title": title, "type": doc_type, "content": current})
                current = para
        if current:
            chunks.append({"title": title, "type": doc_type, "content": current})

        return chunks

    # -- retrieval ---------------------------------------------------------

    def retrieve_context(
        self, query: str, top_k: int = 5
    ) -> list[dict[str, Any]]:
        """Return top-K most semantically relevant chunks for a query.

        Falls back to empty list if the model isn't loaded.
        """
        self._ensure_initialized()

        if self._model is None or self._embeddings is None or len(self._chunks) == 0:
            return []

        try:
            query_embedding = self._model.encode([query], show_progress_bar=False)[0]

            # Cosine similarity
            similarities = np.dot(self._embeddings, query_embedding) / (
                np.linalg.norm(self._embeddings, axis=1) * np.linalg.norm(query_embedding) + 1e-10
            )

            top_indices = np.argsort(similarities)[::-1][:top_k]

            results = []
            for idx in top_indices:
                if similarities[idx] < 0.2:  # Minimum relevance threshold
                    continue
                chunk = dict(self._chunks[idx])
                chunk["score"] = float(similarities[idx])
                results.append(chunk)

            # -- Enrich with Knowledge Graph neighbors --------------------
            if len(results) > 0:
                self._ensure_kg()
                if self._kg is not None and self._kg is not False:
                    graph_chunks = self._graph_neighbor_chunks(query, results)
                    seen_contents = {c["content"] for c in results}
                    for gc in graph_chunks:
                        if gc["content"] not in seen_contents:
                            seen_contents.add(gc["content"])
                            results.append(gc)
                    results.sort(key=lambda x: x.get("score", 0), reverse=True)

            return results

        except Exception as e:
            logger.error(f"EmbeddingRAG retrieval error: {e}")
            return []

    def _ensure_kg(self) -> None:
        """Lazy-load the KnowledgeGraph."""
        if self._kg is not None:
            return
        try:
            from .knowledge_graph import KnowledgeGraph
            self._kg = KnowledgeGraph(self.knowledge_dir)
        except Exception as e:
            logger.warning(f"KnowledgeGraph unavailable: {e}")
            self._kg = False  # type: ignore

    def _graph_neighbor_chunks(
        self, query: str, semantic_results: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Return chunks for graph neighbors of top semantic hits."""
        if self._kg is None or self._kg is False:
            return []

        graph_chunks: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for sr in semantic_results[:3]:
            title = sr.get("title", "")
            neighbors = self._kg.traverse(title, depth=1, max_results=5)
            for neighbor in neighbors:
                nid = neighbor["id"]
                if nid in seen_ids:
                    continue
                seen_ids.add(nid)
                for chunk in self._chunks:
                    ctitle = chunk.get("title", "").lower().replace(" ", "_")
                    if nid in ctitle or ctitle in nid:
                        gc = dict(chunk)
                        gc["score"] = sr.get("score", 0.3) * 0.7
                        gc["source"] = f"graph:{neighbor['relation']}"
                        graph_chunks.append(gc)
                        break

        return graph_chunks

    def get_glossary_term(self, term: str) -> str | None:
        """Look up a glossary term via semantic matching."""
        chunks = self.retrieve_context(term, top_k=1)
        for chunk in chunks:
            if chunk.get("type") == "glossary":
                # Extract the definition part after "TERM: "
                content = chunk["content"]
                if ": " in content:
                    return content.split(": ", 1)[1]
                return content
        return None

    def search(
        self, query: str, top_k: int = 5
    ) -> list[dict[str, Any]]:
        """Alias for retrieve_context."""
        return self.retrieve_context(query, top_k)
