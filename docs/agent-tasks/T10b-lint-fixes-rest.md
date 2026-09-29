# T10b — Manual bugbear / unused-variable fixes everywhere except `src/api/`

Part of the CI-green work (see T10). The owner decided CI will enforce ruff rules **`F`, `E9`, `B`, `I`**. Auto-fixable findings (unused imports, import sorting,
formatting) are applied mechanically by the integrator **after** the manual ones merge. Your job is the findings that need a human decision.
Use the pinned version: `uvx ruff@0.16.9 …`.

## Owns
Every `.py` file under `src/` **except** `src/api/**`, plus `tests/` — about 28 findings across ~23 files (tests: 10, `src/analysis`: 6, `src/research`: 4, `src/scheduler`: 2, one each in
`src/yield_curve`, `visualization`, `llm`, `journal`, `alerts`, `ai`). T10a owns `src/api/**` — do not touch it.

## List your findings
```
uvx ruff@0.16.9 check src tests --no-cache --select B,F841 --output-format concise | grep -v '^src/api/'
```

## Rules for each finding type — the goal is **no behavior change**
- **B904** `raise X(...)` inside `except E as e:` → `raise X(...) from e` (`from None` only when deliberately hiding an internal error, and say why). Never change the exception type or message.
- **B007** unused loop variable → rename to `_name` (or `_`).
- **B905** `zip()` without `strict=` → add `strict=False` (today's behavior). `strict=True` only if equal lengths are guaranteed and a mismatch would be a bug — say so in the report.
- **B010** `setattr(obj, "constant", v)` → `obj.constant = v`. **B033** duplicate set item → remove.
- **B027** empty method in an abstract class → keep as an optional hook with `# noqa: B027  # optional hook`, unless you verify every subclass implements it (then `@abstractmethod`).
- **B028** `warnings.warn` → `stacklevel=2`. **B017** `pytest.raises(Exception)` in tests → the specific exception actually raised (run the test to find it; do not weaken what the test proves).
- **F841** unused variable → drop the binding but keep any call with side effects; unused `except E as e:` → `except E:`. In tests, an unused variable that was meant to be asserted on usually means a **missing assertion**:
  add the assertion if it is obvious, otherwise report it instead of silently deleting it.

## Do not
Run `--fix`/`--unsafe-fixes` blindly, run `ruff format`, sort imports, or clean up anything not on the list. Do not add `# noqa` except the documented B027 case.

## Acceptance
- `uvx ruff@0.16.9 check src tests --no-cache --select B,F841 --output-format concise | grep -v '^src/api/'` prints nothing.
- Full suite, clean room, unchanged result (**1075 passed, 32 skipped**): `env -i HOME=$HOME PATH=$PATH $PY -m pytest tests -q -p no:cacheprovider`
  (from your worktree, with the `.env`/`credentials.yaml` symlinks removed for this run).
- Report a table: file:line · rule · what you did · anything non-trivial (any `from None`, `strict=True`, `@abstractmethod`, or an F841 that hinted at a missing test assertion).
