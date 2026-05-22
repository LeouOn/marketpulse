"""Data quality endpoints"""

from datetime import datetime

from fastapi import APIRouter
from loguru import logger

from .deps import MarketResponse, success_response, error_response, settings

router = APIRouter(prefix="/api/market/data-quality", tags=["data-quality"])


@router.get("", response_model=MarketResponse)
async def get_data_quality_summary():
    """Return a summary of data availability"""
    try:
        from src.api.yahoo_client import YahooFinanceClient

        client = YahooFinanceClient(settings)

        cache_status = "redis_unavailable"
        cache = await client._get_cache()
        if cache:
            cache_status = "redis_connected"

        return success_response({
            "timestamp": datetime.now().isoformat(),
            "cache_status": cache_status,
            "scheduler_running": True,
        })

    except Exception as e:
        logger.error(f"Error fetching data quality summary: {e}")
        return error_response(str(e))


@router.get("/{symbol}", response_model=MarketResponse)
async def get_symbol_data_quality(symbol: str):
    """Per-symbol data quality check"""
    try:
        from src.api.yahoo_client import YahooFinanceClient

        client = YahooFinanceClient(settings)
        yahoo_symbol = client.macro_symbols.get(symbol.upper(), symbol)

        data = client.get_single_symbol_data(yahoo_symbol)

        return success_response({
            "symbol": symbol,
            "has_data": data is not None,
            "last_fetch": datetime.now().isoformat(),
            "source": "yahoo",
            "data": data,
        })

    except Exception as e:
        logger.error(f"Error checking data quality for {symbol}: {e}")
        return error_response(str(e))
