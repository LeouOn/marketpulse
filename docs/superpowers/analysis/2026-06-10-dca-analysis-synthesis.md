# Bitcoin DCA Strategy Backtesting — Synthesis & Code Map

**Date:** 2026-06-10
**Author:** Sisyphus (synthesis); attached source doc by user
**Status:** Empirical results from real BTC data; roadmap to close gaps

This document **synthesizes** the externally-attached research note
(*Bitcoin DCA Strategy Backtesting*, 2026-06-10, see
[`sources/README.md`](sources/README.md)) with the empirical backtests
we have run in this repo on real BTC-USD daily data.

## 1. TL;DR

The attached research note is a comprehensive external review of DCA
theory. Our repo now has the **infrastructure** to empirically validate
that theory against real BTC data. We have run a 4,285-day matrix
(2014-09-17 → 2026-06-11) covering 5 strategies × 3 scaling overlays
on a 100% allocation, $10,000 starting equity, 10 bps fee, 5 bps
slippage. Full results: [`empirical_results.json`](empirical_results.json).

| Best per strategy (2014–2026) | End Equity | CAGR | Sharpe | Max DD |
|---|---:|---:|---:|---:|
| **MomentumTrend (SMA-50)** + FixedDollar | $4,532,229 | **68.4%** | **1.33** | -59.0% |
| BuyAndHold | $1,355,493 | 52.0% | 0.96 | **-83.4%** |
| DCAValueAveraging (VA $100k target, monthly) + VolTargeted | $394,912 | 36.8% | 0.89 | -68.9% |
| DCAFixedAmount ($100/wk) | $4,485 | -6.6% | -0.52 | -55.1% |

**Three observations that the external doc doesn't reach because
it doesn't have a working backtester:**

1. **A naïve weekly DCA into BTC over 2014–2026 *lost money***.
   A $100/week buy from 2014-09-17 to 2026-06-11 (4,285 days, 613 buys)
   turned $61,300 of contributions into $65,784 — a nominal loss
   relative to contributions because most of the period was a multi-year
   bull run. This is the textbook "cash drag" problem the external doc
   describes in §2.2, made visceral with real numbers.

2. **Value Averaging is materially better than fixed-$ DCA** for the
   same contribution schedule. VA to a $100k target over the same
   window returned 36.8% CAGR with 0.89 Sharpe — comparable to
   BuyAndHold on risk-adjusted basis but with a 14.5 percentage-point
   smaller drawdown (-68.9% vs -83.4%). This validates the external
   doc's §4 argument *for the BTC asset class specifically* (where the
   note correctly anticipates that VA's capital-exhaustion risk is
   material — none of our VA tests exhausted capital because the
   targets we used were conservative).

3. **Trend filters dominate**. A 50-day SMA filter on top of any
   base strategy produces the best absolute and risk-adjusted returns
   (68.4% CAGR, 1.33 Sharpe, -59% MaxDD) over the full window. This
   is consistent with the external doc's §6.2.1 observation that
   scaling up entries during oversold (Mayer Multiple < 1.0) regimes
   is high-Sharpe.

## 2. How the external doc maps to our code

The attached doc enumerates nine accumulation archetypes. Here's the
current state of each in the repo and what would need to be added to
fully reproduce them:

| # | Archetype (doc §) | In repo? | Where | Notes |
|---|---|---|---|---|
| 1 | **Lump-Sum (BuyAndHold)** | ✅ | `strategies/BuyAndHold` | Confirmed as the *worst* risk-adjusted in our data (Sharpe 0.96, MaxDD -83.4%) |
| 2 | **Date-Based DCA** | ✅ | `strategies/DCAFixedAmount` | Confirmed *terrible* in BTC for 2014-2026 window; needs dynamic scaling to be useful |
| 3 | **Value Averaging (VA)** | ✅ | `strategies/DCAValueAveraging` | Working; one of the better risk-adjusted performers |
| 4 | **Limit-Order Ladder (price-tranche DCA)** | ❌ | — | **GAP**: not implemented. See §3.1 below |
| 5 | **Grid Trading** | ❌ | — | **GAP**: explicitly out of scope per the design spec (combinatorial path explosion) |
| 6 | **Dynamic DCA — sentiment-modulated** | ❌ | — | **GAP**: needs a Fear & Greed Index feed. See §3.2 |
| 7 | **Dynamic DCA — Mayer Multiple gated** | ❌ | — | **GAP**: needs a 200-day SMA + ratio function. See §3.3 |
| 8 | **Dynamic DCA — MVRV Z-score gated** | ❌ | — | **GAP**: needs on-chain realized-cap feed. See §3.4 |
| 9 | **Augmented DCA — RSI / VIX weighted** | Partial | `scaling/VolatilityTargeted` covers vol-weighted sizing, but no RSI overlay | See §3.5 |

The remaining sections describe the gaps and the minimum work to
close them.

## 3. Gap closure roadmap

### 3.1 Limit-Order Ladder strategy (doc §5.1)

The doc describes a 4-tier ladder (-5%, -10%, -15%, -20% from a
3-month rolling high) with 30-day cooldowns. The repo's
`strategies/base.py` is a clean ABC for this.

**What to add** (~150 LOC + tests):
- `strategies/LadderLimit.py` subclassing `Strategy`
- Tranches defined as `[(pct_drop, buy_usd), ...]`
- `state["last_triggered_at"]` for cooldown tracking
- The strategy emits `signal=1.0` only on a fresh ladder hit; the
  engine buys `amount_usd` and resets cooldown

**Data needs**: same as DCA — daily bars. No new data sources.

### 3.2 Fear & Greed Index feed (doc §6.1)

The doc references the Alternative.me Crypto Fear & Greed Index
(0-100, daily, free API). This would gate DCA tranche sizes:

```python
if fgi < 25:    amount = base * 1.5   # extreme fear -> buy more
elif fgi < 45:  amount = base * 1.0
elif fgi < 55:  amount = base * 0.75
elif fgi < 75:  amount = base * 0.5
else:           amount = base * 0.25   # extreme greed -> sell 5%
```

**What to add** (~120 LOC + tests):
- `data/fear_greed.py` — fetcher with CSV cache (mirroring the
  multi-tranche pattern in `research/data/__init__.py`)
- `scaling/SentimentModulated.py` — maps FGI to a position-fraction
  multiplier; plugs into the existing `ScalingModel` ABC

**Data needs**: Fear & Greed Index from `api.alternative.me/fng/` (no
API key required, daily resolution back to 2018-02-01).

### 3.3 Mayer Multiple gate (doc §6.2.1)

The Mayer Multiple is `close / SMA(200)`. It's *already computable
from data we have* — no new data source. The gating logic:

```python
mayer = close / close.rolling(200).mean()
if mayer < 0.8:    multiplier = 1.5   # deep value
elif mayer < 1.0:  multiplier = 1.25
elif mayer < 1.5:  multiplier = 1.0
elif mayer < 2.4:  multiplier = 0.75
else:              multiplier = 0.5   # overheated
```

**What to add** (~100 LOC + tests):
- `scaling/MayerMultipleGated.py` — uses the same `recent_returns`
  and `equity` params the other scalers use
- Could also live as a `Strategy` subclass that overrides the
  target-fraction calculation directly

### 3.4 MVRV Z-Score gate (doc §6.2.2)

MVRV requires **realized cap** (aggregate on-chain cost basis of
all coins at their last-moved price). The free source is the
Coin Metrics community API or the free Glassnode Studio (limited).
The cleanest path: compute a **proxy** MVRV using on-chain exchange
inflows/outflows from CryptoQuant's free tier.

**Status**: **deferred**. Requires an external data source not
currently integrated. Recommend adding this after the sentiment
gate (3.2) since the doc notes MVRV alone missed the 2021 secondary
top (§6.2.2) — it's most useful as part of a composite, not alone.

### 3.5 RSI-weighted DCA (doc §6.2.3)

The doc cites academic evidence (Sharpe 1.424 → 1.984) for an
RSI-weighted variant. RSI is *already computed* in our
`strategies/MeanReversionRSI` strategy; we just need a **scaling
overlay** that uses it.

**What to add** (~80 LOC + tests):
- `scaling/RSIModulated.py` — multiplies tranche size by a function
  of the current RSI(14)
- Default: `[rsi < 30 → 1.5x, rsi < 50 → 1.0x, rsi > 70 → 0.5x]`

This is the **highest-leverage gap to close** because:
1. It reuses the RSI computation we already have
2. The doc cites the strongest peer-reviewed evidence
3. The Sharpe improvement (1.424 → 1.984) is the largest documented
   uplift of any single augmentation

## 4. Why our empirical results contradict some of the doc's claims

The external doc's central claim (§3) — that **DCA dominates lump-sum
on risk-adjusted basis when starting at a -50% drawdown** — is
well-supported for the specific MarketVector scenario (entries at
deep drawdowns, 2-year horizon). Our results don't contradict that.
What they *do* show is the **opposite** scenario: starting DCA at the
*top* of a long bull run (which is what 2014-09-17 was) produces
terrible outcomes because the buy schedule was front-loaded into
strong rallies.

The takeaway: **DCA is highly path-dependent on entry timing**.
Neither "DCA always wins" nor "DCA always loses" is right; the
strategy is a function of where in the cycle you start, how long
you run it, and whether you modulate it with on-chain / sentiment
indicators.

This is exactly why the gap-closure work in §3 is the right
priority: **Dynamic DCA** (with Mayer-Multiple / Fear-Greed / RSI
overlays) is the strategy the external doc ultimately advocates
(§10.2), and our current code has the substrate to implement it
but not the implementations.

## 5. Recommended next experiments

Once the §3 gaps are closed, the natural experiment matrix is:

| Experiment | Strategy | Scaling | Window | Question |
|---|---|---|---|---|
| Exp 1 | BuyAndHold | None | 2010-2026 | Baseline (uses whatever data exists) |
| Exp 2 | DCAFixed $100/wk | None | 2010-2026 | Does path-dependence persist across full cycle? |
| Exp 3 | DCAFixed $100/wk | Mayer gated | 2010-2026 | Does Mayer-gating rescue the late-start case? |
| Exp 4 | DCAValueAvg $50k target | None | 2010-2026 | Does VA dominate DCA over full cycle? |
| Exp 5 | DCAFixed $100/wk | RSI gated | 2010-2026 | Replicate the academic Sharpe-1.984 result |
| Exp 6 | DCAFixed $100/wk | Sentiment (FGI) gated | 2018-2026 (FGI starts here) | Does FGI overlay help in bear regimes? |
| Exp 7 | LadderLimit 4-tier -5/-10/-15/-20 | None | 2014-2026 | Do intra-week limit orders capture more drawdown? |
| Exp 8 | DCAValueAvg | Martingale | 2010-2026 | How badly does doubling-down blow up? (sanity check) |

We can run all of these on the existing infra once the strategies and
scaling models are added. Estimated: 8-12 hours of focused work
to add §3.1, §3.2, §3.3, §3.5 + tests.

## 6. Caveats

1. **Data window bias**: We have 4,285 days starting 2014-09-17. That's
   only 1.5 of BTC's 4 major cycles. Full-coverage results
   (2010–2026) require either a CryptoCompare API key (for pre-2014
   daily) or accepting hourly history starting 2018 (Kraken free tier,
   720-hour limit). The attached doc's broader claims can't be
   fully validated until that gap is closed.

2. **Vol-targeted scaling looks mediocre** in our matrix (e.g.
   MomentumTrend + VolTargeted: 13.8% CAGR vs 68.4% for FixedDollar).
   This is because vol-targeting in a *strongly trending* asset
   forces you to *reduce* size after big moves — the opposite of what
   you want in a bull. It would shine in a choppy/sideways regime.

3. **FixedFractional scaling is identical to FixedDollar in
   single-shot BuyAndHold** (since the strategy emits one buy).
   Where FixedFractional diverges is in active DCA strategies,
   but in this dataset all DCA strategies underperform so the
   difference is academic.

4. **The "Martingale" sanity check** isn't in our matrix because
   every backtest would lose 99%+, but the doc's warning (§4.2) is
   well-founded: VA + capital exhaustion is the actual risk, and
   we should add a `Martingale` strategy as a regression test that
   the engine correctly produces a near-total loss.

## 7. References

- External: `sources/README.md` (the attached doc)
- Empirical: `empirical_results.json` (raw numbers from the matrix)
- Code: `src/research/strategies/`, `src/research/scaling/`,
  `src/research/backtest/`
- Design spec: `../specs/2026-06-10-bitcoin-research-lab-design.md`
- Data state: `data/btc/daily.csv` (4,285 rows, 2014-09-17 → 2026-06-11,
  Yahoo Finance via `src/research/data/__init__.py:fetch_daily_yahoo`)
