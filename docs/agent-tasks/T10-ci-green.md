# T10 — Make CI meaningful and green, then the mechanical pass (integrator task)

**Owner decisions (2026-09-29):** enforce ruff **`F`, `E9`, `B`, `I`** (keep `ignore = ["E501"]`); do the repo-wide format pass; pin ruff; add Python 3.12 to the CI matrix; lint scope stays `src/` + `tests/`.
Dropped from `select` (not deleted from history): `UP`, `SIM`, `TCH`, `E`, `W` — ~450 style findings with no bug-catching value at py311, and the `UP` family is the kind of autofix that broke startup earlier.

**Prerequisites (merged into `main` first): T10a and T10b** (the manual fixes). Nothing else may be in flight: the last commit reformats ~174 files.

## Measured 2026-09-29 (ruff 0.16.9, merged `main`)
- Current config: 821 findings. With `F,E9,B,I`: ~300, of which **65 are manual** (`B` + `F841`: 37 in `src/api`, 28 elsewhere → T10a, T10b) and the rest are auto-fixable (125 unused imports, 10 empty f-strings, and ~100 unsorted imports).
  The exact auto-fix total varies slightly with how ruff is invoked (233, 238 and 240 were all measured; import-sort counts depend on how first-party packages are detected) — **the pass is `--fix`-driven, so do not validate against a fixed count**; validate the outcome (zero findings, suite green).
- **Mechanical pass validated in a scratch worktree:** `ruff check --select F401,F541,I --fix` (no unsafe fixes) + `ruff format` (173 files) → app imports, clean-room suite **1075 passed / 32 skipped**, identical to before.
- **Format is behavior-preserving:** formatting a copy changed 174 files and 0 had a different syntax tree (docstrings excluded).
- No unused import is in an `__init__.py`, inside a `try:` availability probe, or reached by a test through a dotted-string patch target.
- Full test suite with **no** `--ignore` flags: 1075 passed / 32 skipped in a clean room, so the ignore list can be deleted.

## Steps (separate commits, in this order)
1. **Config**: `pyproject.toml` → `select = ["F", "E9", "B", "I"]`; pin `ruff==0.16.9` (pyproject dev deps and the CI install step) so `format --check` cannot drift.
2. **CI** (`.github/workflows/ci.yml`): remove all 17 `--ignore=…` flags and `-x` (use `--maxfail=20`); matrix Python 3.11 **and** 3.12; add `python -m compileall -q src scripts` and
   `python -c "import src.api.main"`; keep `ruff check src tests` and `ruff format --check src tests`; confirm the frontend job matches what T8 found working (`npm ci && npm run lint && npm run build`).
3. **Startup guard**: `tests/test_app_boots.py` — import `src.api.main`, assert the expected routers loaded (no `Could not load … endpoints` for the routers that must exist), and that
   `src.api.route_utils.route_entries(app)` yields at least the count in `tests/fixtures/route_snapshot.json`.
4. **Mechanical commit**: `ruff check src tests --select F401,F541,I --fix` then `ruff format src tests`. Nothing else. Run the clean-room suite; expect 1075 passed / 32 skipped (plus the new boot tests).
5. `.git-blame-ignore-revs` containing the SHA of step 4, plus `git config blame.ignoreRevsFile .git-blame-ignore-revs` documented in the README.
6. Verify each CI step locally in a clean room and quote the results. If `act` is not available, say plainly that the workflow itself was not executed.
