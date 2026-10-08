# Q1: the 19 signals, alone (plan section 3)

Part of the BTC bottom study. Everything below comes from one run of one frozen dataset against one
pre-registered plan.

- Frame: `data/cache/btc_bottoms/frame.parquet`, sha256
  `7e1107e2e653e493af552efdc516e99dd020a0855e73d3b4d1d917dc8247087e` (4399 rows, 2014-09-17 to 2026-10-02).
- Ran on `feat/btc-bottoms-run-study` @ `d75a07e` (branch from `main` @ `34af522`).
- Reproduce:
  `MARKETPULSE_DATA_DIR=$PWD/data/cache python -m src.research.btc_bottoms.run_study`
  (runtime ≈ 3 min 40 s; results also written to `data/cache/btc_bottoms/results/signals.json`).
- Primary family: **38 cells** (19 signals × 2 horizons); the sweep tried **176 cells** (robustness only).

**Standing limits (plan section 7).** Hindsight labels; `confirm_date` is optimistic (a +30% bounce occurred
before the final low in 2018, 2022 and 2026); the 2026 low is provisional and can still move; MVRV-Z amplitude
has decayed across cycles; macro series revised after release are excluded; Coin Metrics restates its latest
days; BTC prices come from Yahoo; overlapping forward windows are not independent draws; no trading costs or
sizing are modelled; yield-curve snapshots are not used.

**Honesty sentence (plan section 0).** Pre-registration here is only partly honest: the signal thresholds were
written by builders who know BTC's history, and some are textbook numbers. "Primary = defaults" is discipline
against cherry-picking from the sweep, not independence from the data. With 3 events in set A (and only 2
evaluable for the sentiment signals, whose history starts 2018-02), nothing below is significance. The labels
rank evidence; they do not prove anything.

## What the labels say (set A = 3 cycle bear bottoms; B and S as stated)

| signal | A | B (n=1) | S (swings) |
| :--- | :--- | :--- | :--- |
| fgi_mean_30 | **candidate** | cannot evaluate | weak |
| rsi_14 | **candidate** | cannot evaluate | **candidate** |
| fgi / fgi_extreme_streak | weak | cannot evaluate | **candidate** |
| everything else (15) | weak or no evidence | cannot evaluate | weak |

Every B label is "cannot evaluate" by rule (one event). Full per-signal table with counts is in
`signals.json` and the rendered output; the summary above is the whole story: **2 of 19 candidate on A,
12 weak, 5 no evidence.** A "weak" here usually means: it does fire near lows, but it cries wolf too often
(lift < 1.5 or placebo p_lift > 0.10) or is not robust across the threshold grid.

Set A detail for the two candidates (counts visible, k of n):

- **fgi_mean_30** — 30-day mean Fear & Greed ≤ 25: covered **2/2** evaluable (2015 dropped: no FGI data),
  mean lead **86 days**, lift **3.04**, placebo add-one p_lift **0.035**, sweep median lift **2.13**
  (min 0.0, max 3.04 across 5 cells), leave-one-out min hit rate **1.0**. The median episode still saw a
  **further −19% drawdown** before the bottom; the 90-day forward return after episode starts had median
  −1.0% (n=12 episodes with valid windows) vs +7.9% unconditional (n=4309 days).
- **rsi_14** — daily RSI(14) ≤ 30: covered **3/3**, mean lead **99 days**, lift **1.96**, placebo p_lift
  **0.046**, sweep median lift **2.12** (min 1.30 — every grid cell stays above 1.2), leave-one-out min
  hit rate **1.0**. But the median further drawdown from an episode start was **−37%**, and the 90-day
  forward median after starts was +11.0% (n=28) vs +7.9% unconditional.

The tension to hold onto: the "candidate" labels say *early warning*; the forward numbers say *expensive
to act on alone*. A 99-day average lead with −37% median further drawdown is a research flag, not an entry.

On the swing set S (70 events, 42 evaluable for the FGI era): **fgi** (25/42, lift 2.28, LOO min 0.59),
**fgi_extreme_streak** (29/42, lift 2.20, LOO min 0.68) and **rsi_14** (36/70, lift 1.95, LOO min 0.51)
are candidates; the deep-valuation signals (dd_ath 18/70, mayer 17/63) stay weak mostly because
leave-one-out drops below 0.5 — single swing clusters carry their hit rates.

## The 2026 question, signal by signal (set P; report-only, never in any rate above)

The low: 2026-06-30 (close $58,559); confirmation 2026-08-21. "Premium" = close at the first fire vs the
low close; "return" = first fire to the last frame row ($84,497 on 2026-10-02).

| signal | first fire | days before low | premium vs low | return to last row | prior false confirmation* |
| :--- | :--- | ---: | ---: | ---: | :--- |
| dd_ath | 2026-06-05 | 25 | **+4.0%** | **+38.7%** | no |
| close_vs_sma200w | 2026-06-05 | 25 | **+4.0%** | **+38.7%** | no |
| rvol_compress_after_spike | 2026-04-04 | 87 | +14.9% | +25.6% | yes |
| mayer_multiple | 2025-11-20 | 222 | +47.9% | −2.5% | yes |
| fgi_mean_30 | 2025-11-24 | 218 | +50.7% | −4.3% | yes |
| rsi_14 / rsi_14w | 2025-11-14/16 | ~227 | ~+61% | ~−10% | yes |
| dd_90d, washout, fgi, streaks, volume signals | Oct–Dec 2025 | 210–267 | +50% to +113% | −7% to −32% | yes |
| days_since_ath | never | — | — | — | — |

\* fired during the drawdown on or before 2026-05-10, the +30% bounce the plan records as broken by the
June low.

Read plainly:

- **Every fast signal fired months early and stayed fired through another 20–30% of drawdown.** For all of
  them the 2026 episode was a prior false confirmation first (they fired on the May bounce), which is
  exactly what "weak on cry-wolf" predicted.
- **The deep-valuation signals were late and right in 2026**: `dd_ath` (−50% from ATH) and
  `close_vs_sma200w` (below the 200-week average) first fired 2026-06-05, 25 days before the low, at just
  +4% above the low close, and +38.7% to the last row. But these are precisely the signals with the
  *least* A-set evidence (dd_ath 1/3 covered; close_vs_sma200w 1/2 → "no evidence"). One episode is not a
  validation, and the plan forbids reading it as one.
- `days_since_ath` never fired in 2026: the ATH (2025-10-06) never got 365 days old before the low — a
  signal with 2/3 coverage on A was silent exactly when the owner needed it.

## What this evidence does NOT support

- It does not support acting on any single signal. Both A-set candidates had median further drawdowns of
  −19% (fgi_mean_30) and −37% (rsi_14) from episode starts.
- It does not support calling dd_ath/close_vs_sma200w "good" because of 2026: their A-set evidence is the
  weakest of the nineteen, and the 2026 view is report-only by rule.
- It does not support any probabilistic claim ("X% chance of a bottom"): with 2–3 evaluable events, hit
  rates move in jumps of 1/n, and the placebo bounds luck, not truth.
- It does not support swing-set conclusions for pre-2018 history: the FGI-era swings (42 of 70) carry the
  sentiment candidates.

## Deviations and extras

1. **`labels.py` second commit (`1ce84df`)** before any result was run: the hit criterion is now evaluated
   before the NaN gate, so a never-firing signal is "no evidence" (informative absence) rather than
   "cannot evaluate". Reason: writing the runner surfaced that a 0-episode signal has NaN lift *because*
   it never fired. The plan text order is otherwise followed exactly; all boundaries remain inclusive.
2. **Prior-false-confirmation definition** (plan gives the date, not the window): any fire day in
   `[peak_date, 2026-05-10]`. "Inside the 2026 episode" = the event's own `[peak_date, confirm_date]` span.
3. **Benign `RuntimeWarning`** from `study.sweep`'s all-NaN medians (grid cells where a signal never fires)
   is suppressed inside `run_study.sweep_signal` with a comment; `study.py` was not touched (outside this
   task's territory). The NaN results themselves are kept.
4. **Pooled A+B** is computed and reported next to A and B as the plan allows, marked "pooled, descriptive
   only"; it never receives a label.

## Surprises

- How cleanly the 2026 episode splits the panel: fast signals = early but −20/−30% wrong-footed; depth
  signals = 25 days early at +4% premium but statistically unsupported on A.
- `rsi_14w` (weekly RSI) adds nothing over daily RSI here (weak on A, lead 22 vs 99 days but 2/3 coverage).
- The swing-set candidates are all sentiment/momentum; no valuation signal survives leave-one-out on S.

## What the analysis cannot tell us

Whether any of this holds for the next cycle. Set A has three events; two of the sentiment signals have
two evaluable ones. The labels rank what already happened. The 2026 low is provisional. The thresholds
were chosen with hindsight-adjacent knowledge. This is a research tool that makes its own weakness
visible — not a bottom-calling system.
