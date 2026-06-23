"""Check current oil term structure and key levels for the cut/hold decision."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import yfinance as yf

print("=" * 80)
print("OIL TERM STRUCTURE & KEY LEVELS (Jun 20, 2026)")
print("=" * 80)

# Pull the futures curve - key contracts
contracts = {
    "CL=F":   "WTI front month",
    "CLG=F":  "Feb 2027 (7M out)",
    "CLZ=F":  "Dec 2027 (18M out)",
    "CLZ27.NYM": "Dec 2027 (alt ticker)",
    "BZ=F":   "Brent front",
    "B=F":    "Brent (alt)",
    "HO=F":   "Heating oil",
    "RB=F":   "RBOB gasoline",
    "NG=F":   "Natural gas",
}

print("\n1. CURRENT PRICES")
print("-" * 60)
prices = {}
for ticker, desc in contracts.items():
    try:
        df = yf.download(ticker, period="5d", progress=False, auto_adjust=False)
        if df is not None and len(df) > 0:
            close = df["Close"]
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            latest = float(close.iloc[-1])
            prices[ticker] = latest
            print(f"  {ticker:12} ${latest:>8.2f}  ({desc})")
    except Exception as e:
        print(f"  {ticker:12} ERROR: {e}")

print("\n2. TERM STRUCTURE SHAPE")
print("-" * 60)
if "CL=F" in prices:
    front = prices["CL=F"]
    print(f"  Front month (CL=F):     ${front:>8.2f}")
    if "CLZ=F" in prices or "CLZ27.NYM" in prices:
        back = prices.get("CLZ=F") or prices.get("CLZ27.NYM")
        diff = back - front
        pct = (back / front - 1) * 100
        shape = "CONTANGO" if back > front else "BACKWARDATION"
        annualized = ((back / front) ** (12 / 18) - 1) * 100 if abs(diff) > 0.01 else 0
        print(f"  Dec 2027 (CLZ=F):       ${back:>8.2f}")
        print(f"  Difference:             ${diff:>+8.2f} ({pct:>+5.1f}%)")
        print(f"  Shape:                  {shape}")
        print(f"  Implied annualized roll: {annualized:>+5.1f}%/yr")
        if shape == "CONTANGO":
            print(f"  => Market expects LOWER prices ahead (bearish)")
            print(f"  => Storage traders will buy front, store, sell back = profit")
        else:
            print(f"  => Market expects HIGHER prices ahead (bullish)")
            print(f"  => Prompt market is TIGHT (supply constrained NOW)")

print("\n3. KEY LEVELS TO WATCH")
print("-" * 60)
if "CL=F" in prices:
    current = prices["CL=F"]
    levels = [
        (118, "Mar 2026 peak (war high)"),
        (100, "Round number / psychological"),
        (90, "YOUR CUT LEVEL"),
        (81, "Current Brent (approx)"),
        (76, "Current WTI (approx)"),
        (73, "Pre-war (Feb 27, 2026)"),
        (70, "Citi Q4 2026 forecast"),
        (50, "Analyst flush-warning (60M barrels)"),
    ]
    print(f"  {'Price':>8}  {'Description':<40} {'Distance':>10}")
    for price, desc in levels:
        dist = (price / current - 1) * 100
        marker = " <<<" if "YOUR" in desc else ""
        print(f"  ${price:>7.0f}  {desc:<40} {dist:>+9.1f}%{marker}")

print("\n4. RISK/REWARD FROM CURRENT LEVEL")
print("-" * 60)
if "CL=F" in prices:
    current = prices["CL=F"]
    # Bullish targets
    t1 = current * 1.18  # +18% = back to $90-ish on WTI
    t2 = 100
    t3 = 118
    # Bearish targets
    s1 = 73  # pre-war
    s2 = 70  # Citi forecast
    s3 = 50  # flush warning
    print(f"  From current WTI ${current:.2f}:")
    print(f"  UPSIDE targets:")
    print(f"    +18% -> ${t1:.2f} (your $90 cut level)")
    print(f"    +31% -> ${t2:.2f} (round number / psychological)")
    print(f"    +54% -> ${t3:.2f} (Mar peak, IF sustained closure resumes)")
    print(f"  DOWNSIDE targets:")
    print(f"    -5% -> ${s1:.2f} (pre-war level, IF peace holds)")
    print(f"    -9% -> ${s2:.2f} (Citi Q4 forecast)")
    print(f"    -35% -> ${s3:.2f} (flush warning, IF 60M barrels dump)")
    print()
    print(f"  Risk/Reward at $90 cut:")
    print(f"    From $90, upside to $118 = +31%")
    print(f"    From $90, downside to $70 = -22%")
    print(f"    From $90, downside to $50 = -44%")
    print(f"    RR ratio: 31/44 = 0.7x (POOR - downside dominates)")
    print(f"    RR ratio: 31/22 = 1.4x (OK if $70 is the floor)")
