# Archived documents

**Everything in this directory is historical.** These are design documents, implementation
notes and plans written for earlier versions of MarketPulse. They are kept for context and
provenance — **do not follow them as instructions.** They are not maintained and are not
checked against the code.

For current documentation:

| You want | Read |
|---|---|
| What works, what doesn't | [../STATUS.md](../STATUS.md) |
| Install and run | [../../README.md](../../README.md) |
| LLM providers and API | [../../USAGE.md](../../USAGE.md) |
| Backend / frontend detail | [../../BACKEND_DOCUMENTATION.md](../../BACKEND_DOCUMENTATION.md) · [../../FRONTEND_DOCUMENTATION.md](../../FRONTEND_DOCUMENTATION.md) |
| Project state and open work | [../agent-tasks/PICKUP.md](../agent-tasks/PICKUP.md) · [../agent-tasks/FOLLOWUPS.md](../agent-tasks/FOLLOWUPS.md) |

The live `BACKEND_DOCUMENTATION.md`, `FRONTEND_DOCUMENTATION.md` and
`ENHANCED_LLM_DOCUMENTATION.md` live at the **repository root**; the same-named files here are
their superseded earlier revisions.

## Known-stale specifics in these files

Verified 2026-09-29. If you are reading one of these for archaeology, note that:

- **`AI_TRADING_ANALYST.md`** — describes the analyst on pydantic-ai **1.x**
  (`MCPServerStdio`, `Agent(mcp_servers=…)`) and on a hard-coded Claude 4 model requiring
  `ANTHROPIC_API_KEY`. The analyst now runs on the app's configured provider (MiniMax by
  default) on pydantic-ai 2.x. `/api/ai/` still prints the words "AI_TRADING_ANALYST.md",
  which is a dangling reference to this file.
- **`POLYGON_INTEGRATION.md`** — Polygon.io is **not** a supported data provider. The
  providers in `src/llm/model_router.py` are minimax, deepseek, ds4, lm_studio, openrouter,
  alpaca, rithmic and coinbase.
- **`ENHANCED_LLM_DOCUMENTATION.md` / `BACKEND_DOCUMENTATION.md` / `FRONTEND_DOCUMENTATION.md`**
  — describe LM Studio as the primary LLM provider, Python 3.10-era prerequisites, and
  PostgreSQL as required. All three are false today: MiniMax is the default, Python must be
  ≥ 3.11, and SQLite works with no external services.
- **`TESTING.md`** — predates the hermetic test harness in `tests/conftest.py` and the
  `live` / `e2e` / `live_credentials` / `real_data_paths` opt-in markers.
- **`UI_UX_IMPROVEMENT_PLAN.md`**, **`FRONTEND_REFACTOR.md`**, **`IMPLEMENTATION_SUMMARY.md`**,
  **`SYSTEM_EVALUATION.md`** — point-in-time plans; the work they describe is either done or
  superseded.

The archive was last reviewed 2026-09-29; nothing in it has been verified against the current
code beyond the notes above.
