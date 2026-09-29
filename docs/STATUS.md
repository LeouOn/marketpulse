# MarketPulse status

One page, measured **2026-09-29** against `main` (`bbf749f`). Every "verify" command below was
run on a fresh clone of that commit; the transcript is in
[`docs/agent-tasks/PICKUP.md`](agent-tasks/PICKUP.md).

**Legend** — ✅ works · ⚠️ partial · ❌ broken · 🔑 needs a key

---

## Backend API — ✅

FastAPI, 121 routes across 8 routers, boots in ~10 s on SQLite with **no keys and no Docker**.

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -m uvicorn src.api.main:app --port 8000
# then:
curl -s localhost:8000/api/debug/routes | head -c 200
```

* Startup must log `... endpoints loaded successfully` per router and **zero**
  `Could not load ... endpoints` lines. `tests/test_app_boots.py` enforces this in CI.
* PostgreSQL and Redis are optional. Redis absent → caching disabled only.
* `tests/test_app_boots.py` also pins the route count against
  `tests/fixtures/route_snapshot.json`.

## Frontend dashboard — ⚠️

Next.js 16 / React 19. Builds and runs; the API proxy works end to end.

```bash
cd marketpulse-client && npm ci && npm run lint && npm run build && npm run dev
# http://localhost:3000  →  200
curl -s -o /dev/null -w '%{http_code}\n' localhost:3000/api/market/symbols   # → 200 (proxied)
```

* `/api/*` is proxied to `http://localhost:8000` by `src/middleware.ts`; override with `BACKEND_URL`.
* **Open:** the DXY and gold panels predate the additive `symbol` / `instrument` / `is_proxy`
  fields, so proxy instruments are not labelled as such.
* **Behaviour change:** panels that used to show fabricated internals now show **nothing**,
  because internals are withheld unless `MARKETPULSE_ALLOW_MOCK=1`. See
  [`data-provenance.md`](data-provenance.md).

## Multi-asset research lab — ⚠️

`/api/research/{asset}/…` over BTC, EQUITIES, GOLD, OIL, HOUSING.

```bash
curl -s localhost:8000/api/research/assets
for a in BTC EQUITIES GOLD OIL HOUSING; do
  printf '%s ' "$a"; curl -s -o /dev/null -w '%{http_code}\n' "localhost:8000/api/research/$a/data"
done
```

| Asset | Source | Result |
|---|---|---|
| BTC | Yahoo | ✅ 200, 4394 rows (2014-09-17 →) |
| GOLD | Yahoo | ✅ 200, 5498 rows (2004-11-18 →) |
| EQUITIES | Alpaca | 🔑 400 — *"Alpaca credentials are not configured"*, an explicit and correct error |
| OIL | EIA | ❌ 500 — `Out of range float values are not JSON compliant: nan` |
| HOUSING | FRED | ❌ 500 — same NaN error |

* **Open bug (OIL, HOUSING).** The fetch succeeds — `/api/research/OIL/regime` returns 200 with
  real probabilities — but the `/data` payload contains a non-finite float and
  `JSONResponse` refuses to serialise it. `src/api/json_utils.py::to_builtin` already maps
  NaN/inf to `None` and is used by `routers/options.py`; the research payloads do not use it.
  This is a small, low-risk fix in `src/api/routers/research_router.py`.
* 🔑 FRED and/or EIA for the two government-backed assets; Alpaca for EQUITIES.

## Treasury yield curve — ✅ (with one open decision)

```bash
curl -s -X POST localhost:8000/api/yield-curve/refresh     # live FRED fetch
curl -s localhost:8000/api/yield-curve/current
# {"success":true,"data":{"date":"2026-09-29","curve":{"3mo":4.24,"2y":4.81,"10y":5.0…}}}
```

* 🔑 `FRED_API_KEY`. Without it `/api/yield-curve/current` returns `200` with
  `success: false` — an honest "no snapshot", not a crash.
* The backfill date-misalignment bug is **fixed** (`7a4c905`); the regression test fails on the
  old code.
* **Open decision:** `classify_shape` in `src/yield_curve/curves.py` only treats `2s10s < 0` as
  inverted, so a curve where 2y > 30y but 2y < 10y is *not* labelled `INVERTED`, and
  `HUMPED` / `INVERTED_HUMPED` only trigger when 2y, 5y and 30y are all present. Needs a product
  decision, not a lint fix — see [`agent-tasks/FOLLOWUPS.md`](agent-tasks/FOLLOWUPS.md) §1b.

## LLM providers — ⚠️

MiniMax is the default; `ds4` (local), DeepSeek, OpenRouter and LM Studio are configured.

```bash
curl -s localhost:8000/api/llm/models
curl -s localhost:8000/api/llm/model-status
curl -s -X POST localhost:8000/api/llm/chat -H 'Content-Type: application/json' \
     -d '{"message":"In one short sentence: what is a stop loss?"}'
# → 200, real answer
```

* 🔑 the chosen provider's key. `GET /api/llm/model-status` reports `configured` per provider and
  correctly reports `false` for placeholder keys.
* **Known issue:** MiniMax-M3 returns its reasoning inline in `content`, so `/api/llm/chat`
  currently hands the user a raw `<think>…</think>` block before the answer. `strip_think()` in
  `src/ai/` and `src/llm/agents/` handles this, but the chat router does not.
* **Known issue:** the tool-calling agent pipeline (`src/llm/agents/`) is **tool-less on
  MiniMax** — `MiniMaxClient` has no `generate_with_tools`, so the data/technical/orchestrator
  agents answer from model memory. They now report `success=False` rather than pretending
  (`src/llm/agents/base.py`). The fix belongs in `src/llm/minimax_client.py`, or in
  `ModelRouter` by making `route()` capability-aware. Until then, use the AI analyst below,
  which runs its own tool loop.
* For a local provider see [`local-llm-ds4.md`](local-llm-ds4.md) — run it on **:8001**; the API
  owns :8000.

## AI trading analyst — ✅ with one reporting bug

`/api/ai/*` (7 routes) runs on the configured provider — **MiniMax by default, no Anthropic key
needed**.

```bash
curl -s localhost:8000/api/ai/status
curl -s -X POST localhost:8000/api/ai/query -H 'Content-Type: application/json' \
     -d '{"question":"What is a stop loss?","include_technical_analysis":false}'
```

* 🔑 the provider's key. 🔑 `MASSIVE_API_KEY` additionally enables the Massive.com MCP tools
  (market data); without it the analyst still answers, from model knowledge only.
* Verified live against MiniMax-M3: real answer, and a real tool call through a test toolset.
* **Open bug (misleading status).** With **no `.env` at all**, the configured key resolves to an
  unresolved `${api_keys:minimax:api_key}` interpolation token. `_resolve_provider()` in
  `src/ai/massive_analyst.py` only rejects values containing `your_`, so the token is accepted as
  a real key: `/api/ai/status` then reports `provider_api_configured: true` and a real query
  fails with a MiniMax 401 wrapped in `success: true`. With `.env.example` copied (a `your_…`
  placeholder) the endpoint correctly reports
  `minimax API key required (set MINIMAX_API_KEY)`. The existing
  `src/core/keys.py::_PLACEHOLDER` (`^(your_|\$\{)`) is the pattern to reuse.

---

## Tests and CI — ✅

```bash
env -i HOME="$HOME" PATH="$PATH" .venv/bin/python -m pytest tests -q
# → 1078 passed, 32 skipped
uvx ruff@0.16.9 check src tests          # All checks passed!
uvx ruff@0.16.9 format --check src tests # 266 files already formatted
```

The suite is hermetic by default: real keys, `config/credentials.yaml` and research data paths
are neutralised, so it passes with or without a populated `.env`. Opt-ins are listed in the
[README](../README.md#test-opt-ins).

## Open items, in one place

| # | Item | Where |
|---|---|---|
| 1 | `classify_shape` ignores the 2s>30s spread — needs a product decision | `src/yield_curve/curves.py` |
| 2 | `OIL` / `HOUSING` research `/data` returns 500 on a NaN | `src/api/routers/research_router.py` |
| 3 | `/api/ai/status` misreports an unresolved `${…}` key as configured | `src/ai/massive_analyst.py` |
| 4 | `/api/llm/chat` leaks MiniMax's inline `<think>` reasoning | `src/api/routers/llm.py` |
| 5 | Agent pipeline has no tool calling on MiniMax | `src/llm/minimax_client.py` or `src/llm/model_router.py` |
| 6 | Frontend DXY/gold labels predate `symbol` / `instrument` / `is_proxy` | `marketpulse-client/` |
| 7 | Two "computed then discarded" values look like unfinished features | [`agent-tasks/FOLLOWUPS.md`](agent-tasks/FOLLOWUPS.md) §2 |
