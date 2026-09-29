# Follow-ups found during the lint work (not fixed by T10a/T10b — behavior changes)

Found by the T10b analysis (2026-09-29). Each is real but is a behavior change, so it is **not** part of the lint commits.
Line numbers are as of `main` at the time; re-check before editing.

## 1. Yield-curve backfill can write snapshots under the wrong date (data bug) — owner: integrator
`src/scheduler/yield_curve_job.py` (~L156–172, from T6): `curves` only appends non-empty curves, but `dates` keeps every business day, then
`zip(dates, curves)` pairs them by position. `_asof_value` returns `None` for every tenor when a date precedes the first FRED observation in the fetch window
(for example a leading market holiday), so `curves` is shorter than `dates` and **every snapshot after the gap is saved under an earlier date**; today's snapshot can be dropped.
`baseline = curves[i - 5]` and `_delta_fields(dates, …, i)` use the same misaligned indexes.
Fix: build `(date, curve)` pairs, keep only non-empty ones, and derive `dates`/`curves` from the pairs so everything downstream stays aligned; add a test with a leading empty date.
Until then the lint change uses `strict=False` on those zips (preserves today's behavior).

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
- `B905`: provably equal-length `zip`s may take `strict=True`; the yield-curve zips stay `strict=False` until item 1 is fixed.
- `B017`: `pytest.raises(Exception)` narrowed to `dataclasses.FrozenInstanceError` (measured).
