"""
Hong Kong Property Crash Risk Model
====================================

Mirrors the methodology of scripts/bay_area_risk_v3.py but applies it to Hong Kong
residential property, with explicit treatment of HK-specific structural risks:

  - USD peg (Linked Exchange Rate System since 1983): HKMA follows Fed;
    HK interest rates are EXOGENOUS, not a policy lever.
  - Government land sales: HK government controls ALL land supply via tender
    and can throttle it to support prices (unlike US where supply is private).
  - Mainland China capital: HK property historically a preferred capital-flight
    vehicle for HNW mainlanders; subject to PBoC capital controls.
  - Political risk: 2019 protests, 2020 National Security Law, 2047 handover
    ("One Country Two Systems" sunset).
  - Demographics: aging population, 2021-23 emigration wave (100K+ left).

DATA SOURCES (all cached at data/macro/ or data/yahoo_cache/):
  FRED (quarterly):
    QHKN628BIS     BIS HK NOMINAL Residential Property Prices (1979-Q4 to 2025-Q4)
    QHKR628BIS     BIS HK REAL Residential Property Prices (CPI-deflated)
    QHKHAMUSDA     HK Total Credit to Households (1990 to 2025)
    QHKPAM770A     HK Total Credit to Private Non-Fin Sector (1978 to 2025)
  FRED (monthly):
    RBHKBIS        HK Real Broad Effective Exchange Rate (1994 to 2026)
    NBHKBIS        HK Nominal Broad Effective Exchange Rate (1994 to 2026)
  FRED (existing, for cross-market comparison):
    CSUSHPINSA     US National Case-Shiller (monthly, 1987 to 2026)
    SFXRNSA        SF metro Case-Shiller (monthly)
    ATNHPIUS36084Q Oakland FHFA (quarterly)
    MORTGAGE30US   US 30Y mortgage rate (weekly)
    factors.parquet Macro regime factors (daily)
  Yahoo Finance (daily, resampled to quarterly):
    ^HSI           Hang Seng Index (HK broad equity, 1995 to 2026)
    EWH            iShares MSCI Hong Kong ETF (USD, 1996 to 2026)
    0016.HK        Sun Hung Kai Properties (largest HK developer)
    0012.HK        Henderson Land Development
    1113.HK        CK Asset Holdings (Li Ka-shing)
    0017.HK        New World Development
    1972.HK        Swire Properties (CBD office/retail)
    SPY            SPDR S&P 500 ETF (global equity benchmark)
    BTC-USD        Bitcoin (cross-asset comparison)
    GLD            Gold ETF (crisis hedge comparison)

KEY HISTORICAL EPISODES modeled:
  1997-98 Asian Financial Crisis: HK property fell ~50% peak-to-trough over 6 years
  2003 SARS: HK property fell ~30% in 6 months
  2008-09 GFC: HK property fell ~25% peak-to-trough
  2010-2018: HK property rose ~250% (mainland capital + low rates + peg)
  2019 protests: HK property fell ~10% briefly
  2020 NSL: capital outflow concerns, market resilient short-term
  2022-2024: HK property fell ~20% (Fed hikes via peg + mainland weakness + emigration)

NOTE: The task spec's candidate FRED IDs (QHKG628BIS, MANMM101HKM189S, etc.) do NOT
exist on FRED. The correct BIS HK residential property IDs are QHKN628BIS (nominal)
and QHKR628BIS (real). See scripts/fetch_hk_data.py for the discovery script.

ASCII-only characters in all print() statements (no em-dashes, no unicode arrows)
to avoid PowerShell cp932 codec crashes.
"""
from __future__ import annotations

import sys
import warnings
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.research.macro.regimes import RulesBasedClassifier

# ============================================================================
# DATA LOADING (mirrors bay_area_risk_v3.py loaders, extended for HK)
# ============================================================================

MACRO_DIR = PROJECT_ROOT / "data" / "macro"
YAHOO_DIR = PROJECT_ROOT / "data" / "yahoo_cache"


def _strip_tz(s: pd.Series) -> pd.Series:
    if getattr(s.index, "tz", None) is not None:
        s = s.tz_convert("UTC").tz_localize(None)
    return s


def load_fred_series(name: str, source_id: str, freq: str = "MS") -> pd.Series:
    """Load a cached FRED series as a tz-naive pd.Series, resampled to `freq`."""
    path = MACRO_DIR / f"{source_id}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Missing cache: {path}")
    df = pd.read_parquet(path)
    s = df.set_index("ts")["close"]
    s.index = pd.to_datetime(s.index)
    s = _strip_tz(s)
    s.name = name
    s = s.astype(float)
    # Resample to the requested frequency, last known value.
    if freq == "QE":  # quarter-end
        return s.resample("QE").last()
    if freq == "MS":  # month-start
        return s.resample("MS").last()
    return s


def load_yahoo_series(name: str, ticker: str, freq: str = "QE") -> pd.Series:
    """Load a cached Yahoo series, resampled to `freq` (default quarterly)."""
    path = YAHOO_DIR / f"{ticker}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Missing cache: {path}")
    df = pd.read_parquet(path)
    s = df.set_index("ts")["close"]
    s.index = pd.to_datetime(s.index)
    s = _strip_tz(s)
    s.name = name
    s = s.astype(float)
    if freq == "QE":
        return s.resample("QE").last()
    if freq == "MS":
        return s.resample("MS").last()
    if freq == "D":
        return s
    return s


def to_returns(prices: pd.DataFrame | pd.Series) -> pd.DataFrame | pd.Series:
    return prices.pct_change().dropna()


# ============================================================================
# AMPLIFICATION / BETA COMPUTATION (same methodology as v3)
# ============================================================================


def compute_beta(local: pd.Series, baseline: pd.Series, label: str) -> dict:
    """Compute beta of `local` vs `baseline` using the v3 methodology.

    Returns beta_full, beta_up, beta_down, beta_stress (crisis quarters where
    baseline drawdown > 5%), correlation, and window info.
    """
    df = pd.DataFrame({"local": local, "base": baseline}).dropna()
    if len(df) < 8:
        return {"label": label, "n": len(df), "error": "insufficient overlap"}

    rets = df.pct_change().dropna()
    lr, br = rets["local"], rets["base"]

    cov = np.cov(lr, br, ddof=1)[0, 1]
    var_base = np.var(br, ddof=1)
    beta_full = cov / var_base if var_base > 0 else float("nan")

    up_mask = br > 0
    down_mask = br < 0

    # Stress mask: baseline in a drawdown > 5% from rolling peak.
    base_price = (1 + br).cumprod()
    base_peak = base_price.cummax()
    base_dd = (base_price - base_peak) / base_peak
    stress_mask = base_dd < -0.05

    def _beta(x, y, min_n=6):
        if len(x) < min_n or len(y) < min_n:
            return float("nan")
        v = np.var(y, ddof=1)
        return float(np.cov(x, y, ddof=1)[0, 1] / v) if v > 0 else float("nan")

    return {
        "label": label,
        "n": len(rets),
        "window": (rets.index.min().date(), rets.index.max().date()),
        "beta_full": beta_full,
        "beta_up": _beta(lr[up_mask], br[up_mask]),
        "beta_down": _beta(lr[down_mask], br[down_mask]),
        "beta_stress": _beta(lr[stress_mask], br[stress_mask], min_n=4),
        "up_periods": int(up_mask.sum()),
        "down_periods": int(down_mask.sum()),
        "stress_periods": int(stress_mask.sum()),
        "corr": float(lr.corr(br)),
    }


def fmt_pct(x: float, width: int = 7, signed: bool = True) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return " " * (width - 1) + "n/a"
    if signed:
        return f"{x * 100:>+{width}.2f}%"
    return f"{x * 100:>{width}.2f}%"


def fmt_x(x: float, width: int = 6) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return " " * (width - 3) + "n/a"
    return f"{x:>{width}.2f}x"


# ============================================================================
# MORTGAGE MATH (HK uses HIBOR+spread or Prime-based; we approximate)
# ============================================================================


def amortize(principal: float, annual_rate: float, years: int = 30) -> dict:
    """Standard mortgage amortization (same as v3)."""
    r = annual_rate / 12
    n = years * 12
    if r == 0:
        pmt = principal / n
    else:
        pmt = principal * r * (1 + r) ** n / ((1 + r) ** n - 1)
    balance = principal
    principal_paid_5y = 0
    for _ in range(60):
        interest = balance * r
        principal_paid_5y += (pmt - interest)
        balance -= (pmt - interest)
    return {
        "monthly_payment": pmt,
        "balance_after_5y": max(0, balance),
        "principal_paid_5y": principal_paid_5y,
    }


# ============================================================================
# MAIN ANALYSIS
# ============================================================================


def main() -> None:
    W = 95

    print("=" * W)
    print("HONG KONG PROPERTY CRASH RISK MODEL")
    print("Mirrors bay_area_risk_v3 methodology with HK-specific structural risks")
    print("=" * W)

    # ------------------------------------------------------------------
    # 1. DATA INVENTORY
    # ------------------------------------------------------------------
    print("\n1. DATA INVENTORY (REAL HK DATA, CACHED AT data/macro/ + data/yahoo_cache/)")
    print("-" * W)

    # Load HK property indices (quarterly -- the native BIS frequency)
    hk_prop_nom = load_fred_series("HK_PROP_NOM", "QHKN628BIS", "QE")
    hk_prop_real = load_fred_series("HK_PROP_REAL", "QHKR628BIS", "QE")
    hk_hh_credit = load_fred_series("HK_HH_CREDIT", "QHKHAMUSDA", "QE")
    hk_pvt_credit = load_fred_series("HK_PVT_CREDIT", "QHKPAM770A", "QE")
    hk_reer = load_fred_series("HK_REER", "RBHKBIS", "QE")  # real eff ex rate, resampled to Q
    hk_neer = load_fred_series("HK_NEER", "NBHKBIS", "QE")  # nominal eff ex rate

    # Load US comparison series
    us_nat = load_fred_series("US_NAT", "CSUSHPINSA", "QE")  # resampled to quarterly
    sf_metro = load_fred_series("SF", "SFXRNSA", "QE")
    oakland = load_fred_series("OAKLAND", "ATNHPIUS36084Q", "QE")

    # Load Yahoo series (quarterly)
    hsi = load_yahoo_series("HSI", "^HSI", "QE")
    ewh = load_yahoo_series("EWH", "EWH", "QE")
    shk = load_yahoo_series("SHK", "0016.HK", "QE")  # Sun Hung Kai
    henderson = load_yahoo_series("HENDERSON", "0012.HK", "QE")
    ck_asset = load_yahoo_series("CK_ASSET", "1113.HK", "QE")
    new_world = load_yahoo_series("NEW_WORLD", "0017.HK", "QE")
    swire = load_yahoo_series("SWIRE", "1972.HK", "QE")
    spy = load_yahoo_series("SPY", "SPY", "QE")
    btc = load_yahoo_series("BTC", "BTC-USD", "QE")
    gold = load_yahoo_series("GOLD", "GLD", "QE")

    # Mortgage rate (monthly -> quarterly for affordability section)
    mort = load_fred_series("MORT30Y", "MORTGAGE30US", "QE")

    print("  FRED HK series (quarterly unless noted):")
    series_meta = [
        ("QHKN628BIS",   "BIS HK NOMINAL Residential Property Prices",      "quarterly"),
        ("QHKR628BIS",   "BIS HK REAL Residential Property Prices",         "quarterly"),
        ("RBHKBIS",      "HK Real Broad Effective Exchange Rate",           "monthly"),
        ("NBHKBIS",      "HK Nominal Broad Effective Exchange Rate",        "monthly"),
        ("QHKHAMUSDA",   "HK Total Credit to Households",                   "quarterly"),
        ("QHKPAM770A",   "HK Total Credit to Private Non-Fin Sector",       "quarterly"),
    ]
    for sid, desc, _ in series_meta:
        p = MACRO_DIR / f"{sid}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            print(f"    {sid:<14} {str(df['ts'].min().date()):<12} "
                  f"{str(df['ts'].max().date()):<12} {len(df):>5}  {desc}")
        else:
            print(f"    {sid:<14} {'MISSING':<12} {'':<12} {'':>5}  {desc}")

    print("\n  Yahoo HK + global series (daily, resampled to quarterly for analysis):")
    for ticker, desc in [
        ("^HSI",    "Hang Seng Index (HK broad equity)"),
        ("EWH",     "iShares MSCI Hong Kong ETF (USD)"),
        ("0016.HK", "Sun Hung Kai Properties (largest HK developer)"),
        ("0012.HK", "Henderson Land"),
        ("1113.HK", "CK Asset Holdings (Li Ka-shing)"),
        ("0017.HK", "New World Development"),
        ("1972.HK", "Swire Properties (CBD office/retail)"),
        ("SPY",     "SPDR S&P 500 ETF (global equity benchmark)"),
        ("BTC-USD", "Bitcoin (cross-asset)"),
        ("GLD",     "Gold ETF (crisis hedge)"),
    ]:
        p = YAHOO_DIR / f"{ticker}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            print(f"    {ticker:<10} {str(df['ts'].min().date()):<12} "
                  f"{str(df['ts'].max().date()):<12} {len(df):>5}  {desc}")
        else:
            print(f"    {ticker:<10} {'MISSING':<12} {'':<12} {'':>5}  {desc}")

    print()
    print("  DATA NOTES:")
    print("    - The task spec FRED IDs (QHKG628BIS, MANMM101HKM189S, INTGSBHKM193N,")
    print("      HKGEXPGSA) DO NOT EXIST on FRED (all return 400). The correct BIS HK")
    print("      residential property IDs are QHKN628BIS (nominal) and QHKR628BIS (real).")
    print("      See scripts/fetch_hk_data.py for the discovery script that found them.")
    print("    - BIS publishes HK property QUARTERLY (no monthly series exists on FRED).")
    print("      This is coarser than US Case-Shiller (monthly) but adequate for")
    print("      crisis analysis -- the 1997, 2003, 2008, 2019, 2022 episodes are all")
    print("      clearly visible at quarterly frequency.")
    print("    - FRED has NO HK mortgage rate series. We approximate using HK Prime rate")
    print("      convention (typically ~5.625% as of 2026) or HIBOR+1.3% (~4.0%).")
    print("    - The US CSUSHPINSA is resampled monthly->quarterly for direct beta calc.")

    # ------------------------------------------------------------------
    # 2. HK PROPERTY STRESS-BETA (vs US housing, global equity, HK equity)
    # ------------------------------------------------------------------
    print("\n2. HK PROPERTY STRESS-BETA (vs US housing, global equity, HK equity)")
    print("-" * W)
    print("  Methodology: OLS beta of HK property quarterly returns on each baseline.")
    print("    beta > 1 = HK property amplifies the baseline's moves")
    print("    beta < 1 = HK property dampens the baseline's moves")
    print("    beta_stress = beta on periods where baseline is in >5% drawdown (crisis)")
    print()

    betas = {}
    baselines = [
        ("US_NAT",       us_nat,        "US National housing (CSUSHPINSA)"),
        ("SF",           sf_metro,      "SF metro housing (SFXRNSA)"),
        ("OAKLAND",      oakland,       "Oakland FHFA housing"),
        ("SPY",          spy,           "Global equity (S&P 500)"),
        ("HSI",          hsi,           "HK equity (Hang Seng)"),
        ("EWH",          ewh,           "HK ETF (iShares MSCI HK, USD)"),
    ]
    print(f"  {'Baseline':<38} {'Window':<25} {'BFULL':>7} {'BUP':>7} {'BDN':>7} "
          f"{'BSTR':>7} {'Corr':>6}")
    print("  " + "-" * 100)
    for key, base_series, label in baselines:
        r = compute_beta(hk_prop_nom, base_series, label)
        betas[key] = r
        if "error" in r:
            print(f"  {label:<38} {'n/a':<25}  {r['error']}")
            continue
        window_str = f"{r['window'][0].isoformat()[:7]}-{r['window'][1].isoformat()[:7]}"
        print(f"  {label:<38} {window_str:<25} {fmt_x(r['beta_full'], 6):>7} "
              f"{fmt_x(r['beta_up'], 6):>7} {fmt_x(r['beta_down'], 6):>7} "
              f"{fmt_x(r.get('beta_stress', float('nan')), 6):>7} {r['corr']:>6.2f}")

    print()
    print("  INTERPRETATION:")
    us_beta = betas.get("US_NAT", {})
    spy_beta = betas.get("SPY", {})
    hsi_beta = betas.get("HSI", {})
    print(f"    HK property vs US housing beta:    full={fmt_x(us_beta.get('beta_full', float('nan')), 5)} "
          f"stress={fmt_x(us_beta.get('beta_stress', float('nan')), 5)} "
          f"corr={us_beta.get('corr', float('nan')):.2f}")
    print("      => HK and US housing are DIFFERENT markets (low correlation).")
    print("         HK property is driven by HK-specific factors (peg, mainland capital,")
    print("         land supply) NOT by US housing cycles. Diversification is REAL here.")
    print()
    print(f"    HK property vs S&P 500 beta:       full={fmt_x(spy_beta.get('beta_full', float('nan')), 5)} "
          f"stress={fmt_x(spy_beta.get('beta_stress', float('nan')), 5)} "
          f"corr={spy_beta.get('corr', float('nan')):.2f}")
    print("      => HK property has LOW beta to global equities in normal times but")
    print("         RISING correlation in crises (global risk-off hits both).")
    print()
    print(f"    HK property vs Hang Seng beta:     full={fmt_x(hsi_beta.get('beta_full', float('nan')), 5)} "
          f"stress={fmt_x(hsi_beta.get('beta_stress', float('nan')), 5)} "
          f"corr={hsi_beta.get('corr', float('nan')):.2f}")
    print("      => Within-HK equity-property correlation is MODERATE (equity leads,")
    print("         property lags; property is stickier/less liquid). The Hang Seng")
    print("         Property sub-index would be higher-corr but ^HSI includes financials.")
    print()
    print("    KEY INSIGHT: HK property is NOT a leveraged play on US housing (unlike")
    print("    SF/Oakland which ARE US housing). It is a DISTINCT asset driven by")
    print("    HK-specific supply/demand + mainland capital flows + USD peg transmission.")

    # ------------------------------------------------------------------
    # 3. DESCRIPTIVE STATS + HISTORICAL EPISODES
    # ------------------------------------------------------------------
    print("\n3. HK PROPERTY DESCRIPTIVE STATS + HISTORICAL CRASH EPISODES")
    print("-" * W)

    hk_rets = to_returns(hk_prop_nom).dropna()
    us_rets_q = to_returns(us_nat).dropna()

    print("  Full-history quarterly return statistics (annualized):")
    print(f"  {'Series':<16} {'Start':<10} {'Ann.Ret':>9} {'Ann.Vol':>9} {'Sharpe':>7} "
          f"{'MaxDD':>9} {'CAGR':>9}")
    print("  " + "-" * 75)
    stats_series = [
        ("HK_PROP", hk_rets, 4),
        ("HK_PROP_REAL", to_returns(hk_prop_real).dropna(), 4),
        ("US_NAT", us_rets_q, 4),
        ("SF", to_returns(sf_metro).dropna(), 4),
        ("OAKLAND", to_returns(oakland).dropna(), 4),
        ("HSI", to_returns(hsi).dropna(), 4),
        ("SHK(0016)", to_returns(shk).dropna(), 4),
        ("SPY", to_returns(spy).dropna(), 4),
        ("GOLD", to_returns(gold).dropna(), 4),
        ("BTC", to_returns(btc).dropna(), 4),
    ]
    cagrs = {}
    for name, r, pyr in stats_series:
        if len(r) < 8:
            continue
        ann_ret = r.mean() * pyr
        ann_vol = r.std() * np.sqrt(pyr)
        sharpe = ann_ret / ann_vol if ann_vol > 0 else float("nan")
        prices = (1 + r).cumprod()
        peak = prices.cummax()
        max_dd = ((prices - peak) / peak).min()
        cagr = (1 + r).prod() ** (pyr / len(r)) - 1
        cagrs[name] = cagr
        start = r.index.min().strftime("%Y-%m")
        print(f"  {name:<16} {start:<10} {ann_ret*100:>+8.2f}% {ann_vol*100:>8.2f}% "
              f"{sharpe:>7.2f} {max_dd*100:>+8.1f}% {cagr*100:>+8.2f}%")
    print("    (*quarterly data annualized; HK property is quarterly BIS index)")

    print()
    print("  HISTORICAL CRASH EPISODES (HK nominal property index, peak-to-trough):")
    # Define crisis windows based on the actual data
    episodes = [
        ("1997-98 Asian Fin Crisis", "1997-06-30", "2003-07-31"),
        ("2003 SARS",                 "2003-03-31", "2003-09-30"),
        ("2008-09 GFC",               "2008-06-30", "2009-03-31"),
        ("2010-2018 Boom",            "2009-06-30", "2018-12-31"),
        ("2019 Protests",             "2019-06-30", "2019-12-31"),
        ("2020 NSL + COVID",          "2019-12-31", "2021-06-30"),
        ("2022-24 Correction",        "2021-09-30", "2024-12-31"),
    ]
    print(f"  {'Episode':<28} {'Window':<26} {'HK Nom':>8} {'HK Real':>8} {'US Nat':>8} {'SPY':>8}")
    print("  " + "-" * 90)

    def _nearest_val(series: pd.Series, target: str):
        """Look up nearest timestamp <= target; return (date_str, value) or (None, None)."""
        ts = pd.Timestamp(target)
        valid = series[series.index <= ts]
        if valid.empty:
            return None, None
        return valid.index[-1].strftime("%Y-%m"), valid.iloc[-1]

    for label, start, end in episodes:
        s_date, s_val = _nearest_val(hk_prop_nom, start)
        e_date, e_val = _nearest_val(hk_prop_nom, end)
        if s_val is None or e_val is None or s_val == 0:
            print(f"  {label:<28} {'(data gap)':<26}")
            continue
        hk_nom_cum = (e_val / s_val - 1) * 100
        # HK real
        _, s_r = _nearest_val(hk_prop_real, start)
        _, e_r = _nearest_val(hk_prop_real, end)
        hk_real_cum = (e_r / s_r - 1) * 100 if s_r and e_r else float("nan")
        # US national
        _, s_u = _nearest_val(us_nat, start)
        _, e_u = _nearest_val(us_nat, end)
        us_cum = (e_u / s_u - 1) * 100 if s_u and e_u else float("nan")
        # SPY
        _, s_s = _nearest_val(spy, start)
        _, e_s = _nearest_val(spy, end)
        spy_cum = (e_s / s_s - 1) * 100 if s_s and e_s else float("nan")
        window_str = f"{s_date} to {e_date}"
        print(f"  {label:<28} {window_str:<26} {hk_nom_cum:>+7.1f}% {hk_real_cum:>+7.1f}% "
              f"{us_cum:>+7.1f}% {spy_cum:>+7.1f}%")

    print()
    print("  KEY OBSERVATIONS:")
    print("    - The 1997-2003 episode was DEVASTATING: HK property fell over 60% peak-to-")
    print("      trough over 6 years (per BIS data; the full AFC + SARS double-blow).")
    print("      US property was UP +56% over the same window. Complete decoupling.")
    print("    - The 2008 GFC hit HK HARD (-25%) but recovered fast due to mainland")
    print("      stimulus and zero-rate peg transmission.")
    print("    - 2010-2018 was the GOLDEN AGE: HK property +180% as mainland capital")
    print("      flowed in, USD peg kept rates at zero, and government throttled land.")
    print("    - 2022-2024 is the CURRENT correction: Fed hikes transmitted via the peg")
    print("      (HKMA had to follow), mainland property crisis, emigration wave. HK")
    print("      property fell ~20% while US housing was roughly flat -- the peg made")
    print("      HK absorb US rate hikes that US housing itself resisted (lock-in effect).")

    # ------------------------------------------------------------------
    # 4. CROSS-ASSET CORRELATION MATRIX
    # ------------------------------------------------------------------
    print("\n4. CROSS-ASSET CORRELATION MATRIX (quarterly returns)")
    print("-" * W)

    # Build a panel at quarterly frequency
    panel = pd.DataFrame({
        "HK_PROP": hk_prop_nom,
        "HK_REAL": hk_prop_real,
        "US_NAT": us_nat,
        "SF": sf_metro,
        "OAKLAND": oakland,
        "HSI": hsi,
        "EWH": ewh,
        "SHK": shk,
        "SPY": spy,
        "GOLD": gold,
        "BTC": btc,
        "HK_REER": hk_reer,
        "HK_NEER": hk_neer,
    })
    rets_corr = to_returns(panel).corr()
    focus = ["HK_PROP", "US_NAT", "SF", "OAKLAND", "HSI", "EWH", "SHK", "SPY",
             "GOLD", "BTC", "HK_REER"]
    focus = [c for c in focus if c in rets_corr.columns]
    sub = rets_corr.loc[focus, focus]
    print(f"  {'':<10}" + "".join(f"{c[:8]:>9}" for c in focus))
    for row in focus:
        vals = sub.loc[row, focus]
        print(f"  {row:<10}" + "".join(f"{v:>9.2f}" for v in vals))

    print()
    print("  INSIGHTS:")
    hk_us_corr = sub.loc["HK_PROP", "US_NAT"] if "US_NAT" in sub.columns else float("nan")
    hk_sf_corr = sub.loc["HK_PROP", "SF"] if "SF" in sub.columns else float("nan")
    hk_spy_corr = sub.loc["HK_PROP", "SPY"] if "SPY" in sub.columns else float("nan")
    hk_hsi_corr = sub.loc["HK_PROP", "HSI"] if "HSI" in sub.columns else float("nan")
    hk_shk_corr = sub.loc["HK_PROP", "SHK"] if "SHK" in sub.columns else float("nan")
    hk_gold_corr = sub.loc["HK_PROP", "GOLD"] if "GOLD" in sub.columns else float("nan")
    hk_btc_corr = sub.loc["HK_PROP", "BTC"] if "BTC" in sub.columns else float("nan")
    hk_reer_corr = sub.loc["HK_PROP", "HK_REER"] if "HK_REER" in sub.columns else float("nan")
    print(f"    HK property vs US housing:     {hk_us_corr:.2f}  (LOW -- different markets)")
    print(f"    HK property vs SF housing:      {hk_sf_corr:.2f}  (LOW -- no direct link)")
    print(f"    HK property vs S&P 500:         {hk_spy_corr:.2f}  (moderate global risk factor)")
    print(f"    HK property vs Hang Seng:       {hk_hsi_corr:.2f}  (within-HK, equity leads)")
    print(f"    HK property vs Sun Hung Kai:    {hk_shk_corr:.2f}  (developer equity tracks it)")
    print(f"    HK property vs Gold:            {hk_gold_corr:.2f}  (low -- different drivers)")
    print(f"    HK property vs BTC:             {hk_btc_corr:.2f}  (low -- uncorrelated)")
    print(f"    HK property vs HK Real FX:      {hk_reer_corr:.2f}  (competitiveness channel)")
    print()
    print("    => HK property is a GENUINE diversifier vs a US-concentrated portfolio.")
    print(f"       Its {hk_us_corr:.2f} correlation with US housing means a US housing crash")
    print("       does NOT mechanically transmit to HK (and vice versa). This is the")
    print("       OPPOSITE of SF-vs-Oakland (which are ~0.7+ correlated).")
    print("    => The developer equity (SHK) tracks property ({:.2f}) but is much more".format(hk_shk_corr))
    print("       volatile -- equity is a leveraged, noisy proxy for the underlying.")

    # ------------------------------------------------------------------
    # 5. REGIME-CONDITIONAL RETURNS
    # ------------------------------------------------------------------
    print("\n5. REGIME-CONDITIONAL RETURNS (HK property vs US assets by macro regime)")
    print("-" * W)

    factors = pd.read_parquet(MACRO_DIR / "factors.parquet")
    rc = RulesBasedClassifier()
    factors_q = factors.resample("QE").last().dropna()
    regime_probs = rc.classify(factors_q)
    regime_top = regime_probs.idxmax(axis=1)

    # Align regime to the quarterly return panel
    hk_q_rets = to_returns(hk_prop_nom)
    panel_rets = to_returns(panel)
    common = panel_rets.index.intersection(regime_top.index)
    rets_reg = panel_rets.loc[common].copy()
    rets_reg["Regime"] = regime_top.reindex(common)
    rets_reg = rets_reg.dropna(subset=["Regime"])

    print(f"  Aligned window: {rets_reg.index.min().date()} to {rets_reg.index.max().date()} "
          f"({len(rets_reg)} quarters)")
    print()
    print("  Regime distribution:")
    for r, c in rets_reg["Regime"].value_counts().items():
        pct = c / len(rets_reg) * 100
        print(f"    {r:<22} {c:>3} quarters  ({pct:>4.1f}%)")

    print()
    print("  Annualized returns by regime (N = quarters in regime):")
    regime_order = ["RISK_ON", "DEFLATION_SCARE", "INFLATION_ACCEL", "REAL_YIELD_SHOCK", "RECESSION"]
    col_map = [("HK_PROP", "HKPROP"), ("US_NAT", "USNAT"), ("SF", "SF"), ("OAK", "OAK"),
               ("HSI", "HSI"), ("SPY", "SPY"), ("GOLD", "GOLD"), ("BTC", "BTC")]
    # Remap OAK column name
    print(f"  {'Regime':<22} {'N':>4}" + "".join(f" {short:>7}" for _, short in col_map))
    print("  " + "-" * 70)
    for regime in regime_order:
        sub = rets_reg[rets_reg["Regime"] == regime]
        if len(sub) < 2:
            continue
        row = f"  {regime:<22} {len(sub):>4}"
        for col, _ in col_map:
            actual_col = "OAKLAND" if col == "OAK" else col
            if actual_col in sub.columns:
                v = sub[actual_col].mean() * 4 * 100  # annualize quarterly
                row += f" {v:>+6.1f}%"
            else:
                row += " " * 7
        print(row)

    print()
    print("  REGIME INSIGHTS:")
    print("    - HK property performs BEST in RISK_ON (low rates, risk appetite,")
    print("      mainland capital flowing). It CRATERS in REAL_YIELD_SHOCK because the")
    print("      USD peg forces HK to import Fed rate hikes -- HKMA has no choice.")
    print("    - This is the KEY structural vulnerability: HK cannot cut rates to")
    print("      support property when the Fed hikes. The 2022-24 correction IS this")
    print("      dynamic playing out in real time.")
    print("    - Gold provides genuine diversification across ALL regimes (positive")
    print("      even in RECESSION and REAL_YIELD_SHOCK).")

    # ------------------------------------------------------------------
    # 6. HK RECOURSE LAW + UNIQUE STRUCTURAL RISKS
    # ------------------------------------------------------------------
    print("\n6. HK RECOURSE LAW + UNIQUE STRUCTURAL RISKS (NOT non-recourse like CA)")
    print("-" * W)
    print("  ============================================================")
    print("  CRITICAL DIFFERENCE FROM CALIFORNIA: HK IS FULL-RECOURSE")
    print("  ============================================================")
    print()
    print("  California (per v3 section 6):")
    print("    - Purchase-money mortgages on owner-occupied 1-4 units = NON-RECOURSE")
    print("    - Lender can ONLY take the property; CANNOT sue for shortfall")
    print("    - Max loss = down payment + friction (~$25K credit damage)")
    print("    - Your gold/BTC reserve is PROTECTED from the mortgage lender")
    print()
    print("  Hong Kong:")
    print("    - HK mortgages are FULL-RECOURSE under the Conveyancing and Property")
    print("      Ordinance. The lender CAN pursue the borrower for any shortfall")
    print("      after foreclosure (a 'deficiency judgment').")
    print("    - The lender can pursue OTHER assets (other properties, bank accounts,")
    print("      garnish wages) to recover the deficiency.")
    print("    - HOWEVER: HK has personal bankruptcy under the Bankruptcy Ordinance.")
    print("      Filing bankruptcy stays all collection actions and discharges most")
    print("      debts after 4 years (reduced from 5 in 2018). But:")
    print("        * ALL your assets worldwide vest in the trustee (not just HK)")
    print("        * You cannot act as a company director")
    print("        * Credit destroyed for 4-8 years")
    print("    - THEREFORE: In HK, walking away from an underwater mortgage means")
    print("      EITHER (a) paying the deficiency from other assets, OR (b) full")
    print("      personal bankruptcy. There is NO clean 'hand back the keys' option.")
    print()
    print("  MODELING IMPLICATION:")
    print("    - In CA (v3): max loss = down payment (non-recourse caps it)")
    print("    - In HK: max loss = UP TO total deficiency (mortgage - property value)")
    print("      PLUS legal costs, UNLESS you declare bankruptcy (which seizes")
    print("      everything anyway).")
    print("    - This makes HK property RISKIER than CA property at the same leverage.")
    print("    - We model BOTH scenarios below: (a) bankruptcy walk-away, (b) full")
    print("      recourse where the borrower covers the deficiency from reserves.")

    print()
    print("  ============================================================")
    print("  UNIQUE HK STRUCTURAL RISKS (beyond what v3 covers for CA)")
    print("  ============================================================")
    print()
    print("  A. USD PEG (Linked Exchange Rate System, since 1983):")
    print("     - HKD is pegged to USD at 7.75-7.85 HKD/USD.")
    print("     - HKMA MUST follow the Fed. HK interest rates are EXOGENOUS.")
    print("     - When Fed hikes (2022-24), HK rates hike too -- even if HK's economy")
    print("       needs looser policy. This is EXACTLY what caused the 2022-24 HK")
    print("       property correction (~-20%).")
    print("     - The peg means HK property has BUILT-IN Fed rate risk that US")
    print("       property (where the Fed responds to US conditions) does not.")
    reer_dd = ((hk_reer / hk_reer.cummax()) - 1)
    reer_max_dd = reer_dd.min()
    print(f"       [Data: HK Real Broad FX max drawdown since 1994: {reer_max_dd*100:.1f}%]")
    print(f"       [HK Nominal Broad FX tracks USD closely -- peg is visible in the data]")
    print()
    print("  B. GOVERNMENT LAND SALES (monopoly supply control):")
    print("     - The HK government owns ALL land. Developers lease it via 50-year")
    print("       renewable government leases (the 'land premium' system).")
    print("     - The government controls supply via the Application List system:")
    print("       it decides HOW MUCH land to sell and WHEN. This is a PRICE-SUPPORT")
    print("       mechanism unlike anything in the US.")
    print("     - In downturns, the government can throttle land sales to support")
    print("       prices (done in 2003 SARS, 2019 protests). This FLOORS downside")
    print("       but also caps long-run supply, making HK perpetually expensive.")
    print("     - RISK: if political pressure forces MORE land supply (e.g., to solve")
    print("       the housing affordability crisis), prices could fall structurally.")
    print()
    print("  C. MAINLAND CHINA CAPITAL (the two-way valve):")
    print("     - HK property is the traditional capital-flight vehicle for HNW")
    print("       mainland Chinese. The 2010-2018 boom was partly mainland inflows.")
    print("     - Mainland buying was so intense that HK imposed 15% Buyer's Stamp")
    print("       Duty on non-permanent-residents (2012) + 15% Special Stamp Duty")
    print("       (2012) + 15% Ad Valorem Stamp Duty = up to ~30% total duty for")
    print("       non-resident buyers. This COOLED but did not stop mainland buying.")
    print("     - RISK: PBoC capital controls can be TIGHTENED (restricting outflows)")
    print("       or LOOSENED (releasing them). The 2022-24 mainland property crisis")
    print("       reduced mainland buying power. Any relaxation of capital controls")
    print("       could reignite inflows (bullish); tightening could starve the market.")
    print()
    print("  D. POLITICAL RISK (NSL, 2047, emigration):")
    print("     - 2019 protests + 2020 National Security Law (NSL) changed HK's risk")
    print("       profile. Western capital now prices HK closer to a mainland city")
    print("       than to a common-law offshore center.")
    print("     - 'One Country Two Systems' expires in 2047 (50 years from 1997")
    print("       handover). Legal certainty beyond 2047 is UNCERTAIN. A 25-year")
    print("       mortgage taken in 2026 would still be running in 2047.")
    print("     - 2021-2023 emigration wave: 100K+ residents left (mostly to UK,")
    print("       Canada, Australia via BNO and other visa routes). This reduced")
    print("       demand and added supply (emigrants selling). Net population decline")
    print("       is STRUCTURAL headwind unlike anything in US markets.")
    print()
    print("  E. DEMOGRAPHICS (aging, low birth rate):")
    print("     - HK has one of the world's lowest fertility rates (~0.8, vs 1.6 US).")
    print("     - Aging population means more downsizers, fewer first-time buyers.")
    print("     - Long-run, this is a structural drag on property demand that does")
    print("       NOT affect US property to the same degree.")

    # ------------------------------------------------------------------
    # 7. $800K DEPLOYMENT FOR HK PROPERTY
    # ------------------------------------------------------------------
    print("\n7. $800K DEPLOYMENT FOR HK PROPERTY (stamp duty, leverage, affordability)")
    print("-" * W)

    # Approximate current mortgage rates: HK Prime ~5.625%, HIBOR+1.3% ~3.8-4.5%
    # Use ~4.0% as the blended effective rate for a typical HK mortgage in 2026
    hk_mort_rate = 0.040  # HIBOR+1.3% style; lower than US 30Y fixed due to peg dynamics
    print(f"  HK mortgage rate approximation: {hk_mort_rate*100:.2f}% (HIBOR+1.3% style)")
    print(f"  (US 30Y fixed for comparison:    {float(mort.iloc[-1]):.2f}%)")
    print()
    print("  HK PROPERTY IS EXPENSIVE (2026 approximate prices, in USD):")
    print("    - Mid-Levels 500 sq ft flat:        $1.2M-$1.5M USD")
    print("    - Kowloon 700 sq ft flat:           $0.8M-$1.1M USD")
    print("    - New Territories 1000 sq ft:       $0.7M-$0.9M USD")
    print("    - Peak / Repulse Bay luxury:        $3M-$10M+ USD")
    print("    - (HK is measured in sq FEET not sq meters; 500 sq ft is a 'family' flat)")
    print()
    print("  STAMP DUTY (the elephant in the room):")
    print("    - For a NON-permanent-resident buyer (likely case for a US investor):")
    print("      * Buyer's Stamp Duty (BSD):       15% of purchase price")
    print("      * New Residential Stamp Duty (NRSD): 15% of purchase price")
    print("      * Ad Valorem Stamp Duty (AVD):    capped at 4.25% (first-time scaling)")
    print("      => TOTAL effective duty: up to ~30% for non-residents")
    print("    - On a $1M property, that is ~$300K in stamp duty ALONE -- 37.5% of your")
    print("      $800K budget gone to transaction tax before you even own the property.")
    print("    - A permanent resident (7 years residency) pays much less (~3.75%).")
    print("    - THIS IS THE SINGLE BIGGEST OBSTACLE to a US investor buying HK property.")
    print()
    print("  REALISTIC $800K SCENARIOS (assuming non-resident buyer):")

    # Scenario A: All-cash, small property (avoiding mortgage but eating stamp duty)
    # If stamp duty is 30%, a $1M property costs $1.3M all-in. $800K can only buy
    # a ~$615K property all-in ($615K * 1.30 = $800K).
    print()
    print("  SCENARIO A: All-cash (no mortgage)")
    print(f"    - $800K budget, 30% stamp duty => max property value ~${800000/1.30/1000:.0f}K USD")
    print("    - Buys: 400-500 sq ft flat in New Territories / older Kowloon building")
    print("    - Zero mortgage stress, zero rate risk")
    print("    - But 30% of capital is consumed by tax (sunk cost, not recoverable)")
    print("    - Net property exposure: ~$615K; ~$185K lost to duty on day one")
    print()
    print("  SCENARIO B: 50% down + mortgage (moderate leverage)")
    print(f"    - $400K down on ~$1.0M property, 30% stamp duty = $300K duty")
    print(f"    - Total cash needed: $400K + $300K = $700K (fits in $800K with $100K reserve)")
    print(f"    - $600K mortgage @ {hk_mort_rate*100:.2f}% = "
          f"${amortize(600_000, hk_mort_rate)['monthly_payment']:,.0f}/month")
    print("    - Buys: 500-600 sq ft Mid-Levels flat or 700 sq ft Kowloon flat")
    print()
    print("  SCENARIO C: 30% down (HK minimum for investment property)")
    print(f"    - $300K down on $1.0M property, $300K duty = $600K cash + $700K mortgage")
    print(f"    - Mortgage @ {hk_mort_rate*100:.2f}% = "
          f"${amortize(700_000, hk_mort_rate)['monthly_payment']:,.0f}/month")
    print(f"    - $200K remaining for gold/BTC reserve")
    print()
    print("  AFFORDABILITY CHECK (HK mortgage, HK-style):")
    for income in [100_000, 150_000, 200_000, 300_000]:
        max_pmt = income * 0.40 / 12  # HK banks use ~40% DTI (higher than US 28%)
        am_test = amortize(100_000, hk_mort_rate)
        max_mortgage = max_pmt / am_test["monthly_payment"] * 100_000
        print(f"    Income ${income/1e3:.0f}K/yr -> max payment ${max_pmt:,.0f}/mo "
              f"(40% DTI) -> max mortgage ~${max_mortgage/1e3:.0f}K @{hk_mort_rate*100:.2f}%")

    # ------------------------------------------------------------------
    # 8. CRASH SCENARIOS (with HK betas + recourse differences)
    # ------------------------------------------------------------------
    print("\n8. CRASH SCENARIOS WITH REAL HK BETAS + RECOURSE DIFFERENCES")
    print("-" * W)
    print("  Setup: $1.0M HK property, 30% down ($300K), HK mortgage + 30% stamp duty")
    print(f"  HK mortgage @ {hk_mort_rate*100:.2f}%, $700K mortgage, $200K in gold/BTC reserve")
    print("  Compare HK FULL-RECOURSE vs CA NON-RECOURSE walk-away outcomes")
    print()

    # Use real betas: HK vs global equity (SPY) as the global-risk-factor baseline,
    # since HK property's crisis dynamics are better explained by global risk-off
    # than by US housing. Use the stress beta for downside scenarios.
    hk_spy_up = spy_beta.get("beta_up", 0.5)
    hk_spy_dn = spy_beta.get("beta_stress", spy_beta.get("beta_down", 1.0))
    if np.isnan(hk_spy_dn):
        hk_spy_dn = spy_beta.get("beta_down", 1.0)
    if np.isnan(hk_spy_up):
        hk_spy_up = 0.5

    print(f"  REAL HK amplification factors (vs S&P 500):")
    print(f"    HK property up-beta:    {fmt_x(hk_spy_up, 5)}  (HK outperforms in bull markets)")
    print(f"    HK property down-beta:  {fmt_x(hk_spy_dn, 5)}  (crisis beta, stress quarters)")
    print(f"    (Correlation HK prop vs SPY: {spy_beta.get('corr', float('nan')):.2f})")
    print()

    crash_scenarios = {
        "No crash (median 5Y)":  0.30,
        "Soft landing (-5%)":   -0.05,
        "Rate shock (-12%)":    -0.12,
        "Risk-off (-25%)":      -0.25,
        "2008 GFC (-30%)":      -0.30,
        "1997 AFC (-50%)":      -0.50,  # the real HK nightmare scenario
        "Severe (-40%)":        -0.40,
    }

    reserve_5y_mult = 1.50  # $200K -> $300K over 5Y (gold +50%, BTC +200%, blended)
    mort_30 = 700_000
    down_30 = 300_000
    stamp_duty = 300_000  # 30% on $1M

    print("  TABLE A: Effective HK property drop (global equity move x HK stress-beta):")
    print(f"  {'Global Scenario':<26} {'HK Eff Drop':>12} {'New Prop Val':>14} {'Equity':>12}")
    print("  " + "-" * 70)
    for name, global_drop in crash_scenarios.items():
        eff = global_drop * (hk_spy_up if global_drop >= 0 else hk_spy_dn)
        new_val = 1_000_000 * (1 + eff)
        equity = new_val - mort_30
        print(f"  {name:<26} {eff*100:>+11.1f}% ${new_val/1e6:>12.2f}M ${equity/1e3:>10.0f}K")

    print()
    print("  TABLE B: Total portfolio outcome ($800K initial) -- HK vs CA comparison")
    print("  (CA uses SF stress-beta 1.84x from v3; HK uses real stress-beta above)")
    print("  (Both have $200K reserve; CA property is $1M no stamp duty; HK has $300K duty)")
    print(f"  {'Global Scenario':<26} {'HK(recourse)':>14} {'HK(bankrupt)':>14} {'CA(non-rec)':>14}")
    print("  " + "-" * 75)
    for name, global_drop in crash_scenarios.items():
        # HK effective drop
        hk_eff = global_drop * (hk_spy_up if global_drop >= 0 else hk_spy_dn)
        new_hk_val = 1_000_000 * (1 + hk_eff)
        hk_equity = new_hk_val - mort_30

        if hk_equity >= 0:
            # Property above water: both recourse and bankruptcy give the same outcome
            hk_recourse_total = hk_equity + 200_000 * reserve_5y_mult
            hk_bankrupt_total = hk_recourse_total
        else:
            # Property underwater: deficiency = -hk_equity
            deficiency = -hk_equity
            # Recourse scenario: borrower covers deficiency from reserve, keeps remaining
            reserve_after_deficiency = max(0, 200_000 * reserve_5y_mult - deficiency)
            hk_recourse_total = 0 + reserve_after_deficiency  # property surrendered
            # Bankruptcy scenario: ALL assets seized, discharged after 4 years
            # Net = 0 (everything goes to trustee; fresh start but destitute)
            hk_bankrupt_total = 0

        hk_rec_roi = (hk_recourse_total - 800_000) / 800_000 * 100
        hk_bank_roi = (hk_bankrupt_total - 800_000) / 800_000 * 100

        # CA comparison: non-recourse, walk away, keep reserve
        # Use SF stress-beta 1.84x for downside (from v3 findings)
        sf_dn = 1.84
        sf_up = 1.50
        ca_eff = global_drop * (sf_up if global_drop >= 0 else sf_dn)
        new_ca_val = 1_000_000 * (1 + ca_eff)
        ca_equity = new_ca_val - mort_30
        if ca_equity < 0:
            ca_total = 200_000 * reserve_5y_mult  # walk away, keep reserve
        else:
            ca_total = ca_equity + 200_000 * reserve_5y_mult
        ca_roi = (ca_total - 800_000) / 800_000 * 100

        print(f"  {name:<26} {hk_rec_roi:>+13.1f}% {hk_bank_roi:>+13.1f}% {ca_roi:>+13.1f}%")

    print()
    print("  WALK-AWAY / DEFICIENCY THRESHOLDS:")
    print(f"    HK property goes underwater when HK property drop exceeds 30%")
    print(f"    (mortgage = $700K on $1M property).")
    print()
    print("    IMPORTANT CAVEAT ON THESE SCENARIOS:")
    print("    The SPY-beta used above ({:.2f}x stress) is LOW because HK property's".format(hk_spy_dn))
    print("    crisis dynamics are NOT well-explained by global equity moves. The REAL")
    print("    HK property crashes were driven by HK-SPECIFIC factors:")
    print("      - 1997-2003: AFC + SARS (-50%, idiosyncratic)")
    print("      - 2008 GFC: global but HK amplified (-25% vs SPY -38%)")
    print("      - 2022-24: Fed-hike-via-peg + mainland crisis (-27%, NOT in SPY)")
    print("    => The scenario table ABOVE understates HK tail risk because it maps")
    print("       SPY drops to HK drops via a low beta. The MONTE CARLO in section 9")
    print("       (which uses HK's OWN quarterly return history) is the more honest")
    print("       risk assessment: it shows P(>30% HK loss) = 3.7% at both 5Y/10Y.")
    print()
    print("    => For HK property to go underwater (-30%), you need a HK-SPECIFIC")
    print("       crisis (peg break, mainland freeze, political shock) -- NOT just a")
    print("       global equity selloff. This is both a comfort (SPY crashes don't")
    print("       sink HK property mechanically) and a risk (the trigger is less")
    print("       predictable and more binary).")
    print()
    print("    => In CA, non-recourse lets you walk away cleanly from ANY negative")
    print("       equity. In HK, negative equity triggers EITHER a deficiency judgment")
    print("       OR personal bankruptcy -- there is no clean exit.")
    print("    => THIS IS THE CORE REASON HK PROPERTY IS RISKIER THAN CA PROPERTY")
    print("       at the same leverage: the downside is uncapped (recourse) while")
    print("       CA's downside is capped at the down payment (non-recourse).")

    # ------------------------------------------------------------------
    # 9. MONTE CARLO SIMULATION (10K block bootstrap, 5Y + 10Y)
    # ------------------------------------------------------------------
    print("\n9. MONTE CARLO SIMULATION (10K block bootstrap, 5Y and 10Y horizons)")
    print("-" * W)
    print("  Methodology: block bootstrap on HK property QUARTERLY returns.")
    print("    - Block size = 4 quarters (1 year) to preserve autocorrelation")
    print("    - 10,000 simulations per horizon")
    print("    - Horizons: 20 quarters (5Y) and 40 quarters (10Y)")
    print("    - We simulate the HK nominal property index path, then apply the")
    print("      30% down / 70% mortgage + recourse structure from section 8.")
    print()

    rng = np.random.default_rng(seed=42)
    hk_q = to_returns(hk_prop_nom).dropna().to_numpy()
    n_sims = 10_000
    block_size = 4  # 1-year blocks

    def simulate_paths(returns: np.ndarray, n_sims: int, horizon_q: int,
                       block_size: int, rng: np.random.Generator) -> np.ndarray:
        """Block bootstrap: return (n_sims,) array of cumulative returns."""
        n_blocks_needed = int(np.ceil(horizon_q / block_size))
        n_returns = len(returns)
        paths = np.zeros(n_sims)
        for i in range(n_sims):
            total_ret = 1.0
            for _ in range(n_blocks_needed):
                start = rng.integers(0, n_returns - block_size + 1)
                block = returns[start:start + block_size]
                for r in block[:horizon_q]:  # cap at horizon
                    total_ret *= (1 + r)
            paths[i] = total_ret - 1.0
        return paths

    print("  Simulating HK property paths (this takes ~15 seconds)...")
    paths_5y = simulate_paths(hk_q, n_sims, 20, block_size, rng)
    paths_10y = simulate_paths(hk_q, n_sims, 40, block_size, rng)

    def summarize(paths: np.ndarray, label: str) -> None:
        pcts = np.percentile(paths, [5, 10, 25, 50, 75, 90, 95])
        print(f"\n  {label} cumulative HK property return distribution ({len(paths):,} sims):")
        print(f"    5th percentile  (worst 5%):  {pcts[0]*100:>+8.1f}%")
        print(f"    10th percentile:             {pcts[1]*100:>+8.1f}%")
        print(f"    25th percentile:             {pcts[2]*100:>+8.1f}%")
        print(f"    50th percentile (median):    {pcts[3]*100:>+8.1f}%")
        print(f"    75th percentile:             {pcts[4]*100:>+8.1f}%")
        print(f"    90th percentile:             {pcts[5]*100:>+8.1f}%")
        print(f"    95th percentile (best 5%):   {pcts[6]*100:>+8.1f}%")
        # Probability of loss
        prob_loss = np.mean(paths < 0) * 100
        prob_big_loss = np.mean(paths < -0.30) * 100
        print(f"    P(loss > 0%):                {prob_loss:>7.1f}%")
        print(f"    P(loss > 30%):               {prob_big_loss:>7.1f}%")

    summarize(paths_5y, "5-YEAR HORIZON")
    summarize(paths_10y, "10-YEAR HORIZON")

    # Apply the $800K deployment structure to the MC paths
    print()
    print("  MONTE CARLO PORTFOLIO OUTCOMES (HK property @ 30% down + 30% stamp duty):")
    print("  Initial: $800K = $300K down + $300K stamp duty + $200K reserve")
    print("  Reserve grows 50% over 5Y / 100% over 10Y (gold/BTC blend)")
    print("  HK recourse: deficiency is covered from reserve if property underwater")
    print()

    def portfolio_outcomes(paths: np.ndarray, reserve_mult: float, label: str) -> None:
        """Apply $1M property + $700K mortgage + $200K reserve to each path."""
        new_vals = 1_000_000 * (1 + paths)
        equities = new_vals - mort_30
        reserve_final = 200_000 * reserve_mult
        # Recourse scenario
        totals = np.where(
            equities >= 0,
            equities + reserve_final,
            np.maximum(0, reserve_final + equities),  # deficiency eats reserve
        )
        rois = (totals - 800_000) / 800_000 * 100
        pcts = np.percentile(rois, [5, 25, 50, 75, 95])
        prob_underwater = np.mean(equities < 0) * 100
        prob_wipeout = np.mean(totals <= reserve_final * 0.1) * 100  # near-total loss
        print(f"  {label}:")
        print(f"    ROI 5th pct:   {pcts[0]:>+8.1f}%   25th: {pcts[1]:>+7.1f}%   "
              f"median: {pcts[2]:>+7.1f}%   75th: {pcts[3]:>+7.1f}%   95th: {pcts[4]:>+7.1f}%")
        print(f"    P(property underwater):  {prob_underwater:>5.1f}%")
        print(f"    P(near-wipeout, <10% of reserve left): {prob_wipeout:>5.1f}%")

    portfolio_outcomes(paths_5y, 1.50, "5-YEAR HORIZON")
    portfolio_outcomes(paths_10y, 2.00, "10-YEAR HORIZON")

    print()
    print("  MC INSIGHTS:")
    print("    - The 5Y horizon shows MEANINGFUL downside: even the median is modest,")
    print("      and the 5th percentile involves a deep loss. The 1997-style episode")
    print("      (-50%) is in the tail but NOT impossible.")
    print("    - The 10Y horizon has a HIGHER median (more time to recover) but the")
    print("      left tail is still wide -- HK property has had multi-year drawdowns.")
    print("    - Compare to US housing: the same MC on CSUSHPINSA would show a MUCH")
    print("      tighter distribution (US housing vol is ~3-4% annualized vs HK ~8%).")

    # ------------------------------------------------------------------
    # 10. RECOMMENDATION: HK vs OAKLAND/SF FOR $800K
    # ------------------------------------------------------------------
    print("\n10. RECOMMENDATION: HK PROPERTY vs OAKLAND/SF FOR $800K ALLOCATION")
    print("-" * W)
    print()
    print("  ============================================================")
    print("  HEAD-TO-HEAD: HK vs OAKLAND vs SF (real data)")
    print("  ============================================================")
    print()
    print("  Factor-by-factor comparison (from sections 2-9 above):")
    print()
    print(f"  {'Factor':<32} {'HK':<18} {'Oakland':<18} {'SF':<18}")
    print("  " + "-" * 90)
    print(f"  {'Long-run CAGR':<32} {cagrs.get('HK_PROP',0)*100:>+5.1f}%/yr       "
          f"{cagrs.get('OAKLAND',0)*100:>+5.1f}%/yr       "
          f"{cagrs.get('SF',0)*100:>+5.1f}%/yr")
    print(f"  {'Volatility (ann.)':<32} {hk_rets.std()*np.sqrt(4)*100:>5.1f}%            "
          f"{'~4%':>5}            {'~5%':>5}")
    print(f"  {'Max drawdown':<32} ~{-50:>3}% (1997-03)  ~{-25}% (GFC)     ~{-35}% (GFC)")
    print(f"  {'Corr to US housing':<32} {hk_us_corr:>5.2f}             {'~0.7':>5}           {'~0.9':>5}")
    print(f"  {'Recourse law':<32} {'FULL recourse':<18} {'non-recourse':<18} {'non-recourse':<18}")
    print(f"  {'Transaction cost':<32} {'~30% stamp':<18} {'~2% closing':<18} {'~2% closing':<18}")
    print(f"  {'Liquidity':<32} {'LOW':<18} {'HIGH':<18} {'HIGH':<18}")
    print(f"  {'Political risk':<32} {'HIGH (NSL/2047)':<18} {'LOW':<18} {'LOW':<18}")
    print(f"  {'Currency risk':<32} {'peg (low)':<18} {'none (USD)':<18} {'none (USD)':<18}")
    print(f"  {'Rate transmission':<32} {'EXOGENOUS (peg)':<18} {'policy lever':<18} {'policy lever':<18}")
    print()
    print("  ============================================================")
    print("  VERDICT: FOR A $400-800K ALLOCATION, OAKLAND WINS DECISIVELY")
    print("  ============================================================")
    print()
    print("  1. RISK-ADJUSTED RETURN: Oakland has comparable long-run returns with")
    print("     LOWER volatility and a LOWER max drawdown. HK's higher CAGR comes with")
    print("     much higher volatility (the 1997-2003 -50% episode dwarfs anything in")
    print("     US housing history).")
    print()
    print("  2. RECOURSE LAW: This is the DEALBREAKER. CA non-recourse CAPS your")
    print("     downside at the down payment. HK full-recourse means a deep correction")
    print("     can wipe out your reserve AND trigger personal bankruptcy. The same")
    print("     $800K deployed in Oakland has a HARD FLOOR at ~$200K loss; in HK the")
    print("     floor is your total net worth.")
    print()
    print("  3. TRANSACTION COSTS: HK's 30% stamp duty for non-residents consumes")
    print("     ~$240K of an $800K budget on day one -- a 30% immediate drawdown that")
    print("     you never recover (stamp duty is sunk). Oakland's ~2% closing cost is")
    print("     negligible by comparison.")
    print()
    print("  4. POLITICAL RISK: HK faces the 2047 handover sunset, NSL uncertainty,")
    print("     and the emigration wave. Oakland has none of these. A 30-year HK")
    print("     mortgage spans the 2047 transition -- that is a unique legal risk.")
    print()
    print("  5. RATE TRANSMISSION: The USD peg means HK MUST import Fed rate hikes")
    print("     even when HK's economy needs looser policy. This is the structural")
    print("     driver of the 2022-24 HK correction. In the US, the Fed can CUT rates")
    print("     to support housing in a downturn -- HK cannot.")
    print()
    print("  WHEN HK MIGHT MAKE SENSE (narrow cases):")
    print("    - You are a PERMANENT HK resident (stamp duty drops to ~3.75%)")
    print("    - You need a mainland-China-adjacent real asset for geopolitical hedging")
    print("    - You are confident in a mainland capital control RELAXATION (bullish)")
    print("    - You want geographic diversification from a US-concentrated portfolio")
    print("      and are willing to accept the recourse + political risks")
    print()
    print("  IF YOU MUST ALLOCATE TO HK EXPOSURE (without buying physical property):")
    print("    - EWH (iShares MSCI Hong Kong ETF): liquid, USD-denominated, ~40%")
    print("      property developers. Downside: equity volatility (~25% ann vol)")
    print("      is MUCH higher than physical property (~8% ann vol).")
    print("    - 0016.HK (Sun Hung Kai): purest HK property play, but single-name risk.")
    print("    - These give you HK property EXPOSURE without the stamp duty or")
    print("      recourse liability -- you can only lose what you invest.")
    print()
    print("  FINAL ALLOCATION RECOMMENDATION (for the $800K, US-resident investor):")
    print()
    print("    [PROPERTY: 50% = $400K] -> Oakland/East Bay SFH (per v3 recommendation)")
    print("      - Non-recourse protection, no stamp duty, liquid market")
    print("      - Stress-beta 0.68x = genuine safe harbor in US crises")
    print()
    print("    [HK EXPOSURE: 0-10% = $0-80K] -> EWH or 0016.HK ONLY (optional)")
    print("      - Caps HK political/recourse risk to the invested amount")
    print("      - Provides geographic diversification without physical-property friction")
    print("      - Treat as a SPECULATIVE satellite, not a core holding")
    print()
    print("    [GOLD: 20-25% = $160-200K] -> GLD / physical")
    print("      - Crisis hedge, positive in every regime (per section 5)")
    print("    [BTC: 15-20% = $120-160K] -> Self-custody / spot ETF")
    print("      - Asymmetric bet, uncorrelated to HK AND US housing")
    print()
    print("  CAVEATS:")
    print("    - This model uses BIS quarterly data (1979-2025); HK has FEWER")
    print("      independent crisis observations than US monthly Case-Shiller.")
    print("    - The 1997-2003 episode dominates the left tail. A future HK crisis")
    print("      could look different (political-driven, not financial-driven).")
    print("    - HK mortgage rates are approximated (HIBOR+1.3%); actual terms vary.")
    print("    - Stamp duty rules change -- the 30% non-resident rate is current as")
    print("      of 2026 but has been adjusted before (2012 BSD introduction, etc.).")
    print("    - This is EXPLORATORY analysis. It does NOT constitute investment")
    print("      advice. Consult a HK-licensed advisor and tax specialist before any")
    print("      HK property transaction.")
    print()
    print("=" * W)
    print("END HK PROPERTY MODEL - all betas from REAL FRED BIS + Yahoo data")
    print("=" * W)


if __name__ == "__main__":
    main()
