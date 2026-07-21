"""EmbeddingRAG — Semantic knowledge retrieval via sentence embeddings.

Replaces keyword matching with cosine-similarity search over embedded
document chunks.  Uses ``all-MiniLM-L6-v2`` (~80 MB, runs locally).

Usage::

    rag = EmbeddingRAG()
    chunks = rag.retrieve_context("margin cascade overnight", top_k=3)
    # Returns semantically relevant chunks even without keyword overlap.
"""

from __future__ import annotations

import hashlib
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
        cache_dir: str = "data/rag_cache",
    ):
        self.knowledge_dir = Path(knowledge_dir)
        self.model_name = model_name
        self.cache_dir = Path(cache_dir)
        self._model = None
        self._embeddings: np.ndarray | None = None
        self._chunks: list[dict[str, Any]] = []
        self._initialized = False
        self._kg = None  # KnowledgeGraph — lazy-loaded

    @staticmethod
    def _chunk_id(chunk: dict) -> str:
        return hashlib.sha256((chunk["title"] + "\x00" + chunk["content"]).encode("utf-8")).hexdigest()[:16]

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

        self._embeddings = self._load_or_build_embeddings()
        self._initialized = True

    def _load_or_build_embeddings(self) -> np.ndarray | None:
        """Return embedding matrix aligned with self._chunks, using the disk cache."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = self.cache_dir / "manifest.json"
        vectors_path = self.cache_dir / "embeddings.npz"

        manifest: dict = {}
        vectors: dict[str, np.ndarray] = {}
        if manifest_path.exists() and vectors_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                vectors = dict(np.load(vectors_path))
            except Exception as e:
                logger.warning(f"EmbeddingRAG cache unreadable, rebuilding: {e}")
                manifest, vectors = {}, {}

        dim = self._model.get_sentence_embedding_dimension()
        out = np.zeros((len(self._chunks), dim), dtype=np.float32)
        new_manifest: dict = {}
        to_embed: list[int] = []

        for i, chunk in enumerate(self._chunks):
            cid = self._chunk_id(chunk)
            new_manifest[cid] = {
                "title": chunk["title"],
                "type": chunk["type"],
                "content": chunk["content"],
            }
            if cid in vectors and cid in manifest:
                out[i] = vectors[cid]
            else:
                to_embed.append(i)

        if to_embed:
            texts = [self._chunks[i]["content"] for i in to_embed]
            logger.info(f"EmbeddingRAG: embedding {len(texts)} new/changed chunks (cache had {len(vectors)})")
            fresh = self._model.encode(texts, show_progress_bar=False)
            for pos, i in enumerate(to_embed):
                out[i] = fresh[pos]

        try:
            np.savez(vectors_path, **{cid: out[i] for i, cid in enumerate(new_manifest)})
            manifest_path.write_text(json.dumps(new_manifest), encoding="utf-8")
        except Exception as e:
            logger.warning(f"EmbeddingRAG: could not persist cache: {e}")

        return out

    # -- document collection -----------------------------------------------

    def _collect_documents(self) -> list[dict[str, Any]]:
        """Collect all knowledge documents into a flat list."""
        chunks: list[dict[str, Any]] = []

        # Concept docs
        concepts_dir = self.knowledge_dir / "core_concepts"
        if concepts_dir.exists():
            for md_file in sorted(concepts_dir.glob("*.md")):
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
                for md_file in sorted(hy_dir.glob("*.md")):
                    try:
                        content = md_file.read_text(encoding="utf-8")
                        chunks.extend(self._chunk_document(content, md_file.stem, f"{status_dir_name}_hypothesis"))
                    except Exception as e:
                        logger.warning(f"Failed to read {md_file}: {e}")

        # Glossary terms
        glossary_path = self.knowledge_dir / "trading_glossary.json"
        if glossary_path.exists():
            try:
                glossary = json.loads(glossary_path.read_text(encoding="utf-8"))
                for term, definition in glossary.items():
                    chunks.append(
                        {
                            "title": term,
                            "type": "glossary",
                            "content": f"{term}: {definition}",
                        }
                    )
            except Exception as e:
                logger.warning(f"Failed to load glossary: {e}")

        return chunks

    @staticmethod
    def _chunk_document(content: str, title: str, doc_type: str, max_chunk_chars: int = 600) -> list[dict[str, Any]]:
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

    def retrieve_context(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
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

    def _graph_neighbor_chunks(self, query: str, semantic_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
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

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Alias for retrieve_context."""
        return self.retrieve_context(query, top_k)
