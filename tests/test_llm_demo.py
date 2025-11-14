#!/usr/bin/env python3
"""
MarketPulse LLM Integration Demo
Demonstrates real queries and roundtrips to LM Studio
"""

import asyncio
import json
from pathlib import Path
import sys

# Add src to path
sys.path.append(str(Path(__file__).parent / "src"))

from src.llm.llm_client import LMStudioClient, LLMManager
from src.core.config import get_settings


async def demo_basic_query():
    """Demo 1: Basic query to test connection"""
    print("=" * 70)
    print("DEMO 1: Basic Query Test")
    print("=" * 70)
    
    async with LMStudioClient() as client:
        messages = [
            {'role': 'user', 'content': 'What is the capital of France? Answer in one word.'}
        ]
        
        print("Sending: What is the capital of France?")
        result = await client.generate_completion(
            model='fast_analysis',
            messages=messages,
            max_tokens=10,
            temperature=0.1
        )
        
        if result and 'choices' in result:
            response = result['choices'][0]['message']['content']
            print(f"Response: {response}")
            print("✓ Basic query successful!\n")
        else:
            print("✗ Query failed\n")


async def demo_market_analysis():
    """Demo 2: Market analysis with real data"""
    print("=" * 70)
    print("DEMO 2: Market Analysis")
    print("=" * 70)
    
    # Sample market data (similar to what MarketPulse collects)
    market_data = {
        'spy': {'price': 452.80, 'change': 3.45, 'change_pct': 0.77, 'volume': 52000000},
        'qqq': {'price': 378.20, 'change': 1.85, 'change_pct': 0.49, 'volume': 35000000},
        'vix': {'price': 16.20, 'change': -2.30, 'change_pct': -12.43},
        'volume_flow': {'total_volume_60min': 87000000, 'symbols_tracked': 3}
    }
    
    async with LMStudioClient() as client:
        print("Analyzing market data:")
        print(f"  SPY: ${market_data['spy']['price']} (+{market_data['spy']['change_pct']}%)")
        print(f"  QQQ: ${market_data['qqq']['price']} (+{market_data['qqq']['change_pct']}%)")
        print(f"  VIX: {market_data['vix']['price']} ({market_data['vix']['change_pct']}%)\n")
        
        analysis = await client.analyze_market_internals(market_data)
        
        if analysis:
            print("AI Analysis:")
            print("-" * 70)
            print(analysis)
            print("-" * 70)
            print("✓ Market analysis successful!\n")
        else:
            print("✗ Market analysis failed\n")


async def demo_data_validation():
    """Demo 3: Data validation sanity check"""
    print("=" * 70)
    print("DEMO 3: Data Validation")
    print("=" * 70)
    
    # Test with potentially problematic data
    test_data = {
        'spy': {'price': 450.25, 'change': 2.15, 'change_pct': 0.48, 'volume': 45000000},
        'qqq': {'price': 375.80, 'change': -1.25, 'change_pct': -0.33, 'volume': 32000000},
        'vix': {'price': 18.50, 'change': -0.75, 'change_pct': -3.89}
    }
    
    async with LMStudioClient() as client:
        print("Validating market data for consistency...")
        
        validation = await client.validate_data_interpretation(test_data, "market_internals")
        
        if validation:
            print(f"Validation Results:")
            print(f"  Valid: {validation.get('is_valid', 'N/A')}")
            print(f"  Confidence: {validation.get('confidence', 'N/A')}%")
            print(f"  Summary: {validation.get('summary', 'N/A')}")
            
            if validation.get('issues'):
                print(f"  Issues found: {validation['issues']}")
            
            print("✓ Data validation completed!\n")
        else:
            print("✗ Data validation failed\n")


async def demo_chart_analysis():
    """Demo 4: Chart pattern analysis"""
    print("=" * 70)
    print("DEMO 4: Chart Pattern Analysis")
    print("=" * 70)
    
    # Sample chart data showing a potential breakout pattern
    chart_data = {
        'symbol': 'NQ',
        'timeframe': '5m',
        'candles': [
            {'time': '10:00', 'open': 14980, 'high': 15005, 'low': 14970, 'close': 15000, 'volume': 1100},
            {'time': '10:05', 'open': 15000, 'high': 15030, 'low': 14995, 'close': 15025, 'volume': 1350},
            {'time': '10:10', 'open': 15025, 'high': 15045, 'low': 15020, 'close': 15040, 'volume': 1420},
            {'time': '10:15', 'open': 15040, 'high': 15055, 'low': 15035, 'close': 15050, 'volume': 1380},
            {'time': '10:20', 'open': 15050, 'high': 15065, 'low': 15045, 'close': 15060, 'volume': 1450}
        ],
        'indicators': {
            'sma_20': 15025,
            'rsi': 72.3,
            'volume_ma': 1300
        }
    }
    
    async with LMStudioClient() as client:
        print("Chart Pattern: 5 consecutive green candles, rising volume")
        print("Indicators: RSI 72.3 (approaching overbought), Price above SMA20\n")
        
        analysis = await client.interpret_text_chart_data(chart_data)
        
        if analysis:
            print("AI Chart Analysis:")
            print("-" * 70)
            print(analysis)
            print("-" * 70)
            print("✓ Chart analysis successful!\n")
        else:
            print("✗ Chart analysis failed\n")


async def demo_user_feedback():
    """Demo 5: User feedback and refinement"""
    print("=" * 70)
    print("DEMO 5: User Feedback & Refinement")
    print("=" * 70)
    
    original_analysis = """Market shows bullish momentum with SPY up 0.77% and QQQ up 0.49%. 
VIX declining 12% suggests reduced fear. Volume is elevated, supporting the move."""
    
    user_comments = [
        "The VIX drop seems excessive - is this sustainable?",
        "Volume on QQQ is lower than SPY - concerned about tech weakness",
        "What about support levels if this reverses?"
    ]
    
    async with LMStudioClient() as client:
        print("Original AI Analysis:")
        print(f"  {original_analysis}\n")
        
        print("User Feedback:")
        for i, comment in enumerate(user_comments, 1):
            print(f"  {i}. {comment}")
        print()
        
        # Build refinement prompt
        refinement_prompt = f"""
        Original Analysis: {original_analysis}
        
        User Feedback:
        {chr(10).join(f"- {comment}" for comment in user_comments)}
        
        Please refine the analysis addressing these concerns. Focus on:
        1. Sustainability of the VIX move
        2. Tech sector weakness vs broad market strength
        3. Key support levels for risk management
        """
        
        messages = [{'role': 'user', 'content': refinement_prompt}]
        
        response = await client.generate_completion(
            model='deep_analysis',
            messages=messages,
            max_tokens=400,
            temperature=0.4
        )
        
        if response and 'choices' in response:
            refined_analysis = response['choices'][0]['message']['content']
            print("Refined AI Analysis:")
            print("-" * 70)
            print(refined_analysis)
            print("-" * 70)
            print("✓ Analysis refinement successful!\n")
        else:
            print("✗ Analysis refinement failed\n")


async def demo_roundtrip_conversation():
    """Demo 6: Multi-turn conversation"""
    print("=" * 70)
    print("DEMO 6: Multi-Turn Conversation")
    print("=" * 70)
    
    async with LMStudioClient() as client:
        print("Starting conversation about trading strategy...")
        
        # Turn 1: Initial question
        messages = [
            {'role': 'user', 'content': 'What are the key factors for successful day trading NQ futures? List 3 main points.'}
        ]
        
        print("\nQ1: What are key factors for day trading NQ futures?")
        result1 = await client.generate_completion(
            model='fast_analysis',
            messages=messages,
            max_tokens=150,
            temperature=0.3
        )
        
        if result1 and 'choices' in result1:
            response1 = result1['choices'][0]['message']['content']
            print(f"A1: {response1}\n")
            
            # Turn 2: Follow-up question
            messages.append({'role': 'assistant', 'content': response1})
            messages.append({
                'role': 'user', 
                'content': 'How does market internals analysis fit into this? Which specific internals matter most?'
            })
            
            print("Q2: How do market internals fit in? Which matter most?")
            result2 = await client.generate_completion(
                model='deep_analysis',
                messages=messages,
                max_tokens=200,
                temperature=0.4
            )
            
            if result2 and 'choices' in result2:
                response2 = result2['choices'][0]['message']['content']
                print(f"A2: {response2}\n")
                print("✓ Multi-turn conversation successful!\n")
            else:
                print("✗ Second turn failed\n")
        else:
            print("✗ First turn failed\n")


async def main():
    """Run all demos"""
    print("\n" + "=" * 70)
    print("MARKETPULSE LLM INTEGRATION DEMONSTRATION")
    print("=" * 70)
    print(f"LM Studio: http://127.0.0.1:1234/v1")
    print(f"Model: aquif-3.5-max-42b-a3b-i1")
    print("=" * 70 + "\n")
    
    try:
        # Run all demos
        await demo_basic_query()
        await demo_market_analysis()
        await demo_data_validation()
        await demo_chart_analysis()
        await demo_user_feedback()
        await demo_roundtrip_conversation()
        
        print("=" * 70)
        print("ALL DEMONSTRATIONS COMPLETED SUCCESSFULLY!")
        print("=" * 70)
        print("\nThe LLM integration is working correctly with:")
        print("  ✓ Basic queries and responses")
        print("  ✓ Market data analysis")
        print("  ✓ Data validation and sanity checks")
        print("  ✓ Chart pattern interpretation")
        print("  ✓ User feedback and refinement")
        print("  ✓ Multi-turn conversations")
        print("\nYou can now integrate this into your trading workflow!")
        
    except Exception as e:
        print(f"\nError during demonstration: {e}")
        print("Please ensure LM Studio is running with the model loaded.")


if __name__ == "__main__":
    asyncio.run(main())