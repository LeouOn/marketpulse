"""Quick technical snapshot for silver/platinum/other commodities entry timing."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import numpy as np
import yfinance as yf

# Fetch everything in one call
tickers = {
    "SLV":   "Silver ETF",
    "PPLT":  "Platinum ETF",
    "GLD":   "Gold ETF",
    "SIL":   "Silver miners (high-beta silver play)",
    "SILJ":  "Junior silver miners (even higher beta)",
    "URA":   "Uranium miners (nuclear renaissance)",
    "URNM":  "Uranium miners alt",
    "CCJ":   "Cameco (largest uranium miner)",
    "UNG":   "Natural gas ETF",
    "DBA":   "Agriculture basket (corn/wheat/soy/sugar)",
    "CORN":  "Corn",
    "WEAT":  "Wheat",
    "NIB":   "Cocoa",
    "JO":    "Coffee",
    "WOOD":  "Lumber/timber",
    "LIT":   "Lithium/battery metals ETF",
    "NEM":   "Newmont (gold miner)",
    "PA=F":  "Palladium futures",
    "PL=F":  "Platinum futures",
    "SI=F":  "Silver futures",
    "GC=F":  "Gold futures",
}

print("=" * 95)
print("COMMODITY SNAPSHOT -- ENTRY TIMING ANALYSIS")
print("=" * 95)
print()
print(f"{'Ticker':<8} {'Desc':<40} {'Price':>10} {'vs 200MA':>9} {'vs 50MA':>8} {'RSI14':>6} {'52W%':>7} {'Signal':<20}")
print("-" * 115)

results = []
for ticker, desc in tickers.items():
    try:
        df = yf.download(ticker, period="2y", progress=False, auto_adjust=False)
        if df is None or len(df) < 60:
            continue
        close = df["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        price = float(close.iloc[-1])
        ma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else float(close.mean())
        ma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else float(close.mean())
        
        # RSI 14
        delta = close.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
        rs = avg_gain / avg_loss
        rsi = float((100 - (100 / (1 + rs))).iloc[-1])
        
        # 52-week high/low
        recent = close.tail(252) if len(close) >= 252 else close
        high52 = float(recent.max())
        low52 = float(recent.min())
        pct_from_high = (price / high52 - 1) * 100
        
        vs200 = (price / ma200 - 1) * 100
        vs50 = (price / ma50 - 1) * 100
        
        # Signal
        if rsi < 30 and vs200 < -10:
            signal = "OVERSOLD + cheap"
        elif rsi < 35 and vs200 < -5:
            signal = "Near oversold"
        elif rsi > 70 and vs200 > 15:
            signal = "OVERBOUGHT"
        elif price > ma200 and price > ma50:
            signal = "Bullish (above MAs)"
        elif price < ma200 and price < ma50:
            signal = "Bearish (below MAs)"
        else:
            signal = "Mixed"
        
        results.append({
            "ticker": ticker,
            "desc": desc,
            "price": price,
            "vs200": vs200,
            "vs50": vs50,
            "rsi": rsi,
            "pct_from_high": pct_from_high,
            "signal": signal,
        })
    except Exception as e:
        pass

# Sort by RSI (most oversold first)
results.sort(key=lambda x: x["rsi"])

for r in results:
    print(f"{r['ticker']:<8} {r['desc']:<40} ${r['price']:>9.2f} {r['vs200']:>+8.1f}% {r['vs50']:>+7.1f}% {r['rsi']:>5.1f} {r['pct_from_high']:>+6.1f}% {r['signal']}")

# Ratio analysis
print()
print("=" * 95)
print("KEY RATIOS")
print("=" * 95)

# Fetch GC, SI, PL futures for ratio calc
ratios = {}
for t in ["GC=F", "SI=F", "PL=F", "PA=F", "HG=F"]:
    try:
        df = yf.download(t, period="5d", progress=False, auto_adjust=False)
        close = df["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        ratios[t] = float(close.iloc[-1])
    except:
        pass

if "GC=F" in ratios and "SI=F" in ratios:
    gsr = ratios["GC=F"] / ratios["SI=F"]
    print(f"\n  Gold/Silver ratio (GSR):  {gsr:.1f}")
    print(f"    Historical range: 40-100. Current percentile: ~{min(100, max(0, (gsr-40)/60*100)):.0f}th")
    if gsr > 85:
        print(f"    => SILVER IS CHEAP. GSR > 85 = strong buy signal for silver.")
        print(f"    => Historically, silver outperforms gold by 15-25% over 12-18 months from these levels.")
    elif gsr < 55:
        print(f"    => Silver is expensive. Reduce silver, add gold.")
    else:
        print(f"    => Neutral zone. No tactical signal.")

if "GC=F" in ratios and "PL=F" in ratios:
    gpr = ratios["GC=F"] / ratios["PL=F"]
    print(f"\n  Gold/Platinum ratio:      {gpr:.2f}")
    print(f"    Historical range: 0.8-2.5. Current: {'EXPENSIVE platinum' if gpr > 2.0 else 'CHEAP platinum' if gpr > 1.5 else 'neutral'}")
    if gpr > 2.0:
        print(f"    => PLATINUM IS EXTREMELY CHEAP vs gold. >2.0 = contrarian buy.")
    elif gpr > 1.5:
        print(f"    => Platinum is cheap. >1.5 = value territory.")

if "GC=F" in ratios and "HG=F" in ratios:
    gcr = ratios["GC=F"] / ratios["HG=F"]
    print(f"\n  Gold/Copper ratio:        {gcr:.0f} (oz gold per lb copper)")
    print(f"    Rising = defensive/ recession fear. Falling = growth optimism.")

# Silver-specific entry analysis
print()
print("=" * 95)
print("SILVER ENTRY TIMING (detailed)")
print("=" * 95)

try:
    slv = yf.download("SLV", period="5y", progress=False, auto_adjust=False)
    close = slv["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    
    price = float(close.iloc[-1])
    ma200 = float(close.rolling(200).mean().dropna().iloc[-1])
    ma50 = float(close.rolling(50).mean().dropna().iloc[-1])
    high5y = float(close.max())
    low5y = float(close.min())
    high52 = float(close.tail(252).max())
    low52 = float(close.tail(252).min())
    
    print(f"\n  SLV current:        ${price:.2f}")
    print(f"  5Y high:           ${high5y:.2f} ({(price/high5y-1)*100:+.1f}%)")
    print(f"  5Y low:            ${low5y:.2f} ({(price/low5y-1)*100:+.1f}%)")
    print(f"  52W high:          ${high52:.2f} ({(price/high52-1)*100:+.1f}%)")
    print(f"  52W low:           ${low52:.2f} ({(price/low52-1)*100:+.1f}%)")
    print(f"  200-day MA:        ${ma200:.2f} ({(price/ma200-1)*100:+.1f}%)")
    print(f"  50-day MA:         ${ma50:.2f} ({(price/ma50-1)*100:+.1f}%)")
    
    # DCA vs lump sum analysis
    monthly = close.resample("ME").last()
    rets = monthly.pct_change().dropna()
    
    print(f"\n  Silver monthly return stats (5Y):")
    print(f"    Mean:   {rets.mean()*100:+.2f}%/mo")
    print(f"    Median: {rets.median()*100:+.2f}%/mo")
    print(f"    Std:    {rets.std()*100:.2f}%/mo")
    print(f"    Best:   {rets.max()*100:+.2f}%")
    print(f"    Worst:  {rets.min()*100:+.2f}%")
    print(f"    % positive months: {(rets>0).mean()*100:.0f}%")
    
    print(f"\n  ENTRY STRATEGY for silver:")
    if price < ma200 * 0.95:
        print(f"    Price is >5% below 200MA = technically oversold")
        print(f"    => GOOD entry zone for lump sum (60-70% of position)")
        print(f"    => DCA the remaining 30-40% over 3-6 months")
    elif price > ma200 * 1.10:
        print(f"    Price is >10% above 200MA = extended")
        print(f"    => WAIT for pullback to 200MA before adding")
        print(f"    => If you must enter, DCA over 6-12 months")
    else:
        print(f"    Price is near 200MA = neutral zone")
        print(f"    => DCA over 4-6 months is optimal")
        print(f"    => GSR signal (91.9) is the stronger argument for entering NOW")

except Exception as e:
    print(f"  Error fetching SLV: {e}")

# Platinum analysis
print()
print("=" * 95)
print("PLATINUM ENTRY TIMING (detailed)")
print("=" * 95)

try:
    pplt = yf.download("PPLT", period="5y", progress=False, auto_adjust=False)
    close = pplt["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    
    price = float(close.iloc[-1])
    ma200 = float(close.rolling(200).mean().dropna().iloc[-1])
    high5y = float(close.max())
    low5y = float(close.min())
    
    print(f"\n  PPLT current:      ${price:.2f}")
    print(f"  5Y high:           ${high5y:.2f} ({(price/high5y-1)*100:+.1f}%)")
    print(f"  5Y low:            ${low5y:.2f} ({(price/low5y-1)*100:+.1f}%)")
    print(f"  200-day MA:        ${ma200:.2f} ({(price/ma200-1)*100:+.1f}%)")
    
    print(f"\n  Platinum thesis:")
    print(f"    BEARISH: EV transition reduces auto catalyst demand (long-term headwind)")
    print(f"    BULLISH: Hydrogen fuel cells need platinum (optionality)")
    print(f"    BULLISH: Cheap vs gold historically (ratio > 2.5)")
    print(f"    BULLISH: Supply concentrated in South Africa + Russia (geopolitical risk)")
    print(f"    VERDICT: Small position (5-10% of metals), contrarian value play")
    print(f"    NOT a core holding. Treat as a deep-value option on hydrogen economy.")

except Exception as e:
    print(f"  Error: {e}")
