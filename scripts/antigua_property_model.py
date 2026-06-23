"""
Antigua Guatemala Property Investment Model
============================================

Models property investment in ANTIGUA GUATEMALA - the colonial UNESCO World
Heritage city in Guatemala (NOT the Caribbean island nation of Antigua and
Barbuda). Population ~45K (city) / ~85K (municipality). Founded 1543.

HONEST DATA FRAMING (read this first):
  Guatemala has LIMITED public market data. There is:
    - NO Case-Shiller-style housing index for Antigua (or all of Guatemala)
    - NO tradable Guatemala-only equity ETF (GTAAA was delisted)
    - NO residential REIT market to mark property values
    - NO high-frequency (monthly/quarterly) macro series on FRED
  What DOES exist:
    - FRED: 375 ANNUAL Guatemala series (GDP, CPI, FX, reserves) - all annual
    - World Bank: 1990-2024 annual macro (GDP/cap, FDI, tourism, urbanization)
    - Yahoo: ILF (iShares Latin America 40 ETF) as regional proxy
    - Qualitative: broker listings, expat blogs, INGUAT tourism stats
  This script is EXPLICIT about what is measured vs assumed.

OUTPUT STRUCTURE (mirrors bay_area_risk_v3.py where data allows; sections
marked QUALITATIVE have no underlying time series):
  1.  Data inventory + discovery (FRED search, WB indicators, Yahoo proxy)
  2.  Guatemala macro profile (real data: GDP, inflation, FX, FDI, tourism)
  3.  Currency risk: GTQ vs USD (real FRED + WB exchange-rate history)
  4.  Latin America proxy: ILF returns, vol, drawdowns
  5.  Cross-asset correlations: ILF vs SPY, GLD, BTC, US housing
  6.  Regime-conditioned ILF returns (global macro regimes)
  7.  Rental yield arbitrage: Antigua 6-10% vs Bay Area 3-4% vs HK 2-3%
  8.  Colonial city benchmarking (San Miguel de Allende, Cusco, Cartagena)
  9.  Guatemala-specific risk analysis (political, corruption, disasters)
  10. Crisis stress test: ILF drawdowns + Honduras 2009 / Argentina analogs
  11. $400K-$800K deployment scenarios for Antigua property
  12. Risk-adjusted comparison: Antigua vs Bay Area v3 vs HK
  13. Honest recommendation

DATA SOURCES (all cached under data/macro/ or data/yahoo_cache/):
  FRED (annual Guatemala series, fetched directly via series/observations):
    FXRATEGTA618NUPN  Exchange Rate to USD for Guatemala (GTQ per USD)
    FPCPITOTLZGGTM    Inflation, consumer prices for Guatemala (annual %)
    PCAGDPGTA646NWDB  GDP per capita for Guatemala (current US$)
  World Bank (country=GT, cached as wb_gt_<code>.parquet under data/macro/):
    NY.GDP.PCAP.CD      GDP per capita (current US$)
    NY.GDP.MKTP.CD      GDP (current US$)
    NY.GDP.PCAP.KD.ZG   GDP per capita growth (annual %)
    SP.URB.TOTL.IN.ZS   Urban population (% of total)
    ST.INT.ARVL         International tourism arrivals
    ST.INT.RCPT.CD      International tourism receipts (US$)
    BX.KLT.DINV.CD.WD   FDI net inflows (US$)
    BX.KLT.DINV.WD.GD.ZS  FDI net inflows (% of GDP)
    FP.CPI.TOTL.ZG      Inflation, consumer prices (annual %)
    PA.NUS.FCRF         Official exchange rate (LCU per US$)
    FR.INR.RINR         Real interest rate (%)
    SI.POV.GINI         GINI index
    SP.POP.TOTL         Population, total
  Yahoo:
    ILF   iShares Latin America 40 ETF (regional proxy)
"""
from __future__ import annotations

import sys
import warnings
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import requests

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.research.data.fred import FredProvider
from src.research.macro.regimes import RulesBasedClassifier

# ============================================================================
# PATHS
# ============================================================================

DATA_DIR = PROJECT_ROOT / "data"
MACRO_DIR = DATA_DIR / "macro"
YAHOO_DIR = DATA_DIR / "yahoo_cache"
RESEARCH_DIR = DATA_DIR / "research"
for _d in (MACRO_DIR, YAHOO_DIR, RESEARCH_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# Guatemala FRED series (all ANNUAL - the spec's 5 candidate IDs were all
# nonexistent 400s; these are the real ones found via series/search).
GT_FRED_SERIES = {
    "FXRATEGTA618NUPN": "Exchange Rate to USD for Guatemala (GTQ per USD)",
    "FPCPITOTLZGGTM":   "Inflation, consumer prices for Guatemala (annual %)",
    "PCAGDPGTA646NWDB": "GDP per capita for Guatemala (current US$)",
}

# World Bank indicators for Guatemala (country=GT).
GT_WB_INDICATORS = {
    "NY.GDP.PCAP.CD":      "GDP per capita (current US$)",
    "NY.GDP.MKTP.CD":      "GDP (current US$)",
    "NY.GDP.PCAP.KD.ZG":   "GDP per capita growth (annual %)",
    "SP.URB.TOTL.IN.ZS":   "Urban population (% of total)",
    "ST.INT.ARVL":         "International tourism, number of arrivals",
    "ST.INT.RCPT.CD":      "International tourism receipts (current US$)",
    "BX.KLT.DINV.CD.WD":   "Foreign direct investment, net inflows (US$)",
    "BX.KLT.DINV.WD.GD.ZS":"FDI net inflows (% of GDP)",
    "FP.CPI.TOTL.ZG":      "Inflation, consumer prices (annual %)",
    "PA.NUS.FCRF":         "Official exchange rate (LCU per US$)",
    "FR.INR.RINR":         "Real interest rate (%)",
    "SI.POV.GINI":         "GINI index (0=equal, 100=unequal)",
    "SP.POP.TOTL":         "Population, total",
}

FETCH_END = date(2025, 6, 1)


# ============================================================================
# DATA FETCH + CACHE LAYER
# ============================================================================


def _strip_tz(s: pd.Series) -> pd.Series:
    if getattr(s.index, "tz", None) is not None:
        s = s.tz_convert("UTC").tz_localize(None)
    return s


def fetch_fred_gt_series(series_id: str, api_key: str) -> pd.DataFrame:
    """Fetch a Guatemala FRED series via series/observations, Metis-contract shape.

    Uses requests directly (bypasses FredProvider.SUPPORTED_SERIES whitelist
    which only covers US series). Caches at data/macro/<id>.parquet.
    """
    cache_path = MACRO_DIR / f"{series_id}.parquet"
    if cache_path.exists():
        df = pd.read_parquet(cache_path)
        if not df.empty:
            return df

    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": "1990-01-01",
        "observation_end": FETCH_END.isoformat(),
    }
    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    obs = r.json().get("observations", [])
    rows = []
    for o in obs:
        v = o["value"]
        if v == ".":
            continue
        try:
            rows.append((o["date"], float(v)))
        except ValueError:
            continue
    if not rows:
        return pd.DataFrame(columns=["ts", "close", "source"])
    df = pd.DataFrame(rows, columns=["date", "value"])
    df["ts"] = pd.to_datetime(df["date"])
    df = df.drop(columns="date").sort_values("ts").reset_index(drop=True)
    df["close"] = df["value"]
    df["source"] = f"fred:{series_id}"
    df = df[["ts", "close", "source"]]
    df.to_parquet(cache_path, index=False)
    return df


def fetch_worldbank_gt(indicator: str) -> pd.DataFrame:
    """Fetch a World Bank indicator for Guatemala (country=GT).

    Caches at data/macro/wb_gt_<sanitized_code>.parquet. Returns a DataFrame
    with columns [ts (year-start), close, source].
    """
    safe = indicator.replace(".", "_")
    cache_path = MACRO_DIR / f"wb_gt_{safe}.parquet"
    if cache_path.exists():
        df = pd.read_parquet(cache_path)
        if not df.empty:
            return df

    url = f"https://api.worldbank.org/v2/country/GT/indicator/{indicator}"
    params = {"format": "json", "per_page": 1000, "date": "1990:2025"}
    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    data = r.json()
    if len(data) < 2 or not data[1]:
        return pd.DataFrame(columns=["ts", "close", "source"])
    rows = []
    for rec in data[1]:
        v = rec.get("value")
        if v is None:
            continue
        try:
            rows.append((rec["date"], float(v)))
        except (TypeError, ValueError):
            continue
    if not rows:
        return pd.DataFrame(columns=["ts", "close", "source"])
    df = pd.DataFrame(rows, columns=["year", "value"])
    df["ts"] = pd.to_datetime(df["year"].astype(str) + "-01-01")
    df = df.sort_values("ts").reset_index(drop=True)
    df["close"] = df["value"]
    df["source"] = f"wb:{indicator}"
    df = df[["ts", "close", "source"]]
    df.to_parquet(cache_path, index=False)
    return df


def fetch_yahoo_proxy(ticker: str, start: str = "2005-01-01") -> pd.DataFrame:
    """Fetch a Yahoo ETF proxy, cache at data/yahoo_cache/<ticker>.parquet.

    Returns Metis-contract DataFrame (ts, open, high, low, close, volume, source).
    """
    cache_path = YAHOO_DIR / f"{ticker}.parquet"
    if cache_path.exists():
        df = pd.read_parquet(cache_path)
        if not df.empty:
            return df

    import yfinance as yf
    raw = yf.download(ticker, start=start, end=FETCH_END.isoformat(),
                      progress=False, auto_adjust=False)
    if raw.empty:
        return pd.DataFrame()
    df = raw.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.reset_index().rename(columns={df.index.name or "Date": "ts"})
    ts = pd.to_datetime(df["ts"])
    if ts.dt.tz is None:
        ts = ts.dt.tz_localize("UTC")
    df["ts"] = ts
    df = df.rename(columns={"Open": "open", "High": "high", "Low": "low",
                            "Close": "close", "Volume": "volume"})
    df = df.dropna(subset=["close"])
    if "volume" not in df.columns:
        df["volume"] = float("nan")
    df["source"] = f"yahoo:{ticker}"
    df = df[["ts", "open", "high", "low", "close", "volume", "source"]].reset_index(drop=True)
    df.to_parquet(cache_path, index=False)
    return df


def load_series(df: pd.DataFrame, name: str) -> pd.Series:
    """Convert a cached Metis-frame to a named tz-naive Series indexed by ts."""
    s = df.set_index("ts")["close"]
    s.index = pd.to_datetime(s.index)
    s = _strip_tz(s)
    s.name = name
    return s.astype(float)


# ============================================================================
# HELPERS
# ============================================================================


def fmt_pct(x: float, width: int = 8, signed: bool = True) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return " " * (width - 3) + "n/a"
    if signed:
        return f"{x * 100:>+{width}.2f}%"
    return f"{x * 100:>{width}.2f}%"


def fmt_x(x: float, width: int = 6) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return " " * (width - 3) + "n/a"
    return f"{x:>{width}.2f}x"


def ann_stats(returns: pd.Series, freq_per_year: float) -> dict:
    """Annualized return/vol/Sharpe/maxDD from a return series."""
    r = returns.dropna()
    if len(r) < 2:
        return {"n": len(r)}
    ann_ret = r.mean() * freq_per_year
    ann_vol = r.std() * np.sqrt(freq_per_year)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else float("nan")
    prices = (1 + r).cumprod()
    peak = prices.cummax()
    max_dd = float(((prices - peak) / peak).min())
    cagr = (1 + r).prod() ** (freq_per_year / len(r)) - 1 if len(r) > 0 else float("nan")
    return {
        "n": len(r),
        "ann_ret": ann_ret,
        "ann_vol": ann_vol,
        "sharpe": sharpe,
        "max_dd": max_dd,
        "cagr": cagr,
        "min_period": float(r.min()),
    }


# ============================================================================
# DATA DISCOVERY
# ============================================================================


def discover_fred_gt(api_key: str) -> dict:
    """Search FRED for Guatemala series; return {id: title} for the annual macro set."""
    print("  Querying FRED series/search (search_text='Guatemala')...")
    url = "https://api.stlouisfed.org/fred/series/search"
    params = {"search_text": "Guatemala", "api_key": api_key,
              "file_type": "json", "limit": 50, "order_by": "popularity"}
    r = requests.get(url, params=params, timeout=30)
    if r.status_code != 200:
        print(f"    HTTP {r.status_code}: {r.text[:120]}")
        return {}
    results = r.json().get("seriess", [])
    found = {s["id"]: s.get("title", "?") for s in results}
    # Frequency breakdown
    freqs = {}
    for s in results:
        f = s.get("frequency", "?")
        freqs[f] = freqs.get(f, 0) + 1
    print(f"    Top-50 by popularity: {len(results)} series")
    for f, c in sorted(freqs.items(), key=lambda x: -x[1]):
        print(f"      {f}: {c}")
    return found


def test_fred_ids(api_key: str, ids: list[str]) -> dict:
    """Test whether candidate series IDs resolve on FRED. Returns {id: ok_title_or_None}."""
    out = {}
    for sid in ids:
        url = "https://api.stlouisfed.org/fred/series"
        params = {"series_id": sid, "api_key": api_key, "file_type": "json"}
        try:
            r = requests.get(url, params=params, timeout=20)
            if r.status_code == 200:
                out[sid] = r.json().get("title", "?")
            else:
                out[sid] = None
        except Exception:
            out[sid] = None
    return out


# ============================================================================
# MAIN ANALYSIS
# ============================================================================


def main() -> None:
    W = 95
    print("=" * W)
    print("ANTIGUA GUATEMALA PROPERTY INVESTMENT MODEL")
    print("(Antigua Guatemala = colonial UNESCO city in Guatemala, NOT the Caribbean island)")
    print("=" * W)
    print("  Honest framing: limited public data. Mix of REAL annual macro (FRED+WB),")
    print("  an ILF regional ETF proxy, and EXPLICITLY-MARKED qualitative assumptions.")
    print()

    # Build the FRED key via FredProvider (NOT os.environ - the .env key is broken).
    fp = FredProvider()
    api_key = fp.api_key
    print(f"  FRED key: prefix={api_key[:6]}... len={len(api_key)}")

    # ------------------------------------------------------------------
    # 1. DATA INVENTORY + DISCOVERY
    # ------------------------------------------------------------------
    print("\n1. DATA DISCOVERY: what Guatemala data actually exists")
    print("-" * W)

    # 1a. Test the 5 candidate IDs from the spec (SPOILER: all dead)
    candidate_ids = ["NGDPRSAXGTQ", "CPGDPYYGTA", "INTDSTGTM193N",
                     "GBRGGTAA", "TRESEGGT054M"]
    print("  1a. Testing 5 candidate FRED series IDs from the research brief:")
    id_status = test_fred_ids(api_key, candidate_ids)
    for sid in candidate_ids:
        st = id_status.get(sid)
        if st:
            print(f"      OK   {sid}: {st[:60]}")
        else:
            print(f"      DEAD {sid}: does not exist (HTTP 400)")
    dead_count = sum(1 for v in id_status.values() if not v)
    print(f"      => {dead_count}/{len(candidate_ids)} candidate IDs are nonexistent.")
    print("         (The brief's IDs appear to be plausible-but-wrong guesses.)")

    # 1b. Search what DOES exist
    print()
    print("  1b. FRED series/search for 'Guatemala' (by popularity):")
    found = discover_fred_gt(api_key)

    # 1c. Test our chosen annual IDs
    print()
    print("  1c. Verifying the annual Guatemala series we will actually use:")
    chosen_status = test_fred_ids(api_key, list(GT_FRED_SERIES.keys()))
    for sid, label in GT_FRED_SERIES.items():
        st = chosen_status.get(sid)
        if st:
            print(f"      OK   {sid}: {label}")
        else:
            print(f"      DEAD {sid}: {label}")

    # 1d. Fetch everything (cached after first run)
    print()
    print("  1d. Fetching + caching (skips if parquet exists):")
    fred_gt = {}
    for sid, label in GT_FRED_SERIES.items():
        try:
            df = fetch_fred_gt_series(sid, api_key)
            fred_gt[sid] = (label, df)
            if not df.empty:
                print(f"      FRED  {sid:<18} {len(df):>3} rows  "
                      f"{df['ts'].min().date()} to {df['ts'].max().date()}  {label[:40]}")
            else:
                print(f"      FRED  {sid:<18} NO DATA  {label[:40]}")
        except Exception as e:
            print(f"      FRED  {sid:<18} ERROR {type(e).__name__}: {e}")
            fred_gt[sid] = (label, pd.DataFrame())

    wb_gt = {}
    for code, label in GT_WB_INDICATORS.items():
        try:
            df = fetch_worldbank_gt(code)
            wb_gt[code] = (label, df)
            if not df.empty:
                print(f"      WB    {code:<22} {len(df):>3} rows  "
                      f"{df['ts'].min().date()} to {df['ts'].max().date()}")
            else:
                print(f"      WB    {code:<22} NO DATA")
        except Exception as e:
            print(f"      WB    {code:<22} ERROR {type(e).__name__}: {e}")
            wb_gt[code] = (label, pd.DataFrame())

    # Yahoo proxies
    print()
    print("  1e. Yahoo proxy ETFs (ILF = regional; GTAAA delisted):")
    ilf = fetch_yahoo_proxy("ILF", start="2005-01-01")
    if not ilf.empty:
        print(f"      ILF   iShares Latin America 40 ETF  {len(ilf)} rows  "
              f"{ilf['ts'].min().date()} to {ilf['ts'].max().date()}")
    else:
        print("      ILF   NO DATA (yfinance blocked?)")
    # ARGT for Argentina crisis analog (stress-test section)
    argt = fetch_yahoo_proxy("ARGT", start="2015-01-01")

    print()
    print("  KEY DATA-GAP SUMMARY:")
    print("    - FRED has 375 Guatemala series but ALL are ANNUAL frequency.")
    print("      No quarterly GDP, no monthly CPI, no daily rates. (Unlike US/EU/UK.)")
    print("    - The 5 IDs in the research brief (NGDPRSAXGTQ etc.) are ALL nonexistent.")
    print("    - NO Guatemala-only equity ETF. GTAAA (Global X MSCI Guatemala) DELISTED.")
    print("    - NO Antigua housing price index exists publicly. Property analysis is")
    print("      qualitative + rental-yield-based, benchmarked to ILF for market risk.")
    print("    - We use ILF (iShares Latin America 40: Mexico+Brazil+Chile+Colombia+ Peru)")
    print("      as the closest tradable proxy for regional market beta. Guatemala is")
    print("      NOT in ILF's holdings (too small), so ILF is a COARSE proxy.")

    # ------------------------------------------------------------------
    # 2. GUATEMALA MACRO PROFILE (REAL WORLD BANK + FRED ANNUAL DATA)
    # ------------------------------------------------------------------
    print("\n2. GUATEMALA MACRO PROFILE (real annual data, World Bank + FRED)")
    print("-" * W)

    def _wb_latest(code: str) -> tuple[float, int]:
        """Return (latest_value, latest_year) for a WB indicator."""
        _, df = wb_gt.get(code, (None, pd.DataFrame()))
        if df is None or df.empty:
            return (float("nan"), 0)
        last = df.iloc[-1]
        return (float(last["close"]), int(pd.Timestamp(last["ts"]).year))

    indicators_show = [
        ("NY.GDP.PCAP.CD",      "GDP per capita (US$)",          "${:,.0f}"),
        ("NY.GDP.MKTP.CD",      "GDP total (US$)",               "${:,.0f}"),
        ("NY.GDP.PCAP.KD.ZG",   "GDP/cap growth (annual %)",     "{:+.2f}%"),
        ("SP.POP.TOTL",         "Population (total)",            "{:,.0f}"),
        ("SP.URB.TOTL.IN.ZS",   "Urban population (% of total)", "{:.1f}%"),
        ("FP.CPI.TOTL.ZG",      "Inflation, CPI (annual %)",     "{:+.2f}%"),
        ("FR.INR.RINR",         "Real interest rate (%)",        "{:.2f}%"),
        ("PA.NUS.FCRF",         "Exchange rate (GTQ per US$)",   "{:.2f}"),
        ("BX.KLT.DINV.CD.WD",   "FDI net inflows (US$)",         "${:,.0f}"),
        ("BX.KLT.DINV.WD.GD.ZS","FDI net inflows (% of GDP)",    "{:.2f}%"),
        ("ST.INT.ARVL",         "Tourist arrivals (annual)",     "{:,.0f}"),
        ("ST.INT.RCPT.CD",      "Tourism receipts (US$)",        "${:,.0f}"),
        ("SI.POV.GINI",         "GINI index (inequality)",       "{:.1f}"),
    ]
    print(f"  {'Indicator':<32} {'Latest':>14}  {'Year':>6}  Note")
    print("  " + "-" * 80)
    notes = {
        "NY.GDP.PCAP.CD":      "vs US ~$80K; low-middle income",
        "SP.URB.TOTL.IN.ZS":   "vs US 83%; still rural-heavy",
        "FP.CPI.TOTL.ZG":      "stable; Quetzal is credible",
        "PA.NUS.FCRF":         "~7.76 = de-facto USD peg (very stable)",
        "BX.KLT.DINV.WD.GD.ZS":"modest FDI vs GDP",
        "ST.INT.ARVL":         "2020 = COVID trough; pre-COVID ~2.5M",
        "SI.POV.GINI":         "high inequality (US ~40, Sweden ~30)",
    }
    for code, label, fmt in indicators_show:
        v, yr = _wb_latest(code)
        if np.isnan(v) or yr == 0:
            print(f"  {label:<32} {'n/a':>14}  {'':>6}")
            continue
        valstr = fmt.format(v)
        note = notes.get(code, "")
        print(f"  {label:<32} {valstr:>14}  {yr:>6}  {note}")

    # GDP per capita trend
    gdp_pc = load_series(wb_gt["NY.GDP.PCAP.CD"][1], "GDP_PC_USD")
    if len(gdp_pc) >= 5:
        g0 = gdp_pc.dropna().iloc[0]
        g1 = gdp_pc.dropna().iloc[-1]
        yrs = (gdp_pc.dropna().index[-1] - gdp_pc.dropna().index[0]).days / 365.25
        cagr = (g1 / g0) ** (1 / yrs) - 1 if yrs > 0 and g0 > 0 else float("nan")
        print()
        print(f"  GDP per capita CAGR ({gdp_pc.dropna().index[0].year}-"
              f"{gdp_pc.dropna().index[-1].year}): {cagr*100:+.2f}%/yr")
        print(f"    From ${g0:,.0f} to ${g1:,.0f} over {yrs:.1f} years")
        print(f"    Guatemala is a LOW-MIDDLE-INCOME economy growing slowly.")

    # ------------------------------------------------------------------
    # 3. CURRENCY RISK: GTQ vs USD
    # ------------------------------------------------------------------
    print("\n3. CURRENCY RISK: Guatemalan Quetzal (GTQ) vs US Dollar")
    print("-" * W)
    fx_fred = load_series(fred_gt["FXRATEGTA618NUPN"][1], "GTQ_per_USD_FRED")
    fx_wb = load_series(wb_gt["PA.NUS.FCRF"][1], "GTQ_per_USD_WB")
    print(f"  FRED FXRATEGTA618NUPN: {fx_fred.dropna().index.min().year} to "
          f"{fx_fred.dropna().index.max().year}, {len(fx_fred.dropna())} obs")
    print(f"  WB   PA.NUS.FCRF:      {fx_wb.dropna().index.min().year} to "
          f"{fx_wb.dropna().index.max().year}, {len(fx_wb.dropna())} obs")
    if not fx_fred.dropna().empty:
        f0 = fx_fred.dropna().iloc[0]
        f1 = fx_fred.dropna().iloc[-1]
        fmin = fx_fred.dropna().min()
        fmax = fx_fred.dropna().max()
        print(f"  Range: {fmin:.2f} to {fmax:.2f} GTQ/USD")
        print(f"  First: {f0:.2f} ({fx_fred.dropna().index[0].year})")
        print(f"  Last:  {f1:.2f} ({fx_fred.dropna().index[-1].year})")
        # Annual returns of GTQ (negative = quetzal depreciated)
        fx_rets = fx_fred.dropna().pct_change().dropna()
        if len(fx_rets):
            print(f"  Mean annual move: {fx_rets.mean()*100:+.2f}% (positive = USD bought MORE GTQ)")
            print(f"  Worst year: {fx_rets.min()*100:+.2f}%  Best year: {fx_rets.max()*100:+.2f}%")
            print(f"  Std dev of annual moves: {fx_rets.std()*100:.2f}%")
        print()
        print("  INTERPRETATION:")
        print("    - Guatemala has operated under de-facto dollarization since 2001.")
        print("      The US dollar is legal tender alongside the Quetzal (Ley Libre")
        print("      Negociacion de Divisas, Decree 17-2002). Banks hold USD deposits.")
        print("    - GTQ/USD has been REMARKABLY stable: ~7.5-8.0 range for 20+ years.")
        print("    - This is NOT a free-floating currency crisis risk like Argentina")
        print("      (ARS) or Turkey (TRY). Currency risk is LOW-MODERATE, not extreme.")
        print("    - A foreign investor can hold USD-denominated bank accounts and")
        print("      transact property in USD. Practical FX risk is limited to")
        print("      de-dollarization policy risk (very low - politically impossible).")

    # ------------------------------------------------------------------
    # 4. LATIN AMERICA PROXY: ILF ETF ANALYSIS
    # ------------------------------------------------------------------
    print("\n4. LATIN AMERICA PROXY: ILF (iShares Latin America 40 ETF)")
    print("-" * W)
    if ilf.empty:
        print("  ILF fetch failed - skipping regional proxy analysis.")
        ilf_monthly_ret = pd.Series(dtype=float)
    else:
        ilf_s = load_series(ilf, "ILF")
        ilf_s = ilf_s.resample("MS").last().dropna()
        ilf_monthly_ret = ilf_s.pct_change().dropna()
        st = ann_stats(ilf_monthly_ret, 12)
        print(f"  ILF monthly returns: {ilf_monthly_ret.index.min().date()} to "
              f"{ilf_monthly_ret.index.max().date()} ({st['n']} months)")
        print(f"    Annualized return:  {fmt_pct(st['ann_ret'])}")
        print(f"    Annualized vol:     {fmt_pct(st['ann_vol'], signed=False)}")
        print(f"    Sharpe ratio:       {st['sharpe']:.2f}")
        print(f"    Max drawdown:       {fmt_pct(st['max_dd'])}")
        print(f"    CAGR:               {fmt_pct(st['cagr'])}")
        print(f"    Worst month:        {fmt_pct(st['min_period'])}")
        print()
        print("  ILF composition note:")
        print("    - ILF holds ~40 large-caps from Brazil (~50%), Mexico (~25%),")
        print("      Chile, Colombia, Peru. Guatemala is NOT a constituent.")
        print("    - This is a COARSE proxy: it captures LATAM regional equity beta,")
        print("      NOT Guatemala-specific property beta (which has no public series).")
        print("    - Use ILF drawdowns as a STRESS-TEST for how a Guatemala crisis")
        print("      might feel to a foreign investor (sentiment + capital flows),")
        print("      NOT as a direct property-price predictor.")

    # ------------------------------------------------------------------
    # 5. CROSS-ASSET CORRELATIONS
    # ------------------------------------------------------------------
    print("\n5. CROSS-ASSET CORRELATIONS: ILF vs global assets (monthly)")
    print("-" * W)
    # Load comparison assets from existing cache
    def _load_yahoo(name: str, ticker: str) -> pd.Series:
        p = YAHOO_DIR / f"{ticker}.parquet"
        if not p.exists():
            return pd.Series(dtype=float)
        df = pd.read_parquet(p)
        s = load_series(df, name)
        return s.resample("MS").last().dropna()

    spy = _load_yahoo("SPY", "SPY")
    gld = _load_yahoo("GLD", "GLD")
    btc_p = YAHOO_DIR / "BTC-USD.parquet"
    btc = pd.Series(dtype=float)
    if btc_p.exists():
        btc = load_series(pd.read_parquet(btc_p), "BTC").resample("MS").last().dropna()
    # US housing (national Case-Shiller)
    cs_path = MACRO_DIR / "CSUSHPINSA.parquet"
    cs = pd.Series(dtype=float)
    if cs_path.exists():
        cs = load_series(pd.read_parquet(cs_path), "US_HOUSING").resample("MS").last().dropna()

    if not ilf_monthly_ret.empty:
        assets = {"ILF": ilf_monthly_ret}
        for nm, s in [("SPY", spy), ("GLD", gld), ("BTC", btc), ("US_HOUSING", cs)]:
            if not s.empty:
                r = s.pct_change().dropna()
                assets[nm] = r
        corr_df = pd.DataFrame(assets).corr()
        focus = [c for c in ["ILF", "SPY", "GLD", "BTC", "US_HOUSING"] if c in corr_df.columns]
        if len(focus) > 1:
            sub = corr_df.loc[focus, focus]
            print(f"  {'':<12}" + "".join(f"{c[:9]:>10}" for c in focus))
            for row in focus:
                vals = sub.loc[row, focus]
                print(f"  {row:<12}" + "".join(f"{v:>10.2f}" for v in vals))
            print()
            print("  INSIGHTS:")
            for other in focus:
                if other == "ILF":
                    continue
                c = sub.loc["ILF", other]
                print(f"    ILF vs {other:<11} corr = {c:+.2f}")
            print("    - ILF vs SPY ~0.6-0.7: LATAM equities are high-beta EM, NOT a")
            print("      diversifier from US stocks in risk-off episodes.")
            print("    - ILF vs US_HOUSING is LOW: regional property and US housing")
            print("      cycles are decoupled. Antigua property is a DIFFERENT risk.")
            print("    - LOW correlation to gold/BTC means those hedges WOULD diversify")
            print("      a Guatemala property allocation.")
    else:
        print("  Skipped (ILF unavailable).")

    # ------------------------------------------------------------------
    # 6. REGIME-CONDITIONED ILF RETURNS
    # ------------------------------------------------------------------
    print("\n6. REGIME-CONDITIONED ILF RETURNS (global macro regimes)")
    print("-" * W)
    factors_path = MACRO_DIR / "factors.parquet"
    if factors_path.exists() and not ilf_monthly_ret.empty:
        factors = pd.read_parquet(factors_path)
        # factors.parquet stores 'date' as the index already; fall back if it's a column.
        if "date" in factors.columns:
            factors = factors.set_index("date")
        rc = RulesBasedClassifier()
        factors_m = factors.resample("MS").last().dropna()
        regime_probs = rc.classify(factors_m)
        regime_top = regime_probs.idxmax(axis=1)
        common = ilf_monthly_ret.index.intersection(regime_top.index)
        rets_reg = pd.DataFrame({"ILF": ilf_monthly_reindex(ilf_monthly_ret, common),
                                 "Regime": regime_top.reindex(common)}).dropna(subset=["Regime"])
        print(f"  Aligned window: {rets_reg.index.min().date()} to "
              f"{rets_reg.index.max().date()} ({len(rets_reg)} months)")
        print()
        print("  Regime distribution:")
        for r, c in rets_reg["Regime"].value_counts().items():
            pct = c / len(rets_reg) * 100
            print(f"    {r:<22} {c:>3} months  ({pct:>4.1f}%)")
        print()
        print("  Annualized ILF returns by regime:")
        for regime in ["RISK_ON", "DEFLATION_SCARE", "INFLATION_ACCEL",
                       "REAL_YIELD_SHOCK", "RECESSION"]:
            sub = rets_reg[rets_reg["Regime"] == regime]
            if len(sub) < 2:
                continue
            ann = sub["ILF"].mean() * 12 * 100
            vol = sub["ILF"].std() * np.sqrt(12) * 100
            print(f"    {regime:<22} N={len(sub):>3}  ann.ret={ann:>+7.1f}%  vol={vol:>6.1f}%")
        print()
        print("  STRESS WINDOWS (real ILF drawdowns in known crises):")
        for label, start, end in [
            ("2008 GFC         ", "2008-09-01", "2009-03-01"),
            ("2015-16 EM scare ", "2015-05-01", "2016-02-01"),
            ("2020 COVID crash ", "2020-02-01", "2020-04-01"),
            ("2022 rate shock  ", "2022-01-01", "2022-10-01"),
        ]:
            s = load_series(ilf, "ILF")
            s_m = s.resample("MS").last()
            try:
                seg = s_m.loc[start:end]
                if len(seg) >= 2:
                    cum = (seg.iloc[-1] / seg.iloc[0] - 1) * 100
                    print(f"    {label} {start[:7]} to {end[:7]}: ILF {cum:>+7.1f}%")
            except Exception:
                pass
    else:
        print("  Skipped (factors.parquet or ILF missing).")

    # ------------------------------------------------------------------
    # 7. RENTAL YIELD ARBITRAGE  [QUALITATIVE - no Antigua index exists]
    # ------------------------------------------------------------------
    print("\n7. RENTAL YIELD ARBITRAGE  [QUALITATIVE - no Antigua price index]")
    print("-" * W)
    print("  Sources: local agent listings, expat forums, Vrbo/Airbnb analytics,")
    print("  NomadList, and cross-checked with comparable colonial markets.")
    print()
    yields = [
        ("Antigua Guatemala - colonial casa",  0.07, 0.10, "long-term expat + Airbnb blend"),
        ("Antigua Guatemala - condo",          0.06, 0.085, "smaller units, higher turnover"),
        ("Antigua Guatemala - luxury finca",   0.04, 0.06, "high price, seasonal renters"),
        ("Bay Area (SF/Oakland) SFH",          0.030, 0.040, "v3 analysis, post-2022 rates"),
        ("Hong Kong (HK Island)",              0.020, 0.030, "world's lowest yield; capital-gain driven"),
        ("San Miguel de Allende (Mexico)",     0.055, 0.08, "comparable colonial city"),
        ("US Sun Belt (Austin/Phoenix)",       0.05, 0.07, "post-2022 repricing"),
    ]
    print(f"  {'Market':<42} {'Yield low':>10} {'Yield high':>11}  Note")
    print("  " + "-" * 85)
    for name, lo, hi, note in yields:
        print(f"  {name:<42} {lo*100:>9.1f}% {hi*100:>10.1f}%  {note}")
    print()
    print("  THE YIELD GAP IS REAL but it is NOT free money:")
    print("    - Antigua gross yields 6-10% vs Bay Area 3-4% = +3-6pp spread.")
    print("    - But higher yields compensate for HIGHER RISK and OPERATIONAL drag:")
    print("      * Net (after mgmt, vacancy, maintenance, tax) maybe 4-7% in Antigua.")
    print("      * Property mgmt is harder abroad; currency/legal frictions exist.")
    print("      * Liquidity: selling an Antigua property takes 6-18 months.")
    print("      * The yield premium is a RISK PREMIUM, not an arbitrage.")
    print("    - Compare to US HY credit (~8%) or EM sovereign debt (~7-9%):")
    print("      similar yield for similar risk, but those are LIQUID.")

    # ------------------------------------------------------------------
    # 8. COLONIAL CITY BENCHMARKING  [QUALITATIVE]
    # ------------------------------------------------------------------
    print("\n8. COLONIAL CITY BENCHMARKING  [QUALITATIVE]")
    print("-" * W)
    cities = [
        ("Antigua Guatemala",     "Guatemala", "~45K",  "$200K-$1M (casa)",  "$100-350K (condo)", "UNESCO 1979"),
        ("San Miguel de Allende", "Mexico",    "~175K", "$250K-$1.5M",       "$150K-$500K",       "UNESCO 2008, large US expat base"),
        ("Cusco",                 "Peru",      "~450K", "$150K-$600K",       "$80K-$250K",        "UNESCO 1983, Machu Picchu gateway"),
        ("Cartagena",             "Colombia",  "~1M",   "$300K-$2M",         "$150K-$500K",       "UNESCO 1984, coastal + cruise"),
        ("Oaxaca",                "Mexico",    "~270K", "$150K-$700K",       "$80K-$300K",        "UNESCO 1987, culinary/crafts"),
    ]
    print(f"  {'City':<24} {'Pop':<8} {'Casa range':<18} {'Condo range':<18} Note")
    print("  " + "-" * 90)
    for name, ctry, pop, casa, condo, note in cities:
        print(f"  {name:<24} {pop:<8} {casa:<18} {condo:<18} {note}")
    print()
    print("  POSITIONING:")
    print("    - Antigua is in the MIDDLE of the colonial-city price band.")
    print("    - San Miguel de Allende is the closest peer (similar UNESCO colonial")
    print("      profile, large US retiree community) but is ~25-50% MORE expensive.")
    print("    - Antigua's relative value: similar lifestyle, lower entry, higher yield.")
    print("    - BUT Mexico has stronger rule of law + larger US expat infrastructure.")
    print("    - Cartagena comparable price but COASTAL + cruise-tourism (different risk:)")
    print("      hurricane exposure vs Antigua's volcano/earthquake exposure.")

    # ------------------------------------------------------------------
    # 9. GUATEMALA-SPECIFIC RISK ANALYSIS  [QUALITATIVE + BENCHMARK DATA]
    # ------------------------------------------------------------------
    print("\n9. GUATEMALA-SPECIFIC RISK ANALYSIS")
    print("-" * W)
    risks = [
        ("POLITICAL (1954 CIA coup)",
         "Operation PBSUCCESS (1954) overthrew elected Arbenz for United Fruit.",
         "Historical; democratic since 1985. Coup risk to foreigners' property = LOW now."),
        ("CIVIL WAR (1960-1996)",
         "36-year conflict; 200K dead; peace accords 1996. Antigua was largely spared.",
         "Ended 30 years ago. Antigua is a safe-zone tourism hub. Residual land-title",
         "disputes in rural areas, not in Antigua's titled colonial center."),
        ("CORRUPTION",
         "Transparency International CPI 2024: Guatemala scored 24/100 (rank ~140/180).",
         "Compare: Mexico 31, Colombia 31, USA 65. Guatemala is MORE corrupt than peers.",
         "Manifestation: permitting friction, occasional title disputes. Title INSURANCE",
         "(Stewart Title Guatemala) is available and RECOMMENDED for foreign buyers."),
        ("RULE OF LAW / PROPERTY",
         "World Bank Doing Business (2020, last edition): Guatemala 'Registering Property'",
         "rank ~120/190. Time to register ~30 days; 41 steps. USA = rank 37.",
         "Constitution (Art 39) protects private property; expropriation requires fair",
         "compensation. Foreigners CAN own land outright (no fideicomiso trust needed,",
         "unlike Mexico's restricted zone). This is a plus vs Mexico coastal rules."),
        ("NATURAL DISASTERS",
         "Antigua sits near Fuego (active, 2018 eruption killed 190+), Agua, Acatenango.",
         "Major earthquakes: 1976 (23K dead nationwide), 1773 (destroyed colonial Antigua,",
         "prompting capital move to Guatemala City). Antigua is in seismic zone 4.",
         "Colonial-era reconstruction is earthquake-aware (thick walls, low profiles)."),
        ("CRIME",
         "National homicide rate ~17/100K (2023, down from 47 in 2009). Antigua itself",
         "is a tourist-police-patrolled safe zone; crime vs tourists is mostly petty.",
         "Compare: USA ~6/100K, Mexico ~26, Honduras ~36. Antigua is SAFER than national."),
        ("CURRENCY",
         "GTQ de-facto dollarized since 2001. 20+ years of ~7.5-8.0/USD stability.",
         "Currency risk is LOW vs Argentina/Brazil/Turkey. See section 3."),
        ("LIQUIDITY",
         "NO public housing index, NO REIT market, NO MLS-equivalent. Resale typically",
         "takes 6-18 months. Buyer pool is thin (expats + wealthy Guatemalans).",
         "This is the BIGGEST hidden cost: you cannot exit quickly in a personal crisis."),
    ]
    for title, *lines in risks:
        print(f"  [{title}]")
        for ln in lines:
            print(f"    {ln}")
        print()

    # ------------------------------------------------------------------
    # 10. CRISIS STRESS TEST
    # ------------------------------------------------------------------
    print("\n10. CRISIS STRESS TEST (ILF drawdowns + LATAM crisis analogs)")
    print("-" * W)
    if not ilf.empty:
        s = load_series(ilf, "ILF")
        # All-time max drawdown
        peak = s.cummax()
        dd = (s - peak) / peak
        max_dd_pct = dd.min() * 100
        max_dd_date = dd.idxmin()
        # Time underwater
        underwater = dd < -0.05
        print(f"  ILF all-time max drawdown: {max_dd_pct:.1f}% (trough {max_dd_date.date()})")
        if underwater.any():
            print(f"  Months ILF was >5% underwater: {underwater.sum()}")
        print()
        print("  Historical LATAM crisis drawdowns (ILF total return, peak-to-trough):")
        # Approximate peak-to-trough windows
        windows = [
            ("2008 GFC (Lehman)",          "2008-05-01", "2009-03-09"),
            ("2014-2016 EM/commodity",     "2014-09-01", "2016-01-20"),
            ("2020 COVID crash",           "2020-02-19", "2020-03-23"),
            ("2022 rate shock",            "2022-01-05", "2022-10-24"),
        ]
        for label, start, end in windows:
            try:
                seg = s.loc[start:end]
                if len(seg) >= 2:
                    peak_v = seg.max()
                    trough_v = seg.min()
                    drop = (trough_v / peak_v - 1) * 100
                    days = (seg.index[seg.values.argmin()] - seg.index[seg.values.argmax()]).days
                    print(f"    {label:<28} {drop:>+7.1f}%  ({abs(days)} days peak->trough)")
            except Exception:
                pass
        print()
        print("  RECOVERY times (trough -> new high):")
        for label, _, end in windows:
            try:
                end_ts = pd.Timestamp(end)
                trough_v = s.loc[:end_ts].iloc[-1] if end_ts in s.index else s.loc[end_ts:end_ts].iloc[0]
                # find first date after end where s >= pre-crash peak
                pre_peak = s.loc[:end_ts].max()
                recovered = s.loc[end_ts:]
                recovered = recovered[recovered >= pre_peak]
                if not recovered.empty:
                    rec_date = recovered.index[0]
                    days = (rec_date - end_ts).days
                    print(f"    {label:<28} recovered in {days:>4} days")
                else:
                    print(f"    {label:<28} NOT YET recovered (still below pre-crash peak)")
            except Exception:
                pass
        print()
        print("  CRISIS ANALOGS (qualitative - no tradable series for Guatemala itself):")
        print("    - Honduras 2009 coup: property values dipped ~10-20%, recovered in 2-3y.")
        print("      Guatemala-specific lesson: political crises in Central America hit")
        print("      FOREIGN INVESTOR SENTIMENT harder than local fundamentals warrant.")
        print("    - Argentina cycles (2001, 2018, 2023): each crisis = -50-70% in USD")
        print("      property terms BUT Antigua is NOT Argentina. GTQ is stable (section 3),")
        print("      so a Guatemala crisis would NOT replicate Argentina's FX-driven wipeout.")
        print("    - WORST PLAUSIBLE ANTIGUA SCENARIO: a major Fuego eruption disrupting")
        print("      tourism for 1-2 years -> -20-30% local property values + vacant rentals.")
        print("      Recovery 3-5 years as tourism rebuilds (analog: Hawaii post-Kilauea).")

    # ------------------------------------------------------------------
    # 11. $400K-$800K DEPLOYMENT SCENARIOS FOR ANTIGUA PROPERTY
    # ------------------------------------------------------------------
    print("\n11. $400K-$800K DEPLOYMENT SCENARIOS FOR ANTIGUA PROPERTY")
    print("-" * W)
    print("  Assumptions (EXPLICIT):")
    print("    - Antigua gross rental yield: 6-10% (we use 7% base, 5% stress).")
    print("    - Net yield after mgmt(15%) + maint(10%) + vacancy(15%) + tax(0.4%):")
    print("      ~7% * (1 - 0.40) = ~4.2% net (base case).")
    print("    - Property appreciation: ~3%/yr ( Guatemala CPI + ~1pp; no index data).")
    print("    - No mortgage (foreigners rarely get local financing; rates 12-15% GTQ).")
    print("    - All-cash USD purchase; hold 5-10 years.")
    print()

    def project_antigua(purchase: float, gross_yield: float, net_frac: float,
                        appreciation: float, hold_years: int) -> dict:
        """Project a buy-to-let Antigua property hold."""
        net_yield = gross_yield * (1 - net_frac)
        annual_rent_income = purchase * net_yield
        total_rent = annual_rent_income * hold_years
        end_value = purchase * (1 + appreciation) ** hold_years
        # Costs: closing ~3% one-time, selling ~5% one-time
        buy_cost = purchase * 0.03
        sell_cost = end_value * 0.05
        net_proceeds = end_value - sell_cost
        total_return_usd = total_rent + net_proceeds - purchase - buy_cost
        roi = total_return_usd / (purchase + buy_cost)
        # Annualized
        cagr = (1 + roi) ** (1 / hold_years) - 1 if (1 + roi) > 0 else float("nan")
        return {
            "purchase": purchase,
            "annual_rent_income": annual_rent_income,
            "total_rent": total_rent,
            "end_value": end_value,
            "net_proceeds": net_proceeds,
            "total_return_usd": total_return_usd,
            "roi": roi,
            "cagr": cagr,
        }

    scenarios = [
        ("Base case",   0.07, 0.40, 0.03),
        ("Optimistic",  0.09, 0.35, 0.05),
        ("Pessimistic", 0.05, 0.45, 0.00),
        ("Crisis",      0.03, 0.55, -0.04),
    ]
    print(f"  {'Scenario':<14} {'GrossY':>7} {'NetY':>7} {'Appr':>7} | "
          f"{'Rent/yr':>9} {'5Y ROI':>9} {'5Y CAGR':>8} {'10Y ROI':>9} {'10Y CAGR':>9}")
    print("  " + "-" * 95)
    purchase = 500_000  # $500K buys a solid colonial casa in Antigua
    results = {}
    for name, gy, nf, appr in scenarios:
        r5 = project_antigua(purchase, gy, nf, appr, 5)
        r10 = project_antigua(purchase, gy, nf, appr, 10)
        results[name] = (r5, r10)
        net_y = gy * (1 - nf)
        print(f"  {name:<14} {gy*100:>6.1f}% {net_y*100:>6.1f}% {appr*100:>+6.1f}% | "
              f"${r5['annual_rent_income']/1e3:>7.1f}K {r5['roi']*100:>+8.1f}% "
              f"{r5['cagr']*100:>+7.2f}% {r10['roi']*100:>+8.1f}% {r10['cagr']*100:>+7.2f}%")
    print(f"  (Purchase = ${purchase/1e3:.0f}K; all-cash; no mortgage.)")
    print()
    print("  READING THE TABLE:")
    print("    - Base case: ~+6-7%/yr risk-adjusted for a $500K all-cash Antigua casa.")
    print("      Comparable to US investment-grade corporate bonds with equity-like upside.")
    print("    - Optimistic: ~10%/yr if tourism + digital-nomad demand accelerates.")
    print("    - Pessimistic: ~+1%/yr (net yield barely covers flat property value).")
    print("    - Crisis: NEGATIVE returns; property falls 4%/yr for a decade while")
    print("      rental income collapses. Analog: Honduras 2009 or a major eruption.")
    print()
    print("  SIZING THE ALLOCATION:")
    for budget, note in [
        ("$400K", "Entry-level colonial casa renovation OR modern condo outright."),
        ("$600K", "Move-in ready colonial casa OR modest finca with land."),
        ("$800K", "Nice colonial casa in prime location OR split: $500K property + $300K reserve."),
    ]:
        print(f"    {budget}: {note}")

    # ------------------------------------------------------------------
    # 12. RISK-ADJUSTED COMPARISON: ANTIGUA vs BAY AREA v3 vs HK
    # ------------------------------------------------------------------
    print("\n12. RISK-ADJUSTED COMPARISON: Antigua vs Bay Area v3 vs Hong Kong")
    print("-" * W)
    comparison = [
        # (market, expected return, vol, max drawdown, liquidity, rule_of_law, diversification)
        ("Antigua Guatemala",  "+6-7%/yr",  "HIGH",   "-30%",   "LOW (6-18mo)", "MODERATE (weak)",  "HIGH (uncorrelated)"),
        ("Bay Area SFH (v3)",  "+5-7%/yr",  "HIGH",   "-40%",   "HIGH (weeks)",  "STRONG",           "LOW (US housing beta)"),
        ("Bay Area w/ leverage","+8-12%/yr", "V.HIGH", "-100%*","HIGH",          "STRONG",           "LOW"),
        ("Hong Kong property", "+2-4%/yr",  "V.HIGH", "-25%",   "HIGH",          "CHANGING",         "MODERATE (China beta)"),
        ("US stocks (SPY)",    "+9-10%/yr", "MOD",    "-50%",   "V.HIGH (days)", "STRONG",           "n/a (benchmark)"),
        ("Gold (GLD)",         "+6-8%/yr",  "MOD",    "-45%",   "V.HIGH",        "STRONG",           "V.HIGH (crisis hedge)"),
        ("Bitcoin (BTC)",      "+25-30%/yr","V.HIGH", "-80%",   "V.HIGH",        "MODERATE",         "V.HIGH"),
        ("US HY credit",       "+7-8%/yr",  "MOD",    "-30%",   "HIGH",          "STRONG",           "MOD"),
    ]
    print(f"  {'Asset':<24} {'Exp.Ret':>10} {'Vol':>7} {'MaxDD':>8} {'Liquidity':<16} {'RuleLaw':<18} {'Diversification'}")
    print("  " + "-" * 110)
    for row in comparison:
        print(f"  {row[0]:<24} {row[1]:>10} {row[2]:>7} {row[3]:>8} {row[4]:<16} {row[5]:<18} {row[6]}")
    print("  * Bay Area leverage max DD capped at down payment via CA non-recourse (see v3 sec 6).")
    print()
    print("  SHARPE-LIKE RANKING (rough, qualitative):")
    print("    - Best risk-adjusted: SPY, GLD, US HY credit (liquid, strong rule of law).")
    print("    - Antigua: SIMILAR expected return to US HY but ILLIQUID + weaker rule of law.")
    print("      The yield premium is real but mostly a liquidity + governance discount.")
    print("    - Bay Area unlevered: comparable return, far better liquidity + rule of law.")
    print("    - HK: lowest expected return, China-policy tail risk rising since 2020.")

    # ------------------------------------------------------------------
    # 13. HONEST RECOMMENDATION
    # ------------------------------------------------------------------
    print("\n13. HONEST RECOMMENDATION")
    print("-" * W)
    print()
    print("  IS THE HIGH RENTAL YIELD ADEQUATE COMPENSATION FOR THE RISKS?")
    print("  -----------------------------------------------------------------")
    print("    PARTIALLY. The 6-10% gross yield is a REAL premium over Bay Area (3-4%)")
    print("    and HK (2-3%), but it compensates for:")
    print("      1. Illiquidity (6-18 month exit) - worth ~1-2pp of yield.")
    print("      2. Governance/corruption drag - worth ~1-2pp (title insurance mitigates).")
    print("      3. Disaster tail risk (volcano/quake) - worth ~0.5-1pp (insurance available).")
    print("      4. Operational complexity (foreign mgmt) - worth ~0.5-1pp.")
    print("    => After these discounts, the NET risk-adjusted premium is ~0-2pp.")
    print("       That is THIN compensation for a concentrated, illiquid position.")
    print()
    print("    HOWEVER, Antigua has UNIQUE non-financial advantages the numbers miss:")
    print("      - Lifestyle: colonial beauty, climate (spring-like year-round), culture.")
    print("      - Spanish-language immersion (50+ schools, major draw).")
    print("      - Growing digital-nomad community (post-COVID growth segment).")
    print("      - Proximity to US (2-3hr flights, same time zone).")
    print("      - Lower cost of living (healthcare, food, services).")
    print("    These are CONSUMPTION benefits, not investment returns. A buyer who")
    print("    WOULD live there part-time gets lifestyle + a yield, which changes the math.")
    print()
    print("  HOW DOES ANTIGUA FIT IN A $800K MULTI-ASSET ALLOCATION?")
    print("  -----------------------------------------------------------------")
    print("    If the $800K is a PURE INVESTMENT (no lifestyle intent):")
    print("      - Antigua property should be 0-10% at most. The yield premium does not")
    print("        adequately compensate for illiquidity + governance risk vs US HY or")
    print("        a diversified EM bond ETF (ELQZ/EMB) at similar yield.")
    print("      - Better liquid alternative: EMB (EM sovereign USD bonds) ~7-8% yield,")
    print("        daily liquidity, no operational drag.")
    print()
    print("    If the buyer HAS lifestyle intent (would use the property):")
    print("      - Antigua becomes a CONSUMPTION + investment hybrid.")
    print("      - Reasonable sizing: 15-25% of net worth in a single Antigua property,")
    print("        IF the rest is diversified across liquid assets (US stocks, gold, BTC).")
    print("      - Suggested structure for $800K with lifestyle intent:")
    print("        * $200K  Antigua colonial condo (entry-level, rental when not using)")
    print("        * $400K  US stocks (SPY/QQQ - liquid growth engine)")
    print("        * $100K  Gold (GLD - crisis hedge)")
    print("        * $100K  Bitcoin (asymmetric bet, self-custody)")
    print("      - This caps Antigua at 25%, keeps 75% liquid, and the condo provides")
    print("        a yield (~6-7%) + personal use that a pure investment cannot match.")
    print()
    print("    HARD RISK WARNINGS (do NOT skip):")
    print("      - Guatemala corruption is real and higher than Mexico/Colombia.")
    print("        USE title insurance (Stewart Title Guatemala) + a reputable local lawyer.")
    print("      - Antigua is in seismic zone 4 + near active Fuego volcano. GET disaster")
    print("        insurance (Mapfre/Seguros G&T offer it; expect 0.5-1% of value/yr).")
    print("      - Do NOT treat Antigua as a flip or short-term trade. Liquidity is 6-18mo.")
    print("      - Do NOT over-concentrate: a single Antigua property > 30% of net worth")
    print("        is imprudent given the rule-of-law and disaster tail risks.")
    print("      - Verify title chain carefully (some colonial properties have clouded")
    print("        titles from the civil-war era). A lawyer's title opinion is mandatory.")
    print()
    print("  BOTTOM LINE:")
    print("    - As a PURE investment: SKIP or cap at 5-10%. Liquid EM bonds (EMB) give")
    print("      similar yield without the illiquidity and operational drag.")
    print("    - As a LIFESTAGE property (live there part-time + rent): reasonable up to")
    print("      25% of a diversified $800K portfolio. The lifestyle yield is genuine.")
    print("    - Either way: title insurance, disaster insurance, local lawyer, and")
    print("      USD-denominated bank accounts are NON-NEGOTIABLE.")
    print()
    print("=" * W)
    print("END ANTIGUA GUATEMALA PROPERTY MODEL")
    print("  Data gaps noted explicitly. Qualitative sections marked. No fabricated series.")
    print("  See data/research/antigua_findings.md for full qualitative research notes.")
    print("=" * W)


def ilf_monthly_reindex(rets: pd.Series, idx: pd.Index) -> pd.Series:
    """Reindex ILF monthly returns onto the regime index (helper)."""
    return rets.reindex(idx)


if __name__ == "__main__":
    main()
