# Follow-ups found during the lint work (not fixed by T10a/T10b — behavior changes)

Found by the T10b analysis (2026-09-29). Each is real but is a behavior change, so it is **not** part of the lint commits.
Line numbers are as of `main` at the time; re-check before editing.

## 1. Yield-curve backfill wrote snapshots under the wrong date — **FIXED** (`7a4c905`)
`src/scheduler/yield_curve_job.py` (from T6): `curves` only appended non-empty curves, but `dates` kept every business day, then `zip(dates, curves)` paired them by position.
A day before the first FRED observation (e.g. a leading holiday) has no curve, so every later snapshot was saved under an earlier date and the newest days were dropped;
the delta/z-score lookups used the same misaligned indexes. Fixed by carrying `(date, curve)` pairs (zips are now `strict=True`); the regression test failed on the old code
(snapshots dated 9/21… instead of 9/23…).

## 1b. `classify_shape` ignores the 2s>30s spread — open, needs a product decision
`src/yield_curve/curves.py`: `s_2s30s` was computed and never used (deleted for lint). Only `s_2s10s` gates `INVERTED`, so a 2s>30s inversion is not classified as inverted, and
`INVERTED_HUMPED`/`HUMPED` only trigger when the 5y, 2y and 30y points are all present. Decide what "inverted" should mean before changing it (found by the T10b review).

## 2. "Computed then discarded" values that look like unfinished features (F841 — deleted for lint, intent recorded here)
| Site | Discarded value | What it suggests |
|---|---|---|
| `src/yield_curve/curves.py` ~L66 | `s_2s30s` | only `s_2s10s` gates `INVERTED`, so a 2s>30s inversion is not classified as inverted |
| `src/journal/trade_tracker.py` ~L362 | `session_analysis` | `get_insights` analyses sessions and never uses the result (sibling `setup_analysis` is used); also a wasted DB query |
| `src/analysis/strategy_builder.py` ~L456 | `atm_strike_call` | the "covered call (ATM)" strategy is never built; only the OTM spread is |

Genuine dead code (deleted, nothing to follow up): `llm/tools/upstream_tools.py` `price_changes`; `analysis/options_analyzer.py` `volume` / `open_interest`
(removing them also removes a latent `int(None)` crash path).

## 3. Decisions recorded from the T10b review
- `B027` on `Loan/ScalingModel/Strategy.validate_params`: kept as optional hooks with `# noqa: B027  # optional hook` — making them `@abstractmethod` would make 7 strategies (and a directly-instantiated `Loan()` in tests) uninstantiable.
- `B905`: provably equal-length `zip`s take `strict=True` (alert manager, regime narrator, heatmap chart); the yield-curve zips were `strict=False` until item 1 was fixed and are now `strict=True`.
- `B017`: `pytest.raises(Exception)` narrowed to `dataclasses.FrozenInstanceError` (measured).
- Auto-fix counts: 233 findings up front; the fix pass reports 240 because sorting exposes a few more once unused imports are gone — both numbers are right.

## 4. Small leftovers
- `tests/test_research_loans.py:75` has `# type: ignore[abstract]` on a line that instantiates `Loan`, which is not abstract. Harmless, but it misleads readers into thinking `Loan` is abstract
  (the wrong conclusion when someone considers `@abstractmethod`). Not a lint finding, so left alone.
- Enabling the `UP`/`SIM`/`TCH`/`E`/`W` rules later is possible, but treat `UP` autofixes as unsafe here: that family removed a needed `typing` import earlier (`4829f23`, fixed in `ec8d4bc`).
