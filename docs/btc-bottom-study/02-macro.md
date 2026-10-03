# Q2: macro context at BTC bottoms (wave 2b, g1)

- **Frame:** `data/cache/btc_bottoms/frame.parquet`, sha256
  `7e1107e2e653e493af552efdc516e99dd020a0855e73d3b4d1d917dc8247087e` (verified before the run; frozen, no refresh).
- **`main` at run time:** `34af52282d3e9135d13a18dae779fb2ad160b242`.
- **Reproduce** (worktree `../marketpulse-wt/btc-macro`, branch `feat/btc-bottoms-macro-overlay`):

```bash
MARKETPULSE_DATA_DIR=/home/yl/proj/marketpulse/data/cache \
  /home/yl/proj/marketpulse/.venv/bin/python -m src.research.btc_bottoms.macro_overlay
```

- **Runtime:** 144.3 s, fully offline (no network, no refresh, no keys used).
- **Events:** A = 3 (2015-01-14, 2018-12-15, 2022-11-21), B = 1 (2021-07-20), P = 1 (2026-06-30, provisional,
  latest-episode view only), S = 70 swing lows. Pooled A+B (n = 4) is shown only next to A and B.

**Standing limits (plan section 7, repeated).** Hindsight labels; `confirm_date` is optimistic (a +30% bounce
occurred before the final low in 2018, 2022 and 2026); the 2026 low is provisional and can still move; MVRV-Z
amplitude has decayed across cycles; macro series that are revised after release are excluded; Coin Metrics
restates its latest days (treat the last 5 rows of on-chain columns as provisional); BTC prices come from Yahoo;
overlapping forward windows are not independent draws; no trading costs or sizing are modelled; yield-curve
snapshots are not used in this study. **Pre-registration honesty (plan section 0):** the signal thresholds in
`SIGNAL_REGISTRY` were written by builders (and a lead) who know BTC's history, and some are textbook numbers;
"primary = defaults" is discipline against cherry-picking from the sweep, not independence from the data. With
n = 3 in set A nothing here is significance.

## Conditions (pre-registered, plan section 4)

| id | definition | first valid | % non-null (4399 rows) |
|---|---|---|---|
| M1 real_yield_easing | `dfii10` 21d change < 0 | 2014-10-08 | 99.52 |
| M2 dollar_easing | `dxy_ice` 21d pct change < 0 | 2014-10-08 | 99.52 |
| M3a vix_fade | `vix` <= 0.8 × trailing 21d max | 2014-10-07 | 99.55 |
| M3b credit_easing | `baa10y` 21d change < 0 | 2014-10-08 | 99.52 |
| M4 liquidity_up | `net_liquidity` 63d change > 0 | 2014-11-19 | 98.57 |
| M5 valuation_low | `mvrv_z` < 0 | 2014-09-17 | 100.00 |
| M5 extra (< 0.5) | robustness only | 2014-09-17 | 100.00 |
| M5 extra (< 1.0) | robustness only | 2014-09-17 | 100.00 |

All conditions are causal (trailing windows only; prefix-invariance and future-poisoning are unit-tested),
NaN where an input is unknown (warm-up, coverage gaps) — never False-by-default. Note on data vintage: the FRED
dollar column (`dxy`, DTWEXBGS) is first published ~3 days after its observation date and is therefore lagged
**+5 days** in the frame; M2 is defined on the yahoo ICE dollar index (`dxy_ice`, same-day) exactly as the plan
specifies, so no condition consumes the stale FRED dollar column.

## 4a Descriptive: were the conditions true at the lows?

Share of days in `[bottom - 60, bottom]` on which each condition held (k of n non-NaN days; windows clipped to
the frame start 2014-09-17), against the share on all *other* days inside deep drawdowns (drawdown from running
ATH <= -40%, all event windows removed; 898 comparator days).

| condition | A 2015-01-14 | A 2018-12-15 | A 2022-11-21 | B 2021-07-20 | P 2026-06-30 | comparator | majority in A (of 3) |
|---|---|---|---|---|---|---|---|
| M1 | 17/61 = 0.28 | 27/61 = 0.44 | 17/61 = 0.28 | 34/61 = 0.56 | 10/61 = 0.16 | 412/898 = 0.46 | 0 |
| M2 | 1/61 = 0.02 | 6/61 = 0.10 | 31/61 = 0.51 | 22/61 = 0.36 | 10/61 = 0.16 | 469/898 = 0.52 | 1 |
| M3a | 16/61 = 0.26 | 22/61 = 0.36 | 14/61 = 0.23 | 39/61 = 0.64 | 11/61 = 0.18 | 241/898 = 0.27 | 0 |
| M3b | 19/61 = 0.31 | 0/61 = 0.00 | 26/61 = 0.43 | 37/61 = 0.61 | 56/61 = 0.92 | 518/898 = 0.58 | 0 |
| M4 | 44/57 = 0.77 | 0/61 = 0.00 | 2/61 = 0.03 | 23/61 = 0.38 | 43/61 = 0.70 | 451/898 = 0.50 | 1 |
| M5 | 23/61 = 0.38 | 26/61 = 0.43 | 59/61 = 0.97 | 0/61 = 0.00 | 0/61 = 0.00 | 209/898 = 0.23 | 1 |
| M5 < 0.5 (extra) | 61/61 = 1.00 | 57/61 = 0.93 | 61/61 = 1.00 | 0/61 = 0.00 | 28/61 = 0.46 | 475/898 = 0.53 | 3 |
| M5 < 1.0 (extra) | 61/61 = 1.00 | 61/61 = 1.00 | 61/61 = 1.00 | 0/61 = 0.00 | 61/61 = 1.00 | 687/898 = 0.77 | 3 |

**What this says.** The four "easing" conditions (M1, M2, M3a, M3b) do **not** distinguish the cycle lows from
other deep-drawdown days: their window shares sit at or below the deep-drawdown background in most events
(e.g. M1 at the three A lows: 0.28 / 0.44 / 0.28 vs 0.46 background; M3b at 0.31 / 0.00 / 0.43 vs 0.58). Two
episodes are actively *contrarian* to the easing story: into the 2015 low the dollar was rising (M2 true on
1/61 days) and into 2018 credit was tightening and liquidity falling (M3b and M4 true on 0/61 days). What does
separate lows from other drawdown days is **valuation** (M5 family): `mvrv_z < 1.0` held on 61/61 days at every
A low and at P (and < 0.5 on >= 57/61), against a 0.77 / 0.53 background. The 2021 mid-bull B event shows the
mirror image (M5 false on all 61 days), consistent with it not being a valuation bottom.

**Why "true at lows" is not yet a bottom signal.** A condition that is true for most of a drawdown is true at
the bottom by construction, and also months before and after it: `mvrv_z < 1.0` was true on 77% of *all*
deep-drawdown days. Descriptively that makes it a *state* label ("BTC is cheap"), not a *timer*; the relevant
question is precision -- of the days the condition fires, how many precede a confirmed bottom within the
evaluation window -- which is what the combination table below measures, with its base rate (0.110 for set A)
alongside. The gap between a 0.97 share at the 2022 low and a 0.23 background is exactly the base-rate gap the
lift column quantifies, and lift is still only k-of-n with n = 3 cycle events.

### Funding, 2026 episode only (descriptive; ~1 year of history, not tested)

Over the 95 days from the 2026-06-30 low to the last frame row: mean daily total funding +0.0155% (median
+0.0143%, min -0.0134%, max +0.0701%), negative on 12/95 = 12.6% of days. Perp positioning was, on average,
mildly long-pay through the recovery -- no capitulation-style negative-funding regime.

## 4b Declared combinations vs the first signal alone

Evaluated with the study engine (`study.evaluate` on the ANDed fire series, the same engine
`evaluate_combination` uses) with `config_for(horizon)` defaults, placebo (2000 circular shifts, seed 42,
add-one p) and leave-one-out; sweeps exist only for signals (registry grid). **Macro family denominator:
6 conditions + 6 combinations.** `label` is the shared section-6 rule from g4's `labels.py`, which had **not
landed on `main`** at run time -- the label column therefore reads PENDING and the inputs are reported here;
the rule is not re-implemented in this module. Set B has n = 1 event (below the section-6 minimum of 2
evaluable), so its rows are anecdote by construction.

Set A (n = 3 bear bottoms):

| series | hits | episodes | precision | base | lift | placebo p | LOO min hit | sweep median lift |
|---|---|---|---|---|---|---|---|---|
| C1 fgi_extreme_streak & M3a | 2/3 | 13 | 0.308 | 0.110 | 2.81 | 0.113 | 0.50 | -- |
| fgi_extreme_streak alone | 2/3 | 18 | 0.111 | 0.110 | 1.01 | 0.568 | 0.50 | 1.52 |
| C2 dd_ath & M1 | 3/3 | 15 | 0.267 | 0.110 | 2.43 | 0.156 | 1.00 | -- |
| dd_ath alone | 1/3 | 8 | 0.125 | 0.110 | 1.14 | 0.512 | 0.00 | 1.56 |
| C3 mayer_multiple & M4 | 2/3 | 11 | 0.182 | 0.110 | 1.66 | 0.368 | 0.50 | -- |
| mayer_multiple alone | 1/3 | 12 | 0.083 | 0.110 | 0.76 | 0.659 | 0.00 | 0.00 |
| C4 washout_stabilise & M3b | 2/3 | 12 | 0.250 | 0.110 | 2.28 | 0.100 | 0.50 | -- |
| washout_stabilise alone | 2/3 | 16 | 0.125 | 0.110 | 1.14 | 0.475 | 0.50 | 1.37 |
| C5 dd_ath & M5 | 3/3 | 7 | 0.429 | 0.110 | 3.91 | 0.058 | 1.00 | -- |
| C6 capitulation_vol & M2 | 2/3 | 21 | 0.095 | 0.110 | 0.87 | 0.676 | 0.50 | -- |
| capitulation_vol alone | 3/3 | 35 | 0.143 | 0.110 | 1.30 | 0.309 | 1.00 | 1.47 |

Set B (n = 1, cannot-evaluate territory) and pooled A+B (n = 4, shown only next to A and B): see the runner
output for every row. Headlines on pooled A+B: C5 3/4 hits, lift 2.84, placebo 0.083; C2 4/4 hits, lift 2.21,
placebo 0.0999; C1 3/4, lift 2.55, placebo 0.081. Set S (70 swing lows): every combination *reduces* coverage
versus its signal alone (AND is stricter) while mostly *raising* precision -- e.g. C5 13/70 hits with precision
0.889 vs dd_ath alone 18/70 at 0.882; C3 15/70 at 0.923 vs mayer alone 17/70 at 0.833; several swing placebo
p-values are small (C3 0.0050, C5 0.0110, capitulation_vol alone 0.0025).

**Combos vs signals alone, in plain words.** Gating a price/positioning signal with a macro condition raised
both hit rate and lift on the three bear bottoms for C2, C3 and C5 (dd_ath alone 1/3; with M1 3/3 at lift 2.43;
with M5 3/3 at lift 3.91 and precision 0.429), and C5 is the only series in this part whose A-set inputs clear
the visible numeric bars simultaneously (leads 3 of 3 evaluable, lift 3.91, 7 episodes, placebo 0.058, LOO 1.00)
-- but combos have **no pre-registered sweep grid**, so their `sweep_median_lift` input is NaN (reported, not
faked), and with n = 3 none of this is significance. C6 (capitulation_vol & M2) got *worse* than its signal
alone on A (lift 0.87 vs 1.30): the dollar-easing gate removed the 2022 hit. On swings the trade is coverage
for precision, as AND must be.

## Current reading (last frame row, 2026-10-02) for the case-file author

M1 = 0 (real yields rising over 21d), M2 = 0 (dollar rising), M3a = 0 (VIX not faded vs its 21d max), M3b = 1
(credit easing), M4 = 0 (net liquidity falling over 63d), M5 = 0 (`mvrv_z` = 1.017 on the last row, so all
three M5 variants read 0: valuation is above every threshold as of 2026-10-02). Interpretation belongs to
Q3's case files; these are inputs, not a forecast.

## Deviations and extras

1. **Labels PENDING.** `labels.py` was not on `main` at run time; the module calls a stub that returns the
   marker string instead of a label (the rule is deliberately not re-implemented). Swap-in is a one-line
   import change; every label *input* is printed above so the labels can be attached without re-running the
   study.
2. **Combination sweeps absent by design.** No grid was pre-registered for macro conditions or combinations,
   so `sweep_median_lift` is NaN in their label inputs. If the section-6 rule reads a NaN sweep as failing the
   robustness criterion, no combination can be labelled above "weak" -- that determination belongs to
   `labels.py`, not here.
3. **M5 thresholds 0.5 and 1.0** are the plan's declared robustness extras, reported as extras (labelled) in
   every table.
4. **Comparator construction (my judgement, documented).** "All other days inside deep drawdowns" excludes
   every event window -- cycle A, B, P *and* all 70 swing windows -- so the 2026 episode does not sit inside
   its own baseline and swing windows do not double-count cycle days.
5. **Windows clipped to the frame start** (2015 low - 60d < 2014-09-17): n counts only in-frame non-NaN days;
   the earliest swing event (2014-10-05) has n = 0 for the diff-based conditions and reports NaN, not 0.
6. No condition definition, threshold, combination, event set or metric was changed from the plan.
