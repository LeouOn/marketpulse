"""Live validation: FRED + EIA smoke tests, then regime backrun."""
import sys
import os

# ── 1. FRED smoke ──
print("=" * 60)
print("FRED DATA PROVIDER SMOKE TEST")
print("=" * 60)
from src.research.data.fred import FredProvider
fred = FredProvider()

series_checks = [
    ("GOLDAMGBD228NLBM", "Gold LBMA AM", 1000, 5000),
    ("DCOILWTICO", "WTI Spot", 10, 200),
    ("CSUSHPINSA", "Case-Shiller", 100, 400),
    ("DFII10", "10Y Real Yield", -2, 5),
    ("VIXCLS", "VIX", 5, 100),
    ("UNRATE", "Unemployment", 0, 20),
    ("T10YIE", "10Y Breakeven", -2, 8),
]
for sid, name, lo, hi in series_checks:
    try:
        df = fred.fetch(sid, "2024-01-01", "2024-12-31")
        latest = df["close"].iloc[-1]
        ok = lo <= latest <= hi
        status = "OK" if ok else "SUSPECT"
        print(f"  [{status}] {name:20s} ({sid}): {len(df):4d} rows, latest={latest:.2f}")
    except Exception as e:
        print(f"  [FAIL] {name:20s} ({sid}): {e}")

# ── 2. EIA smoke ──
print()
print("=" * 60)
print("EIA DATA PROVIDER SMOKE TEST")
print("=" * 60)
from src.research.data.eia import EiaProvider
eia = EiaProvider()
try:
    df = eia.fetch("PET.RWTC.D", "2024-01-01", "2024-12-31")
    print(f"  [OK] EIA WTI Spot: {len(df)} rows, latest={df['close'].iloc[-1]:.2f}")
except Exception as e:
    print(f"  [FAIL] EIA WTI Spot: {e}")

# ── 3. MacroFactorProvider (all 12 factors) ──
print()
print("=" * 60)
print("MACRO FACTOR PROVIDER (12 factors)")
print("=" * 60)
from src.research.macro.factors import MacroFactorProvider
from datetime import date
mfp = MacroFactorProvider()
factor_df = mfp.load_factors(date(2020, 1, 1), date(2024, 12, 31))
print(f"  Shape: {factor_df.shape}")
print(f"  Columns: {list(factor_df.columns)}")
print(f"  Date range: {factor_df.index[0]} to {factor_df.index[-1]}")
for col in factor_df.columns:
    nan_pct = factor_df[col].isna().mean() * 100
    latest = factor_df[col].dropna().iloc[-1] if factor_df[col].dropna().len() > 0 else "N/A"
    print(f"    {col:25s}: nan={nan_pct:5.1f}%  latest={latest}")

# ── 4. Regime classification (latest) ──
print()
print("=" * 60)
print("CURRENT REGIME CLASSIFICATION")
print("=" * 60)
from src.research.macro.regimes import RulesBasedClassifier, Regime
clf = RulesBasedClassifier()
probs = clf.classify(factor_df)
latest_probs = probs.iloc[-1]
dominant = Regime(latest_probs.idxmax())
print(f"  Date: {factor_df.index[-1].date()}")
print(f"  Dominant regime: {dominant.value}")
print(f"  Probabilities:")
for regime in Regime:
    p = latest_probs.get(regime.value, 0)
    bar = "#" * int(p * 40)
    print(f"    {regime.value:20s}: {p:.3f} {bar}")

# ── 5. Last 12 months regime tape ──
print()
print("=" * 60)
print("LAST 12 MONTHS REGIME TAAPE")
print("=" * 60)
last_12m = probs.tail(252)  # approx 12 months of trading days
monthly = last_12m.resample("ME").agg(lambda x: x.idxmax()).iloc[:, 0] if len(last_12m) > 0 else []
# Simpler: just show the dominant regime per month
last_12m_dates = probs.index[-252:]
for month_start in pd_month_starts(last_12m_dates):
    mask = (probs.index >= month_start) & (probs.index < month_start + pd.Timedelta(days=32))
    if mask.any():
        month_probs = probs[mask].mean()
        dom = Regime(month_probs.idxmax())
        print(f"  {month_start.strftime('%Y-%m')}: {dom.value}")

print()
print("=" * 60)
print("ALL SMOKE TESTS COMPLETE")
print("=" * 60)
