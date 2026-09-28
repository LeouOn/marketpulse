# Local LLM provider: `ds4` (DeepSeek V4 Flash, antirez's implementation)

**Status: not wired in.** The default LLM provider is MiniMax (`MiniMax-M3` via
`https://api.minimax.io/v1`). `ds4` was a local setup (an OpenAI-compatible server
running DeepSeek V4 Flash) that existed only as a block in the gitignored
`config/credentials.yaml`. This note records why it never actually worked and what to
build to bring it back as a first-class provider.

## What the local server offers (from the old credentials.yaml notes)

- OpenAI-compatible API at `http://127.0.0.1:8000/v1`, no auth (any bearer token)
- Native `tool_calls`, SSE streaming, `reasoning_content` in responses
- Health check: `GET /v1/models`
- Model id: `deepseek-v4-flash`

## Why it never worked (verified 2026-09-28)

1. **No `ds4` in the code.** `grep -rn ds4 src` finds nothing. `LLMSettings` has no
   `ds4` field, and `Settings._load_from_yaml` copies YAML keys only into fields that
   exist (`hasattr` check), so the `llm.ds4` block was silently ignored.
2. **Model ids were routed to cloud DeepSeek.** `ModelRouter._provider_for_model`
   guesses the provider from the model id, and any id containing "deepseek" goes to the
   cloud `deepseek` provider. With `deepseek-v4-flash` in `model_routing`, every
   capability resolved to `api.deepseek.com`, whatever `primary_provider` said.
   `primary_provider: ds4` only influenced the fallback list.
3. **Port clash.** ds4 defaulted to `:8000`, the same port as the MarketPulse API
   (`PORT=8000` in `.env`).

## Build checklist

1. **Config** (`src/core/config.py`)
   - Add `LLMSettings.DS4Config` (`base_url`, `api_key`, `timeout`, `model`) and a
     `ds4` field on `LLMSettings`.
   - Add an `if "ds4" in llm_data:` block in `_load_from_yaml`, copying the `minimax`
     one (about line 279).
   - Default `base_url` should be a port other than 8000, e.g. `http://127.0.0.1:8001/v1`.
     Restart the ds4 server on that port and update `credentials.yaml`.
2. **Client** (`src/llm/ds4_client.py`)
   - It speaks the same protocol as `DeepSeekClient`, but that class reads
     `settings.llm.deepseek` in `__init__`. Either give it an optional config argument
     or subclass it and point at `settings.llm.ds4`.
   - `check_health()`: `GET {base_url}/models`, require HTTP 200 and a JSON content type
     (the same rule as `MiniMaxClient.check_health`). A server that isn't running should
     report unhealthy, not raise.
   - Keep `reasoning_content` from responses; decide whether to surface or drop it.
     (MiniMax-M3 puts reasoning inline as `<think>…</think>` in `content`, so anything
     that parses replies already needs to strip that.)
3. **Router** (`src/llm/model_router.py`)
   - Register `ds4` in `__aenter__` and pick its priority.
   - **Fix provider selection by explicit config, not id substrings.** ds4 serves
     `deepseek-v4-flash`, which collides with the cloud DeepSeek heuristic. Options:
     provider-prefixed ids in `model_routing` (`ds4/deepseek-v4-flash`), or resolve
     `primary_provider` first when the id equals `settings.llm.ds4.model`.
   - Extend `_fallback_model_for`, `list_available_models`, and the "unknown capability"
     default in `route()` (currently hard-coded to minimax).
4. **Status surface**
   - `LLMManager.get_status()` in `src/llm/llm_client.py` and `/api/llm/model-status`
     need a `ds4` entry. Check the frontend model picker too.
   - `get_status()` reports a provider `available` whenever its key isn't the placeholder
     string, so an unresolved `${...}` counts as available. Tighten that at the same time.
5. **Tests**: mirror `tests/test_minimax_wiring.py` (config defaults, client health with
   fake sessions, router registration and provider selection, status). Keep them
   independent of the local `credentials.yaml`, as the MiniMax ones now are.
6. **Docs/config**: add a `ds4` block to `config/credentials.example.yaml`, and remove the
   "not wired in" comments from the local `credentials.yaml`.

## Switching back to local once built

In `config/credentials.yaml`:

```yaml
llm:
  model_routing:
    primary_provider: ds4
    fallback_providers: minimax,deepseek,lm_studio,openrouter
    reasoning: <ds4 model id or prefixed id>
    fast: <same>
    standard: <same>
    structured_output: <same>
```

## Related open items (not ds4-specific)

- OpenRouter's health check looks optimistic too (reported healthy with no key).
- Routes/tests that enumerate `app.routes` undercount on FastAPI 0.141 because included
  routers are nested (`_IncludedRouter`); use `app.openapi()` or fix the helpers.
