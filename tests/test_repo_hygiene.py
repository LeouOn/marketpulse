"""Repo hygiene guards: line endings and monster lines.

``src/analysis/ohlc_analyzer.py`` was committed with CR-only line endings
(no ``\\n`` at all -- one giant 35k-char line; old-Mac style). That broke
grep/diff tooling and made the file effectively unreadable. It was converted
to LF; these tests keep it (and any sibling) from coming back.

Git-free by design: a plain pathlib walk over ``src/``, ``tests/`` and
``scripts/``, reading raw bytes, so the guard works on any checkout and
never shells out.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Longest allowed single line in a ``src/`` .py file. Normal formatted code
#: stays under ~120 chars; a missing-final-newline or CR-only file collapses
#: the whole module into one line of many KB.
MAX_LINE_BYTES = 5000


def _py_files(*dirs: str):
    for d in dirs:
        base = REPO_ROOT / d
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*.py")):
            if "__pycache__" in p.parts:
                continue
            yield p


def _rel(p: Path) -> str:
    """Repo-relative path when possible, absolute otherwise (e.g. /tmp copies)."""
    try:
        return str(p.relative_to(REPO_ROOT))
    except ValueError:
        return str(p)


def _cr_only_files(files) -> list[str]:
    """Paths containing a bare ``\\r`` not followed by ``\\n`` (CR-only endings)."""
    offenders = []
    for p in files:
        b = p.read_bytes()
        if b.count(b"\r") > b.count(b"\r\n"):
            offenders.append(_rel(p))
    return offenders


def _monster_line_files(files) -> list[str]:
    """Paths under ``src/`` whose longest line exceeds MAX_LINE_BYTES."""
    offenders = []
    for p in files:
        b = p.read_bytes()
        longest = max(len(line) for line in b.split(b"\n"))
        if longest > MAX_LINE_BYTES:
            offenders.append(f"{_rel(p)} (longest line {longest} bytes)")
    return offenders


def test_no_cr_only_line_endings_in_python_files():
    """No .py under src/, tests/ or scripts/ may use CR-only line endings.

    LF and CRLF are both fine; a bare ``\\r`` without a following ``\\n``
    is not.
    """
    offenders = _cr_only_files(_py_files("src", "tests", "scripts"))
    assert offenders == [], f"CR-only line endings found: {offenders}"


def test_no_monster_single_line_python_files_under_src():
    """No .py under src/ may collapse into a single multi-KB line."""
    offenders = _monster_line_files(_py_files("src"))
    assert offenders == [], f"Monster single-line .py files under src/: {offenders}"


if __name__ == "__main__":
    print("=" * 70)
    print("Repo hygiene - Unit Tests")
    print("=" * 70)
    tests = [
        test_no_cr_only_line_endings_in_python_files,
        test_no_monster_single_line_python_files_under_src,
    ]
    passed = failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  PASS: {fn.__name__}")
            passed += 1
        except Exception:
            import traceback

            print(f"  FAIL: {fn.__name__}")
            traceback.print_exc()
            failed += 1
    print(f"\nResults: {passed}/{len(tests)} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
