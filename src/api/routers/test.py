"""Test and debug endpoints"""

from datetime import datetime
from loguru import logger
from fastapi import APIRouter
from typing import Dict, Any

from .deps import (
    settings, MarketPulseCollector, collector, ohlc_analyzer,
    MarketResponse,
)

router = APIRouter(prefix="/api/test", tags=["test"])


@router.get("/status")
async def test_status():
    """Test endpoint to check global variables"""
    from .deps import collector, ohlc_analyzer
    return {
        "collector_status": collector is not None,
        "collector_type": str(type(collector)) if collector else None,
        "ohlc_analyzer_status": ohlc_analyzer is not None,
        "timestamp": datetime.now().isoformat()
    }


@router.put("/data-source")
async def test_data_source(request: Dict[str, Any]):
    """Test data source connectivity with specified symbols"""
    try:
        logger.info(f"Testing data source with request: {request}")

        test_collector = MarketPulseCollector()
        await test_collector.initialize()

        internals = await test_collector.collect_market_internals()

        analysis = {
            "success": True,
            "data_source": internals.get("data_source", "unknown"),
            "total_symbols": len(internals),
            "market_data": {},
            "sample_data": {},
            "timestamp": datetime.now().isoformat()
        }

        valid_symbols = []
        for symbol, data in internals.items():
            if isinstance(data, dict) and data.get("price", 0) > 0:
                valid_symbols.append(symbol)
                analysis["market_data"][symbol] = {
                    "price": data["price"],
                    "change": data.get("change", 0),
                    "change_pct": data.get("change_pct", 0),
                    "volume": data.get("volume", 0)
                }

        analysis["valid_symbols"] = valid_symbols
        analysis["symbols_with_prices"] = len(valid_symbols)

        sample_keys = list(internals.keys())[:3]
        for key in sample_keys:
            analysis["sample_data"][key] = str(internals[key])[:200]

        logger.info(f"Data source test successful: {len(valid_symbols)} symbols with valid prices")
        return analysis

    except Exception as e:
        logger.error(f"Error in data source test: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@router.put("/yahoo-finance")
async def test_yahoo_finance():
    """Test Yahoo Finance client directly"""
    try:
        logger.info("Testing Yahoo Finance client directly...")

        test_collector = MarketPulseCollector()
        await test_collector.initialize()

        internals = await test_collector.collect_market_internals()

        test_symbols = ["SPY", "QQQ", "AAPL", "BTC-USD", "ETH-USD"]
        results = {}

        for symbol in test_symbols:
            if symbol in internals and isinstance(internals[symbol], dict):
                data = internals[symbol]
                results[symbol] = {
                    "success": True,
                    "price": data.get("price"),
                    "change": data.get("change"),
                    "change_pct": data.get("change_pct"),
                    "volume": data.get("volume"),
                    "timestamp": data.get("timestamp"),
                    "raw_keys": list(data.keys())
                }
            else:
                results[symbol] = {"success": False, "error": "Symbol not found in response"}

        logger.info(f"Yahoo Finance test completed for {len(results)} symbols")
        return {
            "success": True,
            "yahoo_finance_results": results,
            "data_source": internals.get("data_source", "unknown"),
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error in Yahoo Finance test: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }
