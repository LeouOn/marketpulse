"""T12 6-episode regime backrun validation with REAL FRED data."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import warnings
warnings.filterwarnings("ignore")

from datetime import date
import pandas as pd
from src.research.macro.factors import MacroFactorProvider
from src.research.macro.regimes import RulesBasedClassifier, Regime

print("Fetching macro factors 1990-2024 (this takes ~30s)...")
mfp = MacroFactorProvider()
factor_df = mfp.load_factors(date(1990, 1, 1), date(2024, 12, 31))
print(f"  Loaded: {factor_df.shape[0]} rows, {factor_df.shape[1]} columns")
print(f"  Range: {factor_df.index[0].date()} to {factor_df.index[-1].date()}")

print("\nRunning RulesBasedClassifier...")
clf = RulesBasedClassifier()
probs = clf.classify(factor_df)
print(f"  Classified: {probs.shape[0]} rows")

# Regime distribution over full period
print("\n" + "=" * 70)
print("FULL PERIOD REGIME DISTRIBUTION (1990-2024)")
print("=" * 70)
dominant = probs.idxmax(axis=1)
dist = dominant.value_counts()
for regime in Regime:
    count = dist.get(regime.value, 0)
    pct = count / len(dominant) * 100
    bar = "#" * int(pct / 2)
    print(f"  {regime.value:20s}: {count:5d} days ({pct:5.1f}%) {bar}")

# 6-episode validation
print("\n" + "=" * 70)
print("6-EPISODE HISTORICAL VALIDATION")
print("=" * 70)

episodes = [
    ("GFC",            "2008-09-01", "2009-03-31", Regime.RECESSION),
    ("COVID crash",    "2020-02-01", "2020-04-30", Regime.DEFLATION_SCARE),
    ("Inflation surge","2021-11-01", "2022-06-30", Regime.INFLATION_ACCEL),
    ("Real-yield shock","2022-06-01", "2022-10-31", Regime.REAL_YIELD_SHOCK),
    ("Risk-on 2019",   "2019-01-01", "2019-12-31", Regime.RISK_ON),
    ("Risk-on 2023",   "2023-01-01", "2023-12-31", Regime.RISK_ON),
]

pass_count = 0
for name, start, end, expected in episodes:
    mask = (probs.index >= pd.Timestamp(start)) & (probs.index <= pd.Timestamp(end))
    episode = probs[mask]
    if len(episode) == 0:
        print(f"  [SKIP] {name:20s}: no data in range")
        continue
    
    mean_probs = episode.mean()
    top2 = mean_probs.nlargest(2).index.tolist()
    dominant_regime = mean_probs.idxmax()
    dominant_pct = mean_probs.max() * 100
    
    passed = expected.value in top2
    status = "PASS" if passed else "FAIL"
    if passed:
        pass_count += 1
    
    print(f"  [{status}] {name:20s} ({start[:7]} to {end[:7]})")
    print(f"         Expected: {expected.value}")
    print(f"         Got:      {dominant_regime} ({dominant_pct:.1f}%) | top2: {top2}")
    print(f"         All probs: {dict(mean_probs.round(3).astype(float))}")
    print()

print("=" * 70)
print(f"RESULT: {pass_count}/6 episodes passed")
if pass_count >= 5:
    print("VERDICT: ACCEPTABLE (>= 5/6 per spec)")
elif pass_count >= 4:
    print("VERDICT: BORDERLINE — threshold tuning recommended")
else:
    print("VERDICT: FAILED — tune regime thresholds")
print("=" * 70)

# Save regime tape
tape_path = ".omo/evidence/task-12-regime-tape.csv"
import os
os.makedirs(".omo/evidence", exist_ok=True)
tape = probs.copy()
tape["dominant"] = dominant
tape.to_csv(tape_path, index_label="date")
print(f"\nRegime tape saved to {tape_path} ({len(tape)} rows)")
