"""MarketPulse Test Suite
Comprehensive tests for all core components
"""

import pytest
import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
from pathlib import Path
import sys

# Add src to path for testing
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.core.config import Settings
from src.core.database import DatabaseManager, PriceData, MarketInternals
from src.llm.llm_client import LMStudioClient, OpenRouterClient, LLMManager
from src.api.alpaca_client import AlpacaClient
from src.data.market_collector import MarketPulseCollector


class MockSettings:
    """Mock settings for testing without API keys"""
    
    def __init__(self):
        self.database_url = "sqlite:///:memory:"
        
        # Mock API keys
        self.api_keys = Mock()
        self.api_keys.alpaca = Mock()
        self.api_keys.alpaca.key_id = "test_key"
        self.api_keys.alpaca.secret_key = "test_secret"
        self.api_keys.alpaca.base_url = "https://paper-api.alpaca.markets"
        
        self.api_keys.rithmic = Mock()
        self.api_keys.rithmic.username = "test_user"
        self.api_keys.rithmic.password = "test_pass"
        
        self.api_keys.coinbase = Mock()
        self.api_keys.coinbase.api_key = "test_cb_key"
        self.api_keys.coinbase.api_secret = "test_cb_secret"
        
        self.api_keys.openrouter = Mock()
        self.api_keys.openrouter.api_key = "test_or_key"
        
        # LLM settings
        self.llm = Mock()
        self.llm.primary = Mock()
        self.llm.primary.base_url = "http://localhost:1234/v1"
        self.llm.primary.api_key = "not-needed"
        self.llm.primary.timeout = 30
        
        self.llm.fallback = Mock()
        self.llm.fallback.base_url = "https://openrouter.ai/api/v1"
        self.llm.fallback.api_key = "test_fallback"
        self.llm.fallback.timeout = 60
        
        # Market settings
        self.nq_symbol = "MNQ"
        self.btc_symbol = "BTC-USD"
        self.eth_symbol = "ETH-USD"
        
        # Analysis intervals
        self.internals_interval = 60
        self.llm_analysis_interval = 300


class TestMarketPulseCollector:
    """Test the main MarketPulse collector"""
    
    @pytest.fixture
    def mock_settings(self):
        """Create mock settings"""
        return MockSettings()
    
    @pytest.fixture
    def mock_internals_data(self):
        """Create mock market internals data"""
        return {
            'spy': {
                'price': 450.25,
                'change': 1.25,
                'change_pct': 0.28,
                'volume': 50000000,
                'timestamp': '2025-11-02T21:00:00Z'
            },
            'qqq': {
                'price': 180.50,
                'change': 2.15,
                'change_pct': 1.21,
                'volume': 30000000,
                'timestamp': '2025-11-02T21:00:00Z'
            },
            'vix': {
                'price': 18.50,
                'change': -0.50,
                'change_pct': -2.63,
                'volume': 1000000,
                'timestamp': '2025-11-02T21:00:00Z'
            },
            'volume_flow': {
                'total_volume_60min': 85000000,
                'symbols_tracked': 3,
                'timestamp': '2025-11-02T21:00:00Z'
            }
        }
    
    def test_calculate_momentum(self, mock_settings):
        """Test momentum calculation"""
        collector = MarketPulseCollector()
        collector.settings = mock_settings
        
        test_data = {
            'spy': {'change_pct': 2.5},
            'qqq': {'change_pct': 1.8}
        }
        
        momentum = collector._calculate_momentum(test_data)
        assert momentum == 1.25  # 2.5 / 2.0, clamped to -5 to 5
    
    def test_classify_volatility(self, mock_settings):
        """Test volatility regime classification"""
        collector = MarketPulseCollector()
        collector.settings = mock_settings
        
        # Test different volatility levels
        test_data_high = {'vix': {'price': 25.5}}
        test_data_normal = {'vix': {'price': 17.3}}
        test_data_low = {'vix': {'price': 12.8}}
        
        assert collector._classify_volatility(test_data_high) == "EXTREME"
        assert collector._classify_volatility(test_data_normal) == "HIGH"
        assert collector._classify_volatility(test_data_low) == "NORMAL"
    
    def test_calculate_correlation(self, mock_settings):
        """Test correlation calculation"""
        collector = MarketPulseCollector()
        collector.settings = mock_settings
        
        # Test positive correlation
        test_data_positive = {
            'spy': {'change_pct': 1.5},
            'qqq': {'change_pct': 2.0}
        }
        
        correlation = collector._calculate_correlation(test_data_positive)
        assert correlation > 0
        
        # Test negative correlation
        test_data_negative = {
            'spy': {'change_pct': 1.5},
            'qqq': {'change_pct': -2.0}
        }
        
        correlation = collector._calculate_correlation(test_data_negative)
        assert correlation < 0
    
    def test_format_internals_display(self, mock_settings, mock_internals_data):
        """Test market internals display formatting"""
        collector = MarketPulseCollector()
        collector.settings = mock_settings
        
        display = collector.format_internals_display(mock_internals_data)
        
        assert "MarketPulse Market Internals" in display
        assert "SPY (Market): $450.25" in display
        assert "QQQ (Tech): $180.50" in display
        assert "VIX (Vol): 18.50 (NORMAL)" in display
        assert "Market Bias: BULLISH" in display  # Both positive changes
        assert "=" * 70 in display
    
    @pytest.mark.asyncio
    async def test_analyze_with_ai_no_api(self, mock_settings, mock_internals_data):
        """Test AI analysis without actual API calls"""
        collector = MarketPulseCollector()
        collector.settings = mock_settings
        
        # Mock LLM manager
        collector.llm_manager = Mock()
        collector.llm_manager.analyze_market = AsyncMock(return_value="Test AI analysis result")
        
        result = await collector.analyze_with_ai(mock_internals_data, 'quick')
        assert result == "Test AI analysis result"
    
    def test_format_enhanced_display(self, mock_settings, mock_internals_data):
        """Test enhanced display with AI analysis"""
        collector = MarketPulseCollector()
        collector.settings = mock_settings
        
        ai_analysis = "🤖 LM Studio (Fast Analysis):\nMarket looks bullish with good momentum."
        
        enhanced = collector.format_enhanced_display(mock_internals_data, ai_analysis)
        
        assert "MarketPulse Market Internals" in enhanced
        assert "🤖 LM Studio (Fast Analysis):" in enhanced
        assert "Market looks bullish with good momentum" in enhanced


class TestDatabaseManager:
    """Test database operations"""
    
    @pytest.fixture
    def mock_db_manager(self):
        """Create in-memory database for testing"""
        db_manager = DatabaseManager("sqlite:///:memory:")
        db_manager.create_engine()
        db_manager.create_tables()
        return db_manager
    
    def test_save_price_data(self, mock_db_manager):
        """Test saving price data"""
        test_data = [
            {
                'timestamp': datetime.now(),
                'open': 449.00,
                'high': 451.50,
                'low': 448.75,
                'close': 450.25,
                'volume': 50000000,
                'trade_count': 250000,
                'vwap': 450.10
            }
        ]
        
        mock_db_manager.save_price_data("SPY", "1Min", test_data)
        
        # Verify data was saved
        session = mock_db_manager.get_session()
        price_data = session.query(PriceData).first()
        assert price_data.symbol == "SPY"
        assert price_data.timeframe == "1Min"
        assert price_data.close_price == 450.25
        session.close()
    
    def test_save_market_internals(self, mock_db_manager):
        """Test saving market internals"""
        test_internals = {
            'timestamp': datetime.now(),
            'advance_decline_ratio': 1.5,
            'volume_flow': 85000000,
            'momentum_score': 2.1,
            'volatility_regime': 'NORMAL',
            'correlation_strength': 0.85,
            'support_level': 441.50,
            'resistance_level': 459.00
        }
        
        mock_db_manager.save_market_internals("SPY", test_internals)
        
        # Verify data was saved
        session = mock_db_manager.get_session()
        internals_data = session.query(MarketInternals).first()
        assert internals_data.symbol == "SPY"
        assert internals_data.volatility_regime == "NORMAL"
        assert internals_data.momentum_score == 2.1
        session.close()


class TestLLMIntegration:
    """Test LLM integration components"""
    
    @pytest.fixture
    def mock_settings(self):
        return MockSettings()
    
    @pytest.mark.asyncio
    async def test_lm_studio_client_initialization(self, mock_settings):
        """Test LM Studio client initialization"""
        client = LMStudioClient(mock_settings)
        
        assert client.base_url == "http://localhost:1234/v1"
        assert client.timeout == 30
        assert 'fast' in client.models
        assert 'analyst' in client.models
        assert 'reviewer' in client.models
    
    @pytest.mark.asyncio
    async def test_lm_studio_mock_completion(self, mock_settings):
        """Test LM Studio completion with mock response"""
        client = LMStudioClient(mock_settings)
        
        # Mock the session and response
        mock_response = {
            'choices': [
                {'message': {'content': 'Test market analysis'}}
            ]
        }
        
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_post.return_value.__aenter__.return_value.status = 200
            mock_post.return_value.__aenter__.return_value.json = AsyncMock(return_value=mock_response)
            
            async with client:
                result = await client.generate_completion(
                    model='fast',
                    messages=[{'role': 'user', 'content': 'Test message'}],
                    max_tokens=100
                )
                
                assert result['choices'][0]['message']['content'] == 'Test market analysis'
    
    def test_llm_manager_status(self, mock_settings):
        """Test LLM manager status reporting"""
        manager = LLMManager()
        manager.settings = mock_settings
        
        status = manager.get_status()
        
        assert 'lm_studio' in status
        assert 'openrouter' in status
        assert status['lm_studio']['available'] == True
        assert 'fast' in status['lm_studio']['models']


class TestAlpacaClient:
    """Test Alpaca client functionality"""
    
    @pytest.fixture
    def mock_settings(self):
        return MockSettings()
    
    def test_alpaca_client_initialization(self, mock_settings):
        """Test Alpaca client initialization"""
        client = AlpacaClient(mock_settings)
        
        assert client.settings == mock_settings
        assert 'SPY' in client.key_symbols
        assert 'QQQ' in client.key_symbols
        assert 'VIX' in client.key_symbols
    
    def test_format_internals_for_display(self, mock_settings, mock_internals_data):
        """Test internals formatting"""
        client = AlpacaClient(mock_settings)
        
        formatted = client.format_internals_for_display(mock_internals_data)
        
        assert "MARKET INTERNALS" in formatted
        assert "SPY" in formatted
        assert "QQQ" in formatted
        assert "VIX" in formatted


class TestMarketCollectorIntegration:
    """Integration tests for the full system"""
    
    @pytest.fixture
    def mock_settings(self):
        return MockSettings()
    
    @pytest.mark.asyncio
    async def test_full_collection_workflow(self, mock_settings):
        """Test complete collection workflow without APIs"""
        collector = MarketPulseCollector()
        collector.settings = mock_settings
        
        # Mock the database and API calls
        collector.db_manager = Mock()
        collector.db_manager.create_engine = Mock()
        collector.db_manager.create_tables = Mock()
        collector.db_manager.save_market_internals = Mock()
        
        collector.alpaca_client = Mock()
        collector.alpaca_client.get_market_internals = AsyncMock(return_value={
            'spy': {'price': 450.25, 'change': 1.25, 'change_pct': 0.28},
            'qqq': {'price': 180.50, 'change': 2.15, 'change_pct': 1.21}
        })
        
        # Test initialization
        result = await collector.initialize()
        assert result == True
        
        # Test data collection
        internals = await collector.collect_market_internals()
        assert 'spy' in internals
        assert 'qqq' in internals
        
        # Test that database methods were called
        collector.db_manager.save_market_internals.assert_called()


def run_performance_benchmark():
    """Run performance benchmarks"""
    print("🏃 Running Performance Benchmarks...")
    
    # Test calculation speeds
    import time
    
    collector = MarketPulseCollector()
    mock_data = {
        'spy': {'change_pct': 2.5, 'price': 450.0},
        'qqq': {'change_pct': 1.8, 'price': 180.0}
    }
    
    # Benchmark momentum calculation
    start_time = time.time()
    for _ in range(1000):
        collector._calculate_momentum(mock_data)
    momentum_time = time.time() - start_time
    
    # Benchmark volatility classification
    vol_data = {'vix': {'price': 18.5}}
    start_time = time.time()
    for _ in range(1000):
        collector._classify_volatility(vol_data)
    volatility_time = time.time() - start_time
    
    print(f"✅ Momentum calculation (1000 iterations): {momentum_time:.4f}s")
    print(f"✅ Volatility classification (1000 iterations): {volatility_time:.4f}s")
    print(f"✅ Performance benchmarks completed")


if __name__ == "__main__":
    print("🧪 Running MarketPulse Test Suite...")
    print("=" * 50)
    
    # Run performance benchmarks
    run_performance_benchmark()
    
    print("\n📋 Test Categories:")
    print("• Unit tests for core calculations")
    print("• Database operations tests")
    print("• LLM integration tests")
    print("• API client tests")
    print("• Integration tests")
    print("\n💡 Run with pytest for full test suite:")
    print("  pytest tests/test_marketpulse.py -v")
    print("\n✅ All tests designed to run without API keys")