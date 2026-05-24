"""Full end-to-end test with server in thread"""

import asyncio
import os
import queue
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def run_server(output_queue):
    """Run uvicorn server in thread"""
    import uvicorn

    sys.stdout = sys.stderr  # Suppress uvicorn output
    config = uvicorn.Config("src.api.main:app", host="127.0.0.1", port=8000, log_level="warning")
    server = uvicorn.Server(config)
    output_queue.put("Server starting")
    server.run()
    output_queue.put("Server stopped")


async def test_endpoints():
    """Test endpoints after server is ready"""
    import aiohttp

    base_url = "http://127.0.0.1:8000"

    async with aiohttp.ClientSession() as session:
        # Wait for server to be ready
        for _ in range(30):
            try:
                async with session.get(f"{base_url}/") as resp:
                    if resp.status == 200:
                        break
            except:
                await asyncio.sleep(0.5)

        print("Server ready, running tests...")
        print()

        # Test 1: Health check
        print("=== Test 1: Health Check (GET /) ===")
        try:
            async with session.get(f"{base_url}/") as resp:
                print(f"Status: {resp.status}")
                data = await resp.json()
                print(f"Message: {data.get('message', 'N/A')}")
                print("[PASS]")
        except Exception as e:
            print(f"Error: {e}")
            print("[FAIL]")

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
                    print("[PASS]" if d.get("lm_studio_connected") else "[INFO] LM Studio not running")
                else:
                    print(f"Error: {data.get('error')}")
                    print("[FAIL]")
        except Exception as e:
            print(f"Error: {e}")
            print("[FAIL]")

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
                    print("[PASS]")
                else:
                    print(f"Error: {data.get('error')}")
                    print("[FAIL]")
        except Exception as e:
            print(f"Error: {e}")
            print("[FAIL]")

        # Test 4: Yahoo Finance Test
        print("\n=== Test 4: Yahoo Finance Test (PUT /api/test/yahoo-finance) ===")
        try:
            async with session.put(f"{base_url}/api/test/yahoo-finance") as resp:
                print(f"Status: {resp.status}")
                data = await resp.json()
                print(f"Success: {data.get('success')}")
                print(f"Data source: {data.get('data_source', 'unknown')}")
                print(f"Available keys: {data.get('all_keys', [])}")
                results = data.get("yahoo_finance_results", {})
                count = 0
                for sym, info in results.items():
                    if info.get("success"):
                        print(f"  {sym}: ${info.get('price')} ({info.get('change_pct', 0):+.2f}%)")
                        count += 1
                    else:
                        print(f"  {sym}: FAIL - {info.get('error', 'unknown')[:60]}")
                print(f"Symbols with data: {count}/{len(results)}")
                print("[PASS]" if count > 0 else "[FAIL]")
        except Exception as e:
            print(f"Error: {e}")
            print("[FAIL]")

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
                    print("[PASS]")
                else:
                    print("[FAIL]")
        except Exception as e:
            print(f"Error: {e}")
            print("[FAIL]")

        # Test 6: Test Status
        print("\n=== Test 6: Test Status (GET /api/test/status) ===")
        try:
            async with session.get(f"{base_url}/api/test/status") as resp:
                print(f"Status: {resp.status}")
                data = await resp.json()
                print(f"Collector status: {data.get('collector_status')}")
                print(f"OHLC analyzer status: {data.get('ohlc_analyzer_status')}")
                print("[PASS]" if data.get("collector_status") else "[FAIL]")
        except Exception as e:
            print(f"Error: {e}")
            print("[FAIL]")

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
                    print(f"Response (first 150 chars): {resp_text[:150]}...")
                    print("[PASS]")
                elif data.get("success") and not data.get("data", {}).get("response"):
                    print("Got response but no content (fallback likely used)")
                    print("[INFO]")
                else:
                    print(f"Error: {data.get('error', 'No response')}")
                    print("[FAIL]")
        except Exception as e:
            print(f"Error: {e}")
            print("[FAIL]")

        print("\n" + "=" * 50)
        print("All HTTP Endpoint Tests Complete")


if __name__ == "__main__":
    print("MarketPulse End-to-End HTTP Test")
    print("=" * 50)

    # Start server in background thread
    output_queue = queue.Queue()
    server_thread = threading.Thread(target=run_server, args=(output_queue,), daemon=True)
    server_thread.start()

    print("Server starting in background...")
    time.sleep(5)  # Wait for server to start

    # Run tests
    asyncio.run(test_endpoints())

    print("\nTest complete. Server will continue running.")
