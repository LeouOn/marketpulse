# T9 — Make the test suite hermetic: CI parity and a clean working tree

## Problem
1. **Tests dirty tracked files.** After a normal run `git status` shows `data/state/test_positions.json` modified (`tests/test_risk_management.py:~321` uses
   `test_state_file = "data/state/test_positions.json"`), plus untracked `reports/` and other artifacts. Anyone who then runs `git add -A` commits test noise.
2. **Tests depend on the developer's private config.** They read the gitignored `config/credentials.yaml`, real `.env`, and the shell environment. Example already seen: two MiniMax wiring tests failed
   locally only because the local YAML said `primary_provider: ds4`. CI has none of that, and this machine has keys CI does not.

## Goal
`pytest` gives the same result on a keyless clean checkout (CI) as on this machine, and a full run leaves `git status` clean.

## Steps
1. **Clean-room run.** In your worktree remove the `.env` and `config/credentials.yaml` symlinks and start the suite with a scrubbed environment
   (`env -i HOME=$HOME PATH=$PATH $PY -m pytest tests -q -p no:cacheprovider`, mirroring CI's `--ignore` list from `.github/workflows/ci.yml` and also without it). Record failures that exist **only** here (or only with the symlinks).
2. Fix them in the tests (monkeypatch env/settings, build `Settings` from the example YAML, isolate with fixtures). Add an autouse safeguard in `tests/conftest.py`
   (you own it) — e.g. neutralise the real `.env`/credentials/`OPENROUTER_API_KEY`-style variables for tests unless a test opts in, and point any state/report/cache directory at `tmp_path`.
   Coordinate with T0: it may add an env switch (`MARKETPULSE_KEYS_ENV_ONLY`) for key lookups; don't conflict with its name — if it isn't merged yet, keep your fixture generic.
3. **Dirty-tree hunt.** For each test file, run it alone and compare `git status --porcelain` before/after (script it). Fix every offender (`tmp_path`, `monkeypatch.chdir`, env-configured dirs).
   Also find where `reports/` comes from.
4. Add a guard: a session-finish check in `conftest.py` that fails (or warns loudly) if tracked files changed during the run.

## Constraints
Do not edit test files owned by T2a/T2b/T2c (`test_marketpulse.py`, `test_llm_chat_cached_data.py`, `test_e2e_agentic.py`) — report needed changes for them instead. Do not edit `.gitignore` (T3b).

## Acceptance
- Clean-room and normal runs give identical pass/fail sets (list any remaining, each with an owner).
- After the full suite, `git status --porcelain` is empty (except your own intended changes). Report the before/after lists.
