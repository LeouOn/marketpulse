# T8 — Verify the Next.js client on a clean machine and against the real backend

## Context
`marketpulse-client/` (Next 16, React 19, Tailwind 3, Jest, ESLint 9, TypeScript 5) received ~40 UI commits (a "Jane Street" density redesign, command palette, dashboard decomposition, a11y pass).
This machine has **no `node_modules`** and the frontend has never been built here. Node is v24 (via fnm). Scripts: `dev` (`next dev --webpack`), `build`, `lint`, `test` (jest).

## Goal
Know — with evidence — whether the frontend builds, passes its own checks, and renders correctly with live data; fix frontend-only defects; report backend defects.

## Steps
1. `npm ci` (or `npm install` if the lockfile is stale — note it). Then, quoting results: `npm run lint`, `npx tsc --noEmit`, `npm test`, `npm run build`.
2. Fix failures that are frontend-only (lint errors, type errors, broken tests, build errors). Keep changes minimal; no redesign.
3. Start the backend on a spare port (`$PY -m uvicorn src.api.main:app --port 8010`) and the client pointing at it (find the API base-URL setting in `next.config.js` / `.env*` / `src/`; do not change the owner's `.env`).
   Drive every tab/page (dashboard, chart/symbol, compare, reports, research, AI chat, backtest, command palette) with whatever browser automation your environment provides
   (Playwright, or a browser tool). For each: screenshot, console errors, failed network requests (status + URL).
4. Compare on-screen numbers to the API JSON for a few fields (DXY, breadth, P&L, TICK/VOLD) and list anything showing mock/placeholder/proxy data as if it were live.
   (Known backend issues being handled elsewhere: DXY/GC are ETF proxies (T7a), yield curve empty (T6), `/api/research/regimes` 503 (T3a), `/api/ai/*` needs an Anthropic key (T5).)

## Constraints
Edit only `marketpulse-client/**`. Do not commit `node_modules/`, `.next/`, or screenshots (put screenshots in the scratch/temp area and list paths in the report).

## Acceptance
Report: the four command outputs (pass/fail counts), the per-page table (renders? console errors? failing requests?), what you fixed, and a prioritised list of backend/data issues you saw.
