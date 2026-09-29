# Pickup note — 2026-09-29 (after T10 landed)

**State:** everything is merged into `main` (`1c591c1`) except **T11 (docs)**. Nothing is pushed. All agent worktrees are removed; only the shared checkout remains, on `main`.

- **Tests:** 1078 pass / 32 skip in a clean room (no `.env`, no `credentials.yaml`, scrubbed env). Baseline at the start of the session was 919 pass / 20 fail / 6 errors.
- **CI (`.github/workflows/ci.yml`):** Python 3.11 + 3.12, full suite with no `--ignore` list, `compileall` + `import src.api.main`, pinned `ruff==0.16.9`
  enforcing `F, E9, B, I` plus `ruff format --check`, and a frontend `npm run build`. The workflow file itself has **not** been executed (no `act`); each step was run locally.
- **Live check on the final tree:** regimes, yield curve (real data), DXY, options macro-context, backtest regime, AI status (on MiniMax), model-status, dashboard → all 200; 121 routes; every router loads.
- The repo-wide format/import-sort commit is `49ac5b5`, listed in `.git-blame-ignore-revs` (run `git config blame.ignoreRevsFile .git-blame-ignore-revs` on other clones).

## Still to do
1. **T11 — docs + `docs/STATUS.md`:** `docs/agent-tasks/new-worktree.sh T11 main`, then send the prompt (its file already lists what changed since it was written).
2. **Frontend:** adopt T7a's additive fields (`symbol`, `instrument`, `is_proxy`) so DXY/gold are labelled as the real instruments. T7a also **withholds fabricated internals unless `MARKETPULSE_ALLOW_MOCK=1`**,
   so panels that used to show made-up numbers now show nothing.
3. **Open bugs / decisions** are in `docs/agent-tasks/FOLLOWUPS.md` (e.g. `classify_shape` ignores the 2s>30s spread; two "computed then discarded" unfinished features).

## Loose ends
- The shared venv (`.venv`) is on pydantic-ai 1.x while `requirements.txt` says `>=2,<3`. It works on both; align with `uv pip install --python .venv/bin/python -r requirements.txt`.
- 16 merged `task/*` branch labels remain (history is in `main`): `git branch -d $(git branch --list 'task/*')` removes them safely (`-d` refuses anything unmerged).
- Rotate the EIA key if you care: a failing test once printed most of it in a session transcript (tests no longer expose keys).
- `ds4` is built; the local server should listen on :8001 (the API itself uses :8000).

## Workflow that worked (keep it)
One git worktree per task (`docs/agent-tasks/new-worktree.sh <ID> [base]`), disjoint file ownership, dependencies gated, integrate on a scratch branch and verify (normal **and** clean-room suite, plus a live smoke)
before moving `main`. Never work in the shared checkout; check `git branch --show-current` before merging. Never `git add -A`; never print key values.
In zsh don't use `path` as a loop variable (it is tied to `PATH`) and don't put multi-word commands in unquoted variables.
