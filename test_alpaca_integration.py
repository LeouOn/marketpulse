#!/usr/bin/env python3
"""
MarketPulse Alpaca Integration Test Script
Tests Alpaca API connectivity and data retrieval capabilities
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path for imports
sys.path.append(str(Path(__file__).parent / "src"))

from src.api.alpaca_client import AlpacaClient
from src.core.config import get_settings


async def test_alpaca_connection():
    """Test basic Alpaca API connectivity"""
    print("Testing Alpaca API connection...")
    
    try:
        settings = get_settings()
        
        # Check if we have valid credentials
        if (settings.api_keys.alpaca.key_id == "your_alpaca_key_here" or 
            settings.api_keys.alpaca.secret_key == "your_alpaca_secret_here"):
            print("Alpaca credentials not configured. Please update credentials.yaml or .env")
            return False
            
        async with AlpacaClient(settings) as client:
            # Test a simple API call - get account info via bars endpoint
            print("Testing API endpoint access...")
            
            # Try to get 1 minute bars for SPY (should always have data)
            bars = await client.get_bars("SPY", "1Min", 5)
            
            if bars is not None and not bars.empty:
                print(f"Successfully retrieved {len(bars)} bars for SPY")
                print(f"Latest SPY price: ${bars['close'].iloc[-1]:.2f}")
                return True
            else:
                print("Failed to retrieve market data")
                return False
                
    except Exception as e:
        print(f"Alpaca connection test failed: {e}")
        return False


async def test_market_internals():
    """Test market internals collection"""
    print("\nTesting market internals collection...")
    
    try:
        settings = get_settings()
        
        if (settings.api_keys.alpaca.key_id == "your_alpaca_key_here" or 
            settings.api_keys.alpaca.secret_key == "your_alpaca_secret_here"):
            print("Alpaca credentials not configured")
            return False
            
        async with AlpacaClient(settings) as client:
            # Get market internals
            internals = await client.get_market_internals()
            
            if internals:
                print("Market internals collected successfully!")
                print(client.format_internals_for_display(internals))
                return True
            else:
                print("Failed to collect market internals")
                return False
                
    except Exception as e:
        print(f"Market internals test failed: {e}")
        return False


async def test_multiple_symbols():
    """Test data collection for multiple symbols"""
    print("\nTesting multiple symbol data collection...")
    
    try:
        settings = get_settings()
        
        if (settings.api_keys.alpaca.key_id == "your_alpaca_key_here" or 
            settings.api_keys.alpaca.secret_key == "your_alpaca_secret_here"):
            print("Alpaca credentials not configured")
            return False
            
        # Test symbols for market internals
        test_symbols = ['SPY', 'QQQ', 'VIX']
        
        async with AlpacaClient(settings) as client:
            # Get multiple timeframes
            for timeframe in ['1Min', '5Min']:
                print(f"\nTesting {timeframe} timeframe...")
                
                data = await client.get_multiple_bars(test_symbols, timeframe, 10)
                
                if data:
                    print(f"Retrieved data for {len(data)} symbols:")
                    for symbol, df in data.items():
                        if not df.empty:
                            latest = df.iloc[-1]
                            print(f"   {symbol}: ${latest['close']:.2f} (Volume: {latest['volume']:,})")
                else:
                    print(f"No data retrieved for {timeframe}")
                    return False
                    
        return True
        
    except Exception as e:
        print(f"Multiple symbols test failed: {e}")
        return False


async def run_comprehensive_alpaca_test():
    """Run all Alpaca integration tests"""
    print("=" * 80)
    print("MARKETPULSE ALPACA INTEGRATION TESTS")
    print("=" * 80)
    
    # Test results
    results = {
        'connection': False,
        'internals': False,
        'multiple_symbols': False
    }
    
    # Run tests
    results['connection'] = await test_alpaca_connection()
    results['internals'] = await test_market_internals()
    results['multiple_symbols'] = await test_multiple_symbols()
    
    # Summary
    print("\n" + "=" * 80)
    print("ALPACA TEST RESULTS SUMMARY")
    print("=" * 80)
    
    passed = sum(results.values())
    total = len(results)
    
    for test_name, passed_test in results.items():
        status = "PASS" if passed_test else "FAIL"
        print(f"{test_name.replace('_', ' ').title()}: {status}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("All Alpaca tests passed! Integration is working correctly.")
    else:
        print("Some tests failed. Please check configuration and API credentials.")
    
    # Save results
    with open('alpaca_test_results.json', 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
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
    success = asyncio.run(run_comprehensive_alpaca_test())
    sys.exit(0 if success else 1)