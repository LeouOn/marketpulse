# T2b — Repair `tests/test_llm_chat_cached_data.py` (8 failures) and verify the feature

## Problem
All 8 tests fail with `AttributeError: <module 'src.api.routers.llm'> does not have the attribute '_collector'`.
The market-data collector is now reached through `src/api/routers/deps.py`, not a module global in `routers/llm.py`, so the
tests patch a name that no longer exists. The file is ignored by CI.

The tests describe a real product feature: **the LLM chat endpoint (`/api/llm/chat`) injects cached market data into the prompt**
(`_get_cached_market_context`, plus merging frontend-supplied context). If the refactor silently dropped that, it is a regression, not just a stale test.

## Goal
1. Update the tests to patch the new seam.
2. **Prove the feature still works** end to end: with a fake collector returning internals, a request to `/api/llm/chat` (FastAPI `TestClient`, fake LLM router/client so no network)
   must send a prompt that contains the cached market data; with no collector or an exception it must degrade gracefully.
3. If the feature is actually broken, fix it. Keep the diff in `src/api/routers/llm.py` **surgical** — T4 edits the `model-status` handler in the same file, so touch only the chat-context code.

## Acceptance
- `$PY -m pytest tests/test_llm_chat_cached_data.py -q` green, with assertions that check the prompt content (not just a 200).
- Report: what the seam is now, whether the feature had regressed, and every source line you changed.
- Do not edit `.github/workflows/ci.yml` (T10).
