"""
Unit tests for the LLM chat endpoint cached market data injection.
Verifies that:
1. _get_cached_market_context() properly formats market internals
2. chat_with_llm includes cached market data in messages
3. Frontend context generation maps dashboard data correctly (conceptual)
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))


async def _run(fn, *args):
    return await fn(*args)


def test_get_cached_market_context_formats_internals():
    """_get_cached_market_context should format market internals into a readable string."""
    from src.api.routers.llm import _get_cached_market_context

    mock_collector = AsyncMock()
    mock_collector.collect_market_internals.return_value = {
        "spy": {"price": 450.25, "change": 2.15, "change_pct": 0.48, "volume": 45000000},
        "qqq": {"price": 375.80, "change": -1.25, "change_pct": -0.33, "volume": 32000000},
        "vix": {"price": 18.50, "change": -0.75, "change_pct": -3.89, "volume": 0},
        "nq=f": {"price": 15200.0, "change": 45.0, "change_pct": 0.30, "volume": 120000},
        "btc-usd": {"price": 67000.0, "change": 1200.0, "change_pct": 1.82, "volume": 28000000000},
        "eth-usd": {"price": 3500.0, "change": -50.0, "change_pct": -1.41, "volume": 15000000000},
        "data_source": "yahoo",
        "data_quality": "good",
    }

    with patch("src.api.routers.llm._collector", mock_collector):
        result = asyncio.run(_get_cached_market_context())

    assert "[LIVE MARKET DATA from cache]" in result
    assert "SPY (S&P 500)" in result
    assert "450.25" in result
    assert "QQQ (Nasdaq 100)" in result
    assert "375.8" in result
    assert "VIX (Volatility)" in result
    assert "18.5" in result
    assert "NQ Futures" in result
    assert "BTC/USD" in result
    assert "67000" in result
    assert "ETH/USD" in result
    assert "Data Source: yahoo" in result
    assert "Data Quality: good" in result
    print("  PASS: _get_cached_market_context formats internals correctly")


def test_get_cached_market_context_returns_empty_when_no_collector():
    """Should return empty string if collector is None."""
    from src.api.routers.llm import _get_cached_market_context

    with patch("src.api.routers.llm._collector", None):
        result = asyncio.run(_get_cached_market_context())

    assert result == ""
    print("  PASS: Returns empty string when collector is None")


def test_get_cached_market_context_handles_empty_internals():
    """Should return empty string if internals are empty."""
    from src.api.routers.llm import _get_cached_market_context

    mock_collector = AsyncMock()
    mock_collector.collect_market_internals.return_value = None

    with patch("src.api.routers.llm._collector", mock_collector):
        result = asyncio.run(_get_cached_market_context())

    assert result == ""
    print("  PASS: Returns empty string for empty internals")


def test_get_cached_market_context_handles_partial_data():
    """Should format whatever symbols are available."""
    from src.api.routers.llm import _get_cached_market_context

    mock_collector = AsyncMock()
    mock_collector.collect_market_internals.return_value = {
        "spy": {"price": 450.25, "change": 2.15, "change_pct": 0.48, "volume": 45000000},
        "vix": {"price": 18.50, "change": -0.75, "change_pct": -3.89, "volume": 0},
    }

    with patch("src.api.routers.llm._collector", mock_collector):
        result = asyncio.run(_get_cached_market_context())

    assert "SPY (S&P 500)" in result
    assert "VIX (Volatility)" in result
    assert "QQQ" not in result
    print("  PASS: Handles partial data correctly")


def test_get_cached_market_context_handles_exception():
    """Should return empty string on any exception."""
    from src.api.routers.llm import _get_cached_market_context

    mock_collector = AsyncMock()
    mock_collector.collect_market_internals.side_effect = Exception("Redis connection failed")

    with patch("src.api.routers.llm._collector", mock_collector):
        result = asyncio.run(_get_cached_market_context())

    assert result == ""
    print("  PASS: Returns empty string on exception")


def test_chat_endpoint_includes_cached_market_data():
    """chat_with_llm should include cached market data in the messages sent to LLM."""
    from src.api.routers.deps import ChatRequest
    from src.api.routers.llm import chat_with_llm

    mock_collector = AsyncMock()
    mock_collector.collect_market_internals.return_value = {
        "spy": {"price": 450.25, "change": 2.15, "change_pct": 0.48, "volume": 45000000},
        "qqq": {"price": 375.80, "change": -1.25, "change_pct": -0.33, "volume": 32000000},
        "vix": {"price": 18.50, "change": -0.75, "change_pct": -3.89, "volume": 0},
        "data_source": "yahoo",
    }

    captured_messages = []

    mock_client_instance = AsyncMock()
    mock_client_instance.get_active_model.return_value = "test-model"
    mock_client_instance.session = MagicMock()
    mock_client_instance.session.closed = False

    def capture_completion(**kwargs):
        captured_messages.extend(kwargs.get("messages", []))
        return {"choices": [{"message": {"content": "SPY is at $450.25, up 0.48%"}}]}

    mock_client_instance.generate_completion.side_effect = capture_completion

    with (
        patch("src.api.routers.llm._collector", mock_collector),
        patch("src.api.routers.llm._get_llm_client", return_value=mock_client_instance),
    ):
        request = ChatRequest(
            message="What is SPY doing today?",
            context={"query_type": "general_market", "detected_symbols": ["SPY"]},
            symbol="SPY",
        )
        result = asyncio.run(chat_with_llm(request))

    assert result.success is True

    all_content = " ".join(msg["content"] for msg in captured_messages)

    assert "[LIVE MARKET DATA from cache]" in all_content, (
        f"Cached market data not found in messages. Content: {all_content[:500]}"
    )
    assert "SPY (S&P 500)" in all_content, f"SPY data not found in messages. Content: {all_content[:500]}"
    assert "450.25" in all_content, f"SPY price not found in messages. Content: {all_content[:500]}"
    assert "QQQ (Nasdaq 100)" in all_content, f"QQQ data not found in messages. Content: {all_content[:500]}"

    print("  PASS: chat_with_llm includes cached market data in LLM messages")


def test_chat_endpoint_includes_frontend_context_plus_cached():
    """chat_with_llm should include BOTH frontend context and cached market data."""
    from src.api.routers.deps import ChatRequest
    from src.api.routers.llm import chat_with_llm

    mock_collector = AsyncMock()
    mock_collector.collect_market_internals.return_value = {
        "spy": {"price": 450.25, "change": 2.15, "change_pct": 0.48, "volume": 45000000},
        "data_source": "yahoo",
    }

    captured_messages = []

    mock_client_instance = AsyncMock()
    mock_client_instance.get_active_model.return_value = "test-model"
    mock_client_instance.session = MagicMock()
    mock_client_instance.session.closed = False

    def capture_completion(**kwargs):
        captured_messages.extend(kwargs.get("messages", []))
        return {"choices": [{"message": {"content": "Analysis here"}}]}

    mock_client_instance.generate_completion.side_effect = capture_completion

    frontend_context = {
        "market_bias": "BULLISH",
        "volatility_regime": "NORMAL",
        "symbol_prices": {"SPY": {"price": 450.25, "change": 2.15, "change_pct": 0.48}},
        "query_type": "trend_analysis",
        "detected_symbols": ["SPY"],
    }

    with (
        patch("src.api.routers.llm._collector", mock_collector),
        patch("src.api.routers.llm._get_llm_client", return_value=mock_client_instance),
    ):
        request = ChatRequest(
            message="How is SPY trending?",
            context=frontend_context,
            symbol="SPY",
        )
        result = asyncio.run(chat_with_llm(request))

    assert result.success is True
    all_content = " ".join(msg["content"] for msg in captured_messages)

    assert "BULLISH" in all_content, "Frontend context missing from messages"
    assert "[LIVE MARKET DATA from cache]" in all_content, "Cached data missing from messages"
    assert "SPY (S&P 500)" in all_content, "Cached SPY data missing from messages"
    assert "trend_analysis" in all_content, "Query type missing from messages"

    print("  PASS: Both frontend context AND cached data present in messages")


def test_chat_endpoint_works_without_collector():
    """chat_with_llm should still work (without market data) if collector is None."""
    from src.api.routers.deps import ChatRequest
    from src.api.routers.llm import chat_with_llm

    captured_messages = []

    mock_client_instance = AsyncMock()
    mock_client_instance.get_active_model.return_value = "test-model"
    mock_client_instance.session = MagicMock()
    mock_client_instance.session.closed = False

    def capture_completion(**kwargs):
        captured_messages.extend(kwargs.get("messages", []))
        return {"choices": [{"message": {"content": "General response"}}]}

    mock_client_instance.generate_completion.side_effect = capture_completion

    with (
        patch("src.api.routers.llm._collector", None),
        patch("src.api.routers.llm._get_llm_client", return_value=mock_client_instance),
    ):
        request = ChatRequest(
            message="What is a moving average?",
            context=None,
            symbol=None,
        )
        result = asyncio.run(chat_with_llm(request))

    assert result.success is True
    assert len(captured_messages) > 0
    assert "[LIVE MARKET DATA from cache]" not in " ".join(msg["content"] for msg in captured_messages)
    print("  PASS: chat_with_llm works gracefully without collector")


if __name__ == "__main__":
    print("=" * 70)
    print("LLM Chat Cached Market Data Injection - Unit Tests")
    print("=" * 70)

    tests = [
        test_get_cached_market_context_formats_internals,
        test_get_cached_market_context_returns_empty_when_no_collector,
        test_get_cached_market_context_handles_empty_internals,
        test_get_cached_market_context_handles_partial_data,
        test_get_cached_market_context_handles_exception,
        test_chat_endpoint_includes_cached_market_data,
        test_chat_endpoint_includes_frontend_context_plus_cached,
        test_chat_endpoint_works_without_collector,
    ]

    passed = 0
    failed = 0
    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            import traceback

            print(f"  FAIL: {test_fn.__name__}: {e}")
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 70)
    print(f"Results: {passed}/{len(tests)} passed, {failed} failed")
    print("=" * 70)
    sys.exit(0 if failed == 0 else 1)
