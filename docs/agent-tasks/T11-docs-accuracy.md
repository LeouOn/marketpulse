# T11 — Docs that match reality, plus a one-page status map

**Prerequisites (merged into `main` first): T0, T3b, T4, T5, T6, T7a, T10.** Branch from `main` after they land, so you document what exists rather than what was planned.

## Problem (verified 2026-09-28)
The root docs describe an older project. Things the README/USAGE/`tasks` file get wrong today:
- "Python 3.8+" — `pyproject.toml` requires **≥ 3.11**; system Python on the owner's machine is 3.14, and the verified environment is 3.12 via `uv`.
- Quick start uses `requirements-lite.txt`, which omits packages the app imports at startup (`redis`, `plotly`, `pydantic_ai`) — endpoints silently fail to load.
- Key setup: FRED/EIA key placement (T0 defines the real precedence), MiniMax host (`https://api.minimax.io/v1`; `minimax.io` is the website), placeholder resolution from `.env`.
- Feature list still leads with Alpaca/Rithmic/Coinbase and LM Studio; the default LLM provider is MiniMax; `ds4` is a local option (T4); Yahoo, FRED and EIA are what actually work without paid keys.
- `tasks` (root file) is a stale Postgres/Alpaca checklist; `market` and other root scripts are undocumented; `docs/archive/` mixes current and obsolete material.
- Redis/Postgres/Docker are optional: SQLite works (verified), Redis-less runs disable caching only.

## Goal
A newcomer (or the owner after another year away) can go from a fresh clone to a running, verified stack in minutes, and can see at a glance what is real and what isn't.

## Steps
1. Rewrite the README quick start against the current truth. **Execute it** in a scratch clone/worktree (fresh `uv venv`, the documented install command, the documented start command) and fix the doc until it works verbatim.
2. Correct `USAGE.md`, `BACKEND_DOCUMENTATION.md`, `FRONTEND_DOCUMENTATION.md`, `ENHANCED_LLM_DOCUMENTATION.md` where they contradict the code (spot-check claims against the code and against a live run). Move obsolete material into `docs/archive/` with a header saying it is historical. Remove or update the root `tasks` file.
3. Create `docs/STATUS.md`: one page — components (backend, frontend, research lab, yield curve, LLM providers, AI analyst), for each: works / partial / broken / needs key, what it depends on, how to verify it (the exact command). Link `docs/data-provenance.md` (T7a) and `docs/local-llm-ds4.md`.
4. Add a key-setup table (service · env var · where to get it · what breaks without it), covering FRED, EIA, MiniMax, DeepSeek, OpenRouter, Anthropic, Massive, Alpaca, Coinbase, Rithmic.

## Things that changed after this prompt was first written (document them accurately)
- **Everything else is merged into `main`.** You can run `docs/agent-tasks/new-worktree.sh T11 main`.
- **Dev tooling / CI:** ruff is pinned (`ruff==0.16.9`) and enforces `F, E9, B, I`; formatting is enforced with `ruff format --check src tests`; CI runs Python 3.11 and 3.12 with no test `--ignore` list;
  `tests/test_app_boots.py` guards startup. Tell contributors to run `git config blame.ignoreRevsFile .git-blame-ignore-revs` (the mechanical format commit is listed there; GitHub honours the file automatically).
- **Tests are hermetic:** `tests/conftest.py` neutralises real keys/`credentials.yaml` and redirects research data paths; opt-ins are `--live-credentials`, `@pytest.mark.live_credentials`, `@pytest.mark.live`
  (`RUN_LIVE_TESTS=1`) and `@pytest.mark.real_data_paths`. Document the clean-room command: `env -i HOME=$HOME PATH=$PATH python -m pytest tests -q`.
- **AI analyst** (`/api/ai/*`) runs on the configured LLM provider (MiniMax by default) — no Anthropic key needed; `requirements.txt` pins `pydantic-ai>=2,<3`.
- **Keys:** FRED/EIA are resolved by `src/core/keys.py` (env → `.env` → `config/credentials.yaml` `macro_data`); MiniMax lives at `https://api.minimax.io/v1`; `ds4` is a supported local provider (default port 8001).
- **Known open issues** to reflect honestly in `docs/STATUS.md`: see `docs/agent-tasks/FOLLOWUPS.md` (e.g. `classify_shape` ignores 2s>30s) and the mock-data behaviour in `docs/data-provenance.md`
  (internals are withheld unless `MARKETPULSE_ALLOW_MOCK=1`).

## Constraints
Docs only, plus deleting/moving obsolete docs. Every command in the docs must have been run by you. No secrets in examples.

## Acceptance
Report the fresh-clone run transcript (commands + outcomes), the list of doc claims you corrected, and anything you could not verify.
