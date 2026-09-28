# T4 — Build the `ds4` local LLM provider (+ complete the model-status endpoint)

Read `docs/local-llm-ds4.md` first — it is the spec, and this task implements its checklist.

## Context
`ds4` is the owner's local DeepSeek V4 Flash server (antirez's implementation; OpenAI-compatible, no auth, native `tool_calls`, SSE streaming,
`reasoning_content`, health via `GET /v1/models`). It was never wired into the app. **MiniMax (`MiniMax-M3` at `https://api.minimax.io/v1`) is the default primary provider and must stay so.**
Nothing about default behavior may change when no `ds4` config is present.

## Goal
`primary_provider: ds4` (or ds4 in the fallback list) works end to end through `ModelRouter`, selectable by explicit configuration — not by id substrings.

## Requirements
1. **Config** (`src/core/config.py`, `LLMSettings` and the `llm.ds4` YAML loading block only — T0 edits the `macro_data` region of the same file):
   `DS4Config(base_url, api_key, timeout, model)`, YAML loading like the `minimax` block. Default `base_url` `http://127.0.0.1:8001/v1` (8000 is the API's own port).
2. **Client** `src/llm/ds4_client.py`: reuse `DeepSeekClient` behavior (it currently reads `settings.llm.deepseek` in `__init__` — give it an optional config argument or subclass it).
   `check_health()`: `GET {base_url}/models`, healthy only for HTTP 200 + JSON; an unreachable server → `False`, never an exception. Preserve `reasoning_content`.
3. **Router** (`src/llm/model_router.py`): register `ds4`; fix `_provider_for_model` so ds4's `deepseek-v4-flash` is not captured by the cloud-DeepSeek substring rule
   (explicit `provider/model` ids, or "if the id equals the configured ds4 model and ds4 is the primary"); extend `_fallback_model_for`, `list_available_models`, and the hard-coded
   unknown-capability default in `route()`.
4. **Status surface**: `LLMManager.get_status()` (`src/llm/llm_client.py`) and `GET /api/llm/model-status` (`src/api/routers/llm.py`, that handler only — T2b edits the chat code in the same file).
   Today model-status lists only `deepseek` and `lm_studio`; it must also list `minimax`, `openrouter` and `ds4` with real router health.
5. **Tests** modeled on `tests/test_minimax_wiring.py` / `tests/test_openrouter_health.py`: offline, using an in-process fake HTTP server (`aiohttp.web`) for the client and router, and independent of the
   local `config/credentials.yaml`.
6. Update `config/credentials.example.yaml` with a commented `ds4` block, and `docs/local-llm-ds4.md` (status → built; remove the "not wired" text).

## Do not
Edit `config/credentials.yaml` (a symlink to the owner's real file). The owner runs their ds4 server on `:8000` today; do not assume a server is available — no live ds4 test is required, but describe in the report how to verify against the real server.

## Acceptance
Fake-server tests prove: health true/false paths, completion + streaming through the router when ds4 is primary, fallback to MiniMax when ds4 is down,
and `model-status` shape. Full suite: no new failures.
