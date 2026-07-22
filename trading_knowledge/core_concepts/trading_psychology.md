# Trading Psychology

The human operating system behind execution. Technical `edge` and `expectancy` are necessary but not sufficient; the same setup can be +2R or -6R depending on psychological state. The topics below describe concrete failure modes observed in year-2 NQ futures trading and the mechanical rules that interrupt them.

## Tilt

### Definition
Tilt is a sustained sympathetic nervous system activation (fight-or-flight) that overrides the trader's written rules. Not the same as "being upset about a loss." A physiological state — elevated heart rate, shallow breathing, jaw tension, narrowed visual focus — that degrades decision quality for 30-180 minutes after onset.

### Scenario
A short on NQ at 15,250 hits the 20-point stop at 9:42 AM. Within 90 minutes the trader has taken three more setups — each lower-conviction, each larger. The fourth reverses within seconds. By 10:45 AM they are watching the 1-minute chart with chin on hand, muttering at the screen, adding to a loser. This is tilt, not bad luck.

### Somatic Warning Signs
- Clenched jaw, shoulder shrug, leaning toward the monitor
- Faster, shallower breathing; speech clipped or fast
- Hot palms, urge to "do something" when no setup is present
- Loss of peripheral awareness — tunnel vision on the P&L column

### Behavioral Warning Signs
- **Talking too much** — narrating trades to chat, partner, or out loud. Normal flow is quiet.
- **Reverting entries** — flipping long/short on the same level because the first direction "didn't work"
- **Size escalation on losers** — adding to a losing position or trading more contracts after a loss to "make it back"
- **Schedule abandonment** — staying past planned session end, or taking a setup that violates the time-based stop
- **Rule editing** — moving a stop wider because "this move feels different," or skipping the pre-trade checklist

### Detection Rule
If any two of the above are present, exit the platform immediately. Do not flatten the current position with a market order; use a limit at a level likely to fill within 5 minutes, then close the trading app. The cost of being wrong about tilt is one missed setup. The cost of being wrong about not being tilted is the rest of the day.

## Revenge Trading

### Definition
Revenge trading is entering a position primarily to recover a recent loss rather than to express a valid setup. The setup may exist; the motive is wrong. The most common amplifier of `max_drawdown` because it stacks correlated losing positions (same direction, same session, same emotional state) on top of the initial loss.

### The Cycle
1. Real loss occurs — often a clean loss (valid setup, stop hit, no fault)
2. Trader re-interprets it as "the market taking from me"
3. Within minutes, a new position is opened — same direction, similar level, often larger size
4. Entry is late (missed the real entry) or in worse structure (chasing)
5. Loss is larger than the first, or a winner is exited early to "secure" the bounce
6. Cycle repeats; session P&L compounds negatively

### Why It Compounds Losses
- **Correlation**: each revenge trade has the same directional bias as the prior losing trade. Not independent bets — the same bet, layered.
- **Size drift**: the second trade is usually bigger because the trader is "behind." A 2-loss day becomes a 6-loss day even with the same `win_rate`.
- **Time erosion**: revenge trades cluster in the worst window — the volatile post-stop period when spreads widen and `delta` flips chaotically.

### Exit Procedure
1. Close the offending position at market (do not wait for a "better price")
2. Write a one-line note: "[time] revenge entry, [reason], [P&L]"
3. Stand up and physically leave the room for 10 minutes
4. No re-entry for 30 minutes (cooling-off rule, see below)
5. If session P&L is past the daily cap, do not return

## The "Size Small on Volatile Days" Rule

### Why This Rule Gets Broken
Universally agreed on, almost universally broken. Predictable reasons:

- **Volatility feels like opportunity.** Wide ranges, fast moves, news-driven price action look like easy money. The brain reads volatility as edge.
- **Yesterday's size worked.** On a normal day 4-contract size was fine. On a volatile day the same dollar swing happens in 30 seconds instead of 30 minutes — same size is now untenable.
- **Halving feels like quitting.** Cutting to 2 contracts on a day where everything is moving feels like leaving money on the table. It is the entire game.

### What "Small" Actually Means
Hard rule: **halve standard `position_sizing` after any loss day, and quarter it after any day where realized volatility exceeded 1.5x the 20-day average.** Mechanical, not discretionary. The trader does not decide if today "feels" volatile — the prior day's realized range vs. the 20-day average decides.

### Mechanical Enforcement Options
| Option | How it works | Best for |
|---|---|---|
| Reduce contract count | Trade 2 instead of 4. Same stop distance. | NQ day traders. Simplest. |
| Widen stops proportionally | Keep 4 contracts; widen stop so $ risk per trade is halved. | Swing traders, larger accounts. |
| Skip the day | No trading. The highest-`expectancy` "trade" of the day. | CPI / FOMC / NFP days with unclear bias. |

### Volatility Lock-In
Contract count for the next session is set at the end of the prior session based on the prior session's realized volatility vs. its 20-day average. Locked in writing before the next open. Mid-session increases are prohibited.

## Daily Reset

### Definition
The end-of-session ritual that flushes residual emotional and cognitive state from the trading day. Without it, the next session opens with yesterday's P&L still attached. With it, the next session starts at baseline.

### Concrete Procedure (60-90 minutes after close)
1. **Close the platform** — full close, not minimized. Live charts in the background are a trigger.
2. **Write the journal entry** before anything else.
3. **Record P&L plus emotional tag** — single number plus one word ("calm," "foggy," "eager," "angry," "tilted," "neutral"). The tag matters more than the number.
4. **Set next-day max-loss limit** — hard number in the journal. Default: 1.5% of account or 2 losing trades, whichever first.
5. **Set next-day contract count** — using the volatility rule above.
6. **Leave the desk for 30 minutes** — walk, food, anything physical.
7. **No trading content for the evening** — no trading Twitter, no Discord, no P&L screenshots.

### Why the Reset Is Non-Negotiable
The reset after a +$3,000 day is the one that prevents the +$8,000 loss day, because it closes the overconfidence loop. Skipping it on green days is the most common precursor to a tilt-driven red day.

## Journal Review

### Weekly Review (Sunday evening, 30 minutes)
- What was the average emotional tag? Trend matters more than any single day.
- Did `position_sizing` follow the volatility rule every day?
- Which setups produced the best `expectancy` this week? Worst?
- How many trades were revenge trades? (Should be zero. Non-zero requires investigation.)
- Exits on schedule vs. extended/abandoned stops — what is the ratio?
- Did I take any trade pre-flagged as "no-trade" in morning prep? (Yes = system failure.)

### Monthly Review (First weekend of the month, 90 minutes)
- Plot `max_drawdown` for the month vs. trailing 6-month average. Expanding? Re-examine `risk_reward` per trade.
- Calculate `win_rate` and `expectancy` by setup type. Drop any setup with net-negative expectancy for 30 days.
- Walk through the largest losing day minute-by-minute. Find the rule break.
- Largest winning day — skill (repeated A+ setups) or luck (one outsized winner)?
- Cluster the month's "tilted" / "eager" tags by day-of-week and time-of-day. Patterns here are mechanical fixes, not willpower fixes.

### Acting on the Answers
Weekly answers → adjust next week's prep (e.g., "no-trade 9:30-10:00 AM this week"). Monthly answers → adjust the trading plan itself (drop a setup, change session hours, change default `position_sizing`).

## After-Loss Discipline

### The Four Anti-Tilt Mechanisms
Mechanical tripwires that fire automatically. Require no judgment to apply — which is the point, because judgment is what's compromised after a loss.

**1. Max Contracts Per Session**
Hard cap on contract count, set at session start. Example: 8 contracts total, all positions counted. Hit the cap, done. Not "I'll just take one more."

**2. Daily Loss Cap**
A specific dollar amount or percent-of-account number. Hit it, walk away. Sized so hitting it does not materially harm the account (suggested: 1-2% of account). Prevents the 1-loss day from becoming the 5-loss day.

**3. Cooling-Off Rule**
After any losing trade, no re-entry for 30 minutes minimum. Two purposes: interrupts the revenge cycle; surfaces whether the next "setup" was a setup or boredom. If valid in 30 minutes, take it. If the level has moved past, it wasn't there.

**4. Time-Based Stop**
Use a `time_based_stop` on every trade. If the position has not worked within the planned number of bars (e.g., 15 bars on a 5-minute chart), exit regardless of P&L. Prevents the "give it room" trade in every losing journal, and forces a time dimension into trade planning.

### Composite Anti-Tilt Rule
A `position_sizing` change, unplanned re-entry, or stop-widening is a tilt flag. Any one requires a 30-minute platform close, regardless of whether the current position is green.

## Professional Mindset

### What Experienced Traders Do Differently
The list below describes behaviors that distinguish traders who survive year-2+ from those who don't. None are about talent. All are mechanical.

| Amateur behavior | Professional behavior |
|---|---|
| Trades through news without a plan | Pre-defines no-trade windows for CPI / FOMC / NFP |
| Sizes by "what worked last week" | Sizes by realized volatility vs. 20-day average |
| Adjusts stop mid-trade | Sets stop before entry, writes it down, does not move it |
| Tells people about wins | Records all trades in a journal before telling anyone |
| Trades the open because they're "ready" | Has a defined entry window, defaults to no-trade outside it |
| Reacts to a loss within seconds | Cooling-off rule, 30 minutes minimum |
| Sizes up after a loss | Sizes down or skips the next day |
| Finishes day without reviewing | Runs daily reset, sets next-day max loss and contract count |
| Holds a position "to give it room" | Uses `time_based_stop` and pre-defined exit plans |
| Thinks discipline = willpower | Thinks discipline = pre-commitment devices (rules written in advance) |

### The Key Insight
The amateur and professional lists are the same activities, executed in opposite order. The amateur does the right action at the wrong time, or the wrong action at the right time. The professional pre-commits in writing before emotion arrives. Willpower is unreliable; mechanics are not.

### Tools That Enforce Professional Behavior
- **Pre-trade checklist** — printed or pinned, completed before every entry. Minimum items: setup valid, volatility rule applied, `position_sizing` calculated, stop defined, time-based stop defined, exit target defined, daily loss cap remaining.
- **Position-size calculator** — separate from the platform. Contract count = (account risk $) / (stop distance in `point_value` × stop distance in points). Pre-computed for the day's expected stop distance.
- **Session contract ledger** — running tally on-screen. The trader should never have to remember if they've hit the daily cap.
- **End-of-day journal template** — pre-filled with the fields above. Removes the decision of what to write.

### Pre-Commitment Rule
Every rule in this document must exist somewhere outside the trader's memory — written in a notebook, a journal, or a config file. If the only place a rule exists is in the trader's head during a losing trade, it does not exist.
