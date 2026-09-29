# T10a — Manual bugbear / unused-variable fixes in `src/api/`

Part of the CI-green work (see T10). The owner decided CI will enforce ruff rules **`F`, `E9`, `B`, `I`**. The auto-fixable findings (unused imports,
import sorting, formatting) are applied mechanically by the integrator **after** the manual ones are merged. Your job is the findings that need a human decision.
Use the pinned version: `uvx ruff@0.16.9 …` (plain `uvx ruff` may drift).

## Owns
Only `src/api/**` (6 files, 37 findings at the time of writing). Do not touch any other path — T10b owns the rest of the repo.

## List your findings
```
uvx ruff@0.16.9 check src/api --no-cache --select B,F841 --output-format concise
```
Expected mix: mostly **B904** (`raise` inside `except` without `from`), plus a few B007/B905/B010/F841.

## Rules for each finding type — the goal is **no behavior change**
- **B904** `raise X(...)` inside `except E as e:` → `raise X(...) from e`. Use `from None` only if the code is deliberately hiding an internal error from the caller and you can say why.
  Never change the exception type, message, HTTP status code or detail text. (FastAPI responses are unaffected by chaining.)
- **B007** unused loop variable → rename to `_name` (or `_`).
- **B905** `zip()` without `strict=` → add `strict=False` (that is today's behavior). Use `strict=True` only if equal lengths are guaranteed and a mismatch would be a bug — then say so in the report.
- **B010** `setattr(obj, "constant", v)` → `obj.constant = v`. **B033** duplicate set item → remove it.
- **B027** empty method in an abstract class → if subclasses may override it as an optional hook, keep it and add `# noqa: B027  # optional hook`; only make it `@abstractmethod` if you verify every subclass implements it.
- **B028** `warnings.warn` → add `stacklevel=2`. **B017** `assertRaises/pytest.raises(Exception)` → the specific exception (find what is actually raised).
- **F841** unused variable → drop the binding but keep any call with side effects (`result = f()` → `f()`); an unused `except E as e:` → `except E:`.

## Do not
- Run `--fix` or `--unsafe-fixes` blindly, run `ruff format`, sort imports, or "clean up" anything not on the list — the mechanical pass happens later and would conflict.
- Add `# noqa` to make a finding go away, except the documented B027 case.

## Acceptance
- `uvx ruff@0.16.9 check src/api --no-cache --select B,F841` → "All checks passed".
- Full suite, clean room, same result as before your change (**1075 passed, 32 skipped**):
  `env -i HOME=$HOME PATH=$PATH $PY -m pytest tests -q -p no:cacheprovider` (run from your worktree, with the `.env`/`credentials.yaml` symlinks removed for this run).
- Report a table: file:line · rule · what you did · anything non-trivial (especially any `from None`, `strict=True`, or `@abstractmethod`).
