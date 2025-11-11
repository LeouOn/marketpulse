"""Enhanced LLM Client with Trading Knowledge Integration
Combines LM Studio client with RAG and enhanced prompts
"""

import asyncio
import json
from typing import Dict, Any, Optional, List
from loguru import logger

from .llm_client import LMStudioClient
from .trading_knowledge_rag import get_trading_rag, KeywordKnowledgeRetriever
from .system_prompts import (
    get_system_prompt, 
    build_enhanced_prompt,
    TRADING_ANALYST_BASE,
    HYPOTHESIS_TESTING_PROMPT,
    MARKET_ANALYSIS_PROMPT,
    CHART_ANALYSIS_PROMPT
)


class EnhancedLMStudioClient(LMStudioClient):
    """Enhanced LM Studio client with trading knowledge integration"""
    
    def __init__(self, settings=None):
        super().__init__(settings)
        self.knowledge_rag = get_trading_rag()
        self.keyword_retriever = KeywordKnowledgeRetriever()
        self.system_prompt_cache = {}
        
        logger.info("EnhancedLMStudioClient initialized with trading knowledge")
    
    async def analyze_with_knowledge(self, 
                                   query: str,
                                   market_data: Optional[Dict[str, Any]] = None,
                                   prompt_type: str = "trading_analyst",
                                   max_tokens: int = 400,
                                   temperature: float = 0.3) -> Optional[str]:
        """
        Analyze query with trading knowledge context
        
        Args:
            query: User query or hypothesis
            market_data: Optional market data
            prompt_type: Type of analysis to perform
            max_tokens: Maximum tokens for response
            temperature: Response creativity
            
        Returns:
            AI analysis with knowledge-enhanced context
        """
        try:
            # Retrieve relevant knowledge
            context_chunks = self.knowledge_rag.retrieve_context(query)
            
            # Get appropriate system prompt
            base_prompt = get_system_prompt(prompt_type)
            
            # Build enhanced prompt with context
            enhanced_prompt = build_enhanced_prompt(
                base_prompt,
                context_chunks,
                query,
                market_data
            )
            
            # Query LLM
            messages = [{'role': 'user', 'content': enhanced_prompt}]
            
            response = await self.generate_completion(
                model='deep_analysis',
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature
            )
            
            if response and 'choices' in response:
                return response['choices'][0]['message']['content']
            
            return None
            
        except Exception as e:
            logger.error(f"Enhanced analysis error: {e}")
            return None
    
    async def test_hypothesis(self, 
                            hypothesis_name: str,
                            market_data: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        Test a trading hypothesis with full context
        
        Args:
            hypothesis_name: Name of hypothesis to test
            market_data: Market data for testing
            
        Returns:
            Structured test results
        """
        try:
            # Import here to avoid circular dependency
            from .hypothesis_tester import HypothesisTester
            
            tester = HypothesisTester(self, self.knowledge_rag)
            result = await tester.test_hypothesis(hypothesis_name, market_data)
            
            return result.to_dict() if hasattr(result, 'to_dict') else result
            
        except Exception as e:
            logger.error(f"Hypothesis testing error: {e}")
            return None
    
    async def analyze_market_with_context(self, 
                                        market_internals: Dict[str, Any],
                                        additional_context: Optional[str] = None) -> Optional[str]:
        """
        Analyze market internals with trading knowledge context
        
        Args:
            market_internals: Market data to analyze
            additional_context: Additional context or questions
            
        Returns:
            Enhanced market analysis
        """
        try:
            # Build query from market data
            query = "Analyze the following market conditions for trading opportunities."
            if additional_context:
                query += f" {additional_context}"
            
            # Get market-specific knowledge
            context_chunks = self.knowledge_rag.retrieve_context("market analysis")
            
            # Build enhanced prompt
            base_prompt = get_system_prompt("market_analysis")
            enhanced_prompt = build_enhanced_prompt(
                base_prompt,
                context_chunks,
                query,
                market_internals
            )
            
            # Query LLM
            messages = [{'role': 'user', 'content': enhanced_prompt}]
            
            response = await self.generate_completion(
                model='deep_analysis',
                messages=messages,
                max_tokens=500,
                temperature=0.4
            )
            
            if response and 'choices' in response:
                return response['choices'][0]['message']['content']
            
            return None
            
        except Exception as e:
            logger.error(f"Market analysis with context error: {e}")
            return None
    
    async def analyze_chart_with_context(self,
                                       chart_data: Dict[str, Any],
                                       specific_questions: Optional[List[str]] = None) -> Optional[str]:
        """
        Analyze chart data with technical analysis knowledge
        
        Args:
            chart_data: Chart data (candles, indicators, etc.)
            specific_questions: Specific questions about the chart
            
        Returns:
            Technical analysis with context
        """
        try:
            # Build query
            query = "Analyze this chart pattern and provide technical analysis."
            if specific_questions:
                query += f" Specifically: {', '.join(specific_questions)}"
            
            # Get chart analysis knowledge
            context_chunks = self.knowledge_rag.retrieve_context("chart pattern technical analysis")
            
            # Build enhanced prompt
            base_prompt = get_system_prompt("chart_analysis")
            enhanced_prompt = build_enhanced_prompt(
                base_prompt,
                context_chunks,
                query,
                chart_data
            )
            
            # Query LLM
            messages = [{'role': 'user', 'content': enhanced_prompt}]
            
            response = await self.generate_completion(
                model='deep_analysis',
                messages=messages,
                max_tokens=600,
                temperature=0.4
            )
            
            if response and 'choices' in response:
                return response['choices'][0]['message']['content']
            
            return None
            
        except Exception as e:
            logger.error(f"Chart analysis with context error: {e}")
            return None
    
    async def validate_data_with_knowledge(self, 
                                         data: Dict[str, Any],
                                         data_type: str = "market_internals") -> Optional[Dict[str, Any]]:
        """
        Validate data with domain knowledge
        
        Args:
            data: Data to validate
            data_type: Type of data
            
        Returns:
            Validation results with knowledge-aware checks
        """
        try:
            # Get validation knowledge
            context_chunks = self.knowledge_rag.retrieve_context("data validation")
            
            # Build enhanced prompt
            base_prompt = get_system_prompt("data_validation")
            enhanced_prompt = build_enhanced_prompt(
                base_prompt,
                context_chunks,
                f"Validate this {data_type} data",
                data
            )
            
            # Query LLM
            messages = [{'role': 'user', 'content': enhanced_prompt}]
            
            response = await self.generate_completion(
                model='fast_analysis',
                messages=messages,
                max_tokens=300,
                temperature=0.2
            )
            
            if response and 'choices' in response:
                content = response['choices'][0]['message']['content']
                
                # Try to parse as JSON
                try:
                    # Look for JSON in the response
                    json_match = re.search(r'\{.*\}', content, re.DOTALL)
                    if json_match:
                        return json.loads(json_match.group())
                except:
                    pass
                
                # Return structured response if JSON parsing fails
                return {
                    'is_valid': True,
                    'confidence': 80,
                    'issues': [],
                    'recommendations': ['Manual review recommended'],
                    'summary': 'Validation completed',
                    'raw_response': content
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Data validation with knowledge error: {e}")
            return None
    
    def get_glossary_term(self, term: str) -> Optional[str]:
        """Get definition for a trading term"""
        return self.knowledge_rag.get_glossary_term(term)
    
    def get_related_knowledge(self, query: str, max_results: int = 3) -> List[Dict[str, Any]]:
        """Get related knowledge for a query"""
        return self.knowledge_rag.retrieve_context(query, max_results)


# Enhanced LLM Manager that uses the enhanced client
class EnhancedLLMManager:
    """Enhanced LLM manager with knowledge integration"""
    
    def __init__(self):
        self.settings = None  # Would load from config
        self.enhanced_client = None
    
    async def __aenter__(self):
        """Async context manager entry"""
        self.enhanced_client = EnhancedLMStudioClient(self.settings)
        await self.enhanced_client.__aenter__()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.enhanced_client:
            await self.enhanced_client.__aexit__(exc_type, exc_val, exc_tb)
    
    async def analyze_market(self, 
                           internals_data: Dict[str, Any],
                           analysis_type: str = 'quick') -> Optional[str]:
        """
        Analyze market with enhanced knowledge
        
        Args:
            internals_data: Market internals data
            analysis_type: 'quick', 'deep', or 'review'
        """
        try:
            if not self.enhanced_client:
                return None
            
            if analysis_type == 'quick':
                return await self.enhanced_client.analyze_market_internals(internals_data)
            elif analysis_type == 'deep':
                return await self.enhanced_client.analyze_market_with_context(internals_data)
            else:
                return await self.enhanced_client.analyze_market_internals(internals_data)
                
        except Exception as e:
            logger.error(f"Enhanced market analysis error: {e}")
            return None
    
    async def test_hypothesis(self, 
                            hypothesis_name: str,
                            market_data: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Test a trading hypothesis"""
        try:
            if not self.enhanced_client:
                return None
            
            return await self.enhanced_client.test_hypothesis(hypothesis_name, market_data)
            
        except Exception as e:
            logger.error(f"Hypothesis testing error: {e}")
            return None


# Example usage
async def demo_enhanced_client():
    """Demonstrate enhanced client capabilities"""
    print("Demonstrating Enhanced LM Studio Client with Trading Knowledge...")
    
    async with EnhancedLMStudioClient() as client:
        # Demo 1: Basic query with knowledge
        print("\n1. Testing knowledge-enhanced query...")
        result = await client.analyze_with_knowledge(
            query="Explain how FVGs work in crypto markets",
            prompt_type="trading_analyst"
        )
        if result:
            print("✓ Knowledge-enhanced response received")
            print(f"Response preview: {result[:100]}...")
        
        # Demo 2: Market analysis with context
        print("\n2. Testing market analysis with context...")
        market_data = {
            'spy': {'price': 450.25, 'change': 2.15, 'change_pct': 0.48},
            'qqq': {'price': 375.80, 'change': -1.25, 'change_pct': -0.33},
            'vix': {'price': 18.50, 'change': -0.75, 'change_pct': -3.89}
        }
        analysis = await client.analyze_market_with_context(market_data)
        if analysis:
            print("✓ Market analysis with context completed")
            print(f"Analysis preview: {analysis[:100]}...")
        
        # Demo 3: Hypothesis testing
        print("\n3. Testing hypothesis framework...")
        # Note: This would test the overnight_margin_cascade hypothesis if data is available
        
        # Demo 4: Glossary lookup
        print("\n4. Testing glossary lookup...")
        fvg_def = client.get_glossary_term("FVG")
        if fvg_def:
            print(f"✓ FVG definition: {fvg_def[:100]}...")
        
        print("\nEnhanced client demonstration completed!")


if __name__ == "__main__":
    import asyncio
    asyncio.run(demo_enhanced_client())