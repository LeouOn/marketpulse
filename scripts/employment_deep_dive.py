"""Detailed employment and economic data snapshot for June 2026."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import yfinance as yf

print("=" * 90)
print("EMPLOYMENT & ECONOMIC DEEP DIVE -- JUNE 2026 SNAPSHOT")
print("=" * 90)

# ---- Gold price clarification ----
print("\n0. GOLD PRICE CLARIFICATION")
print("-" * 90)
try:
    df = yf.download("GC=F", period="5d", progress=False, auto_adjust=False)
    gc_close = df["Close"]
    if isinstance(gc_close, pd.DataFrame):
        gc_close = gc_close.iloc[:, 0]
    gold_spot = float(gc_close.iloc[-1])
except:
    gold_spot = 4173  # fallback

gold_per_gram = gold_spot / 31.1035
print(f"  Gold spot (GC=F):     ${gold_spot:,.2f}/oz")
print(f"  Gold per gram:        ${gold_per_gram:,.2f}/gram")
print(f"  Gold per kg:          ${gold_per_gram*1000:,.0f}/kg")
print(f"  GLD ETF (1/10th oz):  $387.12/share")
print(f"  => For podcast: use SPOT PRICE ${gold_spot:,.0f}/oz, NOT the ETF price")

# ---- Load FRED employment data ----
print("\n1. LABOR MARKET DETAILED")
print("-" * 90)

def load_fred(name):
    p = Path(f"data/macro/{name}.parquet")
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    df["ts"] = pd.to_datetime(df["ts"])
    if df["ts"].dt.tz is not None:
        df["ts"] = df["ts"].dt.tz_localize(None)
    return df.set_index("ts")["close"].sort_index()

# Unemployment rate - full detail
unrate = load_fred("UNRATE")
if unrate is not None:
    print(f"\n  UNEMPLOYMENT RATE (UNRATE):")
    print(f"    Latest ({unrate.index[-1].date()}): {float(unrate.iloc[-1]):.1f}%")
    print(f"    1Y ago:                    {float(unrate.iloc[-13]):.1f}%")
    print(f"    2Y ago:                    {float(unrate.iloc[-25]):.1f}%")
    print(f"    5Y ago:                    {float(unrate.iloc[-61]):.1f}%")
    print(f"    12M trend:                 {float(unrate.iloc[-13]):.1f}% -> {float(unrate.iloc[-1]):.1f}%")
    
    # Recent 12 months
    print(f"    Last 12 months:")
    for i in range(-12, 0):
        d = unrate.index[i]
        v = float(unrate.iloc[i])
        print(f"      {d.strftime('%Y-%m')}: {v:.1f}%")

# ---- Try to fetch additional employment series from FRED ----
print(f"\n  ADDITIONAL LABOR INDICATORS (try to fetch):")
print(f"  (These are commonly-tracked Fed indicators)")

# Check what we have vs what we'd want
available = {
    "UNRATE": "Unemployment Rate",
    "CPIAUCSL": "CPI (All Items)",
    "IPMAN": "Manufacturing Production (IPMAN proxy for ISM)",
}

wanted = {
    "PAYEMS": "Total Nonfarm Payrolls (jobs count)",
    "ICSA": "Initial Jobless Claims (weekly)",
    "CIVPART": "Labor Force Participation Rate",
    "CES0500000008": "Average Hourly Earnings (wage growth)",
    "IURSA": "Insured Unemployment Rate",
    "UEMPMEAN": "Average Duration of Unemployment (weeks)",
    "JTSJOL": "Job Openings (JOLTS)",
    "JTSQUITR": "Quit Rate (JOLTS - worker confidence)",
    "FEDFUNDS": "Effective Federal Funds Rate",
    "PCEPI": "PCE Price Index (Fed's preferred inflation)",
    "PCEPILFE": "Core PCE (excl food/energy)",
    "GDPC1": "Real GDP",
    "INDPRO": "Industrial Production Index",
    "UMCSENT": "Consumer Sentiment (U Mich)",
    "T10YIE": "Breakeven Inflation",
}

print(f"\n  HAVE in cache: {list(available.keys())}")
print(f"  SHOULD ADD for complete picture:")

# Try fetching a few key ones
import requests
from src.research.data.fred import FredProvider
fp = FredProvider()
key = fp.api_key

test_series = {
    "PAYEMS": "Nonfarm Payrolls",
    "ICSA": "Initial Jobless Claims",
    "CIVPART": "Labor Force Participation",
    "CES0500000008": "Avg Hourly Earnings YoY",
    "FEDFUNDS": "Effective Fed Funds",
    "PCEPI": "PCE Price Index",
    "PCEPILFE": "Core PCE",
    "GDPC1": "Real GDP",
    "INDPRO": "Industrial Production",
    "UMCSENT": "Consumer Sentiment",
    "JTSJOL": "Job Openings (JOLTS)",
    "DTB3": "3-Month T-Bill",
    "BAA10Y": "Baa-10Y Credit Spread",
    "WALCL": "Fed Balance Sheet (Total Assets)",
    "T5YIE": "5Y Breakeven Inflation",
    "M2SL": "M2 Money Supply",
}

print(f"\n  {'Series':<25} {'Latest Value':>15} {'Description':<40}")
print("  " + "-" * 85)

fetched_data = {}
for sid, desc in test_series.items():
    try:
        r = requests.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params={
                "series_id": sid,
                "api_key": key,
                "file_type": "json",
                "limit": 3,
                "sort_order": "desc",
            },
            timeout=10,
        )
        data = r.json()
        obs = data.get("observations", [])
        if obs:
            latest_val = obs[0].get("value", "N/A")
            latest_date = obs[0].get("date", "?")
            try:
                val_float = float(latest_val)
                print(f"  {sid:<25} {val_float:>15,.1f}  {desc} ({latest_date})")
                fetched_data[sid] = {"value": val_float, "date": latest_date, "desc": desc}
            except ValueError:
                print(f"  {sid:<25} {latest_val:>15}  {desc} ({latest_date})")
    except:
        print(f"  {sid:<25} {'N/A':>15}  {desc} (fetch failed)")

# ---- Employment analysis ----
print("\n\n2. EMPLOYMENT SITUATION ANALYSIS")
print("-" * 90)

if unrate is not None:
    current_ur = float(unrate.iloc[-1])
    prev_ur = float(unrate.iloc[-2])
    year_ago_ur = float(unrate.iloc[-13]) if len(unrate) >= 13 else current_ur
    
    print(f"\n  UNEMPLOYMENT RATE:")
    print(f"    Current:      {current_ur:.1f}%")
    print(f"    Last month:   {prev_ur:.1f}%")
    print(f"    1 year ago:   {year_ago_ur:.1f}%")
    print(f"    Change YoY:   {current_ur - year_ago_ur:+.1f}pp")
    
    if current_ur > year_ago_ur + 0.5:
        print(f"    SIGNAL: RISING unemployment (recession risk indicator)")
        print(f"    Sahm Rule: {'TRIGGERED' if current_ur - min(unrate.iloc[-12:].values) > 0.5 else 'not triggered yet'}")
    elif current_ur < year_ago_ur:
        print(f"    SIGNAL: FALLING/improving unemployment (healthy labor market)")
    else:
        print(f"    SIGNAL: STABLE unemployment (neutral)")

if "PAYEMS" in fetched_data:
    print(f"\n  NONFARM PAYROLLS (jobs):")
    print(f"    Latest: {fetched_data['PAYEMS']['value']:,.0f} total jobs")
    print(f"    (Month-over-month change would need prior month for delta)")

if "CIVPART" in fetched_data:
    print(f"\n  LABOR FORCE PARTICIPATION:")
    print(f"    Latest: {fetched_data['CIVPART']['value']:.1f}%")
    print(f"    (Pre-COVID was ~63.4%, long-term decline from 67% in 2000)")

if "CES0500000008" in fetched_data:
    print(f"\n  AVERAGE HOURLY EARNINGS (wage growth):")
    print(f"    Latest: ${fetched_data['CES0500000008']['value']:.2f}")
    print(f"    (If YoY growth > 4%, inflationary pressure. If < 3%, soft labor market)")

if "ICSA" in fetched_data:
    print(f"\n  INITIAL JOBLESS CLAIMS (weekly):")
    print(f"    Latest: {fetched_data['ICSA']['value']:,.0f}")
    print(f"    (Below 250K = healthy. Above 350K = recession signal. Above 500K = crisis)")

if "JTSJOL" in fetched_data:
    print(f"\n  JOB OPENINGS (JOLTS):")
    print(f"    Latest: {fetched_data['JTSJOL']['value']:,.0f}")
    print(f"    (High openings = labor shortage. Low openings = weak demand)")

# ---- Fed / Monetary Policy ----
print("\n\n3. FEDERAL RESERVE & MONETARY POLICY")
print("-" * 90)

if "FEDFUNDS" in fetched_data:
    print(f"\n  EFFECTIVE FED FUNDS RATE: {fetched_data['FEDFUNDS']['value']:.2f}%")

if "WALCL" in fetched_data:
    print(f"  FED BALANCE SHEET: ${fetched_data['WALCL']['value']/1e6:,.0f}T")
    print(f"  (Peak was ~$9T in 2022. QT is shrinking this.)")

if "M2SL" in fetched_data:
    m2 = fetched_data["M2SL"]["value"]
    print(f"  M2 MONEY SUPPLY: ${m2/1e3:,.1f}T")
    print(f"  (M2 growth > 10% = inflationary. Contraction = deflationary)")

if "DTB3" in fetched_data:
    print(f"  3-MONTH T-BILL: {fetched_data['DTB3']['value']:.2f}%")

# ---- Inflation detail ----
print("\n\n4. INFLATION DETAILED")
print("-" * 90)

if "PCEPI" in fetched_data:
    print(f"  PCE PRICE INDEX: {fetched_data['PCEPI']['value']:.1f}")
    print(f"  (Fed's PREFERRED inflation measure. Target: 2%)")

if "PCEPILFE" in fetched_data:
    print(f"  CORE PCE (ex food/energy): {fetched_data['PCEPILFE']['value']:.1f}")
    print(f"  (Fed's PRIMARY inflation target. Sticky > 2.5% = hawkish Fed)")

cpi = load_fred("CPIAUCSL")
if cpi is not None and len(cpi) >= 13:
    cpi_yoy = (cpi.iloc[-1] / cpi.iloc[-13] - 1) * 100
    cpi_3m = (cpi.iloc[-1] / cpi.iloc[-4] - 1) * 400  # annualized 3-month
    print(f"  CPI YoY: {cpi_yoy:.1f}%")
    print(f"  CPI 3M annualized: {cpi_3m:.1f}%")
    print(f"  (3M annualized shows recent trend vs 12M trailing)")

# ---- Credit & Risk ----
print("\n\n5. CREDIT MARKETS & RISK INDICATORS")
print("-" * 90)

if "BAA10Y" in fetched_data:
    print(f"  Baa-10Y Credit Spread: {fetched_data['BAA10Y']['value']:.2f}%")
    print(f"  (Above 2% = stress. Above 3% = crisis. Below 1.5% = calm)")

# VIX
vix = load_fred("VIXCLS")
if vix is not None:
    print(f"  VIX: {float(vix.iloc[-1]):.1f}")

# ---- Economic Growth ----
print("\n\n6. ECONOMIC GROWTH")
print("-" * 90)

if "GDPC1" in fetched_data:
    print(f"  Real GDP (latest): {fetched_data['GDPC1']['value']:,.0f}")
    print(f"  (Need QoQ annualized for growth rate)")

if "INDPRO" in fetched_data:
    print(f"  Industrial Production: {fetched_data['INDPRO']['value']:.1f}")

if "UMCSENT" in fetched_data:
    sent = fetched_data["UMCSENT"]["value"]
    print(f"  Consumer Sentiment (U Mich): {sent:.1f}")
    print(f"  (Below 60 = pessimistic. Above 90 = optimistic. Above 100 = very confident)")

# ---- Summary for podcast ----
print("\n\n" + "=" * 90)
print("PODCAST-READY EMPLOYMENT & ECONOMIC SUMMARY")
print("=" * 90)
print(f"""
KEY NUMBERS FOR JUNE 2026:

LABOR MARKET:
  - Unemployment: {float(unrate.iloc[-1]):.1f}% (was {float(unrate.iloc[-13]):.1f}% a year ago)
  - Trend: {'RISING (concerning)' if unrate.iloc[-1] > unrate.iloc[-13] else 'STABLE or improving'}
""")

for sid, label in [("PAYEMS", "Nonfarm Payrolls"), ("CIVPART", "Participation Rate"), 
                     ("CES0500000008", "Avg Hourly Earnings"), ("ICSA", "Initial Jobless Claims"),
                     ("JTSJOL", "Job Openings")]:
    if sid in fetched_data:
        v = fetched_data[sid]["value"]
        if sid == "ICSA":
            print(f"  - {label}: {v:,.0f}")
        elif sid in ("PAYEMS", "JTSJOL"):
            print(f"  - {label}: {v:,.0f}")
        else:
            print(f"  - {label}: {v}")

print(f"""
INFLATION:
  - CPI YoY: {cpi_yoy:.1f}% (if available)
  - Core PCE: (fetch from FRED)
  - Breakeven: market expects ~{float(load_fred('T10YIE').iloc[-1]):.1f}% inflation over 10Y

FED POLICY:
  - Fed Funds Rate: {fetched_data.get('FEDFUNDS', {}).get('value', 'N/A')}% (if available)
  - Balance Sheet: QT ongoing (shrinking)
  - Real yields: ~{float(load_fred('DFII10').iloc[-1]):.2f}% (restrictive territory)

THE STORY:
  The labor market is {'cooling' if unrate.iloc[-1] > unrate.iloc[-13] else 'stable'}.
  Unemployment at {float(unrate.iloc[-1]):.1f}% is {'above' if float(unrate.iloc[-1]) > 4.0 else 'at or below'} the 
  natural rate. The Fed faces a dilemma: inflation at {cpi_yoy:.1f}% is still above the 2% target,
  but {'rising unemployment' if unrate.iloc[-1] > unrate.iloc[-13] else 'the labor market'} may force a dovish pivot.
  
  Key tension: Real yields at {float(load_fred('DFII10').iloc[-1]):.2f}% are restrictive enough to slow the economy,
  but the Fed hasn't cut because inflation hasn't reached 2%. This creates a fragile equilibrium
  where any negative surprise (Hormuz, credit event, tech correction) could tip into recession.
""")
