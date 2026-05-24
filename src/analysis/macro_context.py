"""Macro Context and VIX Regime Analysis

This module provides market regime classification, VIX analysis, and sector
performance tracking to inform options trading decisions.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional, Literal
from datetime import datetime, timedelta
from loguru import logger


class MacroRegime:
    """Macro market regime analyzer focusing on volatility and market conditions"""

    def __init__(self, yahoo_client):
        """Initialize with Yahoo Finance client

        Args:
            yahoo_client: Instance of YahooFinanceClient
        """
        self.yahoo_client = yahoo_client

        # Sector ETFs for tracking
        self.sector_etfs = {
            'XLK': 'Technology',
            'XLF': 'Financials',
            'XLV': 'Healthcare',
            'XLE': 'Energy',
            'XLI': 'Industrials',
            'XLC': 'Communication',
            'XLY': 'Consumer Discretionary',
            'XLP': 'Consumer Staples',
            'XLB': 'Materials',
            'XLU': 'Utilities',
            'XLRE': 'Real Estate'
        }

    def get_vix_percentile(self, days_lookback: int = 252) -> Dict[str, Any]:
        """Calculate VIX percentile over lookback period

        Args:
            days_lookback: Number of trading days to look back (default 252 = 1 year)

        Returns:
            Dictionary with VIX level, percentile, and historical data
        """
        try:
            # Get VIX historical data
            vix_data = self.yahoo_client.get_bars(
                '^VIX',
                period='1y',
                interval='1d'
            )

            if vix_data is None or vix_data.empty:
                logger.warning("Could not fetch VIX data")
                return {
                    'current_level': None,
                    'percentile': None,
                    'historical_mean': None,
                    'historical_std': None
                }

            # Get current VIX level
            current_vix = float(vix_data['close'].iloc[-1])

            # Calculate percentile
            percentile = (vix_data['close'] < current_vix).sum() / len(vix_data) * 100

            # Calculate statistics
            mean_vix = float(vix_data['close'].mean())
            std_vix = float(vix_data['close'].std())
            min_vix = float(vix_data['close'].min())
            max_vix = float(vix_data['close'].max())

            # Calculate recent trend (last 5 days)
            recent_vix = vix_data['close'].tail(5)
            vix_change = float(current_vix - recent_vix.iloc[0])
            vix_change_pct = (vix_change / recent_vix.iloc[0] * 100) if recent_vix.iloc[0] != 0 else 0

            return {
                'current_level': round(current_vix, 2),
                'percentile': round(percentile, 1),
                'change': round(vix_change, 2),
                'change_pct': round(vix_change_pct, 2),
                'historical_mean': round(mean_vix, 2),
                'historical_std': round(std_vix, 2),
                'historical_min': round(min_vix, 2),
                'historical_max': round(max_vix, 2),
                'lookback_days': days_lookback
            }

        except Exception as e:
            logger.error(f"Error calculating VIX percentile: {e}")
            return {
                'current_level': None,
                'percentile': None,
                'historical_mean': None,
                'historical_std': None,
                'error': str(e)
            }

    def classify_volatility_regime(
        self,
        vix_level: Optional[float] = None
    ) -> Dict[str, Any]:
        """Classify current volatility regime

        Args:
            vix_level: Current VIX level (if None, will fetch current)

        Returns:
            Dictionary with regime classification and trading implications
        """
        try:
            if vix_level is None:
                vix_data = self.get_vix_percentile()
                vix_level = vix_data.get('current_level')

                if vix_level is None:
                    return {
                        'regime': 'unknown',
                        'description': 'Unable to fetch VIX data',
                        'trading_implications': []
                    }
            else:
                vix_data = self.get_vix_percentile()

            percentile = vix_data.get('percentile', 50)

            # Classify regime
            if vix_level < 15:
                regime = 'low_volatility'
                description = 'Low volatility environment - complacent market'
                implications = [
                    'Favorable for selling premium (covered calls, cash-secured puts)',
                    'Consider calendar spreads to benefit from time decay',
                    'Be cautious of sudden volatility spikes',
                    'Earnings plays may offer better premium opportunities'
                ]
                risk_level = 'low'
            elif vix_level < 20:
                regime = 'normal'
                description = 'Normal volatility - balanced market conditions'
                implications = [
                    'Good environment for directional plays with defined risk',
                    'Bull call spreads and bear put spreads work well',
                    'Consider iron condors if expecting range-bound movement',
                    'Both buying and selling premium viable'
                ]
                risk_level = 'moderate'
            elif vix_level < 30:
                regime = 'elevated'
                description = 'Elevated volatility - increased uncertainty'
                implications = [
                    'Premium selling more profitable but riskier',
                    'Use wider spreads for defined-risk strategies',
                    'Be selective with naked positions',
                    'Consider ratio spreads to reduce net cost'
                ]
                risk_level = 'high'
            else:  # vix_level >= 30
                regime = 'high_volatility'
                description = 'High volatility - fearful market, major uncertainty'
                implications = [
                    'Favor defined-risk strategies (spreads, butterflies)',
                    'Avoid naked short options - risk is elevated',
                    'Look for mean reversion opportunities',
                    'Consider longer-dated options to avoid extreme theta decay',
                    'Volatility may contract - selling premium profitable if timed well'
                ]
                risk_level = 'very_high'

            return {
                'regime': regime,
                'vix_level': round(vix_level, 2),
                'percentile': percentile,
                'description': description,
                'trading_implications': implications,
                'risk_level': risk_level,
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error classifying volatility regime: {e}")
            return {
                'regime': 'error',
                'description': f'Error: {str(e)}',
                'trading_implications': [],
                'error': str(e)
            }

    def get_sector_performance(self, period: str = '1mo') -> Dict[str, Any]:
        """Get sector performance relative to SPY

        Args:
            period: Period for analysis ('5d', '1mo', '3mo', etc.)

        Returns:
            Dictionary with sector performance data
        """
        try:
            # Get SPY performance as benchmark
            spy_data = self.yahoo_client.get_bars('SPY', period=period, interval='1d')

            if spy_data is None or spy_data.empty:
                logger.warning("Could not fetch SPY data")
                return {'error': 'Could not fetch benchmark data'}

            spy_return = ((spy_data['close'].iloc[-1] / spy_data['close'].iloc[0]) - 1) * 100

            # Get sector ETF performance
            sector_performance = {}

            for etf, sector_name in self.sector_etfs.items():
                try:
                    sector_data = self.yahoo_client.get_bars(etf, period=period, interval='1d')

                    if sector_data is None or sector_data.empty:
                        continue

                    sector_return = ((sector_data['close'].iloc[-1] / sector_data['close'].iloc[0]) - 1) * 100
                    relative_strength = sector_return - spy_return

                    sector_performance[etf] = {
                        'name': sector_name,
                        'return': round(sector_return, 2),
                        'spy_return': round(spy_return, 2),
                        'relative_strength': round(relative_strength, 2),
                        'outperforming': relative_strength > 0
                    }

                except Exception as e:
                    logger.debug(f"Error fetching {etf}: {e}")
                    continue

            # Sort by relative strength
            sorted_sectors = sorted(
                sector_performance.items(),
                key=lambda x: x[1]['relative_strength'],
                reverse=True
            )

            # Identify leaders and laggards
            top_3 = sorted_sectors[:3] if len(sorted_sectors) >= 3 else sorted_sectors
            bottom_3 = sorted_sectors[-3:] if len(sorted_sectors) >= 3 else []

            return {
                'period': period,
                'spy_return': round(spy_return, 2),
                'sectors': dict(sorted_sectors),
                'leaders': [{'etf': etf, **data} for etf, data in top_3],
                'laggards': [{'etf': etf, **data} for etf, data in bottom_3],
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error getting sector performance: {e}")
            return {'error': str(e)}

    def calculate_correlations(
        self,
        symbols: List[str],
        period: str = '3mo'
    ) -> Optional[pd.DataFrame]:
        """Calculate correlation matrix for given symbols

        Args:
            symbols: List of symbols to analyze
            period: Period for correlation calculation

        Returns:
            Pandas DataFrame with correlation matrix
        """
        try:
            returns_dict = {}

            for symbol in symbols:
                data = self.yahoo_client.get_bars(symbol, period=period, interval='1d')

                if data is not None and not data.empty:
                    # Calculate daily returns
                    returns = data['close'].pct_change().dropna()
                    returns_dict[symbol] = returns

            if not returns_dict:
                return None

            # Create DataFrame and calculate correlation
            returns_df = pd.DataFrame(returns_dict)
            correlation_matrix = returns_df.corr()

            return correlation_matrix

        except Exception as e:
            logger.error(f"Error calculating correlations: {e}")
            return None

    def get_market_breadth(self) -> Dict[str, Any]:
        """Get market breadth indicators

        Returns:
            Dictionary with breadth metrics
        """
        try:
            # Get major indices
            indices = {
                'SPY': 'S&P 500',
                'QQQ': 'NASDAQ',
                'IWM': 'Russell 2000',
                'DIA': 'Dow Jones'
            }

            breadth_data = {}

            for symbol, name in indices.items():
                data = self.yahoo_client.get_bars(symbol, period='5d', interval='1d')

                if data is not None and not data.empty:
                    current = float(data['close'].iloc[-1])
                    prev = float(data['close'].iloc[0])
                    change_pct = ((current / prev) - 1) * 100

                    breadth_data[symbol] = {
                        'name': name,
                        'price': round(current, 2),
                        'change_pct': round(change_pct, 2),
                        'trending': 'up' if change_pct > 0 else 'down'
                    }

            # Calculate advance/decline
            advancing = sum(1 for data in breadth_data.values() if data['change_pct'] > 0)
            total = len(breadth_data)
            ad_ratio = advancing / total if total > 0 else 0

            return {
                'indices': breadth_data,
                'advance_decline_ratio': round(ad_ratio, 2),
                'advancing': advancing,
                'declining': total - advancing,
                'market_bias': 'bullish' if ad_ratio > 0.6 else 'bearish' if ad_ratio < 0.4 else 'neutral',
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error getting market breadth: {e}")
            return {'error': str(e)}

    def get_comprehensive_context(self) -> Dict[str, Any]:
        """Get comprehensive macro context for options trading

        Returns:
            Dictionary with all macro indicators
        """
        try:
            # Get VIX analysis
            vix_data = self.get_vix_percentile()
            regime = self.classify_volatility_regime(vix_data.get('current_level'))

            # Get sector performance
            sector_perf = self.get_sector_performance('1mo')

            # Get market breadth
            breadth = self.get_market_breadth()

            # Get risk-free rate
            risk_free_rate = self.yahoo_client.get_risk_free_rate()

            return {
                'vix': vix_data,
                'volatility_regime': regime,
                'sector_performance': sector_perf,
                'market_breadth': breadth,
                'risk_free_rate': round(risk_free_rate * 100, 2),  # Convert to percentage
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error getting comprehensive context: {e}")
            return {'error': str(e)}
