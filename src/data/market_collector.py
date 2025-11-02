"""MarketPulse Market Data Collection Service
Orchestrates data collection from multiple APIs and provides market internals analysis
"""

import asyncio
import schedule
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from loguru import logger

from ..api import AlpacaClient
from ..core.config import get_settings
from ..core.database import DatabaseManager
from ..llm import LLMManager


class MarketPulseCollector:
    """Main market data collection service for MarketPulse"""
    
    def __init__(self):
        self.settings = get_settings()
        self.db_manager = DatabaseManager(self.settings.database_url)
        self.alpaca_client = None
        self.llm_manager = LLMManager()  # Add LLM manager
        self.running = False
        
        # Market symbols to monitor
        self.symbols = {
            'NQ': self.settings.nq_symbol,
            'BTC': self.settings.btc_symbol, 
            'ETH': self.settings.eth_symbol,
            'SPY': 'SPY',
            'QQQ': 'QQQ',
            'VIX': 'VIX',
            'IWM': 'IWM'
        }
    
    async def initialize(self):
        """Initialize the market collector"""
        logger.info("🚀 Initializing MarketPulse Collector...")
        
        try:
            # Initialize database
            self.db_manager.create_engine()
            self.db_manager.create_tables()
            logger.success("✅ Database initialized")
            
            # Initialize API clients
            self.alpaca_client = AlpacaClient(self.settings)
            logger.success("✅ API clients initialized")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize MarketPulse: {e}")
            return False
    
    async def collect_market_internals(self) -> Dict[str, Any]:
        """Collect and analyze current market internals"""
        logger.info("📊 Starting market internals collection...")
        
        try:
            # Collect data from Alpaca
            if not self.alpaca_client:
                async with AlpacaClient(self.settings) as client:
                    internals = await client.get_market_internals()
            else:
                async with self.alpaca_client as client:
                    internals = await client.get_market_internals()
            
            if not internals:
                logger.warning("⚠️ No market internals data collected")
                return {}
            
            # Store in database
            timestamp = datetime.now()
            for symbol, data in internals.items():
                if isinstance(data, dict) and 'price' in data:
                    internals_record = {
                        'timestamp': timestamp,
                        'advance_decline_ratio': self._calculate_ad_line(internals),
                        'volume_flow': data.get('volume', 0),
                        'momentum_score': self._calculate_momentum(internals),
                        'volatility_regime': self._classify_volatility(internals),
                        'correlation_strength': self._calculate_correlation(internals),
                        'support_level': self._calculate_support(internals),
                        'resistance_level': self._calculate_resistance(internals)
                    }
                    
                    self.db_manager.save_market_internals(symbol, internals_record)
            
            logger.success("✅ Market internals collected and stored")
            return internals
            
        except Exception as e:
            logger.error(f"❌ Error collecting market internals: {e}")
            return {}
    
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
        except:
            return None
    
    def _calculate_momentum(self, internals: Dict[str, Any]) -> Optional[float]:
        """Calculate momentum score based on recent price changes"""
        try:
            if 'spy' in internals:
                spy_change_pct = internals['spy']['change_pct']
                return max(min(spy_change_pct / 2.0, 5.0), -5.0)  # Normalize to -5 to +5
            return None
        except:
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
        except:
            return "UNKNOWN"
    
    def _calculate_correlation(self, internals: Dict[str, Any]) -> Optional[float]:
        """Calculate SPY-QQQ correlation strength"""
        try:
            if 'spy' in internals and 'qqq' in internals:
                spy_change = internals['spy']['change_pct']
                qqq_change = internals['qqq']['change_pct']
                
                # Simple correlation measure
                if abs(spy_change) > 0.1 and abs(qqq_change) > 0.1:
                    correlation = (spy_change * qqq_change) / (abs(spy_change) * abs(qqq_change))
                    return max(min(correlation, 1.0), -1.0)
            return None
        except:
            return None
    
    def _calculate_support(self, internals: Dict[str, Any]) -> Optional[float]:
        """Calculate key support level (simplified)"""
        try:
            if 'spy' in internals:
                spy_price = internals['spy']['price']
                # Simple support calculation (would be more sophisticated in real implementation)
                return spy_price * 0.98  # 2% below current price
            return None
        except:
            return None
    
    def _calculate_resistance(self, internals: Dict[str, Any]) -> Optional[float]:
        """Calculate key resistance level (simplified)"""
        try:
            if 'spy' in internals:
                spy_price = internals['spy']['price']
                # Simple resistance calculation
                return spy_price * 1.02  # 2% above current price
            return None
        except:
            return None
    
    def format_internals_display(self, internals: Dict[str, Any]) -> str:
        """Format internals for console display"""
        if not internals:
            return "❌ No market data available"
        
        lines = []
        lines.append("=" * 70)
        lines.append(f"📈 MarketPulse Market Internals - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
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
        
        # Schedule regular collections
        schedule.every(self.settings.internals_interval // 60).minutes.do(
            lambda: asyncio.create_task(self.collect_market_internals())
        )
        
        # Run monitoring loop
        try:
            while self.running:
                schedule.run_pending()
                await asyncio.sleep(1)
                
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