"""HTTP endpoint tests for MarketPulse"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def test_endpoints():
    """Test HTTP endpoints against running server"""
    import aiohttp

    base_url = "http://127.0.0.1:8000"

    async with aiohttp.ClientSession() as session:
        # Test 1: Health check
        print("\n=== Test 1: Health Check (GET /) ===")
        try:
            async with session.get(f"{base_url}/") as resp:
                print(f"Status: {resp.status}")
                data = await resp.json()
                print(f"Message: {data.get('message', 'N/A')}")
        except Exception as e:
            print(f"Error: {e}")

        # Test 2: LLM Model Status
        print("\n=== Test 2: LM Studio Model Status (GET /api/llm/model-status) ===")
        try:
            async with session.get(f"{base_url}/api/llm/model-status") as resp:
                print(f"Status: {resp.status}")
                data = await resp.json()
                if data.get("success"):
                    d = data.get("data", {})
                    print(f"LM Studio connected: {d.get('lm_studio_connected')}")
                    print(f"Active model: {d.get('active_model')}")
                    print(f"Loaded models: {d.get('loaded_models', [])[:3]}...")
                else:
                    print(f"Error: {data.get('error')}")
        except Exception as e:
            print(f"Error: {e}")

        # Test 3: Available Models
        print("\n=== Test 3: Available Models (GET /api/llm/models) ===")
        try:
            async with session.get(f"{base_url}/api/llm/models") as resp:
                print(f"Status: {resp.status}")
                data = await resp.json()
                if data.get("success"):
                    d = data.get("data", {})
                    print(f"Provider: {d.get('provider')}")
                    print(f"Total models: {d.get('total_count', 0)}")
                    models = d.get("models", [])
                    for m in models[:3]:
                        print(f"  - {m.get('id')} ({m.get('size')})")
                else:
                    print(f"Error: {data.get('error')}")
        except Exception as e:
            print(f"Error: {e}")

        # Test 4: Yahoo Finance Test
        print("\n=== Test 4: Yahoo Finance Test (PUT /api/test/yahoo-finance) ===")
        try:
            async with session.put(f"{base_url}/api/test/yahoo-finance") as resp:
                print(f"Status: {resp.status}")
                data = await resp.json()
                print(f"Success: {data.get('success')}")
                print(f"Data source: {data.get('data_source', 'unknown')}")
                results = data.get("yahoo_finance_results", {})
                for sym, info in list(results.items())[:3]:
                    if info.get("success"):
                        print(f"  {sym}: ${info.get('price')} ({info.get('change_pct', 0):+.2f}%)")
        except Exception as e:
            print(f"Error: {e}")

        # Test 5: Market Internals
        print("\n=== Test 5: Market Internals (GET /api/market/internals) ===")
        try:
            async with session.get(f"{base_url}/api/market/internals") as resp:
                print(f"Status: {resp.status}")
                data = await resp.json()
                print(f"Success: {data.get('success')}")
                if data.get("success") and data.get("data"):
                    d = data.get("data", {})
                    print(f"Data source: {d.get('data_source', 'unknown')}")
                    symbols = [k for k in d.keys() if k not in ["data_source", "timestamp", "volume_flow"]]
                    print(f"Symbols: {symbols[:6]}")
        except Exception as e:
            print(f"Error: {e}")

        # Test 6: Test Status
        print("\n=== Test 6: Test Status (GET /api/test/status) ===")
        try:
            async with session.get(f"{base_url}/api/test/status") as resp:
                print(f"Status: {resp.status}")
                data = await resp.json()
                print(f"Collector status: {data.get('collector_status')}")
                print(f"OHLC analyzer status: {data.get('ohlc_analyzer_status')}")
        except Exception as e:
            print(f"Error: {e}")

        # Test 7: LLM Chat
        print("\n=== Test 7: LLM Chat (POST /api/llm/chat) ===")
        try:
            payload = {
                "message": "Hello, what is the current trend for SPY?",
                "symbol": "SPY",
                "context": {"query_type": "trend_analysis"},
            }
            async with session.post(f"{base_url}/api/llm/chat", json=payload) as resp:
                print(f"Status: {resp.status}")
                data = await resp.json()
                print(f"Success: {data.get('success')}")
                if data.get("success") and data.get("data", {}).get("response"):
                    resp_text = data["data"]["response"]
                    print(f"Response (first 200 chars): {resp_text[:200]}...")
                else:
                    print(f"Error: {data.get('error', 'No response')}")
        except Exception as e:
            print(f"Error: {e}")

        print("\n=== All Tests Complete ===")


if __name__ == "__main__":
    print("MarketPulse HTTP Endpoint Tests")
    print("=" * 50)
    asyncio.run(test_endpoints())
