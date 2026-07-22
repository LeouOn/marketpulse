# Market Regimes

A regime is the character of the market right now. It decides which setups belong in your playbook and which don't. Before you take any trade, answer four questions: is price trending, how volatile is it, how heavy is participation, and what phase is the move in? If you can't answer all four, you're trading blind.

This document is the decision layer that sits above entries and sizing. Entries live in `ict_methodology.md`. Sizing math lives in `risk_management.md`. Read those next, but read this first to know what game you're playing.

## The Four Dimensions

Every market sits somewhere on each of these four axes at the same time. The combination tells you the regime.

1. **Direction.** Trending up, trending down, or ranging. Use HH/HL or LL/LH counts over the last 5 to 10 sessions, as defined in `market_structure.md`.
2. **Volatility.** Low, normal, high, or extreme. Read it from VIX, ATR(14), and today's range vs the 20-day average range.
3. **Participation.** Thin (Asia, lunch, holidays), normal, or heavy (FOMC, NFP, market open, options expiry). Which `kill_zone` you're in matters more than the clock.
4. **Phase.** Trend-start, trend-mature, trend-end, or reversal-setting-up. This is the one that costs you money when you get it wrong.

When all four align, your confidence is high. When they conflict, sit out or cut size. Conflicting dimensions are how experienced traders blow up.

---

## Trending Market

Direction has a clear lean. Volatility is usually normal or rising. The move keeps making progress in one direction with sustained `momentum`.

### What to do

- Trade pullbacks to `Order Block`s or `FVG`s in the trend direction. Don't predict tops on the third pullback, ride until structure breaks.
- Take ICT setups aligned with the higher timeframe. HTF bullish plus a 15m `Order Block` tap during NY `kill_zone` is a clean entry.
- Trade breakout-and-retest. The first push through resistance often fails; the retest of broken resistance as support is the real entry.
- Hold partial runners. Trends pay you to be patient, so don't close at 1R if structure is intact.

### What NOT to do

- Don't take `mean_reversion` setups. "This is overbought" is how you short a trend that runs another 10 handles against you.
- Don't `fade` strength. Selling the first red candle in an uptrend is gambling.
- Don't size up just because you "feel" the trend is strong. That's the pyramiding intuition trap.
- Don't expect V-top reversals without a structural break first.

### Position sizing

NORMAL. Trend confirmation doesn't change math, it changes frequency. Keep size at your standard 1R risk and let the trade count do the work.

---

## Ranging Market

Price is bouncing between clear horizontal support and resistance. Multiple touches, declining volume, no real progress. `momentum` is flat. This is a `mean_reversion` environment.

### What to do

- Sell at range high, buy at range low. Place stops just outside the boundary and target the opposite side.
- Take OTE setups on the range's `Order Block`s. The range extremes are themselves OBs.
- `fade` breakouts that fail to close outside the range. The first push often traps breakout traders.
- Cut winners at the midpoint. Ranges are mean-reverting, so don't expect runs.

### What NOT to do

- Don't trade `breakout` setups. The trader who keeps buying the high in a range bleeds slowly until they catch a fakeout that runs 40 ticks against them.
- Don't trend-follow. There's no trend to follow, so every "this is the start" trade is a guess.
- Don't increase size on a "breakout" signal that turns out false. Half the time it works isn't a strategy.
- Don't hold overnight unless the range is unusually tight and you have a clear event tomorrow.

### Position sizing

REDUCED. `mean_reversion` win rates are lower than trend-following. Drop to half your normal size until you have 5 to 10 trades in this regime confirming the boundary holds. The win rate has to be there before you scale.

---

## High Volatility / Chaotic

VIX over 25, wide intraday ranges, news in progress, gap opens, news-driven whipsaws. The market is loud but not necessarily directional. This is where most accounts die.

### What to do

- Sit out. The best trade is often no trade.
- If you must play it, wait 15 to 30 minutes after the event for direction to confirm, then take only the cleanest post-news reaction setup with a clear stop.
- Trade `scalping` only if that's your primary methodology and you've practiced it in this regime.
- Use wider stops and smaller size. Volatility expansion means your normal stop gets run even when you're right.

### What NOT to do

- Don't scalp aggressively. Wide ranges and tight stops equal getting stopped out then watching it run 50 ticks in your original direction.
- Don't add to losers. "It'll come back" is the most expensive sentence in trading, and it's twice as true on FOMC days.
- Don't trade out of boredom. The market is loud but offers nothing. Closing the charts is a valid trade.
- Don't use the same setups you used yesterday. Yesterday's `FVG` entries work in normal vol; today they get run by 30-handle swings.

### Position sizing

HALVED. High volatility amplifies both wins and losses equally. Your losing trades will be physically larger without any edge increase. Half size keeps dollar risk constant.

---

## Low Volatility / Compressed

VIX under 12, narrow ranges for several sessions, ATR(14) declining. The market is quiet. Something is loading.

### What to do

- Look for pre-`breakout` positioning using Wyckoff accumulation or distribution patterns. Springs, upthrusts, and range contractions near a level matter.
- Reduce trading frequency. Setups are rare and small. Force trades and you give back yesterday's gain.
- Wait for expansion before sizing up. The first big bar is your signal.
- Mark the levels and set alerts. Compression is for planning, not acting.

### What NOT to do

- Don't force `scalping` in a 40-tick range. You're paying commissions to make 4 ticks.
- Don't expect directional follow-through on weak breakouts in compressed vol. The first push often fails.
- Don't size up "because vol is low." Low vol means small dollar moves, not safer trades.
- Don't ignore the setup entirely. Compression before expansion is where the biggest moves start. Have your orders staged.

### Position sizing

NORMAL. If you're anticipating an imminent breakout, REDUCED until the breakout direction confirms. Uncertainty is not a reason to add risk.

---

## Regime Identification Tools

You need a fast read on each dimension. Here's the toolkit.

- **Price action.** Count HH/HL or LL/LH over the last 5 to 10 sessions, as `market_structure.md` describes. Three of each in a row is a trend.
- **Volatility.** VIX for the broad read, ATR(14) for the local read. Compare today's range to the 20-day average range: above 1.5x is high, below 0.7x is compressed.
- **Breadth.** When you have it, the percentage of S&P 500 names above their 20-day MA. Above 60% supports uptrends, below 40% supports downtrends.
- **Time-based.** Which `kill_zone` is active. Asian range usually sets the day's boundaries, London breaks them, NY either continues or reverses.
- **Composite.** When all four dimensions point the same direction, your read is high-confidence. When they conflict, you're in a transition. Trade like it's a transition, not a trend.

---

## Regime Transitions

This is where the money is and where the losses come from. Transitions are when the regime you identified yesterday stops being true.

- **Trend-start.** Best risk-reward of any phase. Early in a new trend, enter on the first or second pullback and target a multi-day move. Don't be late, but don't be the first person in either. Wait for the structure break, then trade the first pullback.
- **Trend-mature.** Trend-following still works. Smaller targets, tighter trailing stops. Most of your trades live here.
- **Trend-end.** The setup graveyard. The trend is breaking but the old playbook still fires. Every pullback entry is a trap. Cut size by half until you see clear reversal structure.
- **Reversal-setting-up.** Distribution at the top, accumulation at the bottom. Two-legged moves, expanding volatility at the boundary, divergence between price and `momentum`. Don't catch the first reversal. Wait for HTF confirmation, then trade the breakout of the reversal range.
- **Volatility expansion after compression.** Compressed vol resolves directionally. Bias in the direction the prior compression was leaning.

The "this time is different" trap lives at trend-end. You see the trend is older, you feel the top, and you start fading strength before structure breaks. That trade works 1 time out of 5 and loses 5R the other 4. Wait for the break.

---

## Decision Framework

| Regime | Setup preference | Size | Key risk |
|---|---|---|---|
| Trending | Pullbacks, ICT HTF-aligned, breakout-retest | NORMAL | `mean_reversion` against the trend |
| Ranging | Sell high, buy low, `fade` false breakouts | REDUCED | `breakout` traps at the boundary |
| High vol / chaotic | Sit out, or post-news reaction only | HALVED | `scalping` into news, adding losers |
| Low vol / compressed | Wait, or Wyckoff pre-breakout | NORMAL | Forcing `scalping` in tight ranges |
| Trend-start | First/second pullback in new trend | NORMAL | Being too early, predicting the top |
| Trend-end | Sit out, or HTF-confirmed reversal | HALVED | Fading before structure breaks |

---

## Quick Reference

Before every session, write down:

- Direction?
- Volatility level?
- Participation level (which `kill_zone`)?
- Phase of the move?

If you can't fill in all four in under a minute, you're missing context. Sit out. Regime confusion is the number one cause of "I had no business taking that trade."

When the regime changes mid-session, respect it. Close what no longer fits and step down in size. The trade that made sense at 9:30 may be suicide at 11:00.