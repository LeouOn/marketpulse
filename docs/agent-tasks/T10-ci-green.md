# T10 — Make CI meaningful and green, then one mechanical format pass

**Prerequisites (all merged into `main` first): T1, T2a, T2b, T2c, T3a, T3b, T5, T9.** Branch from `main` after they land. Nothing else may be in flight when you finish: your last commit reformats ~158 files and conflicts with every open branch.

## Problem (verified 2026-09-28)
`.github/workflows/ci.yml` (Python 3.11):
- `ruff check src/ tests/` reports **831 findings** (596 auto-fixable, 75 more with `--unsafe-fixes`) and `ruff format --check src/ tests/` says **158 files would be reformatted** — the lint step cannot pass today.
- The pytest step passes 17 `--ignore=…` flags, which hides the legacy tests, and `-x` stops at the first failure.
- Nothing guards the failure that started this session: **the API not importing at all** (a stripped `typing` import; and a `callable | None` annotation). Nothing verifies startup or the route table.
- Local runs use Python 3.12; CI uses 3.11 only.

## Goal
CI fails when the product is broken, and passes now.

## Steps (separate commits, in this order)
1. **Remove `--ignore` entries** for every test file made green by T2a/T2b/T2c/T9 (and any others now passing); keep an ignore only with a comment that names the reason and the owner. Drop `-x` (use `--maxfail=20`). Add `-m "not live and not e2e"` if not implied.
2. **Ruff policy** in `pyproject.toml`: choose a rule set that catches real bugs without noise — at minimum `F` (pyflakes: undefined names, unused imports that hide bugs) and `E9`; add `I`/`UP`/`B` only if the resulting churn is acceptable. Record the decision and rationale in the commit message. Apply auto-fixes for the chosen set in one commit — mechanical only, then run the full suite.
3. **Startup guard tests**: `tests/test_app_boots.py` — import `src.api.main`, assert no `Could not load … endpoints` import failures were logged for the optional routers you expect to be present, and that `src.api.route_utils.route_entries(app)` yields ≥ the count in `tests/fixtures/route_snapshot.json`. Add a CI step `python -c "import src.api.main"` with a clear failure message.
4. **Matrix**: Python 3.11 and 3.12. Add `ruff check` to fail on `F821`, and a `python -m compileall -q src scripts` step.
5. **Frontend job**: run it locally (`npm ci && npm run lint && npm run build`) and make sure the workflow's frontend steps match what T8 found working.
6. **Format pass, last**: `ruff format src tests` as a single commit containing *only* formatting; run the full suite afterwards and confirm identical results.

## Acceptance
- Locally reproduce each CI step in a clean-room environment (no `.env`, no `credentials.yaml`, scrubbed env) and quote all results.
- If you can run GitHub Actions (e.g. `act`) do; if not, state clearly that the workflow itself was not executed.
- Tell the owner to merge immediately, because the format commit invalidates every other branch.
