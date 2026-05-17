"""Quick test script for MarketPulse endpoints"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger

async def test_endpoints():
    """Test MarketPulse endpoints"""
    import aiohttp

    base_url = "http://127.0.0.1:8000"

    async with aiohttp.ClientSession() as session:
        # Test 1: Health check
        print("\n=== Test 1: Health Check ===")
        try:
            async with session.get(f"{base_url}/") as resp:
                print(f"Status: {resp.status}")
                data = await resp.json()
                print(f"Response: {data}")
        except Exception as e:
            print(f"Error: {e}")

        # Test 2: LLM Model Status
        print("\n=== Test 2: LM Studio Model Status ===")
        try:
            async with session.get(f"{base_url}/api/llm/model-status") as resp:
                print(f"Status: {resp.status}")
                data = await resp.json()
                print(f"Response: {data}")
        except Exception as e:
            print(f"Error: {e}")

        # Test 3: Available Models
        print("\n=== Test 3: Available Models ===")
        try:
            async with session.get(f"{base_url}/api/llm/models") as resp:
                print(f"Status: {resp.status}")
                data = await resp.json()
                print(f"Response: {data}")
        except Exception as e:
            print(f"Error: {e}")

        # Test 4: Yahoo Finance Test
        print("\n=== Test 4: Yahoo Finance Test ===")
        try:
            async with session.put(f"{base_url}/api/test/yahoo-finance") as resp:
                print(f"Status: {resp.status}")
                data = await resp.json()
                print(f"Data source: {data.get('data_source', 'unknown')}")
                print(f"Success: {data.get('success')}")
        except Exception as e:
            print(f"Error: {e}")

        # Test 5: Market Internals
        print("\n=== Test 5: Market Internals ===")
        try:
            async with session.get(f"{base_url}/api/market/internals") as resp:
                print(f"Status: {resp.status}")
                data = await resp.json()
                print(f"Success: {data.get('success')}")
                if data.get('data'):
                    symbols = list(data['data'].keys())[:5]
                    print(f"Symbols: {symbols}")
        except Exception as e:
            print(f"Error: {e}")

        # Test 6: LLM Chat
        print("\n=== Test 6: LLM Chat ===")
        try:
            payload = {
                "message": "What is the current market trend for SPY?",
                "symbol": "SPY"
            }
            async with session.post(f"{base_url}/api/llm/chat", json=payload) as resp:
                print(f"Status: {resp.status}")
                data = await resp.json()
                print(f"Success: {data.get('success')}")
                if data.get('data', {}).get('response'):
                    print(f"Response: {data['data']['response'][:200]}...")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_endpoints())