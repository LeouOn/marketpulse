# Market Structure Concepts

## Fair Value Gaps (FVG)

### Definition
A Fair Value Gap (FVG) is an imbalance in price where there is a gap between candles with no overlapping prices. It represents an area where price moved so quickly that not all orders were filled, creating an inefficiency that the market often seeks to correct.

### Identification
An FVG is formed when:
1. A candle's high is lower than the low of the candle two periods before (bullish FVG)
2. A candle's low is higher than the high of the candle two periods before (bearish FVG)

```
Bullish FVG:
  Candle 1: High = 100
  Candle 2: Any candle
  Candle 3: Low = 105
  → FVG exists between 100-105

Bearish FVG:
  Candle 1: Low = 100
  Candle 2: Any candle
  Candle 3: High = 95
  → FVG exists between 95-100
```

### Trading Significance
- **Price Magnet**: FVGs act as magnets for price, often getting filled before major moves continue
- **Entry Points**: Traders look to enter at FVGs in the direction of higher timeframe bias
- **Stop Placement**: Stops often placed beyond FVGs as they represent areas of interest
- **Mitigation**: When price returns to fill an FVG, it's called "mitigation"

### Timeframe Considerations
- **Lower Timeframes (1m-5m)**: Many small FVGs, quick mitigation
- **Medium Timeframes (15m-1h)**: More significant FVGs, take longer to fill
- **Higher Timeframes (4h-Daily)**: Major FVGs, can take days/weeks to mitigate

## Order Blocks

### Definition
An Order Block is a consolidation area before a strong impulsive move, representing potential institutional order placement. It's essentially the last opposing candle before a strong move.

### Identification
Bullish Order Block:
- Look for a strong bullish move (multiple green candles)
- Identify the last red candle before the move started
- That red candle is the bullish order block

Bearish Order Block:
- Look for a strong bearish move (multiple red candles)
- Identify the last green candle before the move started
- That green candle is the bearish order block

### Trading Significance
- **Support/Resistance**: Order blocks act as support (bullish) or resistance (bearish) on retests
- **Entry Points**: High-probability entry when price returns to order block
- **Confirmation**: Look for additional confluence (FVGs, liquidity, etc.)

## Liquidity Concepts

### Liquidity Sweeps
A liquidity sweep occurs when price moves beyond a recent high or low to trigger stop losses and grab liquidity before reversing in the opposite direction.

**Characteristics:**
- Quick move beyond recent swing point
- Immediate reversal
- Often coincides with news or session opens
- Creates long wicks beyond structure

**Trading Implication:** The sweep often marks the true direction of the next move.

### Liquidity Voids
Areas on the chart with little trading activity, often created by gaps or fast moves.

**Characteristics:**
- Low volume areas
- Price moves quickly through these zones
- Act as price magnets (similar to FVGs)

## Market Structure Hierarchy

### Higher Timeframe Bias
Always establish higher timeframe bias first:

**Daily/4h Bias:**
- Bullish: Higher highs and higher lows
- Bearish: Lower highs and lower lows
- Range: Neither clear highs nor lows

**Entry Timeframe (5m-15m):**
- Trade only in direction of higher timeframe bias
- Look for entries at key levels (FVGs, Order Blocks)
- Use lower timeframe for precise timing

### Break of Structure (BOS)
When price breaks a previous swing high (bullish) or swing low (bearish), indicating potential trend continuation.

### Change of Character (ChoCh)
When price breaks a previous swing low in an uptrend (or high in downtrend), indicating potential trend change.

## ICT Kill Zones

### Asian Kill Zone (19:00-23:00 EST)
- Tokyo session open
- Often sets the day's high/low
- Good for range trading

### London Kill Zone (02:00-04:00 EST)
- London session open
- Highest volume period
- Often creates major moves
- Best for trend continuation trades

### New York Kill Zone (09:30-10:30 EST)
- US equities open
- High volatility
- Often reverses London moves
- Good for counter-trend setups

## Cumulative Volume Delta (CVD)

### Definition
Running total of the difference between buying and selling volume:
CVD = Σ(Buy Volume - Sell Volume)

### Calculation
- **Positive Delta**: More buying volume than selling
- **Negative Delta**: More selling volume than buying
- **Divergence**: When CVD moves opposite to price

### Trading Applications
1. **Trend Confirmation**: CVD moving with price confirms trend strength
2. **Reversal Signals**: CVD divergence from price suggests potential reversal
3. **Exhaustion**: Extreme CVD readings may indicate overextension
4. **Liquidity**: CVD can show where large orders are being filled

### Crypto-Specific Considerations
- **Perpetuals vs Spot**: CVD patterns differ due to funding rate mechanics
- **Exchange Differences**: Binance, Bybit, dYdX have different CVD patterns
- **Funding Rate Impact**: High funding can artificially inflate/deflate CVD

## Crypto Derivatives Mechanics

### Funding Rate
Periodic payment between long and short traders to keep perpetual futures pegged to spot price.

**Payment Times:** 00:00, 08:00, 16:00 UTC (most exchanges)

**Calculation:**
- Positive funding: Longs pay shorts (bearish sentiment)
- Negative funding: Shorts pay longs (bullish sentiment)
- Rate based on premium/discount to spot

**Trading Implications:**
- High positive funding: Longs expensive, potential short opportunity
- High negative funding: Shorts expensive, potential long opportunity
- Funding rate arbitrage: Spot-perpetual basis trading

### Margin Requirements

**Cross Margin:**
- Shares margin across all positions
- Lower liquidation risk for individual positions
- Higher overall risk (one bad trade affects all)

**Isolated Margin:**
- Margin dedicated to single position
- Safer for individual trades
- Higher liquidation risk per position

**Overnight Margin:**
- Additional margin required to hold positions overnight
- Typically 2-4 hours before traditional market close
- Forces position closure for undercapitalized traders

### Liquidation Mechanics

**Liquidation Price Calculation:**
- Based on maintenance margin requirement
- Varies by leverage and position size
- Mark price (fair price) used, not last price

**Liquidation Cascade:**
- Forced liquidation pushes price further
- Triggers more liquidations
- Creates extreme volatility
- Often marks local tops/bottoms

**Prevention:**
- Monitor margin ratio
- Use appropriate leverage
- Set stop losses before liquidation
- Maintain adequate collateral

## Time-Based Patterns

### Overnight Session (20:00-02:00 EST)
- Lower volume
- Often range-bound
- News-driven moves
- Setup for London open

### London Open (02:00-04:00 EST)
- Highest volume
- Trend establishment
- Breakout opportunities
- Liquidity grabs common

### New York Open (09:30-10:30 EST)
- High volatility
- Often reverses London trend
- Equities correlation
- Economic data releases

### Power Hour (15:00-16:00 EST)
- Volume increases
- Position squaring
- Trend continuation or reversal
- Setup for overnight session

### Crypto-Specific Times
- **00:00 UTC**: Funding rate payment, margin requirements
- **08:00 UTC**: Asian session peak, funding payment
- **16:00 UTC**: US session close, funding payment

## Volume Analysis

### Volume Profile
Distribution of volume across price levels over a specific time period.

**Key Levels:**
- **Point of Control (POC)**: Price with highest volume
- **Value Area**: 70% of volume around POC (one standard deviation)
- **High Volume Nodes**: Areas of significant trading interest
- **Low Volume Nodes**: Areas of price acceptance, potential support/resistance

### Volume Delta Patterns
**Buying Pressure:**
- Positive delta increasing
- Price rising with delta
- Confirmation of uptrend

**Selling Pressure:**
- Negative delta increasing
- Price falling with delta
- Confirmation of downtrend

**Divergence Signals:**
- Price rising, delta falling = Weak uptrend, potential reversal
- Price falling, delta rising = Weak downtrend, potential reversal

### Crypto Volume Considerations
- **Wash Trading**: Fake volume on some exchanges
- **Exchange Differences**: Real volume vs reported volume
- **Funding Impact**: Volume spikes around funding times
- **Perpetual vs Spot**: Different volume patterns

## Risk Management

### Position Sizing
**Fixed Fractional:**
- Risk fixed percentage of account (1-2% typical)
- Position size = (Account Risk) / (Trade Risk in points)

**Kelly Criterion:**
- Optimal position size based on win rate and win/loss ratio
- Conservative Kelly = Full Kelly / 2 or 4

### Stop Loss Placement
**Technical Levels:**
- Beyond recent swing points
- Beyond FVGs and Order Blocks
- Beyond liquidity sweeps

**Volatility-Based:**
- ATR multiples (1.5x to 2x ATR)
- Standard deviation bands
- Percentage of account

**Time-Based:**
- Exit if trade doesn't work within X minutes/hours
- Close before specific times (margin, funding, news)

### Risk:Reward Ratios
**Minimum 2:1** for most trades
**3:1 or higher** for breakout trades
**1:1 acceptable** for high-probability scalp setups

## Trading Psychology

### Common Biases
**Recency Bias:** Overweighting recent trades
**Confirmation Bias:** Seeking info that confirms existing position
**Loss Aversion:** Holding losers too long, taking profits too early
**FOMO:** Entering late due to fear of missing out
**Revenge Trading:** Taking trades to recover losses quickly

### Discipline Rules
1. **Trade Plan:** Every trade needs entry, stop, target before execution
2. **Max Loss:** Daily loss limit (e.g., 2% of account)
3. **Review:** Journal every trade with screenshot and reasoning
4. **Breaks:** Take breaks after consecutive losses or wins
5. **Process Over Outcome:** Focus on following plan, not just P&L

## Market Regimes

### Trending Markets
**Characteristics:**
- Clear higher highs/higher lows (uptrend) or lower highs/lower lows (downtrend)
- Pullbacks are shallow (38-50% Fibonacci)
- Volume confirms direction
- Moving averages act as support/resistance

**Strategy:** Trade with trend, enter on pullbacks

### Ranging Markets
**Characteristics:**
- Price oscillates between support and resistance
- No clear trend direction
- False breakouts common
- Mean reversion works

**Strategy:** Fade extremes, buy support, sell resistance

### High Volatility
**Characteristics:**
- Large daily ranges
- Gaps common
- News-driven moves
- Liquidations frequent

**Strategy:** Wider stops, smaller size, avoid FOMO

### Low Volatility
**Characteristics:**
- Small daily ranges
- Low volume
- Grinding price action
- Breakouts often false

**Strategy:** Mean reversion, smaller targets, patience