"""
Weekly Macro Briefing Generator
Produces a podcast-ready markdown file for NotebookLM.
Run every week: python scripts/weekly_macro_briefing.py
Output: reports/weekly/macro_briefing_YYYY-MM-DD.md
"""
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import numpy as np
import yfinance as yf
from src.research.macro.regimes import RulesBasedClassifier

# ============================================================================
# DATA LOADING
# ============================================================================

def load_fred_series(name):
    """Load a FRED series from cached parquet."""
    path = Path(f"data/macro/{name}.parquet")
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    df["ts"] = pd.to_datetime(df["ts"])
    if df["ts"].dt.tz is not None:
        df["ts"] = df["ts"].dt.tz_convert("UTC").dt.tz_localize(None)
    return df.set_index("ts")["close"].sort_index()

def fetch_latest(ticker, period="5d"):
    """Fetch latest price via yfinance."""
    try:
        df = yf.download(ticker, period=period, progress=False, auto_adjust=False)
        if df is None or len(df) == 0:
            return None, None
        close = df["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        return float(close.iloc[-1]), float(close.iloc[0])
    except:
        return None, None

def fetch_history(ticker, days=30):
    """Fetch N days of history."""
    try:
        df = yf.download(ticker, period=f"{days}d", progress=False, auto_adjust=False)
        if df is None or len(df) == 0:
            return None
        close = df["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        return close
    except:
        return None

# ============================================================================
# MAIN BRIEFING GENERATOR
# ============================================================================

def generate_briefing():
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")
    
    print(f"Generating macro briefing for {date_str}...")
    
    # ---- Load FRED macro data ----
    fred_series = {
        "DFF": "Fed Funds Rate",
        "DGS10": "10Y Treasury",
        "DFII10": "10Y Real Yield",
        "T10YIE": "10Y Breakeven Inflation",
        "DTWEXBGS": "DXY (Trade-Weighted Dollar)",
        "VIXCLS": "VIX",
        "UNRATE": "Unemployment",
        "CPIAUCSL": "CPI",
        "MORTGAGE30US": "30Y Mortgage Rate",
        "DCOILWTICO": "WTI Oil (FRED)",
        "CSUSHPINSA": "Case-Shiller CA",
        "IPMAN": "Manufacturing (IPMAN)",
    }
    
    fred_data = {}
    for sid, name in fred_series.items():
        s = load_fred_series(sid)
        if s is not None and len(s) > 0:
            fred_data[sid] = {"name": name, "series": s, "latest": float(s.iloc[-1])}
    
    # ---- Load factors for regime classification ----
    factors = pd.read_parquet("data/macro/factors.parquet")
    
    # ---- Classify current regime ----
    rc = RulesBasedClassifier()
    regime_probs = rc.classify(factors)
    latest_regime = regime_probs.iloc[-1]
    top_regime = latest_regime.idxmax()
    
    # Gold: use spot (GC=F) not GLD ETF
    gold_spot, _ = fetch_latest("GC=F", "8d")
    silver_spot, _ = fetch_latest("SI=F", "8d")
    gold_spot_30d = fetch_history("GC=F", 30)
    
    # ---- Fetch live market data ----
    market_tickers = {
        "SPY": "S&P 500",
        "QQQ": "Nasdaq 100",
        "NQ=F": "E-mini Nasdaq (futures)",
        "^GSPC": "S&P 500 Index",
        "GLD": "Gold ETF",
        "SLV": "Silver ETF",
        "PPLT": "Platinum ETF",
        "CL=F": "WTI Crude Oil",
        "BTC-USD": "Bitcoin",
        "EWH": "Hong Kong ETF",
        "URA": "Uranium Miners",
        "XLE": "Energy Sector",
        "STNG": "Scorpio Tankers",
        "LMT": "Lockheed Martin",
        "UAL": "United Airlines",
        "ICLN": "Clean Energy",
        "SPY_hist": "SPY 30D",
    }
    
    market_data = {}
    for ticker, name in market_tickers.items():
        if ticker.endswith("_hist"):
            continue
        latest, week_ago = fetch_latest(ticker, period="8d")
        hist_30d = fetch_history(ticker, 30)
        market_data[ticker] = {
            "name": name,
            "latest": latest,
            "week_ago": week_ago,
            "hist_30d": hist_30d,
        }
    
    # ---- Compute key metrics ----
    
    # Rates
    dff = fred_data.get("DFF", {}).get("latest", 0)
    dgs10 = fred_data.get("DGS10", {}).get("latest", 0)
    dfii10 = fred_data.get("DFII10", {}).get("latest", 0)
    t10yie = fred_data.get("T10YIE", {}).get("latest", 0)
    dtwex = fred_data.get("DTWEXBGS", {}).get("latest", 0)
    vix = fred_data.get("VIXCLS", {}).get("latest", 0)
    unrate = fred_data.get("UNRATE", {}).get("latest", 0)
    cpi_yoy = None
    if "CPIAUCSL" in fred_data:
        cpi_s = fred_data["CPIAUCSEL" if "CPIAUCSEL" in fred_data else "CPIAUCSL"]["series"]
        if len(cpi_s) >= 13:
            cpi_yoy = (cpi_s.iloc[-1] / cpi_s.iloc[-13] - 1) * 100
    mort30 = fred_data.get("MORTGAGE30US", {}).get("latest", 0)
    
    # Market prices
    spy = market_data.get("SPY", {}).get("latest", 0)
    qqq = market_data.get("QQQ", {}).get("latest", 0)
    gld = market_data.get("GLD", {}).get("latest", 0)
    slv = market_data.get("SLV", {}).get("latest", 0)
    cl = market_data.get("CL=F", {}).get("latest", 0)
    btc = market_data.get("BTC-USD", {}).get("latest", 0)
    
    # Week-over-week changes
    def wow(ticker):
        d = market_data.get(ticker, {})
        if d.get("latest") and d.get("week_ago") and d["week_ago"] > 0:
            return (d["latest"] / d["week_ago"] - 1) * 100
        return None
    
    spy_wow = wow("SPY")
    qqq_wow = wow("QQQ")
    gld_wow = wow("GLD")
    slv_wow = wow("SLV")
    cl_wow = wow("CL=F")
    btc_wow = wow("BTC-USD")
    
    # 30-day returns
    def ret_30d(ticker):
        h = market_data.get(ticker, {}).get("hist_30d")
        if h is not None and len(h) >= 2:
            return (h.iloc[-1] / h.iloc[0] - 1) * 100
        return None
    
    spy_30d = ret_30d("SPY")
    gld_30d = ret_30d("GLD")
    slv_30d = ret_30d("SLV")
    cl_30d = ret_30d("CL=F")
    btc_30d = ret_30d("BTC-USD")
    
    # Gold/Silver ratio
    gsr = None
    gld_price = fetch_latest("GC=F", "5d")[0]
    si_price = fetch_latest("SI=F", "5d")[0]
    if gld_price and si_price and si_price > 0:
        gsr = gld_price / si_price
    
    # Oil term structure
    clz27 = fetch_latest("CLZ27.NYM", "5d")[0]
    cl_front = cl
    
    # Regime probabilities
    regime_pct = {r: float(latest_regime[r]) * 100 for r in latest_regime.index}
    
    # ============================================================================
    # GENERATE BRIEFING TEXT
    # ============================================================================
    
    equity_observation = (
        "Equity momentum is positive but the regime and VIX suggest caution. "
        "Do not chase strength without momentum confirmation."
        if top_regime != "RISK_ON"
        else "RISK_ON regime supports equity longs. "
        "Trend-following strategies should be favored over counter-trend."
    )

    gsr_display = f"{gsr:.1f}" if gsr else "N/A"
    cpi_display = f"{cpi_yoy:.1f}%" if cpi_yoy else "N/A"
    
    briefing = f"""# Weekly Macro Briefing - {date_str}

## Overview

**Date:** {date_str}
**Macro Regime:** {top_regime} ({regime_pct[top_regime]:.0f}% probability)

### Regime Probability Distribution
- RISK_ON: {regime_pct.get('RISK_ON', 0):.0f}%
- RECESSION: {regime_pct.get('RECESSION', 0):.0f}%
- INFLATION_ACCEL: {regime_pct.get('INFLATION_ACCEL', 0):.0f}%
- DEFLATION_SCARE: {regime_pct.get('DEFLATION_SCARE', 0):.0f}%
- REAL_YIELD_SHOCK: {regime_pct.get('REAL_YIELD_SHOCK', 0):.0f}%

**What this means:** The macro environment is currently classified as {top_regime}. This regime has been the dominant state, reflecting the balance between economic growth, inflation pressures, and central bank policy.

---

## Interest Rates & Bonds

**Current Rate Structure:**
- Fed Funds Rate: {dff:.2f}%
- 10Y Treasury Yield: {dgs10:.2f}%
- 10Y Real Yield: {dfii10:.2f}%
- 10Y Breakeven Inflation: {t10yie:.2f}%
- 30Y Mortgage Rate: {mort30:.2f}%

**Analysis:** The yield curve shows a {('steepening' if dgs10 > dff else 'flat/inverted')} pattern with the 10Y at {dgs10:.2f}% versus Fed Funds at {dff:.2f}%. Real yields at {dfii10:.2f}% {'remain elevated' if dfii10 > 1.5 else 'have moderated'}, which {'continues to pressure risk assets and precious metals' if dfii10 > 1.5 else 'is supportive of risk assets and gold'}. The breakeven inflation rate of {t10yie:.2f}% suggests markets expect inflation to {'remain sticky' if t10yie > 2.5 else 'continue moderating'}.

**Key signal:** {'High real yields above 2% are a headwind for gold, Bitcoin, and growth stocks. The Fed remains restrictive.' if dfii10 > 2.0 else 'Real yields below 2% are supportive of risk assets and precious metals. The Fed may be approaching a pivot.'}

---

## The Dollar & Currency

**Trade-Weighted Dollar Index:** {dtwex:.1f}

**Analysis:** The dollar is {'strengthening' if dtwex > 105 else 'relatively stable' if dtwex > 95 else 'weakening'}, which {'pressures commodity prices and emerging markets' if dtwex > 105 else 'supports commodity prices and risk assets' if dtwex < 95 else 'is neutral for cross-asset positioning'}. The dollar's trajectory will be a key driver for gold, oil, and equities in the coming weeks.

---

## Volatility & Sentiment

**VIX:** {vix:.1f}

**Interpretation:**
- VIX < 15: Complacency, low fear, potential for sharp correction
- VIX 15-20: Normal range, healthy market
- VIX 20-30: Elevated fear, size down risk positions
- VIX > 30: Crisis mode, defensive only

**Current read:** VIX at {vix:.1f} is {'in the crisis zone' if vix > 30 else 'elevated, suggesting market uncertainty' if vix > 20 else 'in the normal range' if vix > 15 else 'low, suggesting complacency'}. {'The market is pricing significant tail risk. Reduce position sizes.' if vix > 25 else 'Volatility is manageable. Standard risk parameters apply.' if vix > 15 else 'Low VIX can be a contrarian sell signal if other indicators deteriorate.'}

---

## Equities

**S&P 500 (SPY):** ${spy:.2f} ({spy_wow:+.1f}% week, {spy_30d:+.1f}% month)
**Nasdaq 100 (QQQ):** ${qqq:.2f} ({qqq_wow:+.1f}% week)

**Analysis:** The S&P 500 is {('up' if spy_wow > 0 else 'down')} {abs(spy_wow):.1f}% this week and {('up' if spy_30d > 0 else 'down')} {abs(spy_30d):.1f}% over the past month. The market is {'in a confirmed uptrend' if spy_30d > 3 else 'consolidating' if abs(spy_30d) < 3 else 'in a correction phase'}. The Nasdaq {'is outperforming the S&P' if qqq_wow > spy_wow else 'is underperforming the S&P'}, suggesting {'risk-on rotation into growth/tech' if qqq_wow > spy_wow else 'defensive rotation'}.

**Key observation:** {equity_observation}

---

## Commodities

### Oil (WTI)
**Current:** ${cl:.2f}/bbl ({cl_wow:+.1f}% week, {cl_30d:+.1f}% month)
**Dec 2027 Futures:** ${clz27:.2f}/bbl
**Term Structure:** {('BACKWARDATION (tight prompt market)' if cl > clz27 else 'CONTANGO (market expects normalization)' if clz27 > cl else 'FLAT')}
**Spread:** ${cl - clz27:+.2f}/bbl

**Context:** The Strait of Hormuz crisis continues to dominate oil markets. Iran has repeatedly threatened and enacted closures throughout 2026, though the US-Iran memorandum of understanding signed June 18 provided temporary relief. Today (June 20), Iran declared the strait "closed" again over Israel's Lebanon strikes, though CENTCOM disputes this claim. The term structure in {('backwardation suggests physical tightness persists' if cl > clz27 else 'contango suggests markets expect supply normalization')}. Oil at ${cl:.0f} is well below the March peak of ~$118 but remains {('+' if cl > 67 else '')}{(cl/67-1)*100:.0f}% above the pre-war level of ~$67.

### Gold
**GLD:** ${gld:.2f} ({gld_wow:+.1f}% week, {gld_30d:+.1f}% month)
**Gold/Silver Ratio:** {gsr_display}

**Analysis:** Gold is {('rallying' if gld_wow > 0 else 'pulling back')} this week. The gold/silver ratio at {gsr_display} is {('elevated (silver historically cheap)' if gsr and gsr > 80 else 'neutral' if gsr and 55 < gsr <= 80 else 'low (silver expensive)' if gsr else '')}. Real yields at {dfii10:.2f}% {'remain a headwind for gold' if dfii10 > 2 else 'are supportive of gold'}. Gold's performance during the Iran war and Hormuz disruption has been surprisingly muted, as real yields and dollar strength offset safe-haven demand.

### Silver
**SLV:** ${slv:.2f} ({slv_wow:+.1f}% week, {slv_30d:+.1f}% month)

**Analysis:** Silver is {'outperforming gold' if slv_wow > gld_wow else 'underperforming gold'} this week. Silver's dual nature (monetary + industrial) means it benefits from both safe-haven flows and industrial demand. The solar panel and electrification trend provides structural demand support.

### Uranium
**URA:** ${market_data.get('URA', {}).get('latest', 0):.2f}

**Analysis:** Uranium miners represent the structural nuclear renaissance play. AI data centers, global decarbonization, and COP28 commitments to triple nuclear capacity by 2050 underpin multi-year demand growth.

---

## Cryptocurrency

**Bitcoin:** ${btc:,.0f} ({btc_wow:+.1f}% week, {btc_30d:+.1f}% month)

**Analysis:** Bitcoin is {('rallying' if btc_wow > 0 else 'consolidating' if abs(btc_wow) < 3 else 'selling off')} this week. The correlation between Bitcoin and tech equities remains positive, while its correlation with gold remains low, supporting the digital gold narrative. {'Bitcoin is acting as a risk asset, not a safe haven, in the current environment.' if spy_wow > 0 and btc_wow > 0 else 'Bitcoin is decoupling from equities, potentially finding its own narrative.'}

---

## Housing

**30Y Mortgage Rate:** {mort30:.2f}%
**Case-Shiller CA:** {fred_data.get('CSUSHPINSA', {}).get('latest', 'N/A')}

**Analysis:** Mortgage rates at {mort30:.2f}% {'continue to pressure housing affordability' if mort30 > 6.5 else 'are becoming more supportive of housing demand'}. The Bay Area market, with its high absolute prices, is particularly sensitive to rate movements. Potential homebuyers should monitor the 10Y Treasury yield as a leading indicator for mortgage rate direction.

---

## Employment & Inflation

**Unemployment Rate:** {unrate:.1f}%
**CPI Year-over-Year:** {cpi_display}
**Manufacturing (IPMAN):** {fred_data.get('IPMAN', {}).get('latest', 'N/A')}

**Analysis:** Unemployment at {unrate:.1f}% is {('elevated and rising, consistent with recession risk' if unrate > 5 else 'stable at a level consistent with moderate growth' if unrate > 3.5 else 'very low, suggesting a tight labor market')}. The Sahm Rule recession indicator should be monitored for signs of labor market deterioration. {'A rising unemployment rate is the single most important recession signal to watch.' if unrate > 4.5 else ''}

---

## Geopolitical Risk Monitor

**Strait of Hormuz:** ACTIVE CRISIS - Iran declared closure again today (June 20) over Israel's Lebanon strikes. US/CENTCOM disputes. This is the 4th closure cycle in 2026. Pattern: Iran declares closure, market spikes, ceasefire negotiated, repeat.

**US-Iran Status:** Memorandum of Understanding signed June 18. Fragile. 60-day negotiation window. Iran wants US port blockade lifted; US wants Hormuz guaranteed open.

**Key risk:** If Israel escalates in Lebanon, the ceasefire could collapse, potentially triggering a full re-closure of Hormuz and oil spike toward $100+.

**Oil trading implication:** Trim into strength ($88-92 area). The recurring closure pattern creates spikes that fade. Each cycle has a lower peak ($118 to ~$90 range). The market is learning to price in periodic disruption rather than permanent closure.

---

## Cross-Asset Correlations (Quick Read)

| Pair | Correlation | Signal |
|------|------------|--------|
| Gold vs Real Yields | Negative (strong) | High real yields pressure gold |
| Silver vs Gold | Positive (high) | Silver is high-beta gold |
| Oil vs VIX | Positive | Oil spikes create fear |
| BTC vs SPY | Positive (moderate) | BTC behaves as risk asset |
| Dollar vs Gold | Negative | Strong dollar pressures gold |
| Dollar vs Oil | Negative | Strong dollar pressures oil |

---

## MNQ Trading Bias for Next Week

**Regime:** {top_regime} ({regime_pct[top_regime]:.0f}%)
**VIX:** {vix:.1f}
**Direction Bias:** {('LONG-FAVORABLE' if top_regime == 'RISK_ON' and vix < 25 else 'NEUTRAL/DEFENSIVE' if top_regime in ['INFLATION_ACCEL', 'DEFLATION_SCARE'] or vix > 25 else 'SHORT-FAVORABLE' if top_regime == 'REAL_YIELD_SHOCK' else 'CAUTIOUS')}

**Key rule:** {'DO NOT FIGHT THE TREND. RISK_ON + low VIX = trend-following environment. Counter-trend trades have lost 53% historically in this regime.' if top_regime == 'RISK_ON' and vix < 25 else 'Reduce risk. Elevated VIX or non-RISK_ON regime means smaller positions, tighter stops.'}

---

## What to Watch Next Week

1. **Hormuz status** - Any escalation in Lebanon could trigger re-closure cycle
2. **10Y Treasury yield** - If it breaks above {'4.5%' if dgs10 < 4.5 else '5%'}, risk assets will face pressure
3. **VIX** - A spike above 30 would signal crisis mode; reduce all risk positions
4. **Unemployment claims** - Rising claims = recession signal
5. **Gold/Silver ratio** - If it breaks above 90, silver is a strong buy signal
6. **Bitcoin** - Watch for decoupling from equities as a risk sentiment indicator
7. **Fed speakers** - Any hint of pivot or hawkish surprise

---

## Portfolio Positioning Summary

| Asset | Current Bias | Rationale |
|-------|-------------|-----------|
| Equities (SPY/QQQ) | {('Overweight' if top_regime == 'RISK_ON' and vix < 20 else 'Neutral' if vix < 25 else 'Underweight')} | {('RISK_ON regime supports risk' if top_regime == 'RISK_ON' else 'Regime uncertainty suggests caution')} |
| Gold | {('Accumulate on weakness' if dfii10 > 2 else 'Core holding')} | Real yields {'are a headwind; DCA' if dfii10 > 2 else 'supportive'} |
| Silver | Accumulate | GSR at {gsr:.0f} if available; DCA over 4-6 months |
| Oil | Trim into strength | Sell 60-70% at $88-92; keep 10% tail hedge |
| Bitcoin | Core holding | Structural bull; size for volatility |
| Cash/T-bills | {('Overweight' if vix > 25 else 'Moderate')} | {('Defensive in elevated VIX' if vix > 25 else 'Optionality for opportunities')} |

---

## Trend Danger Score (for MNQ/NQ trading)

Based on regime ({top_regime}), VIX ({vix:.1f}), and trend structure:
**Score:** {min(100, int(regime_pct.get('RISK_ON', 0) * 0.4 + (25 if vix < 18 else 15 if vix < 25 else 5) + 20))}/100
**Guidance:** {('EXTREME DANGER for counter-trend. Trade WITH the trend or stay flat.' if regime_pct.get('RISK_ON', 0) > 35 and vix < 25 else 'Moderate risk. Counter-trend OK with small size and tight stops.' if regime_pct.get('RISK_ON', 0) < 30 else 'Standard risk management applies.')}

---

*Generated by Weekly Macro Briefing Generator on {date_str}*
*Data sources: FRED, Yahoo Finance, internal regime classifier*
*This is analysis, not investment advice. Consult a financial advisor.*
"""

    # ---- Save to file ----
    report_dir = Path("reports/weekly")
    report_dir.mkdir(parents=True, exist_ok=True)
    
    output_path = report_dir / f"macro_briefing_{date_str}.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(briefing)
    
    print(f"\nBriefing saved to: {output_path}")
    print(f"File size: {output_path.stat().st_size / 1024:.1f} KB")
    print(f"Word count: {len(briefing.split())} words")
    
    return briefing, output_path

# ============================================================================
# RUN
# ============================================================================

if __name__ == "__main__":
    briefing, path = generate_briefing()
    print("\n" + "=" * 80)
    print("FULL BRIEFING OUTPUT:")
    print("=" * 80)
    print(briefing)
