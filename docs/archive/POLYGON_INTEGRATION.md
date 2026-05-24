# Polygon.io Integration Guide

**Complete implementation guide for adding Polygon.io (now Massive.com) to MarketPulse**

---

## 🎯 Why Polygon.io?

**What You Get:**
- ✅ Real-time market data (no 15min delay!)
- ✅ Tick-level data for **true CVD** calculation
- ✅ Futures data (MNQ, ES, NQ directly)
- ✅ WebSocket streaming for live updates
- ✅ 10+ years historical data
- ✅ Professional-grade infrastructure
- ✅ Better rate limits than Yahoo

**Cost**: $99/month (Developer plan) - **Worth every penny for serious trading**

---

## 📦 Step 1: Setup (15 minutes)

### 1.1 Get API Key

1. Go to https://massive.com (formerly polygon.io)
2. Sign up for account
3. Choose **Developer Plan** ($99/mo)
4. Get your API key from dashboard

### 1.2 Install Python Client

```bash
pip install polygon-api-client
```

### 1.3 Add to Environment

Create or edit `.env` file:
```bash
# Polygon.io API (now Massive.com)
POLYGON_API_KEY=your_api_key_here

# Optional: Choose data tier
POLYGON_TIER=developer  # or 'starter', 'advanced'
```

### 1.4 Update requirements.txt

Add to `requirements.txt`:
```
polygon-api-client>=1.13.0
```

---

## 🔧 Step 2: Create Polygon Client (30 minutes)

Create `src/api/polygon_client.py`:

```python
"""
Polygon.io Market Data Client

Provides real-time and historical market data from Polygon.io (Massive.com)
Supports stocks, options, futures, forex, and crypto.
"""

from polygon import RESTClient, WebSocketClient
from polygon.websocket.models import WebSocketMessage, EquityTrade, EquityQuote, EquityAgg
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime, timedelta
from loguru import logger
import os
import asyncio


class PolygonMarketDataClient:
    """
    Polygon.io REST API client for market data

    Provides real-time quotes, historical data, and options/futures support.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Polygon client

        Args:
            api_key: Polygon API key (defaults to env var POLYGON_API_KEY)
        """
        self.api_key = api_key or os.getenv('POLYGON_API_KEY')
        if not self.api_key:
            raise ValueError("POLYGON_API_KEY not found")

        self.client = RESTClient(api_key=self.api_key)
        logger.info("Polygon.io client initialized")

    # ========================================================================
    # REAL-TIME DATA
    # ========================================================================

    def get_last_trade(self, symbol: str) -> Dict[str, Any]:
        """
        Get most recent trade

        Args:
            symbol: Stock/futures symbol (e.g., 'AAPL', 'F:MNQ')

        Returns:
            Dict with price, size, exchange, timestamp
        """
        try:
            trade = self.client.get_last_trade(ticker=symbol)

            return {
                'price': trade.price,
                'size': trade.size,
                'exchange': trade.exchange,
                'timestamp': trade.sip_timestamp
            }

        except Exception as e:
            logger.error(f"Error getting last trade for {symbol}: {e}")
            raise

    def get_last_quote(self, symbol: str) -> Dict[str, Any]:
        """
        Get most recent quote (bid/ask)

        Args:
            symbol: Stock/futures symbol

        Returns:
            Dict with bid, ask, bid_size, ask_size
        """
        try:
            quote = self.client.get_last_quote(ticker=symbol)

            return {
                'bid': quote.bid_price,
                'ask': quote.ask_price,
                'bid_size': quote.bid_size,
                'ask_size': quote.ask_size,
                'timestamp': quote.sip_timestamp
            }

        except Exception as e:
            logger.error(f"Error getting last quote for {symbol}: {e}")
            raise

    # ========================================================================
    # HISTORICAL DATA
    # ========================================================================

    def get_bars(
        self,
        symbol: str,
        timespan: str = 'minute',
        multiplier: int = 1,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        Get historical OHLCV bars

        Args:
            symbol: Stock/futures symbol
            timespan: 'minute', 'hour', 'day', 'week', 'month', 'quarter', 'year'
            multiplier: Size of timespan (e.g., 5 for 5-minute bars)
            from_date: Start date (defaults to 7 days ago)
            to_date: End date (defaults to now)
            limit: Max bars to return

        Returns:
            List of OHLCV bars
        """
        try:
            if from_date is None:
                from_date = datetime.now() - timedelta(days=7)
            if to_date is None:
                to_date = datetime.now()

            aggs = self.client.get_aggs(
                ticker=symbol,
                multiplier=multiplier,
                timespan=timespan,
                from_=from_date.strftime('%Y-%m-%d'),
                to=to_date.strftime('%Y-%m-%d'),
                limit=limit
            )

            bars = []
            for agg in aggs:
                bars.append({
                    'timestamp': datetime.fromtimestamp(agg.timestamp / 1000),
                    'open': agg.open,
                    'high': agg.high,
                    'low': agg.low,
                    'close': agg.close,
                    'volume': agg.volume,
                    'vwap': agg.vwap,
                    'transactions': agg.transactions
                })

            logger.info(f"Retrieved {len(bars)} bars for {symbol}")
            return bars

        except Exception as e:
            logger.error(f"Error getting bars for {symbol}: {e}")
            raise

    def get_trades(
        self,
        symbol: str,
        date: datetime,
        limit: int = 50000
    ) -> List[Dict[str, Any]]:
        """
        Get tick-level trades for true CVD calculation

        Args:
            symbol: Stock/futures symbol
            date: Date to get trades for
            limit: Max trades to return (default 50k)

        Returns:
            List of trades with price, size, timestamp
        """
        try:
            trades_iter = self.client.list_trades(
                ticker=symbol,
                timestamp=date.strftime('%Y-%m-%d'),
                limit=limit
            )

            trades = []
            for trade in trades_iter:
                trades.append({
                    'price': trade.price,
                    'size': trade.size,
                    'exchange': trade.exchange,
                    'timestamp': datetime.fromtimestamp(trade.sip_timestamp / 1000000000),
                    'conditions': trade.conditions
                })

            logger.info(f"Retrieved {len(trades)} trades for {symbol} on {date.date()}")
            return trades

        except Exception as e:
            logger.error(f"Error getting trades for {symbol}: {e}")
            raise

    # ========================================================================
    # FUTURES DATA
    # ========================================================================

    def get_futures_quote(self, symbol: str) -> Dict[str, Any]:
        """
        Get futures quote (MNQ, ES, NQ, etc.)

        Args:
            symbol: Futures symbol WITHOUT prefix (e.g., 'MNQ', not 'F:MNQ')

        Returns:
            Dict with bid, ask, last price
        """
        # Polygon uses 'F:' prefix for futures
        futures_symbol = f"F:{symbol}" if not symbol.startswith('F:') else symbol

        try:
            # Get last trade
            trade = self.get_last_trade(futures_symbol)

            # Get quote
            quote = self.get_last_quote(futures_symbol)

            return {
                'symbol': symbol,
                'last_price': trade['price'],
                'bid': quote['bid'],
                'ask': quote['ask'],
                'bid_size': quote['bid_size'],
                'ask_size': quote['ask_size'],
                'timestamp': quote['timestamp']
            }

        except Exception as e:
            logger.error(f"Error getting futures quote for {symbol}: {e}")
            raise

    # ========================================================================
    # OPTIONS DATA
    # ========================================================================

    def get_options_contract(self, contract: str) -> Dict[str, Any]:
        """
        Get options contract details and Greeks

        Args:
            contract: Options contract (e.g., 'O:AAPL251219C00150000')

        Returns:
            Dict with Greeks, IV, and pricing
        """
        try:
            snapshot = self.client.get_snapshot_option(ticker=contract)

            return {
                'underlying': snapshot.underlying_asset.ticker,
                'strike': snapshot.details.strike_price,
                'expiration': snapshot.details.expiration_date,
                'type': snapshot.details.contract_type,
                'last_price': snapshot.last_trade.price if snapshot.last_trade else None,
                'bid': snapshot.last_quote.bid if snapshot.last_quote else None,
                'ask': snapshot.last_quote.ask if snapshot.last_quote else None,
                'greeks': {
                    'delta': snapshot.greeks.delta if snapshot.greeks else None,
                    'gamma': snapshot.greeks.gamma if snapshot.greeks else None,
                    'theta': snapshot.greeks.theta if snapshot.greeks else None,
                    'vega': snapshot.greeks.vega if snapshot.greeks else None
                },
                'implied_volatility': snapshot.implied_volatility,
                'open_interest': snapshot.open_interest,
                'volume': snapshot.day.volume if snapshot.day else None
            }

        except Exception as e:
            logger.error(f"Error getting options contract {contract}: {e}")
            raise


class PolygonStreamClient:
    """
    Polygon.io WebSocket client for real-time streaming

    Provides live trades, quotes, and aggregates.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize WebSocket client

        Args:
            api_key: Polygon API key
        """
        self.api_key = api_key or os.getenv('POLYGON_API_KEY')
        if not self.api_key:
            raise ValueError("POLYGON_API_KEY not found")

        # Initialize WebSocket (will connect when run() is called)
        self.ws = None
        self.subscriptions = {}

        logger.info("Polygon WebSocket client initialized")

    async def connect(self, market: str = 'stocks'):
        """
        Connect to WebSocket

        Args:
            market: 'stocks', 'options', 'forex', 'crypto'
        """
        self.ws = WebSocketClient(
            api_key=self.api_key,
            feed='delayed',  # Use 'realtime' with paid plan
            market=market,
            subscriptions=[]
        )

        logger.info(f"Connected to Polygon WebSocket ({market})")

    async def subscribe_trades(
        self,
        symbol: str,
        callback: Callable[[Dict[str, Any]], None]
    ):
        """
        Subscribe to real-time trades

        Args:
            symbol: Symbol to subscribe to
            callback: Function to call on each trade
        """
        if not self.ws:
            await self.connect()

        async def handle_trade(msgs: List[WebSocketMessage]):
            """Handle incoming trade messages"""
            for msg in msgs:
                if isinstance(msg, EquityTrade):
                    trade_data = {
                        'symbol': msg.symbol,
                        'price': msg.price,
                        'size': msg.size,
                        'timestamp': datetime.fromtimestamp(msg.timestamp / 1000),
                        'exchange': msg.exchange
                    }
                    callback(trade_data)

        self.ws.subscribe_trades(symbol, handle_trade)
        logger.info(f"Subscribed to trades for {symbol}")

    async def subscribe_quotes(
        self,
        symbol: str,
        callback: Callable[[Dict[str, Any]], None]
    ):
        """
        Subscribe to real-time quotes (bid/ask)

        Args:
            symbol: Symbol to subscribe to
            callback: Function to call on each quote
        """
        if not self.ws:
            await self.connect()

        async def handle_quote(msgs: List[WebSocketMessage]):
            """Handle incoming quote messages"""
            for msg in msgs:
                if isinstance(msg, EquityQuote):
                    quote_data = {
                        'symbol': msg.symbol,
                        'bid': msg.bid_price,
                        'ask': msg.ask_price,
                        'bid_size': msg.bid_size,
                        'ask_size': msg.ask_size,
                        'timestamp': datetime.fromtimestamp(msg.timestamp / 1000)
                    }
                    callback(quote_data)

        self.ws.subscribe_quotes(symbol, handle_quote)
        logger.info(f"Subscribed to quotes for {symbol}")

    async def run(self):
        """Start the WebSocket connection"""
        if self.ws:
            await self.ws.run()


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

if __name__ == "__main__":
    # REST API example
    client = PolygonMarketDataClient()

    # Get real-time quote
    quote = client.get_last_quote('AAPL')
    print(f"AAPL: Bid ${quote['bid']}, Ask ${quote['ask']}")

    # Get futures quote
    mnq_quote = client.get_futures_quote('MNQ')
    print(f"MNQ: Last ${mnq_quote['last_price']}")

    # Get historical bars
    bars = client.get_bars('MNQ', timespan='minute', multiplier=5, limit=100)
    print(f"Retrieved {len(bars)} 5-minute bars")

    # WebSocket streaming example
    async def on_trade(trade):
        print(f"Trade: {trade['symbol']} @ ${trade['price']} x {trade['size']}")

    async def stream_example():
        stream = PolygonStreamClient()
        await stream.subscribe_trades('AAPL', on_trade)
        await stream.run()

    # Run streaming (comment out for now)
    # asyncio.run(stream_example())
```

---

## 📊 Step 3: Implement True CVD (1 hour)

Create `src/analysis/realtime_cvd.py`:

```python
"""
Real-Time CVD Calculator using Polygon.io tick data

Calculates true Cumulative Volume Delta from tick-level trades.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from collections import deque
from loguru import logger
import numpy as np


class RealTimeCVDCalculator:
    """
    Calculate true CVD from tick-by-tick trade data

    Uses bid/ask to determine if trade was buy or sell.
    """

    def __init__(self, lookback: int = 10000):
        """
        Initialize CVD calculator

        Args:
            lookback: Number of ticks to keep in memory
        """
        self.lookback = lookback
        self.ticks = deque(maxlen=lookback)
        self.cvd = 0.0

        logger.info(f"RealTimeCVD initialized (lookback: {lookback} ticks)")

    def process_trade(
        self,
        price: float,
        size: int,
        bid: float,
        ask: float,
        timestamp: datetime
    ) -> Dict[str, Any]:
        """
        Process a single trade tick

        Args:
            price: Trade price
            size: Trade size (shares/contracts)
            bid: Current bid price
            ask: Current ask price
            timestamp: Trade timestamp

        Returns:
            Dict with delta, cvd, and trade classification
        """
        # Classify trade as buy or sell
        if price >= ask:
            # Trade at ask or above = aggressive buy
            delta = size
            classification = 'buy'
        elif price <= bid:
            # Trade at bid or below = aggressive sell
            delta = -size
            classification = 'sell'
        else:
            # Trade between bid/ask = neutral
            # Use midpoint method: if closer to ask, it's a buy
            mid = (bid + ask) / 2
            if price >= mid:
                delta = size * 0.5  # Partial buy
                classification = 'buy_neutral'
            else:
                delta = -size * 0.5  # Partial sell
                classification = 'sell_neutral'

        # Update CVD
        self.cvd += delta

        # Store tick
        tick_data = {
            'timestamp': timestamp,
            'price': price,
            'size': size,
            'bid': bid,
            'ask': ask,
            'delta': delta,
            'cvd': self.cvd,
            'classification': classification
        }

        self.ticks.append(tick_data)

        return tick_data

    def get_cvd(self) -> float:
        """Get current CVD value"""
        return self.cvd

    def get_cvd_slope(self, lookback: int = 100) -> float:
        """
        Calculate CVD slope (rate of change)

        Args:
            lookback: Number of recent ticks to analyze

        Returns:
            CVD slope (positive = buying pressure, negative = selling)
        """
        if len(self.ticks) < lookback:
            return 0.0

        recent_ticks = list(self.ticks)[-lookback:]
        cvd_values = [t['cvd'] for t in recent_ticks]

        # Linear regression slope
        x = np.arange(len(cvd_values))
        slope = np.polyfit(x, cvd_values, 1)[0]

        return slope

    def get_delta_divergence(
        self,
        price_data: List[float],
        lookback: int = 50
    ) -> Optional[str]:
        """
        Detect delta divergence

        Args:
            price_data: Recent price values
            lookback: Lookback period

        Returns:
            'bullish' if bullish divergence, 'bearish' if bearish, None otherwise
        """
        if len(self.ticks) < lookback or len(price_data) < lookback:
            return None

        recent_ticks = list(self.ticks)[-lookback:]
        recent_prices = price_data[-lookback:]

        # Check if price making new high but CVD not
        price_trend = np.polyfit(range(len(recent_prices)), recent_prices, 1)[0]
        cvd_trend = np.polyfit(range(len(recent_ticks)), [t['cvd'] for t in recent_ticks], 1)[0]

        # Bullish divergence: price falling but CVD rising
        if price_trend < 0 and cvd_trend > 0:
            return 'bullish'

        # Bearish divergence: price rising but CVD falling
        if price_trend > 0 and cvd_trend < 0:
            return 'bearish'

        return None

    def get_statistics(self) -> Dict[str, Any]:
        """Get CVD statistics"""
        if not self.ticks:
            return {}

        ticks_list = list(self.ticks)

        buy_volume = sum(t['delta'] for t in ticks_list if t['delta'] > 0)
        sell_volume = abs(sum(t['delta'] for t in ticks_list if t['delta'] < 0))

        return {
            'cvd': self.cvd,
            'total_ticks': len(ticks_list),
            'buy_volume': buy_volume,
            'sell_volume': sell_volume,
            'buy_sell_ratio': buy_volume / sell_volume if sell_volume > 0 else float('inf'),
            'cvd_slope': self.get_cvd_slope(),
            'net_delta': buy_volume - sell_volume
        }

    def reset(self):
        """Reset CVD to zero"""
        self.cvd = 0.0
        self.ticks.clear()
        logger.info("CVD reset")


# ============================================================================
# INTEGRATION WITH POLYGON
# ============================================================================

class PolygonCVDIntegration:
    """
    Integrate Polygon.io with CVD calculator

    Streams live trades and calculates CVD in real-time.
    """

    def __init__(self, polygon_stream_client, symbol: str):
        """
        Initialize integration

        Args:
            polygon_stream_client: PolygonStreamClient instance
            symbol: Symbol to track
        """
        self.stream = polygon_stream_client
        self.symbol = symbol
        self.cvd_calc = RealTimeCVDCalculator()

        self.current_bid = None
        self.current_ask = None

    async def start(self):
        """Start streaming and CVD calculation"""
        # Subscribe to quotes (for bid/ask)
        await self.stream.subscribe_quotes(self.symbol, self._on_quote)

        # Subscribe to trades
        await self.stream.subscribe_trades(self.symbol, self._on_trade)

        logger.info(f"Started CVD tracking for {self.symbol}")

        # Run stream
        await self.stream.run()

    def _on_quote(self, quote: Dict[str, Any]):
        """Handle quote update"""
        self.current_bid = quote['bid']
        self.current_ask = quote['ask']

    def _on_trade(self, trade: Dict[str, Any]):
        """Handle trade tick"""
        if self.current_bid is None or self.current_ask is None:
            # Wait for first quote
            return

        # Process trade
        tick = self.cvd_calc.process_trade(
            price=trade['price'],
            size=trade['size'],
            bid=self.current_bid,
            ask=self.current_ask,
            timestamp=trade['timestamp']
        )

        # Log significant CVD changes
        slope = self.cvd_calc.get_cvd_slope()
        if abs(slope) > 1000:  # Threshold
            logger.info(
                f"Strong CVD movement: {slope:+.0f}, "
                f"Total CVD: {self.cvd_calc.cvd:+.0f}"
            )

    def get_cvd_data(self) -> Dict[str, Any]:
        """Get current CVD data"""
        return self.cvd_calc.get_statistics()
```

---

## 🔌 Step 4: Integration with Existing System (2 hours)

### 4.1 Update ICT Signal Generator

Edit `src/analysis/ict_signal_generator.py`:

```python
# Add at top
from src.api.polygon_client import PolygonMarketDataClient
from src.analysis.realtime_cvd import RealTimeCVDCalculator

class ICTSignalGenerator:
    def __init__(self, use_polygon: bool = True):
        # ... existing code ...

        # Add Polygon support
        if use_polygon:
            try:
                self.polygon_client = PolygonMarketDataClient()
                self.cvd_calculator = RealTimeCVDCalculator()
                logger.info("Polygon integration enabled for true CVD")
            except:
                logger.warning("Polygon not available, using Yahoo")
                self.polygon_client = None
                self.cvd_calculator = None
        else:
            self.polygon_client = None
            self.cvd_calculator = None

    def _get_cvd_confirmation(self, symbol: str, direction: str) -> bool:
        """Get CVD confirmation (uses Polygon if available)"""
        if self.cvd_calculator:
            # Use real CVD from Polygon
            cvd_slope = self.cvd_calculator.get_cvd_slope()

            if direction == "long":
                return cvd_slope > 500  # Positive slope = buying
            else:
                return cvd_slope < -500  # Negative slope = selling
        else:
            # Fall back to synthetic CVD
            return self._calculate_synthetic_cvd(symbol, direction)
```

### 4.2 Add Polygon Endpoint

Create `src/api/polygon_endpoints.py`:

```python
"""
Polygon.io API Endpoints

Expose Polygon market data through FastAPI.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
from loguru import logger

from src.api.polygon_client import PolygonMarketDataClient

polygon_router = APIRouter(prefix="/api/polygon", tags=["Polygon Market Data"])

# Initialize client
try:
    polygon_client = PolygonMarketDataClient()
except:
    polygon_client = None
    logger.warning("Polygon client not available (missing API key)")


@polygon_router.get("/quote/{symbol}")
async def get_realtime_quote(symbol: str):
    """Get real-time quote for symbol"""
    if not polygon_client:
        raise HTTPException(status_code=503, detail="Polygon not configured")

    try:
        quote = polygon_client.get_last_quote(symbol)
        return {"success": True, "data": quote}
    except Exception as e:
        logger.error(f"Error getting quote: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@polygon_router.get("/futures/{symbol}")
async def get_futures_quote(symbol: str):
    """Get futures quote (MNQ, ES, NQ, etc.)"""
    if not polygon_client:
        raise HTTPException(status_code=503, detail="Polygon not configured")

    try:
        quote = polygon_client.get_futures_quote(symbol)
        return {"success": True, "data": quote}
    except Exception as e:
        logger.error(f"Error getting futures quote: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@polygon_router.get("/bars/{symbol}")
async def get_historical_bars(
    symbol: str,
    timespan: str = Query('minute'),
    multiplier: int = Query(1),
    limit: int = Query(100)
):
    """Get historical OHLCV bars"""
    if not polygon_client:
        raise HTTPException(status_code=503, detail="Polygon not configured")

    try:
        bars = polygon_client.get_bars(
            symbol=symbol,
            timespan=timespan,
            multiplier=multiplier,
            limit=limit
        )
        return {"success": True, "data": bars}
    except Exception as e:
        logger.error(f"Error getting bars: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

### 4.3 Register Router

Edit `src/api/main.py`:

```python
# Add with other router imports
try:
    from .polygon_endpoints import polygon_router
    app.include_router(polygon_router)
    logger.info("Polygon endpoints loaded successfully")
except Exception as e:
    logger.warning(f"Could not load Polygon endpoints: {e}")
```

---

## 🧪 Step 5: Testing (1 hour)

Create `tests/test_polygon_integration.py`:

```python
"""
Polygon.io Integration Tests
"""

import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import os
import pytest
from src.api.polygon_client import PolygonMarketDataClient

# Skip tests if no API key
skip_if_no_key = pytest.mark.skipif(
    not os.getenv('POLYGON_API_KEY'),
    reason="POLYGON_API_KEY not set"
)


@skip_if_no_key
class TestPolygonClient:
    """Test Polygon REST client"""

    def setup_method(self):
        self.client = PolygonMarketDataClient()

    def test_get_last_quote(self):
        """Test real-time quote"""
        quote = self.client.get_last_quote('AAPL')

        assert 'bid' in quote
        assert 'ask' in quote
        assert quote['bid'] > 0
        assert quote['ask'] > quote['bid']

    def test_get_futures_quote(self):
        """Test futures quote"""
        quote = self.client.get_futures_quote('MNQ')

        assert 'last_price' in quote
        assert 'bid' in quote
        assert 'ask' in quote

    def test_get_bars(self):
        """Test historical bars"""
        bars = self.client.get_bars('AAPL', timespan='minute', limit=10)

        assert len(bars) > 0
        assert 'open' in bars[0]
        assert 'high' in bars[0]
        assert 'low' in bars[0]
        assert 'close' in bars[0]
        assert 'volume' in bars[0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

---

## 🚀 Step 6: Deployment Checklist

### Pre-Deployment

- [ ] Get Polygon API key ($99/mo Developer plan)
- [ ] Add `POLYGON_API_KEY` to `.env`
- [ ] Install `polygon-api-client` package
- [ ] Test API connection
- [ ] Verify rate limits (100 calls/min on Developer plan)

### Implementation

- [ ] Create `src/api/polygon_client.py`
- [ ] Create `src/analysis/realtime_cvd.py`
- [ ] Create `src/api/polygon_endpoints.py`
- [ ] Update `src/api/main.py` to register router
- [ ] Update ICT signal generator to use Polygon CVD
- [ ] Create tests

### Testing

- [ ] Test REST API calls
- [ ] Test futures quotes (MNQ)
- [ ] Test historical bars
- [ ] Test WebSocket streaming
- [ ] Test CVD calculation
- [ ] Verify failover to Yahoo works

### Production

- [ ] Monitor API usage (stay under limits)
- [ ] Set up error alerts
- [ ] Log all API calls for debugging
- [ ] Implement caching for repeated calls
- [ ] Monitor costs ($99/mo base + overages)

---

## 💡 Usage Examples

### Get MNQ Real-Time Quote

```python
from src.api.polygon_client import PolygonMarketDataClient

client = PolygonMarketDataClient()

# Get current MNQ price
quote = client.get_futures_quote('MNQ')
print(f"MNQ: ${quote['last_price']}")
print(f"Bid: ${quote['bid']} x {quote['bid_size']}")
print(f"Ask: ${quote['ask']} x {quote['ask_size']}")
```

### Stream Real-Time CVD

```python
from src.api.polygon_client import PolygonStreamClient
from src.analysis.realtime_cvd import PolygonCVDIntegration

stream = PolygonStreamClient()
cvd_tracker = PolygonCVDIntegration(stream, 'MNQ')

# Start streaming (runs forever)
await cvd_tracker.start()

# In another function, get CVD data
cvd_data = cvd_tracker.get_cvd_data()
print(f"Current CVD: {cvd_data['cvd']:+,.0f}")
print(f"CVD Slope: {cvd_data['cvd_slope']:+.2f}")
```

### Use in Trading Signal

```python
from src.analysis.ict_signal_generator import ICTSignalGenerator

# Initialize with Polygon
signal_gen = ICTSignalGenerator(use_polygon=True)

# Generate signals with true CVD
signals = signal_gen.generate_signals(
    symbol='MNQ',
    timeframe='5min',
    min_confidence=75
)

for signal in signals:
    print(f"{signal.direction.upper()} @ {signal.entry_price}")
    print(f"CVD Confirmation: {'✅' if signal.cvd_confirms else '❌'}")
```

---

## 📊 Cost Analysis

### Monthly Costs

| Item | Cost | Notes |
|------|------|-------|
| Polygon Developer | $99/mo | 100 calls/min, real-time data |
| Overages | ~$10-20/mo | If exceeding limits |
| **Total** | **~$110-120/mo** | |

### ROI Calculation

**If Polygon CVD improves win rate by just 3%:**

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Win Rate | 55% | 58% | +3% |
| Monthly Trades | 100 | 100 | - |
| Avg Win | $150 | $150 | - |
| Avg Loss | -$100 | -$100 | - |
| **Monthly P&L** | **$500** | **$950** | **+$450** |

**ROI: $450 extra profit - $120 cost = $330/month net gain**

**Payback Period: Immediate** ✅

---

## 🎯 Success Metrics

**Track these after integration:**

1. **CVD Accuracy**: Compare synthetic vs real CVD on same trades
2. **Signal Quality**: Win rate with real CVD vs synthetic
3. **API Reliability**: Uptime, errors, latency
4. **Cost Management**: Stay within rate limits
5. **Data Completeness**: % of trades with CVD data

---

**Ready to integrate? Start with Step 1!** 🚀
