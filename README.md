# MarketPulse 📈

A market-analysis platform: FastAPI backend, Next.js dashboard, a multi-asset macro
research lab, a Treasury yield-curve pipeline, and an AI trading analyst.

> **Not everything here works.** Before you trust a feature, read
> **[docs/STATUS.md](docs/STATUS.md)** — one page, per component: works / partial / broken /
  needs a key, and the exact command to check it yourself.

## 🚀 Quick Start

Verified end to end from a fresh clone on 2026-09-29 (Python 3.12.14, Node 24.21.0).

### Prerequisites

| Requirement | Version | Why |
|---|---|---|
| **Python** | **≥ 3.11** (`pyproject.toml`); 3.12 verified | `requires-python = ">=3.11"` |
| **[uv](https://docs.astral.sh/uv/)** | any recent | used for the venv and installs below |
| **Node.js** | **≥ 20.9** | required by Next.js 16.2.6 (`marketpulse-client/node_modules/next/package.json`) |
| PostgreSQL · Redis · Docker | *optional* | SQLite works; without Redis only caching is disabled |

### 1. Clone and install

```bash
git clone <repository-url> marketpulse
cd marketpulse

uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt

# Frontend (separate dependency tree)
cd marketpulse-client && npm ci && cd ..
```

`requirements.txt` is the full dependency set. **`requirements-lite.txt` is not a valid
install for the app** — it omits `redis`, `plotly` and `pydantic_ai`, and endpoints that need
them fail silently at startup instead of erroring.

### 2. Configure keys (optional to boot, required for most data)

```bash
cp .env.example .env      # then fill in the keys you have
```

The app **boots with no keys at all** and serves Yahoo-backed market data, the symbol and
asset registries, options chains, and the LLM configuration. See
[Keys](#-keys) for what each key unlocks.

### 3. Run it

```bash
# Backend — http://localhost:8000
.venv/bin/python -m uvicorn src.api.main:app --port 8000
```

Startup takes ~10 s and logs one `... endpoints loaded successfully` line per router; there
should be **no** `Could not load ... endpoints` warnings. 121 routes are registered.

```bash
# Frontend — http://localhost:3000 (separate terminal)
cd marketpulse-client && npm run dev
```

The dashboard proxies `/api/*` to `http://localhost:8000` through
`marketpulse-client/src/middleware.ts`; set `BACKEND_URL` to point elsewhere.

### Access points

| | |
|---|---|
| Dashboard | http://localhost:3000 |
| API | http://localhost:8000 |
| OpenAPI docs | http://localhost:8000/docs · http://localhost:8000/redoc |
| Route inventory | http://localhost:8000/api/debug/routes |

## 🔑 Keys

Resolution order for the data-API keys (`FRED_API_KEY`, `EIA_API_KEY`) is implemented in
[`src/core/keys.py`](src/core/keys.py):

1. the process environment
2. `.env`, then `config/.env` (later file wins)
3. `config/credentials.yaml` under `macro_data:` (`FRED_API_KEY` → `fred_api_key`)

Empty values and placeholders (`your_…`, an unresolved `${…}`) are skipped, so a placeholder
in a higher-priority source never hides a real key below it. Set
`MARKETPULSE_KEYS_ENV_ONLY=1` to consult the process environment only.

| Service | Env var | Where to get it | Without it |
|---|---|---|---|
| **FRED** | `FRED_API_KEY` | <https://fredaccount.stlouisfed.org/apikeys> (free, instant) | Yield-curve pipeline and all FRED-backed macro factors fail. The repo ships a **stale** cache in `data/macro/`, so some pages render old numbers rather than erroring. |
| **EIA** | `EIA_API_KEY` | <https://www.eia.gov/opendata/register> (free) | Oil fundamentals (`OIL` research asset) unavailable. |
| **MiniMax** | `MINIMAX_API_KEY` | <https://platform.minimaxi.com> — API host is `https://api.minimax.io/v1` (`minimax.io` is the website) | The default LLM provider is unconfigured: no AI analysis, no AI analyst. Everything else still works. |
| **DeepSeek** | `DEEPSEEK_API_KEY` | <https://platform.deepseek.com> | Fallback LLM provider unavailable. |
| **OpenRouter** | `OPENROUTER_API_KEY` | <https://openrouter.ai/keys> | Fallback LLM provider unavailable. |
| **Alpaca** | `API_KEYS_ALPACA_KEY_ID` / `API_KEYS_ALPACA_SECRET_KEY` (or `api_keys.alpaca` in `config/credentials.yaml`) | <https://app.alpaca.markets> | The `EQUITIES` research asset fails with an explicit "Alpaca credentials are not configured" error. Everything else is unaffected. |
| **Anthropic** | `ANTHROPIC_API_KEY` | <https://console.anthropic.com> | Nothing needs it any more — the AI analyst runs on the configured provider. |
| **Massive** | `MASSIVE_API_KEY` | <https://massive.com> | The AI analyst's Massive.com MCP tools are disabled; the analyst still answers without market data. |
| **Coinbase** | `API_KEYS_COINBASE_API_KEY` / `_SECRET` / `_PASSPHRASE` | <https://pro.coinbase.com> | Crypto collection beyond the public Yahoo path is unavailable. |
| **Rithmic** | `API_KEYS_RITHMIC_*` | <https://www.rithmic.com> | Rithmic futures feed unavailable. |

Placeholders like `your_minimax_api_key` are treated as "not configured" — the app tells you
which variable to set rather than failing with a 401.

## ✅ What works with no keys

Verified on a fresh clone with an empty environment:

| Endpoint | Result |
|---|---|
| `/api/market/symbols`, `/api/research/assets` | 200 — static registries |
| `/api/market/internals`, `/api/market/macro` | 200 — **live Yahoo** data (`data_source: "yahoo"`) |
| `/api/options/expirations/{symbol}` | 200 — Yahoo options chain |
| `/api/llm/models`, `/api/llm/model-status` | 200 — configuration only |
| `/api/yield-curve/current` | 200 with `success: false` — honest "no snapshot yet" |

## 🔬 Development

```bash
# Tests — hermetic by default: real keys, credentials.yaml and research paths are neutralised
env -i HOME="$HOME" PATH="$PATH" .venv/bin/python -m pytest tests -q
# → 1078 passed, 32 skipped

# Lint and format (ruff is pinned; this is exactly what CI runs)
uvx ruff@0.16.9 check src tests
uvx ruff@0.16.9 format --check src tests

# Frontend
cd marketpulse-client && npm run lint && npm run build
```

CI (`.github/workflows/ci.yml`) runs the full suite on **Python 3.11 and 3.12** with no
`--ignore` list, plus `compileall`, an `import src.api.main` check, `ruff check`,
`ruff format --check`, and a frontend `npm run build`.

The repo-wide import-sort/format commit is listed in `.git-blame-ignore-revs`. On a fresh
clone, run once:

```bash
git config blame.ignoreRevsFile .git-blame-ignore-revs
```

### Test opt-ins

The default suite touches no network and no real credentials. Opt in per need:

| Opt-in | Effect |
|---|---|
| `RUN_LIVE_TESTS=1` | runs `@pytest.mark.live` tests (real FRED/EIA/Yahoo/LLM calls) |
| `pytest --live-credentials` | allows tests to use real `config/credentials.yaml` |
| `@pytest.mark.real_data_paths` | skips the autouse redirect of `src.research.data` paths |
| `pytest --run-e2e` or `RUN_E2E=1` | `@pytest.mark.e2e` smoke tests (need API **and** frontend running) |

## 🧠 LLM providers

The default provider is **MiniMax** (`https://api.minimax.io/v1`, model `MiniMax-M3`).
`ds4` is a supported **local** provider — run its server on **:8001**, because the API itself
uses :8000 (see [docs/local-llm-ds4.md](docs/local-llm-ds4.md)). LM Studio and OpenRouter are
configured as fallbacks. `llm.model_routing.primary_provider` selects the default; the AI
analyst follows it rather than hard-coding a vendor.

## 🏗️ Architecture

```
marketpulse/
├── src/
│   ├── api/          # FastAPI routers, one module per domain (121 routes)
│   ├── ai/           # AI trading analyst (pydantic-ai agent + Massive MCP tools)
│   ├── llm/          # provider clients, model router, tool-calling agents
│   ├── research/     # multi-asset macro research lab
│   ├── yield_curve/  # Treasury curve pipeline and history
│   ├── analysis/     # technicals, divergence, ICT, options, risk
│   ├── core/         # settings, key resolution
│   └── scheduler/    # scheduled jobs
├── marketpulse-client/  # Next.js 16 / React 19 dashboard
├── config/           # credentials (git-ignored), credentials.example.yaml
├── data/             # datasets and caches (partly committed)
├── scripts/          # one-off analysis and ops scripts
├── tests/            # hermetic by default
└── docs/
```

## 📁 Other entry points

Convenience wrappers exist for Windows and for containers. They were **not** exercised while
verifying this guide, so prefer the two-terminal commands above if something misbehaves.

| File | What it is |
|---|---|
| `Makefile` | `make help` lists the targets (`install`, `dev`, `test`, `lint`, `format`, `docker-*`). `make install` uses `pip`/`venv` rather than `uv`; the `uv` commands above are the verified path. |
| `scripts/dev.sh`, `scripts/dev.ps1` | One-command dev startup for both servers (the `make dev` target). |
| `scripts/setup.ps1` | Windows one-time dependency setup. There is **no** `scripts/setup.sh`. |
| `start-dev.bat`, `stop-dev.bat`, `marketpulse.bat` | Windows wrappers around the above. |
| `docker.sh`, `docker-compose.yml`, `Dockerfile.api` | Container path. Entirely optional — SQLite works with no Docker. `scripts/docker.sh` and `scripts/docker.ps1` are the entry points; there is no `scripts/docker.sh` (the script is at the repo root). |
| `market` | **PostgreSQL-only** database initialiser. It blocks on `pg_isready -h localhost -p 5432`, so it is useless — and unnecessary — on the default SQLite setup. |
| `audit_system.py` | Prints DB and Redis connectivity. Redis is optional; a Redis failure is expected on a bare setup. |
| `requirements-lite.txt` | A partial dependency list kept for reference. **Not** a working app install. |
| `scripts/*.py` | ~30 one-off analysis and ops scripts (yield-curve backfill, regime backtests, sector rotation, Warsh dashboards…). Each is standalone; none is imported by the app. |

## 📊 Data sources

- **Yahoo Finance** — equities, ETFs, futures, crypto, VIX, options chains. Needs no key, and
  is what the app falls back to. See [docs/data-provenance.md](docs/data-provenance.md) for
  exactly which field comes from where, and which values are withheld.
- **FRED** — Treasury yields and macro series.
- **EIA** — oil spot prices and inventories.
- **Alpaca / Rithmic / Coinbase** — optional feeds, all require keys.

Fabricated market internals are **withheld unless `MARKETPULSE_ALLOW_MOCK=1`**; with it unset
you get real data or nothing.

## 📚 Further reading

| Document | What it covers |
|---|---|
| [docs/STATUS.md](docs/STATUS.md) | **Start here** — what works, what doesn't, how to check |
| [docs/data-provenance.md](docs/data-provenance.md) | where each market number comes from |
| [docs/local-llm-ds4.md](docs/local-llm-ds4.md) | running a local `ds4` LLM server |
| [USAGE.md](USAGE.md) | day-to-day operation |
| [docs/agent-tasks/PICKUP.md](docs/agent-tasks/PICKUP.md) | current state of the project and open work |
| [docs/agent-tasks/FOLLOWUPS.md](docs/agent-tasks/FOLLOWUPS.md) | known bugs and decisions |
| [docs/archive/](docs/archive/) | superseded design documents, kept for history |
