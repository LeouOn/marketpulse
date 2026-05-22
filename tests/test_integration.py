"""Quick test script for MarketPulse - no external dependencies needed"""
import sys
import os
import asyncio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test that all modules can be imported"""
    print("\n=== Testing Imports ===")

    try:
        from src.core.config import get_settings
        print("[OK] config")
    except Exception as e:
        print(f"[FAIL] config: {e}")

    try:
        from src.core.cache import CacheService
        print("[OK] cache")
    except Exception as e:
        print(f"[FAIL] cache: {e}")

    try:
        from src.core.database import DatabaseManager
        print("[OK] database")
    except Exception as e:
        print(f"[FAIL] database: {e}")

    try:
        from src.api.yahoo_client import YahooFinanceClient
        print("[OK] yahoo_client")
    except Exception as e:
        print(f"[FAIL] yahoo_client: {e}")

    try:
        from src.llm.llm_client import LMStudioClient, OpenRouterClient, LLMManager
        print("[OK] llm_client")
    except Exception as e:
        print(f"[FAIL] llm_client: {e}")

    try:
        from src.llm.minimax_client import MiniMaxClient
        print("[OK] minimax_client")
    except Exception as e:
        print(f"[FAIL] minimax_client: {e}")

    try:
        from src.data.market_collector import MarketPulseCollector
        print("[OK] market_collector")
    except Exception as e:
        print(f"[FAIL] market_collector: {e}")

    try:
        from src.api.alpaca_client import AlpacaClient
        print("[OK] alpaca_client")
    except Exception as e:
        print(f"[FAIL] alpaca_client: {e}")

    try:
        from src.api.rithmic_client import RithmicClient
        print("[OK] rithmic_client")
    except Exception as e:
        print(f"[FAIL] rithmic_client: {e}")

    try:
        from src.api.coinbase_client import CoinbaseClient
        print("[OK] coinbase_client")
    except Exception as e:
        print(f"[FAIL] coinbase_client: {e}")

    try:
        from src.api.market_data_collector import MarketDataCollector
        print("[OK] market_data_collector")
    except Exception as e:
        print(f"[FAIL] market_data_collector: {e}")

    try:
        from src.api.auth import validate_api_key
        print("[OK] auth")
    except Exception as e:
        print(f"[FAIL] auth: {e}")


def test_yahoo_client():
    """Test Yahoo Finance client"""
    print("\n=== Testing Yahoo Finance ===")

    from src.api.yahoo_client import YahooFinanceClient

    client = YahooFinanceClient()

    # Test with a single symbol to be quick
    try:
        data = client.get_single_symbol_data("SPY")
        if data:
            print(f"[OK] SPY: ${data['price']:.2f} ({data['change_pct']:+.2f}%)")
        else:
            print("[FAIL] No data returned")
    except Exception as e:
        print(f"[FAIL] Yahoo Finance error: {e}")


def test_llm_config():
    """Test LLM configuration"""
    print("\n=== Testing LLM Config ===")

    from src.core.config import get_settings

    settings = get_settings()

    print(f"Primary LLM URL: {settings.llm.primary.base_url}")
    print(f"Fallback LLM URL: {settings.llm.fallback.base_url}")
    print(f"MiniMax URL: {settings.llm.minimax.base_url}")
    print(f"MiniMax model: {settings.llm.minimax.model}")


async def test_cache_isolation():
    """Test cache with timeout"""
    print("\n=== Testing Cache (with timeout) ===")

    from src.core.cache import CacheService

    cache = CacheService()
    print("Cache service created")

    try:
        # Use wait_for to add timeout
        result = await asyncio.wait_for(cache.connect(), timeout=3)
        print(f"Cache connect result: {result}")
    except asyncio.TimeoutError:
        print("[SKIP] Cache connection timed out (Redis not running - expected)")
    except Exception as e:
        print(f"[INFO] Cache error: {e}")


def test_api_fixtures():
    """Test API router imports"""
    print("\n=== Testing API Routers ===")

    try:
        from src.api.routers import market, llm, test, websocket
        print("[OK] All routers imported")
    except Exception as e:
        print(f"[FAIL] Router import error: {e}")


if __name__ == "__main__":
    print("MarketPulse Integration Test")
    print("=" * 50)

    test_imports()
    test_llm_config()
    test_api_fixtures()

    # Run async tests
    asyncio.run(test_cache_isolation())

    # Test Yahoo (sync, may take a few seconds)
    test_yahoo_client()

    print("\n" + "=" * 50)
    print("Tests complete")