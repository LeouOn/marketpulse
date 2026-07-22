# Liquidity Cascade Patterns Hypothesis

## Hypothesis Statement
Five calendar-anchored events are claimed to produce detectable cascades in futures and crypto perpetuals: (1) monthly OPEX Friday close at 16:00 ET (gamma plus MOC rebalancing in NQ/ES); (2) FOMC window at 14:00 ET (volatility compressed into 13:30-14:30 ET); (3) crypto funding resets at 00:00, 08:00, 16:00 UTC when |funding| > 0.10%/8h amplify the prevailing trend; (4) Sunday 18:00 ET equity reopen (Friday-to-Sunday gap correlates with Monday opening range); (5) quarter-end Mar/Jun/Sep/Dec (pension rebalancing produces larger NQ MOC imbalances and pinned closes than quarter-mid dates).

## Background
Microstructure literature documents calendar liquidity anomalies around scheduled macro events. Crypto perpetuals add a second layer through the 8-hour funding cadence. Each pattern isolates a distinct driver so the signal can be tested independently.

## Mechanism
1. **OPEX Friday**: Dealers hedge short-dated index options into 16:00 ET gamma and charm. MOC orders concentrate; NQ and ES pin to strikes
2. **FOMC Window**: At 14:00 ET the FOMC releases the statement; press conference at 14:30 ET. Quote depth withdraws 15-30 minutes ahead
3. **Funding Reset Cascade**: When |funding| > 0.10%/8h, the paying side closes before the snapshot. Forced rotation triggers liquidations
4. **Sunday Gap-and-Fill**: Equity futures reopen 18:00 ET Sunday after 53 hours electronic-only. The Friday gap is re-tested Monday, with 09:30-09:45 ET opening range absorbing much of the fill
5. **Quarter-End MOC Pin**: Pensions rebalance on the last trading day of Mar/Jun/Sep/Dec. Imbalances concentrate in MOC orders 15:50-16:00 ET, pinning NQ

## What to Look For

### Price Action Patterns
- **OPEX Friday**: 15:45-16:15 ET range wider than non-OPEX Fridays
- **FOMC Window**: NQ 13:30-14:30 ET range wider than the same 30-min window on the prior trading day
- **Funding Reset Cascade**: When |funding| > 0.10%/8h, directional continuation in 30 min around the reset stamp
- **Sunday Gap-and-Fill**: Sunday 18:00 ET gap vs Friday 17:00 ET close predicts Monday 09:30-09:45 ET opening range width
- **Quarter-End MOC Pin**: NQ closing print on the last trading day of Mar/Jun/Sep/Dec sits closer to at-the-money strike than quarter-mid dates

### Volume Characteristics
- **OPEX Friday**: NQ volume 15:45-16:15 ET is 1.5-2.5x non-OPEX Fridays; MOC imbalance skews by gamma sign
- **FOMC Window**: Volume 13:30-14:30 ET is 2-3x prior-day matched window
- **Funding Reset Cascade**: Volume at funding reset spikes 1.5-2x baseline when |funding| > 0.10%/8h
- **Sunday Gap-and-Fill**: NQ volume in the first 15 minutes of Sunday 18:00 ET and Monday 09:30 ET both elevated
- **Quarter-End MOC Pin**: MOC order imbalance on quarter-end days exceeds quarter-mid days

### Market Conditions
- **OPEX Friday**: More pronounced on quarterly-OPEX months (Mar/Jun/Sep/Dec)
- **FOMC Window**: SEP and dot plot meetings carry larger volatility than non-Sep meetings
- **Funding Reset Cascade**: High-leverage regime amplifies the magnitude
- **Sunday Gap-Fill**: Larger gaps after weekend macro news; smaller gaps into FOMC weeks
- **Quarter-End MOC Pin**: Effect strongest when index YTD diverges from policy benchmark by more than 50 bps

## Testing Criteria

### Statistical Requirements
- Statistical significance: p < 0.05
- Sample size: N >= 90 (N = number of qualifying events per pattern)
- Consistency: 60% of qualifying periods show the pattern
- Magnitude: average move > 0.5% within the relevant event window

### Data Requirements
- **Instruments**: NQ futures (CME), ES futures (CME), BTC-PERP and ETH-PERP (Binance, Bybit)
- **Timeframe**: 1-minute and 5-minute bars around each event window; daily OHLC for gap calculations
- **Features**: Price (OHLC), volume (total, buy, sell where available), CVD, funding rate, open interest, MOC order imbalance where available, VIX intraday
- **Control**: Matched clock-time windows on non-event days

### Success Metrics
1. **OPEX Friday**: NQ 15-min realized volatility at 15:45-16:15 ET on OPEX Fridays is statistically greater than non-OPEX Fridays (Welch's t-test, p < 0.05)
2. **FOMC Window**: NQ 30-min realized volatility at 13:30-14:30 ET on FOMC days exceeds matched prior-day window with p < 0.05
3. **Funding Reset Cascade**: Directional move in BTC-PERP 30 minutes around extreme-funding resets exceeds matched non-extreme windows; consistency > 60%
4. **Sunday Gap-Fill**: Correlation between |Friday-to-Sunday gap| and Monday opening range magnitude > 0.3 with p < 0.05
5. **Quarter-End MOC Pin**: NQ MOC order imbalance on quarter-end days exceeds quarter-mid days; close-to-strike deviation smaller on quarter-ends

## Related Concepts

### Funding Rate Pressure
- High positive funding = longs paying shorts; high negative funding = shorts paying longs. Funding at 00:00, 08:00, 16:00 UTC are the trigger points.

### Cross-Margin vs Isolated Margin
- Cross-margin faces portfolio margin calls around funding; isolated-margin only per-trade margin, dampening cascade on dYdX.

### Liquidation Cascades
- Forced liquidations mark local extremes at the funding reset, similar to the 00:00 UTC pattern in overnight_margin_cascade.

### Traditional Market Correlation
- Equity index MOC rebalancing overlaps mutual fund quarter-end window dressing.

## Potential Confounding Factors
1. **Macro Overlap**: FOMC days occasionally fall on OPEX Fridays (4-6x per decade), combining both patterns
2. **News Events**: Geopolitical shocks on Friday close or Sunday reopen can dominate the gap pattern
3. **Exchange Maintenance**: Crypto maintenance overlapping a funding reset changes the price-discovery venue
4. **Whale Activity**: Single large fills around 16:00 ET or funding stamps mimic the cascade signature
5. **Daylight Saving Time**: ET clock shifts vs UTC funding stamps twice yearly

## Risk Factors

### False Positives
- Random volatility around event windows when no macro release coincides; funding arbitrage activity unrelated to extreme funding regimes; single large institutional order at 16:00 ET unrelated to OPEX; cross-asset contagion from a non-scheduled event

### False Negatives
- Effect diluted across multiple trading venues if only one feed is sampled; crypto exchanges with longer funding intervals (4h or 1h) break the 8h cadence assumption; pension rebalancing increasingly automates across multiple days

## Trading Implications

### If Hypothesis Confirmed
1. **Pre-Event Positioning**: Scale in 15-30 minutes before each event window with stops sized to the historical range
2. **OPEX Fade**: Mean-revert stretched NQ closes during 15:45-16:15 ET on OPEX Fridays toward the dealer-neutral strike
3. **FOMC Straddle**: Buy 13:30-14:30 ET NQ straddles on FOMC days when realized vol under-prices the window
4. **Funding Cascade**: Trade with the prevailing direction at funding reset when |funding| > 0.10%/8h
5. **Sunday Gap Fade**: Trade toward Friday close from the Sunday 18:00 ET gap extreme if gap > 1%; exit at Monday 09:45 ET

### Position Sizing
- Reduce size during FOMC and OPEX overlap sessions; increase size on quarter-end days; time-based stops preferable to price-based around funding resets

## Data Sources

### Primary
- Binance: BTCUSDT-PERP, ETHUSDT-PERP; Bybit: BTC-PERP, ETH-PERP; CME: NQ (1-min); ES for spread context

### Secondary
- CBOE: VIX intraday; Coinbase: BTC and ETH spot; Fed calendar: official FOMC dates

### Features to Extract
- Price: OHLC (1-min); Volume: Total and buy/sell when available; CVD (L2-derived); Funding Rate: 8-hour by exchange; Open Interest: change around event; MOC Order Imbalance where available; Calendar Markers: OPEX, FOMC, quarter-end, funding-extreme flags

## Next Steps
1. **Event Calendar**: Encode all five event types into a calendar flag set with ET/UTC timestamps
2. **Data Collection**: Pull 90+ qualifying events per pattern from cached data
3. **Pattern Recognition**: Compute realized volatility in event vs control window
4. **Statistical Testing**: Welch's t-test per pattern; ANOVA for joint significance
5. **Robustness Checks**: Sub-period, regime splits (VIX above/below 20), per-instrument
6. **Composite Score**: Combine z-scores across patterns into a daily cascade probability feature
7. **Strategy Development**: Convert confirmed patterns into entry/exit rules

## Related Hypotheses
- **Overnight Margin Cascade**: Sibling covering 00:00 UTC margin cascade on green days; this doc extends to all three funding resets and both directions
- **Funding Rate Cascade**: Targets funding-driven moves regardless of magnitude; this doc adds an extreme-funding threshold
- **Session Open Reversals**: Overlap with Sunday and Asia open patterns
- **Quarterly OPEX Pinning**: NQ pins to strikes at all four quarter-ends; this doc focuses on MOC-order-imbalance signature

## Notes
- Effect magnitude varies by regime: high-VIX amplifies cascades; low-VIX dampens them.
