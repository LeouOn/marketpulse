"""Mock Market Data Provider for Testing
Bootstraps base prices from Yahoo Finance when available,
falls back to static defaults only if Yahoo is unreachable.
Adds realistic variance around real prices with bounded drift.

Fabricated fields are labelled ``source: mock``. Callers must omit them
unless ``MARKETPULSE_ALLOW_MOCK`` is set (see ``allow_mock``).
"""

import os
import random
from datetime import datetime
from typing import Any

from loguru import logger

# Realistic price bounds for mean reversion
PRICE_BOUNDS = {
    "SPY": (350, 550),  # Mean: 450, bounds: 350-550
    "QQQ": (300, 480),  # Mean: 390, bounds: 300-480
    "VIX": (10, 60),  # Mean: 20, bounds: 10-60 (can't be negative, rarely above 60 in mock
    "IWM": (180, 280),  # Mean: 230, bounds: 180-280
    "DIA": (350, 450),  # Mean: 400, bounds: 350-450
    "AAPL": (150, 250),  # Mean: 200, bounds: 150-250
    "TSLA": (150, 400),  # Mean: 275, bounds: 150-400
    "NVDA": (400, 800),  # Mean: 600, bounds: 400-800
}

FALLBACK_PRICES = {
    "SPY": 450.0,
    "QQQ": 390.0,
    "VIX": 20.0,
    "IWM": 230.0,
    "DIA": 400.0,
    "AAPL": 200.0,
    "TSLA": 275.0,
    "NVDA": 600.0,
}

# Last-resort levels for every MACRO_CATALOG key. Used only when Yahoo is
# unreachable and the caller has opted into mock data. Not live quotes.
FALLBACK_MACRO = {
    "DXY": 101.0,
    "TNX": 4.5,
    "CL": 70.0,
    "GC": 3300.0,
    "BTC": 94000.0,
    "ETH": 1800.0,
    "SOL": 150.0,
    "XRP": 0.5,
    "NIKKEI": 38000.0,
    "HSI": 18000.0,
    "SSE": 3200.0,
    "ASX": 8000.0,
    "FTSE": 8300.0,
    "DAX": 18000.0,
    "CAC": 7500.0,
    "STOXX": 4900.0,
    "EURUSD": 1.08,
    "GBPUSD": 1.27,
    "USDJPY": 150.0,
    "AUDUSD": 0.66,
    "USDCAD": 1.36,
    "USDCHF": 0.88,
}


def allow_mock() -> bool:
    """True when fabricated series may be returned. Matches market_data_collector."""
    return os.getenv("MARKETPULSE_ALLOW_MOCK", "").lower() in ("1", "true", "yes")


def local_market_session(now: datetime | None = None) -> str:
    """Coarse session label from the server's local hour. Not an exchange calendar."""
    hour = (now or datetime.now()).hour
    if 9 <= hour < 16:
        return "US Regular"
    if 16 <= hour < 20:
        return "US After Hours"
    if hour >= 20 or hour < 4:
        return "Asian Session"
    return "European Session"


def macro_yahoo_map() -> dict[str, str]:
    """Key -> Yahoo symbol. Same dict YahooFinanceClient.macro_symbols is built from."""
    from src.api.yahoo_client import MACRO_CATALOG

    return {name: meta["symbol"] for name, meta in MACRO_CATALOG.items()}


# Maximum allowed single-day change percentage
MAX_CHANGE_PCT = 5.0  # 5% max daily change in mock data


def _bootstrap_from_yahoo():
    """Try to pull current prices from Yahoo Finance to use as mock base."""
    try:
        import yfinance as yf

        symbols = {
            "SPY": "SPY",
            "QQQ": "QQQ",
            "VIX": "^VIX",
            "IWM": "IWM",
            "DIA": "DIA",
            "AAPL": "AAPL",
            "TSLA": "TSLA",
            "NVDA": "NVDA",
        }
        macro_map = macro_yahoo_map()
        all_yahoo = {**symbols, **macro_map}
        ticker_list = list(all_yahoo.values())
        data = yf.download(ticker_list, period="1d", interval="1d", progress=False, auto_adjust=False)
        if data.empty or "Close" not in data:
            return dict(FALLBACK_PRICES), dict(FALLBACK_MACRO)

        prices = {}
        for name, ysym in symbols.items():
            try:
                if ysym in data["Close"].columns:
                    val = data["Close"][ysym].dropna().iloc[-1]
                    prices[name] = float(val)
            except Exception:
                pass

        macro = {}
        for name, ysym in macro_map.items():
            try:
                if ysym in data["Close"].columns:
                    val = data["Close"][ysym].dropna().iloc[-1]
                    macro[name] = float(val)
            except Exception:
                pass

        if prices:
            logger.info(f"Bootstrapped mock base prices from Yahoo: {list(prices.keys())}")
        merged_macro = dict(FALLBACK_MACRO)
        merged_macro.update(macro)
        return prices or FALLBACK_PRICES, merged_macro
    except Exception as e:
        logger.warning(f"Could not bootstrap from Yahoo, using static defaults: {e}")
        return FALLBACK_PRICES, dict(FALLBACK_MACRO)


class MockMarketDataProvider:
    """Provides realistic mock market data based on live base prices"""

    def __init__(self):
        self.base_prices, self.macro_base = _bootstrap_from_yahoo()
        self.last_update = datetime.now()
        self.trend_direction = {}

    async def get_market_internals(self) -> dict[str, Any]:
        """Get mock market internals with synthetic flag"""
        now = datetime.now()
        self._update_trends()
        internals = {}

        for symbol, base_price in self.base_prices.items():
            price_change = self._generate_price_change(symbol, base_price)
            internals[symbol.lower()] = {
                "price": price_change["price"],
                "change": price_change["change"],
                "change_pct": price_change["change_pct"],
                "volume": self._generate_volume(symbol),
                "timestamp": now.isoformat(),
            }

        total_volume = sum(
            internals[sym.lower()]["volume"] for sym in ["SPY", "QQQ", "IWM"] if sym.lower() in internals
        )
        internals["volume_flow"] = {"total_volume_60min": total_volume, "symbols_tracked": len(self.base_prices)}
        # Mark as synthetic so validation can catch it
        internals["synthetic"] = True
        internals["data_source"] = "mock"
        return internals

    async def get_macro_data(self) -> dict[str, Any]:
        """Fabricated macro payload. Every series is tagged source=mock.

        The market router must not serve this unless ``allow_mock()`` is true.
        """
        from src.api.yahoo_client import MACRO_CATALOG

        now = datetime.now()
        macro_data = {}

        for symbol, base_value in self.macro_base.items():
            change = self._generate_macro_change(symbol, base_value)
            meta = MACRO_CATALOG.get(symbol, {})
            macro_data[symbol] = {
                "price": change["price"],
                "change": change["change"],
                "change_pct": change["change_pct"],
                "timestamp": now.isoformat(),
                "symbol": meta.get("symbol", symbol),
                "instrument": meta.get("instrument", symbol),
                "is_proxy": bool(meta.get("is_proxy", False)),
                "source": "mock",
            }

        macro_data.update(
            {
                "market_session": local_market_session(now),
                "market_session_basis": "local_clock",
                "economic_sentiment": self._get_sentiment_indicator(),
                "sector_performance": self._get_sector_performance(),
                "risk_appetite": self._get_risk_appetite(),
                "source": "mock",
                "field_sources": {
                    "market_session": "derived",
                    "economic_sentiment": "mock",
                    "sector_performance": "mock",
                    "risk_appetite": "mock",
                },
            }
        )
        return macro_data

    def _update_trends(self):
        if random.random() < 0.1:
            for symbol in list(self.base_prices.keys()):
                if random.random() < 0.3:
                    self.trend_direction[symbol] = random.choice(["up", "down", "sideways"])

    def _generate_price_change(self, symbol: str, base_price: float) -> dict[str, float]:
        """Generate price with bounded drift and mean reversion"""
        trend = self.trend_direction.get(symbol, "sideways")
        volatility = 0.03 if symbol == "VIX" else 0.025 if symbol in ["TSLA", "NVDA"] else 0.008
        bias = 0.3 if trend == "up" else -0.3 if trend == "down" else 0.0
        change_pct = random.gauss(bias, 1) * volatility

        # Clamp change to MAX_CHANGE_PCT
        change_pct = max(-MAX_CHANGE_PCT, min(MAX_CHANGE_PCT, change_pct))

        change = base_price * (change_pct / 100)
        new_price = base_price + change

        # Apply mean reversion toward the midpoint of our bounds
        if symbol in PRICE_BOUNDS:
            min_price, max_price = PRICE_BOUNDS[symbol]
            midpoint = (min_price + max_price) / 2
            # If we're outside bounds, force toward midpoint
            if new_price < min_price:
                new_price = min_price
            elif new_price > max_price:
                new_price = max_price
            else:
                # Mean reversion: pull 10% back toward midpoint
                new_price = new_price * 0.9 + midpoint * 0.1

        self.base_prices[symbol] = new_price
        return {"price": new_price, "change": change, "change_pct": change_pct}

    def _generate_volume(self, symbol: str) -> int:
        """Generate realistic volume within bounds"""
        base_volumes = {
            "SPY": 45_000_000,
            "QQQ": 32_000_000,
            "VIX": 0,
            "IWM": 28_000_000,
            "DIA": 18_000_000,
            "AAPL": 55_000_000,
            "TSLA": 95_000_000,
            "NVDA": 42_000_000,
        }
        base = base_volumes.get(symbol, 20_000_000)
        if base == 0:
            return 0
        # Keep volume within 0.5x to 1.5x of base (more conservative than before)
        return int(base * random.uniform(0.5, 1.5))

    def _generate_macro_change(self, symbol: str, base_value: float) -> dict[str, float]:
        volatilities = {"DXY": 0.005, "TNX": 0.02, "CL": 0.025, "GC": 0.008, "BTC": 0.04, "ETH": 0.045}
        volatility = volatilities.get(symbol, 0.01)
        change_pct = random.gauss(0, 1) * volatility
        change = base_value * change_pct
        new_price = base_value + change
        self.macro_base[symbol] = new_price
        return {"price": new_price, "change": change, "change_pct": change_pct * 100}

    def _get_market_session(self) -> str:
        return local_market_session()

    def _get_sentiment_indicator(self) -> str:
        s = random.gauss(0, 1)
        if s > 1:
            return "Very Bullish"
        if s > 0.5:
            return "Bullish"
        if s > -0.5:
            return "Neutral"
        if s > -1:
            return "Bearish"
        return "Very Bearish"

    def _get_sector_performance(self) -> dict[str, float]:
        return {
            "Technology": round(random.gauss(0.5, 1.2), 2),
            "Healthcare": round(random.gauss(0.2, 0.8), 2),
            "Financials": round(random.gauss(0.1, 1.0), 2),
            "Energy": round(random.gauss(-0.2, 1.5), 2),
            "Consumer Discretionary": round(random.gauss(0.3, 1.1), 2),
            "Industrials": round(random.gauss(0.0, 0.9), 2),
            "Materials": round(random.gauss(-0.1, 1.0), 2),
            "Utilities": round(random.gauss(-0.3, 0.7), 2),
            "Real Estate": round(random.gauss(-0.2, 0.8), 2),
            "Communication Services": round(random.gauss(0.4, 1.3), 2),
        }

    def _get_risk_appetite(self) -> str:
        spy_pct = (self.base_prices.get("SPY", 580) - FALLBACK_PRICES["SPY"]) / FALLBACK_PRICES["SPY"]
        vix_diff = self.base_prices.get("VIX", 18.5) - FALLBACK_PRICES["VIX"]
        score = spy_pct - (vix_diff / 18.5)
        if score > 0.02:
            return "Risk On"
        if score < -0.02:
            return "Risk Off"
        return "Balanced"


mock_provider = MockMarketDataProvider()
