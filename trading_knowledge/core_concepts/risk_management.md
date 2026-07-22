# Risk Management

The structured side of trading: how much to risk per trade, when to stop, and how to size up or down. Assumes a futures trader working primarily with MNQ ($20/point, $5/tick). Refer to `position_sizing`, `max_drawdown`, `risk_reward`, `win_rate`, `expectancy`, and `sharpe_ratio` in the glossary for foundational definitions.

## 1. The 1% Rule

Risk a fixed percentage of account equity per trade. The number comes out of the math: a streak of 1% losses is survivable; a streak of 5% losses is not. The 1% rule survives normal losing streaks.

**Formula:**

```
risk_dollars = account_equity × risk_pct
risk_per_contract = (entry - stop) × point_value
contracts = risk_dollars / risk_per_contract
```

For MNQ: `point_value = 20`, `tick = 0.25 points = $5 per tick`.

**Worked example (MNQ):** $25,000 account, 1% risk = $250. Entry 18,500, stop 18,490 (10 points). Risk per contract = 10 × $20 = $200. Contracts = $250 / $200 = 1.25, round DOWN to 1. The trade risks $200 (0.8% of account). Math rounds against you; accept the rounding, do not push to 2 contracts to hit exactly 1%.

**Sizing table (MNQ, 10-point stop = $200/contract risk):**

| Account Size | 1% Risk | Contracts | Effective Risk |
|--------------|---------|-----------|----------------|
| $5,000       | $50     | 0         | 0              |
| $10,000      | $100    | 0         | 0              |
| $20,000      | $200    | 1         | 1.00%          |
| $50,000      | $500    | 2         | 0.80%          |
| $100,000     | $1,000  | 5         | 1.00%          |
| $250,000     | $2,500  | 12        | 0.96%          |

Sub-$20k accounts with 10-point MNQ stops are stuck at 1 contract or zero. Either tighten the stop (only if the setup warrants it) or trade MES ($5/point). Do not widen the stop to force a position.

**Why 2% is the cap, not 5%:** ten consecutive losses leaves you at 90.4% (1% risk), 81.7% (2%), or 59.9% (5%). Ten losses is routine for any strategy under 70% `win_rate`. The 1% rule keeps you in the game.

**Rule:** Risk 1% per trade, 2% absolute cap. If the math gives you zero contracts, the account is too small for the setup, not the other way around.

## 2. Session, Daily, and Weekly Loss Limits

Hard stops that override any setup. Once hit, you are done for the period.

**Standard framework:**

| Period     | Max Loss      | Action                                   |
|------------|---------------|------------------------------------------|
| Per trade  | 1% of equity  | Stop is the stop. No averaging down.     |
| Per session| 1% of equity  | Stop trading for the rest of the session.|
| Per day    | 2% of equity  | Close platform, walk away, journal.      |
| Per week   | 5% of equity  | Sit out the rest of the week.            |

"Walk away" is concrete: cancel all orders, close the platform window (not minimize), journal the day with screenshots, leave the desk. Do not reopen until the next session. Sitting at the desk with a closed platform is revenge trading waiting to happen.

**Rule:** Hit the daily -2% limit and the platform closes. Hit the weekly -5% limit and you do not trade the rest of the week, including the weekend.

## 3. R-Multiple Thinking

R is a unit of risk. Define R as the dollar amount risked on the entry. A 2R winner returns twice the risk; a 0.5R loss returns half.

**Formula:**

```
trade_R = (exit_price - entry_price) / (entry_price - stop_price)   [long]
trade_R = (entry_price - exit_price) / (stop_price - entry_price)   [short]
```

Win or loss, R is signed. A -1R loss is a full stop-out. A +3R win is three times the risk captured.

**Expectancy formula:**

```
expectancy = (win_rate × avg_win_R) - ((1 - win_rate) × 1)
```

40% `win_rate` with 3R average wins: `expectancy = (0.4 × 3) - (0.6 × 1) = 1.2 - 0.6 = 0.6R per trade`. Positive expectancy means the strategy makes money over many trades regardless of any single outcome.

**Win-rate vs avg-R combinations (expectancy per trade):**

| Win Rate | Avg Win | Avg Loss | Expectancy |
|----------|---------|----------|------------|
| 70%      | 0.5R    | 1.0R     | -0.15R     |
| 60%      | 1.0R    | 1.0R     | +0.20R     |
| 50%      | 1.5R    | 1.0R     | +0.25R     |
| 45%      | 2.0R    | 1.0R     | +0.35R     |
| 40%      | 3.0R    | 1.0R     | +0.60R     |
| 30%      | 4.0R    | 1.0R     | +0.50R     |

70% wins with 0.5R targets is a losing strategy. 40% wins with 3R targets is winning. Track every trade in R units, not dollars, so you can see the real `edge` independent of contract size.

**Rule:** Measure every trade in R. A strategy is good when expectancy > 0 over 30+ trades, regardless of win rate alone.

## 4. Fixed-Fractional vs Kelly Sizing

Fixed-fractional is the 1% rule from Section 1. Kelly sizes based on your `edge`.

**Full Kelly formula:**

```
f* = W - (1 - W) / R
```

W = `win_rate` (decimal), R = avg win size / avg loss size. Example: 40% wins, 3:1 reward-to-risk → `f* = 0.4 - 0.6/3 = 0.4 - 0.2 = 0.20` = 20% of account per trade.

Full Kelly is mathematically optimal for long-run bankroll growth but assumes perfect estimates of W and R, no drawdown tolerance, and no emotional survival. Use fractional Kelly.

**Fractional Kelly:**

| Fraction        | Position Size  | Use Case                                     |
|-----------------|----------------|----------------------------------------------|
| Full (1.0)      | 20% of equity  | Academic optimum. Drawdowns will destroy you.|
| Half (0.5)      | 10%            | Aggressive. Still too much for most traders. |
| Quarter (0.25)  | 5%             | Aggressive but survivable. Comp traders only.|
| Eighth (0.125)  | 2.5%           | Conservative. Reasonable ceiling.            |
| **Standard**    | **1%**         | **Fixed-fractional. Ignores Kelly entirely.**|

Most traders cap at 1-2% per trade, well below even fractional Kelly. The extra edge is wiped out by execution errors, emotional mistakes, and parameter uncertainty. Quarter-Kelly on a $25k account with a 10-point MNQ stop = 5% risk = 6 contracts. One bad session can take out a week of `expectancy`. Fixed-fractional 1% gives 1 contract.

**Rule:** Size at 1% fixed-fractional. Treat Kelly as a ceiling check, not a target.

## 5. Scaling In vs Scaling Out

Both techniques add or trim exposure mid-trade. Opposite risk profiles.

**Scaling out (partial profits):** enter full size, close 1/3 to 1/2 at predefined R multiples (1R, 2R, 3R), move stop on remainder to breakeven once 1R is locked. Lets the trade work without giving back open profits. Best for `risk_reward` setups with multiple measured targets (S/R levels, fibs, prior swings).

Worked example (MNQ long): entry 18,500, stop 18,490 (1R = $200). 5 contracts in. Price hits 18,510 (1R). Sell 2, lock +$400. Move stop on remaining 3 to 18,500. Trade is now free.

**Scaling in (adding to winners):** enter with half or third of intended size, add the rest only if price moves past a confirmed level. Each add gets its own stop moved to breakeven of that entry. Average winning price, never losing price. Best for trend trades with multi-bar continuation.

Scaling in with stops at breakeven of each entry means the total position has zero downside once the first add triggers.

**Do not scale in on a losing trade.** "Averaging down" is a way to lose 5R instead of 1R.

**Rule:** Scale out at predefined R multiples, never scale in against your trade direction.

## 6. Size Down on Vol, Reduce on Losing Streaks

Mechanical rules that override judgment when judgment is the problem.

**Volatility adjustment:** use ATR on the entry timeframe. If today's ATR is 1.5× the 20-day average, reduce position size proportionally (ATR 50% larger → 50% of normal size). Formula: `adjusted_contracts = base_contracts × (baseline_ATR / current_ATR)`.

**Losing streak rules:**

| Trigger                          | Action                                       |
|----------------------------------|----------------------------------------------|
| Single losing day                | Next session: max 50% of normal size.        |
| 2 consecutive losing days        | Next session: max 25% of normal size.        |
| Hit weekly -5% limit             | Sit out the next session entirely.           |
| 3 consecutive losing weeks       | Strategy review. Paper trade for 1 week before resuming. |
| Single trade loss > 3R           | Review the trade in detail before next entry. |

The 50% rule after a losing day is mechanical, not optional. Day after a loss, judgment is biased toward revenge; smaller size neutralizes the bias without willpower.

**Tilt detection:** urge to enter without a stop, widen a stop, increase size to "make it back", or take a setup you normally skip. Close the platform. The setup will be there tomorrow.

**Rule:** After any losing day, halve size next session. After the weekly limit, sit out the next day.

## 7. Drawdown Governance

`max_drawdown` is the peak-to-trough decline of your account. Define tiered responses before you hit them, so the decision is mechanical in the moment.

**Standard drawdown tiers:**

| Drawdown        | Tier      | Required Action                                              |
|-----------------|-----------|--------------------------------------------------------------|
| 0% to -5%       | Normal    | 1% per trade. Standard rules.                                |
| -5% to -10%     | Reduced   | 0.5% per trade. Take ~50% fewer setups.                      |
| -10% to -15%    | Cash      | No trading. Cash only. Review journal for pattern.           |
| Beyond -15%     | Re-eval   | Strategy lost `edge`. Paper trade 20+ before returning live.  |

Past -10% you are in "save the account" mode, not "make it back" mode.

**Calculating drawdown:** `drawdown_pct = (peak_equity - current_equity) / peak_equity × 100`. Track running peak equity in a spreadsheet. Do not reset peak within the same drawdown tier; the tier remains until equity exceeds the prior peak.

**Rule:** -5% = reduce size, -10% = cash, -15% = strategy review and paper trade. Decide the tiers now, follow them when the time comes.

## 8. Correlation Risk

When you hold multiple correlated positions, your real risk is the sum of correlated exposure, not individual risks.

**NQ/ES correlation:** NQ and ES are 0.85+ correlated on most days. Holding 2 MNQ and 3 MES is not "5 micro contracts of risk". It is a single large position with correlation premium.

**Correlation-adjusted sizing:**

```
effective_risk = sum(risk_i × correlation_multiplier_i)
correlation_multiplier = 1.0 for single position
                        = 1.5 for 2 correlated positions
                        = 2.0 for 3+ correlated positions
```

Worked example: 2 MNQ longs at $200 risk each ($400) plus 2 MES longs at $100 risk each ($200). Nominal $600, but NQ/ES correlation multiplier 1.5: effective risk = ($400 × 1.0) + ($200 × 1.5) = $700. Against $20,000 that is 3.5% effective risk on what looks like 3.0%.

**Common baskets:** NQ + ES + RTY all correlate 0.8+, treat as one. NQ + QQQ is highly correlated. NQ + BTC is moderate. ES + 6E (Euro FX) is uncorrelated, real diversification.

**Rule:** Sum correlated positions and apply 1.5-2.0× multiplier. Cap the basket at 1% effective risk.

## Putting It Together

Risk management is the only edge that compounds. A 40% `win_rate` strategy with 2R targets and 1% sizing has positive `expectancy` and prints over hundreds of trades. The same strategy at 5% sizing blows up in the first bad streak. Same entries, opposite outcomes.

Daily checklist: equity recorded (peak vs current), daily limit calculated (2%), weekly tracker updated, base size confirmed, ATR vol check, streak state (halve after a losing day). Boring on purpose. If risk decisions feel exciting, you are doing them wrong.

**Rule:** Boring risk rules, tracked mechanically, applied consistently. The strategy does the work; risk management keeps you alive to see it.