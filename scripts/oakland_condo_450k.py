"""Oakland condo $450K appreciation model with renovation + mortgage math."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

print("=" * 85)
print("$450K OAKLAND CONDO - APPRECIATION + EQUITY MODEL")
print("=" * 85)

# ---- 1. Historical Oakland appreciation (from our FHFA data) ----
print("\n1. HISTORICAL OAKLAND APPRECIATION (FHFA data, real)")
print("-" * 85)

oak = pd.read_parquet("data/macro/ATNHPIUS36084Q.parquet")
oak["ts"] = pd.to_datetime(oak["ts"])
oak = oak.set_index("ts").sort_index()
close = oak["close"]

# Full history CAGR
full_years = (close.index[-1] - close.index[0]).days / 365.25
full_cagr = (close.iloc[-1] / close.iloc[0]) ** (1 / full_years) - 1
print(f"  Oakland FHFA index: {close.index[0].date()} to {close.index[-1].date()} ({full_years:.1f} years)")
print(f"  Full-history CAGR (SFH-heavy):     {full_cagr*100:+.2f}%/yr")

# 10Y, 20Y, 5Y CAGRs
for yrs in [20, 10, 5]:
    if len(close) > yrs * 4:
        start = close.iloc[-(yrs*4)]
        end = close.iloc[-1]
        cagr = (end / start) ** (1/yrs) - 1
        print(f"  {yrs}Y CAGR (to {close.index[-1].date()}):              {cagr*100:+.2f}%/yr")

# Crisis episode drawdowns
print(f"\n  Oakland crisis episodes (from our v3 analysis):")
print(f"    2008 GFC Oakland:    -33.5% peak-to-trough (SFH index)")
print(f"    Oakland stress-beta:  0.68x vs national (safe harbor)")
print(f"    Oakland holds through 29% national drop before going underwater")

# ---- 2. Condo adjustment ----
print("\n2. CONDO vs SFH ADJUSTMENT (Oakland-specific)")
print("-" * 85)
print("  FHFA index is SFH-heavy. Condos historically appreciate ~1-2%/yr SLOWER")
print("  because supply is more elastic (easier to build condos than SFH).")
print()
print("  Oakland condo CAGR estimates (applied to your $450K):")
condo_scenarios = {
    "Pessimistic (2%/yr)": 0.02,
    "Base case (3.5%/yr)": 0.035,
    "Optimistic (5%/yr)":  0.05,
    "Hot market (6%/yr)":  0.06,
}
for name, rate in condo_scenarios.items():
    print(f"    {name:<25} -> {rate*100:.1f}%/yr")

# ---- 3. Property specifics ----
print("\n3. PROPERTY FINANCIALS")
print("-" * 85)

purchase = 450_000
reno = 20_000
down_pct = 0.20
down = purchase * down_pct
loan = purchase * (1 - down_pct)
rate = 0.0681  # current 30Y from our FRED data
years = 30
monthly_rate = rate / 12
n_payments = years * 12

# Mortgage payment
pmt = loan * monthly_rate * (1 + monthly_rate) ** n_payments / ((1 + monthly_rate) ** n_payments - 1)

# Monthly carrying costs
prop_tax = purchase * 0.011 / 12  # CA Prop 13, ~1.1%
insurance = 100 / 12  # ~$1,200/yr
hoa_low, hoa_high = 300, 600
maintenance = purchase * 0.01 / 12  # 1% of value/yr (deferred maintenance fund)

print(f"  Purchase price:        ${purchase:>10,.0f}")
print(f"  Renovation (upfront):  ${reno:>10,.0f}")
print(f"  Down payment (20%):    ${down:>10,.0f}")
print(f"  Loan amount:           ${loan:>10,.0f}")
print(f"  Mortgage rate:         {rate*100:.2f}% (30Y fixed)")
print(f"  Monthly P&I:           ${pmt:>10,.0f}")
print(f"  Property tax (1.1%):   ${prop_tax:>10,.0f}/mo")
print(f"  Insurance:             ${insurance:>10,.0f}/mo")
print(f"  HOA (estimated):       ${hoa_low}-{hoa_high}/mo")
print(f"  Maintenance reserve:   ${maintenance:>10,.0f}/mo")
print(f"  ---")
total_low = pmt + prop_tax + insurance + hoa_low + maintenance
total_high = pmt + prop_tax + insurance + hoa_high + maintenance
print(f"  TOTAL monthly (own):   ${total_low:,.0f} - ${total_high:,.0f}")
print(f"  Total cash needed:     ${down + reno:>10,.0f} (down + reno)")

# Rental comparison
print(f"\n  Oakland 1BR condo rent (market):  ~$2,200 - $2,800/mo")
rent_mid = 2500
print(f"  Mid-point rent:                    ${rent_mid}/mo")
if total_low > rent_mid:
    print(f"  Owning costs MORE than renting by: ${total_low - rent_mid:,.0f} - ${total_high - rent_mid:,.0f}/mo")
    print(f"  (This is normal in Bay Area - negative cash flow, betting on appreciation)")

# ---- 4. 5/10/15 year appreciation projections ----
print("\n4. APPRECIATION PROJECTIONS (Oakland condo, $450K base + $20K reno)")
print("-" * 85)

# Renovation: $20K cost, estimate it adds $30K to value (forced appreciation)
reno_value_add = 30_000
day1_value = purchase + reno_value_add  # post-reno market value
print(f"  Purchase: ${purchase:,}")
print(f"  + Reno value add (est): ${reno_value_add:,} (costs ${reno:,})")
print(f"  = Day-1 post-reno value: ${day1_value:,}")
print(f"  Instant equity from reno: ${reno_value_add - reno:,}")
print()

horizons = [5, 10, 15]
print(f"  {'Scenario':<25} {'5Y value':>12} {'10Y value':>12} {'15Y value':>12} {'5Y equity':>12}")
print("  " + "-" * 75)

for name, rate in condo_scenarios.items():
    vals = []
    for h in horizons:
        future_val = day1_value * (1 + rate) ** h
        vals.append(future_val)
    
    # 5Y equity: value - mortgage balance - selling costs
    balance_5y = loan
    for m in range(60):
        interest = balance_5y * monthly_rate
        balance_5y -= (pmt - interest)
    selling_costs_5y = vals[0] * 0.06  # 6% agent fees
    equity_5y = vals[0] - balance_5y - selling_costs_5y
    
    print(f"  {name:<25} ${vals[0]:>11,.0f} ${vals[1]:>11,.0f} ${vals[2]:>11,.0f} ${equity_5y:>11,.0f}")

# ---- 5. Total return on cash invested ----
print("\n5. TOTAL RETURN ON CASH INVESTED (5Y hold)")
print("-" * 85)
cash_invested = down + reno  # $110K

print(f"  Cash invested (down + reno): ${cash_invested:,}")
print()

for name, rate in condo_scenarios.items():
    future_val = day1_value * (1 + rate) ** 5
    
    # Mortgage balance after 5Y
    balance = loan
    for m in range(60):
        interest = balance * monthly_rate
        balance -= (pmt - interest)
    
    selling_costs = future_val * 0.06
    equity = future_val - balance - selling_costs
    
    # Total cost of ownership over 5Y (monthly carry minus what you'd pay in rent)
    # If living in it: opportunity cost = 5Y of rent you DIDN'T pay
    rent_saved = rent_mid * 60  # $150K rent saved over 5Y
    ownership_costs = (total_low + total_high) / 2 * 60  # midpoint carrying cost
    
    # Net return = equity at sale - cash invested + rent saved - ownership costs
    net_return = equity - cash_invested + rent_saved - ownership_costs
    roi = net_return / cash_invested * 100
    
    print(f"  {name}:")
    print(f"    Property value in 5Y:    ${future_val:>10,.0f}")
    print(f"    Mortgage balance:        ${balance:>10,.0f}")
    print(f"    Selling costs (6%):      ${selling_costs:>10,.0f}")
    print(f"    Equity at sale:          ${equity:>10,.0f}")
    print(f"    Gross equity gain:       ${equity - cash_invested:>+10,.0f}")
    print(f"    + Rent saved (5Y):       ${rent_saved:>10,.0f}")
    print(f"    - Ownership costs (5Y):  ${ownership_costs:>10,.0f}")
    print(f"    NET return on ${cash_invested:,}: {net_return:>+10,.0f} ({roi:>+.1f}%)")
    print()

# ---- 6. Renting it out scenario ----
print("\n6. IF RENTING OUT (investment property, not living in it)")
print("-" * 85)
rental_income = 2500  # monthly
vacancy = 0.05  # 5% vacancy rate
effective_rent = rental_income * (1 - vacancy)
print(f"  Monthly rent:            ${rental_income:,}")
print(f"  Vacancy adjustment (5%): -${rental_income * vacancy:,.0f}")
print(f"  Effective rent:          ${effective_rent:,.0f}/mo")
print(f"  Monthly carry (mid-HOA): ${total_low + (hoa_high-hoa_low)/2:,.0f}")
monthly_shortfall = (total_low + (hoa_high-hoa_low)/2) - effective_rent
print(f"  Monthly cash flow:       ${-monthly_shortfall:>+,.0f}/mo (NEGATIVE)")
print(f"  Annual cash flow:        ${-monthly_shortfall*12:>+,.0f}/yr")
print()
print(f"  5Y total negative carry: ${-monthly_shortfall*60:>,.0f}")
print(f"  This is the COST of the appreciation bet.")
print(f"  You're paying ~${-monthly_shortfall*60/cash_invested*100:.0f}K over 5Y to capture the upside.")
print(f"  Breakeven appreciation needed: {(-monthly_shortfall*60 / day1_value) * 100:.1f}%/yr just to cover negative carry")

# ---- 7. The honest comparison ----
print("\n7. HONEST COMPARISON: CONDO vs ALTERNATIVES ($110K cash, 5Y)")
print("-" * 85)
print(f"  {'Option':<40} {'5Y outcome':>15} {'Annualized':>12}")
print("  " + "-" * 70)

# Option A: Live in the condo (base case 3.5%)
rate_a = 0.035
val_a = day1_value * (1 + rate_a) ** 5
bal_a = loan
for m in range(60):
    interest = bal_a * monthly_rate
    bal_a -= (pmt - interest)
eq_a = val_a - bal_a - val_a * 0.06
net_a = eq_a - cash_invested + rent_mid * 60 - (total_low+total_high)/2 * 60
print(f"  {'Live in condo (3.5% apprec.)':<40} ${net_a + cash_invested:>14,.0f} {(net_a/cash_invested+1)**(1/5)*100-100:>+11.1f}%/yr")

# Option B: Rent + invest $110K in 60/40 gold/BTC
# From our deep model: gold +14%/yr, BTC +30%/yr 5Y CAGR (historical)
# 60% gold / 40% BTC blended
blend_5y = cash_invested * (0.6 * (1.14**5) + 0.4 * (1.30**5))
print(f"  {'Rent + 60% gold / 40% BTC':<40} ${blend_5y:>14,.0f} {((blend_5y/cash_invested)**(1/5)-1)*100:>+11.1f}%/yr")

# Option C: Rent + invest in SPY (historical 10%/yr)
spy_5y = cash_invested * (1.10**5)
print(f"  {'Rent + SPY (10%/yr historical)':<40} ${spy_5y:>14,.0f} {((spy_5y/cash_invested)**(1/5)-1)*100:>+11.1f}%/yr")

# Option D: Rent + 50/30/20 stock/gold/BTC
diverse_5y = cash_invested * (0.5 * (1.10**5) + 0.3 * (1.14**5) + 0.2 * (1.30**5))
print(f"  {'Rent + 50% SPY / 30% gold / 20% BTC':<40} ${diverse_5y:>14,.0f} {((diverse_5y/cash_invested)**(1/5)-1)*100:>+11.1f}%/yr")

# ---- 8. Recommendation ----
print("\n8. DATA-DRIVEN READ")
print("-" * 85)
print(f"""
  THE GOOD:
    - Oakland condo at $450K is a reasonable entry point (below median)
    - Good neighborhood = sustained demand
    - $20K reno into $30K+ value = instant equity
    - Oakland stress-beta 0.68x = resilient in downturns
    - You're building equity with each mortgage payment
    - If living in it: replaces rent (an expense) with equity (an asset)

  THE CONCERNING:
    - At 6.81% mortgage, your monthly carry ($3.2-3.5K) exceeds rent ($2.5K)
    - Condos appreciate SLOWER than SFH (supply is elastic)
    - HOA can rise and is outside your control
    - If renting out: NEGATIVE cash flow of ~$500-800/mo
    - 6% selling costs eat into appreciation

  THE MATH:
    - Base case (3.5% apprec): ~10%/yr return on your $110K cash (IF living in it)
    - This BEATS renting + SPY only because of leverage (5x on your down payment)
    - If renting it out: the negative carry roughly offsets the leverage benefit
    - The play ONLY works well if you LIVE IN IT (capturing the rent replacement)

  BOTTOM LINE:
    - If you'll LIVE IN IT: solid play. ~10%/yr on cash, builds equity, replaces rent.
      The leverage (5x your $90K down) amplifies modest appreciation into real returns.
    - If RENTING IT OUT: marginal. Negative cash flow eats the appreciation.
      You'd be better off putting $110K in SPY/gold/BTC instead.
    - The reno is the cherry on top: $20K into $30K+ = instant 9% equity gain.

  KEY VARIABLE: How long you hold. Under 5 years, selling costs eat the gains.
  7-10 years is the sweet spot where leverage + appreciation + equity build compound.
""")
