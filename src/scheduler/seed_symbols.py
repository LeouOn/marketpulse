from loguru import logger

from src.core.config import get_settings
from src.core.database import DatabaseManager, Symbol

SYMBOLS = [
    ("SPY", "S&P 500 ETF", "etf", "SPY"),
    ("QQQ", "Nasdaq 100 ETF", "etf", "QQQ"),
    ("IWM", "Russell 2000 ETF", "etf", "IWM"),
    ("DIA", "Dow Jones ETF", "etf", "DIA"),
    ("VTI", "Total Stock Market ETF", "etf", "VTI"),
    ("VOO", "S&P 500 Index Fund", "etf", "VOO"),
    ("UUP", "US Dollar Bull ETF", "etf", "UUP"),
    ("GLD", "Gold ETF", "etf", "GLD"),
    ("AAPL", "Apple Inc.", "stock", "AAPL"),
    ("TSLA", "Tesla Inc.", "stock", "TSLA"),
    ("NVDA", "NVIDIA Corporation", "stock", "NVDA"),
    ("^VIX", "CBOE Volatility Index", "index", "^VIX"),
    ("^N225", "Nikkei 225", "index", "^N225"),
    ("^HSI", "Hang Seng Index", "index", "^HSI"),
    ("^AXJO", "ASX 200", "index", "^AXJO"),
    ("^FTSE", "FTSE 100", "index", "^FTSE"),
    ("^GDAXI", "DAX 40", "index", "^GDAXI"),
    ("^FCHI", "CAC 40", "index", "^FCHI"),
    ("^STOXX50E", "Euro Stoxx 50", "index", "^STOXX50E"),
    ("^TNX", "10-Year Treasury Yield", "index", "^TNX"),
    ("NQ=F", "Nasdaq 100 Futures", "future", "NQ=F"),
    ("ES=F", "S&P 500 Futures", "future", "ES=F"),
    ("CL=F", "Crude Oil Futures", "future", "CL=F"),
    ("BTC-USD", "Bitcoin USD", "crypto", "BTC-USD"),
    ("ETH-USD", "Ethereum USD", "crypto", "ETH-USD"),
    ("SOL-USD", "Solana USD", "crypto", "SOL-USD"),
    ("XRP-USD", "XRP USD", "crypto", "XRP-USD"),
    ("EURUSD=X", "EUR/USD", "forex", "EURUSD=X"),
    ("GBPUSD=X", "GBP/USD", "forex", "GBPUSD=X"),
    ("USDJPY=X", "USD/JPY", "forex", "USDJPY=X"),
    ("AUDUSD=X", "AUD/USD", "forex", "AUDUSD=X"),
    ("USDCAD=X", "USD/CAD", "forex", "USDCAD=X"),
    ("USDCHF=X", "USD/CHF", "forex", "USDCHF=X"),
    ("000001.SS", "Shanghai Composite", "index", "000001.SS"),
]


def seed_symbols():
    try:
        settings = get_settings()
        db = DatabaseManager(settings.database_url)
        session = db.get_session()
    except Exception as e:
        logger.error(f"Cannot connect to database for seeding: {e}")
        return
    try:
        for symbol, name, asset_type, yahoo_symbol in SYMBOLS:
            row = Symbol(
                symbol=symbol,
                name=name,
                asset_type=asset_type,
                yahoo_symbol=yahoo_symbol,
            )
            session.merge(row)
        session.commit()
        logger.info(f"Seeded {len(SYMBOLS)} symbols")
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to seed symbols: {e}")
    finally:
        session.close()


if __name__ == "__main__":
    seed_symbols()
