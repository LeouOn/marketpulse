"""Screener data endpoints"""


from fastapi import APIRouter
from loguru import logger

from .deps import MarketResponse, error_response, settings, success_response

router = APIRouter(prefix="/api/market/screeners", tags=["screeners"])


@router.get("/{screener_type}", response_model=MarketResponse)
async def get_screener_data(screener_type: str):
    """Get screener data (gainers, losers, most_active)"""
    valid_types = ["gainers", "losers", "most_active"]
    if screener_type not in valid_types:
        return error_response(f"Invalid screener type: {screener_type}. Valid: {valid_types}")

    try:
        from src.api.yahoo_client import YahooFinanceClient

        client = YahooFinanceClient(settings)

        cache = await client._get_cache()
        if cache:
            cached = await cache.get(f"screener:{screener_type}")
            if cached:
                return success_response({"screener_type": screener_type, "results": cached})

        results = client.get_screener_data(screener_type)

        if cache and results:
            await cache.set(f"screener:{screener_type}", results, 300)

        return success_response({"screener_type": screener_type, "results": results})

    except Exception as e:
        logger.error(f"Error fetching screener data ({screener_type}): {e}")
        return error_response(str(e))


@router.get("/{screener_type}/history", response_model=MarketResponse)
async def get_screener_history(screener_type: str):
    """Get historical screener data (placeholder)"""
    valid_types = ["gainers", "losers", "most_active"]
    if screener_type not in valid_types:
        return error_response(f"Invalid screener type: {screener_type}. Valid: {valid_types}")

    try:
        from src.api.yahoo_client import YahooFinanceClient

        client = YahooFinanceClient(settings)

        cache = await client._get_cache()
        latest = None
        if cache:
            latest = await cache.get(f"screener:{screener_type}")

        return success_response({
            "screener_type": screener_type,
            "message": "Historical data coming soon",
            "latest": latest,
        })

    except Exception as e:
        logger.error(f"Error fetching screener history ({screener_type}): {e}")
        return error_response(str(e))
