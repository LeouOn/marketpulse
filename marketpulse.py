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
    logger.info("🚀 MarketPulse - Single Collection Mode")
    
    try:
        collector = MarketPulseCollector()
        
        if not await collector.initialize():
            logger.error("❌ Failed to initialize MarketPulse")
            return False
        
        # Collect data
        logger.info("📊 Collecting market internals...")
        internals = await collector.collect_market_internals()
        
        # Display results
        display = collector.format_internals_display(internals)
        print("\n" + display)
        
        logger.success("✅ Collection completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        return False


async def monitor_continuous():
    """Run continuous market monitoring"""
    setup_logging()
    logger.info("🔄 MarketPulse - Continuous Monitoring Mode")
    
    try:
        collector = MarketPulseCollector()
        
        if not await collector.initialize():
            logger.error("❌ Failed to initialize MarketPulse")
            return False
        
        logger.info("⏰ Starting continuous monitoring (Ctrl+C to stop)")
        await collector.run_continuous_monitoring()
        
    except KeyboardInterrupt:
        logger.info("⏹️ Monitoring stopped by user")
    except Exception as e:
        logger.error(f"❌ Error: {e}")


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
    
    print("🚀 MarketPulse - Market Internals Analysis System")
    print("=" * 55)
    print("📈 Analyzing NQ, BTC, ETH market internals")
    print("🤖 Powered by Alpaca API + LM Studio")
    print("=" * 55)
    
    if args.mode == "collect":
        print("\n📊 Running single collection...\n")
        success = asyncio.run(collect_once())
    else:
        print("\n🔄 Starting continuous monitoring...\n")
        asyncio.run(monitor_continuous())
        success = True
    
    if success:
        print("\n✅ MarketPulse completed successfully!")
    else:
        print("\n❌ MarketPulse encountered errors")
        sys.exit(1)


if __name__ == "__main__":
    main()