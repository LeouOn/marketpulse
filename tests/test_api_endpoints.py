from fastapi import FastAPI
from pydantic import BaseModel
from typing import Dict, Any
import sys
import asyncio
from datetime import datetime

sys.path.append('.')
from src.data.market_collector import MarketPulseCollector

# Create a minimal FastAPI app for testing
app = FastAPI(title="MarketPulse Test API")

class DataSourceRequest(BaseModel):
    symbols: list = ["SPY", "QQQ", "AAPL", "BTC-USD"]

@app.put("/test/data-source")
async def test_data_source(request: DataSourceRequest):
    """Test data source connectivity with specified symbols"""
    try:
        print(f"Testing data source with symbols: {request.symbols}")

        # Create fresh collector
        collector = MarketPulseCollector()
        await collector.initialize()

        # Collect market data
        internals = await collector.collect_market_internals()

        # Analyze results
        analysis = {
            "success": True,
            "data_source": internals.get("data_source", "unknown"),
            "total_symbols": len(internals),
            "market_data": {},
            "sample_data": {},
            "timestamp": datetime.now().isoformat()
        }

        # Check for valid price data
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

        # Add sample of raw data
        sample_keys = list(internals.keys())[:3]
        for key in sample_keys:
            analysis["sample_data"][key] = str(internals[key])[:200]  # First 200 chars

        return analysis

    except Exception as e:
        print(f"Error in data source test: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

@app.put("/test/yahoo-direct")
async def test_yahoo_direct():
    """Test Yahoo Finance client directly"""
    try:
        from src.api.yahoo_client import YahooFinanceClient
        from src.core.config import get_settings

        settings = get_settings()
        client = YahooFinanceClient(settings)

        test_symbols = ["SPY", "QQQ", "AAPL"]
        results = {}

        for symbol in test_symbols:
            try:
                print(f"Testing {symbol}...")
                data = client.get_market_data([symbol])
                if symbol in data:
                    results[symbol] = {
                        "success": True,
                        "price": data[symbol].get("price"),
                        "change": data[symbol].get("change"),
                        "change_pct": data[symbol].get("change_pct"),
                        "volume": data[symbol].get("volume"),
                        "raw_keys": list(data[symbol].keys())
                    }
                else:
                    results[symbol] = {"success": False, "error": "Symbol not found in response"}
            except Exception as e:
                results[symbol] = {"success": False, "error": str(e)}

        return {
            "success": True,
            "yahoo_finance_results": results,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        print(f"Error in Yahoo Finance test: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001, reload=False)