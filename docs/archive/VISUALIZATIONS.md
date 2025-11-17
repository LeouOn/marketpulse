# MarketPulse Visualizations 📊

## Interactive Charts & Market Analysis

Beautiful, interactive visualizations powered by Plotly with real-time data.

---

## 🎨 Features

### ✅ What's Included:

- **📈 Candlestick Charts** - Interactive price charts with zoom, pan, hover
- **📊 Technical Indicators** - 15+ indicators with customizable overlays
- **🗺️ Market Heatmaps** - Sector performance with color gradients
- **🔊 Volume Profile** - Horizontal volume distribution (POC, VAH, VAL)
- **🎯 ICT Overlays** - Fair Value Gaps, Order Blocks, Liquidity Pools
- **📉 Indicator Panels** - RSI, MACD, Stochastic in separate subplots
- **🎛️ Trading Dashboard** - Complete analysis in one page
- **💹 Real-time Analysis** - Live technical analysis with signals

---

## 🚀 Quick Start

### Start MarketPulse

```bash
python src/api/main.py
```

### Visit Visualization Home

Open your browser to:
```
http://localhost:8000/api/viz/
```

---

## 📊 Available Endpoints

### 1. Candlestick Chart

**GET** `/api/viz/candlestick/{symbol}`

Interactive price chart with technical indicators.

**Parameters:**
- `symbol` (required): Stock symbol (e.g., AAPL, MNQ, SPY)
- `timeframe` (optional): 1m, 5m, 15m, 1h, 1d (default: 1d)
- `period` (optional): 1d, 5d, 1mo, 3mo, 6mo, 1y (default: 1mo)
- `indicators` (optional): Comma-separated list of indicators
- `height` (optional): Chart height in pixels (default: 800)

**Available Indicators:**
- Moving Averages: `sma_20`, `sma_50`, `sma_200`, `ema_9`, `ema_21`, `ema_50`
- Oscillators: `rsi`, `macd`, `stochastic`, `adx`
- Bands: `bollinger`, `supertrend`
- Volume: `vwap`, `obv`
- Volatility: `atr`

**Examples:**

```bash
# Basic chart
http://localhost:8000/api/viz/candlestick/AAPL

# With indicators
http://localhost:8000/api/viz/candlestick/AAPL?indicators=sma_20,ema_50,vwap&period=3mo

# MNQ futures with Supertrend
http://localhost:8000/api/viz/candlestick/MNQ?timeframe=5m&period=1d&indicators=sma_20,vwap,supertrend

# Full technical analysis
http://localhost:8000/api/viz/candlestick/TSLA?indicators=sma_20,sma_50,ema_21,bollinger,vwap,supertrend&period=6mo
```

**Screenshot Example:**
```
Price Chart with:
- Candlesticks (green/red)
- SMA 20, 50 overlays
- Bollinger Bands (shaded area)
- VWAP (orange line)
- Volume bars below
- Interactive zoom/pan
- Hover for details
```

---

### 2. Indicator Panel

**GET** `/api/viz/indicators/{symbol}`

Multi-panel view of RSI, MACD, and Stochastic.

**Parameters:**
- `symbol` (required): Stock symbol
- `timeframe` (optional): 1m, 5m, 15m, 1h, 1d (default: 1d)
- `period` (optional): 1d, 5d, 1mo, 3mo, 6mo, 1y (default: 1mo)

**Examples:**

```bash
# Daily indicators
http://localhost:8000/api/viz/indicators/AAPL

# 5-minute for day trading
http://localhost:8000/api/viz/indicators/MNQ?timeframe=5m&period=1d

# Long-term view
http://localhost:8000/api/viz/indicators/SPY?period=1y
```

**What You See:**
- **RSI Panel**:
  - RSI line (blue)
  - Overbought level (70) - red dashed
  - Oversold level (30) - green dashed

- **MACD Panel**:
  - MACD line (blue)
  - Signal line (orange)
  - Histogram (green/red bars)

- **Stochastic Panel**:
  - %K line (blue)
  - %D line (orange)
  - Overbought (80) / Oversold (20) levels

---

### 3. Volume Profile

**GET** `/api/viz/volume-profile/{symbol}`

Horizontal volume distribution showing POC, VAH, VAL.

**Parameters:**
- `symbol` (required): Stock symbol
- `timeframe` (optional): 1m, 5m, 15m, 1h, 1d (default: 1d)
- `period` (optional): 1d, 5d, 1mo, 3mo (default: 1mo)
- `bins` (optional): Number of price levels (default: 50)

**Examples:**

```bash
# Basic volume profile
http://localhost:8000/api/viz/volume-profile/AAPL

# Intraday (more granular)
http://localhost:8000/api/viz/volume-profile/MNQ?timeframe=5m&period=1d&bins=100

# Longer term
http://localhost:8000/api/viz/volume-profile/SPY?period=3mo&bins=75
```

**Key Levels:**
- **POC** (Point of Control): Highest volume - yellow line
- **VAH** (Value Area High): Top of 70% volume - cyan dashed
- **VAL** (Value Area Low): Bottom of 70% volume - cyan dashed
- **Volume Bars**: Horizontal bars showing volume at each price

**Use Case:**
- Find support/resistance based on volume
- Identify fair value area (between VAH/VAL)
- POC acts as magnet for price

---

### 4. Market Heatmap

**GET** `/api/viz/market-heatmap`

Color-coded treemap showing sector or index performance.

**Parameters:**
- `sector` (optional): true for sectors, false for indices (default: true)

**Examples:**

```bash
# Sector performance
http://localhost:8000/api/viz/market-heatmap?sector=true

# Major indices
http://localhost:8000/api/viz/market-heatmap?sector=false
```

**Sectors Tracked:**
- Technology (XLK)
- Financials (XLF)
- Healthcare (XLV)
- Consumer Discretionary (XLY)
- Communication (XLC)
- Industrials (XLI)
- Consumer Staples (XLP)
- Energy (XLE)
- Utilities (XLU)
- Real Estate (XLRE)
- Materials (XLB)

**Color Scale:**
- 🟢 Green: Positive performance
- 🟡 Yellow: Neutral
- 🔴 Red: Negative performance

**Use Case:**
- Identify hot sectors
- Sector rotation analysis
- Risk-on vs risk-off sentiment
- Market breadth visualization

---

### 5. Technical Analysis (JSON)

**GET** `/api/viz/analysis/{symbol}`

Comprehensive analysis returning structured JSON data.

**Parameters:**
- `symbol` (required): Stock symbol
- `timeframe` (optional): 1m, 5m, 15m, 1h, 1d (default: 1d)
- `period` (optional): 1d, 5d, 1mo, 3mo, 6mo, 1y (default: 1mo)

**Examples:**

```bash
# Get analysis for AAPL
http://localhost:8000/api/viz/analysis/AAPL?period=3mo

# Intraday analysis
http://localhost:8000/api/viz/analysis/MNQ?timeframe=5m&period=1d
```

**Response Structure:**

```json
{
  "success": true,
  "data": {
    "symbol": "AAPL",
    "timestamp": "2025-11-15T22:30:00",
    "current_price": 175.43,
    "trends": {
      "sma_trend": "bullish",
      "rsi_signal": "neutral",
      "macd_signal": "bullish",
      "supertrend": "bullish"
    },
    "support_resistance": {
      "resistance": [178.50, 180.25, 182.00],
      "support": [172.80, 170.50, 168.20]
    },
    "indicators": {
      "sma_20": 174.25,
      "sma_50": 172.10,
      "sma_200": 168.50,
      "ema_21": 174.80,
      "rsi": 58.3,
      "macd": 1.25,
      "macd_signal": 0.85,
      "bb_upper": 177.50,
      "bb_lower": 171.00,
      "atr": 2.45,
      "adx": 28.5
    },
    "signals": {
      "overall": "bullish",
      "strength": 2
    }
  }
}
```

**Use Case:**
- Automated trading systems
- Programmatic analysis
- Building custom dashboards
- Signal aggregation

---

### 6. Trading Dashboard

**GET** `/api/viz/dashboard/{symbol}`

Complete trading dashboard with all analysis in one page.

**Parameters:**
- `symbol` (required): Stock symbol
- `timeframe` (optional): 1m, 5m, 15m, 1h, 1d (default: 1d)
- `period` (optional): 1d, 5d, 1mo, 3mo, 6mo, 1y (default: 3mo)

**Examples:**

```bash
# Complete dashboard
http://localhost:8000/api/viz/dashboard/AAPL

# Intraday trading view
http://localhost:8000/api/viz/dashboard/MNQ?timeframe=5m&period=1d

# Long-term analysis
http://localhost:8000/api/viz/dashboard/SPY?period=1y
```

**Dashboard Includes:**

**1. Header Metrics:**
- Current Price
- RSI (14) with overbought/oversold indication
- Trend (bullish/bearish/strong)
- MACD Signal
- ATR (volatility)
- Volume

**2. Price Chart:**
- Candlesticks
- SMA 20, 50
- EMA 21
- Bollinger Bands
- VWAP
- Volume subplot

**3. Indicator Panel:**
- RSI with levels
- MACD with histogram
- Stochastic

**4. Analysis Section:**
- Support & Resistance levels
- Trend analysis breakdown
- Signal summary

---

## 💡 Usage Examples

### Day Trading MNQ

```bash
# 5-minute chart with key indicators
http://localhost:8000/api/viz/candlestick/MNQ?timeframe=5m&period=1d&indicators=sma_20,vwap,supertrend,ema_9

# Volume profile for key levels
http://localhost:8000/api/viz/volume-profile/MNQ?timeframe=5m&period=1d&bins=100

# Complete dashboard
http://localhost:8000/api/viz/dashboard/MNQ?timeframe=5m&period=1d
```

### Swing Trading AAPL

```bash
# Daily chart with full analysis
http://localhost:8000/api/viz/candlestick/AAPL?period=6mo&indicators=sma_20,sma_50,sma_200,bollinger,vwap

# Indicator confirmation
http://localhost:8000/api/viz/indicators/AAPL?period=6mo

# JSON analysis for alerts
http://localhost:8000/api/viz/analysis/AAPL?period=6mo
```

### Market Overview

```bash
# Sector heatmap for rotation
http://localhost:8000/api/viz/market-heatmap?sector=true

# Index dashboard
http://localhost:8000/api/viz/dashboard/SPY?period=3mo
```

---

## 🎨 Customization

### Color Scheme

Charts use a professional dark theme with:
- 🟢 Bullish Candles: `#26a69a` (teal green)
- 🔴 Bearish Candles: `#ef5350` (red)
- 📊 Volume Up: `rgba(38, 166, 154, 0.5)` (transparent green)
- 📉 Volume Down: `rgba(239, 83, 80, 0.5)` (transparent red)
- 🌑 Background: `#1e1e1e` (dark grey)
- 📏 Grid: `#2d2d2d` (slightly lighter grey)

### Interactive Features

All charts support:
- ✅ Zoom (box select or scroll)
- ✅ Pan (click and drag)
- ✅ Hover details (shows OHLCV + indicators)
- ✅ Legend toggle (click to hide/show)
- ✅ Export (camera icon - save as PNG)
- ✅ Autoscale (home icon - reset zoom)
- ✅ Responsive (adapts to screen size)

---

## 🔧 Technical Indicators Reference

### Moving Averages

**Simple Moving Average (SMA):**
- Periods: 20, 50, 200
- Use: Trend direction, support/resistance
- Signal: Price above SMA = bullish

**Exponential Moving Average (EMA):**
- Periods: 9, 21, 50
- Use: Faster reaction to price changes
- Popular: EMA 9/21 crossover

### Oscillators

**RSI (Relative Strength Index):**
- Range: 0-100
- Overbought: > 70
- Oversold: < 30
- Use: Momentum and reversal signals

**MACD (Moving Average Convergence Divergence):**
- Components: MACD line, Signal line, Histogram
- Signal: MACD crosses above Signal = bullish
- Histogram: Shows momentum strength

**Stochastic:**
- Range: 0-100
- Overbought: > 80
- Oversold: < 20
- Use: Momentum in ranging markets

**ADX (Average Directional Index):**
- Range: 0-100
- Strong Trend: > 25
- Very Strong: > 50
- Use: Trend strength measurement

### Bands & Channels

**Bollinger Bands:**
- Components: Upper, Middle (SMA 20), Lower
- Width: ±2 standard deviations
- Use: Volatility and overbought/oversold
- Signal: Price at upper band = overbought

**Supertrend:**
- Based on ATR
- Color: Green = bullish, Red = bearish
- Use: Trend following
- Signal: Color change = trend reversal

### Volume Indicators

**VWAP (Volume Weighted Average Price):**
- Resets daily
- Use: Intraday support/resistance
- Institutional: Often use VWAP for execution

**OBV (On-Balance Volume):**
- Cumulative volume based on price direction
- Use: Volume confirmation of trends
- Divergence: Price up but OBV down = weak

### Volatility

**ATR (Average True Range):**
- Measures volatility (not direction)
- Use: Position sizing, stop loss placement
- High ATR = volatile market

---

## 🎯 Trading Workflows

### Morning Routine

1. **Check Market Heatmap**
   ```
   /api/viz/market-heatmap?sector=true
   ```
   - Identify strong sectors
   - Note rotation patterns

2. **Scan Major Indices**
   ```
   /api/viz/dashboard/SPY
   /api/viz/dashboard/QQQ
   /api/viz/dashboard/IWM
   ```
   - Overall market direction
   - Support/resistance levels

3. **Setup Watchlist**
   ```
   /api/viz/analysis/AAPL
   /api/viz/analysis/TSLA
   /api/viz/analysis/NVDA
   ```
   - Get JSON analysis for each
   - Identify setups

### During Trading

1. **Monitor Price Action**
   ```
   /api/viz/candlestick/MNQ?timeframe=5m&period=1d&indicators=vwap,sma_20,supertrend
   ```
   - Watch for setups
   - Key levels from VWAP/volume profile

2. **Confirm with Indicators**
   ```
   /api/viz/indicators/MNQ?timeframe=5m&period=1d
   ```
   - RSI confirmation
   - MACD alignment
   - Stochastic timing

3. **Check Volume Profile**
   ```
   /api/viz/volume-profile/MNQ?timeframe=5m&period=1d&bins=100
   ```
   - POC as target/support
   - Value area for fair price

### End of Day Review

1. **Performance Check**
   - Use risk dashboard (coming soon)
   - Review wins/losses

2. **Market Analysis**
   ```
   /api/viz/dashboard/SPY?period=3mo
   ```
   - How did market behave?
   - Trend still intact?

3. **Plan Tomorrow**
   ```
   /api/viz/analysis/{symbols}
   ```
   - Identify setups
   - Note key levels

---

## 🚀 Performance Tips

1. **Use Appropriate Timeframes:**
   - Day trading: 1m, 5m, 15m
   - Swing trading: 1h, 1d
   - Long-term: 1d, 1wk

2. **Limit Indicators:**
   - Don't overload (max 4-5 on one chart)
   - Choose complementary indicators
   - More isn't always better

3. **Caching:**
   - Browser caches chart images
   - Re-fetch only when needed
   - Consider API rate limits

4. **Mobile Viewing:**
   - Charts are responsive
   - Works on phones/tablets
   - Best on larger screens for detail

---

## 📱 Integration Ideas

### With Your Trading System

```python
# Get analysis
import requests

response = requests.get('http://localhost:8000/api/viz/analysis/AAPL?period=3mo')
analysis = response.json()['data']

# Check if bullish
if analysis['signals']['overall'] == 'bullish' and analysis['indicators']['rsi'] < 70:
    # Entry conditions met
    print("Bullish setup confirmed!")
    print(f"Entry: {analysis['current_price']}")
    print(f"Resistance: {analysis['support_resistance']['resistance']}")
```

### Alerts Based on Indicators

```python
# Monitor RSI
analysis = get_analysis('MNQ')
rsi = analysis['indicators']['rsi']

if rsi > 70:
    send_alert("MNQ Overbought - RSI: " + str(rsi))
elif rsi < 30:
    send_alert("MNQ Oversold - RSI: " + str(rsi))
```

### Automated Screenshot

```python
# Take screenshot of chart
from selenium import webdriver

driver = webdriver.Chrome()
driver.get('http://localhost:8000/api/viz/dashboard/AAPL')
driver.save_screenshot('aapl_dashboard.png')
```

---

## 🎓 Learning Resources

### Understanding Indicators

- **Moving Averages**: Smooth price data, identify trends
- **RSI**: Momentum oscillator, find overbought/oversold
- **MACD**: Trend and momentum combined
- **Bollinger Bands**: Volatility and mean reversion
- **Volume**: Confirmation of price moves

### Best Practices

1. **Multiple Timeframe Analysis**
   - Check daily for trend
   - Use intraday for timing

2. **Indicator Confluence**
   - Wait for multiple confirmations
   - Don't rely on single indicator

3. **Volume Confirmation**
   - Strong moves need volume
   - Low volume = weak signal

4. **Respect Support/Resistance**
   - Use volume profile for key levels
   - Previous highs/lows important

---

## 🔗 API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/viz/` | GET | Visualization home page |
| `/api/viz/candlestick/{symbol}` | GET | Candlestick chart |
| `/api/viz/indicators/{symbol}` | GET | Indicator panel |
| `/api/viz/volume-profile/{symbol}` | GET | Volume profile |
| `/api/viz/market-heatmap` | GET | Market heatmap |
| `/api/viz/analysis/{symbol}` | GET | Technical analysis (JSON) |
| `/api/viz/dashboard/{symbol}` | GET | Trading dashboard |

---

## 🎉 Next Steps

1. **Try Your First Chart:**
   ```
   http://localhost:8000/api/viz/candlestick/AAPL?indicators=sma_20,rsi,macd
   ```

2. **Explore the Dashboard:**
   ```
   http://localhost:8000/api/viz/dashboard/MNQ?timeframe=5m&period=1d
   ```

3. **Check Market Overview:**
   ```
   http://localhost:8000/api/viz/market-heatmap
   ```

4. **Build Your Workflow:**
   - Morning: Market heatmap + indices
   - Trading: Symbol dashboard + indicators
   - Evening: Performance review

---

**Happy Trading! 📊🚀**

*MarketPulse Visualizations v1.0*
*Interactive, Real-time, Beautiful*
