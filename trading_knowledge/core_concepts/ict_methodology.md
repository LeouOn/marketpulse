# ICT Methodology

`ICT` (Inner Circle Trader) is the framework developed by Michael Huddleston that synthesizes market structure, session timing, and institutional order flow into a single decision process. This document is the playbook layer. It assumes you already know the primitives. If you need the definitions of `FVG`, `Order Block`, `BOS`, `ChoCh`, `liquidity_sweep`, or `Kill Zone`, see `market_structure.md` first. The primitives are the vocabulary; this doc is the grammar.

The core claim of ICT is that price is not random. It moves between institutional decision points called PD arrays in a predictable cycle (accumulation, manipulation, distribution) at predictable times (the `Kill Zone` windows). A high-probability trade is the intersection of all three: the right time, the right price level, and the right confirmation.

## PD Arrays (Premium / Discount Arrays)

A PD array is a cluster of institutional decision points at a single price region. It is the level where the algorithm is most likely to react.

### Anatomy of a PD Array

A PD array is built from three to four overlapping elements: a swing high or swing low (the boundary of the move), an `FVG` inside that swing (the imbalance), an `Order Block` at the origin of the move (the institutional footprint), and optionally a `BPR` (break and retest of an internal level). When two or more elements stack at the same price, you have a PD array. Single-element levels are weak. Stacked levels are strong.

### Premium vs Discount

The current price determines which arrays matter. Discount (below the 50% equilibrium of the current range): only look for longs. Premium (above the 50% equilibrium): only look for shorts. Buys below the 50% line, sells above it. This single rule eliminates the majority of bad trades.

### Why Arrays Matter

Institutions cannot enter size at market. They need resting limit orders at a level. PD arrays are where those resting orders live. Price returns to the array, the institution fills, and the move continues in the direction of the higher timeframe bias. The array is a delivery mechanism, not just a technical level.

## Power of 3 (`PO3`)

`PO3` is the session cycle. Every trading session in `ICT` follows three phases:

1. **Accumulation** (first part of the session). Price ranges. Institutions build positions. The range high and range low are the boundaries of the day.
2. **Manipulation** (middle of the session). Price fakes out one side of the range, triggering stops and pulling in retail flow. This is the Judas Swing. The stop run marks the true directional extreme.
3. **Distribution** (final part of the session). The real move begins. Price drives in the direction of the day's bias, often running through the opposite liquidity pool.

For a New York session: accumulation in the first 30-60 minutes, manipulation around 10:00-11:00 ET, distribution from 11:00 onward into the close.

## ICT 2022 Model

The 2022 model is the canonical time-and-price map for trading the NYSE session.

### AM Session (9:30 - 12:00 ET)

- **9:30 - 10:00**: Judas Swing window. The first move after the open is typically opposite the day's true direction.
- **10:00 - 11:00**: Silver Bullet window (see below).
- **11:00 - 12:00**: Continuation. If the bias is established and a PD array tapped, this is where the real move runs.

### Lunch Chop (12:00 - 13:00 ET)

Generally avoided. Volume thins, ranges narrow, and most moves are noise. Exception: if a setup is already in motion, manage it. Do not initiate fresh positions here.

### PM Session (13:00 - 16:00 ET)

- **13:00 - 14:00**: Continuation or reversal of the AM move. AM session PD arrays become targets.
- **14:00 - 15:00**: Setup window for the close.
- **15:00 - 16:00**: Power Hour. Position squaring, often a final drive in the day's direction.

The 2022 model is "when to look." Combine it with PD arrays and you have a complete trade.

## Judas Swing

The Judas Swing is the opening false move. The market "kisses" one direction before going the other.

### Identification

- The first 15-30 minutes of a session establish the opening range.
- The Judas Swing is the break of that range in one direction, followed by a reversal.
- It most commonly appears between 9:30 and 10:00 ET on NYSE equities and `NQ`.

### How to Use It

If the daily bias is bullish and the Judas Swing sweeps the opening range low, you have a long entry signal at the PD array inside that low. The stop goes below the sweep. The target is the opposite liquidity pool (opening range high or prior session high).

The Judas Swing fails when the opening range break is the real move (trend days). See the failure modes below.

## Silver Bullet (10:00 - 11:00 ET)

The Silver Bullet is a specific one-hour window where ICT methodology says high-quality short setups appear. The 10:00-11:00 ET window is the primary one for `NQ`.

### Why This Window

By 10:00 ET, the London session is closed, the AM Judas Swing has played out, and real institutional orders begin to flow. The 10:00 hour is the start of distribution in the `PO3` cycle for the US session. Short setups here benefit from clearer HTF bias, defined risk (the AM session high or low is a tight stop reference), and larger moves (distribution runs longer than manipulation).

### Setup

For a short: HTF bearish bias, AM session high identified, price taps a premium PD array inside that high, displacement candle down confirms entry. For a long: mirror conditions with a discount array.

The Silver Bullet is a time filter, not a strategy on its own.

## Turtle Soup

A Turtle Soup is a failed break of structure used as a reversal signal. The name comes from the original "Turtle Traders" trend-following system; this setup fades their stops.

### Bullish Turtle Soup (short signal)

1. Price sweeps above a recent swing high.
2. The candle closes back inside the range.
3. The sweep creates a long upper wick.
4. A PD array sits just above the swept high (sell-side liquidity was resting there).
5. Enter short on the close of the sweep candle or on the retest of the wick. Stop above the sweep high.

### Bearish Turtle Soup (long signal)

Mirror: sweep below a swing low, close back inside, wick below, enter long, stop below the sweep low.

The Turtle Soup is the most precise `liquidity_sweep` pattern. It confirms institutions needed that liquidity and are now done. The reversal is high-probability when it occurs at a PD array inside a Kill Zone.

## Optimal Trade Entry (`OTE`)

`OTE` is the 62-79% Fibonacci retracement of the most recent impulsive move, taken in the direction of the higher timeframe bias. It is the specific price level where you enter.

### Drawing the Fib

1. Identify the most recent impulsive move (a strong displacement candle sequence).
2. Draw the Fibonacci from swing low to swing high (for longs) or swing high to swing low (for shorts).
3. The 62% and 79% levels are the entry zone. The 70.5% level is the most commonly cited midpoint.

The Fibonacci is not magic. It works because institutions scale into positions at predetermined levels, and the 62-79% zone is where their limit orders cluster.

### Combining with PD Arrays

A high-probability `OTE` entry requires the Fib level and a PD array to overlap. A Fib alone is weak. A PD array alone is good. Both stacked is excellent. The best trades are when the 70% Fib lands directly inside an `Order Block` or `FVG` at a premium or discount level.

## Institutional Order Flow

The primitives (`liquidity_sweep`, displacement candles, `FVG`, breaker blocks) are covered in `market_structure.md`. The synthesis layer is "why do institutions cause these."

### Stop Hunts

A `liquidity_sweep` is a stop hunt. Institutions need the other side's liquidity to fill their orders. They push price through obvious swing points to trigger retail stops, then use that liquidity to enter. The sweep is the entry, not noise.

### Rebalancing

Displacement candles and `FVG`s are rebalancing moves. When a large institution enters, order flow creates an imbalance. Price moves fast through the level where their orders sat, leaving an `FVG` behind. That `FVG` is the institutional footprint. When price returns to the `FVG` (the `mitigation`), it is testing whether the institution is still there. If the level holds, the position is still working.

### The Cycle

Liquidity sweep (entry), displacement (fill), FVG (footprint), mitigation (retest), continuation (distribution). This is the same `PO3` cycle at the price level. Time and price run the same pattern.

## Entry Checklist

The operational version of the framework. A trade that does not clear every step is skipped.

1. **HTF bias established.** Daily or 4H chart shows clear direction via `BOS` or `ChoCh`. No range.
2. **Kill Zone active.** Inside a `Kill Zone` window (London 02:00-04:00, NY AM 09:30-12:00, Silver Bullet 10:00-11:00, PM 13:00-16:00).
3. **LTF `MSS` confirmed.** On the 5-minute or 15-minute chart, a Market Structure Shift has printed in the direction of HTF bias.
4. **PD array tapped.** Premium array (shorts) or discount array (longs) reached. Array contains `Order Block`, `FVG`, or both. See `market_structure.md`.
5. **Entry model selected.** Choose one: (a) `OTE` Fib 62-79% inside the PD array, (b) `BPR` retest, or (c) `mitigation` of the `FVG` from MSS displacement.
6. **Confirmation signal.** At least one of: displacement candle, volume spike, or `CVD` divergence with the sweep.
7. **Risk defined.** Stop placed beyond the PD array (below OB or FVG for longs, above for shorts).
8. **Target identified.** Minimum 2:1 R:R. Primary target is the opposing liquidity pool.
9. **Kill Zone validity check.** If more than 30 minutes past Kill Zone close, reduce size or skip.
10. **No news conflict.** If a high-impact release is inside the next 15 minutes, do not enter.

If all ten conditions are met, take the trade at the next candle open after confirmation. If any condition is unclear, the answer is no.

## PD Array Trade Example: NQ Long

Setup: 10:15 ET, Tuesday. NQ is in a daily uptrend. HTF bias is bullish.

**Step 1 (Judas Swing):** NQ opens at 15,200. First 15 minutes push down to 15,180, sweeping the prior day's low at 15,182. The 09:45 candle closes back above 15,200 with a long lower wick. Judas Swing low confirmed.

**Step 2 (MSS):** On the 5-minute chart, the 09:50 swing high at 15,220 is taken out by a strong bullish displacement candle at 10:08. LTF `MSS`. Structure shifted bullish on the entry timeframe.

**Step 3 (PD array):** The displacement candle left a `FVG` between 15,215 and 15,218. Above it at 15,225 sits a bullish `Order Block` from the prior day. Both are in discount relative to the dealing range (high 15,280, equilibrium 15,240).

**Step 4 (Entry):** Price pulls back to 15,216. The `OTE` Fib from the 09:50 swing low to the 10:08 swing high lands 70% at 15,215. Fib, `FVG`, and discount zone are stacked. Pullback candle shows declining volume and a small body (absorption). Entry at 15,216.50.

**Step 5 (Risk):** Stop below the `Order Block` at 15,222 (~5.5 points risk on MNQ). Target is the opposing liquidity pool at the prior swing high 15,250 (~6:1 R:R).

**Step 6 (Management):** Price bounces from the `FVG`, retests entry as support, then runs. Half closed at 15,245. Stop on remainder to breakeven at 15,217. Final target 15,250 hit at 11:42.

The sequence is what matters: HTF bias, Judas Swing, LTF `MSS`, PD array in discount, stacked confirmation, defined risk. The framework stays the same; the levels change with the chart.

## When ICT Setups Fail

The framework is not infallible. Honest acknowledgment of failure modes is part of the methodology.

### Trend Days

On strong trend days, the Judas Swing does not reverse. The opening range break IS the move. Rule: if daily ATR is exceeded in the first 30 minutes and displacement is sustained, do not fade it. Wait for the next session.

### News Events

FOMC, CPI, NFP, and other high-impact releases override Kill Zone logic. A setup that looks textbook at 09:55 will fail at 10:00 when the print drops. Rule: do not enter inside the 15-minute window before a known release. After the release, wait for the post-news PD array to form.

### Low Liquidity Sessions

Holiday sessions, summer doldrums (mid-July through mid-August), and days around US holidays produce thin books. Judas Swings are noisier, displacements smaller, `FVG`s fill instantly. Rule: reduce size by half or sit out.

### Conflicting HTF Bias

If the daily and 4H charts disagree on direction, no setup is valid. Rule: no clear HTF bias, no trade.

### Late Entries

An ICT setup at 11:45 ET has lower expectancy than the same setup at 10:15 ET. By 11:45, the AM distribution has already run and the lunch chop is starting. Rule: trades taken more than 30 minutes past a Kill Zone peak are downgraded in size or skipped.

### Pure FVG Reliance

A `FVG` by itself is not a setup. It is one element of a PD array. Trading naked `FVG`s without order flow confirmation, bias alignment, and session timing produces low win rates. See `market_structure.md` for the FVG primitive; remember it is necessary but not sufficient.

## Summary

`ICT` is a time, price, and confirmation framework. The time comes from `Kill Zone` windows (most importantly the 10:00-11:00 ET Silver Bullet). The price comes from PD arrays at premium or discount, identified through `FVG`, `Order Block`, and `BPR` elements. The confirmation comes from displacement, volume, `CVD` divergence, and the Judas Swing. The entry model is `OTE` (62-79% Fib) inside the array, in the direction of the higher timeframe bias, on a confirmed LTF `MSS`. The cycle is `PO3` (accumulation, manipulation, distribution), repeated every session. The framework fails on trend days, at news, in thin liquidity, and when the HTF bias is unclear. Skip those. The rest are the high-probability ones.
