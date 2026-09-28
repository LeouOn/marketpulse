# T6 — Yield-curve pipeline: make it produce data, and fail loudly when it can't

**Prerequisite: T0 must be merged** (branch this task from `main` after T0: `new-worktree.sh T6 main`). T0 introduces `src/core/keys.py`; use its resolver, do not reinvent key lookup.

## Problem (verified 2026-09-28)
`GET /api/yield-curve/current` → `{"success":true,"data":null,"timestamp":null}`, `/history` → `snapshots: []`. Nothing tells the caller why.
Known contributor: `src/yield_curve/fetcher.py::_require_key` read `os.getenv("FRED_API_KEY")` and could not see the key in `.env` (T0 fixes the resolver). Unknown until you look:
whether `src/scheduler/yield_curve_job.py::run_yield_curve_pipeline` is ever scheduled/started by the app, whether the DB tables exist, and whether the pipeline succeeds against real FRED data.

## Goal
With a fresh checkout and the FRED key in `.env`, the yield-curve endpoints return real Treasury-curve data without manual steps, and every failure mode is visible.

## Steps
1. Reproduce (spare port). Trace the path: router (`src/api/routers/yield_curve.py`) → history DAO → pipeline job → fetcher → scheduler wiring (`src/scheduler/scheduler.py`, `main.py` lifespan).
2. Run the pipeline once against **real FRED** (a handful of requests: the tenors in `TENORS` in `fetcher.py`). Confirm curve, spreads (`2s10s`, `3m10y`, …), shape classification and NY Fed recession probability are sensible for today's market; sanity-check them against the raw FRED numbers.
3. Make it self-starting: populate on startup when the table is empty (non-blocking) and refresh daily (business days) via the scheduler. Make sure a scheduler failure logs and surfaces.
4. Make the API honest: when there is no data, return a reason (`no_data: pipeline has not run` / `last_error: …`) instead of a bare `null` — additive to the existing response shape so the frontend keeps working (check `marketpulse-client/src` for consumers; do not edit the frontend).
5. Document a manual trigger (CLI or endpoint) and give the exact command.

## Constraints
Do not modify `src/core/keys.py` beyond bug fixes (T0 owns it). Do not touch `src/research/`. The DB is SQLite via `DATABASE_URL`; don't commit `*.db`.

## Acceptance
- Offline tests with a fake FRED client cover: successful run persists a snapshot, second run is idempotent for the same date, FRED failure is recorded and surfaced, endpoint response with and without data.
- Live evidence: after starting the app with an empty DB, `/api/yield-curve/current` returns today's real curve (quote key numbers; never the key).
- Full suite: no new failures.
