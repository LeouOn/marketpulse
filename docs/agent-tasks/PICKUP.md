# Pickup note — 2026-09-28 (updated after integration)

**State:** everything is merged into `main` (`66b8ff5`): T0–T9 (T2a–c, T3a–b, T7a–b included). No conflicts. Nothing is pushed.
Suite: **1075 pass / 0 fail** (baseline was 919 pass / 20 fail / 6 errors), identical in a clean room (no `.env`, no `credentials.yaml`)
and on pydantic-ai 1.x and 2.x. Live smoke on the merged app: 11/11 previously broken or key-dependent endpoints return 200
(regimes, yield curve, DXY, backtest regime, heatmap, options macro-context, AI status on MiniMax…), 121 routes, every router loads.

Two integration fixes were needed on top of the agent branches:
- `tests/conftest.py` (T9) masked *any* path ending in `config/credentials.yaml` and always redirected the research data paths, which broke T4's and T3b's
  self-isolating tests. Now it masks only the developer's real file (by resolved path) and honours a `real_data_paths` marker.
- `/api/options/macro-context` returned 500 on `numpy.bool`; added `src/api/json_utils.to_builtin` (regression test fails without the fix).

## Still to do
1. **T10 — CI green + one format pass** (`T10-ci-green.md`). Last, and merge immediately (it reformats ~158 files). Needs your call on the ruff rule set.
2. **T11 — docs + `docs/STATUS.md`** (`T11-docs-accuracy.md`), after T10.
3. Frontend: adopt the new additive fields from T7a (`symbol`, `instrument`, `is_proxy`) so DXY/gold are labelled as the real instruments.
   Also note T7a now **withholds fabricated internals unless `MARKETPULSE_ALLOW_MOCK=1`**, so panels that showed made-up numbers will show nothing.

## Loose ends
- Shared venv is on pydantic-ai 1.x while `requirements.txt` now says `>=2,<3` (works on both). Upgrade: `uv pip install --python .venv/bin/python -r requirements.txt`.
- 11 agent worktrees (`../marketpulse-wt/T*`) and their `task/*` branches are merged and can go:
  `for t in T1 T2b T2c T3a T3b T4 T5 T6 T7a T7b; do git worktree remove --force ../marketpulse-wt/$t; done` then `git branch -d task/<id>`
  (T5's worktree holds a ~GB `.venv`). Not removed automatically in case an agent session is idle in one.
- Strays from earlier: empty `../marketpulse-wt/marketpulse-wt/`, and `scratch/merge-check` + its `mergecheck` worktree.
- Rotate the EIA key if you care: a failing test once printed most of it (fixed for tests).
- `ds4` is built (T4); the local server listens on :8000, the API's own port, so run it on :8001.

## Workflow that worked (keep it)
One git worktree per task (`docs/agent-tasks/new-worktree.sh <ID> [base]`), disjoint file ownership, dependencies gated, integrate on a scratch branch and run the
suite (normal **and** clean-room) before moving `main`. Never work in the shared checkout; check `git branch --show-current` before merging. Never `git add -A`; never print key values.
