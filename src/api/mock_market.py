"""Mock Market Data Provider for Testing
Provides realistic market data without requiring API keys
"""

import random
import time
from datetime import datetime, timedelta
from typing import Dict, Any
import asyncio

class MockMarketDataProvider:
    """Provides realistic mock market data for testing purposes"""

    def __init__(self):
        # Base prices around current market levels
        self.base_prices = {
            'SPY': 450.25,
            'QQQ': 375.80,
            'VIX': 18.50,
            'IWM': 195.40,
            'DIA': 375.60,
            'AAPL': 175.80,
            'TSLA': 245.30,
            'NVDA': 475.20
        }

        # Macro indicators with realistic values
        self.macro_base = {
            'DXY': 105.8,      # Dollar Index
            'TNX': 4.25,       # 10Y Treasury Yield
            'CLF': 75.20,      # Crude Oil Futures
            'GC': 1980.50,     # Gold Futures
            'BTC': 43500,      # Bitcoin
            'ETH': 2280        # Ethereum
        }

        self.last_update = datetime.now()
        self.trend_direction = {}

    async def get_market_internals(self) -> Dict[str, Any]:
        """Generate realistic market internals"""
        now = datetime.now()

        # Simulate market trends
        self._update_trends()

        internals = {}

        # Generate data for key symbols
        for symbol, base_price in self.base_prices.items():
            price_change = self._generate_price_change(symbol, base_price)

            internals[symbol.lower()] = {
                'price': price_change['price'],
                'change': price_change['change'],
                'change_pct': price_change['change_pct'],
                'volume': self._generate_volume(symbol),
                'timestamp': now.isoformat()
            }

        # Add volume flow metrics
        total_volume = sum(internals[sym.lower()]['volume'] for sym in ['SPY', 'QQQ', 'IWM'])

        internals['volume_flow'] = {
            'total_volume_60min': total_volume,
            'symbols_tracked': len(self.base_prices)
        }

        return internals

    async def get_macro_data(self) -> Dict[str, Any]:
        """Generate important macro indicators"""
        now = datetime.now()
        macro_data = {}

        for symbol, base_value in self.macro_base.items():
            change = self._generate_macro_change(symbol, base_value)
            macro_data[symbol] = {
                'price': change['price'],
                'change': change['change'],
                'change_pct': change['change_pct'],
                'timestamp': now.isoformat()
            }

        # Add additional macro metrics
        macro_data.update({
            'market_session': self._get_market_session(),
            'economic_sentiment': self._get_sentiment_indicator(),
            'sector_performance': self._get_sector_performance(),
            'risk_appetite': self._get_risk_appetite()
        })

        return macro_data

    def _update_trends(self):
        """Update trend directions for realistic price movements"""
        if random.random() < 0.1:  # 10% chance to change trend
            symbols = list(self.base_prices.keys())
            for symbol in symbols:
                if random.random() < 0.3:  # 30% chance for each symbol
                    self.trend_direction[symbol] = random.choice(['up', 'down', 'sideways'])

    def _generate_price_change(self, symbol: str, base_price: float) -> Dict[str, float]:
        """Generate realistic price change"""
        trend = self.trend_direction.get(symbol, 'sideways')

        # Base volatility by symbol type
        if symbol == 'VIX':
            volatility = 0.03  # VIX is more volatile
        elif symbol in ['TSLA', 'NVDA']:
            volatility = 0.025  # Tech stocks
        else:
            volatility = 0.008  # ETFs and indices

        # Apply trend bias
        if trend == 'up':
            bias = 0.3
        elif trend == 'down':
            bias = -0.3
        else:
            bias = 0.0

        # Generate random change
        change_pct = (random.gauss(bias, 1) * volatility)
        change = base_price * change_pct
        new_price = base_price + change

        # Update base price for next iteration
        self.base_prices[symbol] = new_price

        return {
            'price': new_price,
            'change': change,
            'change_pct': change_pct * 100
        }

    def _generate_volume(self, symbol: str) -> int:
        """Generate realistic volume data"""
        base_volumes = {
            'SPY': 45000000,
            'QQQ': 32000000,
            'VIX': 15000000,
            'IWM': 28000000,
            'DIA': 18000000,
            'AAPL': 55000000,
            'TSLA': 95000000,
            'NVDA': 42000000
        }

        base = base_volumes.get(symbol, 20000000)
        # Add variance (-50% to +100%)
        variance = random.uniform(0.5, 2.0)
        return int(base * variance)

    def _generate_macro_change(self, symbol: str, base_value: float) -> Dict[str, float]:
        """Generate realistic macro indicator changes"""
        volatilities = {
            'DXY': 0.005,   # Dollar Index
            'TNX': 0.02,    # Treasury Yield
            'CLF': 0.025,   # Oil
            'GC': 0.008,    # Gold
            'BTC': 0.04,    # Bitcoin
            'ETH': 0.045    # Ethereum
        }

        volatility = volatilities.get(symbol, 0.01)
        change_pct = random.gauss(0, 1) * volatility
        change = base_value * change_pct
        new_price = base_value + change

        # Update base price
        self.macro_base[symbol] = new_price

        return {
            'price': new_price,
            'change': change,
            'change_pct': change_pct * 100
        }

    def _get_market_session(self) -> str:
        """Determine current market session"""
        now = datetime.now()
        hour = now.hour

        if 9 <= hour < 16:
            return "US Regular"
        elif 16 <= hour < 20:
            return "US After Hours"
        elif hour >= 20 or hour < 4:
            return "Asian Session"
        else:
            return "European Session"

    def _get_sentiment_indicator(self) -> str:
        """Generate economic sentiment indicator"""
        sentiment_score = random.gauss(0, 1)

        if sentiment_score > 1:
            return "Very Bullish"
        elif sentiment_score > 0.5:
            return "Bullish"
        elif sentiment_score > -0.5:
            return "Neutral"
        elif sentiment_score > -1:
            return "Bearish"
        else:
            return "Very Bearish"

    def _get_sector_performance(self) -> Dict[str, float]:
        """Generate sector performance data"""
        sectors = {
            'Technology': random.gauss(0.5, 1.2),
            'Healthcare': random.gauss(0.2, 0.8),
            'Financials': random.gauss(0.1, 1.0),
            'Energy': random.gauss(-0.2, 1.5),
            'Consumer Discretionary': random.gauss(0.3, 1.1),
            'Industrials': random.gauss(0.0, 0.9),
            'Materials': random.gauss(-0.1, 1.0),
            'Utilities': random.gauss(-0.3, 0.7),
            'Real Estate': random.gauss(-0.2, 0.8),
            'Communication Services': random.gauss(0.4, 1.3)
        }

        return {sector: round(perf, 2) for sector, perf in sectors.items()}

    def _get_risk_appetite(self) -> str:
        """Calculate risk appetite based on market data"""
        # Simple risk calculation based on VIX and correlation
        vix_change = self.base_prices['VIX'] - 18.50  # From base
        spy_change_pct = (self.base_prices['SPY'] - 450.25) / 450.25

        risk_score = spy_change_pct - (vix_change / 18.50)

        if risk_score > 0.02:
            return "Risk On"
        elif risk_score < -0.02:
            return "Risk Off"
        else:
            return "Balanced"

# Global instance
mock_provider = MockMarketDataProvider()