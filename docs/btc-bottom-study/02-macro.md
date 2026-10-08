# Q2: macro context at BTC bottoms (wave 2b, g1)

- **Frame:** `data/cache/btc_bottoms/frame.parquet`, sha256
  `7e1107e2e653e493af552efdc516e99dd020a0855e73d3b4d1d917dc8247087e` (verified before the run; frozen, no refresh).
- **`main` at run time:** `5566d3a` (revision run; first run on `34af522`, numbers unchanged).
- **Reproduce** (from the repo root, i.e. a checkout that shares the frozen cache):

```bash
MARKETPULSE_DATA_DIR=$PWD/data/cache python -m src.research.btc_bottoms.macro_overlay
```

  In a separate worktree, point `MARKETPULSE_DATA_DIR` at the checkout that holds the frozen
  `data/cache/btc_bottoms/frame.parquet` (the runner verifies the sha256 and aborts on mismatch, so a wrong
  path fails loudly rather than silently).
- **Runtime:** ~155 s, fully offline (no network, no refresh, no keys used).
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
NaN where an input is unknown (warm-up, coverage gaps) — never False-by-default. Data-vintage note: the FRED
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
| **M5 (primary, < 0)** | 23/61 = 0.38 | 26/61 = 0.43 | 59/61 = 0.97 | 0/61 = 0.00 | 0/61 = 0.00 | 209/898 = 0.23 | **1** |
| M5 < 0.5 (extra) | 61/61 = 1.00 | 57/61 = 0.93 | 61/61 = 1.00 | 0/61 = 0.00 | 28/61 = 0.46 | 475/898 = 0.53 | 3 |
| M5 < 1.0 (extra) | 61/61 = 1.00 | 61/61 = 1.00 | 61/61 = 1.00 | 0/61 = 0.00 | 61/61 = 1.00 | 687/898 = 0.77 | 3 |

**The pre-registered result first.** The four "easing" conditions (M1, M2, M3a, M3b) do **not** distinguish
the cycle lows from other deep-drawdown days: their window shares sit at or below the deep-drawdown background
in most events (M1: 0.28 / 0.44 / 0.28 vs 0.46 background; M3b: 0.31 / 0.00 / 0.43 vs 0.58). Two episodes are
actively *contrarian* to the easing story: into the 2015 low the dollar was rising (M2 true on 1/61 days) and
into 2018 credit was tightening and liquidity falling (M3b and M4 true on 0/61 days). The **primary**
valuation condition, M5 (`mvrv_z < 0`), held on 0.38 / 0.43 / 0.97 of window days at the three A lows against
a 0.23 background — a real but uneven gap, majority in only **1 of 3** A lows, and **0/61 at the 2026 low**
(`mvrv_z` was +0.23 there). The M5 extras are monotone *loosenings* of that threshold, decided in the plan as
robustness variants: a looser threshold is trivially true more often, so only the gap to the background
matters — `< 0.5` reads about 0.97 vs 0.53, and `< 1.0` reads 1.00 vs 0.77, i.e. barely a gap. The "3 of 3
majority" reading belongs to those loosened thresholds and depends on a threshold chosen after the history was
known; it is not the pre-registered result.

**Why "true at lows" is not yet a bottom signal.** A condition that is true for most of a drawdown is true at
the bottom by construction, and also months before and after it: even the primary M5 was true on 23% of *all*
deep-drawdown days. Descriptively that makes it a *state* label ("BTC is cheap"), not a *timer*; the relevant
question is precision -- of the days the condition fires, how many precede a confirmed bottom within the
evaluation window -- which is what the combination table below measures, with its base rate (0.110 for set A)
alongside, and lift is still only k-of-n with n = 3 cycle events.

### Funding, 2026 episode only (descriptive; ~1 year of history, not tested)

Over the 95 days from the 2026-06-30 low to the last frame row: mean daily total funding +0.0155% (median
+0.0143%, min -0.0134%, max +0.0701%), negative on 12/95 = 12.6% of days. Perp positioning was, on average,
mildly long-pay through the recovery -- no capitulation-style negative-funding regime.

## 4b Declared combinations vs the first signal alone

Evaluated with the study engine (`study.evaluate` on the ANDed fire series, the same engine
`evaluate_combination` uses) with `config_for(horizon)` defaults, placebo (2000 circular shifts, seed 42,
add-one p), leave-one-out and registry sweeps (signals only). **Macro family denominator: 6 conditions + 6
combinations.** Labels come from g4's frozen `labels.py` (plan section 6, verbatim). Combos have no
pre-registered sweep grid, so their `sweep_median_lift` input is NaN and the frozen rule reads every
combination that meets the hit criterion as **"cannot evaluate"** — kept as the rule demands; no sweep was
invented to rescue a label. `fire-day share` = fraction of all frame days the series is on; `episodes/year` =
episode starts per year over the frame (both computed once, not per set). Set B has n = 1 event, below the
rule's minimum of 2 evaluable, so its rows read "cannot evaluate" by construction.

Set A (n = 3 bear bottoms):

| series | fire share | eps/yr | hits | episodes | precision | base | lift | placebo p | LOO min hit | sweep med | **label** |
|---|---|---|---|---|---|---|---|---|---|---|---|
| C1 fgi_extreme_streak & M3a | 0.034 | 1.08 | 2/3 | 13 | 0.308 | 0.110 | 2.81 | 0.113 | 0.50 | -- | cannot evaluate |
| fgi_extreme_streak alone | 0.120 | 1.49 | 2/3 | 18 | 0.111 | 0.110 | 1.01 | 0.568 | 0.50 | 1.52 | weak |
| C2 dd_ath & M1 | 0.156 | 1.25 | 3/3 | 15 | 0.267 | 0.110 | 2.43 | 0.156 | 1.00 | -- | cannot evaluate |
| dd_ath alone | 0.315 | 0.66 | 1/3 | 8 | 0.125 | 0.110 | 1.14 | 0.512 | 0.00 | 1.56 | no evidence |
| C3 mayer_multiple & M4 | 0.045 | 0.91 | 2/3 | 11 | 0.182 | 0.110 | 1.66 | 0.368 | 0.50 | -- | cannot evaluate |
| mayer_multiple alone | 0.144 | 1.00 | 1/3 | 12 | 0.083 | 0.110 | 0.76 | 0.659 | 0.00 | 0.00 | no evidence |
| C4 washout_stabilise & M3b | 0.022 | 1.00 | 2/3 | 12 | 0.250 | 0.110 | 2.28 | 0.100 | 0.50 | -- | cannot evaluate |
| washout_stabilise alone | 0.053 | 1.33 | 2/3 | 16 | 0.125 | 0.110 | 1.14 | 0.475 | 0.50 | 1.37 | weak |
| C5 dd_ath & M5 | 0.084 | 0.58 | 3/3 | 7 | 0.429 | 0.110 | 3.91 | 0.058 | 1.00 | -- | cannot evaluate |
| C6 capitulation_vol & M2 | 0.007 | 1.74 | 2/3 | 21 | 0.095 | 0.110 | 0.87 | 0.676 | 0.50 | -- | cannot evaluate |
| capitulation_vol alone | 0.015 | 2.91 | 3/3 | 35 | 0.143 | 0.110 | 1.30 | 0.309 | 1.00 | 1.47 | weak |

Pooled A+B (n = 4, shown only next to A and B) and S (70 swings): every row is in the runner output; on pooled
A+B the combos read C1 3/4 lift 2.55 p=0.081, C2 4/4 lift 2.21 p=0.0999, C4 3/4 lift 2.21 p=0.075, C5 3/4 lift
2.84 p=0.083 — all still "cannot evaluate" (NaN sweep). On S every combination *reduces* coverage versus its
signal alone (AND is stricter) while mostly *raising* precision (C5 13/70 at 0.889 vs dd_ath 18/70 at 0.882;
C3 15/70 at 0.923 vs mayer 17/70 at 0.833), with several small swing placebo p-values (C3 0.0050, C5 0.0110,
capitulation_vol alone 0.0025) and labels "weak"/"cannot evaluate" throughout.

### Why combo hit counts are not comparable to the signal alone (fragmentation)

`dd_ath` is a persistent state (on 31.5% of all days; 0.66 episodes/year): its episode *starts* rarely fall
inside a bottom pre-window — only 2015's does — so alone it reads 1/3 even though the state itself was on
through the 2018 and 2022 declines. Gating with M5 *restarts* the state later: C5's in-window starts are
2015-01-13, 2018-11-20 (25 days before that low) and 2022-06-14 (160 days before the low, with BTC then far
above the eventual 15.8k). A jump from 1/3 to 3/3 therefore partly reflects *when* a gated episode begins, and
a gate that flickers manufactures more starts (see the eps/yr column). This is why the hit column alone is not
evidence: read it with lift, placebo and the diagnostics. By those, C2's 3/3 with placebo p = 0.156 is
unremarkable — a third of random shifts of its fire pattern do as well.

### POST-PLAN EXTRA (decided after seeing results; NOT a label and cannot change one)

Combo robustness: the FIRST signal's registry grid swept with the macro gate held fixed (set A; never-firing
cells excluded and counted):

| combo | cells | never-firing | median lift | min | max |
|---|---|---|---|---|---|
| C1 (fgi_extreme_streak & m3a) | 12 | 0 | 1.03 | 0.00 | 2.81 |
| C2 (dd_ath & m1) | 7 | 0 | 2.43 | 1.74 | 3.91 |
| C3 (mayer_multiple & m4) | 6 | 0 | 1.49 | 0.00 | 3.04 |
| C4 (washout_stabilise & m3b) | 36 | 0 | 2.28 | 0.00 | 3.51 |
| C5 (dd_ath & m5) | 7 | 0 | 6.84 | 3.91 | 6.84 |
| C6 (capitulation_vol & m2) | 12 | 0 | 1.04 | 0.70 | 2.61 |

Had a grid been pre-registered, C2 (2.43), C3 (1.49), C4 (2.28) and C5 (6.84) would clear the rule's 1.2
sweep-median bar, and C1 (1.03) and C6 (1.04) would not. This was decided after the results were seen, is
reported for context only, and changes no label: under the frozen rule every combination remains "cannot
evaluate".

## The 2026 question (set P, report-only; P never enters any rate or label)

Fire days inside the 2026 episode span `[peak 2025-10-06, confirm 2026-08-21]`, mirroring g4's convention:

| series | fire days | first fire | days before low | before confirm | close at first fire | low close | return to last row |
|---|---|---|---|---|---|---|---|
| C1 fgi_extreme_streak & M3a | 43 | 2025-11-25 | 217 | 269 | 87,342 | 58,559 | -3.3% |
| fgi_extreme_streak alone | 149 | 2025-11-09 | 233 | 285 | 104,720 | 58,559 | -19.3% |
| C2 dd_ath & M1 | **4** | **2026-06-27** | **3** | 55 | 59,940 | 58,559 | **+41.0%** |
| dd_ath alone | 15 | 2026-06-05 | 25 | 77 | 60,923 | 58,559 | +38.7% |
| C3 mayer_multiple & M4 | 57 | 2026-01-31 | 150 | 202 | 78,621 | 58,559 | +7.5% |
| mayer_multiple alone | 87 | 2025-11-20 | 222 | 274 | 86,632 | 58,559 | -2.5% |
| C4 washout_stabilise & M3b | 44 | 2025-12-05 | 207 | 259 | 89,388 | 58,559 | -5.5% |
| washout_stabilise alone | 91 | 2025-12-02 | 210 | 262 | 91,350 | 58,559 | -7.5% |
| **C5 dd_ath & M5** | **0** | -- | -- | -- | -- | 58,559 | -- |
| C6 capitulation_vol & M2 | 1 | 2026-02-05 | 145 | 197 | 62,702 | 58,559 | +34.8% |
| capitulation_vol alone | 3 | 2025-10-10 | 263 | 315 | 113,214 | 58,559 | -25.3% |

**The point that matters for the owner's question:** **C5 — the strongest series on set A — had ZERO fire
days in the 2026 episode** (M5, `mvrv_z < 0`, was true on no day; `mvrv_z` was +0.23 at the low and 1.02 on
the last row). The best-looking backtest combination would have been silent at the 2026 low. The macro gate
that actually fired near the low was C2 (dd_ath & M1: first fire 2026-06-27, 3 days before the low, 4 fire
days, close 59,940 vs the 58,559 low, +41.0% to the last row) — but C2's set-A placebo p of 0.156 says its
3/3 is unremarkable, and its label is "cannot evaluate" like every combo.

## Current reading (last frame row, 2026-10-02) for the case-file author

M1 = 0 (real yields rising over 21d), M2 = 0 (dollar rising), M3a = 0 (VIX not faded vs its 21d max), M3b = 1
(credit easing), M4 = 0 (net liquidity falling over 63d), M5 = 0 (`mvrv_z` = 1.017 on the last row, so all
three M5 variants read 0: valuation is above every threshold as of 2026-10-02). Interpretation belongs to
Q3's case files; these are inputs, not a forecast.

## Deviations and extras

1. **Combination sweeps absent by pre-registration.** No grid was registered for macro conditions or
   combinations, so `sweep_median_lift` is NaN in their label inputs and the frozen rule reads them as
   "cannot evaluate". Kept exactly as the rule demands; the grid sweep above is labelled a post-plan extra
   that cannot change any label.
2. **M5 thresholds 0.5 and 1.0** are the plan's declared robustness extras; the narrative leads with the
   pre-registered primary (< 0) and treats the extras as monotone loosenings.
3. **Comparator construction (my judgement, documented).** "All other days inside deep drawdowns" excludes
   every event window -- cycle A, B, P *and* all 70 swing windows -- so the 2026 episode does not sit inside
   its own baseline and swing windows do not double-count cycle days.
4. **Windows clipped to the frame start** (2015 low - 60d < 2014-09-17): n counts only in-frame non-NaN days;
   the earliest swing event (2014-10-05) has n = 0 for the diff-based conditions and reports NaN, not 0.
5. No condition definition, threshold, combination, event set or metric was changed from the plan.
