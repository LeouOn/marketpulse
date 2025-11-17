# Divergence Detection System

## Overview

MarketPulse includes a comprehensive divergence detection system that automatically scans for price-indicator disagreements across multiple technical indicators. Divergences are powerful trading signals that often precede trend reversals or continuations.

## What are Divergences?

A divergence occurs when price action and a technical indicator disagree, creating a divergence in their movement patterns. This disagreement often signals:
- **Regular Divergences**: Potential trend reversals
- **Hidden Divergences**: Trend continuation opportunities

## Divergence Types

### Regular Bullish Divergence (REVERSAL ↑)
- **Pattern**: Price makes a lower low, but indicator makes a higher low
- **Signal**: Potential reversal from downtrend to uptrend
- **Action**: Look for long entry opportunities

### Regular Bearish Divergence (REVERSAL ↓)
- **Pattern**: Price makes a higher high, but indicator makes a lower high
- **Signal**: Potential reversal from uptrend to downtrend
- **Action**: Look for short entry opportunities or exit longs

### Hidden Bullish Divergence (CONTINUATION ↑)
- **Pattern**: Price makes a higher low, but indicator makes a lower low
- **Signal**: Uptrend continuation expected
- **Action**: Add to long positions on pullbacks

### Hidden Bearish Divergence (CONTINUATION ↓)
- **Pattern**: Price makes a lower high, but indicator makes a higher high
- **Signal**: Downtrend continuation expected
- **Action**: Add to short positions on rallies

## Indicators Scanned

MarketPulse scans for divergences across these indicators:

### 1. RSI (Relative Strength Index)
- **Best For**: Identifying overbought/oversold divergences
- **Strength**: Most reliable in ranging markets
- **Look For**: Divergences in overbought (>70) and oversold (<30) zones

### 2. MACD (Moving Average Convergence Divergence)
- **Best For**: Momentum divergences
- **Strength**: Excellent for trend reversal signals
- **Look For**: Histogram divergences for clearest signals

### 3. Stochastic Oscillator
- **Best For**: Short-term reversals
- **Strength**: Very sensitive to price changes
- **Look For**: Divergences in extreme zones (>80 or <20)

### 4. Volume (OBV - On Balance Volume)
- **Best For**: Confirming price moves with volume
- **Strength**: MOST POWERFUL - volume doesn't lie
- **Look For**: Volume divergences receive 10% bonus strength
- **Note**: Volume divergences are particularly reliable

## API Endpoints

### 1. Scan for Divergences (JSON)

**GET** `/api/divergence/scan/{symbol}`

Get all detected divergences for a symbol.

**Parameters:**
- `symbol`: Stock symbol (e.g., AAPL, SPY, MNQ)
- `timeframe`: Chart timeframe (1m, 5m, 15m, 1h, 1d) - default: 1d
- `period`: Historical period (1d, 5d, 1mo, 3mo, 6mo, 1y) - default: 3mo
- `min_strength`: Minimum strength threshold (0-100) - default: 60

**Example:**
```bash
curl "http://localhost:8000/api/divergence/scan/AAPL?period=3mo&min_strength=60"
```

**Response:**
```json
{
  "success": true,
  "data": {
    "symbol": "AAPL",
    "timestamp": "2024-11-16T12:00:00",
    "total_divergences": 5,
    "by_type": {
      "regular_bullish": 2,
      "regular_bearish": 1,
      "hidden_bullish": 1,
      "hidden_bearish": 1
    },
    "divergences": [
      {
        "type": "regular_bullish",
        "indicator": "rsi",
        "strength": 85.0,
        "start_time": "2024-10-01",
        "end_time": "2024-10-15",
        "description": "Regular bullish divergence: Price LL but RSI HL (strength: 85)",
        "price_points": [45, 82],
        "indicator_points": [46, 81]
      }
    ],
    "strongest": {
      "type": "regular_bullish",
      "indicator": "obv",
      "strength": 99.0,
      "description": "Volume (OBV) bullish divergence - very strong signal!"
    },
    "signal": "BULLISH"
  }
}
```

### 2. Divergence Chart (HTML)

**GET** `/api/divergence/chart/{symbol}`

Interactive candlestick chart with divergence overlays.

**Parameters:**
- Same as scan endpoint
- `indicators`: Comma-separated list (e.g., "sma_20,ema_50")

**Example:**
```
http://localhost:8000/api/divergence/chart/AAPL?period=3mo&indicators=sma_20,vwap
```

### 3. Divergence Dashboard (HTML)

**GET** `/api/divergence/dashboard/{symbol}`

Comprehensive dashboard with:
- Price chart with divergence annotations
- Indicator panels (RSI, MACD, Stochastic)
- Divergence summary and list
- Educational content

**Example:**
```
http://localhost:8000/api/divergence/dashboard/AAPL?period=3mo
```

## Usage Examples

### Python Client

```python
import requests

# Scan for divergences
response = requests.get(
    "http://localhost:8000/api/divergence/scan/AAPL",
    params={
        "period": "3mo",
        "timeframe": "1d",
        "min_strength": 70.0
    }
)

data = response.json()["data"]

# Check overall signal
print(f"Signal: {data['signal']}")
print(f"Found {data['total_divergences']} divergences")

# Examine strongest divergence
if data['strongest']:
    div = data['strongest']
    print(f"\nStrongest: {div['indicator'].upper()} {div['type']}")
    print(f"Strength: {div['strength']:.0f}")
    print(f"Description: {div['description']}")

# List all divergences
for div in data['divergences']:
    print(f"\n{div['indicator'].upper()} - {div['type']}")
    print(f"  Strength: {div['strength']:.0f}")
    print(f"  Period: {div['start_time']} to {div['end_time']}")
```

### Trading Strategy Integration

```python
from src.analysis.divergence_detector import scan_for_divergences
from src.api.yahoo_client import YahooFinanceClient

# Get historical data
client = YahooFinanceClient()
df = client.get_historical_data("MNQ", period="3mo", interval="1d")

# Scan for divergences
result = scan_for_divergences(df, min_strength=70.0)

# Make trading decisions
if result['signal'] == 'STRONG_BULLISH':
    print("🟢 Strong bullish signal - Consider long entry")

    # Check if we have volume confirmation
    volume_divs = [d for d in result['divergences'] if d['indicator'] == 'obv']
    if volume_divs:
        print("✅ Volume confirms divergence - HIGH CONFIDENCE")

elif result['signal'] == 'STRONG_BEARISH':
    print("🔴 Strong bearish signal - Consider short entry or exit longs")

# Check for specific setups
bullish_count = result['by_type']['regular_bullish']
if bullish_count >= 2:
    print(f"📊 Multiple bullish divergences detected ({bullish_count})")
    print("   Wait for price confirmation before entering")
```

## Strength Scoring

Divergences are scored 0-100 based on:

1. **Magnitude of Divergence** (0-40 points)
   - Larger price/indicator disagreement = higher score
   - Based on percentage changes

2. **Clear Divergence Bonus** (+10 points)
   - Both price and indicator changes > 2%

3. **Extreme Divergence Bonus** (+10 points)
   - Either price or indicator change > 5%

4. **Volume Divergence Bonus** (+10%)
   - OBV divergences receive 10% extra strength
   - Volume doesn't lie!

5. **Hidden Divergence Penalty** (-20%)
   - Hidden divergences score 80% of regular divergences
   - Still valuable, but less dramatic

### Strength Thresholds

- **90-100**: EXTREMELY STRONG - Rare, very high probability
- **75-89**: STRONG - High confidence signal
- **60-74**: MODERATE - Good signal, confirm with other factors
- **40-59**: WEAK - Be cautious, wait for confirmation
- **<40**: VERY WEAK - Likely noise, ignore

## Trading Best Practices

### 1. Confirmation is Key
- Don't trade divergences alone
- Wait for price action confirmation:
  - Candlestick reversal patterns
  - Break of trend lines
  - Key support/resistance levels

### 2. Combine with ICT Concepts
- **FVG + Divergence** = High probability setup
- **Order Block + Divergence** = Strong reversal zone
- **Liquidity Sweep + Divergence** = Excellent entry

### 3. Timeframe Analysis
```python
# Scan multiple timeframes
for timeframe in ['1d', '4h', '1h']:
    result = scan_for_divergences(df, min_strength=60)
    print(f"{timeframe}: {result['signal']}")

# Look for alignment:
# - Daily + 4H bullish = Strong uptrend
# - Higher timeframe divergence > lower timeframe
```

### 4. Volume is King
- Prioritize volume divergences (OBV)
- Volume divergences are the most reliable
- If price and volume diverge, trust volume

### 5. Risk Management
Even with strong divergences:
- Always use stop losses
- Position size appropriately
- Don't risk more than 1-2% per trade

## Example Trade Setup

### MNQ Futures Scalping with Divergences

```python
from src.analysis.divergence_detector import scan_for_divergences
from src.analysis.risk_manager import RiskManager

# 1. Scan for divergences on 5-minute chart
df = client.get_historical_data("MNQ", period="1d", interval="5m")
result = scan_for_divergences(df, min_strength=75.0)

# 2. Check for strong bullish divergence
if result['signal'] in ['BULLISH', 'STRONG_BULLISH']:
    strongest = result['strongest']

    if strongest and strongest['strength'] >= 85:
        print(f"🎯 Strong {strongest['indicator'].upper()} divergence detected")

        # 3. Check risk management
        entry_price = df['close'].iloc[-1]
        stop_loss = df['low'].iloc[-10:].min() - 5  # Below recent lows
        take_profit = entry_price + (entry_price - stop_loss) * 2  # 2:1 R:R

        # 4. Validate with risk manager
        risk_mgr = RiskManager()
        validation = risk_mgr.validate_trade(
            symbol="MNQ",
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            direction="LONG",
            contracts=1
        )

        if validation.approved:
            print("✅ Trade approved by risk manager")
            print(f"   Entry: ${entry_price:.2f}")
            print(f"   Stop: ${stop_loss:.2f}")
            print(f"   Target: ${take_profit:.2f}")
            print(f"   R:R: 1:{validation.risk_reward_ratio:.2f}")
        else:
            print(f"❌ Trade rejected: {validation.reason}")
```

## Visualization Examples

### Chart Annotations

Divergences are displayed on charts with:
- **Green annotations** for bullish divergences
- **Red annotations** for bearish divergences
- **Solid lines** for regular divergences
- **Dotted lines** for hidden divergences
- **Shaded regions** highlighting divergence zones
- **Arrows** pointing to divergence locations

### Dashboard Features

The divergence dashboard (`/api/divergence/dashboard/{symbol}`) includes:
- Real-time divergence detection
- Color-coded signal banner
- Metrics cards showing counts by type
- Interactive price chart with overlays
- Indicator panels (RSI, MACD, Stochastic)
- Detailed divergence list with strength bars
- Educational content

## Performance Considerations

### Optimization Tips

1. **Adjust Parameters**:
   ```python
   # For day trading (more sensitive)
   detector = DivergenceDetector(min_strength=50.0, lookback=30)

   # For swing trading (higher quality)
   detector = DivergenceDetector(min_strength=75.0, lookback=50)
   ```

2. **Filter by Indicators**:
   ```python
   # Only scan RSI and MACD (faster)
   result = scan_for_divergences(df, indicators=['rsi', 'macd'])
   ```

3. **Cache Results**:
   ```python
   # Cache divergence scans for repeated queries
   # Divergences don't change on historical data
   ```

## Limitations

1. **Lagging Indicator**: Divergences form after the fact
2. **False Signals**: Not all divergences lead to reversals
3. **Requires Confirmation**: Don't trade divergences alone
4. **Timeframe Dependent**: Different timeframes show different divergences

## Testing

Run divergence tests:

```bash
# Run all divergence tests
pytest tests/test_divergence.py -v

# Run with detailed output
pytest tests/test_divergence.py -v -s

# Run specific test
pytest tests/test_divergence.py::TestDivergenceDetector::test_bullish_divergence_detection -v
```

Test results (all passing):
```
tests/test_divergence.py::TestDivergenceDetector::test_detector_initialization PASSED
tests/test_divergence.py::TestDivergenceDetector::test_pivot_detection PASSED
tests/test_divergence.py::TestDivergenceDetector::test_bullish_divergence_detection PASSED
tests/test_divergence.py::TestDivergenceDetector::test_bearish_divergence_detection PASSED
tests/test_divergence.py::TestDivergenceDetector::test_scan_for_divergences PASSED
tests/test_divergence.py::TestDivergenceDetector::test_divergence_strength_calculation PASSED
tests/test_divergence.py::TestDivergenceDetector::test_real_world_pattern PASSED
tests/test_divergence.py::test_divergence_types PASSED

======================== 8 passed in 1.09s ========================
```

## Integration with Other Features

### With ICT Analysis
```python
# Combine divergences with FVG detection
from src.analysis.ict_analyzer import ICTAnalyzer

ict = ICTAnalyzer()
fvgs = ict.detect_fair_value_gaps(df)
divs = scan_for_divergences(df)

# Look for FVG + Divergence combo
if divs['signal'] == 'STRONG_BULLISH' and len(fvgs['bullish']) > 0:
    print("🎯 PREMIUM SETUP: Bullish FVG + Divergence")
```

### With Risk Management
```python
# Use divergence strength to adjust position size
from src.analysis.risk_manager import RiskManager

risk_mgr = RiskManager()
div_strength = result['strongest']['strength']

# Increase position size for stronger divergences
if div_strength >= 90:
    contracts = 2  # Double position
elif div_strength >= 75:
    contracts = 1  # Normal position
else:
    contracts = 0  # Skip trade
```

### With Alerts
```python
# Send alert when strong divergence detected
from src.alerts.alert_manager import AlertManager

alerts = AlertManager()

if result['total_divergences'] > 0 and result['strongest']['strength'] >= 85:
    alerts.send_divergence_alert(
        symbol="MNQ",
        divergence=result['strongest'],
        priority='high'
    )
```

## Further Reading

- **Regular vs Hidden Divergences**: https://www.investopedia.com/articles/trading/09/divergence-convergence.asp
- **RSI Divergence Strategy**: Classic reversal signals
- **MACD Divergence**: Momentum-based reversals
- **Volume Divergence**: The most reliable divergence type

## Summary

Divergence detection is one of the most powerful edges in trading. MarketPulse's system:

✅ Scans 4 major indicators automatically
✅ Detects both regular and hidden divergences
✅ Calculates objective strength scores (0-100)
✅ Provides interactive visualizations
✅ Integrates with risk management
✅ Offers multiple timeframe analysis

**Remember**: Divergences are most powerful when combined with:
1. Price action confirmation
2. Key support/resistance levels
3. ICT concepts (FVG, Order Blocks)
4. Proper risk management
5. Volume confirmation

Happy trading! 📈
