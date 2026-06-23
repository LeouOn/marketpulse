"""Gold vs Bitcoin vs Property: $800K analysis."""
import sys, os, warnings
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from datetime import date
from src.research.data.yahoo import YahooProvider
from src.research.data.fred import FredProvider
from src.research.data import load_daily
from src.research.montecarlo import simulate_gbm
from src.research.macro.factors import MacroFactorProvider

y = YahooProvider(); f = FredProvider()
P = "=" * 80
print(P)
print("GOLD vs BITCOIN vs PROPERTY: $800K ALLOCATION ANALYSIS")
print(P)

btc = load_daily("2018-01-01", "2025-06-19")
gld = y.fetch("GLD", "2015-06-19", "2025-06-19")
cs = f.fetch("CSUSHPINSA", "2015-06-01", "2025-06-01")

print("\n1. HISTORICAL PERFORMANCE")
print("-" * 80)
for name, df, col in [("Bitcoin", btc, "close"), ("Gold (GLD)", gld, "close"), ("Property", cs, "close")]:
    s, e = df[col].iloc[0], df[col].iloc[-1]
    yrs = (df.index[-1] - df.index[0]).days / 365.25 if hasattr(df.index[-1], "days") else 7.0
    cagr = ((e/s) ** (1/yrs) - 1) * 100
    rets = df[col].pct_change().dropna()
    vol = rets.std() * np.sqrt(252) * 100
    sharpe = (rets.mean()*252) / (rets.std()*np.sqrt(252)) if rets.std() > 0 else 0
    dd = ((df[col] / df[col].expanding().max() - 1) * 100).min()
    print(f"  {name:15s}: CAGR={cagr:+6.1f}%/yr  Vol={vol:5.1f}%  Sharpe={sharpe:.2f}  MaxDD={dd:.0f}%")

print("\n2. WHAT $800K BECOMES (historical rates)")
print("-" * 80)
for name, df, col in [("Bitcoin", btc, "close"), ("Gold (GLD)", gld, "close"), ("Property", cs, "close")]:
    s, e = df[col].iloc[0], df[col].iloc[-1]
    yrs = 7.0 if name == "Bitcoin" else 10.0
    cagr = (e/s) ** (1/yrs) - 1
    f5 = 800000 * (1+cagr)**5
    f10 = 800000 * (1+cagr)**10
    print(f"  {name:15s}: 5Y=${f5:>12,.0f}  10Y=${f10:>12,.0f}  ({cagr*100:+.1f}%/yr)")

mfp = MacroFactorProvider()
fdf = mfp.load_factors(date(2020,1,1), date(2025,6,19))
mort_rate = fdf.mortgage_30y.dropna().iloc[-1] / 100
cpi_yoy = fdf.cpi_yoy.dropna().iloc[-1]
real_mort = mort_rate - cpi_yoy
cs_cagr = ((cs.close.iloc[-1] / cs.close.iloc[0]) ** (1/10) - 1)

print(f"\n3. PROPERTY LEVERAGE (mortgage={mort_rate*100:.2f}%, real={real_mort*100:.2f}%)")
print("-" * 80)
for label, prop_val, down, mortgage in [
    ("A: $800K property cash",     800000,  800000, 0),
    ("B: $160K down on $800K",     800000,  160000, 640000),
    ("C: $800K down on $4M",      4000000,  800000, 3200000),
]:
    ann = mortgage * (mort_rate*(1+mort_rate)**30) / ((1+mort_rate)**30-1) if mortgage > 0 else 0
    print(f"\n  {label}:")
    for yr in [5, 10, 30]:
        pf = prop_val * (1 + cs_cagr) ** yr
        rem = max(mortgage*(1+mort_rate)**yr - ann*((1+mort_rate)**yr-1)/mort_rate, 0) if mortgage > 0 else 0
        eq = pf - rem
        roi = (eq - down) / down * 100
        print(f"    {yr:2d}Y: Value=${pf:>10,.0f}  Equity=${eq:>10,.0f}  ROI={roi:+.0f}%")
    if mortgage > 0:
        print(f"    Payment: ${ann/12:,.0f}/mo")

print(f"\n4. MONTE CARLO 5-YEAR FORWARD ($800K each)")
print("-" * 80)
for name, mu, sigma in [
    ("Gold",                0.05, 0.16),
    ("Bitcoin",             0.15, 0.60),
    ("Property (cash)",     0.05, 0.05),
    ("Property (5x lev)",   0.25, 0.25),
]:
    r = simulate_gbm(mu=mu, sigma=sigma, s0=800000, n_steps=5*252, n_paths=10000, seed=42)
    t = r.terminal_values
    rets = (t / 800000 - 1) * 100
    med_val = np.percentile(t, 50)
    print(f"  {name:22s}: Med=${med_val/1e6:.2f}M  |  "
          f"5th={np.percentile(rets,5):+.0f}%  Med={np.percentile(rets,50):+.0f}%  "
          f"95th={np.percentile(rets,95):+.0f}%  |  "
          f"P(>0)={np.mean(rets>0)*100:.0f}%  P(<-50%)={np.mean(rets<-50)*100:.0f}%")

print(f"\n5. STRATEGIC ASSESSMENT")
print("-" * 80)
print(f"""
  CURRENT MACRO (June 2026):
    10Y Real Yield:  {fdf.real_yield_10y.dropna().iloc[-1]:.2f}% (HIGH - headwind for all)
    Mortgage Rate:   {mort_rate*100:.2f}% (HIGH - leverage is expensive)
    Real Mortgage:   {real_mort*100:.2f}% (after inflation - moderate)
    VIX:             {fdf.vix.dropna().iloc[-1]:.1f} (elevated)

  THE THREE ASSETS:

  GOLD:
    + 5000-year track record, zero counterparty risk, crisis insurance
    - No yield, opportunity cost when real yields >2% (current)
    Best in: INFLATION, RECESSION, DEFLATION_SCARE
    5Y median: ~$1.02M (+28%). Low vol, low risk, low reward.

  BITCOIN:
    + Asymmetric upside, outside monetary system, fixed supply
    - -80% drawdowns happened 3x. Untested in deep recession.
    Best in: RISK_ON + liquidity expansion
    5Y median: ~$1.6M (+100%) but 5th pct = ~$160K (-80%)
    Highest expected return, highest risk of total loss.

  PROPERTY (with leverage):
    + ONLY asset where $800K controls $4M. 5x leverage at fixed rate 30Y.
    + Forced savings (principal paydown), inflation hedge, you live in it
    - Illiquid, concentrated, transaction costs, maintenance
    Best in: moderate growth + stable/falling rates
    5Y median (5x lev): ~$2.5M (+200%) but 20% decline = total equity wipeout

  THE LEVERAGE INSIGHT (the whole game):
    $800K down on $4M property at 5% appreciation = $200K/yr gains
    That's 25%/yr on your $800K equity, BEFORE:
    - Principal paydown (forced savings ~$20K/yr early years)
    - Rental income or replaced rent (lifestyle benefit)
    - Tax deductions (mortgage interest, depreciation)
    In 10 years at 5% appreciation: property = $6.5M, equity = $3.3M+ = 300%+ ROI

  BUT: At 6.85% mortgage, you need property to appreciate faster than
  the real mortgage cost ({real_mort*100:.1f}% after inflation) to come out ahead.
  Case-Shiller national 10Y CAGR: {cs_cagr*100:.1f}%/yr.

  RECOMMENDED $800K SPLIT (illustrative, not financial advice):
  +-------------------------+----------+-----------------------------------+
  | Asset                   | Amount   | Rationale                         |
  +-------------------------+----------+-----------------------------------+
  | Property (down payment) | $350K    | 20% down on $1.75M = 5x leverage |
  | Gold (GLD/physical)     | $200K    | Crisis insurance + inflation hedge|
  | Bitcoin (DCA 6-12mo)    | $100K    | Asymmetric upside satellite       |
  | Cash / T-Bills          | $150K    | Dry powder at 4.3% yield          |
  +-------------------------+----------+-----------------------------------+
  | TOTAL                   | $800K    | Balanced across all four buckets  |
  +-------------------------+----------+-----------------------------------+

  WHY THIS SPLIT:
  - Property leverage is your return engine ($350K controls $1.75M)
  - Gold is your hedge (rallies in recession when property suffers)
  - Bitcoin is your lottery ticket (small allocation, huge upside)
  - Cash gives optionality (buy more of whatever crashes)
""")
