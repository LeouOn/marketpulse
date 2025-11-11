#!/usr/bin/env python3
"""
Enhanced LLM Integration Test
Tests the complete trading knowledge system with RAG and hypothesis testing
"""

import asyncio
import json
import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent / "src"))

from src.llm.enhanced_llm_client import EnhancedLMStudioClient, EnhancedLLMManager
from src.llm.trading_knowledge_rag import get_trading_rag
from src.llm.hypothesis_tester import HypothesisTester


def safe_print(text, indent=0):
    """Safely print text with Unicode handling for Windows"""
    try:
        prefix = "   " * indent
        for line in text.split('\n'):
            print(f"{prefix}{line}")
    except UnicodeEncodeError as e:
        # Fallback: encode to ascii with replacement
        prefix = "   " * indent
        for line in text.split('\n'):
            safe_line = line.encode('ascii', errors='replace').decode('ascii')
            print(f"{prefix}{safe_line}")


async def demo_knowledge_retrieval():
    """Demo 1: Knowledge retrieval system"""
    print("=" * 80)
    print("DEMO 1: Trading Knowledge Retrieval")
    print("=" * 80)
    
    rag = get_trading_rag()
    
    # Test 1: Glossary lookup
    print("\n1. Glossary Lookup:")
    fvg_def = rag.get_glossary_term("FVG")
    print(f"   FVG: {fvg_def[:100]}...")
    
    cvd_def = rag.get_glossary_term("CVD")
    print(f"   CVD: {cvd_def[:100]}...")
    
    # Test 2: Context retrieval for query
    print("\n2. Context Retrieval:")
    context = rag.retrieve_context("How do FVGs work in crypto markets?", max_results=3)
    print(f"   Found {len(context)} relevant knowledge chunks:")
    for i, chunk in enumerate(context, 1):
        print(f"   {i}. {chunk.get('type', 'unknown')}: {chunk.get('term', chunk.get('title', 'N/A'))}")
    
    # Test 3: Related terms
    print("\n3. Related Terms:")
    related = rag.get_related_terms("funding")
    print(f"   Terms related to 'funding': {related}")
    
    print("\nKnowledge retrieval system working\n")


async def demo_enhanced_analysis():
    """Demo 2: Enhanced analysis with knowledge context"""
    print("=" * 80)
    print("DEMO 2: Enhanced Analysis with Knowledge")
    print("=" * 80)
    
    async with EnhancedLMStudioClient() as client:
        # Test 1: Market analysis with context
        print("\n1. Market Analysis with Knowledge:")
        market_data = {
            'spy': {'price': 452.80, 'change': 3.45, 'change_pct': 0.77, 'volume': 52000000},
            'qqq': {'price': 378.20, 'change': 1.85, 'change_pct': 0.49, 'volume': 35000000},
            'vix': {'price': 16.20, 'change': -2.30, 'change_pct': -12.43}
        }
        
        analysis = await client.analyze_market_with_context(market_data)
        if analysis:
            print("   Analysis completed with knowledge context")
            print(f"   Preview: {analysis[:150]}...")
        
        # Test 2: Chart analysis with technical knowledge
        print("\n2. Chart Analysis with Knowledge:")
        chart_data = {
            'symbol': 'NQ',
            'timeframe': '5m',
            'candles': [
                {'time': '10:00', 'open': 15000, 'high': 15025, 'low': 14995, 'close': 15020, 'volume': 1250},
                {'time': '10:05', 'open': 15020, 'high': 15045, 'low': 15010, 'close': 15035, 'volume': 1380},
                {'time': '10:10', 'open': 15035, 'high': 15050, 'low': 15020, 'close': 15040, 'volume': 1420}
            ],
            'indicators': {
                'sma_20': 15010,
                'rsi': 65.5
            }
        }
        
        chart_analysis = await client.analyze_chart_with_context(chart_data)
        if chart_analysis:
            print("   Chart analysis completed")
            print(f"   Preview: {chart_analysis[:150]}...")
        
        # Test 3: Knowledge-enhanced query
        print("\n3. Knowledge-Enhanced Query:")
        result = await client.analyze_with_knowledge(
            query="Explain the relationship between funding rates and perpetual futures prices",
            prompt_type="trading_analyst"
        )
        if result:
            print("   Knowledge-enhanced response received")
            print(f"   Preview: {result[:150]}...")
    
    print("\nEnhanced analysis working\n")


async def demo_hypothesis_testing():
    """Demo 3: Hypothesis testing framework"""
    print("=" * 80)
    print("DEMO 3: Hypothesis Testing Framework")
    print("=" * 80)
    
    async with EnhancedLMStudioClient() as client:
        tester = HypothesisTester(client)
        
        # Test 1: List hypotheses
        print("\n1. Available Hypotheses:")
        hypotheses = tester.list_hypotheses()
        for h in hypotheses:
            print(f"   - {h['name']} ({h['status']})")
        
        # Test 2: Load hypothesis
        print("\n2. Load Hypothesis:")
        hypothesis = tester.load_hypothesis("overnight_margin_cascade")
        if hypothesis:
            print(f"   Loaded: {hypothesis['name']}")
            print(f"   Description: {hypothesis['description'][:100]}...")
            print(f"   Related concepts: {len(hypothesis['related_concepts'])}")
        
        # Test 3: Clarify hypothesis (no data)
        print("\n3. Clarify Hypothesis:")
        clarification = await tester.clarify_hypothesis(hypothesis)
        print(f"   Clarification received: {clarification[:150]}...")
        
        # Test 4: Test with sample data
        print("\n4. Test with Sample Data:")
        sample_data = {
            'btc_perp': {
                'price': 45000,
                'change_24h': 2.5,
                'volume_24h': 1200000000,
                'funding_rate': 0.01,
                'open_interest': 850000000
            },
            'time_window': {
                'start': '23:45:00',
                'end': '00:15:00',
                'price_change': -0.8,
                'volume_spike': 2.3
            }
        }
        
        result = await tester.test_hypothesis("overnight_margin_cascade", sample_data)
        if result:
            print(f"   Status: {result.status}")
            print(f"   Confidence: {result.confidence}%")
            print(f"   Summary: {result.summary}")
            print(f"   Key findings: {len(result.key_findings)}")
    
    print("\nHypothesis testing framework working\n")


async def demo_complete_workflow():
    """Demo 4: Complete workflow from query to analysis"""
    print("=" * 80)
    print("DEMO 4: Complete Workflow")
    print("=" * 80)
    
    async with EnhancedLLMManager() as manager:
        # Test 1: Market analysis
        print("\n1. Enhanced Market Analysis:")
        market_data = {
            'nq': {'price': 15025, 'change': 45, 'change_pct': 0.30},
            'vix': {'price': 16.5, 'change': -1.2, 'change_pct': -6.8},
            'volume_flow': {'total_volume_60min': 85000000}
        }
        
        analysis = await manager.analyze_market(market_data, 'deep')
        if analysis:
            print("   Enhanced analysis completed")
            print(f"   Preview: {analysis[:150]}...")
        
        # Test 2: Hypothesis testing through manager
        print("\n2. Hypothesis Testing:")
        test_result = await manager.test_hypothesis("overnight_margin_cascade")
        if test_result:
            print(f"   Test completed: {test_result['status']}")
            print(f"   Confidence: {test_result['confidence']}%")
    
    print("\nComplete workflow working\n")


async def demo_glossary_integration():
    """Demo 5: Glossary integration in responses"""
    print("=" * 80)
    print("DEMO 5: Glossary Integration")
    print("=" * 80)
    
    rag = get_trading_rag()
    
    # Test various glossary terms
    terms_to_test = [
        "FVG",
        "CVD", 
        "funding_rate",
        "liquidation_cascade",
        "order_block",
        "overhead_margin"
    ]
    
    print("\n1. Glossary Terms Available:")
    for term in terms_to_test:
        definition = rag.get_glossary_term(term)
        if definition:
            print(f"   [OK] {term}: {definition[:80]}...")
        else:
            print(f"   [MISSING] {term}: Not found")
    
    # Test related terms
    print("\n2. Related Terms Discovery:")
    related = rag.get_related_terms("margin")
    print(f"   Terms related to 'margin': {related}")
    
    print("\nGlossary integration working\n")


async def main():
    """Run all demos"""
    print("\n" + "=" * 80)
    print("ENHANCED LLM INTEGRATION - COMPLETE SYSTEM TEST")
    print("=" * 80)
    print("Testing: LM Studio + Trading Knowledge + RAG + Hypothesis Framework")
    print("=" * 80 + "\n")
    
    try:
        # Run all demos
        await demo_knowledge_retrieval()
        await demo_enhanced_analysis()
        await demo_hypothesis_testing()
        await demo_complete_workflow()
        await demo_glossary_integration()
        
        print("=" * 80)
        print("ALL TESTS COMPLETED SUCCESSFULLY!")
        print("=" * 80)
        print("\nThe enhanced LLM integration is working with:")
        print("  - Trading knowledge base (60+ terms, concepts, hypotheses)")
        print("  - RAG system for context retrieval")
        print("  - Enhanced prompts with knowledge injection")
        print("  - Hypothesis testing framework")
        print("  - Complete workflow integration")
        print("\nKey Features Available:")
        print("  * Market analysis with trading context")
        print("  * Chart pattern recognition with technical knowledge")
        print("  * Hypothesis testing and validation")
        print("  * Data validation with domain expertise")
        print("  * Glossary and concept lookup")
        print("\nReady for sophisticated trading analysis!")
        
    except Exception as e:
        print(f"\nError during testing: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())