"""Alpaca API Client for MarketPulse
Handles stock market data collection from Alpaca Markets
"""

import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
import pandas as pd
from loguru import logger

from ..core.config import Settings


class AlpacaClient:
    """Alpaca Markets API client for real-time and historical market data"""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.api_key = settings.api_keys.alpaca.key_id
        self.secret_key = settings.api_keys.alpaca.secret_key
        self.base_url = settings.api_keys.alpaca.base_url
        
        self.session = None
        
        # Important symbols for market internals
        self.key_symbols = [
            'SPY',    # S&P 500 ETF (market breadth)
            'QQQ',    # NASDAQ ETF (tech sector)
            'IWM',    # Russell 2000 (small caps)
            'VIX',    # Volatility index
            'DIA',    # Dow Jones ETF
            'AAPL',   # Large cap tech
            'TSLA',   # Growth stock sentiment
            'NVDA'    # AI/semiconductor leader
        ]
        
    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession(
            headers={
                'APCA-API-KEY-ID': self.api_key,
                'APCA-API-SECRET-KEY': self.secret_key
            }
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
    
    async def get_bars(self, symbol: str, timeframe: str = '1Min', 
                      limit: int = 100) -> Optional[pd.DataFrame]:
        """
        Get OHLCV data for a symbol
        
        Args:
            symbol: Stock symbol (e.g., 'SPY')
            timeframe: '1Min', '5Min', '15Min', '1Hour', '1Day'
            limit: Number of bars to retrieve
            
        Returns:
            DataFrame with OHLCV data
        """
        try:
            # Calculate timeframe
            now = datetime.now()
            if timeframe == '1Min':
                start_time = now - timedelta(minutes=limit)
            elif timeframe == '5Min':
                start_time = now - timedelta(minutes=limit * 5)
            elif timeframe == '15Min':
                start_time = now - timedelta(minutes=limit * 15)
            elif timeframe == '1Hour':
                start_time = now - timedelta(hours=limit)
            elif timeframe == '1Day':
                start_time = now - timedelta(days=limit)
            else:
                start_time = now - timedelta(hours=limit)
            
            # Alpaca API endpoint
            url = f"{self.base_url}/v2/stocks/{symbol}/bars"
            params = {
                'timeframe': timeframe,
                'start': start_time.isoformat(),
                'end': now.isoformat(),
                'limit': limit,
                'adjustment': 'raw'
            }
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if 'bars' in data and data['bars']:
                        bars_df = pd.DataFrame(data['bars'])
                        bars_df['timestamp'] = pd.to_datetime(bars_df['t'])
                        bars_df.set_index('timestamp', inplace=True)
                        
                        # Rename columns to standard format
                        bars_df = bars_df.rename(columns={
                            'o': 'open',
                            'h': 'high', 
                            'l': 'low',
                            'c': 'close',
                            'v': 'volume'
                        })
                        
                        logger.debug(f"Retrieved {len(bars_df)} bars for {symbol}")
                        return bars_df
                    else:
                        logger.warning(f"No bars data found for {symbol}")
                        return None
                else:
                    logger.error(f"Alpaca API error {response.status}: {await response.text()}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error fetching bars for {symbol}: {e}")
            return None
    
    async def get_multiple_bars(self, symbols: List[str], 
                               timeframe: str = '1Min', 
                               limit: int = 100) -> Dict[str, pd.DataFrame]:
        """Get bars for multiple symbols concurrently"""
        tasks = []
        for symbol in symbols:
            task = self.get_bars(symbol, timeframe, limit)
            tasks.append((symbol, task))
        
        results = {}
        for symbol, task in tasks:
            try:
                df = await task
                if df is not None:
                    results[symbol] = df
            except Exception as e:
                logger.error(f"Failed to get data for {symbol}: {e}")
        
        return results
    
    async def get_market_internals(self) -> Dict[str, Any]:
        """
        Calculate basic market internals using key symbols
        This is the core function for getting regular market condition updates
        """
        try:
            logger.info("📊 Collecting market internals from Alpaca...")
            
            # Get current market data for key symbols
            data = await self.get_multiple_bars(self.key_symbols, '1Min', 60)
            
            if not data:
                logger.warning("No market data available")
                return {}
            
            internals = {}
            
            # SPY - Overall market sentiment
            if 'SPY' in data and not data['SPY'].empty:
                spy_latest = data['SPY'].iloc[-1]
                spy_prev = data['SPY'].iloc[-2] if len(data['SPY']) > 1 else spy_latest
                
                internals['spy'] = {
                    'price': float(spy_latest['close']),
                    'change': float(spy_latest['close'] - spy_prev['close']),
                    'change_pct': float((spy_latest['close'] - spy_prev['close']) / spy_prev['close'] * 100),
                    'volume': int(spy_latest['volume']),
                    'timestamp': spy_latest.name.isoformat()
                }
            
            # QQQ - NASDAQ/tech sentiment
            if 'QQQ' in data and not data['QQQ'].empty:
                qqq_latest = data['QQQ'].iloc[-1]
                qqq_prev = data['QQQ'].iloc[-2] if len(data['QQQ']) > 1 else qqq_latest
                
                internals['qqq'] = {
                    'price': float(qqq_latest['close']),
                    'change': float(qqq_latest['close'] - qqq_prev['close']),
                    'change_pct': float((qqq_latest['close'] - qqq_prev['close']) / qqq_prev['close'] * 100),
                    'volume': int(qqq_latest['volume']),
                    'timestamp': qqq_latest.name.isoformat()
                }
            
            # VIX - Volatility indicator
            if 'VIX' in data and not data['VIX'].empty:
                vix_latest = data['VIX'].iloc[-1]
                vix_prev = data['VIX'].iloc[-2] if len(data['VIX']) > 1 else vix_latest
                
                internals['vix'] = {
                    'price': float(vix_latest['close']),
                    'change': float(vix_latest['close'] - vix_prev['close']),
                    'change_pct': float((vix_latest['close'] - vix_prev['close']) / vix_prev['close'] * 100),
                    'volume': int(vix_latest['volume']),
                    'timestamp': vix_latest.name.isoformat()
                }
            
            # Volume flow analysis
            total_volume = sum(data[symbol]['volume'].sum() for symbol in data.keys())
            internals['volume_flow'] = {
                'total_volume_60min': int(total_volume),
                'symbols_tracked': len(data),
                'timestamp': datetime.now().isoformat()
            }
            
            logger.success("✅ Market internals collected successfully")
            return internals
            
        except Exception as e:
            logger.error(f"Error collecting market internals: {e}")
            return {}
    
    def format_internals_for_display(self, internals: Dict[str, Any]) -> str:
        """Format market internals for console display"""
        if not internals:
            return "❌ No market data available"
        
        lines = []
        lines.append("=" * 60)
        lines.append(f"📈 MARKET INTERNALS - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 60)
        
        # SPY (Market sentiment)
        if 'spy' in internals:
            spy = internals['spy']
            change_emoji = "🟢" if spy['change'] >= 0 else "🔴"
            lines.append(f"{change_emoji} SPY: ${spy['price']:.2f} | {spy['change']:+.2f} ({spy['change_pct']:+.2f}%)")
        
        # QQQ (Tech sentiment)  
        if 'qqq' in internals:
            qqq = internals['qqq']
            change_emoji = "🟢" if qqq['change'] >= 0 else "🔴"
            lines.append(f"{change_emoji} QQQ: ${qqq['price']:.2f} | {qqq['change']:+.2f} ({qqq['change_pct']:+.2f}%)")
        
        # VIX (Volatility)
        if 'vix' in internals:
            vix = internals['vix']
            vol_regime = "HIGH" if vix['price'] > 20 else "NORMAL" if vix['price'] > 15 else "LOW"
            vol_emoji = "🔴" if vix['change'] > 0 else "🟢"  # Higher VIX = red (bad)
            lines.append(f"{vol_emoji} VIX: {vix['price']:.2f} ({vol_regime}) | {vix['change']:+.2f}")
        
        # Volume flow
        if 'volume_flow' in internals:
            vf = internals['volume_flow']
            lines.append(f"📊 Volume: {vf['total_volume_60min']:,} (60min) | Symbols: {vf['symbols_tracked']}")
        
        lines.append("=" * 60)
        return "\n".join(lines)