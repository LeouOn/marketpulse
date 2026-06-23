# System Expansion Menu - What We Can Build Next
# -----------------------------------------------------------------------------
# CURATED OPTIONS (not exhaustive - just the high-value ones for your situation)
# Each option shows: what it does, why it matters for you, time to build,
# NotebookLM integration potential
# =============================================================================

## TIER 1: ESSENTIAL (Should Build Soon)
# These fill actual gaps in your current system. High value, specific use cases.

### 1. Portfolio Dashboard ($800K Tracker)
**What it does:** Tracks your actual positions vs. the recommended allocation
from our earlier work. Shows:
- Current allocation (SPY, GLD, SLV, SIL, BTC, oil hedge, cash)
- Performance per position (P&L, % return)
- Drift from target allocation (when to rebalance)
- Tax-loss harvesting opportunities
- Dividend/interest income tracking
- Risk metrics: max drawdown, beta to SPY, correlation matrix

**Why it matters:** You have a plan. This tool executes it. Without tracking,
drift happens and you don't know when to rebalance. This is the #1 missing piece
for any investor with a multi-asset strategy.

**Build time:** 1-2 hours (deep task with our existing data)
**NotebookLM:** Upload weekly portfolio snapshots for "How is my portfolio
doing?" podcast. Contrarian source: compare your returns to SPY over time.

**Data sources:** Yahoo Finance, FRED (for risk-free rate), your input for cost basis

**Script:** scripts/portfolio_dashboard.py
**Output:** reports/portfolio/snapshot_YYYY-MM-DD.md

---

### 2. Credit/Financial Conditions Monitor
**What it does:** Tracks the #1 leading indicator for crashes - credit spreads.
- BAA-10Y credit spread (already have BAA10Y)
- High Yield (HY) OAS spread
- Investment Grade (IG) OAS
- TED spread (bank stress)
- Term structure (yield curve: 2Y/10Y, 3M/10Y)
- Regional bank stress indicators (KRE, KBE ETF performance)
- Commercial real estate stress (CMBS spreads)
- Repo market stress (SOFR-Treasury spread)

**Why it matters:** EVERY major crash in history had credit spreads blow out
BEFORE equities sold off. 2008 GFC: BAA went from 2% to 9% in 6 months. March 2020:
HY OAS doubled in 4 weeks. 2022 mini-banking crisis: regional bank ETF (KRE) fell 30%
while SPY was flat.

**If you watch nothing else, watch credit spreads.** They tell you a crash
is coming before the stock market knows.

**Build time:** 1-2 hours
**NotebookLM:** EXCELLENT source material. "Are we close to a credit event?"
topic with contrarian views (bulls say "spreads are fine" vs bears say
"spreads are widening").

**Script:** scripts/credit_monitor.py
**Output:** reports/credit/conditions_YYYY-MM-DD.md

---

### 3. Geopolitical Event Tracker
**What it does:** Centralized dashboard for all major geopolitical flashpoints:
- Strait of Hormuz (current active crisis)
- China/Taiwan (TSMC risk, military tensions)
- Russia/Ukraine (war, sanctions, energy)
- Middle East (Israel/Iran, Lebanon, Syria)
- North Korea
- Trade wars (US-China tariffs, EU-US)
- Sanctions regimes
- OPEC+ decisions
- Major elections (2026 midterms, 2028)

For each: current status, key dates, market implications, escalation probability.

**Why it matters:** Geopolitical risk is the #1 driver of oil, gold, defense stocks,
and risk-off events. You already care about Hormuz. This expands to ALL flashpoints.

**Build time:** 2-3 hours (web scraping + manual data entry hybrid)
**NotebookLM:** PERFECT source material. Geopolitical podcasts are the most engaging
type - clear narratives, heroes and villains, real consequences.

**Script:** scripts/geopolitical_tracker.py
**Output:** reports/geopolitical/snapshot_YYYY-MM-DD.md

**Data sources:** Reuters, ISW (Institute for Study of War), manual entry for events

---

### 4. Crypto On-Chain Dashboard
**What it does:** Real-time Bitcoin/Ethereum ecosystem health:
- BTC hash rate (mining network security)
- BTC exchange balances (selling pressure proxy)
- BTC MVRV ratio (market value vs realized value - cycle indicator)
- BTC fear/greed index
- BTC dominance (vs altcoins)
- Stablecoin total supply (USDT, USDC, DAI)
- ETH gas fees (network activity)
- ETF flows (Bitcoin spot ETF, Ethereum ETF)

**Why it matters:** You have a BTC position. On-chain data shows you what
HODLers and miners are doing BEFORE price moves. MVRV above 3 = cycle top.
Exchange balances dropping = supply shock incoming. These are the indicators
that called the 2021 top and 2022 bottom.

**Build time:** 1-2 hours
**NotebookLM:** Good source for "Is Bitcoin's bull run over?" debates.
Contrarian source: Bitcoin maxis vs "crypto is dead" skeptics.

**Script:** scripts/crypto_dashboard.py
**Output:** reports/crypto/snapshot_YYYY-MM-DD.md

**Data sources:** Blockchain.com, CoinGlass, Glassnode (free tier), Yahoo (BTC-USD)

---

## TIER 2: HIGH VALUE (Build When Ready)
# These would significantly improve specific aspects of your system.

### 5. MNQ Trade Journal
**What it does:** Log every MNQ trade with full context:
- Entry/exit price, size, P&L
- Regime at entry (RISK_ON, RECESSION, etc.)
- Trend danger score at entry
- VIX at entry
- Account balance before/after
- Post-mortem: did you follow the anti-blowup rules?
- Aggregate stats: win rate, avg P&L, max drawdown, rule violations

**Why it matters:** The MNQ sizing tool tells you WHAT to do. The journal tells
you WHAT YOU ACTUALLY DID. The gap between the two is where most traders lose
money. The journal closes that gap.

**Build time:** 2-3 hours (database schema + CLI)
**NotebookLM:** Upload your trade log. "Review my last 20 trades and identify
patterns in my violations." This is EXACTLY the kind of analysis AI excels at.

**Script:** scripts/mnq_journal.py
**Output:** reports/mnq_trades/journal.md + SQLite database

---

### 6. Sector Rotation Tracker
**What it does:** Tracks performance and momentum of the 11 S&P sectors:
- XLK (Tech), XLF (Financials), XLE (Energy), XLV (Health)
- XLY (Discretionary), XLP (Staples), XLI (Industrials)
- XLU (Utilities), XLB (Materials), XLRE (Real Estate), XLC (Comm)
- Plus key sub-sectors: KRE (Regional Banks), SMH (Semis), IYR (REITs)

For each: 1M, 3M, 6M, YTD performance + relative strength ranking

**Why it matters:** Sector rotation tells you what the market is betting on.
RISK_ON + early cycle = Tech + Discretionary leading. RECESSION = Staples +
Utilities + Healthcare. Energy + Materials leading = inflation regime.

**This is what tells you which sectors to be long/short in MNQ.**
If semis (SMH) are leading and tech is strong, NQ has tailwind. If staples
are leading and tech is weak, NQ is range-bound at best.

**Build time:** 1-2 hours
**NotebookLM:** Good for "what is the market telling us about the cycle?"
podcasts with sector rotation data as the source.

**Script:** scripts/sector_rotation.py
**Output:** reports/sectors/rotation_YYYY-MM-DD.md

---

### 7. Treasury Yield Curve Monitor
**What it does:** Full yield curve analysis:
- 2Y, 5Y, 10Y, 30Y Treasury yields
- Spreads: 2s10s, 3m10y, 5s30s
- Historical context (inversions, steepenings)
- Curve shape classification (normal, flat, inverted, humped)

**Why it matters:** The yield curve inverted in 2022 and is one of the most
reliable recession indicators. 2s10s has been positive recently - is that
bullish (no recession) or ominous (curve steepening due to long-end concerns)?

**Build time:** 1 hour (we have DGS2, DGS5, DGS10, DGS30 from FRED)
**NotebookLM:** Good for "What does the yield curve tell us?" podcasts.
Historical parallels (1989, 2000, 2006 inversions all preceded recessions).

**Script:** scripts/yield_curve.py
**Output:** reports/rates/curve_YYYY-MM-DD.md

---

## TIER 3: PERSONAL FINANCE (Build When You Start Deploying)
# These help with the actual execution of your $800K plan.

### 8. Tax-Efficient Rebalancing Calculator
**What it does:** When your allocation drifts, shows the TAX-OPTIMAL way
to rebalance:
- Which lots to sell (long-term vs short-term)
- Wash sale rule awareness (30-day rule)
- Tax-loss harvesting opportunities
- Estimated tax impact per trade
- Optimal rebalancing frequency

**Why it matters:** If you rebalance quarterly and don't think about taxes,
you can lose 15-37% of your gains to taxes. With planning, you can defer,
harvest losses, and stay tax-efficient.

**Build time:** 2-3 hours (requires understanding of your tax situation)
**NotebookLM:** Not directly relevant - this is a calculator, not analysis.

**Script:** scripts/tax_rebalancer.py
**Output:** Interactive (asks for your cost basis, returns optimal trades)

---

### 9. DCA Cost Basis Tracker
**What it does:** Tracks the average cost of your DCA positions:
- Silver (DCA over 4-6 months per our plan)
- Bitcoin (if you DCA instead of lump sum)
- SPY (if you DCA into broad equity)

Shows: total invested, average price, current value, unrealized gain/loss.

**Why it matters:** DCA makes tax-loss harvesting complex (you have many lots).
This tool tracks each lot so you can sell specific ones for tax efficiency.

**Build time:** 1-2 hours
**NotebookLM:** Not directly relevant.

**Script:** scripts/dca_tracker.py
**Output:** reports/portfolio/dca_ledger.md

---

## TIER 4: WILD CARDS (Exploratory, Fun Projects)
# These are interesting but not essential. Build if you're curious.

### 10. News Headline Scraper
**What it does:** Scrapes top financial headlines daily and creates a brief:
- Reuters, Bloomberg, FT top stories
- Categorized: macro, markets, crypto, geopolitics
- AI-generated summary of top 3 stories
- Direct links to articles for NotebookLM source packs

**Why it matters:** Saves you 30 minutes/day of news scanning. Auto-generates
the source pack for your daily podcast.

**Build time:** 2-3 hours (scraping + summarization)
**NotebookLM:** Excellent - your daily podcast source pack is auto-generated.

**Script:** scripts/news_scraper.py
**Output:** reports/news/snapshot_YYYY-MM-DD.md

---

### 11. Earnings Calendar for Your Holdings
**What it does:** Tracks upcoming earnings for your stocks (WPM, PAAS, XOM, etc.):
- Date, time, expected EPS
- Historical beat/miss rate
- Implied move (options pricing)
- Pre/post earnings performance

**Why it matters:** Avoid holding through earnings if you don't want volatility.
Or, position for earnings plays if you want to.

**Build time:** 2-3 hours
**NotebookLM:** Good for stock-specific analysis.

**Script:** scripts/earnings_tracker.py
**Output:** reports/earnings/upcoming.md

---

### 12. Mandala/Spiritual Practice Tracker
**What it does:** Personal - track your mandala offerings, orgone builds,
moissanite collection:
- Silver shot used per offering (and remaining inventory)
- Orgone pieces built (materials, design, date)
- Moissanite pieces acquired (specs, source, cost)

**Why it matters:** This is your personal practice. Tracking it adds intention
and helps you see patterns over time.

**Build time:** 1 hour
**NotebookLM:** Not relevant (this is personal, not analysis).

**Script:** scripts/practice_tracker.py
**Output:** reports/personal/practice_log.md

---

## TIER 5: LONG-TERM (Build When You're Ready)
# These are ambitious projects for when the system matures.

### 13. Backtesting Framework
**What it does:** Lets you backtest any strategy against historical data:
- "What if I went 100% gold during RECESSION regimes?"
- "What if I sold when trend danger score > 75?"
- "What if I DCA'd silver when GSR > 85?"

**Why it matters:** Validates our analysis with actual data. "This strategy
worked X% of the time" is more compelling than "this should work theoretically."

**Build time:** 4-6 hours (significant infrastructure)
**NotebookLM:** Good for strategy validation podcasts.

**Script:** scripts/backtester.py
**Output:** reports/backtests/[strategy]_results.md

---

### 14. Marketpulse Web Dashboard Integration
**What it does:** Adds a `/research` or `/macro` route to your existing
Next.js marketpulse frontend that:
- Displays the current macro regime
- Shows the trend danger score
- Lists the weekly briefing
- Renders the MNQ sizing recommendation
- Embeds the credit/geopolitical dashboards

**Why it matters:** A daily browser tab showing your entire macro picture.
Better than running scripts manually. Makes the system actually USED.

**Build time:** 8-12 hours (full web feature)
**NotebookLM:** Not relevant (this is a UI, not a document).

---

## MY TOP 3 RECOMMENDATIONS (Given Your Situation)

If I had to pick 3 to build next, they'd be:

### #1: Credit/Financial Conditions Monitor
**Why first:** Credit spreads are the #1 crash predictor. You're holding
$800K across multiple asset classes. If credit blows out, you NEED to know
before the equity market sells off. This is the early warning system.

### #2: Portfolio Dashboard
**Why second:** You have a plan. This executes it. Without tracking, you
drift, miss rebalancing opportunities, and don't know your true risk exposure.
This closes the gap between analysis and action.

### #3: Geopolitical Event Tracker
**Why third:** You already engage with geopolitics (Hormuz analysis).
Expanding to all major flashpoints gives you a systematic view of the
risks that drive oil, gold, and defense stocks. Perfect NotebookLM content.

---

## HOW TO CHOOSE

Ask yourself:

1. **"What problem am I currently trying to solve?"**
   - Executing my $800K plan? -> Portfolio Dashboard
   - Avoiding the next crash? -> Credit Monitor
   - Tracking geopolitical risk? -> Geopolitical Tracker
   - Improving my MNQ trading? -> Trade Journal + Sector Rotation
   - Understanding Bitcoin better? -> Crypto Dashboard

2. **"What would I actually USE every week?"**
   - Be honest. If you wouldn't run the tool weekly, it's not worth building.

3. **"What generates the best NotebookLM content?"**
   - Credit Monitor, Geopolitical Tracker, Crypto Dashboard = best podcasts
   - Portfolio Dashboard = decent podcasts (how am I doing?)
   - Trade Journal = good podcasts (review my mistakes)

---

*This menu is part of the LLM-First Analysis System.*
*See templates/llm_first_system.md for the complete workflow.*
