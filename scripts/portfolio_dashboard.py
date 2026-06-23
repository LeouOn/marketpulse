"""
Portfolio Dashboard
Tracks $800K allocation across multiple asset classes.

Closes the gap between the recommended allocation plan (50% property when ready /
diversified metals basket / oil hedge / BTC / cash) and actual deployment.
Use this to see drift, rebalancing signals, P&L, and portfolio risk.

Modes:
  python scripts/portfolio_dashboard.py
      Static mode. Uses default recommended allocation if no config exists.
      If reports/portfolio/config.json exists (from a prior --interactive run),
      loads the user's actual positions and computes real drift / P&L.

  python scripts/portfolio_dashboard.py --interactive
      Interactive setup. Asks for current positions ($ / % / skip) and saves
      answers to reports/portfolio/config.json for future static runs.

  python scripts/portfolio_dashboard.py --reset
      Delete the saved config and start fresh on next --interactive run.

Output:
  - Console summary (quick check)
  - reports/portfolio/snapshot_YYYY-MM-DD.md (markdown report for record-keeping)
  - reports/portfolio/config.json (only when --interactive used)

Data sources:
  - Live prices via yfinance (cached in-memory for the duration of the run)
  - Historical daily series from data/yahoo_cache/{ticker}.parquet
  - Falls back to yfinance history if a ticker is not cached locally
"""
import sys
import os
import json
import argparse
import warnings
from pathlib import Path
from datetime import datetime, date

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import numpy as np
import yfinance as yf

warnings.filterwarnings("ignore")

# ============================================================================
# CONFIGURATION
# ============================================================================

TOTAL_CASH = 800_000

# Default recommended allocation (from earlier $800K allocation work).
# target_pct must sum to 1.0 across all *deployed* assets (property deferred).
# Property is kept in the table at 0% so the dashboard can flag when to deploy.
DEFAULT_ALLOCATION = {
    "Property (Oakland)": {"type": "real_estate", "target_pct": 0.00,   "ticker": None,      "note": "Deferred - lives with parents"},
    "Gold (GLD)":         {"type": "etf",         "target_pct": 0.11,   "ticker": "GLD"},
    "Silver (SLV)":       {"type": "etf",         "target_pct": 0.075,  "ticker": "SLV"},
    "Copper (HG=F)":      {"type": "commodity",   "target_pct": 0.0375, "ticker": "HG=F"},
    "Platinum (PPLT)":    {"type": "etf",         "target_pct": 0.025,  "ticker": "PPLT"},
    "Bitcoin (BTC-USD)":  {"type": "crypto",      "target_pct": 0.15,   "ticker": "BTC-USD"},
    "Broad Equity (SPY)": {"type": "etf",         "target_pct": 0.25,   "ticker": "SPY"},
    "Oil Hedge (CL=F)":   {"type": "commodity",   "target_pct": 0.10,   "ticker": "CL=F"},
    "Cash/T-Bills (BIL)": {"type": "bonds",       "target_pct": 0.25,   "ticker": "BIL"},
}

# Rebalancing tolerance in percentage points of allocation.
# drift > +3pp  -> TRIM
# drift < -3pp  -> ADD
# otherwise     -> HOLD
DRIFT_TOLERANCE = 0.03

# Risk guardrails.
CASH_MIN_PCT, CASH_MAX_PCT = 0.10, 0.25     # dry powder band
SINGLE_POSITION_MAX_PCT = 0.40              # concentration ceiling

# Asset-class default betas to SPY (used when data is too short to regress).
ASSET_CLASS_BETAS = {
    "real_estate": 0.30,
    "etf":         0.90,
    "commodity":   0.35,
    "crypto":      1.20,
    "bonds":       0.00,
}

# Asset-class default annualized volatility (used when history is short).
ASSET_CLASS_VOLS = {
    "real_estate": 0.06,
    "etf":         0.18,
    "commodity":   0.30,
    "crypto":      0.65,
    "bonds":       0.005,
}

# Paths
PROJECT_ROOT   = Path(__file__).resolve().parent.parent
YAHOO_CACHE_DIR = PROJECT_ROOT / "data" / "yahoo_cache"
REPORT_DIR     = PROJECT_ROOT / "reports" / "portfolio"
CONFIG_PATH    = REPORT_DIR / "config.json"


# ============================================================================
# PRICE FETCHING (live via yfinance, history via parquet cache)
# ============================================================================

# In-run cache so we never hit the network twice for the same ticker.
_PRICE_CACHE: dict = {}
_HISTORY_CACHE: dict = {}


def load_cached_history(ticker):
    """Load daily close history from data/yahoo_cache/{ticker}.parquet.

    Returns a sorted pd.Series named after the ticker, or None if unavailable.
    """
    if not ticker:
        return None
    path = YAHOO_CACHE_DIR / f"{ticker}.parquet"
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path)
        if "ts" in df.columns:
            df["ts"] = pd.to_datetime(df["ts"], utc=True)
            # Normalize to tz-naive so this composes cleanly with yfinance data.
            df["ts"] = df["ts"].dt.tz_convert("UTC").dt.tz_localize(None)
            df = df.set_index("ts")
        if "close" not in df.columns:
            return None
        s = df["close"].dropna().sort_index()
        s.name = ticker
        return s
    except Exception:
        return None


def fetch_latest_price(ticker):
    """Return (latest_price, week_ago_price, source) for a ticker.

    Tries yfinance live first; falls back to the most recent cached value
    in data/yahoo_cache/ if the live fetch fails or the ticker is delisted.
    """
    if not ticker:
        return None, None, "no-ticker"
    if ticker in _PRICE_CACHE:
        return _PRICE_CACHE[ticker]

    # 1) Live via yfinance
    try:
        df = yf.download(ticker, period="8d", progress=False, auto_adjust=False)
        if df is not None and len(df) > 0:
            close = df["Close"]
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            close = close.dropna()
            if len(close) > 0:
                latest = float(close.iloc[-1])
                week_ago = float(close.iloc[0]) if len(close) >= 5 else None
                result = (latest, week_ago, "yahoo:live")
                _PRICE_CACHE[ticker] = result
                return result
    except Exception:
        pass

    # 2) Fall back to local parquet cache
    s = load_cached_history(ticker)
    if s is not None and len(s) > 0:
        latest = float(s.iloc[-1])
        # week_ago = ~5 trading days back if available
        week_ago = float(s.iloc[-6]) if len(s) >= 6 else None
        result = (latest, week_ago, "yahoo:cache")
        _PRICE_CACHE[ticker] = result
        return result

    result = (None, None, "unavailable")
    _PRICE_CACHE[ticker] = result
    return result


def fetch_history_for_analysis(ticker, days=252):
    """Return ~N days of daily closes for vol/correlation/beta work.

    Prefers fresh yfinance data so that multiple tickers align on the same
    recent dates (critical for correlation). Falls back to the local parquet
    cache only if the live fetch fails. Results are memoized in-run.
    """
    if not ticker:
        return None
    if ticker in _HISTORY_CACHE:
        cached = _HISTORY_CACHE[ticker]
        return cached.tail(days) if cached is not None else None

    # 1) Live via yfinance (fresh, date-aligned across tickers)
    try:
        df = yf.download(ticker, period="1y", progress=False, auto_adjust=False)
        if df is not None and len(df) > 0:
            close = df["Close"]
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            close = close.dropna()
            if getattr(close.index, "tz", None) is not None:
                close.index = close.index.tz_convert("UTC").tz_localize(None)
            if len(close) >= 30:
                close.name = ticker
                _HISTORY_CACHE[ticker] = close
                return close.tail(days)
    except Exception:
        pass

    # 2) Fall back to local parquet cache (may be stale, but better than nothing)
    s = load_cached_history(ticker)
    if s is not None and len(s) >= 30:
        _HISTORY_CACHE[ticker] = s
        return s.tail(days)

    _HISTORY_CACHE[ticker] = None
    return None


# ============================================================================
# CONFIG LOAD / SAVE
# ============================================================================

def load_config():
    """Load user position config. Returns None if not present.

    Uses utf-8-sig to transparently strip a BOM if present (configs edited
    in Windows Notepad / via PowerShell Set-Content -Encoding UTF8 carry one).
    """
    if not CONFIG_PATH.exists():
        return None
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
            cfg = json.load(f)
        # Basic shape check
        if "positions" not in cfg:
            return None
        return cfg
    except Exception as e:
        print(f"  WARNING: could not read config ({e}); using defaults.")
        return None


def save_config(cfg):
    """Persist user position config to reports/portfolio/config.json."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    cfg["updated"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    return CONFIG_PATH


def reset_config():
    """Delete the saved config."""
    if CONFIG_PATH.exists():
        CONFIG_PATH.unlink()
        print(f"  Removed existing config: {CONFIG_PATH}")
    else:
        print("  No existing config to remove.")


# ============================================================================
# INTERACTIVE MODE
# ============================================================================

def _parse_amount(raw, total_capital):
    """Parse a user input like '88000', '$88000', '11%', '0.11', 'skip'.

    Returns dict: {"value": float|None, "cost_basis": float|None,
                   "acquisition_date": str|None}
    Returns None for the whole record if user types 'skip' / blank.
    """
    raw = (raw or "").strip()
    if raw == "" or raw.lower() in ("skip", "s", "-"):
        return None

    rec = {"value": None, "cost_basis": None, "acquisition_date": None}

    # Percentage?
    if raw.endswith("%"):
        try:
            pct = float(raw[:-1].lstrip("$").strip()) / 100.0
            rec["value"] = pct * total_capital
        except ValueError:
            print(f"    Could not parse percentage '{raw}'. Treating as skip.")
            return None
    else:
        try:
            num = float(raw.lstrip("$").replace(",", ""))
            # If number looks like a fraction (between 0 and 1), treat as pct.
            if 0.0 < num < 1.0:
                rec["value"] = num * total_capital
            else:
                rec["value"] = num
        except ValueError:
            print(f"    Could not parse '{raw}'. Treating as skip.")
            return None
    return rec


def run_interactive_setup(allocation, total_capital):
    """Ask the user for current positions on each asset.

    Saves a config dict to reports/portfolio/config.json.
    """
    print("=" * 78)
    print("PORTFOLIO DASHBOARD - INTERACTIVE SETUP")
    print("=" * 78)
    print(f"\nTotal capital to track: ${total_capital:,.0f}")
    print(f"\nTarget allocation (recommended plan):\n")
    print(f"  {'Asset':<24} {'Target %':>10} {'Target $':>14}  Type")
    print("  " + "-" * 70)
    for name, spec in allocation.items():
        tgt_pct = spec["target_pct"]
        tgt_dollars = tgt_pct * total_capital
        print(f"  {name:<24} {tgt_pct*100:>9.2f}% ${tgt_dollars:>13,.0f}  {spec['type']}")
    print()
    print("For each asset below, enter one of:")
    print("  - Dollar amount:     88000   or   $88000")
    print("  - Percent of total:  11%     or   0.11")
    print("  - skip / blank:      nothing deployed in this asset yet")
    print()

    positions = {}
    for name, spec in allocation.items():
        note = spec.get("note", "")
        prompt_extra = f"  [{note}]" if note else ""
        raw = input(f"How much in {name}?{prompt_extra} ").strip()
        rec = _parse_amount(raw, total_capital)
        if rec is None:
            print(f"    -> skipped (0 currently)")
            continue

        # Optionally collect cost basis for P&L tracking
        cb_raw = input(f"   Cost basis for {name}? (optional, blank=none) ").strip()
        if cb_raw:
            try:
                rec["cost_basis"] = float(cb_raw.lstrip("$").replace(",", ""))
            except ValueError:
                print("    -> ignoring unparseable cost basis")

        acq_raw = input(f"   Acquisition date for {name}? (YYYY-MM-DD, blank=none) ").strip()
        if acq_raw:
            try:
                # validate
                datetime.strptime(acq_raw, "%Y-%m-%d")
                rec["acquisition_date"] = acq_raw
            except ValueError:
                print("    -> ignoring unparseable date")

        positions[name] = rec
        print(f"    -> recorded ${rec['value']:,.0f}")
        print()

    cfg = {
        "total_capital": total_capital,
        "positions": positions,
    }
    path = save_config(cfg)
    print(f"\nSaved config to: {path}")
    print(f"You can now run 'python scripts/portfolio_dashboard.py' (no flags) to use it.")
    return cfg


# ============================================================================
# PORTFOLIO BUILDING
# ============================================================================

def build_portfolio(allocation, config, total_capital):
    """Build a per-asset analysis table.

    Columns:
      asset, type, ticker, target_pct, target_value,
      current_value, current_pct, drift, action,
      latest_price, week_ago_price, price_source, price_wow,
      cost_basis, pnl_dollars, pnl_pct, annualized_return,
      implied_shares

    If config is None (static mode) we treat current == target so the user
    can see what the plan looks like at today's prices.
    """
    rows = []
    cfg_positions = (config or {}).get("positions", {}) if config else {}

    for name, spec in allocation.items():
        tgt_pct = float(spec["target_pct"])
        tgt_value = tgt_pct * total_capital
        ticker = spec.get("ticker")
        atype = spec.get("type", "unknown")
        note = spec.get("note", "")

        # Current position from config (if any)
        pos = cfg_positions.get(name)
        if pos is not None and pos.get("value") is not None:
            current_value = float(pos["value"])
            cost_basis = pos.get("cost_basis")
            acq = pos.get("acquisition_date")
            source_kind = "config"
        else:
            # Static mode: assume deployed at target (only for deployed assets).
            # Skipped assets / 0% target -> current 0.
            if config is None and tgt_pct > 0:
                current_value = tgt_value
                cost_basis = None
                acq = None
                source_kind = "target-assumed"
            else:
                current_value = 0.0
                cost_basis = None
                acq = None
                source_kind = "not-deployed"

        # Price fetch (best-effort)
        latest_price, week_ago_price, price_source = fetch_latest_price(ticker)
        price_wow = None
        if latest_price and week_ago_price and week_ago_price > 0:
            price_wow = (latest_price / week_ago_price - 1.0) * 100.0

        # Implied shares (only meaningful for marketable assets)
        implied_shares = None
        if latest_price and latest_price > 0:
            implied_shares = current_value / latest_price

        rows.append({
            "asset": name,
            "type": atype,
            "ticker": ticker or "",
            "note": note,
            "target_pct": tgt_pct,
            "target_value": tgt_value,
            "current_value": current_value,
            "cost_basis": cost_basis,
            "acquisition_date": acq,
            "latest_price": latest_price,
            "week_ago_price": week_ago_price,
            "price_source": price_source,
            "price_wow": price_wow,
            "implied_shares": implied_shares,
            "source_kind": source_kind,
        })

    df = pd.DataFrame(rows)

    # Compute current % relative to total CURRENT deployed value.
    # Note: we anchor on total_capital (plan), not deployed value, so that an
    # under-deployed portfolio shows up as < 100% deployed (useful signal).
    df["current_pct"] = df["current_value"] / total_capital
    df["drift"] = df["current_pct"] - df["target_pct"]
    df["action"] = df["drift"].apply(_action_from_drift)

    # P&L where cost basis known (pandas stores None as NaN in numeric cols,
    # so we gate with pd.notna to avoid NaN arithmetic leaking into output).
    df["pnl_dollars"] = df.apply(
        lambda r: (r["current_value"] - r["cost_basis"])
                  if pd.notna(r["cost_basis"]) and r["cost_basis"] > 0
                     and pd.notna(r["current_value"])
                  else None,
        axis=1,
    )
    df["pnl_pct"] = df.apply(
        lambda r: (r["pnl_dollars"] / r["cost_basis"] * 100.0)
                  if pd.notna(r["cost_basis"]) and r["cost_basis"] > 0
                     and pd.notna(r["pnl_dollars"])
                  else None,
        axis=1,
    )
    df["annualized_return"] = df.apply(
        lambda r: _annualized_return(r["current_value"], r["cost_basis"], r["acquisition_date"]),
        axis=1,
    )

    return df


def _action_from_drift(drift):
    """Map a drift (in pp) to a rebalancing action label."""
    if drift > DRIFT_TOLERANCE:
        return "TRIM"
    if drift < -DRIFT_TOLERANCE:
        return "ADD"
    return "HOLD"


def _annualized_return(current_value, cost_basis, acq_date):
    """Annualized % return if cost basis + acquisition date provided."""
    if pd.isna(cost_basis) or not cost_basis or cost_basis <= 0:
        return None
    if pd.isna(current_value) or not current_value:
        return None
    if not acq_date:
        return None
    try:
        d = datetime.strptime(acq_date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    today = date.today()
    years = (today - d).days / 365.25
    if years < 30 / 365.25:
        return None  # too short to annualize meaningfully
    ratio = current_value / cost_basis
    if ratio <= 0:
        return None
    return (ratio ** (1.0 / years) - 1.0) * 100.0


# ============================================================================
# ALLOCATION / DRIFT ANALYSIS
# ============================================================================

def summarize_allocation(df, total_capital):
    """Return a dict of headline allocation numbers."""
    deployed = float(df["current_value"].sum())
    target_deployed = float(df["target_value"].sum())
    by_type = df.groupby("type").agg(
        current=("current_value", "sum"),
        target=("target_value", "sum"),
    )
    return {
        "total_capital": total_capital,
        "deployed": deployed,
        "deployed_pct_of_capital": deployed / total_capital if total_capital else 0.0,
        "target_deployed": target_deployed,
        "cash_undeployed": total_capital - deployed,
        "by_type": by_type,
        "n_actions_trim": int((df["action"] == "TRIM").sum()),
        "n_actions_add": int((df["action"] == "ADD").sum()),
        "n_actions_hold": int((df["action"] == "HOLD").sum()),
    }


# ============================================================================
# PERFORMANCE TRACKING
# ============================================================================

def summarize_performance(df):
    """Compute portfolio-level P&L over positions where cost basis is known."""
    has_cb = df["cost_basis"].notna() & (df["cost_basis"] > 0)
    sub = df[has_cb]
    if sub.empty:
        return {
            "positions_tracked": 0,
            "total_cost_basis": 0.0,
            "total_current_value": 0.0,
            "total_pnl_dollars": 0.0,
            "total_pnl_pct": None,
        }
    total_cb = float(sub["cost_basis"].sum())
    total_cur = float(sub["current_value"].sum())
    pnl = total_cur - total_cb
    return {
        "positions_tracked": int(len(sub)),
        "total_cost_basis": total_cb,
        "total_current_value": total_cur,
        "total_pnl_dollars": pnl,
        "total_pnl_pct": (pnl / total_cb * 100.0) if total_cb else None,
    }


# ============================================================================
# REBALANCING SIGNALS
# ============================================================================

def build_rebalancing_signals(df, total_capital):
    """For each position outside tolerance, compute the $ amount to trim/add
    to return to target."""
    signals = []
    for _, r in df.iterrows():
        target_value = r["target_pct"] * total_capital
        delta = target_value - r["current_value"]    # positive = buy, negative = sell
        action = r["action"]
        if action == "HOLD":
            continue
        # Skip TRIM/ADD noise for positions that are 0% target and 0 deployed.
        if r["target_pct"] == 0 and r["current_value"] == 0:
            continue
        signals.append({
            "asset": r["asset"],
            "action": action,
            "current_pct": r["current_pct"],
            "target_pct": r["target_pct"],
            "drift_pp": r["drift"] * 100.0,
            "current_value": r["current_value"],
            "target_value": target_value,
            "delta_dollars": delta,
        })
    # Sort: biggest absolute drift first
    signals.sort(key=lambda s: abs(s["drift_pp"]), reverse=True)
    return signals


# ============================================================================
# RISK METRICS
# ============================================================================

def compute_risk_metrics(df, total_capital):
    """Compute portfolio beta, volatility, cash check, concentration."""
    # ----- Beta to SPY (weighted) -----
    beta_components = []
    for _, r in df.iterrows():
        if r["current_value"] <= 0:
            continue
        w = r["current_value"] / total_capital
        beta_est = _estimate_beta(r["ticker"], r["type"])
        beta_components.append((r["asset"], w, beta_est))
    portfolio_beta = sum(w * b for _, w, b in beta_components)

    # ----- Volatility (two methods) -----
    # Method A: weighted avg of individual vols (ignores correlations - overestimate)
    vol_components = []
    for _, r in df.iterrows():
        if r["current_value"] <= 0:
            continue
        w = r["current_value"] / total_capital
        vol_est = _estimate_vol(r["ticker"], r["type"])
        vol_components.append((r["asset"], w, vol_est))
    portfolio_vol_weighted = sum(w * v for _, w, v in vol_components)

    # Method B: proper portfolio vol from covariance matrix of available tickers
    portfolio_vol_proper, n_assets_in_cov = _portfolio_vol_from_covariance(df, total_capital)

    # ----- Cash allocation check -----
    cash_row = df[df["type"] == "bonds"]
    cash_value = float(cash_row["current_value"].sum()) if not cash_row.empty else 0.0
    cash_pct = cash_value / total_capital if total_capital else 0.0
    if cash_pct < CASH_MIN_PCT:
        cash_status = f"BELOW MIN ({CASH_MIN_PCT*100:.0f}%) - low dry powder"
    elif cash_pct > CASH_MAX_PCT:
        cash_status = f"ABOVE MAX ({CASH_MAX_PCT*100:.0f}%) - excess cash drag"
    else:
        cash_status = f"OK (within {CASH_MIN_PCT*100:.0f}-{CASH_MAX_PCT*100:.0f}%)"

    # ----- Concentration check -----
    concentration = df[df["current_value"] > 0].copy()
    concentration["pct"] = concentration["current_value"] / total_capital
    concentration = concentration.sort_values("pct", ascending=False)
    biggest = concentration.iloc[0] if not concentration.empty else None
    concentration_breach = biggest is not None and biggest["pct"] > SINGLE_POSITION_MAX_PCT

    return {
        "portfolio_beta": portfolio_beta,
        "beta_components": beta_components,
        "portfolio_vol_weighted": portfolio_vol_weighted,
        "portfolio_vol_proper": portfolio_vol_proper,
        "cov_n_assets": n_assets_in_cov,
        "cash_value": cash_value,
        "cash_pct": cash_pct,
        "cash_status": cash_status,
        "biggest_position": {
            "asset": biggest["asset"],
            "pct": float(biggest["pct"]),
        } if biggest is not None else None,
        "concentration_breach": concentration_breach,
        "concentration_threshold": SINGLE_POSITION_MAX_PCT,
    }


def _estimate_beta(ticker, atype):
    """Estimate beta to SPY. Regress on cached history if available;
    else fall back to asset-class default."""
    if not ticker or ticker == "SPY":
        return 1.0
    spy = fetch_history_for_analysis("SPY", days=252)
    asset = fetch_history_for_analysis(ticker, days=252)
    if spy is None or asset is None:
        return ASSET_CLASS_BETAS.get(atype, 0.5)
    joined = pd.concat([spy, asset], axis=1, join="inner").dropna()
    if len(joined) < 60:
        return ASSET_CLASS_BETAS.get(atype, 0.5)
    spy_ret = joined.iloc[:, 0].pct_change().dropna()
    asset_ret = joined.iloc[:, 1].pct_change().dropna()
    common = pd.concat([spy_ret, asset_ret], axis=1, join="inner").dropna()
    if len(common) < 60 or common.iloc[:, 0].std() == 0:
        return ASSET_CLASS_BETAS.get(atype, 0.5)
    cov = np.cov(common.iloc[:, 0], common.iloc[:, 1])
    var_spy = cov[0, 0]
    if var_spy == 0:
        return ASSET_CLASS_BETAS.get(atype, 0.5)
    beta = cov[1, 0] / var_spy
    # Guard against absurd estimates from low-variance series
    beta = float(np.clip(beta, -2.0, 3.0))
    return beta


def _estimate_vol(ticker, atype):
    """Estimate annualized volatility from cached daily returns, with
    asset-class fallback."""
    if not ticker:
        return ASSET_CLASS_VOLS.get(atype, 0.20)
    s = fetch_history_for_analysis(ticker, days=252)
    if s is None or len(s) < 30:
        return ASSET_CLASS_VOLS.get(atype, 0.20)
    rets = s.pct_change().dropna()
    if len(rets) < 30:
        return ASSET_CLASS_VOLS.get(atype, 0.20)
    vol = float(rets.std() * np.sqrt(252))
    return vol


def _portfolio_vol_from_covariance(df, total_capital):
    """Proper portfolio vol: sqrt(w' * Cov * w).

    Only includes positions with available price history. If correlations
    can't be computed for the majority of the book, returns (None, count).
    """
    series = {}
    weights = {}
    for _, r in df.iterrows():
        if r["current_value"] <= 0 or not r["ticker"]:
            continue
        s = fetch_history_for_analysis(r["ticker"], days=252)
        if s is None or len(s) < 60:
            continue
        series[r["ticker"]] = s
        weights[r["ticker"]] = r["current_value"] / total_capital

    if len(series) < 2:
        return None, len(series)

    # Align and compute returns
    panel = pd.DataFrame(series).dropna()
    if len(panel) < 60:
        return None, len(series)
    rets = panel.pct_change().dropna()
    if len(rets) < 60:
        return None, len(series)

    cov = rets.cov() * 252  # annualized covariance
    w = pd.Series(weights).reindex(cov.index).fillna(0.0).values
    var = float(w @ cov.values @ w)
    if var < 0:
        return None, len(series)
    return float(np.sqrt(var)), len(series)


# ============================================================================
# CORRELATION MATRIX
# ============================================================================

def compute_correlation_matrix(df):
    """Build a correlation matrix of daily returns across deployed tickers."""
    series = {}
    for _, r in df.iterrows():
        if r["current_value"] <= 0 or not r["ticker"]:
            continue
        s = fetch_history_for_analysis(r["ticker"], days=252)
        if s is None or len(s) < 60:
            continue
        series[r["ticker"]] = s
    if len(series) < 2:
        return None, None
    panel = pd.DataFrame(series).dropna()
    if len(panel) < 60:
        return None, None
    rets = panel.pct_change().dropna()
    corr = rets.corr()
    return corr, rets


# ============================================================================
# CONSOLE RENDERING
# ============================================================================

def _is_blank(x):
    """True for None / NaN / missing."""
    if x is None:
        return True
    try:
        return bool(pd.isna(x))
    except (TypeError, ValueError):
        return False


def _fmt_money(x):
    if _is_blank(x):
        return "n/a"
    if x == 0:
        return "$0"
    return f"${x:,.0f}"


def _fmt_pct(x, width=6):
    if _is_blank(x):
        return "n/a".rjust(width)
    return f"{x*100:>+.2f}%".rjust(width) if x < 1 else f"{x*100:>.2f}%".rjust(width)


def _fmt_price(x):
    if _is_blank(x):
        return "n/a"
    if x >= 1000:
        return f"${x:,.2f}"
    return f"${x:.2f}"


def render_console(df, alloc, perf, signals, risk, corr, total_capital, mode):
    """Print the full console summary."""
    today = datetime.now().strftime("%Y-%m-%d")
    P = "=" * 78
    print()
    print(P)
    print(f"PORTFOLIO DASHBOARD - {today}")
    print(P)
    print(f"  Total capital tracked: ${total_capital:,.0f}")
    print(f"  Mode: {mode}")
    deployed = alloc["deployed"]
    print(f"  Deployed: ${deployed:,.0f} ({alloc['deployed_pct_of_capital']*100:.1f}% of capital)")
    cash_undeployed = alloc["cash_undeployed"]
    print(f"  Cash / un-deployed: ${cash_undeployed:,.0f}")
    if perf["positions_tracked"] > 0:
        pnl = perf["total_pnl_dollars"]
        pnl_pct = perf["total_pnl_pct"]
        print(f"  Total P&L (tracked): ${pnl:+,.0f} ({pnl_pct:+.2f}% on ${perf['total_cost_basis']:,.0f} basis)")
    print(P)

    # ---- Section 1: Prices ----
    print("\n1. CURRENT MARKET PRICES")
    print("-" * 78)
    print(f"  {'Asset':<24} {'Ticker':<10} {'Price':>12} {'WoW %':>8}  Source")
    print("  " + "-" * 70)
    for _, r in df.iterrows():
        price = _fmt_price(r["latest_price"])
        wow = f"{r['price_wow']:+.2f}%" if not _is_blank(r["price_wow"]) else "n/a"
        print(f"  {r['asset']:<24} {r['ticker'] or '-':<10} {price:>12} {wow:>8}  {r['price_source']}")

    # ---- Section 2: Allocation summary ----
    print("\n2. ALLOCATION SUMMARY (current vs target)")
    print("-" * 78)
    print(f"  {'Asset':<24} {'Current $':>12} {'Cur %':>7} {'Tgt %':>7} {'Drift pp':>9} {'Action':>7}")
    print("  " + "-" * 70)
    for _, r in df.iterrows():
        cur = r["current_value"]
        drift_pp = r["drift"] * 100.0
        print(
            f"  {r['asset']:<24} "
            f"${cur:>11,.0f} "
            f"{r['current_pct']*100:>6.2f}% "
            f"{r['target_pct']*100:>6.2f}% "
            f"{drift_pp:>+8.2f} "
            f"{r['action']:>7}"
        )

    # By type
    print()
    print("  By asset class:")
    by_type = alloc["by_type"]
    for atype, row in by_type.iterrows():
        cur = float(row["current"])
        tgt = float(row["target"])
        cur_pct = cur / total_capital * 100
        tgt_pct = tgt / total_capital * 100
        print(f"    {atype:<12} ${cur:>11,.0f} ({cur_pct:5.2f}%)  "
              f"target ${tgt:>11,.0f} ({tgt_pct:5.2f}%)")

    # ---- Section 3: Rebalancing signals ----
    print("\n3. REBALANCING SIGNALS (drift > +/-3.0pp)")
    print("-" * 78)
    if not signals:
        print("  All positions within tolerance. No rebalancing required.")
    else:
        for s in signals:
            direction = "BUY " if s["delta_dollars"] > 0 else "SELL"
            verb = "add" if s["action"] == "ADD" else "trim"
            print(
                f"  {direction}: {s['asset']}\n"
                f"      current {s['current_pct']*100:.2f}% vs target {s['target_pct']*100:.2f}% "
                f"(drift {s['drift_pp']:+.2f}pp) -> {verb} ${abs(s['delta_dollars']):,.0f}"
            )
        # Summary
        total_buy = sum(s["delta_dollars"] for s in signals if s["delta_dollars"] > 0)
        total_sell = -sum(s["delta_dollars"] for s in signals if s["delta_dollars"] < 0)
        print(f"\n  Net rebalance: ${total_buy:,.0f} to deploy, ${total_sell:,.0f} to raise")

    # ---- Section 4: Performance ----
    print("\n4. PERFORMANCE TRACKING")
    print("-" * 78)
    if perf["positions_tracked"] == 0:
        print("  No cost-basis data recorded.")
        print("  Run 'python scripts/portfolio_dashboard.py --interactive' and enter")
        print("  cost basis to enable P&L tracking.")
    else:
        print(f"  {'Asset':<24} {'Cost Basis':>12} {'Current':>12} {'P&L $':>12} {'P&L %':>8} {'Ann %':>8}")
        print("  " + "-" * 70)
        for _, r in df.iterrows():
            if _is_blank(r["cost_basis"]) or r["cost_basis"] <= 0:
                continue
            ann = f"{r['annualized_return']:+.2f}%" if not _is_blank(r["annualized_return"]) else "n/a"
            pnl_d = f"${r['pnl_dollars']:>+11,.0f}" if not _is_blank(r["pnl_dollars"]) else "n/a".rjust(12)
            pnl_p = f"{r['pnl_pct']:>+7.2f}%" if not _is_blank(r["pnl_pct"]) else "n/a".rjust(8)
            print(
                f"  {r['asset']:<24} "
                f"${r['cost_basis']:>11,.0f} "
                f"${r['current_value']:>11,.0f} "
                f"{pnl_d} "
                f"{pnl_p} "
                f"{ann:>8}"
            )
        print("  " + "-" * 70)
        print(f"  {'TOTAL (tracked)':<24} "
              f"${perf['total_cost_basis']:>11,.0f} "
              f"${perf['total_current_value']:>11,.0f} "
              f"${perf['total_pnl_dollars']:>+11,.0f} "
              f"{perf['total_pnl_pct']:>+7.2f}%")

    # ---- Section 5: Risk metrics ----
    print("\n5. RISK METRICS")
    print("-" * 78)
    print(f"  Portfolio beta to SPY:        {risk['portfolio_beta']:.2f}")
    print(f"  Portfolio vol (weighted avg): {risk['portfolio_vol_weighted']*100:.1f}%")
    if risk["portfolio_vol_proper"] is not None:
        print(f"  Portfolio vol (covariance):   {risk['portfolio_vol_proper']*100:.1f}% "
              f"(from {risk['cov_n_assets']} assets)")
    else:
        print(f"  Portfolio vol (covariance):   n/a (insufficient shared history)")
    print()
    print("  Beta contributions (weight * asset beta):")
    for asset, w, b in risk["beta_components"]:
        contrib = w * b
        print(f"    {asset:<24} w={w*100:5.1f}%  beta={b:+5.2f}  contrib={contrib:+.3f}")
    print()
    print(f"  Cash allocation: ${risk['cash_value']:,.0f} ({risk['cash_pct']*100:.1f}%) -> {risk['cash_status']}")
    if risk["biggest_position"] is not None:
        bp = risk["biggest_position"]
        breach_tag = " [BREACH]" if risk["concentration_breach"] else ""
        print(f"  Biggest position: {bp['asset']} ({bp['pct']*100:.1f}%) "
              f"[limit {risk['concentration_threshold']*100:.0f}%]{breach_tag}")

    # ---- Section 6: Correlation matrix ----
    print("\n6. CORRELATION MATRIX (daily returns, ~1Y)")
    print("-" * 78)
    if corr is None:
        print("  Not enough shared price history to compute correlations.")
    else:
        _print_corr_matrix_console(corr)

    # ---- Section 7: Next steps ----
    print("\n7. NEXT STEPS")
    print("-" * 78)
    for i, s in enumerate(_build_next_steps(df, signals, risk, alloc, mode), 1):
        print(f"  {i}. {s}")

    print()
    print(P)


def _print_corr_matrix_console(corr):
    """Pretty-print a correlation matrix to the console."""
    tickers = list(corr.columns)
    header = "  " + " " * 10 + "".join(f"{t:>10}" for t in tickers)
    print(header)
    print("  " + "-" * (10 + 10 * len(tickers)))
    for t0 in tickers:
        row = f"  {t0:<10}"
        for t1 in tickers:
            v = corr.loc[t0, t1]
            row += f"{v:>10.2f}"
        print(row)


def _build_next_steps(df, signals, risk, alloc, mode):
    """Return a list of action-oriented next-step strings tailored to the
    current state. Consumed by both the console and markdown renderers."""
    steps = []

    if mode == "static (no config)":
        steps.append("Run 'python scripts/portfolio_dashboard.py --interactive' once")
        steps.append("to record your actual positions and enable P&L tracking.")

    if alloc["deployed_pct_of_capital"] < 0.90:
        steps.append(f"Deploy capital: only {alloc['deployed_pct_of_capital']*100:.1f}% of "
                     f"${alloc['total_capital']:,.0f} is currently allocated.")

    if signals:
        biggest = signals[0]
        direction = "add to" if biggest["delta_dollars"] > 0 else "trim"
        steps.append(f"Largest drift: {biggest['asset']} ({biggest['drift_pp']:+.2f}pp). "
                     f"Rebalance by {direction} ${abs(biggest['delta_dollars']):,.0f}.")

    if risk["cash_pct"] < CASH_MIN_PCT:
        steps.append(f"Raise cash to at least {CASH_MIN_PCT*100:.0f}% for dry powder "
                     f"(currently {risk['cash_pct']*100:.1f}%).")
    elif risk["cash_pct"] > CASH_MAX_PCT:
        steps.append(f"Excess cash: {risk['cash_pct']*100:.1f}% > {CASH_MAX_PCT*100:.0f}% target. "
                     f"Deploy into underweight positions.")

    if risk["concentration_breach"]:
        bp = risk["biggest_position"]
        steps.append(f"Concentration breach: {bp['asset']} at {bp['pct']*100:.1f}% "
                     f"(limit {risk['concentration_threshold']*100:.0f}%). Trim toward target.")

    if risk["portfolio_beta"] > 1.3:
        steps.append(f"High portfolio beta ({risk['portfolio_beta']:.2f}): portfolio amplifies SPY moves. "
                     f"Consider adding gold / cash to hedge.")
    elif risk["portfolio_beta"] < 0.5:
        steps.append(f"Low portfolio beta ({risk['portfolio_beta']:.2f}): defensive. "
                     f"Acceptable for capital-preservation phase.")

    if risk["portfolio_vol_weighted"] > 0.30:
        steps.append(f"High expected volatility ({risk['portfolio_vol_weighted']*100:.1f}%). "
                     f"Size positions so a 1-sigma move does not impair capital.")

    if not steps:
        steps.append("Portfolio is within all guardrails. No action required.")
    return steps


# ============================================================================
# MARKDOWN REPORT
# ============================================================================

def render_markdown(df, alloc, perf, signals, risk, corr, total_capital, mode):
    """Build the markdown snapshot report."""
    today = datetime.now().strftime("%Y-%m-%d")
    lines = []
    lines.append(f"# Portfolio Dashboard - {today}")
    lines.append("")
    lines.append(f"**Total capital:** ${total_capital:,.0f}  ")
    lines.append(f"**Mode:** {mode}  ")
    lines.append(f"**Deployed:** ${alloc['deployed']:,.0f} "
                 f"({alloc['deployed_pct_of_capital']*100:.1f}%)  ")
    lines.append(f"**Cash / un-deployed:** ${alloc['cash_undeployed']:,.0f}  ")
    if perf["positions_tracked"] > 0:
        lines.append(f"**Total P&L (tracked):** "
                     f"${perf['total_pnl_dollars']:+,.0f} "
                     f"({perf['total_pnl_pct']:+.2f}%)")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Prices
    lines.append("## 1. Current Market Prices")
    lines.append("")
    lines.append("| Asset | Ticker | Price | WoW % | Source |")
    lines.append("|-------|--------|------:|------:|--------|")
    for _, r in df.iterrows():
        if _is_blank(r["latest_price"]):
            price = "n/a"
        else:
            price = f"${r['latest_price']:,.2f}"
        wow = f"{r['price_wow']:+.2f}%" if not _is_blank(r["price_wow"]) else "n/a"
        lines.append(f"| {r['asset']} | {r['ticker']} | {price} | {wow} | {r['price_source']} |")
    lines.append("")

    # Allocation
    lines.append("## 2. Allocation Summary")
    lines.append("")
    lines.append("| Asset | Current $ | Current % | Target % | Drift (pp) | Action |")
    lines.append("|-------|----------:|----------:|---------:|-----------:|:-------|")
    for _, r in df.iterrows():
        drift_pp = r["drift"] * 100.0
        lines.append(
            f"| {r['asset']} | ${r['current_value']:,.0f} | "
            f"{r['current_pct']*100:.2f}% | {r['target_pct']*100:.2f}% | "
            f"{drift_pp:+.2f} | **{r['action']}** |"
        )
    lines.append("")
    lines.append("**By asset class:**")
    lines.append("")
    lines.append("| Class | Current $ | Current % | Target $ | Target % |")
    lines.append("|-------|----------:|----------:|---------:|---------:|")
    for atype, row in alloc["by_type"].iterrows():
        cur = float(row["current"])
        tgt = float(row["target"])
        lines.append(
            f"| {atype} | ${cur:,.0f} | {cur/total_capital*100:.2f}% | "
            f"${tgt:,.0f} | {tgt/total_capital*100:.2f}% |"
        )
    lines.append("")

    # Rebalancing
    lines.append("## 3. Rebalancing Signals (drift > +/-3.0pp)")
    lines.append("")
    if not signals:
        lines.append("All positions within tolerance. No rebalancing required.")
    else:
        lines.append("| Action | Asset | Current % | Target % | Drift (pp) | $ Move |")
        lines.append("|:-------|-------|----------:|---------:|-----------:|-------:|")
        for s in signals:
            verb = "BUY" if s["delta_dollars"] > 0 else "SELL"
            lines.append(
                f"| **{verb}** | {s['asset']} | {s['current_pct']*100:.2f}% | "
                f"{s['target_pct']*100:.2f}% | {s['drift_pp']:+.2f} | "
                f"${abs(s['delta_dollars']):,.0f} |"
            )
        total_buy = sum(s["delta_dollars"] for s in signals if s["delta_dollars"] > 0)
        total_sell = -sum(s["delta_dollars"] for s in signals if s["delta_dollars"] < 0)
        lines.append("")
        lines.append(f"**Net rebalance:** ${total_buy:,.0f} to deploy, "
                     f"${total_sell:,.0f} to raise.")
    lines.append("")

    # Performance
    lines.append("## 4. Performance Tracking")
    lines.append("")
    if perf["positions_tracked"] == 0:
        lines.append("No cost-basis data recorded. Run `--interactive` and enter cost basis "
                     "to enable P&L tracking.")
    else:
        lines.append("| Asset | Cost Basis | Current | P&L $ | P&L % | Annualized % |")
        lines.append("|-------|-----------:|--------:|------:|------:|-------------:|")
        for _, r in df.iterrows():
            if _is_blank(r["cost_basis"]) or r["cost_basis"] <= 0:
                continue
            ann = f"{r['annualized_return']:+.2f}%" if not _is_blank(r["annualized_return"]) else "n/a"
            pnl_d = f"${r['pnl_dollars']:+,.0f}" if not _is_blank(r["pnl_dollars"]) else "n/a"
            pnl_p = f"{r['pnl_pct']:+.2f}%" if not _is_blank(r["pnl_pct"]) else "n/a"
            lines.append(
                f"| {r['asset']} | ${r['cost_basis']:,.0f} | ${r['current_value']:,.0f} | "
                f"{pnl_d} | {pnl_p} | {ann} |"
            )
        lines.append("| **TOTAL** | "
                     f"${perf['total_cost_basis']:,.0f} | "
                     f"${perf['total_current_value']:,.0f} | "
                     f"${perf['total_pnl_dollars']:+,.0f} | "
                     f"{perf['total_pnl_pct']:+.2f}% | |")
    lines.append("")

    # Risk
    lines.append("## 5. Risk Metrics")
    lines.append("")
    lines.append(f"- **Portfolio beta to SPY:** {risk['portfolio_beta']:.2f}")
    lines.append(f"- **Portfolio vol (weighted avg):** {risk['portfolio_vol_weighted']*100:.1f}%")
    if risk["portfolio_vol_proper"] is not None:
        lines.append(f"- **Portfolio vol (covariance):** {risk['portfolio_vol_proper']*100:.1f}% "
                     f"(from {risk['cov_n_assets']} assets)")
    else:
        lines.append("- **Portfolio vol (covariance):** n/a (insufficient shared history)")
    lines.append("")
    lines.append("**Beta contributions:**")
    lines.append("")
    lines.append("| Asset | Weight | Beta | Contribution |")
    lines.append("|-------|------:|-----:|-------------:|")
    for asset, w, b in risk["beta_components"]:
        lines.append(f"| {asset} | {w*100:.1f}% | {b:+.2f} | {w*b:+.3f} |")
    lines.append("")
    lines.append(f"- **Cash allocation:** ${risk['cash_value']:,.0f} "
                 f"({risk['cash_pct']*100:.1f}%) -> {risk['cash_status']}")
    if risk["biggest_position"] is not None:
        bp = risk["biggest_position"]
        breach_tag = " **[BREACH]**" if risk["concentration_breach"] else ""
        lines.append(f"- **Biggest position:** {bp['asset']} ({bp['pct']*100:.1f}%) "
                     f"[limit {risk['concentration_threshold']*100:.0f}%]{breach_tag}")
    lines.append("")

    # Correlation
    lines.append("## 6. Correlation Matrix")
    lines.append("")
    if corr is None:
        lines.append("Not enough shared price history to compute correlations.")
    else:
        headers = "| Asset | " + " | ".join(corr.columns) + " |"
        sep = "|-------|" + "|".join(["------:"] * len(corr.columns)) + "|"
        lines.append(headers)
        lines.append(sep)
        for t0 in corr.index:
            cells = " | ".join(f"{corr.loc[t0, t1]:+.2f}" for t1 in corr.columns)
            lines.append(f"| {t0} | {cells} |")
    lines.append("")

    # Next steps
    lines.append("## 7. Next Steps")
    lines.append("")
    for i, s in enumerate(_build_next_steps(df, signals, risk, alloc, mode), 1):
        lines.append(f"{i}. {s}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"*Generated by `scripts/portfolio_dashboard.py` on {today}. "
                 f"Prices: Yahoo Finance (live where available, cached otherwise). "
                 f"This is analysis, not investment advice.*")

    return "\n".join(lines)


# ============================================================================
# MAIN
# ============================================================================

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Portfolio dashboard for $800K multi-asset allocation."
    )
    parser.add_argument(
        "--interactive", action="store_true",
        help="Run interactive setup to record current positions.",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Delete saved config (reports/portfolio/config.json).",
    )
    parser.add_argument(
        "--capital", type=float, default=float(TOTAL_CASH),
        help=f"Total capital to track (default ${TOTAL_CASH}).",
    )
    args = parser.parse_args(argv)

    if args.reset:
        reset_config()
        return 0

    if args.interactive:
        cfg = run_interactive_setup(DEFAULT_ALLOCATION, args.capital)
    else:
        cfg = load_config()

    if cfg is None:
        mode = "static (no config - assumes target deployed)"
    else:
        mode = f"loaded from {CONFIG_PATH.name}"

    # Build the portfolio table
    df = build_portfolio(DEFAULT_ALLOCATION, cfg, args.capital)

    # Analyses
    alloc = summarize_allocation(df, args.capital)
    perf = summarize_performance(df)
    signals = build_rebalancing_signals(df, args.capital)
    risk = compute_risk_metrics(df, args.capital)
    corr, _returns = compute_correlation_matrix(df)

    # Render console
    render_console(df, alloc, perf, signals, risk, corr, args.capital, mode)

    # Write markdown snapshot
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    md_path = REPORT_DIR / f"snapshot_{today}.md"
    md = render_markdown(df, alloc, perf, signals, risk, corr, args.capital, mode)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"\nMarkdown snapshot written to: {md_path}")
    print(f"  ({md_path.stat().st_size / 1024:.1f} KB)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
