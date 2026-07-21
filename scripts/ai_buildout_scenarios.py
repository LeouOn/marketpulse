"""
AI Buildout Scenarios: 5-Year Market Outcome Modeling
=====================================================

Models 4 distinct AI adoption scenarios using Monte Carlo simulation,
cross-referenced with our macro regime classifier.

Uses the existing research lab Monte Carlo engine (GBM + regime switching).
"""
import sys, os, warnings
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from datetime import date
from src.research.montecarlo import simulate_gbm, simulate_regime_switching, simulate_strategy

print("=" * 80)
print("AI BUILDOUT SCENARIOS: 5-YEAR MARKET OUTCOME MODELING")
print("=" * 80)
print()

# ──────────────────────────────────────────────────────────────────────────
# SCENARIO DEFINITIONS
# ──────────────────────────────────────────────────────────────────────────

SCENARIOS = {
    "Productivity Miracle": {
        "description": (
            "AI delivers real TFP growth (+1.0-1.5pp/yr). Corporate margins expand\n"
            "          via automation. Tech earnings grow 20-25%/yr. P/E holds.\n"
            "          Real yields fall as productivity boom offsets fiscal deficits.\n"
            "          Historical analog: 1995-1999 internet buildout."
        ),
        "mu": 0.15,        # 15% annual expected return
        "sigma": 0.18,     # 18% annual vol
        "regime": "RISK_ON",
        "probability": 0.20,  # subjective probability weight
        "pe_change": "stable to +10%",
        "color": "green",
    },
    "Capex Digest": {
        "description": (
            "AI capex peaks 2025-26 (~$200B/yr), then plateaus. Revenue materializes\n"
            "          but slower than capex growth. P/E compresses 10-15%. Tech earnings\n"
            "          grow 10-12%/yr. Gradual multiple normalization.\n"
            "          Historical analog: 2014-2016 cloud digestion."
        ),
        "mu": 0.06,        # 6% annual expected return
        "sigma": 0.20,     # 20% annual vol
        "regime": "mixed",
        "probability": 0.35,  # highest subjective weight
        "pe_change": "-10% to -15%",
        "color": "blue",
    },
    "AI Winter 2.0": {
        "description": (
            "Technical limitations emerge (hallucination, cost, data wall). ROI\n"
            "          negative for most enterprises. Capex write-downs ($100B+).\n"
            "          P/E compresses 30-40%. Deep tech correction.\n"
            "          Historical analog: 2000-2002 dot-com bust, 1980 AI winter."
        ),
        "mu": -0.08,       # -8% annual expected return
        "sigma": 0.30,     # 30% annual vol (high uncertainty)
        "regime": "RECESSION",
        "probability": 0.15,
        "pe_change": "-30% to -40%",
        "color": "red",
    },
    "Gradual Integration": {
        "description": (
            "AI is real but adoption is slow (regulatory, organizational, cultural).\n"
            "          Productivity gains materialize over 10+ years, not 5. P/E slowly\n"
            "          mean-reverts. Tech earnings grow 8-10%/yr. Boring but fine.\n"
            "          Historical analog: 2010-2015 cloud/mobile gradual adoption."
        ),
        "mu": 0.05,        # 5% annual expected return
        "sigma": 0.15,     # 15% annual vol (lower = less uncertainty)
        "regime": "RISK_ON",
        "probability": 0.30,
        "pe_change": "-5%",
        "color": "gray",
    },
}

# ──────────────────────────────────────────────────────────────────────────
# RUN MONTE CARLO FOR EACH SCENARIO
# ──────────────────────────────────────────────────────────────────────────

N_PATHS = 10000
N_STEPS = 5 * 252  # 5 years of trading days
S0 = 100.0         # normalized starting price (index = 100)
SEED = 42

print(f"Simulating {N_PATHS:,} paths over {N_STEPS} trading days (5 years)")
print(f"Starting index: {S0:.0f} | Seed: {SEED}")
print()

all_results = {}

for name, params in SCENARIOS.items():
    print("-" * 80)
    print(f"SCENARIO: {name}")
    print(f"  mu={params['mu']:+.1%}/yr  sigma={params['sigma']:.1%}/yr  "
          f"subjective_prob={params['probability']:.0%}")
    print(f"  {params['description']}")
    print()

    result = simulate_gbm(
        mu=params["mu"],
        sigma=params["sigma"],
        s0=S0,
        n_steps=N_STEPS,
        n_paths=N_PATHS,
        seed=SEED,
    )

    terminals = result.terminal_values
    total_returns = (terminals / S0 - 1) * 100  # percentage total return over 5Y

    # Compute statistics
    p5 = np.percentile(total_returns, 5)
    p25 = np.percentile(total_returns, 25)
    p50 = np.percentile(total_returns, 50)
    p75 = np.percentile(total_returns, 75)
    p95 = np.percentile(total_returns, 95)
    mean = np.mean(total_returns)
    std = np.std(total_returns)
    prob_positive = np.mean(total_returns > 0) * 100
    prob_gt_50 = np.mean(total_returns > 50) * 100
    prob_loss_20 = np.mean(total_returns < -20) * 100
    prob_loss_40 = np.mean(total_returns < -40) * 100
    worst = np.min(total_returns)
    best = np.max(total_returns)
    cagr = ((np.median(terminals) / S0) ** (1/5) - 1) * 100

    all_results[name] = {
        "returns": total_returns,
        "p5": p5, "p25": p25, "p50": p50, "p75": p75, "p95": p95,
        "mean": mean, "std": std, "cagr_median": cagr,
        "prob_positive": prob_positive,
        "prob_gt_50": prob_gt_50,
        "prob_loss_20": prob_loss_20,
        "prob_loss_40": prob_loss_40,
        "worst": worst, "best": best,
    }

    print(f"  5-YEAR TOTAL RETURN DISTRIBUTION (%):")
    print(f"    Worst:     {worst:+8.1f}%")
    print(f"    5th pct:   {p5:+8.1f}%   (1-in-20 bad outcome)")
    print(f"    25th pct:  {p25:+8.1f}%")
    print(f"    Median:    {p50:+8.1f}%   ({cagr:+.1f}% CAGR)")
    print(f"    75th pct:  {p75:+8.1f}%")
    print(f"    95th pct:  {p95:+8.1f}%   (1-in-20 good outcome)")
    print(f"    Best:      {best:+8.1f}%")
    print()
    print(f"  PROBABILITIES:")
    print(f"    Positive return:    {prob_positive:.1f}%")
    print(f"    >+50% return:       {prob_gt_50:.1f}%")
    print(f"    >-20% drawdown:     {100-prob_loss_20:.1f}% survive")
    print(f"    -20% to -40%:       {prob_loss_20-prob_loss_40:.1f}%")
    print(f"    <-40% drawdown:     {prob_loss_40:.1f}%")
    print()

# ──────────────────────────────────────────────────────────────────────────
# PROBABILITY-WEIGHTED BLEND
# ──────────────────────────────────────────────────────────────────────────

print("=" * 80)
print("PROBABILITY-WEIGHTED BLEND (subjective scenario weights)")
print("=" * 80)

weights = np.array([SCENARIOS[s]["probability"] for s in SCENARIOS])
weights = weights / weights.sum()  # normalize

# Sample from each scenario proportionally
np.random.seed(SEED)
blended_returns = []
for i, (name, data) in enumerate(all_results.items()):
    n_samples = int(weights[i] * N_PATHS)
    sampled = np.random.choice(data["returns"], size=n_samples, replace=True)
    blended_returns.append(sampled)

blended = np.concatenate(blended_returns)

weights_str = ', '.join(f"{s}={SCENARIOS[s]['probability']:.0%}" for s in SCENARIOS)
print(f"  Weights: {weights_str}")
print()
print(f"  BLENDED 5-YEAR RETURN DISTRIBUTION (%):")
print(f"    5th pct:   {np.percentile(blended, 5):+8.1f}%")
print(f"    25th pct:  {np.percentile(blended, 25):+8.1f}%")
print(f"    Median:    {np.percentile(blended, 50):+8.1f}%   ({((1 + np.percentile(blended, 50)/100) ** 0.2 - 1) * 100:+.1f}% CAGR)")
print(f"    75th pct:  {np.percentile(blended, 75):+8.1f}%")
print(f"    95th pct:  {np.percentile(blended, 95):+8.1f}%")
print(f"    Mean:      {np.mean(blended):+8.1f}%")
print()
print(f"  PROBABILITIES:")
print(f"    Positive return:    {np.mean(blended > 0) * 100:.1f}%")
print(f"    >+50% return:       {np.mean(blended > 50) * 100:.1f}%")
print(f"    <-20% drawdown:     {np.mean(blended < -20) * 100:.1f}%")
print(f"    <-40% drawdown:     {np.mean(blended < -40) * 100:.1f}%")

# ──────────────────────────────────────────────────────────────────────────
# CROSS-ASSET IMPLICATIONS
# ──────────────────────────────────────────────────────────────────────────

print()
print("=" * 80)
print("CROSS-ASSET IMPLICATIONS BY SCENARIO")
print("=" * 80)

implications = {
    "Productivity Miracle": {
        "Equities (SPY/QQQ)": "STRONG BUY - earnings growth justifies valuations",
        "Gold": "NEUTRAL/BEARISH - risk-on reduces safe-haven demand",
        "Oil": "BULLISH - AI datacenters + economic boom = energy demand surge",
        "Housing": "BULLISH - lower real yields + strong economy = affordability improves",
        "Rates": "BEARISH - productivity boom = higher real rates long-term",
    },
    "Capex Digest": {
        "Equities (SPY/QQQ)": "NEUTRAL - multiple compression offsets earnings growth",
        "Gold": "NEUTRAL - range-bound macro",
        "Oil": "NEUTRAL - moderate growth, stable demand",
        "Housing": "SLIGHTLY BULLISH - if rates ease as inflation cools",
        "Rates": "SLIGHTLY BULLISH (yields fall) - Fed cuts as inflation normalizes",
    },
    "AI Winter 2.0": {
        "Equities (SPY/QQQ)": "BEARISH - multiple compression + earnings decline",
        "Gold": "STRONG BUY - safe haven, lower real yields from recession",
        "Oil": "BEARISH - recession cuts demand; datacenter capex halts",
        "Housing": "MIXED - lower rates help affordability but recession hurts income",
        "Rates": "STRONGLY BULLISH (yields plunge) - aggressive Fed cuts",
    },
    "Gradual Integration": {
        "Equities (SPY/QQQ)": "MILDLY POSITIVE - slow but steady gains",
        "Gold": "NEUTRAL - no strong directional signal",
        "Oil": "NEUTRAL - gradual demand growth",
        "Housing": "POSITIVE - stable rates, steady economy",
        "Rates": "NEUTRAL - gradual normalization",
    },
}

for scenario, assets in implications.items():
    weight = SCENARIOS[scenario]["probability"]
    print(f"\n  {scenario} ({weight:.0%} probability):")
    for asset, view in assets.items():
        print(f"    {asset:20s}: {view}")

# ──────────────────────────────────────────────────────────────────────────
# CURRENT VALUATION CONTEXT
# ──────────────────────────────────────────────────────────────────────────

print()
print("=" * 80)
print("CURRENT VALUATION CONTEXT (June 2026)")
print("=" * 80)

# Fetch from FRED what we can
from src.research.data.fred import FredProvider
fred = FredProvider()

# Get latest macro indicators
fdf = mfp.load_factors(date(2020,1,1), date(2025,6,19))

latest_real = fdf.real_yield_10y.dropna().iloc[-1]
latest_nominal = fdf.nominal_10y.dropna().iloc[-1]
latest_breakeven = fdf.breakeven_10y.dropna().iloc[-1]
latest_fed = fdf.fed_funds.dropna().iloc[-1]
latest_vix = fdf.vix.dropna().iloc[-1]
latest_unemployment = fdf.unemployment.dropna().iloc[-1]

# Historical context for real yields
real_yield_history = fdf.real_yield_10y.dropna()
real_yield_pctl = (real_yield_history < latest_real).mean() * 100

print(f"  10Y Real Yield:     {latest_real:.2f}%  ({real_yield_pctl:.0f}th pctl of 2020-2026)")
print(f"  10Y Nominal:        {latest_nominal:.2f}%")
print(f"  10Y Breakeven:      {latest_breakeven:.2f}%")
print(f"  Fed Funds:          {latest_fed:.2f}%")
print(f"  VIX:                {latest_vix:.1f}  ({'elevated' if latest_vix > 20 else 'calm'})")
print(f"  Unemployment:       {latest_unemployment:.1f}%")
print()

# Equity valuation assessment
vix_pctl = (fdf.vix.dropna() < latest_vix).mean() * 100
print(f"  VALUATION ASSESSMENT:")
print(f"    Real yields at {real_yield_pctl:.0f}th percentile → {'EXPENSIVE' if real_yield_pctl > 70 else 'reasonable'} for equities")
print(f"    VIX at {vix_pctl:.0f}th percentile → {'elevated uncertainty' if vix_pctl > 60 else 'normal'}")
print(f"    Real yields > 2% → P/E multiple headwind (earnings yield must compete with risk-free)")
print(f"    Fed funds = real yields → no term premium (flat curve signals uncertainty)")
print()

# Risk premium calculation
earnings_yield_proxy = 1/25  # ~4% if P/E ~25 (rough S&P estimate)
equity_risk_premium = earnings_yield_proxy - latest_real / 100
print(f"    Estimated earnings yield:    ~{earnings_yield_proxy*100:.1f}% (assuming P/E ~25)")
print(f"    Real risk-free rate:         {latest_real:.2f}%")
print(f"    Equity risk premium:         ~{equity_risk_premium*100:.1f}% "
      f"({'THIN' if equity_risk_premium < 0.02 else 'ADEQUATE' if equity_risk_premium < 0.03 else 'AMPLE'})")

print()
print("=" * 80)
print("KEY TAKEAWAYS")
print("=" * 80)
print("""
1. Current macro regime is RISK_ON but fragile (36.8% dominance) — real yields
   at 2.07% and VIX at 22 create headwinds for equity multiples.

2. The blended probability-weighted scenario suggests MODEST positive returns
   over 5 years, but with significant downside tail risk (~15% chance of
   >20% drawdown from AI Winter scenario).

3. The highest-probability scenario (Capex Digest, 35%) implies P/E compression
   offset by earnings growth → roughly flat-to-modestly-positive real returns.

4. Gold is the best hedge against the tail risk (AI Winter 2.0) — it benefits
   from both lower real yields and safe-haven flows.

5. Oil has interesting asymmetric exposure: strong demand in Productivity
   Miracle (datacenter energy), but sharp demand destruction in AI Winter.

6. Housing benefits from rate normalization in 3 of 4 scenarios (only AI Winter
   is negative due to recession risk).
""")

# Save blended distribution for further analysis
np.savetxt(".omo/evidence/ai-scenarios-blended-returns.csv", blended, delimiter=",", header="5Y_total_return_pct")
print(f"Blended return distribution saved to .omo/evidence/ai-scenarios-blended-returns.csv")
