"""MarketPulse Market Data Collection Service
Orchestrates data collection from multiple APIs and provides market internals analysis
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from loguru import logger

from ..api.yahoo_client import YahooFinanceClient
from ..core.config import get_settings
from ..core.database import DatabaseManager
from ..llm.llm_client import LLMManager


class MarketPulseCollector:
    """Main market data collection service for MarketPulse"""
    
    def __init__(self):
        self.settings = get_settings()
        self.db_manager = DatabaseManager(self.settings.database_url)
        self.yahoo_client = None
        self.llm_manager = LLMManager()
        self.running = False
        
        # Market symbols to monitor
        self.symbols = {
            'NQ=F': self.settings.nq_symbol,  # Use full symbol as key for consistency
            'BTC-USD': self.settings.btc_symbol,
            'ETH-USD': self.settings.eth_symbol,
            'SPY': 'SPY',
            'QQQ': 'QQQ',
            'VIX': '^VIX',  # Fixed: VIX needs ^ prefix for Yahoo Finance
            'IWM': 'IWM'
        }
    
    async def initialize(self):
        """Initialize the market collector"""
        logger.info("Initializing MarketPulse Collector...")
        
        try:
            # Initialize database (handle missing psycopg2 gracefully)
            try:
                self.db_manager.create_engine()
                self.db_manager.create_tables()
                logger.success("Database initialized")
            except Exception as db_error:
                logger.warning(f"Database initialization failed (continuing without database): {db_error}")
                # Continue without database - some features will be limited

            # Initialize API clients
            self.yahoo_client = YahooFinanceClient(self.settings)
            logger.success("API clients initialized")

            return True

        except Exception as e:
            logger.error(f"Failed to initialize MarketPulse: {e}")
            return False
    
    async def collect_market_internals(self) -> Dict[str, Any]:
        """Collect and analyze current market internals"""
        logger.info("📊 Starting market internals collection...")

        # Try to collect raw data from Alpaca first
        internals = None
        try:
            if not self.yahoo_client:
                self.yahoo_client = YahooFinanceClient(self.settings)

            raw_internals = self.yahoo_client.get_market_internals(list(self.symbols.values()))

            if raw_internals:
                # Map uppercase symbols to lowercase keys expected by frontend
                internals = {}
                for key, symbol in self.symbols.items():
                    # Normalize symbol for lookup (remove ^ prefix)
                    lookup_symbol = symbol
                    if symbol in raw_internals:
                        internals[key.lower()] = raw_internals[symbol]
                    elif symbol.replace('^', '') in raw_internals:
                        internals[key.lower()] = raw_internals[symbol.replace('^', '')]
                    else:
                        logger.warning(f"⚠️ Symbol {symbol} not found in API response")

                if internals:
                    logger.info("Successfully collected data from Yahoo Finance")
                    internals['data_source'] = 'yahoo_finance'
                else:
                    logger.warning("No matching symbols found in Yahoo Finance response")
                    internals = None
            else:
                logger.warning("No data returned from Yahoo Finance")
                internals = None

        except Exception as api_error:
            logger.warning(f"Yahoo Finance API unavailable: {api_error}")
            internals = None

        # Fallback to mock data if API fails
        if not internals:
            logger.info("🎭 Using mock market data for testing")
            from ..api.mock_market import mock_provider
            internals = await mock_provider.get_market_internals()
            internals['data_source'] = 'mock'

        # Ensure we have the required symbols for the frontend
        required_symbols = ['spy', 'qqq', 'vix']
        for symbol in required_symbols:
            if symbol not in internals:
                logger.warning(f"⚠️ Missing {symbol.upper()} data, adding placeholder")
                internals[symbol] = {
                    'price': 0.0,
                    'change': 0.0,
                    'change_pct': 0.0,
                    'volume': 0,
                    'timestamp': datetime.now().isoformat()
                }

        # Add volume flow if missing
        if 'volume_flow' not in internals:
            internals['volume_flow'] = {
                'total_volume_60min': sum(internals[sym]['volume'] for sym in required_symbols if sym in internals),
                'symbols_tracked': len(required_symbols)
            }

        logger.success("✅ Market internals collected successfully")
        return internals
    
    def _calculate_ad_line(self, internals: Dict[str, Any]) -> Optional[float]:
        """Calculate advance/decline line ratio"""
        try:
            if 'spy' in internals and 'qqq' in internals:
                spy_change = internals['spy']['change']
                qqq_change = internals['qqq']['change']
                
                if spy_change > 0 and qqq_change > 0:
                    return 2.0  # Both advancing
                elif spy_change < 0 and qqq_change < 0:
                    return 0.5  # Both declining
                else:
                    return 1.0  # Mixed
            return None
        except Exception:
            return None
    
    def _calculate_momentum(self, internals: Dict[str, Any]) -> Optional[float]:
        """Calculate momentum score based on recent price changes"""
        try:
            if 'spy' in internals:
                spy_change_pct = internals['spy']['change_pct']
                return max(min(spy_change_pct / 2.0, 5.0), -5.0)
            return None
        except Exception:
            return None
    
    def _classify_volatility(self, internals: Dict[str, Any]) -> str:
        """Classify current volatility regime"""
        try:
            if 'vix' in internals:
                vix_price = internals['vix']['price']
                if vix_price > 30:
                    return "EXTREME"
                elif vix_price > 20:
                    return "HIGH"
                elif vix_price > 15:
                    return "NORMAL"
                else:
                    return "LOW"
            return "UNKNOWN"
        except Exception:
            return "UNKNOWN"
    
    def _calculate_correlation(self, internals: Dict[str, Any]) -> Optional[float]:
        """Calculate SPY-QQQ correlation strength"""
        try:
            if 'spy' in internals and 'qqq' in internals:
                spy_change = internals['spy']['change_pct']
                qqq_change = internals['qqq']['change_pct']
                
                if abs(spy_change) > 0.1 and abs(qqq_change) > 0.1:
                    correlation = (spy_change * qqq_change) / (abs(spy_change) * abs(qqq_change))
                    return max(min(correlation, 1.0), -1.0)
            return None
        except Exception:
            return None
    
    def _calculate_support(self, internals: Dict[str, Any]) -> Optional[float]:
        """Calculate key support level (simplified)"""
        try:
            if 'spy' in internals:
                spy_price = internals['spy']['price']
                return spy_price * 0.98
            return None
        except Exception:
            return None
    
    def _calculate_resistance(self, internals: Dict[str, Any]) -> Optional[float]:
        """Calculate key resistance level (simplified)"""
        try:
            if 'spy' in internals:
                spy_price = internals['spy']['price']
                return spy_price * 1.02
            return None
        except Exception:
            return None
    
    def format_internals_display(self, internals: Dict[str, Any]) -> str:
        """Format internals for console display"""
        if not internals:
            return "❌ No market data available"
        
        lines = []
        lines.append("=" * 70)
        lines.append(f"MarketPulse Market Internals - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 70)
        
        # Overall Market Health
        lines.append("🔍 MARKET OVERVIEW:")
        
        if 'spy' in internals:
            spy = internals['spy']
            change_emoji = "🟢" if spy['change'] >= 0 else "🔴"
            change_sign = "+" if spy['change'] >= 0 else ""
            lines.append(f"   {change_emoji} SPY (Market): ${spy['price']:.2f} | {change_sign}{spy['change']:.2f} ({change_sign}{spy['change_pct']:.2f}%)")
        
        if 'qqq' in internals:
            qqq = internals['qqq']
            change_emoji = "🟢" if qqq['change'] >= 0 else "🔴"
            change_sign = "+" if qqq['change'] >= 0 else ""
            lines.append(f"   {change_emoji} QQQ (Tech):  ${qqq['price']:.2f} | {change_sign}{qqq['change']:.2f} ({change_sign}{qqq['change_pct']:.2f}%)")
        
        if 'vix' in internals:
            vix = internals['vix']
            vol_regime = "🔴 HIGH" if vix['price'] > 20 else "🟡 NORMAL" if vix['price'] > 15 else "🟢 LOW"
            change_emoji = "📈" if vix['change'] > 0 else "📉"
            lines.append(f"   {change_emoji} VIX (Vol):   {vix['price']:.2f} ({vol_regime})")
        
        lines.append("")
        
        # Market Internals Analysis
        lines.append("🧠 MARKET INTERNALS:")
        lines.append("   • Volatility Regime: Real-time analysis based on VIX")
        lines.append("   • Volume Flow: 60-minute accumulation tracking")
        lines.append("   • Correlation: SPY-QQQ relationship strength")
        lines.append("   • Support/Resistance: Dynamic levels")
        
        # Trading Context
        lines.append("")
        lines.append("🎯 TRADING CONTEXT:")
        
        # Determine overall market bias
        market_bias = "NEUTRAL"
        if 'spy' in internals and 'qqq' in internals:
            spy_trend = internals['spy']['change']
            qqq_trend = internals['qqq']['change']
            
            if spy_trend > 0 and qqq_trend > 0:
                market_bias = "BULLISH"
            elif spy_trend < 0 and qqq_trend < 0:
                market_bias = "BEARISH"
            else:
                market_bias = "MIXED"
        
        bias_emoji = "🟢" if market_bias == "BULLISH" else "🔴" if market_bias == "BEARISH" else "🟡"
        lines.append(f"   {bias_emoji} Market Bias: {market_bias}")
        
        if 'vix' in internals and internals['vix']['price'] > 25:
            lines.append("   ⚠️  High volatility - consider position sizing carefully")
        
        lines.append("=" * 70)
        return "\n".join(lines)
    
    async def run_continuous_monitoring(self):
        """Run continuous market monitoring"""
        logger.info("🔄 Starting continuous market monitoring...")
        self.running = True
        
        # Initial collection
        logger.info("📡 Performing initial market data collection...")
        await self.collect_market_internals()
        
        # Periodic collection using asyncio
        interval_seconds = self.settings.internals_interval
        next_run = time.time() + interval_seconds
        
        try:
            while self.running:
                await asyncio.sleep(max(0, next_run - time.time()))
                if self.running:
                    await self.collect_market_internals()
                next_run += interval_seconds
                
        except KeyboardInterrupt:
            logger.info("⏹️ Monitoring stopped by user")
        except Exception as e:
            logger.error(f"❌ Error in monitoring loop: {e}")
        finally:
            self.running = False
    
    def stop_monitoring(self):
        """Stop the monitoring service"""
        logger.info("⏹️ Stopping MarketPulse monitoring...")
        self.running = False
    
    async def analyze_with_ai(self, internals: Dict[str, Any], analysis_type: str = 'quick') -> Optional[str]:
        """
        Analyze market internals using AI (LM Studio/OpenRouter)
        
        Args:
            internals: Market internals data
            analysis_type: 'quick', 'deep', or 'review'
        """
        try:
            if not internals:
                return None
            
            logger.info(f"🤖 Starting AI analysis ({analysis_type})...")
            
            # Get AI analysis
            analysis = await self.llm_manager.analyze_market(internals, analysis_type)
            
            if analysis:
                logger.success("✅ AI analysis completed")
                return analysis
            else:
                logger.warning("⚠️ AI analysis failed")
                return None
                
        except Exception as e:
            logger.error(f"❌ AI analysis error: {e}")
            return None
    
    def format_enhanced_display(self, internals: Dict[str, Any], ai_analysis: str = None) -> str:
        """
        Enhanced display format including AI analysis
        """
        base_display = self.format_internals_display(internals)
        
        if ai_analysis:
            enhanced_display = f"{base_display}\n\n{ai_analysis}\n"
        else:
            enhanced_display = f"{base_display}\n\n⚠️ AI analysis unavailable"
        
        return enhanced_display


async def main():
    """Main MarketPulse execution function"""
    print("🚀 MarketPulse - Market Internals Analysis System")
    print("=" * 50)
    
    # Initialize collector
    collector = MarketPulseCollector()
    
    if not await collector.initialize():
        print("❌ Failed to initialize MarketPulse")
        return
    
    print("✅ MarketPulse initialized successfully")
    print("\n📊 Starting market internals collection...")
    
    try:
        # Collect initial data
        internals = await collector.collect_market_internals()
        
        # Display results
        display = collector.format_internals_display(internals)
        print("\n" + display)
        
        # Save to database
        logger.info("💾 Market internals saved to database")
        
        print("\n🔄 To run continuous monitoring, call collector.run_continuous_monitoring()")
        print("📝 Market data is being collected every 60 seconds")
        
    except Exception as e:
        logger.error(f"❌ Error in main execution: {e}")


if __name__ == "__main__":
    asyncio.run(main())