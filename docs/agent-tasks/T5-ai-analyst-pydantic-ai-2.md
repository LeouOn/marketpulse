# T5 — Port the AI analyst to pydantic-ai 2.x and lift the `<2` pin

## Context
`requirements.txt` pins `pydantic-ai>=1.0,<2` because 2.x **removed `pydantic_ai.mcp.MCPServerStdio`** (replaced by an `MCPToolset`-style API), which
`src/ai/massive_analyst.py` imports (`from pydantic_ai.mcp import MCPServerStdio`, used in `create_massive_mcp_server`). With 2.51 installed,
`/api/ai/*` failed to load; the pin restored it. Separately, `GET /api/ai/status` returns `Anthropic API key required (set ANTHROPIC_API_KEY)` — the analyst is built on
`AnthropicModel`, and neither `ANTHROPIC_API_KEY` nor `MASSIVE_API_KEY` exists on this machine.

## Environment
You are the one task that **must not use the shared venv**. Create your own inside the worktree:
`uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt "pydantic-ai>=2"` (uv's cache makes this fast), and run everything with `.venv/bin/python`.

## Goal
1. Port `src/ai/massive_analyst.py` (and anything else importing `pydantic_ai`: `grep -rn pydantic_ai src`) to the pydantic-ai 2.x API. **Read the installed package source and its docs — do not
   guess the API from memory.** Preserve behavior: same MCP server command (`uvx --from git+https://github.com/massive-com/mcp_massive@v0.4.0 mcp_massive`, env carrying `MASSIVE_API_KEY`),
   same endpoints in `src/api/ai_endpoints.py`, same response shapes.
2. Remove the `<2` pin from `requirements.txt` **only if** everything passes on 2.x; otherwise keep it and explain why.
3. Tests without network or keys: use pydantic-ai's `TestModel`/`FunctionModel` for the agent and a fake MCP toolset. Cover: agent creation with and without `MASSIVE_API_KEY`, the missing-`ANTHROPIC_API_KEY`
   path (`/api/ai/status` message), and one analysis call returning a structured result.
4. `/api/ai/*` must load on startup (look for "AI Trading Analyst endpoints loaded successfully" in the log, and 0 `Could not load AI endpoints` warnings).

## Investigate and report (do not implement unless it is a few lines)
Can the analyst run on the app's default provider (MiniMax, OpenAI-compatible at `https://api.minimax.io/v1`) instead of being hard-blocked on an Anthropic key? Check whether pydantic-ai 2.x's OpenAI-compatible
model/provider takes a `base_url`, and whether tool calling works with MiniMax-M3 (a tiny live call with the MiniMax key from `.env` is allowed). Give a recommendation with the options and their cost.

## Acceptance
Offline tests green under 2.x in your venv; also re-run the **shared-venv** (1.x) suite on your branch to prove you didn't break the pinned setup if the pin stays; report both results.
