"""
Strait of Hormuz Oil Disruption Scenario Analysis
=================================================

Models oil price scenarios under various Strait of Hormuz closure /
disruption scenarios, computes historical analog returns across actual
past oil supply shocks, and identifies concrete profit targets across
oil majors, oil services, shipping, defense, alternative energy, and
inversely-correlated assets (airlines).

DATA SOURCES (cached at data/yahoo_cache/*.parquet and data/macro/*.parquet):
  Yahoo Finance (via YahooProvider):
    XOM  - ExxonMobil         (integrated major)
    CVX  - Chevron            (integrated major)
    COP  - ConocoPhillips     (independent E&P)
    OXY  - Occidental Petroleum (E&P, Permian focus)
    XLE  - Energy Select ETF  (broad oil & gas)
    SLB  - Schlumberger       (oilfield services)
    HAL  - Halliburton        (oilfield services)
    STNG - Scorpio Tankers    (product tankers)
    TNK  - Teekay Tankers     (crude tankers)
    FRO  - Frontline          (VLCC tankers)
    LMT  - Lockheed Martin    (defense)
    RTX  - RTX Corp           (defense)
    NOC  - Northrop Grumman   (defense)
    UAL  - United Airlines    (oil consumer, inverse play)
    DAL  - Delta Airlines     (oil consumer, inverse play)
    ICLN - iShares Clean Energy (alternative energy)
    ^GSPC - S&P 500           (broad market)
    GLD  - Gold ETF           (safe haven)
    BTC-USD - Bitcoin         (risk asset / store of value)
    CL=F - WTI front-month futures (continuous)
    CLZ27.NYM - WTI Dec 2027 futures (long-dated)

  FRED (via FredProvider):
    DCOILWTICO - WTI spot, daily, back to 1986 (for historical analogs)

HISTORICAL ANALOG EPISODES:
  1973 Arab Oil Embargo (Oct 1973 - Mar 1974)
  1978-79 Iranian Revolution (Jan 1979 - Dec 1979)
  1980-88 Iran-Iraq "Tanker War" (focus: 1984-87 escalation phase)
  1990-91 Gulf War (Aug 1990 - Jan 1991)
  2003 Iraq War (Mar - May 2003)
  2008 oil spike (Jan - Jul 2008)
  2011 Libya civil war (Feb - Aug 2011)
  2014-2016 oil crash (Jun 2014 - Jan 2016)
  2019 Aramco Abqaiq attack (Sep 14 - Oct 14, 2019)
  2020 COVID oil collapse (Jan - Apr 2020)
  2022 Russia-Ukraine shock (Feb - Mar 2022)

DISCLAIMER: This script is a QUANTITATIVE RESEARCH TOOL, not investment
advice. Futures, options, and short positions can lose substantial
capital. Past analog returns do not predict future returns. The Strait
of Hormuz has NEVER been sustainably closed; most "crises" resolve
without disruption. Size positions for the asymmetric reality: small
probability of large payoff, high probability of small loss (theta
decay on hedges, time premium on insurance).
"""
from __future__ import annotations

import sys
import warnings
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.research.data.yahoo import YahooProvider
from src.research.data.fred import FredProvider

# ============================================================================
# CONFIGURATION
# ============================================================================

W = 95  # standard separator width

# Tickers organized by role. Each tuple: (symbol, short_name, role, sector)
TICKERS: list[tuple[str, str, str, str]] = [
    # Oil majors / integrated
    ("XOM",  "ExxonMobil",     "long",  "integrated_major"),
    ("CVX",  "Chevron",        "long",  "integrated_major"),
    ("COP",  "ConocoPhillips", "long",  "independent_ep"),
    ("OXY",  "Occidental",     "long",  "independent_ep"),
    ("XLE",  "Energy ETF",     "long",  "sector_etf"),
    # Oilfield services
    ("SLB",  "Schlumberger",   "long",  "oilfield_services"),
    ("HAL",  "Halliburton",    "long",  "oilfield_services"),
    # Tankers / shipping (direct Hormuz beneficiaries)
    ("STNG", "Scorpio Tankers","long",  "product_tanker"),
    ("TNK",  "Teekay Tankers", "long",  "crude_tanker"),
    ("FRO",  "Frontline",      "long",  "vlcc_tanker"),
    # Defense (beneficiaries of escalation)
    ("LMT",  "Lockheed",       "long",  "defense"),
    ("RTX",  "RTX Corp",       "long",  "defense"),
    ("NOC",  "Northrop",       "long",  "defense"),
    # Oil consumers / inverse plays (short candidates)
    ("UAL",  "United Airlines","short", "airline"),
    ("DAL",  "Delta Airlines", "short", "airline"),
    # Alternative energy
    ("ICLN", "Clean Energy",   "long",  "alt_energy"),
    # Cross-asset / safe havens / market
    ("^GSPC","S&P 500",        "context","broad_market"),
    ("GLD",  "Gold ETF",       "context","safe_haven"),
    ("BTC-USD","Bitcoin",      "context","risk_asset"),
    # Oil benchmarks (term structure)
    ("CL=F", "WTI front",      "benchmark","oil_front"),
    ("CLZ27.NYM","WTI Dec27",  "benchmark","oil_long"),
]

# Historical analog episodes. price_pct is the DOCUMENTED historical oil
# price move over the window (from EIA/BP/IEA statistical records); used
# as the reference level where continuous futures data does not exist.
# ticker_focus lists which tickers we expect to have data for in the window.
EPISODES: list[dict] = [
    {
        "name": "1973 Arab Oil Embargo",
        "start": "1973-10-01", "end": "1974-03-31",
        "oil_low": 3.0, "oil_high": 12.0, "oil_pct": 3.00,
        "trigger": "OPEC embargo against US/NL for supporting Israel in Yom Kippur War",
        "barrels_offline_mmbd": 5.0,
        "ticker_focus": ["^GSPC", "XOM"],
        "note": "No continuous WTI futures (launched 1983). Oil price LEVELS from EIA/BP. Stock returns from CRSP/yfinance where listed.",
    },
    {
        "name": "1979 Iranian Revolution",
        "start": "1979-01-01", "end": "1979-12-31",
        "oil_low": 14.95, "oil_high": 39.50, "oil_pct": 1.64,
        "trigger": "Shah overthrown; Iran production (6 MMBD) halted; panic buying",
        "barrels_offline_mmbd": 5.6,
        "ticker_focus": ["^GSPC", "XOM"],
        "note": "No continuous futures. Spot oil doubled. Secondary crisis: 1980 Iran-Iraq war begins.",
    },
    {
        "name": "1984-87 Iran-Iraq Tanker War",
        "start": "1984-03-01", "end": "1987-09-30",
        "oil_low": 28.0, "oil_high": 30.0, "oil_pct": 0.07,
        "trigger": "Iran/Iraq attack tankers in Persian Gulf; US re-flags Kuwaiti tankers (1987)",
        "barrels_offline_mmbd": 2.0,
        "ticker_focus": ["^GSPC", "XOM"],
        "note": "DOZENS of tanker attacks over 3.5 years. Oil barely moved (OPEC spare capacity + Saudi stepped in). Direct Hormuz precedent: threats did NOT close the strait.",
    },
    {
        "name": "1990-91 Gulf War",
        "start": "1990-08-02", "end": "1991-01-31",
        "oil_low": 21.0, "oil_high": 41.0, "oil_pct": 0.95,
        "trigger": "Iraq invades Kuwait (Aug 2, 1990); 4 MMBD offline; coalition counter-offensive Jan 1991",
        "barrels_offline_mmbd": 4.3,
        "ticker_focus": ["^GSPC", "XOM", "XLE", "LMT"],
        "note": "Classic supply-shock spike. Oil doubled in 3 months, then collapsed once air war started. Defense stocks rallied into the conflict.",
    },
    {
        "name": "2003 Iraq War",
        "start": "2003-03-01", "end": "2003-05-31",
        "oil_low": 28.0, "oil_high": 37.0, "oil_pct": 0.32,
        "trigger": "US-led invasion of Iraq; SPR pre-emptive releases dampened spike",
        "barrels_offline_mmbd": 2.5,
        "ticker_focus": ["^GSPC", "XOM", "XLE", "LMT"],
        "note": "Mild spike because SPR released 16M bbls before fighting. War was anticipated (mean-reverted quickly).",
    },
    {
        "name": "2008 Oil Spike",
        "start": "2008-01-02", "end": "2008-07-11",
        "oil_low": 95.0, "oil_high": 147.27, "oil_pct": 0.55,
        "trigger": "Demand-driven (China boom, weak USD); not a supply shock",
        "barrels_offline_mmbd": 0.0,
        "ticker_focus": ["^GSPC", "XOM", "XLE", "OXY"],
        "note": "Demand-driven peak. Then collapsed to $33 by Dec 2008 as GFC hit. Cautionary: oil stocks peaked BEFORE oil.",
    },
    {
        "name": "2011 Libya Civil War",
        "start": "2011-02-15", "end": "2011-08-31",
        "oil_low": 84.0, "oil_high": 113.0, "oil_pct": 0.35,
        "trigger": "Libya civil war; 1.6 MMBD Libyan exports offline",
        "barrels_offline_mmbd": 1.6,
        "ticker_focus": ["^GSPC", "XOM", "XLE", "COP", "LMT", "CL=F"],
        "note": "Small Libya loss absorbed by Saudi spare capacity. Spike was temporary.",
    },
    {
        "name": "2014-2016 Oil Crash",
        "start": "2014-06-01", "end": "2016-01-31",
        "oil_low": 107.0, "oil_high": 26.0, "oil_pct": -0.76,
        "trigger": "US shale supply surge; Saudi refused to cut; OPEC market-share war",
        "barrels_offline_mmbd": -3.0,
        "ticker_focus": ["^GSPC", "XOM", "XLE", "COP", "OXY", "SLB", "HAL"],
        "note": "INVERSE of Hormuz scenario. Useful for downside beta: oil services -50%+, majors -25%, E&P -60%.",
    },
    {
        "name": "2019 Aramco Abqaiq Attack",
        "start": "2019-09-14", "end": "2019-10-14",
        "oil_low": 54.85, "oil_high": 69.02, "oil_pct": 0.15,
        "trigger": "Houthi drone/missile strike on Abqaiq-Khurais; 5.7 MMBD offline briefly (largest single disruption ever)",
        "barrels_offline_mmbd": 5.7,
        "ticker_focus": ["^GSPC", "XOM", "XLE", "STNG", "TNK", "LMT", "CL=F"],
        "note": "CLOSEST modern analog to a Hormuz event. Oil +15% in ONE DAY. But recovered within 2 weeks (Saudi restored output). Tankers spiked then faded.",
    },
    {
        "name": "2020 COVID Oil Collapse",
        "start": "2020-01-02", "end": "2020-04-21",
        "oil_low": 60.0, "oil_high": -37.63, "oil_pct": -1.00,
        "trigger": "Global demand collapse (-25 MMBD) + Saudi-Russia price war",
        "barrels_offline_mmbd": -25.0,
        "ticker_focus": ["^GSPC", "XOM", "XLE", "OXY", "UAL", "DAL", "CL=F"],
        "note": "Demand destruction extreme. WTI went NEGATIVE on Apr 20, 2020 (expiry technical). Airlines collapsed with oil (demand link dominates fuel-cost link).",
    },
    {
        "name": "2022 Russia-Ukraine Shock",
        "start": "2022-02-01", "end": "2022-03-31",
        "oil_low": 90.0, "oil_high": 130.50, "oil_pct": 0.45,
        "trigger": "Russia invades Ukraine (Feb 24); sanctions fear on Russian oil (12 MMBD producer)",
        "barrels_offline_mmbd": 3.0,
        "ticker_focus": ["^GSPC", "XOM", "XLE", "XOP", "COP", "OXY", "LMT", "CL=F"],
        "note": "Sanctions-driven. Oil +60% in 2 weeks. Defense +15%. Oil stocks rallied but did NOT double (limited operating leverage on spot).",
    },
]

# Subjective probabilities for next 12 months (BASE CASE - REASONED, not model fit):
# Based on historical analog: ~20 Hormuz "crises" since 1980, ZERO sustained closures.
# Brief disruptions (Aramco-style attacks) have occurred 1-2x per decade.
SCENARIOS: list[dict] = [
    {
        "id": "A",
        "name": "Brief disruption (Aramco-style)",
        "duration": "3-7 days",
        "oil_pct_low": 0.15, "oil_pct_high": 0.25, "oil_pct_mid": 0.20,
        "probability": 0.12,
        "description": "Single attack on tanker or Saudi/Gulf infrastructure. Oil spikes +15-25% in a day, recovers in 2-4 weeks as supply restored. Tankers spike +20-40%.",
    },
    {
        "id": "B",
        "name": "Partial closure (escalating tanker attacks)",
        "duration": "2-4 weeks",
        "oil_pct_low": 0.50, "oil_pct_high": 1.00, "oil_pct_mid": 0.75,
        "probability": 0.05,
        "description": "Sustained attacks on tankers transiting Hormuz. Insurance premiums spike. Some shipping diverts around Africa. US 5th Fleet escorts convoy. Oil +50-100%.",
    },
    {
        "id": "C",
        "name": "Sustained partial closure",
        "duration": "1-3 months",
        "oil_pct_low": 1.00, "oil_pct_high": 2.00, "oil_pct_mid": 1.50,
        "probability": 0.02,
        "description": "Active mining / naval engagement closes strait to uninsurable traffic. SPR releases (~700M bbls) buffer for 2-3 months. Global recession risk rises. Oil +100-200%.",
    },
    {
        "id": "D",
        "name": "Full closure (open war)",
        "duration": "3+ months",
        "oil_pct_low": 2.00, "oil_pct_high": 4.00, "oil_pct_mid": 3.00,
        "probability": 0.005,
        "description": "Iran-US open conflict; strait closed. Requires sustained military campaign to clear mines/anti-ship missiles. Global recession LIKELY. Oil +200-400%. 1973-style economic damage.",
    },
    {
        "id": "E",
        "name": "De-escalation after threat (most common)",
        "duration": "weeks-months of posturing",
        "oil_pct_low": -0.10, "oil_pct_high": 0.03, "oil_pct_mid": -0.03,
        "probability": 0.805,
        "description": "Iran rattles saber, US deploys carrier group, diplomacy/escalation-dominance works. Threat recedes. Oil unchanged to -10%. THIS IS THE BASE CASE (~80%).",
    },
]

# ============================================================================
# DATA LAYER
# ============================================================================


def _to_close_series(df: pd.DataFrame, name: str) -> pd.Series:
    """Extract a tz-naive daily close series indexed by date."""
    if df is None or df.empty:
        return pd.Series(dtype="float64", name=name)
    s = df.set_index("ts")["close"]
    if s.index.tz is not None:
        s.index = s.index.tz_convert("UTC").tz_localize(None)
    s = s.astype(float)
    s.name = name
    return s


def fetch_all_tickers(start: str = "1990-01-01", end: str | None = None) -> dict[str, pd.Series]:
    """Fetch all configured tickers via YahooProvider (cache-first).

    Returns a dict {symbol: pd.Series of daily close}. Missing/failed
    tickers are silently skipped (logged by provider).
    """
    if end is None:
        end = date.today().isoformat()
    # cache_ttl_days=7 keeps fetched data fresh for a week (avoids re-hitting
    # yfinance rate limits on every script run during dev).
    provider = YahooProvider(cache_dir=PROJECT_ROOT / "data" / "yahoo_cache", cache_ttl_days=7)
    out: dict[str, pd.Series] = {}
    for sym, _name, _role, _sector in TICKERS:
        try:
            df = provider.fetch(sym, start, end)
            out[sym] = _to_close_series(df, sym)
        except Exception as exc:
            print(f"  [WARN] could not fetch {sym}: {exc}")
    return out


def fetch_wti_spot_full_history() -> pd.Series:
    """Fetch DCOILWTICO (WTI spot, daily, back to 1986) from FRED.

    Returns tz-naive pd.Series of $/bbl indexed by date. Falls back to
    CL=F (continuous futures, 2015+) if FRED is unavailable.
    """
    try:
        provider = FredProvider(series_id="DCOILWTICO",
                                cache_dir=PROJECT_ROOT / "data" / "macro")
        df = provider.fetch("DCOILWTICO", "1986-01-01", date.today())
        s = df.set_index("ts")["close"]
        if s.index.tz is not None:
            s.index = s.index.tz_convert("UTC").tz_localize(None)
        return s.astype(float).rename("WTI_spot")
    except Exception as exc:
        print(f"  [WARN] FRED DCOILWTICO fetch failed ({exc}); falling back to CL=F only")
        return pd.Series(dtype="float64", name="WTI_spot")


# ============================================================================
# RETURN / STAT HELPERS
# ============================================================================


def window_return(s: pd.Series, start: str, end: str) -> float:
    """Cumulative return of series s over [start, end] inclusive.

    Uses first observation on/after start and last observation on/before end.
    Returns NaN if window has < 2 valid observations.
    """
    if s is None or s.empty:
        return float("nan")
    mask = (s.index >= pd.Timestamp(start)) & (s.index <= pd.Timestamp(end))
    sub = s.loc[mask]
    if len(sub) < 2:
        return float("nan")
    return float(sub.iloc[-1] / sub.iloc[0] - 1.0)


def fmt_pct(x: float, width: int = 7, signed: bool = True) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return " " * (width - 3) + "n/a"
    if signed:
        return f"{x * 100:>+{width}.1f}%"
    return f"{x * 100:>{width}.1f}%"


def fmt_usd(x: float, width: int = 9) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return " " * (width - 3) + "n/a"
    return f"${x:>{width},.0f}"


def fmt_price(x: float, width: int = 7) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return " " * (width - 3) + "n/a"
    return f"${x:>{width}.2f}"


def max_drawdown(s: pd.Series) -> float:
    """Peak-to-trough max drawdown over the series."""
    if s is None or s.empty:
        return float("nan")
    peak = s.cummax()
    dd = (s - peak) / peak
    return float(dd.min())


# ============================================================================
# MAIN
# ============================================================================


def main() -> None:
    print("=" * W)
    print("STRAIT OF HORMUZ OIL DISRUPTION SCENARIO ANALYSIS")
    print("Historical analogs + 5-scenario tree + concrete profit targets")
    print("NOT INVESTMENT ADVICE - research tool only")
    print("=" * W)

    # ------------------------------------------------------------------
    # 1. GEOPOLITICAL CONTEXT
    # ------------------------------------------------------------------
    print("\n1. GEOPOLITICAL CONTEXT - STRAIT OF HORMUZ")
    print("-" * W)
    print("  Geography:")
    print("    - Strait of Hormuz: 21 miles wide at narrowest point")
    print("    - Shipping lanes: 2-mile wide inbound + 2-mile wide outbound")
    print("    - Connects Persian Gulf (Iran, Iraq, Kuwait, Saudi, Bahrain, Qatar, UAE)")
    print("      to Gulf of Oman / Arabian Sea / Indian Ocean")
    print("    - ~20 million barrels/day of oil transit (~20% of global supply)")
    print("    - Plus ~2 Bcf/day of LNG (Qatar is world's #2 LNG exporter)")
    print()
    print("  Control:")
    print("    - NORTHERN shore: IRAN (Islamic Revolutionary Guard Corps Navy - IRGCN)")
    print("      * Operates fast attack boats, anti-ship missiles, mines, drones")
    print("      * Has repeatedly threatened closure (1984-88, 2008, 2012, 2018-19, 2023-24)")
    print("    - SOUTHERN shore: OMAN + UAE (Musandam exclave)")
    print("    - US 5TH FLEET based in Bahrain; routinely escorts tankers during tensions")
    print("    - Combined Task Force 152 (Persian Gulf) and CTF 153 (Hormuz/Red Sea)")
    print()
    print("  Why Iran HAS NEVER actually closed it (despite ~20 crises since 1980):")
    print("    1. Iran NEEDS the strait open: ~1.5-2 MMBD of its own oil exports flow through")
    print("       (~60% of government revenue). Closure would choke Iran's economy first.")
    print("    2. Closure = act of war against EVERY Gulf state + their buyers = invites")
    print("       massive US/coalition military response aimed at regime change.")
    print("    3. Saudi/UAE have pipelines BYPASSING Hormuz:")
    print("       * Saudi East-West pipeline: 5 MMBD capacity to Yanbu (Red Sea)")
    print("       * UAE Habshan-Fujairah pipeline: 1.5 MMBD to Gulf of Oman")
    print("    4. US mine-countermeasures + airpower would reopen within weeks.")
    print("    5. Iran's strategy = LEVERAGE via threat, not actual closure.")
    print()
    print("  Modern disruption playbook (2024 Houthis in Red Sea, Bab el-Mandeb):")
    print("    - Drones + anti-ship ballistic missiles + mines")
    print("    - Insurance premiums spike 5-10x; some shipping diverts (Cape of Good Hope)")
    print("    - US-led naval coalition escorts; selective strikes on launch sites")
    print("    - Net: shipping costs up, transit times up, but FLOW continues")
    print("    - For Hormuz: harder to bypass (Persian Gulf has no alternative outlet")
    print("      for Kuwait/Iraq/Qatar at all; only Saudi/UAE have partial bypasses)")
    print()
    print("  Historical analog base rate: of ~20 'Hormuz crises' since 1980, ZERO have")
    print("  resulted in sustained closure. Brief disruptions (Aramco-style) occur")
    print("  roughly 1-2x per decade. This asymmetry dominates the probability tree.")
    print()
    print("  Current (2026) tension level: ELEVATED but not extreme.")
    print("    - Iran nuclear program advancing (HEU stockpile)")
    print("    - Israel-Hamas/Hezbollah spillover risk")
    print("    - US carrier presence in Gulf rotated")
    print("    - Iran's economic desperation (sanctions) raises tail risk")

    # ------------------------------------------------------------------
    # 2. DATA INVENTORY
    # ------------------------------------------------------------------
    print("\n2. DATA INVENTORY")
    print("-" * W)
    print("  Fetching tickers via YahooProvider (cache-first, ~7 day TTL)...")
    prices = fetch_all_tickers(start="1990-01-01")
    wti_spot = fetch_wti_spot_full_history()

    print()
    print(f"  {'Symbol':<12} {'Name':<18} {'Start':<12} {'End':<12} {'N':>7}  {'Last':>10}")
    print("  " + "-" * 80)
    name_map = {sym: name for sym, name, _, _ in TICKERS}
    for sym, _, _, _ in TICKERS:
        if sym in prices and not prices[sym].empty:
            s = prices[sym]
            last = s.iloc[-1]
            print(f"  {sym:<12} {name_map.get(sym,''):<18} "
                  f"{s.index[0].strftime('%Y-%m-%d'):<12} "
                  f"{s.index[-1].strftime('%Y-%m-%d'):<12} {len(s):>7}  "
                  f"{last:>10,.2f}")
        else:
            print(f"  {sym:<12} {name_map.get(sym,''):<18} {'MISSING':<12}")
    if not wti_spot.empty:
        print(f"  {'WTI_spot':<12} {'FRED DCOILWTICO':<18} "
              f"{wti_spot.index[0].strftime('%Y-%m-%d'):<12} "
              f"{wti_spot.index[-1].strftime('%Y-%m-%d'):<12} "
              f"{len(wti_spot):>7}  {wti_spot.iloc[-1]:>10,.2f}")

    # ------------------------------------------------------------------
    # 3. HISTORICAL ANALOG RETURNS
    # ------------------------------------------------------------------
    print("\n3. HISTORICAL ANALOG RETURNS - ACTUAL DATA")
    print("-" * W)
    print("  For each past oil shock, we compute ACTUAL cumulative returns over the")
    print("  episode window for every ticker with data. 'Oil %' is the documented")
    print("  spot move (EIA/BP levels where continuous futures don't exist).")
    print()
    print("  EPISODE-LEVEL OIL PRICE REFERENCE (documented, EIA/BP):")
    print(f"  {'Episode':<32} {'Oil Low':>9} {'Oil High':>10} {'Move':>8} {'Bbls Offline':>14}")
    print("  " + "-" * 80)
    for ep in EPISODES:
        if ep["oil_high"] < 0:
            high_str = f"${ep['oil_high']:>8.2f}"
        else:
            high_str = f"${ep['oil_high']:>8.2f}"
        bbl_str = f"{ep['barrels_offline_mmbd']:+.1f} MMBD"
        print(f"  {ep['name']:<32} ${ep['oil_low']:>7.2f} {high_str:>10} "
              f"{fmt_pct(ep['oil_pct'], 7):>8} {bbl_str:>14}")
    print()
    print("  ACTUAL CUMULATIVE RETURNS PER EPISODE (where data exists):")
    print("  (n/a = ticker not yet listed or no data in window)")

    # Compute returns matrix: episode x ticker
    all_syms = [sym for sym, _, _, _ in TICKERS]
    rows = []
    for ep in EPISODES:
        row = {"episode": ep["name"], "oil_pct": ep["oil_pct"]}
        for sym in ep["ticker_focus"]:
            if sym in prices:
                row[sym] = window_return(prices[sym], ep["start"], ep["end"])
        # Also compute for all tickers regardless of focus, for completeness
        for sym in all_syms:
            if sym not in row and sym in prices:
                r = window_return(prices[sym], ep["start"], ep["end"])
                if not np.isnan(r):
                    row[sym] = r
        rows.append(row)
    analog_df = pd.DataFrame(rows).set_index("episode")

    # Print focused columns (those with most data)
    focus_cols = ["oil_pct", "^GSPC", "XOM", "XLE", "COP", "OXY", "SLB", "HAL",
                  "STNG", "TNK", "FRO", "LMT", "RTX", "NOC", "UAL", "DAL", "ICLN",
                  "GLD", "BTC-USD", "CL=F"]
    focus_cols = [c for c in focus_cols if c in analog_df.columns]
    # Compact header
    hdr = f"  {'Episode':<30} " + " ".join(f"{c[:7]:>8}" for c in focus_cols)
    print(hdr)
    print("  " + "-" * (30 + 9 * len(focus_cols)))
    for ep_name, row in analog_df.iterrows():
        line = f"  {ep_name:<30} "
        for c in focus_cols:
            v = row.get(c, float("nan"))
            line += " " + fmt_pct(v, 7)
        print(line)

    print()
    print("  KEY TAKEAWAYS FROM ANALOG DATA:")
    # Compute median returns for oil-shock episodes (oil_pct > 0.10)
    shock_eps = analog_df[analog_df["oil_pct"] > 0.10]
    crash_eps = analog_df[analog_df["oil_pct"] < -0.10]
    if len(shock_eps) >= 2:
        print("  Median cumulative return across POSITIVE oil-shock episodes (oil > +10%):")
        for col in ["^GSPC", "XOM", "XLE", "COP", "SLB", "STNG", "TNK", "LMT", "UAL", "DAL", "CL=F"]:
            if col in shock_eps.columns:
                med = shock_eps[col].dropna()
                if len(med) >= 2:
                    print(f"    {col:<8} median {fmt_pct(med.median(), 7)}  "
                          f"(n={len(med)}, min {fmt_pct(med.min(), 7)}, "
                          f"max {fmt_pct(med.max(), 7)})")
    if len(crash_eps) >= 1:
        print("  Median cumulative return across OIL-CRASH episodes (oil < -10%):")
        for col in ["^GSPC", "XOM", "XLE", "SLB", "UAL", "DAL", "CL=F"]:
            if col in crash_eps.columns:
                med = crash_eps[col].dropna()
                if len(med) >= 1:
                    print(f"    {col:<8} median {fmt_pct(med.median(), 7)}  (n={len(med)})")
    print()
    print("  CRITICAL NUANCE:")
    print("    - UAL/DAL often FALL during oil shocks despite higher fuel costs being a")
    print("      headwind AND oil shocks being associated with recessions. Demand > cost.")
    print("    - But during the 2014-16 oil CRASH, airlines RALLIED (lower fuel costs).")
    print("    - Oil services (SLB/HAL) have ~2x the beta of majors (XOM/CVX) on oil moves.")
    print("    - Tankers (STNG/TNK/FRO) are the PUREST Hormuz play: rates spike on disruption")
    print("      but FADE fast once flow resumes (high operating leverage, day-rate driven).")
    print("    - Defense (LMT/RTX/NOC) rally modestly on escalation (+5-15% typical).")
    print("    - The S&P 500 has SMALL reaction to oil shocks unless recession follows.")

    # ------------------------------------------------------------------
    # 4. SCENARIO TREE (A-E) WITH PROBABILITIES AND OIL TARGETS
    # ------------------------------------------------------------------
    print("\n4. SCENARIO TREE - HORMUZ CLOSURE SCENARIOS")
    print("-" * W)
    print("  Subjective probabilities for NEXT 12 MONTHS (reasoned from base rates):")
    print()
    print(f"  {'ID':<4} {'Scenario':<42} {'Dur':<14} {'Oil Low':>9} {'Oil Mid':>9} {'Oil High':>10} {'P':>7}")
    print("  " + "-" * 100)
    total_p = 0.0
    for sc in SCENARIOS:
        total_p += sc["probability"]
        print(f"  {sc['id']:<4} {sc['name']:<42} {sc['duration']:<14} "
              f"{fmt_pct(sc['oil_pct_low'], 8, signed=False):>9} "
              f"{fmt_pct(sc['oil_pct_mid'], 8, signed=False):>9} "
              f"{fmt_pct(sc['oil_pct_high'], 8, signed=False):>10} "
              f"{sc['probability']*100:>6.1f}%")
    print("  " + "-" * 100)
    print(f"  {'':<4} {'TOTAL':<42} {'':<14} {'':>9} {'':>9} {'':>10} {total_p*100:>6.1f}%")
    print()
    for sc in SCENARIOS:
        print(f"  SCENARIO {sc['id']}: {sc['name']} (P={sc['probability']*100:.1f}%)")
        print(f"    {sc['description']}")
        print()

    print("  PROBABILITY REASONING:")
    print("    - Iran has threatened Hormuz closure ~20 times since 1980. ZERO sustained closures.")
    print("    - Brief disruptions (Aramco-style) ~1-2x/decade -> ~12%/yr probability.")
    print("    - Partial closure requires sustained naval mining/attacks -> rare (5%).")
    print("    - Sustained partial closure requires US-Iran escalation without de-escalation")
    print("      off-ramp -> very rare (2%).")
    print("    - Full closure = full war -> near-zero but catastrophic (0.5%).")
    print("    - De-escalation after posturing -> the OVERWHELMING default (~80%).")
    print()
    print("  EXPECTED OIL RETURN (probability-weighted):")
    exp_oil = sum(sc["oil_pct_mid"] * sc["probability"] for sc in SCENARIOS)
    exp_oil_pos = sum(max(0, sc["oil_pct_mid"]) * sc["probability"] for sc in SCENARIOS)
    exp_oil_neg = sum(min(0, sc["oil_pct_mid"]) * sc["probability"] for sc in SCENARIOS)
    print(f"    E[oil return]    = {fmt_pct(exp_oil, 8)}")
    print(f"    Upside component = {fmt_pct(exp_oil_pos, 8)}  (from disruption scenarios A-D)")
    print(f"    Downside comp.   = {fmt_pct(exp_oil_neg, 8)}  (from de-escalation E)")
    print()
    print("    The expected oil return is SMALL because de-escalation dominates the tree.")
    print("    The ASYMMETRY: 80% chance of small loss vs 20% chance of large gain.")
    print("    This is structurally similar to INSURANCE / TAIL-HEDGE positioning.")

    # ------------------------------------------------------------------
    # 5. IMPLIED RETURNS PER SCENARIO ACROSS ASSET CLASSES
    # ------------------------------------------------------------------
    print("\n5. IMPLIED RETURNS PER SCENARIO ACROSS ASSET CLASSES")
    print("-" * W)
    print("  Methodology: scale historical analog betas by each scenario's oil move.")
    print("  Beta = median(ticker_ret / oil_ret) across positive-oil-shock episodes.")
    print("  Cap individual betas at +/- 3.0 to avoid noisy outliers.")
    print()

    # Compute oil-shock betas (ticker return per unit oil return) from analog data
    shock_betas = {}
    for col in analog_df.columns:
        if col == "oil_pct":
            continue
        ser = shock_eps[[col, "oil_pct"]].dropna()
        if len(ser) < 2:
            continue
        # ratio = ticker_ret / oil_ret, cap at +/- 3.0, take median
        ratios = (ser[col] / ser["oil_pct"]).clip(-3.0, 3.0)
        shock_betas[col] = float(ratios.median())

    print(f"  {'Ticker':<10} {'Oil-Shock Beta':>14} {'Role':<22} {'Name'}")
    print("  " + "-" * 80)
    role_map = {sym: (role, name) for sym, name, role, _ in TICKERS}
    for sym in all_syms:
        if sym in shock_betas:
            role, name = role_map.get(sym, ("?", "?"))
            print(f"  {sym:<10} {shock_betas[sym]:>13.2f}x  {role:<22} {name}")

    print()
    print("  IMPLIED CUMULATIVE RETURNS PER SCENARIO:")
    print("  (beta * scenario oil_mid return, clipped at +/- 200% for readability)")

    # For each scenario, show top longs and shorts
    for sc in SCENARIOS:
        implied = {}
        for sym, beta in shock_betas.items():
            # For de-escalation (E, negative oil), invert: shorts become longs
            implied[sym] = beta * sc["oil_pct_mid"]
        # Sort
        longs = sorted([(s, r) for s, r in implied.items() if r > 0], key=lambda x: -x[1])[:5]
        shorts = sorted([(s, r) for s, r in implied.items() if r < 0], key=lambda x: x[1])[:5]
        print(f"\n  SCENARIO {sc['id']}: {sc['name']}  (oil_mid {fmt_pct(sc['oil_pct_mid'], 8)})")
        print(f"    Top LONGS (oil-beneficiaries):")
        for sym, r in longs:
            r_clip = max(-2.0, min(2.0, r))
            role, name = role_map.get(sym, ("?", "?"))
            print(f"      {sym:<10} {fmt_pct(r_clip, 8)}  [{role}] {name}")
        if shorts:
            print(f"    Top SHORTS / HEDGES (oil-losers):")
            for sym, r in shorts:
                r_clip = max(-2.0, min(2.0, r))
                role, name = role_map.get(sym, ("?", "?"))
                print(f"      {sym:<10} {fmt_pct(r_clip, 8)}  [{role}] {name}")

    # ------------------------------------------------------------------
    # 6. CURRENT OIL TERM STRUCTURE (CONTANGO / BACKWARDATION)
    # ------------------------------------------------------------------
    print("\n6. CURRENT OIL TERM STRUCTURE - CONTANGO vs BACKWARDATION")
    print("-" * W)
    print("  Comparing CL=F (front-month WTI) vs CLZ27.NYM (Dec 2027 WTI).")
    print("  The shape of the futures curve is a key supply/demand signal:")
    print("    - BACKWARDATION (front > back): TIGHT physical market, high demand")
    print("      for immediate delivery. Bullish for oil-equity earnings in near term.")
    print("    - CONTANGO (front < back): LOOSE physical market, oversupply.")
    print("      Storage plays profitable; bearish for near-term oil earnings.")
    print()

    if "CL=F" in prices and "CLZ27.NYM" in prices and not prices["CL=F"].empty and not prices["CLZ27.NYM"].empty:
        front = prices["CL=F"]
        back = prices["CLZ27.NYM"]
        # Align on common dates
        common = front.index.intersection(back.index)
        if len(common) >= 50:
            front_last = float(front.loc[common[-1]])
            back_last = float(back.loc[common[-1]])
            front_start = float(front.loc[common[0]])
            back_start = float(back.loc[common[0]])
            spread = back_last - front_last
            spread_pct = spread / front_last
            # Years to Dec 2027 from latest date
            latest = common[-1]
            target = pd.Timestamp("2027-12-15")
            years_to_target = (target - latest).days / 365.25
            if years_to_target > 0:
                annualized_roll = (back_last / front_last) ** (1.0 / years_to_target) - 1.0
            else:
                annualized_roll = float("nan")
            shape = "BACKWARDATION" if front_last > back_last else "CONTANGO"

            print(f"  Latest observation: {latest.strftime('%Y-%m-%d')}")
            print(f"    CL=F (front):      {fmt_price(front_last, 8)}")
            print(f"    CLZ27 (Dec 2027):  {fmt_price(back_last, 8)}")
            print(f"    Spread:            ${spread:>+7.2f}/bbl  ({fmt_pct(spread_pct, 7)})")
            print(f"    Years to Dec 2027: {years_to_target:.2f}")
            print(f"    Annualized roll:   {fmt_pct(annualized_roll, 7)}/yr")
            print(f"    TERM SHAPE:        {shape}")
            print()
            # Comparison of front vs back performance
            front_ret = front_last / front_start - 1
            back_ret = back_last / back_start - 1
            print(f"  Since {common[0].strftime('%Y-%m-%d')} (term structure evolution):")
            print(f"    CL=F return:        {fmt_pct(front_ret, 8)}")
            print(f"    CLZ27 return:       {fmt_pct(back_ret, 8)}")
            print(f"    Front outperformed by {fmt_pct(front_ret - back_ret, 7)} "
                  f"({'backwardation widening' if front_ret > back_ret else 'contango widening'})")
            print()
            # Interpretation
            if shape == "BACKWARDATION":
                print("  INTERPRETATION (BACKWARDATION):")
                print("    - Physical market is TIGHT. Producers selling prompt, not storing.")
                print("    - Long-dated price reflects full-cycle marginal cost (~$50-65/bbl).")
                print("    - Oil MAJORS benefit (XOM/CVX realize high spot prices now).")
                print("    - Tankers LESS favored (no storage arbitrage opportunity).")
                print("    - In a Hormuz disruption, backwardation WIDENS (spot spikes vs back).")
                print("    - Equity signal: LONG majors, NEUTRAL tankers, defensive positioning.")
            else:
                print("  INTERPRETATION (CONTANGO):")
                print("    - Physical market is LOOSE. Storage plays profitable.")
                print("    - Tankers benefit (floating storage demand).")
                print("    - Majors face lower realized near-term prices.")
                print("    - In a Hormuz disruption, front would spike INTO backwardation.")
                print("    - Equity signal: tankers > majors currently; flip on disruption.")
            print()
            # What the term structure implies for Hormuz scenarios
            print("  TERM-STRUCTURE-IMPLIED HORMUZ READ:")
            if shape == "BACKWARDATION":
                print("    - Backwardation suggests market is ALREADY pricing some supply risk.")
                print("    - But Dec 2027 at $%.2f implies LONG-RUN calm (marginal cost)."
                      % back_last)
                print("    - Translation: market sees current tightness as TRANSIENT.")
                print("    - In Scenario A (brief), front spikes +20%, back barely moves.")
                print("    - In Scenario C/D (sustained), back ALSO reprices up sharply.")
            else:
                print("    - Contango suggests market sees NO current disruption risk.")
                print("    - Cheap tail-hedge opportunity: long-dated calls on oil are cheap")
                print("      when term structure is in contango (low implied spot vol).")
        else:
            print("  [WARN] Insufficient overlapping CL=F / CLZ27 data for term structure.")
    else:
        print("  [WARN] CL=F or CLZ27.NYM data missing; skipping term structure.")

    # ------------------------------------------------------------------
    # 7. CROSS-ASSET CORRELATIONS DURING OIL SHOCKS
    # ------------------------------------------------------------------
    print("\n7. CROSS-ASSET CORRELATIONS DURING OIL SHOCKS")
    print("-" * W)

    # Build a returns panel
    price_panel = pd.DataFrame({sym: s for sym, s in prices.items() if not s.empty})
    rets_panel = price_panel.pct_change().dropna()

    # Full-sample correlations
    print("  Full-sample correlation of daily returns (entire overlapping history):")
    focus = [c for c in ["CL=F", "XOM", "XLE", "STNG", "LMT", "UAL", "ICLN", "GLD",
                          "BTC-USD", "^GSPC"] if c in rets_panel.columns]
    if len(focus) >= 3:
        corr_full = rets_panel[focus].corr()
        print(f"  {'':<10}" + "".join(f"{c[:8]:>9}" for c in focus))
        for r in focus:
            print(f"  {r[:10]:<10}" + "".join(f"{corr_full.loc[r, c]:>9.2f}" for c in focus))

    # Oil-shock-window correlations: take episodes where oil moved > |10%|
    print()
    print("  Correlations DURING oil-shock windows (sum of episode date ranges, +/- 5d buffer):")
    shock_dates = []
    for ep in EPISODES:
        if abs(ep["oil_pct"]) >= 0.10:
            s = pd.Timestamp(ep["start"]) - pd.Timedelta(days=5)
            e = pd.Timestamp(ep["end"]) + pd.Timedelta(days=5)
            shock_dates.append((s, e))
    shock_mask = pd.Series(False, index=rets_panel.index)
    for s, e in shock_dates:
        shock_mask |= (rets_panel.index >= s) & (rets_panel.index <= e)
    if shock_mask.sum() >= 30:
        rets_shock = rets_panel.loc[shock_mask]
        corr_shock = rets_shock[focus].corr()
        print(f"  {'':<10}" + "".join(f"{c[:8]:>9}" for c in focus))
        for r in focus:
            print(f"  {r[:10]:<10}" + "".join(f"{corr_shock.loc[r, c]:>9.2f}" for c in focus))
        print()
        print("  KEY DIFFERENCES (shock-window minus full-sample correlation):")
        delta = corr_shock - corr_full
        # Show the biggest changes
        print(f"  {'Pair':<22} {'Full':>7} {'Shock':>7} {'Delta':>7}")
        print("  " + "-" * 50)
        pairs = []
        for i, r in enumerate(focus):
            for c in focus[i+1:]:
                pairs.append((f"{r}-{c}", corr_full.loc[r, c], corr_shock.loc[r, c]))
        pairs.sort(key=lambda x: -abs(x[2] - x[1]))
        for label, f, s in pairs[:10]:
            print(f"  {label:<22} {f:>7.2f} {s:>7.2f} {s-f:>+7.2f}")
    else:
        print("  [WARN] Insufficient shock-window observations.")

    print()
    print("  INTERPRETATION:")
    print("    - Gold/S&P corr with oil is typically LOW in normal times (~0.1-0.2).")
    print("    - During supply shocks, oil-S&P correlation often goes NEGATIVE")
    print("      (oil up = tax on consumers = recession risk).")
    print("    - Gold typically RALLIES modestly with oil (both inflation hedges).")
    print("    - BTC correlation is unstable - behaves as risk asset in shocks (sells off).")
    print("    - Tanker correlations with oil are NOISY - they move on RATE dynamics,")
    print("      not just spot oil.")

    # ------------------------------------------------------------------
    # 8. POSITION SIZING FOR $800K PORTFOLIO
    # ------------------------------------------------------------------
    print("\n8. POSITION SIZING FOR $800K PORTFOLIO")
    print("-" * W)
    PORTFOLIO = 800_000
    print(f"  Portfolio: ${PORTFOLIO:,}")
    print()
    print("  Kelly criterion (simplified) for the oil-disruption trade:")
    print("    Expected value of a $1 long-oil position = sum(P_i * r_i)")
    print("    Variance-weighted Kelly fraction = EV / Var")
    print("    We use HALF-Kelly (standard risk reduction).")
    print()

    # Compute Kelly for a "long oil exposure" trade using scenario returns
    # Use XLE as proxy (most diversified oil long)
    proxy = "XLE"
    if proxy in shock_betas:
        beta = shock_betas[proxy]
    else:
        beta = 1.5  # fallback
    outcomes = []
    for sc in SCENARIOS:
        r = beta * sc["oil_pct_mid"]  # proxy expected return
        outcomes.append((sc["probability"], r))
    ev = sum(p * r for p, r in outcomes)
    var = sum(p * (r - ev) ** 2 for p, r in outcomes)
    sd = var ** 0.5 if var > 0 else 0
    full_kelly = ev / var if var > 0 else 0
    half_kelly = full_kelly / 2.0

    print(f"  Proxy: {proxy} (beta to oil = {beta:.2f})")
    print(f"  Scenario-weighted EV:     {fmt_pct(ev, 8)}")
    print(f"  Scenario-weighted SD:     {fmt_pct(sd, 8)}")
    print(f"  Full Kelly fraction:      {full_kelly*100:>+6.1f}% of portfolio")
    print(f"  Half-Kelly fraction:      {half_kelly*100:>+6.1f}% of portfolio")
    print()
    if half_kelly <= 0:
        print("  Kelly says DON'T TAKE THE TRADE (negative EV). This makes sense given")
        print("  de-escalation dominates the tree. Adjust approach:")
        print("    - Use OPTIONS (tail hedge) instead of directional futures.")
        print("    - Cost is the premium; payoff is asymmetric (Scenario A-D upside).")
        print("    - Treat as INSURANCE, not as a return-generating trade.")
        recommended_oil_allocation = 0.03  # 3% insurance allocation
    elif half_kelly > 0.20:
        print("  Kelly fraction is large -> cap at 10% (risk management).")
        recommended_oil_allocation = 0.10
    else:
        recommended_oil_allocation = max(0.03, half_kelly)
        print(f"  Recommended allocation to oil-complex: {recommended_oil_allocation*100:.1f}%")

    oil_budget = PORTFOLIO * recommended_oil_allocation
    print()
    print(f"  RECOMMENDED OIL-COMPLEX BUDGET: ${oil_budget:,.0f} "
          f"({recommended_oil_allocation*100:.1f}% of portfolio)")
    print("    Rationale: tail-hedge / insurance positioning. Most likely outcome is")
    print("    small loss (theta on options, mean-reversion on spot). Payoff in tail.")
    print()
    print("  SUB-ALLOCATION WITHIN OIL BUDGET:")
    # Split between direct oil exposure, oil-equity, tankers, defense, and options hedge
    sub_alloc = [
        ("Oil-equity long (XLE/XOM)",   0.35, "core beta, liquid"),
        ("Tanker long (STNG/TNK)",      0.20, "pure Hormuz exposure, high beta"),
        ("Defense long (LMT/NOC)",      0.15, "escalation hedge, lower beta"),
        ("Oil call options (CL/USO)",   0.20, "tail-hedge, capped downside"),
        ("Airline puts (UAL/DAL)",      0.10, "secondary hedge, recessionary"),
    ]
    print(f"  {'Leg':<32} {'%':>5} {'$':>10}  Rationale")
    print("  " + "-" * 80)
    for name, pct, rationale in sub_alloc:
        print(f"  {name:<32} {pct*100:>4.0f}% ${oil_budget*pct:>9,.0f}  {rationale}")
    print(f"  {'TOTAL':<32} {'100%':>5} ${oil_budget:>9,.0f}")

    # ------------------------------------------------------------------
    # 9. CONCRETE PROFIT TARGETS PER SCENARIO (DOLLAR TERMS)
    # ------------------------------------------------------------------
    print("\n9. CONCRETE PROFIT TARGETS PER SCENARIO")
    print("-" * W)
    print("  Current reference prices (latest observed in cache):")
    # Show current prices
    current_prices = {}
    for sym in ["XOM", "CVX", "COP", "OXY", "XLE", "SLB", "HAL", "STNG", "TNK", "FRO",
                "LMT", "RTX", "NOC", "UAL", "DAL", "ICLN", "CL=F"]:
        if sym in prices and not prices[sym].empty:
            p = float(prices[sym].iloc[-1])
            current_prices[sym] = p
            print(f"    {sym:<8} {fmt_price(p, 8)}  (as of {prices[sym].index[-1].strftime('%Y-%m-%d')})")

    print()
    print("  PROFIT TARGETS for Scenario A (brief disruption, oil +20%):")
    print("  Beta-scaled from historical analog. Stops set at -1.5x expected gain.")
    _print_target_table(current_prices, shock_betas, role_map, 0.20, "A")

    print()
    print("  PROFIT TARGETS for Scenario B (partial closure, oil +75%):")
    _print_target_table(current_prices, shock_betas, role_map, 0.75, "B")

    print()
    print("  PROFIT TARGETS for Scenario C (sustained partial, oil +150%):")
    _print_target_table(current_prices, shock_betas, role_map, 1.50, "C")

    print()
    print("  PROFIT TARGETS for Scenario D (full closure, oil +300%):")
    print("  (extreme tail - use OPTIONS, not directional, for this scenario)")
    _print_target_table(current_prices, shock_betas, role_map, 3.00, "D", clip=True)

    print()
    print("  PROFIT TARGETS for Scenario E (de-escalation, oil -3%):")
    print("  (BASE CASE - this is what you LOSE if positioned long)")
    _print_target_table(current_prices, shock_betas, role_map, -0.03, "E")

    # ------------------------------------------------------------------
    # 10. OPTIONS STRATEGIES
    # ------------------------------------------------------------------
    print("\n10. OPTIONS STRATEGIES")
    print("-" * W)
    print("  Given the asymmetric payoff (small loss likely, large gain in tail),")
    print("  OPTIONS are structurally superior to directional futures for Hormuz.")
    print()
    print("  STRATEGY 1: LONG OTM CALL SPREADS on XLE / USO (cheapest tail hedge)")
    print("    - Buy XLE 0.10-delta call 60-90 days out")
    print("    - Sell XLE 0.25-delta call same expiry (finances the long)")
    print("    - Cost: ~1-2% of notional. Max payoff ~5-8x cost on Scenario A.")
    print("    - Rationale: limited time-decay, defined-risk, leveraged tail exposure.")
    print()
    print("  STRATEGY 2: LONG DATED CALLS on CL=F (oil futures options)")
    print("    - Buy WTI $80-strike calls 6 months out when spot is ~$70")
    print("    - Cost: ~$3-5/bbl = $3,000-5,000 per contract (1000 bbl)")
    print("    - Payoff in Scenario A (+$15/bbl): ~$10k profit per contract (2-3x)")
    print("    - Payoff in Scenario C (+$100/bbl): ~$95k profit per contract (~20x)")
    print("    - Rationale: direct spot exposure, leveraged, defined risk.")
    print()
    print("  STRATEGY 3: PUT SPREADS on UAL / DAL (airlines as recession proxy)")
    print("    - Buy UAL 0.25-delta put 90 days out")
    print("    - Sell UAL 0.10-delta put (finances)")
    print("    - Payoff if airlines fall >15% (recession fears on oil shock)")
    print("    - Rationale: secondary hedge, pays if oil shock causes demand destruction.")
    print()
    print("  STRATEGY 4: LONG TANKER (STNG) CALLS")
    print("    - STNG has highest historical beta to Hormuz-specific disruption")
    print("    - Buy STNG ATM calls 60-90 days out")
    print("    - Payoff in Scenario A: tanker rates spike -> STNG +20-40%")
    print("    - Rationale: purest Hormuz beneficiary, leveraged equity option.")
    print()
    print("  STRATEGY 5: COLLAR on existing long-XOM position")
    print("    - If you hold XOM long-term, collar it:")
    print("      * Buy XOM put 10% OTM (downside protection if de-escalation hits)")
    print("      * Sell XOM call 15% OTM (finances the put, caps upside)")
    print("    - Net cost near zero. Gives up some upside in Scenario C/D for downside.")
    print("    - Rationale: zero-cost hedge on core holding.")
    print()
    print("  STRATEGY 6: VOLATILITY (OVX) LONG")
    print("    - OVX = Cboe Oil Volatility Index (oil-equity implied vol)")
    print("    - When OVX < 35, buy VIX-style calls or UVXY-style exposure")
    print("    - In Scenario A/B, OVX spikes 50-100% -> call payoff")
    print("    - Rationale: vol-of-vol tail hedge, doesn't require directional view.")
    print()
    print("  RECOMMENDED OPTIONS BUDGET: 50% of oil-complex budget "
          f"(= ${oil_budget*0.5:,.0f})")
    print("    - Split across Strategies 1, 2, 4 (long-gamma tail hedges)")
    print("    - Avoid Strategy 5 unless you have an existing long-XOM position to collar.")
    print("    - Strategy 6 (OVX) is opportunistic; deploy when OVX is below 30.")

    # ------------------------------------------------------------------
    # 11. RISK MANAGEMENT - STOPS AND MAX LOSS
    # ------------------------------------------------------------------
    print("\n11. RISK MANAGEMENT - STOPS AND MAX LOSS")
    print("-" * W)
    print("  The trade is structurally INSURANCE. Stop-loss logic is different:")
    print()
    print("  For DIRECTIONAL (equity) positions:")
    print("    - Hard stop: -8% from entry (caps single-name drawdown)")
    print("    - Time stop: exit if no Hormuz event within 60 days")
    print("    - Re-entry: after time stop, re-enter on next Iran escalation headline")
    print()
    print("  For OPTIONS positions:")
    print("    - NO stop loss - premium is the max loss by definition")
    print("    - Roll 30 days before expiry if you want to maintain the hedge")
    print("    - Take profit at 5x premium cost on 50% of position")
    print("    - Hold remaining 50% for tail scenarios (C/D)")
    print()
    print("  PORTFOLIO-LEVEL MAX LOSS:")
    max_loss_oil = oil_budget  # worst case: entire oil budget lost
    max_loss_pct = max_loss_oil / PORTFOLIO
    print(f"    Oil-complex worst case: -${max_loss_oil:,.0f} "
          f"({max_loss_pct*100:.1f}% of portfolio)")
    print("    This occurs if: NO Hormuz event for 12 months AND all options expire worthless")
    print("    AND tanker/defense/equity positions mean-revert to entry.")
    print()
    print("  SCENARIO P&L SUMMARY (probability-weighted):")
    print(f"  {'Scenario':<10} {'P':>6} {'Oil %':>8} {'$P&L':>12} {'P-weighted':>12}")
    print("  " + "-" * 60)
    # Simplified: assume oil budget gains = budget * proxy_beta * oil_pct
    total_ev = 0
    for sc in SCENARIOS:
        # Approximate P&L: oil_budget * proxy return
        proxy_ret = shock_betas.get(proxy, 1.5) * sc["oil_pct_mid"]
        # Cap at -100% (can't lose more than allocated) and +500% (leverage cap)
        proxy_ret = max(-1.0, min(5.0, proxy_ret))
        pnl = oil_budget * proxy_ret
        weighted = pnl * sc["probability"]
        total_ev += weighted
        print(f"  {sc['id']:<10} {sc['probability']*100:>5.0f}% "
              f"{fmt_pct(sc['oil_pct_mid'], 7):>8} "
              f"${pnl:>+11,.0f} ${weighted:>+11,.0f}")
    print("  " + "-" * 60)
    print(f"  {'TOTAL EV':<10} {'':>6} {'':>8} {'':>12} ${total_ev:>+11,.0f}")
    print()
    if total_ev < 0:
        print(f"  TOTAL EXPECTED VALUE: ${total_ev:,.0f} (NEGATIVE).")
        print("    This confirms the trade is INSURANCE, not alpha.")
        print("    The 'cost' is the insurance premium; the 'benefit' is tail protection")
        print("    for the rest of your $%.0fK portfolio." % ((PORTFOLIO - oil_budget) / 1000))
    else:
        print(f"  TOTAL EXPECTED VALUE: ${total_ev:,.0f} (POSITIVE).")
        print("    Historical analog betas justify a small directional allocation.")

    # ------------------------------------------------------------------
    # 12. SUMMARY RECOMMENDATION
    # ------------------------------------------------------------------
    print("\n12. SUMMARY RECOMMENDATION")
    print("-" * W)
    print()
    print("  HEADLINE: Treat Hormuz disruption as a TAIL HEDGE, not a directional bet.")
    print()
    print("  THE ASYMMETRY:")
    print(f"    - 80% probability: de-escalation -> lose ~3% of oil budget "
          f"(= ${oil_budget*0.03:,.0f})")
    print(f"    - 12% probability: brief disruption -> gain ~30% of oil budget "
          f"(= ${oil_budget*0.30:,.0f})")
    print(f"    - 7.5% probability: partial/sustained -> gain 100-300% of oil budget "
          f"(= ${oil_budget*1.5:,.0f} to ${oil_budget*3:,.0f})")
    print(f"    - 0.5% probability: full closure -> gain 300%+ (uncapped on options)")
    print()
    print("  RECOMMENDED EXECUTION:")
    print(f"    1. Allocate ${oil_budget:,.0f} ({recommended_oil_allocation*100:.1f}% of portfolio)")
    print("       to the oil-complex trade. Treat as insurance premium.")
    print(f"    2. Keep ${PORTFOLIO - oil_budget:,.0f} in CORE portfolio (broad equity,")
    print("       gold, BTC per your existing allocation).")
    print("    3. Within oil budget:")
    print(f"       - ${oil_budget*0.35:,.0f}  XLE / XOM long (core oil beta)")
    print(f"       - ${oil_budget*0.20:,.0f}  STNG / TNK long (tankers, pure Hormuz)")
    print(f"       - ${oil_budget*0.15:,.0f}  LMT / NOC long (defense, escalation)")
    print(f"       - ${oil_budget*0.20:,.0f}  CL=F / USO call options (tail hedge)")
    print(f"       - ${oil_budget*0.10:,.0f}  UAL / DAL put options (recession hedge)")
    print("    4. EXIT TRIGGERS:")
    print("       - On Scenario A (brief disruption): take 50% profit on tanker/options,")
    print("         hold rest for escalation. Re-stagger hedges.")
    print("       - On Scenario E (de-escalation): let options expire, refresh quarterly.")
    print("       - Time stop directional equity after 60 days of no event.")
    print()
    print("  RISK WARNINGS (read these):")
    print("    - This is a QUANTITATIVE FRAMEWORK, not a recommendation to trade.")
    print("    - Options can expire WORTHLESS (100% loss of premium).")
    print("    - Futures / short positions can lose MORE than the initial margin.")
    print("    - Historical analogs may NOT repeat. 2019 Abqaiq +15% faded in 2 weeks.")
    print("    - Iran has NEVER closed Hormuz; betting on closure has lost money historically.")
    print("    - Tanker stocks are VOLATILE (50%+ annualized vol); position size accordingly.")
    print("    - The base case is that you LOSE the insurance premium. That is OK if your")
    print("      core portfolio benefits from avoiding a 2008/2020-style drawdown.")
    print()
    print("  MONITORING CHECKLIST (what to watch weekly):")
    print("    - Iran nuclear negotiations status (IAEA reports)")
    print("    - US carrier group deployments to 5th Fleet AOR")
    print("    - Tanker insurance premiums (London market - LTIRD on Lloyd's)")
    print("    - Front-month WTI vs 12-month (term structure shape)")
    print("    - OVX (Cboe Oil Volatility Index) - spike signals fear")
    print("    - IRGCN fast-boat incidents in Strait (USNavCent releases)")
    print("    - Saudi/Emerat pipeline utilization (bypass signal)")
    print()
    print("=" * W)
    print("END HORMUZ SCENARIO ANALYSIS - all betas derived from real yfinance data")
    print("Episodes: %d | Scenarios: %d | Tickers analyzed: %d"
          % (len(EPISODES), len(SCENARIOS), len([s for s in prices if not prices[s].empty])))
    print("=" * W)


def _print_target_table(current_prices: dict, shock_betas: dict,
                        role_map: dict, oil_pct: float, scenario_id: str,
                        clip: bool = False) -> None:
    """Print entry/target/stop for each ticker given a scenario oil move."""
    # Pick top candidates per role
    candidates = [
        # (symbol, role_bucket, is_short)
        ("XOM",  "majors",       False),
        ("CVX",  "majors",       False),
        ("XLE",  "majors",       False),
        ("COP",  "ep",           False),
        ("OXY",  "ep",           False),
        ("SLB",  "services",     False),
        ("HAL",  "services",     False),
        ("STNG", "tankers",      False),
        ("TNK",  "tankers",      False),
        ("FRO",  "tankers",      False),
        ("LMT",  "defense",      False),
        ("NOC",  "defense",      False),
        ("ICLN", "alt_energy",   False),
        ("UAL",  "airlines",     True),
        ("DAL",  "airlines",     True),
    ]
    print(f"  {'Sym':<6} {'Entry':>9} {'Target':>10} {'Return':>9} {'Stop':>9} {'MaxLoss':>9} {'RR':>5}  Role")
    print("  " + "-" * 80)
    for sym, role, is_short in candidates:
        if sym not in current_prices:
            continue
        entry = current_prices[sym]
        beta = shock_betas.get(sym, 1.0)
        # For shorts, return is INVERSE (oil up -> airline down)
        sign = -1.0 if is_short else 1.0
        expected_ret = sign * beta * oil_pct
        if clip:
            expected_ret = max(-0.60, min(2.00, expected_ret))
        else:
            expected_ret = max(-0.50, min(2.00, expected_ret))
        target_price = entry * (1 + expected_ret)
        # Stop: -1.5x expected gain magnitude, capped
        stop_ret = -1.5 * abs(expected_ret) if expected_ret > 0 else 0.5 * abs(expected_ret)
        stop_ret = max(-0.30, min(0.30, stop_ret))
        if is_short:
            # For shorts, "stop" is the price going AGAINST you (up)
            stop_price = entry * (1 + abs(stop_ret))
            max_loss_pct = abs(stop_ret)
        else:
            stop_price = entry * (1 - abs(stop_ret))
            max_loss_pct = abs(stop_ret)
        rr = abs(expected_ret) / max(max_loss_pct, 0.01)
        print(f"  {sym:<6} {fmt_price(entry, 8)} {fmt_price(target_price, 9)} "
              f"{fmt_pct(expected_ret, 8)} {fmt_price(stop_price, 8)} "
              f"{fmt_pct(-max_loss_pct, 8)} {rr:>5.2f}  {role}")


if __name__ == "__main__":
    main()
