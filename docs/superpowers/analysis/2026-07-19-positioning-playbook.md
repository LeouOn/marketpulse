# Smart Money Positioning Playbook by Scenario

**Date:** 2026-07-19
**Status:** Living document — update as curve signals arrive
**Related:** `docs/superpowers/analysis/2026-07-15-warsh-framework-hypotheses.md`, `docs/superpowers/analysis/2026-07-19-warsh-toolkit-deep-dive.md`

---

## Purpose

This playbook maps each Warsh hypothesis scenario to concrete asset allocation, position sizing, and risk management rules. The goal: when the yield curve monitor fires a signal, you already know the playbook. No improvising under pressure.

---

## The Curve as Regime Filter

Before any deployment, check the 2s10s spread. The curve is your traffic light:

| 2s10s Level | Signal | Action |
|-------------|--------|--------|
| Below +20 bps | 🔴 RED — Curve near inversion | Full defensive. No new deployments. |
| +20 to +40 bps | 🟡 YELLOW — Flat, status quo | Capital preservation. Small positions only. Wait. |
| +40 to +60 bps | 🟢 GREEN-WATCH — Early steepening | Begin accumulation of value/quality. Moderate sizing. |
| +60 to +100 bps | 🟢 GREEN — Steepening confirmed | Full deployment of value thesis. Normal sizing. |
| +100+ bps | 🟢🟢 FULL GREEN — Healthy curve | Maximum conviction. Value significantly outperforms. |
| Below 0 (inverted) | ⚫ BLACK — Recession risk | Maximum defensive. Wait for re-steepening. |

**Current state (July 19, 2026): 2s10s = +41 bps. YELLOW.** Capital preservation mode. Small positions only.

---

## Scenario A: Genuine Hawk (30% probability)

### Description
Warsh truly believes in the 2% target and fights inflation. QT continues aggressively. Balance sheet shrinks toward $5T. Rates stay higher for longer. No shadow easing.

### Curve trajectory
2s10s stays flat at +30-50 bps for 12-18+ months. Value style continues to struggle. Growth/momentum dominates.

### What to own
| Asset | Direction | Rationale |
|-------|-----------|-----------|
| **Cash / T-bills** | Overweight | Earn 3.8-4.2% risk-free while waiting |
| **Short-duration bonds** | Overweight | Minimal duration risk |
| **USD** | Overweight | Hawkish Fed = strong dollar |
| **Defensive sectors** | Market weight | Healthcare, utilities, consumer staples |
| **MU** | Hold (if already in) | Fundamentals intact but chart broken. Stop at $800. |

### What to avoid
| Asset | Rationale |
|-------|-----------|
| Long-duration Treasuries | Hawkish Fed = bond bear market |
| Small caps (IWM) | Floating-rate debt + flat curve = margin compression |
| Emerging markets | Strong USD + tight Fed = capital flight |
| Crypto (BTC) | Tight liquidity = risk-off |
| Value traps (BABA) | Structural decline continues regardless of Fed |

### Position sizing
Max 2-3% risk per new position. Cash position: 60-70% of portfolio.

### Exit signal for this scenario
2s10s pushes through +60 bps → Scenario A is wrong, transition to Scenario C playbook.

---

## Scenario B: Pantomime (15% probability)

### Description
Warsh was appointed to sound hawkish while doing dovish. Shadow easing from day one via expanded RMP, slowed QT, expanded SRF. The curve steepens fast as the market figures out the pantomime.

### Curve trajectory
2s10s steepens to +60-80 bps within 3-6 months. Value rotation begins earlier than consensus expects.

### What to own
| Asset | Direction | Rationale |
|-------|-----------|-----------|
| **Value stocks** | Maximum overweight | Curve steepening = value rotation begins |
| **Small caps (IWM)** | Overweight | Cheaper funding + domestic growth |
| **Gold** | Overweight | Shadow easing = inflation hedge demand |
| **BTC** | Overweight | Shadow QE = liquidity bid |
| **INTU, ADBE, CRM** | Accumulate | Quality value at deep discounts (-49% to -67%) |
| **Oil** | Overweight | Inflation + geopolitical risk |

### What to avoid
| Asset | Rationale |
|-------|-----------|
| Long-duration bonds | Inflation returns, bonds sell off |
| USD | Shadow easing = dollar weakness |
| Mega-cap tech at highs | Rotation away from concentration |

### Position sizing
Max 5% risk per new position. Cash position: 30-40% of portfolio.

### Entry triggers
- 2s10s pushes through +50 bps in less than 4 weeks = pantomime accelerating
- RMP volume doubles from current $40B to $80B+ per month
- QT pace cut from $60B to $30B or less

### Exit signal for this scenario
2s10s stalls at +40-50 bps after 3 months → pantomime was wrong, revert to Scenario A or C.

---

## Scenario C: Transition (55% probability) — MOST LIKELY

### Description
Warsh starts hawkish to establish credibility, then pivots to pragmatic accommodation over 6-12 months as fiscal/economic reality demands. The 2% target becomes fiction (3-3.5% tolerated). Balance sheet panel provides institutional cover.

### Curve trajectory
2s10s stays flat at +30-50 bps for 3-6 months, then steepens to +60-100 bps as Warsh pivots. Value rotation begins mid-to-late 2027.

### The three-phase positioning plan

#### Phase 1: WAIT (Now through FOMC July 28-29)
| Action | Detail |
|--------|--------|
| **2s10s level** | +30-50 bps (current: +41) |
| **Portfolio** | 70-80% cash, 20-30% existing positions |
| **New deployments** | None except very small (1-2% risk) |
| **Focus** | Watch FOMC language, balance sheet panel, RMP volume |
| **Existing MU** | Hold with stop at $800. Thesis intact. |
| **Existing BABA** | Hold. Watch Pentagon lawsuit outcome. |

#### Phase 2: ACCUMULATE (Triggered by 2s10s through +50 bps)
| Action | Detail |
|--------|--------|
| **2s10s level** | +50-80 bps |
| **Portfolio** | 50-60% cash, 40-50% deployed |
| **Deploy in** | Quality value first: INTU, ADBE, CRM, MSFT |
| **Position size** | 3-4% risk per position |
| **Entry method** | Scale in over 2-3 weeks. Don't buy all at once. |
| **Stop levels** | 15-20% below entry on each position |

#### Phase 3: CONVICTION (Triggered by 2s10s through +80 bps)
| Action | Detail |
|--------|--------|
| **2s10s level** | +80-120 bps |
| **Portfolio** | 20-30% cash, 70-80% deployed |
| **Deploy in** | Full value rotation: small caps (IWM), cyclicals, commodities |
| **Position size** | 5% risk per position |
| **Entry method** | Add to Phase 2 positions. Initiate small-cap and commodity positions. |
| **Reduce** | Begin trimming if 2s10s exceeds +150 bps (late-cycle signal) |

### What to own by phase

| Phase | Core Holdings | Satellite | Avoid |
|-------|--------------|-----------|-------|
| **Wait** | Cash, T-bills | MU (hold), BABA (hold) | New deployments |
| **Accumulate** | INTU, ADBE, CRM, MSFT | Small starter in IWM | Chasing momentum |
| **Conviction** | IWM, value ETFs, energy | BTC, gold | Long bonds |

---

## Smart Money Signals to Watch

### Bond market positioning (the smartest money)
| Signal | Where to Find It | What It Means |
|--------|-----------------|---------------|
| **Steepener positioning** | CFTC TFF report, ICE data | Bond traders betting on curve steepening = they expect Scenario B/C |
| **2s10s futures** | CME 2Y/10Y spread futures | Direct bet on curve shape |
| **Mortgage spread** | Bloomberg/Refinitiv | Widening spreads = MBS selling pressure |
| **Term premium** | NY Fed ACM model | Negative term premium = market expects Fed ease. Positive = market expects tight. |

### Equity market signals
| Signal | Source | What It Means |
|--------|--------|---------------|
| **Russell 2000 vs S&P 500** | Yahoo/Google Finance | R2000 outperforming = rotation beginning |
| **Value vs Growth (IVE/IVW)** | iShares ETF comparison | Value outperforming = regime shift confirmed |
| **Small-cap fund flows** | ICI weekly flow data | Inflows into small-cap funds = smart money rotating |
| **Insider buying** | SEC Form 4 filings | Executives buying their own stock = confidence |

### Commodity and currency signals
| Signal | Source | What It Means |
|--------|--------|---------------|
| **Gold price** | Spot/COMEX | Gold rising = inflation/fear = dovish expectations |
| **DXY (dollar index)** | ICE | Dollar falling = easing expectations |
| **Oil forward curve** | NYMEX CL futures | Backwardation = tight near-term supply. Contango = oversupply. |
| **Yen/USD** | Spot | Yen strengthening = risk-off, BoJ normalization |

### Crypto signals
| Signal | Source | What It Means |
|--------|--------|---------------|
| **BTC ETF flows** | SoSoValue, CoinShares | Inflows = institutional risk appetite. Outflows = risk-off. |
| **Stablecoin supply** | Glassnode, DefiLlama | Expanding = liquidity entering crypto. Contracting = leaving. |
| **BTC dominance** | TradingView | Rising = risk-off within crypto (flight to quality). |

---

## Risk Management Framework

### The Golden Rule
**Never risk more than you can psychologically survive losing.** The constraint isn't financial capacity — it's psychological capacity. After a $11K+ loss month, your psychological breaking point is lower than you think.

### Position sizing by curve level

| 2s10s Level | Max Risk Per Position | Max Total Portfolio Risk | Cash Floor |
|-------------|----------------------|-------------------------|------------|
| 🔴 Below +20 | 0% (no new positions) | 5% | 80% |
| 🟡 +20 to +40 | 1-2% | 10% | 70% |
| 🟢 +40 to +60 | 3-4% | 20% | 50% |
| 🟢 +60 to +100 | 5% | 35% | 30% |
| 🟢🟢 +100+ | 5-7% | 50% | 20% |

### Hard stops and invalidation
- Every position gets a hard stop at entry. No exceptions.
- If 2s10s drops below +20 bps from above +40, reduce all risk positions by 50%.
- If 2s10s inverts (below 0), go to maximum defensive. No exceptions.
- If a position loses more than 20% from entry, cut. Don't average down.

### The anti-tilt protocol
1. After any single-day loss > 3% of portfolio: stop trading for 24 hours.
2. After consecutive losses on 3 trades: stop for 48 hours.
3. After weekly drawdown > 8%: stop for 1 week.
4. The curve monitor runs regardless — it doesn't need you to watch it.
5. When it fires a signal, that's when you come back. Not before.

---

## Historical Parallels

### Greenspan 1987-1989 (closest parallel to Scenario C)
- Appointed by political president (Reagan)
- First crisis: 1987 crash (2 months into tenure)
- Response: massive liquidity, then return to tight policy
- Curve: steepened as Greenspan provided liquidity, then flattened as he tightened
- Lesson: Warsh will reveal his true nature during the first crisis (Iran/Hormuz/oil spike)

### Bernanke 2008-2009 (Scenario B parallel)
- Inherited crisis, responded with unprecedented easing
- QE1 started quietly, expanded dramatically
- Curve steepened from near-inversion to +280bps over 18 months
- Lesson: if Warsh faces a credit event, the pantomime becomes explicit QE fast

### Powell 2020-2022 (Scenario A parallel)
- COVID easing → inflation surge → aggressive tightening
- Curve went from deeply inverted to rapidly steepening
- Lesson: Fed Chairs who stay too hawkish eventually create the recession they were trying to prevent

---

## The Smart Money Alignment Strategy

The goal isn't to be the smartest analyst. It's to be **positioned where the smart money is heading before they get there**.

### Who is the smart money?
1. **Bond market** — the smartest macro investors. They price the curve before equity markets react.
2. **Hedge fund positioning** — visible in 13F filings, CFTC data, prime broker reports.
3. **Corporate insiders** — executives buying their own stock at discounts (INTU, ADBE insiders).
4. **Sovereign wealth funds** — large, patient capital that moves slowly but signals direction.

### How to align
1. **Watch the bond market first.** If steepener positioning is building (CFTC data), the smart money is betting on Scenario B/C. Follow them.
2. **Watch insider buying.** If INTU/ADBE insiders are accumulating at -49%/-67% discounts, they believe the moat holds. Follow them.
3. **Watch fund flows.** When small-cap ETFs see sustained inflows (not just one day), the rotation is real. Follow the flows.
4. **DON'T watch retail sentiment.** Reddit, Twitter, TikTok = dumb money. If retail is excited, you're late.

### The alignment checklist
Before deploying capital in Phase 2 or 3:
- [ ] Is 2s10s above the trigger level (+50 for Phase 2, +80 for Phase 3)?
- [ ] Are bond traders positioned for steepening? (CFTC data)
- [ ] Is insider buying present in the names you want to buy?
- [ ] Are small-cap/value ETFs seeing net inflows?
- [ ] Is the dollar weakening (DXY declining)?
- [ ] Is gold stable or rising?

If 4+ of these are YES, deploy. If fewer, wait. The curve is the tiebreaker.

---

## Current Assessment (July 19, 2026)

| Factor | State | Signal |
|--------|-------|--------|
| 2s10s | +41 bps | 🟡 YELLOW — still in wait zone |
| Bond steepener positioning | Building ("WarshGPT" article) | 🟢 Early green |
| Insider buying (INTU/ADBE) | Unknown — check Form 4 | ❓ Unknown |
| Small-cap ETF flows | Neutral (post-reconstitution) | 🟡 Neutral |
| Dollar (DXY) | Elevated | 🔴 Hawkish signal |
| Gold | Falling ($3,978) | 🔴 Hawkish signal (market believes Scenario A) |
| **Overall** | **Mixed** | **WAIT. Don't deploy until FOMC July 28-29.** |

**Next checkpoint: FOMC July 28-29.** Warsh's first meeting. Everything before it is rhetoric. Everything after it is policy.

---

## Quick Reference: The Deployment Decision Tree

```
Is 2s10s > 50 bps?
├── NO → STAY DEFENSIVE (Phase 1: Wait)
│   ├── Is FOMC meeting within 2 weeks? → Wait for it
│   └── Not within 2 weeks? → Small positions only (1-2% risk)
│
└── YES → BEGIN DEPLOYMENT
    ├── Is 2s10s > 80 bps? → FULL DEPLOYMENT (Phase 3: Conviction)
    │   ├── Buy: Value ETFs, small caps, commodities
    │   └── Position size: 5% risk each
    │
    └── 50-80 bps? → GRADUAL DEPLOYMENT (Phase 2: Accumulate)
        ├── Buy: Quality value (INTU, ADBE, CRM, MSFT)
        └── Position size: 3-4% risk each
```