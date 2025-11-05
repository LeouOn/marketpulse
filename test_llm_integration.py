#!/usr/bin/env python3
"""
MarketPulse LLM Integration Test Script
Tests LM Studio (Gemma 3) and OpenRouter LLM connectivity
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Add src to path for imports
sys.path.append(str(Path(__file__).parent / "src"))

from src.llm.llm_client import LMStudioClient, OpenRouterClient, LLMManager
from src.core.config import get_settings


async def test_lm_studio_connection():
    """Test LM Studio connection and basic functionality"""
    print("🔌 Testing LM Studio connection (Gemma 3)...")
    
    try:
        settings = get_settings()
        base_url = settings.llm.primary.base_url
        timeout = settings.llm.primary.timeout
        
        print(f"📡 Connecting to: {base_url}")
        print(f"⏱️  Timeout: {timeout}s")
        
        async with LMStudioClient(settings) as client:
            # Test basic completion
            messages = [
                {'role': 'user', 'content': 'Hello, respond with just "Connection test successful" if you can hear me.'}
            ]
            
            print("🧪 Testing basic completion...")
            result = await client.generate_completion(
                model='fast',
                messages=messages,
                max_tokens=10,
                temperature=0.1
            )
            
            if result and 'choices' in result:
                response = result['choices'][0]['message']['content']
                print(f"✅ LM Studio responded: {response}")
                return True
            else:
                print("❌ No response from LM Studio")
                return False
                
    except Exception as e:
        print(f"❌ LM Studio connection failed: {e}")
        print("💡 Make sure LM Studio is running and Gemma 3 model is loaded")
        return False


async def test_market_analysis():
    """Test market analysis with LM Studio"""
    print("\n📊 Testing market analysis capabilities...")
    
    try:
        settings = get_settings()
        
        # Sample market data for testing
        sample_internals = {
            'spy': {'price': 450.25, 'change': 2.15, 'change_pct': 0.48, 'volume': 45000000},
            'qqq': {'price': 375.80, 'change': -1.25, 'change_pct': -0.33, 'volume': 32000000},
            'vix': {'price': 18.50, 'change': -0.75, 'change_pct': -3.89},
            'volume_flow': {'total_volume_60min': 77000000, 'symbols_tracked': 3}
        }
        
        async with LMStudioClient(settings) as client:
            print("🔍 Testing quick market analysis...")
            analysis = await client.analyze_market_internals(sample_internals)
            
            if analysis:
                print("✅ Market analysis successful!")
                print("🤖 Analysis Result:")
                print("-" * 60)
                print(analysis)
                print("-" * 60)
                return True
            else:
                print("❌ Market analysis failed")
                return False
                
    except Exception as e:
        print(f"❌ Market analysis test failed: {e}")
        return False


async def test_model_performance():
    """Test different model types for performance comparison"""
    print("\n⚡ Testing model performance (Speed Test)...")
    
    try:
        settings = get_settings()
        models_to_test = ['fast', 'analyst', 'reviewer']
        
        async with LMStudioClient(settings) as client:
            test_message = [
                {'role': 'user', 'content': 'Briefly explain what market volatility means in one sentence.'}
            ]
            
            results = {}
            
            for model_type in models_to_test:
                print(f"🧪 Testing {model_type} model...")
                start_time = time.time()
                
                result = await client.generate_completion(
                    model=model_type,
                    messages=test_message,
                    max_tokens=50,
                    temperature=0.3
                )
                
                end_time = time.time()
                duration = end_time - start_time
                
                if result and 'choices' in result:
                    response = result['choices'][0]['message']['content']
                    results[model_type] = {
                        'success': True,
                        'duration': f"{duration:.2f}s",
                        'response': response,
                        'status': '✅ PASS'
                    }
                    print(f"✅ {model_type}: {duration:.2f}s - {response[:50]}...")
                else:
                    results[model_type] = {
                        'success': False,
                        'duration': f"{duration:.2f}s",
                        'status': '❌ FAIL'
                    }
                    print(f"❌ {model_type}: Failed ({duration:.2f}s)")
            
            # Check if at least fast model works
            return results.get('fast', {}).get('success', False)
            
    except Exception as e:
        print(f"❌ Model performance test failed: {e}")
        return False


async def test_openrouter_fallback():
    """Test OpenRouter fallback functionality"""
    print("\n☁️  Testing OpenRouter fallback...")
    
    try:
        settings = get_settings()
        
        # Check if OpenRouter API key is configured
        if (settings.llm.fallback.api_key == "your_openrouter_api_key" or 
            not settings.llm.fallback.api_key):
            print("⚠️  OpenRouter API key not configured - skipping fallback test")
            return True  # Not a failure if not configured
        
        async with OpenRouterClient(settings) as client:
            messages = [
                {'role': 'user', 'content': 'Respond with "OpenRouter fallback working"'}
            ]
            
            result = await client.generate_completion(
                model="openai/gpt-4o-mini",
                messages=messages,
                max_tokens=20,
                temperature=0.1
            )
            
            if result and 'choices' in result:
                response = result['choices'][0]['message']['content']
                print(f"✅ OpenRouter fallback working: {response}")
                return True
            else:
                print("❌ OpenRouter fallback failed")
                return False
                
    except Exception as e:
        print(f"❌ OpenRouter fallback test failed: {e}")
        return False


async def test_llm_manager():
    """Test the LLM Manager orchestrator"""
    print("\n🎯 Testing LLM Manager orchestrator...")
    
    try:
        llm_manager = LLMManager()
        
        # Test status check
        status = llm_manager.get_status()
        print("📋 LLM Services Status:")
        print(json.dumps(status, indent=2))
        
        # Test market analysis through manager
        sample_data = {
            'spy': {'price': 450.25, 'change': 2.15},
            'qqq': {'price': 375.80, 'change': -1.25},
            'vix': {'price': 18.50, 'change': -0.75}
        }
        
        print("\n🧪 Testing manager market analysis...")
        analysis = await llm_manager.analyze_market(sample_data, 'quick')
        
        if analysis:
            print("✅ LLM Manager analysis successful!")
            print(f"🤖 Result: {analysis[:100]}...")
            return True
        else:
            print("❌ LLM Manager analysis failed")
            return False
            
    except Exception as e:
        print(f"❌ LLM Manager test failed: {e}")
        return False


async def run_comprehensive_llm_test():
    """Run all LLM integration tests"""
    print("=" * 80)
    print("🚀 MARKETPULSE LLM INTEGRATION TESTS")
    print("=" * 80)
    
    # Test results
    results = {
        'lm_studio_connection': False,
        'market_analysis': False,
        'model_performance': False,
        'openrouter_fallback': False,
        'llm_manager': False
    }
    
    # Run tests
    results['lm_studio_connection'] = await test_lm_studio_connection()
    results['market_analysis'] = await test_market_analysis()
    results['model_performance'] = await test_model_performance()
    results['openrouter_fallback'] = await test_openrouter_fallback()
    results['llm_manager'] = await test_llm_manager()
    
    # Summary
    print("\n" + "=" * 80)
    print("📋 LLM TEST RESULTS SUMMARY")
    print("=" * 80)
    
    passed = sum(results.values())
    total = len(results)
    
    for test_name, passed_test in results.items():
        status = "✅ PASS" if passed_test else "❌ FAIL"
        print(f"{test_name.replace('_', ' ').title()}: {status}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All LLM tests passed! Gemma 3 integration is working correctly.")
    elif results['lm_studio_connection']:
        print("✅ LM Studio connection working - core functionality operational.")
        print("⚠️  Some advanced features may need configuration.")
    else:
        print("⚠️  LM Studio connection failed. Check if it's running with Gemma 3 loaded.")
    
    # Save results
    with open('llm_test_results.json', 'w') as f:
        json.dump({
            'timestamp': time.time(),
            'results': results,
            'summary': {
                'passed': passed,
                'total': total,
                'success_rate': f"{(passed/total)*100:.1f}%"
            }
        }, f, indent=2)
    
    return passed == total


if __name__ == "__main__":
    # Ensure we're in the right directory
    os.chdir(Path(__file__).parent)
    
    # Run the tests
    success = asyncio.run(run_comprehensive_llm_test())
    sys.exit(0 if success else 1)