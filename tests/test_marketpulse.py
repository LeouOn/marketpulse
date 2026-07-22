"""MarketPulse Test Suite

Stale-suite cleanup: this file was created in the initial repo setup
(`4b02494 setup and initialize market pulse`, 2026-05-21) and largely drifted
from the current API surface. Surviving tests were either re-anchored to
the current API or, where they tested concepts/columns that no longer exist,
deleted. Cross-cutting coverage that lives in dedicated test files (test_rag,
test_llm_chat_cached_data, test_database_engine, etc.) was not affected.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

# Add src to path for testing
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.data.market_collector import MarketPulseCollector
from src.llm.llm_client import LLMManager, LMStudioClient


class TestMarketPulseCollector:
    def test_calculate_momentum(self, mock_settings):
        """Test momentum calculation"""
        collector = MarketPulseCollector()
        collector.settings = mock_settings

        test_data = {"spy": {"change_pct": 2.5}, "qqq": {"change_pct": 1.8}}

        momentum = collector._calculate_momentum(test_data)
        assert momentum == 1.25

    def test_classify_volatility(self, mock_settings):
        """Test volatility regime classification with current thresholds (>30 EXTREME, >20 HIGH, >15 NORMAL, <=15 LOW)."""
        collector = MarketPulseCollector()
        collector.settings = mock_settings

        assert collector._classify_volatility({"vix": {"price": 35.0}}) == "EXTREME"
        assert collector._classify_volatility({"vix": {"price": 25.0}}) == "HIGH"
        assert collector._classify_volatility({"vix": {"price": 17.0}}) == "NORMAL"
        assert collector._classify_volatility({"vix": {"price": 12.0}}) == "LOW"
        assert collector._classify_volatility({"vix": {"price": 18.50}}) == "NORMAL"

    def test_calculate_correlation(self, mock_settings):
        """Test correlation calculation"""
        collector = MarketPulseCollector()
        collector.settings = mock_settings

        positive = collector._calculate_correlation({"spy": {"change_pct": 1.5}, "qqq": {"change_pct": 2.0}})
        assert positive > 0

        negative = collector._calculate_correlation({"spy": {"change_pct": 1.5}, "qqq": {"change_pct": -2.0}})
        assert negative < 0

    def test_format_internals_display(self, mock_settings, mock_internals_data):
        """Test market internals display formatting (current format uses emojis + pipe-separated fields)."""
        collector = MarketPulseCollector()
        collector.settings = mock_settings

        display = collector.format_internals_display(mock_internals_data)

        assert "MarketPulse Market Internals" in display
        assert "SPY (Market):" in display
        assert "$450.25" in display
        assert "QQQ (Tech):" in display
        assert "$180.50" in display
        assert "VIX (Vol):" in display
        assert "18.50" in display
        assert "Market Bias: BULLISH" in display
        assert "=" * 70 in display

    @pytest.mark.asyncio
    async def test_analyze_with_ai_no_api(self, mock_settings, mock_internals_data):
        """Test AI analysis without actual API calls"""
        collector = MarketPulseCollector()
        collector.settings = mock_settings

        collector.llm_manager = Mock()
        collector.llm_manager.analyze_market = AsyncMock(return_value="Test AI analysis result")

        result = await collector.analyze_with_ai(mock_internals_data, "quick")
        assert result == "Test AI analysis result"

    def test_format_enhanced_display(self, mock_settings, mock_internals_data):
        """Test enhanced display with AI analysis"""
        collector = MarketPulseCollector()
        collector.settings = mock_settings

        ai_analysis = "🤖 Analysis:\nMarket looks bullish with good momentum."
        enhanced = collector.format_enhanced_display(mock_internals_data, ai_analysis)

        assert "MarketPulse Market Internals" in enhanced
        assert "🤖" in enhanced
        assert "Market looks bullish with good momentum" in enhanced


class TestLLMIntegration:
    @pytest.mark.asyncio
    async def test_lm_studio_client_initialization(self, mock_settings):
        """Test LM Studio client initialization (model_capabilities is the current registry)."""
        client = LMStudioClient(mock_settings)

        assert client.base_url == "http://localhost:1234/v1"
        assert client.timeout == 30
        assert "fast_analysis" in client.model_capabilities
        assert "deep_analysis" in client.model_capabilities
        assert "trade_review" in client.model_capabilities
        assert "data_validation" in client.model_capabilities

    @pytest.mark.asyncio
    async def test_lm_studio_mock_completion(self, mock_settings):
        """Test LM Studio completion with mock response"""
        client = LMStudioClient(mock_settings)

        mock_response = {"choices": [{"message": {"content": "Test market analysis"}}]}

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.return_value.__aenter__.return_value.status = 200
            mock_post.return_value.__aenter__.return_value.json = AsyncMock(return_value=mock_response)

            async with client:
                result = await client.generate_completion(
                    model="fast_analysis", messages=[{"role": "user", "content": "Test message"}], max_tokens=100
                )

                assert result["choices"][0]["message"]["content"] == "Test market analysis"

    def test_llm_manager_status(self, mock_settings):
        """Test LLM manager status reporting (current schema: deepseek/lm_studio/openrouter/minimax)."""
        manager = LLMManager()
        manager.settings = mock_settings

        status = manager.get_status()

        assert "deepseek" in status
        assert "lm_studio" in status
        assert "openrouter" in status
        assert "minimax" in status
        assert status["lm_studio"]["available"] is True


if __name__ == "__main__":
    print("MarketPulse Test Suite")
    print("=" * 50)
    print("Run with: pytest tests/test_marketpulse.py -v")
