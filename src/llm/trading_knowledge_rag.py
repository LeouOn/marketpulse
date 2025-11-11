"""Trading Knowledge RAG (Retrieval-Augmented Generation) System
Lightweight keyword-based knowledge retrieval for trading concepts
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from loguru import logger


class TradingKnowledgeRAG:
    """Simple keyword-based knowledge retriever for trading concepts"""
    
    def __init__(self, knowledge_dir: str = "trading_knowledge"):
        self.knowledge_dir = Path(knowledge_dir)
        self.glossary = self._load_glossary()
        self.concept_docs = self._load_concept_documents()
        self.hypothesis_docs = self._load_hypothesis_documents()
        
        logger.info(f"TradingKnowledgeRAG initialized with {len(self.glossary)} glossary terms")
        logger.info(f"Loaded {len(self.concept_docs)} concept documents")
        logger.info(f"Loaded {len(self.hypothesis_docs)} hypothesis documents")
    
    def _load_glossary(self) -> Dict[str, str]:
        """Load trading glossary from JSON file"""
        glossary_path = self.knowledge_dir / "trading_glossary.json"
        if not glossary_path.exists():
            logger.warning(f"Glossary not found at {glossary_path}")
            return {}
        
        try:
            with open(glossary_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading glossary: {e}")
            return {}
    
    def _load_concept_documents(self) -> List[Dict[str, Any]]:
        """Load all concept documents from core_concepts directory"""
        concept_docs = []
        concepts_dir = self.knowledge_dir / "core_concepts"
        
        if not concepts_dir.exists():
            logger.warning(f"Concepts directory not found at {concepts_dir}")
            return concept_docs
        
        for md_file in concepts_dir.glob("*.md"):
            try:
                content = md_file.read_text(encoding='utf-8')
                concept_docs.append({
                    'file': str(md_file),
                    'title': md_file.stem.replace('_', ' ').title(),
                    'content': content,
                    'type': 'concept'
                })
            except Exception as e:
                logger.error(f"Error loading concept doc {md_file}: {e}")
        
        return concept_docs
    
    def _load_hypothesis_documents(self) -> List[Dict[str, Any]]:
        """Load all hypothesis documents from hypotheses directory"""
        hypothesis_docs = []
        hypotheses_dir = self.knowledge_dir / "hypotheses"
        
        if not hypotheses_dir.exists():
            logger.warning(f"Hypotheses directory not found at {hypotheses_dir}")
            return hypothesis_docs
        
        # Load active hypotheses
        active_dir = hypotheses_dir / "active"
        if active_dir.exists():
            for md_file in active_dir.glob("*.md"):
                try:
                    content = md_file.read_text(encoding='utf-8')
                    hypothesis_docs.append({
                        'file': str(md_file),
                        'title': md_file.stem.replace('_', ' ').title(),
                        'content': content,
                        'type': 'hypothesis',
                        'status': 'active'
                    })
                except Exception as e:
                    logger.error(f"Error loading active hypothesis {md_file}: {e}")
        
        # Load tested hypotheses
        tested_dir = hypotheses_dir / "tested"
        if tested_dir.exists():
            for md_file in tested_dir.glob("*.md"):
                try:
                    content = md_file.read_text(encoding='utf-8')
                    hypothesis_docs.append({
                        'file': str(md_file),
                        'title': md_file.stem.replace('_', ' ').title(),
                        'content': content,
                        'type': 'hypothesis',
                        'status': 'tested'
                    })
                except Exception as e:
                    logger.error(f"Error loading tested hypothesis {md_file}: {e}")
        
        return hypothesis_docs
    
    def retrieve_context(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieve relevant knowledge based on query keywords
        
        Args:
            query: User query or hypothesis to analyze
            max_results: Maximum number of context chunks to return
            
        Returns:
            List of relevant knowledge chunks with metadata
        """
        query_lower = query.lower()
        relevant_docs = []
        term_matches = []
        
        # 1. Check for glossary term matches
        for term, definition in self.glossary.items():
            if self._term_matches(term, query_lower):
                term_matches.append({
                    'type': 'glossary',
                    'term': term,
                    'content': f"**{term}**: {definition}",
                    'relevance_score': self._calculate_relevance(term, query_lower)
                })
        
        # 2. Check concept documents for keyword matches
        for doc in self.concept_docs:
            relevance = self._calculate_document_relevance(doc['content'], query_lower)
            if relevance > 0.3:  # Threshold for relevance
                relevant_docs.append({
                    'type': 'concept',
                    'title': doc['title'],
                    'content': self._extract_relevant_section(doc['content'], query_lower),
                    'file': doc['file'],
                    'relevance_score': relevance
                })
        
        # 3. Check hypothesis documents for matches
        for doc in self.hypothesis_docs:
            relevance = self._calculate_document_relevance(doc['content'], query_lower)
            if relevance > 0.3:
                relevant_docs.append({
                    'type': doc['status'] + '_hypothesis',
                    'title': doc['title'],
                    'content': self._extract_relevant_section(doc['content'], query_lower),
                    'file': doc['file'],
                    'relevance_score': relevance
                })
        
        # 4. Sort by relevance and return top results
        all_matches = term_matches + relevant_docs
        all_matches.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
        
        return all_matches[:max_results]
    
    def _term_matches(self, term: str, query: str) -> bool:
        """Check if glossary term matches query"""
        # Exact match or plural form
        if term.lower() in query:
            return True
        
        # Check for common variations
        variations = [
            term.lower(),
            term.lower() + 's',  # plural
            term.lower().replace('_', ' '),  # spaced version
        ]
        
        return any(var in query for var in variations)
    
    def _calculate_relevance(self, term: str, query: str) -> float:
        """Calculate relevance score for glossary term"""
        if term.lower() in query:
            return 1.0
        
        # Check if query contains related words
        term_words = set(term.lower().replace('_', ' ').split())
        query_words = set(query.split())
        
        overlap = term_words.intersection(query_words)
        return len(overlap) / len(term_words) if term_words else 0.0
    
    def _calculate_document_relevance(self, content: str, query: str) -> float:
        """Calculate relevance score for document based on keyword matches"""
        content_lower = content.lower()
        query_words = query.split()
        
        # Count matching keywords
        matches = sum(1 for word in query_words if word in content_lower)
        
        # Normalize by query length
        return matches / len(query_words) if query_words else 0.0
    
    def _extract_relevant_section(self, content: str, query: str, max_chars: int = 500) -> str:
        """Extract most relevant section of document"""
        content_lower = content.lower()
        query_words = query.split()
        
        # Find best matching paragraph
        paragraphs = content.split('\n\n')
        best_paragraph = ""
        best_score = 0
        
        for para in paragraphs:
            para_lower = para.lower()
            score = sum(1 for word in query_words if word in para_lower)
            
            if score > best_score:
                best_score = score
                best_paragraph = para
        
        # Return best paragraph or truncated content
        if best_paragraph:
            return best_paragraph[:max_chars] + "..." if len(best_paragraph) > max_chars else best_paragraph
        
        return content[:max_chars] + "..."
    
    def get_glossary_term(self, term: str) -> Optional[str]:
        """Get definition for specific glossary term"""
        return self.glossary.get(term, self.glossary.get(term.lower()))
    
    def get_related_terms(self, term: str) -> List[str]:
        """Get related glossary terms"""
        term_lower = term.lower()
        related = []
        
        for glossary_term in self.glossary.keys():
            if term_lower in glossary_term.lower() or glossary_term.lower() in term_lower:
                related.append(glossary_term)
        
        return related
    
    def add_glossary_term(self, term: str, definition: str) -> bool:
        """Add new term to glossary"""
        try:
            self.glossary[term] = definition
            
            # Save to file
            glossary_path = self.knowledge_dir / "trading_glossary.json"
            with open(glossary_path, 'w', encoding='utf-8') as f:
                json.dump(self.glossary, f, indent=2)
            
            logger.info(f"Added glossary term: {term}")
            return True
        except Exception as e:
            logger.error(f"Error adding glossary term: {e}")
            return False


# Simple keyword matcher for quick lookups
class KeywordKnowledgeRetriever:
    """Even simpler keyword-based retriever"""
    
    def __init__(self, knowledge_dir: str = "trading_knowledge"):
        self.knowledge_dir = Path(knowledge_dir)
        self.glossary = self._load_glossary()
    
    def _load_glossary(self) -> Dict[str, str]:
        """Load trading glossary"""
        glossary_path = self.knowledge_dir / "trading_glossary.json"
        if glossary_path.exists():
            try:
                with open(glossary_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {}
    
    def retrieve_context(self, query: str) -> List[str]:
        """Retrieve relevant context snippets"""
        query_lower = query.lower()
        relevant_docs = []
        
        # Check glossary
        for term, definition in self.glossary.items():
            if term.lower() in query_lower or any(word in term.lower() for word in query_lower.split()):
                relevant_docs.append(f"**{term}**: {definition}")
        
        # Check concept documents
        concepts_dir = self.knowledge_dir / "core_concepts"
        if concepts_dir.exists():
            for md_file in concepts_dir.glob("*.md"):
                try:
                    content = md_file.read_text(encoding='utf-8')
                    if any(word in content.lower() for word in query_lower.split()):
                        # Extract first relevant paragraph
                        paragraphs = content.split('\n\n')
                        for para in paragraphs:
                            if any(word in para.lower() for word in query_lower.split()):
                                relevant_docs.append(f"From {md_file.stem}: {para[:300]}...")
                                break
                except:
                    continue
        
        return relevant_docs[:3]  # Top 3 matches


# Global instance for convenience
_trading_rag_instance = None


def get_trading_rag(knowledge_dir: str = "trading_knowledge") -> TradingKnowledgeRAG:
    """Get or create global TradingKnowledgeRAG instance"""
    global _trading_rag_instance
    if _trading_rag_instance is None:
        _trading_rag_instance = TradingKnowledgeRAG(knowledge_dir)
    return _trading_rag_instance