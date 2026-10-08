# BTC bottom study: analysis plan

Written 2026-10-03, before any result of the study exists. Committed first so that every later number can be checked
against what was decided in advance.

**Question (owner):** after missing the 2026 low (close **$58,559 on 2026-06-30**, -53.06% from the $124,753 close high of
2025-10-06; last close in the frozen data $84,497 on 2026-10-02), which bottom signals, with which macro context, would have
flagged it, and how often do they cry wolf? This is a research tool, not advice. It cannot call a bottom in real time.

## 0. How honest is this pre-registration

Partly. The signal thresholds in `SIGNAL_REGISTRY` were written by builders (and a lead) who know BTC's history, and some are textbook
numbers (RSI 30, Mayer 0.8, Fear and Greed 25). The lead had seen MVRV-Z at the lows (about -0.2 to -0.5 at earlier lows, +0.2 at 2026) before
choosing a primary valuation threshold of 0, which is the textbook boundary, not a tuned value. So "primary = defaults" is discipline against
cherry-picking from the sweep, not independence from the data. Every report repeats this sentence.

## 1. Data freeze

- Frame: `data/cache/btc_bottoms/frame.parquet`, **sha256 `7e1107e2e653e493af552efdc516e99dd020a0855e73d3b4d1d917dc8247087e`**, 4399 rows,
  2014-09-17 to 2026-10-02, 31 columns. All three analyses read this same file. **Never refresh it during the study** (`build_frame(refresh=False)`).
  Set `MARKETPULSE_DATA_DIR=<repo>/data/cache` so every worktree sees the same cache. Verify the hash at the start of every run and
  print it in every output.
- Build inputs: events = `find_bottoms(frame, horizon)` with defaults; signals = `compute_signals(asof(frame, 5))`; macro conditions are computed
  from `asof(frame, 5)` columns; `net_liquidity` is recomputed AFTER `asof` from the filled columns (the stored column is empty on Sundays and
  Mondays). `main` commit used is printed in every report.
- No synthetic data, no `mvrv.csv`, no `on_chain.fetch_mvrv`. MVRV-Z comes from the frame (Coin Metrics community, real).

## 2. Event sets (hindsight labels from `events.py`)

| Set | Definition | n | Use |
|---|---|---|---|
| A | cycle, `severity == "bear_bottom"` | 3 (2015-01-14, 2018-12-15, 2022-11-21) | primary cycle result |
| B | cycle, `deep_correction`, not provisional | 1 (2021-07-20) | reported separately, never pooled silently |
| P | provisional 2026-06-30 | 1 | latest-episode view ONLY; never enters any rate, lift or placebo |
| S | swing, all | about 70, 50 nested in cycle spans | swing result; also report nested vs not nested |

Pooled A plus B (n = 4) may be shown only next to A and B. An event is *evaluable* for a signal if the signal is non-NaN somewhere in
`[bottom - pre_window, confirm]`; every rate is k of n_evaluable, and events dropped for NaN are listed (the Fear and Greed series starts
2018-02, the 200-week average needs 1400 days, funding starts 2025-10).

## 3. Q1: signals alone (owner: g4, `run_study.py`, `01-signals.md`)

All 19 registry signals at their **registry default** thresholds, `_fire` forms, evaluated with `study.config_for(horizon)` defaults.
Per signal and set: hit rate (k of n_evaluable), usable lead (fires on or before `confirm_date`) and signed lead in days, late-only and
missed counts, episodes, precision, base rate, lift, placebo (2000 shifts, seed 42, add-one p), sweep over the registry grid
(median / min / max of lift, cells tried), leave-one-cycle-out, forward 30/90/180-day returns after episode starts vs all days (with `n_valid`)
and further drawdown. **Cells in the primary family: 19 signals x 2 horizons = 38**; print this denominator.

**The 2026 question, answered separately for every signal (set P):** first fire date inside the 2026 episode relative to the low (2026-06-30) and
to confirmation (2026-08-21); close at first fire vs the low; the return from first fire to the last row; and whether the signal had a prior false
confirmation (the +30% bounce of 2026-05-10 was broken by the June low).

## 4. Q2: macro context (owner: g1, `macro_overlay.py`, `02-macro.md`)

Six conditions, fixed now. Definitions use `asof` columns, daily, causal:

| id | name | definition |
|---|---|---|
| M1 | real_yield_easing | `dfii10` 21-day change < 0 |
| M2 | dollar_easing | `dxy_ice` 21-day percent change < 0 |
| M3a | vix_fade | `vix` <= 0.8 x its trailing 21-day maximum |
| M3b | credit_easing | `baa10y` 21-day change < 0 |
| M4 | liquidity_up | `net_liquidity` 63-day change > 0 |
| M5 | valuation_low | `mvrv_z` < 0 (robustness only: 0.5 and 1.0) |

(a) *Descriptive:* for each event in A, B, P and for S, the share of days in `[bottom - 60, bottom]` on which each condition held, against the share
on all other days **inside deep drawdowns** (drawdown from ATH <= -40%), because lows occur in drawdowns and an all-days comparator would
flatter every condition. (b) *Declared combinations, exactly these six, no others*, evaluated with `study.evaluate_combination` and compared to the
first signal alone: C1 `fgi_extreme_streak` AND M3a; C2 `dd_ath` AND M1; C3 `mayer_multiple` AND M4; C4 `washout_stabilise` AND M3b;
C5 `dd_ath` AND M5; C6 `capitulation_vol` AND M2. Denominator for the macro family: 6 conditions plus 6 combinations.
Funding rate (one year of history) is described for the 2026 episode only; it is not tested.

## 5. Q3: case files and the current reading (owner: g3, `dossiers.py`, `03-case-files.md`)

For each cycle low and the 2026 episode: a table at peak, bottom minus 90 / 60 / 30 / 7 days, bottom, confirm and the last row, showing
close, drawdown, all 19 signal readings and fire flags, M1 to M5, `mvrv_z`, `fgi_value`, real yield level, `baa10y`, `net_liquidity`; and the
timeline of false confirmations (2018: 3, 2022: 1, 2026: 1) with dates. Then the **current reading** as of the last frame row: which signals and macro
conditions are on and since when. It is descriptive and states it is not a forecast. It must also repeat the standing risk flag from
`docs/agent-tasks/PICKUP.md`: after 13-week real-yield surges of 50bp or more, the next 13 weeks of BTC were weaker (n small, overlapping), and
that bucket is where we are now.

## 6. Language rule for conclusions (fixed now)

Only these labels may be used about a signal:
- **candidate**: usable lead in at least 2 of the evaluable events of set A, lift >= 1.5 with >= 3 episodes, placebo add-one p_lift <= 0.10, sweep
  median lift >= 1.2, and leave-one-out keeps hit rate >= 0.5.
- **weak**: meets the hit criterion but fails the lift, placebo or robustness test.
- **no evidence**: anything else.
- **cannot evaluate**: fewer than 2 evaluable events.
Never "validated", "predictive", "proven" or "works". Every table shows counts. The report states plainly that with n = 3 in set A nothing here is
significance, and that the thresholds were set after the history was known.

## 7. Standing limits (repeat in every report)

Hindsight labels; `confirm_date` is optimistic (a +30% bounce occurred before the final low in 2018, 2022 and 2026); the 2026 low is provisional and can
still move; MVRV-Z amplitude has decayed across cycles; macro series that are revised after release are excluded; Coin Metrics restates its latest
days (treat the last 5 rows of on-chain columns as provisional); BTC prices come from Yahoo; overlapping forward windows are not independent draws;
no trading costs or sizing are modelled; yield-curve snapshots are not used in this study.

## 8. Ownership and review

Each owner writes only its own module, tests (small, synthetic, deterministic) and part file, prints the frame hash and `main` commit, and gives the
commands to reproduce. After all three land, `check` re-derives numbers and methodology and `check2` audits leakage, point-in-time handling and
whether every claim obeys section 6. The lead integrates and reports to the owner.
