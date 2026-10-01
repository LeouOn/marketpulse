# T12 — Does the `RECESSION` regime label match when recessions actually happened?

Branch from `main` (`docs/agent-tasks/new-worktree.sh T12 main`). Read `.agent-task/README.md` (shared rules) first.

## Why
The macro regime tape (`src/research/macro/regimes.py`, `GET /api/research/regimes`, the CLI) labels `RECESSION` as the **dominant** regime on about **20% of all days since 1990**.
NBER-dated recessions cover roughly **8%** of that span (Jul-1990..Mar-1991, Mar..Nov-2001, Dec-2007..Jun-2009, Feb..Apr-2020 — verify against the NBER series, don't trust this list).
The `RECESSION` score is forced to exactly `1.0` on every day the Sahm-rule flag is on (`sahm_recession`, built in `src/research/macro/factors.py`), otherwise it falls back to a sigmoid on the ISM-proxy z-score.
So the label probably over-runs, but nobody has measured it. It matters because the tape is the thing downstream consumers (dashboard, CLI, any future gating) would read.
Background and the neighbouring decisions: `docs/agent-tasks/FOLLOWUPS.md` §5 and the "Score scale" section of the `regimes.py` module docstring.

## Goal
Measure, with evidence, how well `RECESSION` agrees with the NBER dates; find out **which component** causes any disagreement; and — only if the evidence supports it — fix it without breaking what already works.

## Part 1 — the measurement (always do this; it is the deliverable even if nothing needs fixing)
1. Get the NBER recession indicator from FRED (`USREC` monthly; `USRECD` daily may also exist — verify the series IDs live; the key resolves via `src.core.keys`).
2. Build the platform's tape for 1990 → today: `MacroFactorProvider().load_factors(...)` then `generate_regime_tape(factor_df, include_scores=True)`. Use the classifier's own `LOOKBACK_DAYS` padding.
3. Report, in a table:
   - share of days `RECESSION` is **dominant** vs the NBER share; precision, recall and F1 of "RECESSION-dominant" against NBER, daily;
   - the same for the **Sahm flag alone** and for the **ISM-fallback score alone** (e.g. fallback score > 0.5), so you can say which one drives the disagreement;
   - per NBER recession: first day the label fired (lead/lag in days vs the NBER start) and how many days it stayed on **after** the NBER end;
   - every false-positive period (label on, NBER off): dates, length, and whether Sahm or the fallback was responsible.
4. Be careful and say so in the report: NBER announces peaks/troughs with a long delay and the factor frame uses **current-vintage** unemployment, so this is "agreement with the final dates", not a real-time hit rate. Sahm is a *concurrent* indicator, so some lag at the start is expected and is not a bug.

## Part 2 — a fix, only if Part 1 shows one is warranted
Candidate causes to check (do not assume): the flag staying on long after unemployment peaks; the ISM-proxy fallback (`IPMAN`, not the real ISM PMI — see the factor table in `factors.py`) firing outside recessions; the Sahm window/threshold implementation differing from the standard definition (3-month average of unemployment rising ≥0.5pp above its minimum of the prior 12 months).
If you change anything:
- You may edit **only** the `RECESSION` leg in `compute_logits` (and its `_TH_REC_*`/`_SL_REC_*` constants) and the Sahm computation in `factors.py`, plus tests and the study files below.
  Do **not** touch `generate_regime_tape`, the softmax, the router, `model.py` or the frontend — they were just changed and merged by the integrator.
- Lessons from the last regime fix, which you must follow: build the baseline first and keep it; prototype variants **offline on a saved frame**, scored against positives **and negative controls**;
  prefer a change that is robust across a neighbourhood of thresholds over the single best-fitting one (report the neighbours); don't tune to one episode.
- The change must keep **all 8 live acceptance episodes** passing (`RUN_LIVE_TESTS=1 pytest tests/test_research_macro_regimes.py -k "backrun or tape"`) — the GFC episode expects `RECESSION` in the top-2.
- Verify end to end through the real endpoint (`GET /api/research/regimes`, spare port), not just offline: the endpoint padded its history differently from offline code once and hid a bug.

## Deliverables
- `scripts/recession_label_study.py` — reproducible, prints the Part 1 tables (read-only; writes nothing under tracked paths).
- `docs/regime-recession-study.md` — the tables, the verdict (is the label over-running? by how much? which component?), and, if you changed code, the before/after numbers on both NBER agreement **and** the acceptance episodes.
- If you fixed something: offline tests on synthetic unemployment paths pinning the new behaviour, plus a `@pytest.mark.live` test asserting NBER agreement stays above a modest threshold with margin (not pinned to today's exact numbers).
- Update `docs/agent-tasks/FOLLOWUPS.md` §5 (mark the item done/not-needed with a pointer to the study).

## Acceptance
Report the headline numbers (before → after if changed), the full suite in a clean room (`env -i HOME=$HOME PATH=$PATH $PY -m pytest tests -q -p no:cacheprovider`), `uvx ruff@0.16.9 check/format --check src tests`, and the live acceptance run.
If the label turns out to be fine (the 20% is mostly real recession-like months or lag that is inherent), say so plainly — a clean "no change needed, here is the evidence" is a valid outcome.
