#!/usr/bin/env python3
"""
MarketPulse - Main Entry Point
Real-time market internals analysis system
"""

import asyncio
import argparse
import sys
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.data.market_collector import MarketPulseCollector
from loguru import logger


def setup_logging():
    """Configure logging for MarketPulse"""
    logger.remove()  # Remove default handler
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <level>{message}</level>",
        level="INFO"
    )


async def collect_once():
    """Collect market internals once and display"""
    setup_logging()
    logger.info("MarketPulse - Single Collection Mode")
    
    try:
        collector = MarketPulseCollector()
        
        if not await collector.initialize():
            logger.error("Failed to initialize MarketPulse")
            return False
        
        # Collect data
        logger.info("Collecting market internals...")
        internals = await collector.collect_market_internals()
        
        # Display results
        display = collector.format_internals_display(internals)
        print("\n" + display)
        
        logger.success("Collection completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Error: {e}")
        return False


async def monitor_continuous():
    """Run continuous market monitoring"""
    setup_logging()
    logger.info("MarketPulse - Continuous Monitoring Mode")
    
    try:
        collector = MarketPulseCollector()
        
        if not await collector.initialize():
            logger.error("Failed to initialize MarketPulse")
            return False
        
        logger.info("Starting continuous monitoring (Ctrl+C to stop)")
        await collector.run_continuous_monitoring()
        
    except KeyboardInterrupt:
        logger.info("Monitoring stopped by user")
    except Exception as e:
        logger.error(f"Error: {e}")

async def get_trading_dashboard(self):
    """
    Simplified view for active trading
    Returns only the essentials - no clutter
    """
    internals = await self.collect_market_internals()
    
    dashboard = {
        'timestamp': internals['timestamp'],
        'nq_price': internals['nq']['price'],
        'nq_change': internals['nq']['change_pct'],
        
        # Critical internals only
        'tick': internals.get('tick', 'N/A'),
        'tick_signal': self._interpret_tick(internals.get('tick')),
        'vold': internals.get('vold', 'N/A'),
        'vold_signal': self._interpret_vold(internals.get('vold')),
        'vix': internals.get('vix', 'N/A'),
        'vix_regime': self._interpret_vix(internals.get('vix')),
        
        # Your ATR for stop loss calculation
        'nq_atr_5m': self._calculate_atr(internals['nq'], period=14),
        'suggested_stop': self._calculate_stop_loss(internals['nq']),
    }
    
    return dashboard

def _interpret_tick(self, tick_value):
    """Simple TICK interpretation"""
    if tick_value > 800:
        return "EXTREME_BULLISH"
    elif tick_value > 400:
        return "BULLISH"
    elif tick_value < -800:
        return "EXTREME_BEARISH"
    elif tick_value < -400:
        return "BEARISH"
    else:
        return "NEUTRAL"

def _calculate_stop_loss(self, nq_data):
    """Calculate ATR-based stop loss"""
    atr = self._calculate_atr(nq_data, period=14)
    
    # For scalps: 1.5x ATR, min 20, max 60
    scalp_stop = max(20, min(60, int(atr * 1.5)))
    
    # For breakouts: 2.0x ATR, min 40, max 100
    breakout_stop = max(40, min(100, int(atr * 2.0)))
    
    return {
        'scalp': scalp_stop,
        'breakout': breakout_stop,
        'current_atr': round(atr, 2)
    }

async def generate_morning_prep(self):
    """
    Generate morning trading prep report
    Run this before 9:30am ET
    """
    internals = await self.collect_market_internals()
    
    stop = self._calculate_stop_loss(internals['nq'])
    
    prep_report = f"""
    MORNING PREP - {internals['timestamp']}
    {'='*50}
    
    NQ OVERNIGHT:
    - Current: {internals['nq']['price']}
    - Change: {internals['nq']['change_pct']}%
    - Range: {internals['nq'].get('overnight_high', 'N/A')} - {internals['nq'].get('overnight_low', 'N/A')}
    
    VOLATILITY REGIME:
    - VIX: {internals.get('vix', 'N/A')} → {self._interpret_vix(internals.get('vix'))}
    - ATR (5m): {self._calculate_atr(internals['nq'])}
    - Suggested Stops: Scalp={stop['scalp']}pts, Breakout={stop['breakout']}pts
    
    MARKET BREADTH:
    - TICK: {internals.get('tick', 'N/A')} ({self._interpret_tick(internals.get('tick'))})
    - VOLD: {internals.get('vold', 'N/A')}
    - ADD: {internals.get('add', 'N/A')}
    
    TRADING BIAS:
    {self._generate_bias(internals)}
    
    LEVELS TO WATCH:
    {self._generate_key_levels(internals)}
    """
    
    return prep_report

def get_stop_loss_for_entry(entry_price, trade_type='scalp', manual_atr=None):
    """
    Quick stop loss calculator
    
    Args:
        entry_price: Your entry price
        trade_type: 'scalp', 'breakout', or 'range'
        manual_atr: Optional manual ATR override
    
    Returns:
        stop_loss_price and point_risk
    """
    if manual_atr:
        atr = manual_atr
    else:
        # Fetch latest ATR from your data
        atr = fetch_latest_atr()  # You'll implement this
    
    multipliers = {
        'scalp': 1.5,
        'breakout': 2.0,
        'range': 1.0
    }
    
    stop_distance = atr * multipliers[trade_type]
    stop_distance = max(20, min(100, stop_distance))  # Your bounds
    
    return {
        'stop_price': entry_price - stop_distance,
        'point_risk': stop_distance,
        'dollar_risk_per_mnq': stop_distance * 2,  # $2/point
        'dollar_risk_4mnq': stop_distance * 8
    }

# Use Case 1: Journal Analysis (Daily)
async def analyze_trading_day(trades_data, internals_data):
    """
    Use LLM to analyze your trading day
    Run this AFTER market close
    """
    
    prompt = f"""
    Analyze this trading day for an NQ futures trader:
    
    TRADES:
    {format_trades(trades_data)}
    
    MARKET INTERNALS:
    {format_internals(internals_data)}
    
    Provide analysis on:
    1. Were entries aligned with market conditions?
    2. Did exits leave money on the table or protect capital appropriately?
    3. Were there patterns in winning vs losing trades?
    4. Suggestions for tomorrow
    
    Be concise and actionable.
    """
    
    analysis = await call_lm_studio(prompt, model="qwen3-30b")
    return analysis
# Use Case 2: Pattern Recognition Assistant (Weekly)
async def identify_edge_patterns(week_of_trades):
    """
    Use LLM to spot patterns in your winning trades
    Run this weekly
    """
    
    prompt = f"""
    Review this week of NQ trades:
    
    {format_week_data(week_of_trades)}
    
    Identify:
    1. Common characteristics of winning trades
    2. Common characteristics of losing trades
    3. Patterns I might be missing
    4. Are there certain market conditions where I perform best?
    
    Help me refine my edge.
    """
    
    insights = await call_lm_studio(prompt, model="glm-4.5-air")
    return insights
# Use Case 3: Real-Time Bias Check (Morning)
async def get_market_bias_llm(internals, news_headlines):
    """
    Use LLM for morning market bias
    But still trade YOUR system - this is context only
    """
    
    prompt = f"""
    Market internals for NQ trading:
    {format_internals_concise(internals)}
    
    Recent headlines:
    {format_headlines(news_headlines)}
    
    In 3 sentences or less:
    - Overall market bias (bullish/bearish/neutral)
    - Key risk factors today
    - Trading approach suggestion
    """
    
    bias = await call_lm_studio(prompt, model="qwen3-30b")
    return bias
def main():
    """Main MarketPulse entry point"""
    parser = argparse.ArgumentParser(description="MarketPulse - Market Internals Analysis")
    parser.add_argument(
        "--mode", 
        choices=["collect", "monitor"], 
        default="collect",
        help="Mode: 'collect' for single collection, 'monitor' for continuous monitoring"
    )
    
    args = parser.parse_args()
    
    print("MarketPulse - Market Internals Analysis System")
    print("=" * 55)
    print("Analyzing NQ, BTC, ETH market internals")
    print("Powered by Alpaca API + LM Studio")
    print("=" * 55)
    
    if args.mode == "collect":
        print("\nRunning single collection...\n")
        success = asyncio.run(collect_once())
    else:
        print("\nStarting continuous monitoring...\n")
        asyncio.run(monitor_continuous())
        success = True
    
    if success:
        print("\nMarketPulse completed successfully!")
    else:
        print("\nMarketPulse encountered errors")
        sys.exit(1)


if __name__ == "__main__":
    main()