"""Live validation: FRED + EIA + macro factors + regime classification."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import warnings
warnings.filterwarnings("ignore")

print("=" * 60)
print("FRED DATA PROVIDER SMOKE TEST")
print("=" * 60)
from src.research.data.fred import FredProvider
fred = FredProvider()

for sid, name, lo, hi in [
    ("GOLDAMGBD228NLBM", "Gold LBMA AM", 1000, 5000),
    ("DCOILWTICO", "WTI Spot", 10, 200),
    ("CSUSHPINSA", "Case-Shiller", 100, 400),
    ("DFII10", "10Y Real Yield", -2, 5),
    ("VIXCLS", "VIX", 5, 100),
    ("UNRATE", "Unemployment", 0, 20),
    ("T10YIE", "10Y Breakeven", -2, 8),
]:
    try:
        df = fred.fetch(sid, "2024-01-01", "2024-12-31")
        latest = df["close"].iloc[-1]
        ok = lo <= latest <= hi
        status = "OK" if ok else "SUSPECT"
        print(f"  [{status}] {name:20s}: {len(df):4d} rows, latest={latest:.2f}")
    except Exception as e:
        print(f"  [FAIL] {name:20s}: {e}")

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

print()
print("=" * 60)
print("MACRO FACTOR PROVIDER (12 factors)")
print("=" * 60)
from src.research.macro.factors import MacroFactorProvider
from datetime import date
mfp = MacroFactorProvider()
factor_df = mfp.load_factors(date(2020, 1, 1), date(2024, 12, 31))
print(f"  Shape: {factor_df.shape}")
print(f"  Date range: {factor_df.index[0].date()} to {factor_df.index[-1].date()}")
for col in factor_df.columns:
    nan_pct = factor_df[col].isna().mean() * 100
    non_na = factor_df[col].dropna()
    latest = non_na.iloc[-1] if len(non_na) > 0 else "N/A"
    print(f"    {col:25s}: nan={nan_pct:5.1f}%  latest={latest}")

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

print()
print("=" * 60)
print("LAST 12 MONTHS REGIME TAPE")
print("=" * 60)
import pandas as pd
for month_end in pd.date_range(end=probs.index[-1], periods=12, freq="ME"):
    month_mask = (probs.index.month == month_end.month) & (probs.index.year == month_end.year)
    month_data = probs[month_mask]
    if len(month_data) == 0:
        continue
    dom = Regime(month_data.mean().idxmax())
    print(f"  {month_end.strftime('%Y-%m')}: {dom.value}")

print()
print("ALL SMOKE TESTS COMPLETE")
