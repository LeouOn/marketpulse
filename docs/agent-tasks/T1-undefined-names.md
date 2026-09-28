# T1 — Fix undefined-name bugs (ruff F821)

## Problem
An earlier ruff autofix pass (`4829f23 style: apply ruff lint fixes`) and a bad merge left code that only fails at runtime.
`uvx ruff check src tests scripts --select F821 --output-format concise` currently reports:

| File | Count | Likely cause (hypothesis — verify) |
|------|-------|------------------------------------|
| `src/analysis/order_flow.py` ~L520–558 | 12 | An orphaned method **body** sits after `_resolve_price` with no `def` line: it uses `self`, `volume_bars`, `lookback`, `imbalances`. Recover the original method with `git log -p -S"volume_bars" -- src/analysis/order_flow.py`, find its callers, restore the header. |
| `src/llm/minimax_client.py` L147 | 1 | `internals_data` used inside a method whose parameter has a different name (data-validation prompt). |
| `src/llm/tools/technical_tools.py` L197 | 1 | Quoted annotation `"np.ndarray"` with no `numpy` import. Add a `TYPE_CHECKING` import (or a real import). |
| `scripts/ai_buildout_scenarios.py` | 1 | — |
| `scripts/live_validation.py` | 2 | — |

## Goal
Zero `F821` across `src tests scripts`, with the *behavior* of the restored code verified, not just the linter silenced.

## Steps
1. Fix each item. For `order_flow.py`, identify the method, its callers and intended return type from history and usage; do not invent behavior.
2. Add offline unit tests for the restored order-flow method (synthetic volume bars → expected imbalance detection) and for the
   MiniMax data-validation path (fake session; assert the prompt contains the data and the JSON parse path works).
3. Also run `uvx ruff check src tests scripts --select F821,F811,E9` and `$PY -m compileall -q src scripts`; fix anything else in that class (`F811` redefinitions
   often hide a lost method). Do **not** reformat or fix unrelated lint — a repo-wide format pass is T10.

## Acceptance
- `uvx ruff check src tests scripts --select F821` → "All checks passed".
- Tests above pass; full suite has no new failures.
- Report what the orphaned block turned out to be and how you confirmed the restored signature.
