"""Symbol detail and search endpoints"""

from datetime import datetime

from fastapi import APIRouter, Query
from loguru import logger

from .deps import MarketResponse, error_response, settings, success_response

router = APIRouter(prefix="/api/market/symbols", tags=["symbols"])


def _classify_asset_type(yahoo_sym: str) -> str:
    """Bucket a macro symbol by its Yahoo suffix (shared by list and search).

    Search previously hard-coded ``"other"`` for macro matches, so the same
    symbol showed a different ``asset_type`` depending on the endpoint.
    """
    if yahoo_sym.endswith("-USD"):
        return "crypto"
    if yahoo_sym.startswith("^"):
        return "index"
    if yahoo_sym.endswith("=X"):
        return "forex"
    if yahoo_sym.endswith("=F"):
        return "futures"
    return "etf"


@router.get("", response_model=MarketResponse)
async def list_symbols():
    """Return list of all tracked symbols"""
    try:
        from src.api.yahoo_client import YahooFinanceClient

        client = YahooFinanceClient(settings)
        symbols = []

        for sym in client.market_symbols:
            symbols.append(
                {
                    "symbol": sym,
                    "name": sym,
                    "asset_type": "equity",
                    "yahoo_symbol": sym,
                }
            )

        for name, yahoo_sym in client.macro_symbols.items():
            symbols.append(
                {
                    "symbol": name,
                    "name": name,
                    "asset_type": _classify_asset_type(yahoo_sym),
                    "yahoo_symbol": yahoo_sym,
                }
            )

        return success_response({"symbols": symbols, "total": len(symbols)})

    except Exception as e:
        logger.error(f"Error listing symbols: {e}")
        return error_response(str(e))


@router.get("/search", response_model=MarketResponse)
async def search_symbols(q: str = Query(..., min_length=1)):
    """Search through known symbols"""
    try:
        from src.api.yahoo_client import YahooFinanceClient

        client = YahooFinanceClient(settings)
        # A whitespace-only query used to fall through as a substring that
        # matches nothing, silently returning an empty result.
        query = q.strip().upper()
        if not query:
            return error_response("query must contain at least one non-whitespace character")
        matches = []

        for sym in client.market_symbols:
            if query in sym.upper():
                matches.append(
                    {
                        "symbol": sym,
                        "name": sym,
                        "asset_type": "equity",
                        "yahoo_symbol": sym,
                    }
                )

        for name, yahoo_sym in client.macro_symbols.items():
            if query in name.upper() or query in yahoo_sym.upper():
                matches.append(
                    {
                        "symbol": name,
                        "name": name,
                        "asset_type": _classify_asset_type(yahoo_sym),
                        "yahoo_symbol": yahoo_sym,
                    }
                )

        return success_response({"query": q, "results": matches[:10]})

    except Exception as e:
        logger.error(f"Error searching symbols: {e}")
        return error_response(str(e))


@router.get("/{symbol}", response_model=MarketResponse)
async def get_symbol_profile(symbol: str):
    """Get full profile for a symbol"""
    try:
        from src.api.yahoo_client import YahooFinanceClient

        client = YahooFinanceClient(settings)
        yahoo_symbol = client.macro_symbols.get(symbol.upper(), symbol)

        info = client.get_symbol_info(yahoo_symbol)
        range_data = client.get_52w_range(yahoo_symbol)
        price_data = client.get_single_symbol_data(yahoo_symbol)

        profile = {
            "symbol": symbol,
            "yahoo_symbol": yahoo_symbol,
            "info": info,
            "range_52w": range_data,
            "current_price": price_data,
            "timestamp": datetime.now().isoformat(),
        }

        return success_response(profile)

    except Exception as e:
        logger.error(f"Error fetching profile for {symbol}: {e}")
        return error_response(str(e))


@router.get("/{symbol}/stats", response_model=MarketResponse)
async def get_symbol_stats(symbol: str):
    """Get stats for a symbol"""
    try:
        from src.api.yahoo_client import YahooFinanceClient

        client = YahooFinanceClient(settings)
        yahoo_symbol = client.macro_symbols.get(symbol.upper(), symbol)

        range_data = client.get_52w_range(yahoo_symbol)
        if range_data is None:
            return error_response(f"Could not fetch stats for {symbol}")

        # A partial range dict (missing keys) used to surface as a cryptic
        # KeyError ('high_52w'); missing stats degrade to null.
        return success_response(
            {
                "symbol": symbol,
                "high_52w": range_data.get("high_52w"),
                "low_52w": range_data.get("low_52w"),
                "pct_from_high": range_data.get("pct_from_high"),
                "pct_from_low": range_data.get("pct_from_low"),
                "current_price": range_data.get("current_price"),
            }
        )

    except Exception as e:
        logger.error(f"Error fetching stats for {symbol}: {e}")
        return error_response(str(e))


@router.get("/{symbol}/52w-range", response_model=MarketResponse)
async def get_52w_range(symbol: str):
    """Get 52-week range for a symbol"""
    try:
        from src.api.yahoo_client import YahooFinanceClient

        client = YahooFinanceClient(settings)
        yahoo_symbol = client.macro_symbols.get(symbol.upper(), symbol)

        range_data = client.get_52w_range(yahoo_symbol)
        if range_data is None:
            return error_response(f"Could not fetch 52w range for {symbol}")

        return success_response(range_data)

    except Exception as e:
        logger.error(f"Error fetching 52w range for {symbol}: {e}")
        return error_response(str(e))
