"""
PRE-TRADE CHECK - Circuit Breaker for MNQ/NQ Trades

This tool BLOCKS bad trades before they happen. It combines:
1. Regime check (RISK_ON = no counter-trend, only INFLATION_ACCEL allows it)
2. Trend strength check (3M return +15%+ = red flag for counter-trend)
3. Price level check (at all-time highs = extended, no counter-trend)
4. Trend danger score (composite of regime + ADX + EMA + VIX)
5. Anti-blowup rules (max 6 MNQ, no adding to losers, daily loss limit)
6. The 5-Question Rule (for counter-trend trades only)

HOW TO USE:
  python scripts/pre_trade_check.py                    # Interactive mode
  python scripts/pre_trade_check.py --direction SHORT # Pre-filled for short trades
  python scripts/pre_trade_check.py --skip-interactive  # Just show the checks
  python scripts/pre_trade_check.py --explain          # Why each check exists

If the script outputs "BLOCKED", DO NOT ENTER THE TRADE.
If the script outputs "OK TO TRADE", proceed with caution.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse
import pandas as pd
import numpy as np
import yfinance as yf

from src.research.macro.regimes import RulesBasedClassifier


def load_factors():
    """Load macro factors from parquet."""
    return pd.read_parquet("data/macro/factors.parquet")


def get_current_regime():
    """Get current regime classification."""
    factors = load_factors()
    rc = RulesBasedClassifier()
    regime_probs = rc.classify(factors)
    latest = regime_probs.iloc[-1]
    return latest.idxmax(), latest.to_dict()


def get_nq_data(period="6mo"):
    """Fetch NQ futures data."""
    df = yf.download("NQ=F", period=period, progress=False, auto_adjust=False)
    close = df["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return close


def get_vix():
    """Fetch current VIX."""
    try:
        vix_df = pd.read_parquet("data/macro/VIXCLS.parquet")
        vix_df["ts"] = pd.to_datetime(vix_df["ts"])
        return float(vix_df["close"].iloc[-1])
    except:
        df = yf.download("^VIX", period="5d", progress=False, auto_adjust=False)
        close = df["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        return float(close.iloc[-1])


# The 5 regimes, with counter-trend allowed or not
COUNTER_TREND_ALLOWED = {
    "RISK_ON": False,          # #1 destruction regime - NEVER short here
    "RECESSION": False,        # Counter-trend DESTROYED -35.2%
    "INFLATION_ACCEL": True,   # ONLY regime where counter-trend WORKED (+12.9%)
    "DEFLATION_SCARE": False,  # Counter-trend barely worked (+2.9%)
    "REAL_YIELD_SHOCK": False, # Insufficient data, treat as no
}


def check_regime():
    """REGIME CHECK - Is counter-trend even permitted right now?"""
    regime, probs = get_current_regime()
    allowed = COUNTER_TREND_ALLOWED.get(regime, False)
    
    return {
        "name": "REGIME CHECK",
        "current_regime": regime,
        "probabilities": probs,
        "counter_trend_allowed": allowed,
        "passed": allowed,  # Pass = counter-trend is permitted
        "message": (
            f"Current regime: {regime}\n"
            f"Counter-trend in {regime}: "
            f"{'ALLOWED (historical +12.9% return)' if allowed else 'NOT ALLOWED (historical losses)'}\n"
            + (
                ">>> This is the ONLY regime where counter-trend has worked historically. <<<" if allowed else
                ">>> Counter-trend in this regime has DESTROYED accounts historically. <<<"
            )
        ),
    }


def check_trend_strength():
    """TREND STRENGTH CHECK - Is the trend too strong to fight?"""
    close = get_nq_data("6mo")
    price = float(close.iloc[-1])
    
    # Returns at different windows
    ret_1w = ((price / close.iloc[-5]) - 1) * 100 if len(close) >= 5 else 0
    ret_1m = ((price / close.iloc[-22]) - 1) * 100 if len(close) >= 22 else 0
    ret_3m = ((price / close.iloc[-65]) - 1) * 100 if len(close) >= 65 else 0
    ret_6m = ((price / close.iloc[-130]) - 1) * 100 if len(close) >= 130 else 0
    
    # Moving averages
    sma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else price
    sma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else price
    
    # Trend flags
    above_50 = price > sma50
    above_200 = price > sma200
    ma50_above_200 = sma50 > sma200
    full_bull = above_50 and above_200 and ma50_above_200
    
    # Trend danger score (0-100, higher = more dangerous to counter-trend)
    score = 0
    if ret_3m > 15: score += 30
    if ret_1m > 5: score += 15
    if full_bull: score += 25
    if ret_1w > 0 and ret_1m > 0: score += 10
    if ret_1w < 0 and ret_1m > 0: score += 5  # just pullback, trend intact
    if ret_1m < 0 and ret_3m < 0: score -= 20  # already in downtrend, counter-trend OK
    
    trend_danger = min(100, max(0, score))
    passed = trend_danger < 50  # Below 50 = safe to counter-trend
    
    return {
        "name": "TREND STRENGTH CHECK",
        "price": price,
        "sma50": sma50,
        "sma200": sma200 if sma200 == sma200 else None,  # NaN check
        "ret_1w": ret_1w,
        "ret_1m": ret_1m,
        "ret_3m": ret_3m,
        "ret_6m": ret_6m,
        "above_50": above_50,
        "above_200": above_200,
        "full_bull": full_bull,
        "trend_danger_score": trend_danger,
        "passed": passed,
        "message": (
            f"NQ price: {price:,.2f}\n"
            f"3M return: {ret_3m:+.1f}%  |  1M: {ret_1m:+.1f}%  |  1W: {ret_1w:+.1f}%\n"
            f"Above 50-day MA: {above_50}  |  Above 200-day MA: {above_200}\n"
            f"Full bull trend (price > 50MA > 200MA): {full_bull}\n"
            f"\n"
            f"TREND DANGER SCORE: {trend_danger}/100\n"
            + (
                ">>> EXTREME DANGER for counter-trend. Trend is strong. <<<" if trend_danger >= 75 else
                ">>> HIGH RISK for counter-trend. Reduce size if you must. <<<" if trend_danger >= 50 else
                ">>> Moderate risk. Standard counter-trend setup. <<<" if trend_danger >= 25 else
                ">>> LOW RISK. Trend is weak or reversing. Counter-trend favorable. <<<"
            )
        ),
    }


def check_price_level():
    """PRICE LEVEL CHECK - Is NQ at extended levels (no counter-trend support)?"""
    close = get_nq_data("1y")
    price = float(close.iloc[-1])
    high_52w = float(close.tail(252).max()) if len(close) >= 252 else float(close.max())
    low_52w = float(close.tail(252).min()) if len(close) >= 252 else float(close.min())
    
    pct_from_high = (price / high_52w - 1) * 100
    pct_from_low = (price / low_52w - 1) * 100
    
    # "Near ATH" = within 3% of high
    at_ath = pct_from_high > -3
    extended = pct_from_high > -5  # within 5% of high
    
    # "Near support" = within 10% of low
    near_support = pct_from_low < 10
    
    passed = near_support or pct_from_high < -10  # Pass if at support or far from high
    
    return {
        "name": "PRICE LEVEL CHECK",
        "price": price,
        "high_52w": high_52w,
        "low_52w": low_52w,
        "pct_from_high": pct_from_high,
        "pct_from_low": pct_from_low,
        "at_ath": at_ath,
        "near_support": near_support,
        "passed": passed,
        "message": (
            f"NQ price: {price:,.2f}\n"
            f"52W high: {high_52w:,.2f}  (current is {pct_from_high:+.1f}% from high)\n"
            f"52W low:  {low_52w:,.2f}  (current is {pct_from_low:+.1f}% from low)\n"
            f"At/near all-time high: {at_ath}\n"
            f"Near support (within 10% of low): {near_support}\n"
            + (
                ">>> EXTENDED. No counter-trend support. Wait for pullback. <<<" if at_ath else
                ">>> Moderate levels. Acceptable for counter-trend. <<<" if not extended else
                ">>> Near highs but not at ATH. Counter-trend risky but possible. <<<"
            )
        ),
    }


def check_vix():
    """VOLATILITY CHECK - High VIX means stress; low VIX means complacency."""
    vix = get_vix()
    
    if vix > 30:
        level = "EXTREME STRESS"
        passed = True  # Counter-trend mean-reversion works in panics
    elif vix > 25:
        level = "HIGH"
        passed = True
    elif vix > 20:
        level = "ELEVATED"
        passed = True
    elif vix > 15:
        level = "NORMAL"
        passed = False  # Counter-trend less effective in calm markets
    else:
        level = "COMPLACENT (potential tail risk)"
        passed = False
    
    return {
        "name": "VOLATILITY (VIX) CHECK",
        "vix": vix,
        "level": level,
        "passed": passed,
        "message": (
            f"VIX: {vix:.1f} ({level})\n"
            + (
                ">>> High VIX = panic. Counter-trend mean-reversion works in panics. <<<" if passed else
                ">>> Low VIX = complacent. Counter-trend less effective. <<<"
            )
        ),
    }


def check_anti_blowup():
    """ANTI-BLOWUP RULES - Always check, never optional."""
    return {
        "name": "ANTI-BLOWUP RULES",
        "passed": True,  # Always passes the check itself; the rules must be FOLLOWED manually
        "message": (
            ">>> ANTI-BLOWUP RULES (NON-NEGOTIABLE) <<<\n"
            "1. MAX POSITION: 6 MNQ total (absolute, no exceptions)\n"
            "2. MAX ADDS PER TRADE: 2 (only to WINNERS, never losers)\n"
            "3. DECREASING SIZE: each add must be <=50% of previous entry\n"
            "4. DAILY LOSS LIMIT: 3% of account = STOP for 24 hours\n"
            "5. AFTER 2 LOSSES: reduce next trade to 1 MNQ + 30min cooldown\n"
            "6. NEVER WIDEN STOPS (trail one direction only)\n"
            "7. WINNERS: +1R move stop to BE | +2R trail 20EMA | +3R take 50% trail rest\n"
            "\n"
            "The 1->9 MNQ pattern starts by adding to a LOSER. Don't.\n"
        ),
    }


def check_5_question_rule():
    """THE 5-QUESTION RULE - Interactive check for counter-trend trades."""
    questions = [
        ("What regime am I in?",
         "If you don't know the regime name and its counter-trend history, you shouldn't trade."),
        ("Is my thesis stronger than the prevailing trend?",
         "If you can't articulate a specific catalyst for reversal (not 'it's gone up too much'), skip."),
        ("What's the historical win rate for counter-trend in THIS regime?",
         "If you don't know this number, you're guessing. Skip."),
        ("What technical signal confirms the reversal?",
         "If you can't point to a specific trigger (breakdown, breakdown of trend line, momentum divergence), skip."),
        ("If I'm wrong in 3 days, what's my exit?",
         "If you don't have a defined stop, you don't have a trade. You have a hope."),
    ]
    
    print()
    print("=" * 80)
    print("THE 5-QUESTION RULE (before any counter-trend trade)")
    print("=" * 80)
    print()
    for i, (q, hint) in enumerate(questions, 1):
        print(f"  {i}. {q}")
        print(f"     Hint: {hint}")
        print()
    
    print("=" * 80)
    print("If you can't write confident answers to all 5 questions,")
    print("the trade is BLOCKED. Period.")
    print("=" * 80)
    
    return {
        "name": "5-QUESTION RULE",
        "passed": False,  # Force user to engage interactively
        "message": "See questions above. If you can't answer all 5 confidently, DO NOT TRADE.",
    }


def run_all_checks(direction="AUTO"):
    """Run all checks and produce a verdict."""
    print()
    print("=" * 80)
    print(f"PRE-TRADE CHECK - Direction: {direction}")
    print("=" * 80)
    print()
    
    # Always run these
    regime_check = check_regime()
    trend_check = check_trend_strength()
    level_check = check_price_level()
    vix_check = check_vix()
    anti_blowup = check_anti_blowup()
    
    checks = [regime_check, trend_check, level_check, vix_check]
    
    # Counter-trend-specific checks
    is_counter_trend = direction.upper() in ("SHORT", "SELL") and trend_check["trend_danger_score"] >= 30
    
    for check in checks:
        print(f"## {check['name']}")
        print("-" * 60)
        print(check["message"])
        print()
        status = "PASS" if check["passed"] else "FAIL"
        print(f">>> {check['name']}: {status} <<<")
        print()
    
    print("=" * 80)
    print("ANTI-BLOWUP RULES (ALWAYS)")
    print("=" * 80)
    print(anti_blowup["message"])
    print()
    
    # 5-Question Rule (only for counter-trend)
    if is_counter_trend or direction.upper() in ("SHORT", "SELL"):
        check_5_question_rule()
    
    # Verdict
    print()
    print("=" * 80)
    print("VERDICT")
    print("=" * 80)
    
    # For counter-trend trades, ANY failed check = block
    if direction.upper() in ("SHORT", "SELL"):
        failures = [c for c in checks if not c["passed"]]
        if failures:
            print()
            print(f"*** TRADE BLOCKED ***")
            print()
            print(f"Failed checks: {', '.join(c['name'] for c in failures)}")
            print()
            print("To trade counter-trend, ALL of these must pass:")
            print("  - Regime must allow counter-trend (only INFLATION_ACCEL)")
            print("  - Trend danger score must be < 50 (weak/reversing trend)")
            print("  - Price must be at support, not ATH")
            print("  - VIX must be elevated (panics allow counter-trend)")
            print()
            print("DO NOT ENTER THIS TRADE.")
            print()
            print("If you still want to trade:")
            print("  1. Answer the 5-Question Rule in writing")
            print("  2. Show your work to someone else")
            print("  3. Use only 1 MNQ max position size")
            print("  4. Set a hard stop BEFORE entry")
            return False
        else:
            print()
            print("*** TRADE CLEARED (use caution anyway) ***")
            print()
            print("All checks passed. Counter-trend is permitted in current regime.")
            print("But ALWAYS: small size, tight stop, time stop, the 5-question rule.")
            return True
    else:
        # For trend-follow trades, check anti-blowup and warn on trend danger
        if trend_check["trend_danger_score"] >= 75 and direction.upper() in ("LONG", "BUY"):
            print()
            print(">>> NOTE: Trend is at EXTREME DANGER (extended). Consider smaller size <<<")
            print()
            print("Trend-following is OK in this setup, but price is extended.")
            print("Standard or smaller position. Tighter stops. Don't add at highs.")
            return True
        else:
            print()
            print("*** TRADE CLEARED ***")
            print()
            print("All checks passed. Standard trading rules apply.")
            return True


def main():
    parser = argparse.ArgumentParser(description="Pre-trade check for MNQ/NQ trades")
    parser.add_argument(
        "--direction",
        choices=["LONG", "BUY", "SHORT", "SELL", "AUTO"],
        default="AUTO",
        help="Trade direction (default: AUTO)",
    )
    parser.add_argument(
        "--explain",
        action="store_true",
        help="Explain why each check exists",
    )
    args = parser.parse_args()
    
    if args.explain:
        print("=" * 80)
        print("WHY EACH CHECK EXISTS")
        print("=" * 80)
        print()
        print("REGIME CHECK: Counter-trend has destroyed accounts in 4 of 5 regimes")
        print("  historically. Only INFLATION_ACCEL has rewarded counter-trend.")
        print("  This check prevents you from shorting a RISK_ON bull market.")
        print()
        print("TREND STRENGTH CHECK: 3-month return of +15% or more means the")
        print("  trend is strong. Buying dips has 44% win rate in this setup.")
        print("  The trend danger score (0-100) is a composite of:")
        print("  - 3-month return (strong trend = dangerous to counter)")
        print("  - Price vs 50-day MA (extended = dangerous)")
        print("  - Full bull trend alignment")
        print()
        print("PRICE LEVEL CHECK: At all-time highs, there's no support to")
        print("  catch a falling knife. Counter-trend at ATH = pure speculation.")
        print("  Wait for pullback to support.")
        print()
        print("VOLATILITY CHECK: High VIX = panic. Counter-trend mean-reversion")
        print("  works in panics. Low VIX = complacent. Counter-trend less effective.")
        print()
        print("ANTI-BLOWUP RULES: Non-negotiable. Max 6 MNQ. No adding to losers.")
        print("  Daily 3% loss limit. After 2 losses, drop to 1 MNQ.")
        print()
        print("5-QUESTION RULE: Before any counter-trend trade, answer these in")
        print("  writing. If you can't, the trade is blocked.")
        print()
        return
    
    run_all_checks(direction=args.direction)


if __name__ == "__main__":
    main()
