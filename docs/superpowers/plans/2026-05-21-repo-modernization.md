# Repo Modernization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modernize MarketPulse repo — upgrade dependencies, replace legacy tooling with ruff, fix deprecation warnings, consolidate project structure, and improve test infrastructure.

**Architecture:** Incremental, non-breaking changes. Each task produces a working, testable state. Python tooling consolidated into `pyproject.toml`. Frontend eslint updated. Tests reorganized with shared fixtures.

**Tech Stack:** Python 3.14, FastAPI, Next.js 16, React 19, SQLAlchemy 2.0, ruff, pytest

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `pyproject.toml` | Single source of truth for Python project config, ruff, pytest, mypy |
| Modify | `src/core/database.py` | Fix SQLAlchemy `declarative_base()` deprecation |
| Modify | `requirements.txt` | Upgrade pinned dependencies |
| Modify | `marketpulse-client/package.json` | Upgrade React 18→19, ESLint 8→9 |
| Create | `tests/conftest.py` | Shared MockSettings fixture (deduplicated from test files) |
| Move | `test_application.py`, `test_e2e.py`, `test_endpoints.py`, `test_http.py`, `test_integration.py`, `evaluate_system.py` | Consolidate loose root files into `tests/` or remove |
| Create | `marketpulse-client/eslint.config.mjs` | ESLint flat config (v9) |
| Remove | `marketpulse-client/tsconfig.tsbuildinfo` | Build artifact tracked in git |
| Create | `src/analysis/__init__.py` | Missing init file |

---

### Task 1: Create `pyproject.toml` and add ruff

**Files:**
- Create: `pyproject.toml`
- Modify: `requirements.txt`

- [ ] **Step 1: Create `pyproject.toml` with ruff config, pytest config, and project metadata**

```toml
[project]
name = "marketpulse"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.34.0",
    "psycopg[binary]>=3.2.2",
    "sqlalchemy[asyncio]>=2.0.35",
    "alembic>=1.14.0",
    "pydantic>=2.10.0",
    "pydantic-settings>=2.7.0",
    "alpaca-py>=0.35.0",
    "aiohttp>=3.11.0",
    "pandas>=2.2.3",
    "numpy>=2.1.2",
    "openai>=1.60.0",
    "python-dotenv>=1.0.1",
    "pyyaml>=6.0.2",
    "schedule>=1.2.2",
    "loguru>=0.7.3",
    "python-dateutil>=2.9.0",
    "pytz>=2024.2",
    "websockets>=14.0",
    "yfinance>=0.2.51",
    "redis>=5.2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3.4",
    "pytest-asyncio>=0.25.0",
    "ruff>=0.9.0",
    "mypy>=1.14.0",
]

[tool.ruff]
target-version = "py311"
line-length = 120

[tool.ruff.lint]
select = [
    "E",    # pycodestyle errors
    "W",    # pycodestyle warnings
    "F",    # pyflakes
    "I",    # isort
    "UP",   # pyupgrade
    "B",    # flake8-bugbear
    "SIM",  # flake8-simplify
    "TCH",  # flake8-type-checking
]
ignore = ["E501"]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]

[tool.mypy]
ignore_missing_imports = true
python_version = "3.11"
```

- [ ] **Step 2: Update `requirements.txt` — upgrade pinned versions and replace alpaca-trade-api with alpaca-py**

Replace `requirements.txt` contents with:

```
fastapi>=0.115.0
uvicorn[standard]>=0.34.0
psycopg[binary]>=3.2.2
sqlalchemy[asyncio]>=2.0.35
alembic>=1.14.0
pydantic>=2.10.0
pydantic-settings>=2.7.0
alpaca-py>=0.35.0
aiohttp>=3.11.0
pandas>=2.2.3
numpy>=2.1.2
openai>=1.60.0
python-dotenv>=1.0.1
pyyaml>=6.0.2
schedule>=1.2.2
loguru>=0.7.3
python-dateutil>=2.9.0
pytz>=2024.2
websockets>=14.0
yfinance>=0.2.51
redis>=5.2.0
pytest>=8.3.4
pytest-asyncio>=0.25.0
ruff>=0.9.0
```

Key changes: `alpaca-trade-api` → `alpaca-py`, `websockets` 10.4 → 14+, minimum versions rather than pinned, removed `black`/`isort` (replaced by ruff).

- [ ] **Step 3: Install ruff**

Run: `pip install ruff`

- [ ] **Step 4: Run ruff check on src/ to see current state**

Run: `ruff check src/ tests/ --statistics`
Expected: List of lint violations (informational — do NOT auto-fix yet)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml requirements.txt
git commit -m "chore: add pyproject.toml with ruff config, upgrade dependency versions"
```

---

### Task 2: Fix SQLAlchemy `declarative_base()` deprecation

**Files:**
- Modify: `src/core/database.py:4,9`

- [ ] **Step 1: Replace `from sqlalchemy.ext.declarative import declarative_base` with modern `DeclarativeBase`**

In `src/core/database.py`, replace:

```python
from sqlalchemy.ext.declarative import declarative_base
```

with:

```python
from sqlalchemy.orm import DeclarativeBase
```

And replace:

```python
Base = declarative_base()
```

with:

```python
class Base(DeclarativeBase):
    pass
```

This eliminates the `MovedIn20Warning` that currently appears in test output.

- [ ] **Step 2: Run tests to verify no regressions**

Run: `python -m pytest tests/test_marketpulse.py -v`
Expected: All existing tests pass (6 tests from TestDatabaseManager + others)

- [ ] **Step 3: Commit**

```bash
git add src/core/database.py
git commit -m "fix: replace deprecated declarative_base() with DeclarativeBase"
```

---

### Task 3: Create shared `conftest.py` with common fixtures

**Files:**
- Create: `tests/conftest.py`
- Modify: `tests/test_marketpulse.py` (remove duplicated MockSettings)
- Modify: `tests/test_llm_chat_cached_data.py` (use shared fixture if applicable)

- [ ] **Step 1: Create `tests/conftest.py` with MockSettings fixture**

```python
import pytest
from unittest.mock import Mock


class MockSettings:
    def __init__(self):
        self.database_url = "sqlite:///:memory:"

        self.api_keys = Mock()
        self.api_keys.alpaca = Mock()
        self.api_keys.alpaca.key_id = "test_key"
        self.api_keys.alpaca.secret_key = "test_secret"
        self.api_keys.alpaca.base_url = "https://paper-api.alpaca.markets"

        self.api_keys.rithmic = Mock()
        self.api_keys.rithmic.username = "test_user"
        self.api_keys.rithmic.password = "test_pass"

        self.api_keys.coinbase = Mock()
        self.api_keys.coinbase.api_key = "test_cb_key"
        self.api_keys.coinbase.api_secret = "test_cb_secret"

        self.api_keys.openrouter = Mock()
        self.api_keys.openrouter.api_key = "test_or_key"

        self.llm = Mock()
        self.llm.primary = Mock()
        self.llm.primary.base_url = "http://localhost:1234/v1"
        self.llm.primary.api_key = "not-needed"
        self.llm.primary.timeout = 30

        self.llm.fallback = Mock()
        self.llm.fallback.base_url = "https://openrouter.ai/api/v1"
        self.llm.fallback.api_key = "test_fallback"
        self.llm.fallback.timeout = 60

        self.nq_symbol = "NQ=F"
        self.btc_symbol = "BTC-USD"
        self.eth_symbol = "ETH-USD"

        self.internals_interval = 60
        self.llm_analysis_interval = 300


@pytest.fixture
def mock_settings():
    return MockSettings()


@pytest.fixture
def mock_internals_data():
    return {
        'spy': {
            'price': 450.25,
            'change': 1.25,
            'change_pct': 0.28,
            'volume': 50000000,
            'timestamp': '2025-11-02T21:00:00Z'
        },
        'qqq': {
            'price': 180.50,
            'change': 2.15,
            'change_pct': 1.21,
            'volume': 30000000,
            'timestamp': '2025-11-02T21:00:00Z'
        },
        'vix': {
            'price': 18.50,
            'change': -0.50,
            'change_pct': -2.63,
            'volume': 1000000,
            'timestamp': '2025-11-02T21:00:00Z'
        },
        'volume_flow': {
            'total_volume_60min': 85000000,
            'symbols_tracked': 3,
            'timestamp': '2025-11-02T21:00:00Z'
        }
    }
```

- [ ] **Step 2: Update `tests/test_marketpulse.py` — remove local MockSettings class, import from conftest**

Remove the `MockSettings` class (lines 23-66) and the `mock_settings` / `mock_internals_data` fixtures from `test_marketpulse.py`. These are now provided by `conftest.py`.

Add at the top:
```python
from tests.conftest import MockSettings
```

Remove these fixtures from the test classes:
- `TestMarketPulseCollector.mock_settings` fixture
- `TestMarketPulseCollector.mock_internals_data` fixture
- `TestLLMIntegration.mock_settings` fixture
- `TestAlpacaClient.mock_settings` fixture
- `TestMarketCollectorIntegration.mock_settings` fixture

The fixtures will be auto-discovered from `conftest.py`.

- [ ] **Step 3: Run tests to verify conftest works**

Run: `python -m pytest tests/test_marketpulse.py -v`
Expected: All 15 tests pass

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py tests/test_marketpulse.py
git commit -m "refactor: extract shared MockSettings to conftest.py"
```

---

### Task 4: Consolidate loose root test files

**Files:**
- Move: `test_application.py`, `test_e2e.py`, `test_endpoints.py`, `test_http.py`, `test_integration.py` → `tests/`
- Move: `evaluate_system.py` → `scripts/`

- [ ] **Step 1: Move test files from repo root to tests/**

```bash
git mv test_application.py tests/
git mv test_e2e.py tests/
git mv test_endpoints.py tests/
git mv test_http.py tests/
git mv test_integration.py tests/
git mv evaluate_system.py scripts/
```

- [ ] **Step 2: Add missing `__init__.py` to `src/analysis/`**

Create `src/analysis/__init__.py`:

```python
```

(empty file)

- [ ] **Step 3: Run full test suite to verify everything still discovers correctly**

Run: `python -m pytest tests/ --co -q`
Expected: All tests collected (34+ tests)

- [ ] **Step 4: Commit**

```bash
git add src/analysis/__init__.py
git add tests/test_application.py tests/test_e2e.py tests/test_endpoints.py tests/test_http.py tests/test_integration.py scripts/evaluate_system.py
git commit -m "refactor: move loose root test files to tests/, add missing __init__.py"
```

---

### Task 5: Clean git-tracked artifacts and update `.gitignore`

**Files:**
- Modify: `.gitignore`
- Remove from tracking: `marketpulse-client/tsconfig.tsbuildinfo`

- [ ] **Step 1: Remove `tsconfig.tsbuildinfo` from git tracking**

```bash
git rm --cached marketpulse-client/tsconfig.tsbuildinfo
```

- [ ] **Step 2: Add `tsconfig.tsbuildinfo` pattern to `.gitignore` if not already present**

Verify `.gitignore` already has `*.tsbuildinfo` (it does — line 40). No change needed.

- [ ] **Step 3: Remove any tracked `__pycache__` directories from git**

```bash
git rm -r --cached src/**/__pycache__/ 2>$null
git rm -r --cached tests/__pycache__/ 2>$null
```

(These may already be untracked — the command will simply skip if nothing found.)

- [ ] **Step 4: Commit**

```bash
git commit -m "chore: remove build artifacts from git tracking"
```

---

### Task 6: Update frontend — React 19, ESLint 9 flat config

**Files:**
- Modify: `marketpulse-client/package.json`
- Create: `marketpulse-client/eslint.config.mjs`

- [ ] **Step 1: Update `marketpulse-client/package.json` dependencies**

Change:
- `"react": "^18"` → `"react": "^19"`
- `"react-dom": "^18"` → `"react-dom": "^19"`
- `"@types/react": "^18"` → `"@types/react": "^19"`
- `"@types/react-dom": "^18"` → `"@types/react-dom": "^19"`
- `"eslint": "^8"` → `"eslint": "^9"`
- `"eslint-config-next": "15.1.0"` → `"eslint-config-next": "^16.0.0"`

Updated `package.json` dependencies section:

```json
{
  "dependencies": {
    "@tanstack/react-query": "^5.90.8",
    "@tanstack/react-query-devtools": "^5.90.2",
    "clsx": "^2.1.1",
    "framer-motion": "^12.23.24",
    "lucide-react": "^0.408.0",
    "next": "^16.2.6",
    "react": "^19",
    "react-dom": "^19",
    "tailwind-merge": "^2.6.0"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.4.8",
    "@testing-library/react": "^16.0.0",
    "@types/jest": "^29.5.12",
    "@types/node": "^20",
    "@types/react": "^19",
    "@types/react-dom": "^19",
    "eslint": "^9",
    "eslint-config-next": "^16.0.0",
    "jest": "^29.7.0",
    "jest-environment-jsdom": "^29.7.0",
    "postcss": "^8",
    "tailwindcss": "^3.4.1",
    "typescript": "^5"
  }
}
```

- [ ] **Step 2: Create ESLint flat config `marketpulse-client/eslint.config.mjs`**

```javascript
import { dirname } from "path";
import { fileURLToPath } from "url";
import { FlatCompat } from "@eslint/eslintrc";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const compat = new FlatCompat({
  baseDirectory: __dirname,
});

const eslintConfig = [
  ...compat.extends("next/core-web-vitals", "next/typescript"),
];

export default eslintConfig;
```

- [ ] **Step 3: Install frontend dependencies**

Run: `cd marketpulse-client && npm install`

Expected: Packages installed. May show peer dependency warnings for React 19 transition — these are expected and non-blocking.

- [ ] **Step 4: Verify frontend still builds**

Run: `cd marketpulse-client && npm run lint`
Expected: ESLint runs without errors using new flat config

- [ ] **Step 5: Commit**

```bash
git add marketpulse-client/package.json marketpulse-client/package-lock.json marketpulse-client/eslint.config.mjs
git commit -m "chore: upgrade React 18→19, ESLint 8→9 with flat config"
```

---

### Task 7: Run ruff auto-fix and format

**Files:**
- All Python files in `src/` and `tests/`

- [ ] **Step 1: Run ruff check with safe auto-fixes**

Run: `ruff check src/ tests/ --fix --unsafe-fixes`

This will fix import ordering (isort), unused imports, and other safe auto-fixes.

- [ ] **Step 2: Run ruff format**

Run: `ruff format src/ tests/`

This replaces `black` + `isort` formatting.

- [ ] **Step 3: Run full test suite to verify no breakage**

Run: `python -m pytest tests/ -v`
Expected: All tests pass (may need minor fixes if auto-fix removed something incorrectly)

- [ ] **Step 4: Commit**

```bash
git add src/ tests/
git commit -m "style: apply ruff lint fixes and formatting"
```

---

### Task 8: Update Makefile for ruff

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Update lint and format targets to use ruff**

Replace the lint target:

```makefile
lint: ## Run linting checks
	@echo "Linting Python code with ruff..."
	ruff check src/ tests/
	@echo "Linting frontend code..."
	cd marketpulse-client && npm run lint || echo "Frontend linting not configured"
```

Replace the format target:

```makefile
format: ## Format code
	@echo "Formatting Python code with ruff..."
	ruff format src/ tests/
	ruff check src/ tests/ --fix
	@echo "Formatting frontend code..."
	cd marketpulse-client && npm run format || echo "Frontend formatting not configured"
```

- [ ] **Step 2: Commit**

```bash
git add Makefile
git commit -m "chore: update Makefile to use ruff instead of black/isort/flake8"
```

---

### Task 9: Clean up duplicate README Quick Start sections

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Remove the duplicate "Quick Start" section**

The README has two Quick Start sections:
1. Lines 7-76: The detailed one with prerequisites, automated setup, manual setup, access points
2. Lines 113-131: An older, simpler version

Remove lines 113-131 (the second "Quick Start" section through "Data Sources"). Keep the first, more comprehensive section.

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: remove duplicate Quick Start section from README"
```

---

### Task 10: Final verification

**Files:**
- None (verification only)

- [ ] **Step 1: Run full Python test suite**

Run: `python -m pytest tests/ -v`
Expected: All 34+ tests pass with no warnings

- [ ] **Step 2: Run ruff check — should be clean**

Run: `ruff check src/ tests/`
Expected: "All checks passed!" or 0 issues

- [ ] **Step 3: Verify frontend lint**

Run: `cd marketpulse-client && npm run lint`
Expected: No errors

- [ ] **Step 4: Verify no SQLAlchemy deprecation warnings**

Run: `python -m pytest tests/test_marketpulse.py -v -W error::DeprecationWarning 2>&1 | Select-String "MovedIn20Warning"`
Expected: No output (warning is gone)
