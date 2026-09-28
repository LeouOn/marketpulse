# T2c — `tests/test_e2e_agentic.py` is a script pretending to be a test file

## Problem
pytest reports 6 **errors** (`fixture 'settings' not found`) for `test_deepseek_connectivity`, `test_model_router`, `test_data_agent`,
`test_technical_agent`, `test_full_orchestrator`, `test_structured_output`. The functions take a `settings` argument and print results — they were
written as a manual script (see `main()` and the `__main__` block; the docstring calls it an "end-to-end trace") and call **live LLM APIs** (the orchestrator smoke test says "requires DEEPSEEK_API_KEY").
CI ignores the file.

## Goal
1. Make the file a proper **opt-in live test module**: add a `settings` fixture (`get_settings()`), mark each test `@pytest.mark.live`
   (skipped unless `RUN_LIVE_TESTS=1` — see the marker docs in `pyproject.toml`), assert on results instead of printing, and
   choose the provider from configuration (the default primary provider is now **MiniMax**, not DeepSeek — check what each test hard-codes).
2. **Run it live once** with `RUN_LIVE_TESTS=1` against the configured providers (MiniMax key and DeepSeek/OpenRouter keys are available via
   `.env`/environment). This is the first end-to-end check of the agent pipeline (`src/llm/agents/`: data agent, technical agent, orchestrator,
   structured output) with MiniMax as primary. Keep prompts small; do not loop.
3. Fix genuine defects you find in `src/llm/agents/` (list each; keep diffs minimal). Known quirk: MiniMax-M3 returns its reasoning inline as `<think>…</think>`
   in `content`; check whether the agents' JSON/structured parsing survives that.

## Acceptance
- Default `pytest tests/test_e2e_agentic.py -q` → skipped, not errors.
- `RUN_LIVE_TESTS=1 $PY -m pytest tests/test_e2e_agentic.py -q` results quoted in your report, per test, with any failure explained (provider issue vs code bug).
- Do not edit CI config (T10).
