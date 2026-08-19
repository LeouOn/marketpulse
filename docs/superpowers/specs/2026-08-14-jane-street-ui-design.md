# MarketPulse UI Redesign — Jane Street Quant Workstation

**Date:** 2026-08-14
**Status:** Approved direction (user decisions locked 2026-08-14)
**Target:** `marketpulse-client` (Next.js 16 App Router, React 19, Tailwind 3.4, lightweight-charts 5.2)

## Goal

Restyle the entire MarketPulse UI (all routes) into a Jane Street-style expert quant
workstation: dark, dense, chart-and-table-first, keyboard-operable, visually quiet —
the data dominates. Add a light mode toggle. No changes to data flow, API contracts,
React Query keys, or routing.

## User decisions

| Decision | Choice |
|---|---|
| Scope | Whole app, all pages + shell chrome |
| Theme | Dark default **+ light toggle** |
| Density | Full density (Jane Street signature) |
| Typography | Inter (UI) + monospace (all market data) |
| Keyboard | Command palette (Ctrl+K / `/`) + j/k row nav + `?` help (maintainer recommendation, accepted) |

## Design language (derived from Bonsai/jdash research)

Principles: flat panels, 1px borders, 2–4px radii, tiny uppercase panel titles,
compact rows, monospace tabular numerals, explicit state everywhere, no gradients /
glass / shadows / oversized KPI cards. Semantic color is signal, never decoration.

### Color tokens

Dark (default, `:root`):

```
--canvas:          #17181b   (app background)
--surface:         #1d1e22   (panels)
--surface-raised:  #24262b   (inputs, raised rows)
--surface-hover:   #2b2e34

--border-subtle:   #2b2f35
--border-default:  #3a3f47
--border-strong:   #555b63
--border-focus:    #4aa6d8

--text-primary:    #e6e8eb
--text-secondary:  #a4a9b1
--text-muted:      #737a84

--accent-teal:     #3b9da0   (primary series / brand accent)
--accent-green:    #8be879   (up / positive / live)
--accent-red:      #ff5e62   (down / negative / error)
--accent-amber:    #e4b455   (warning / stale / pending)
--accent-blue:     #7d9fc7   (selection / links / secondary series)
```

Light (`[data-theme="light"]`): Jane Street public-site inspired — paper background
`#f6f7f5`, white surfaces `#ffffff`, raised `#efefec`, text `#1c1e21` / `#5a5f66` /
`#8a9098`, borders `#d9dcd7` / `#c4c8c2` / `#9aa09a`, pale-green brand wash
`#d6e9e2` (selection tint / active nav), focus `#2b6ca3`. Semantic hues darkened for
contrast: teal `#1f7a7d`, green `#1e7d3c`, red `#c73a3e`, amber `#8a6415`,
blue `#3d5a80`.

Conventions kept from current app: green = up/positive, red = down/negative. Never
rely on color alone — always sign/delta text, state label, or glyph with it.

### Typography

- UI: **Inter** (existing, `next/font`).
- Data: **JetBrains Mono** (new, `next/font`), applied to every price, pct, volume,
  timestamp, ID, and axis label. `font-variant-numeric: tabular-nums` everywhere
  numeric.
- Panel titles: 11px uppercase, `letter-spacing: 0.08em`, `--text-secondary`.
- Scale: 11/12/13/15/18/22px. Hero numbers (e.g. NQ price) may use 22–28px mono.

### Density rules

- Table body rows 26–28px (`py-[3px] text-[12.5px]` equivalent), header rows ~28px.
- Panel padding 8–10px; panel gap 8–10px; page gutter 12–16px.
- Border radius: 2px panels, 3px controls. Shadows: none (borders only).
- Kill: `rounded-xl/2xl`, `shadow-*`, gradient text, glass blur, oversized cards.

### Component styles

- **Panel**: `bg-[--surface] border border-[--border-subtle] rounded-[2px]`,
  title bar `px-2.5 py-1.5` uppercase.
- **Data table**: collapsed 1px borders, uppercase 11px headers, zebra via
  `--surface-raised` at low contrast, numeric cells right-aligned mono, focused row
  `bg #17394b` + 1px `--border-focus` outline (dark) / `#d6e9e2` tint (light).
- **Controls**: 28px height, 1px border, 3px radius, visible focus ring, kbd hints
  on primary actions.
- **Status**: dot + explicit text (`LIVE`, `DELAYED 15m`, `STALE`, `ERROR`) + data
  age; never a bare colored dot.
- **Charts**: lightweight-charts themed from a shared `chartTheme()` helper reading
  CSS custom properties via `getComputedStyle` (so light/dark both work). Candles
  green/coral, volume 30% alpha, gridlines `--border-subtle`, axis text
  `--text-muted`. Multi-series palette: teal, green, coral, blue, amber, muted violet
  (rarely).
- **Missing data**: hatched background (`repeating-linear-gradient`), `—` glyph —
  never a blank cell that reads as zero.

### Interaction

- **Command palette** (`Ctrl+K` or `/`): fuzzy nav to all routes + symbol lookup
  (reuses TopBar search logic), `?` opens keyboard-help overlay.
- **Table keyboard nav**: j/k or ↑/↓ moves focused row, Enter opens (`/chart/SYM`),
  Escape clears. Implemented on trending table + dashboard data tables via one
  reusable `useRowNav` hook.
- All existing mouse interactions unchanged.

## Architecture changes

1. **ThemeProvider** (`src/components/theme-provider.tsx`): React context,
   `data-theme` on `<html>`, persisted `localStorage`, inline no-flash script in
   `layout.tsx`. Default: dark.
2. **Chart theme module** (`src/lib/chart-theme.ts`): `getChartTheme()` reads CSS
   vars; used by `ChartWidget`, `MultiLineChart` (compare page), re-subscribes on
   theme change.
3. **Decompose `ThreeColumnDashboard.tsx`** (641 lines) into
   `src/components/dashboard/` modules: `CommandCenter.tsx` (NQ hero + breadth +
   regime + position calc + session stats), `CenterTabs.tsx` (tab frame), existing
   tab components stay, `AiChatPanel.tsx` (wrapper around `llm-chat`), plus small
   shared pieces (`StatTile`, `MiniTable`). Props/data contracts unchanged — purely
   structural + styling.
4. **New components**: `CommandPalette.tsx`, `KbdHelp.tsx`, `useRowNav` hook,
   `StateDot.tsx` (status dot + label + age).
5. **Tailwind**: extend colors to CSS-var-backed aliases (`canvas`, `surface`,
   `line`, `ink`, `pos`, `neg`, `warn`, `sel`, `teal`), fonts `sans`/`mono`, compact
   component classes (`.panel`, `.panel-title`, `.data-table`, `.btn`, `.kbd`).
6. **Re-brand**: flat wordmark "MARKETPULSE" (mono, letterspaced) replacing
   blue→purple gradient; new `icon.svg` (concentric-circle motif, teal on charcoal).

## Non-goals / constraints

- No changes to: API client (`lib/api.ts`), React Query keys/hooks, middleware,
  routing, WS/NDJSON streaming logic, `llm-chat.tsx` streaming internals (styling
  only), backend.
- No library additions beyond JetBrains Mono via `next/font/google`. No
  component-library deps (no shadcn/radix).
- Charts stay on lightweight-charts 5.2.
- Visual + structural refactor only; behavior preserved.

## Pages in scope (all)

Shell (`LayoutShell`, `Sidebar`, `TopBar`, footer) · `/` (dashboard) · `/trending` ·
`/chart/[symbol]` · `/symbol/[symbol]` · `/research/[asset]` · `/research/compare` ·
`/research/reports` · `/research/reports/[id]` · all tab components ·
`YieldCurvePanel` · `llm-chat` (visual only) · shared primitives (`Sparkline`,
`PriceCell`, `FiftyTwoWeekBar`, `AssetPicker`, `AgentTracePanel`,
`PipelineProgress`, `LoadingSpinner`).

## Success criteria

1. `npm run build` passes; existing Jest tests pass; no TS errors (no `as any`).
2. Every route renders correctly in **dark and light**, verified by Playwright
   screenshots.
3. No residual old-palette utilities on scoped pages (grep clean for
   `emerald-|from-blue-500|rounded-2xl|shadow-` in touched files, excluding
   intentional exceptions).
4. Ctrl+K palette navigates; j/k works on trending table; `?` shows help.
5. Dashboard still polls/updates (60s cycle intact), charts still render candles,
   chat still streams.
