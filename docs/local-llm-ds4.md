# Local LLM provider: `ds4` (DeepSeek V4 Flash, antirez's implementation)

**Status: built (T4).** ds4 is a first-class provider: configured via the
`llm.ds4` block (default `http://127.0.0.1:8001/v1` — **not** 8000, which is
the MarketPulse API itself), client `src/llm/ds4_client.py`, registered in
`ModelRouter`, listed in `/api/llm/model-status` and `LLMManager.get_status()`.
MiniMax (`MiniMax-M3` at `https://api.minimax.io/v1`) remains the DEFAULT
primary provider; nothing changes when no `ds4` block is configured.

## What the local server offers

- OpenAI-compatible API (default expected at `http://127.0.0.1:8001/v1`),
  no auth (any bearer token)
- Native `tool_calls`, SSE streaming, `reasoning_content` in responses
  (`DS4Client` returns the raw response dict, so `reasoning_content`
  survives end to end)
- Health check: `GET /v1/models` — healthy only for HTTP 200 + JSON; an
  unreachable server reports unhealthy, never raises
- Model id: `deepseek-v4-flash`

## How model ids route (the old collision, fixed)

`ModelRouter._provider_for_model` resolves providers explicitly now:

- `"ds4/deepseek-v4-flash"` (provider-prefixed) → `ds4`, and the client
  receives the bare model id
- the bare `deepseek-v4-flash` → `ds4` when `primary_provider: ds4`
  (otherwise the cloud-DeepSeek substring rule still applies)

## Switching to local

In `config/credentials.yaml` (see `config/credentials.example.yaml` for a
commented block):

```yaml
llm:
  ds4:
    base_url: http://127.0.0.1:8001/v1
  model_routing:
    primary_provider: ds4
    fallback_providers: minimax,deepseek,lm_studio,openrouter
    reasoning: ds4/deepseek-v4-flash
    fast: ds4/deepseek-v4-flash
    standard: ds4/deepseek-v4-flash
    structured_output: ds4/deepseek-v4-flash
```

If ds4 is down, `ModelRouter.route()` falls through the fallback chain
(e.g. to MiniMax) automatically.

## Verifying against the real server

No live ds4 test runs in CI (the server is the owner's local machine).
With the server running on `:8001`:

```bash
curl -s http://127.0.0.1:8001/v1/models | head -c 200        # health
curl -s localhost:8000/api/llm/model-status | python -m json.tool | grep -A5 '"ds4"'
$PY -m pytest tests/test_ds4_wiring.py -q                     # offline suite
```

`model-status` should show `"ds4": {"healthy": true, ...}` with a response
time, and chat with `primary_provider: ds4` should answer from the local
server (fallback to MiniMax appears in the router log if it is down).

## Related open items (not ds4-specific)

- OpenRouter's health check still looks optimistic with no session
  (key present ⇒ healthy); MiniMax shares that fast-path by design.
- Routes/tests that enumerate `app.routes` undercount on FastAPI 0.141
  because included routers are nested (`_IncludedRouter`); use
  `app.openapi()` or fix the helpers.
