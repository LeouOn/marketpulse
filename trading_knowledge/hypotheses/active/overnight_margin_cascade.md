# Overnight Margin Cascade Hypothesis

## Hypothesis Statement
On green days in crypto perpetuals, there may be a selloff cascade around margin requirement times (typically 00:00 UTC) as traders close positions to avoid overnight fees. Red days may show buying back for similar reasons.

## Background
Traditional equity markets have overnight margin requirements that force traders to close positions or post additional collateral. While crypto markets trade 24/7, many crypto exchanges and brokers impose "overnight" margin requirements based on traditional market hours (typically 20:00-00:00 UTC window).

## Mechanism
1. **Green Day Setup**: Market is up significantly during the day session
2. **Margin Pressure**: As 00:00 UTC approaches, undercapitalized traders must close positions
3. **Cascade Effect**: Initial selling triggers stops, creating cascading liquidations
4. **Reversal**: After margin window passes, positions may be re-established

## What to Look For

### Price Action Patterns
- **Timing**: Selloff begins 15-30 minutes before 00:00 UTC
- **Intensity**: Peak selling around 23:45-00:00 UTC
- **Recovery**: Bounce back begins 00:00-00:15 UTC
- **Magnitude**: Minimum 0.5-1.0% move during the window

### Volume Characteristics
- **Volume Spike**: 2-3x normal volume during margin window
- **Delta Shift**: CVD should show aggressive selling pressure
- **Perpetual vs Spot**: Effect should be stronger in perpetuals than spot

### Market Conditions
- **Daily Bias**: Effect stronger on days with >2% daily move
- **Leverage**: More pronounced in high-leverage environments
- **Funding Rate**: Correlation with extreme funding rates

## Testing Criteria

### Statistical Requirements
- **Sample Size**: Minimum 90 days of data
- **Significance**: p-value < 0.05 for effect detection
- **Effect Size**: Minimum 0.5% average move during window
- **Consistency**: Effect present in >60% of qualifying days

### Data Requirements
- **Instruments**: BTC-PERP, ETH-PERP (Binance, Bybit, dYdX)
- **Timeframe**: 1-minute data around 00:00 UTC (23:30-00:30)
- **Features**: Price, volume, CVD, funding rate, open interest
- **Control**: Compare to random 30-minute windows

### Success Metrics
1. **Primary**: Statistically significant price movement during margin window
2. **Secondary**: Volume spike correlation with price movement
3. **Tertiary**: Perpetual-spot basis change during window

## Related Concepts

### Funding Rate Pressure
- High positive funding = longs paying shorts = potential long liquidation
- High negative funding = shorts paying longs = potential short liquidation
- Funding payments occur at 00:00, 08:00, 16:00 UTC

### Cross-Margin vs Isolated Margin
- Cross-margin: Entire account balance at risk, more sensitive to margin calls
- Isolated: Only position margin at risk, less systemic risk

### Liquidation Cascades
- Forced liquidations create predictable price pressure
- Often mark local extremes (tops on green days, bottoms on red days)
- Can be front-run by sophisticated traders

### Traditional Market Correlation
- Effect may correlate with traditional market hours (16:00 EST close)
- Crypto "overnight" defined by when traditional brokers require settlement
- Asian session open (00:00 UTC) may amplify or dampen effect

## Potential Confounding Factors

1. **Funding Rate Payments**: Occur at same time (00:00 UTC)
2. **Asian Session Open**: Tokyo trading begins 00:00 UTC
3. **News Events**: Scheduled news often released at session opens
4. **Exchange Maintenance**: Some exchanges have maintenance windows
5. **Large Trader Activity**: Whales may exploit known patterns

## Risk Factors

### False Positives
- Random volatility around session open
- Funding rate arbitrage activity
- Large individual trades (whale activity)

### False Negatives
- Effect may be diluted across multiple time zones
- Different exchanges have different margin requirements
- Institutional traders may not be subject to same rules

## Trading Implications

### If Hypothesis Confirmed
1. **Fade the Cascade**: Enter counter-trend positions after initial move
2. **Time Entries**: Use margin window for better entry prices
3. **Risk Management**: Wider stops around 00:00 UTC
4. **Scalping**: Trade the volatility spike during window

### Position Sizing
- Reduce size during margin window (increased volatility)
- Increase size after window passes (more predictable)
- Consider time-based stops rather than price-based

## Data Sources

### Primary
- Binance: BTCUSDT-PERP, ETHUSDT-PERP (highest volume)
- Bybit: BTC-PERP, ETH-PERP (good for funding rate data)
- dYdX: BTC-USD, ETH-USD (decentralized, different patterns)

### Secondary
- Coinbase: BTC-USD, ETH-USD (spot, for basis comparison)
- FTX historical data (if available, for longer history)

### Features to Extract
- Price: Open, High, Low, Close (1-min)
- Volume: Total, buy, sell (if available)
- CVD: Cumulative volume delta
- Funding Rate: 8-hour rate
- Open Interest: Total contracts outstanding
- Liquidations: Forced closure data (if available)

## Next Steps

1. **Data Collection**: Gather 90 days of 1-minute data
2. **Pattern Recognition**: Identify margin window moves
3. **Statistical Testing**: T-test for significance
4. **Robustness Checks**: Different time windows, instruments
5. **Real-Time Monitoring**: Track effect going forward
6. **Strategy Development**: Create trading rules if confirmed

## Related Hypotheses

- **Funding Rate Cascade**: Similar effect at funding times
- **Session Open Reversals**: Reversals at major session opens
- **Weekend Gap Fills**: Crypto gaps filling on Sunday opens
- **Maintenance Window Moves**: Exchange maintenance impact

## Notes

- Effect may vary by market regime (bull/bear)
- May be stronger during high volatility periods
- Could be arbitraged away as more traders discover it
- Requires continuous monitoring as market structure evolves