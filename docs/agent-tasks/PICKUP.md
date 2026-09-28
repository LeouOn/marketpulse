# Pickup note — 2026-09-28

**State:** only T0 is merged into `main`. T1, T2a–c, T3a–b, T4, T5, T6, T7a–b, T8 and T9 are committed on `task/*` branches and
**not merged**. A trial merge of all of them (`scratch/eval`, kept for reference, not on `main`) had **0 conflicts**:
1069 pass / 3 fail (baseline 919 pass / 20 fail / 6 errors), identical in a clean-room run (no `.env`, no `credentials.yaml`).
Nothing is pushed. T10 (CI + format pass) and T11 (docs) have not started.

## Fix before merging
1. **T9 conftest vs T4/T3b tests** — the 3 failures: `test_ds4_wiring.py::TestDS4Config::test_yaml_loads_ds4_block` and two in
   `test_research_data_cache_paths.py`. Each passes alone and with `main`'s `conftest.py`; T9's session guards redirect paths/config under them.
   Fix in `tests/conftest.py` (or let those tests opt out).
2. **`GET /api/options/macro-context` → 500** `Unable to serialize unknown type: numpy.bool` (T7b; VIX data now loads but isn't JSON-safe).
3. **T5** had uncommitted edits when last checked (an agent was live). Don't merge until it is committed.

## Then
Merge in this order (T2a is already inside T9's branch): `T1 T2a T2b T2c T3a T3b T4 T5 T7a T7b T8 T9 T6` →
run the full suite, normal and clean-room (`env -i`, no `.env`/`credentials.yaml`) → **T10** (last: it reformats ~158 files) → **T11**.

## Loose ends
- The shared checkout `/home/yl/proj/marketpulse` was left on `task/T9`; put it back on `main` when no agent is using it.
- Stray: empty `../marketpulse-wt/marketpulse-wt/`, and `scratch/merge-check` + its worktree `mergecheck` (someone's earlier dry run).
- Rotate the EIA key if you care: a failing test once printed most of it (T0 session). Fixed for tests; see T9 notes.
- Frontend label changes for the corrected DXY/gold values (T7a) still need doing in `marketpulse-client/`.
- `ds4` is built (T4) but the owner's local server still listens on :8000, the API's own port — use :8001.

## Workflow that worked (keep it)
One git worktree per task (`docs/agent-tasks/new-worktree.sh <ID> [base]`), disjoint file ownership per task, dependencies gated (T0 → T6; T10 last),
integrate in a scratch branch and run the suite before touching `main`. **Never work in the shared checkout**, and check `git branch --show-current`
before any merge (an agent once switched it under me). Never `git add -A`; never print key values.
