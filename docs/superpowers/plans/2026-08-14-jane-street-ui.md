# Jane Street UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle all of `marketpulse-client` into a dense, dark-first Jane Street-style quant workstation with a light-mode toggle, monospace data typography, themed charts, and keyboard-first navigation — with zero changes to data flow, API contracts, or routing.

**Architecture:** Token-first restyle. One CSS custom-property system (`:root` dark / `[data-theme="light"]`) drives everything; Tailwind aliases point at those vars so every surface flips with `data-theme`. A ThemeProvider flips the attribute, a chart-theme module reads the vars for `lightweight-charts`, and the 641-line `ThreeColumnDashboard` is decomposed into focused modules while keeping its data contracts identical.

**Tech Stack:** Next.js 16 (App Router), React 19, Tailwind 3.4, lightweight-charts 5.2, JetBrains Mono via `next/font/google`, Jest + Testing Library, Playwright (visual verification).

**Spec:** `docs/superpowers/specs/2026-08-14-jane-street-ui-design.md`

## Global Constraints

- **No behavior changes.** API client (`src/lib/api.ts`), React Query keys/hooks, `src/middleware.ts`, routing, WS/NDJSON streaming logic stay untouched. `llm-chat.tsx` gets visual-only changes.
- **No type suppression.** `as any` / `@ts-ignore` are forbidden. Strict TS stays green.
- **No new runtime deps.** JetBrains Mono comes via `next/font/google` (build-time, no package).
- **Every command runs in `marketpulse-client/`** unless noted.
- **Commit policy:** commit steps below are written per convention but execution defers until the user explicitly approves commits.
- **Design tokens (verbatim from spec):**

```
DARK :root
--canvas #17181b  --surface #1d1e22  --surface-raised #24262b  --surface-hover #2b2e34
--border-subtle #2b2f35  --border-default #3a3f47  --border-strong #555b63  --border-focus #4aa6d8
--text-primary #e6e8eb  --text-secondary #a4a9b1  --text-muted #737a84
--teal #3b9da0  --green #8be879  --red #ff5e62  --amber #e4b455  --blue #7d9fc7
LIGHT [data-theme="light"]
--canvas #f6f7f5  --surface #ffffff  --surface-raised #efefec  --surface-hover #e6e8e3
--border-subtle #d9dcd7  --border-default #c4c8c2  --border-strong #9aa09a  --border-focus #2b6ca3
--text-primary #1c1e21  --text-secondary #5a5f66  --text-muted #8a9098
--teal #1f7a7d  --green #1e7d3c  --red #c73a3e  --amber #8a6415  --blue #3d5a80
--brand-wash #d6e9e2 (light only; selection tint / active nav)
Series palette order: teal, green, coral(red), blue, amber, #b69bd8 (rare)
```

- **Class migration map** (apply to every file in restyle tasks; every task implicitly includes this table):

| Old utility | New utility |
|---|---|
| `bg-black`, `bg-gray-950` | `bg-canvas` |
| `bg-gray-900` (cards) | `bg-surface` |
| `bg-gray-800`, `bg-gray-800/60`, `bg-gray-800/50`, `bg-slate-900/50` | `bg-surface-raised` |
| `bg-gray-700`, hover `bg-gray-700/50` | `bg-surface-hover` |
| `border-gray-800`, `border-slate-800` | `border-line-subtle` |
| `border-gray-700`, `border-gray-600` | `border-line` |
| `text-white` | `text-ink` |
| `text-gray-100/200/300` | `text-ink` |
| `text-gray-400`, `text-slate-400` | `text-ink-secondary` |
| `text-gray-500`, `text-gray-600`, `text-slate-500` | `text-ink-muted` |
| `text-emerald-400/500/600`, `text-emerald-*` | `text-pos` |
| `text-red-400/500/600` | `text-neg` |
| `text-yellow-400`, `text-amber-400/500` | `text-warn` |
| `text-blue-400/500/600` (actions/info) | `text-sel` |
| `text-purple-400/500/600` | `text-teal` |
| `bg-emerald-500/10`, `bg-emerald-500/20`, `bg-emerald-100` | `bg-pos-dim` |
| `bg-red-500/10`, `bg-red-500/20` | `bg-neg-dim` |
| `bg-blue-500/10`, `bg-blue-500/20` | `bg-sel-dim` |
| `bg-yellow-500/10`, `bg-amber-500/10` | `bg-warn-dim` |
| `from-blue-500 to-purple-500 ...` (gradients) | flat `text-teal` (or `text-ink` for headings) |
| `rounded-lg`, `rounded-xl`, `rounded-2xl` | `rounded-[2px]` (panels) / `rounded-[3px]` (controls) |
| `shadow`, `shadow-lg`, `shadow-2xl` | remove |
| `backdrop-blur*`, glass patterns | remove |
| `text-sm text-gray-500` table headers | `panel-title` style: 11px uppercase tracking |
| price/pct/volume/timestamp values | add `font-mono tabular-nums` |

- **Density rules for restyles:** panel padding `p-2.5` (10px) max, panel gaps `gap-2.5`, table cells `px-2 py-[3px]` with `text-[12.5px]`, panel titles `text-[11px] uppercase tracking-[0.08em] text-ink-secondary`, buttons `h-7`, inputs `h-7`.
- **Verification sequence used throughout:** `npm run build` (type-check + build), `npm test` (Jest), `npm run lint`. Visual: Playwright screenshots dark + light.

---

### Task 1: Design token foundation (globals.css, Tailwind, fonts, ThemeProvider)

**Files:**
- Modify: `src/app/globals.css` (full rewrite)
- Modify: `tailwind.config.ts` (full rewrite)
- Modify: `src/app/layout.tsx`
- Create: `src/components/theme-provider.tsx`
- Test: `src/components/__tests__/theme-provider.test.tsx`

**Interfaces:**
- Produces: `useTheme(): { theme: 'dark' | 'light'; toggleTheme: () => void }` from `@/components/theme-provider`; Tailwind color aliases `canvas, surface, surface-raised, surface-hover, line, line-subtle, line-strong, line-focus, ink, ink-secondary, ink-muted, pos, pos-dim, neg, neg-dim, warn, warn-dim, sel, sel-dim, teal, teal-dim`; font utilities `font-sans` (Inter) / `font-mono` (JetBrains Mono). All legacy CSS classes (`.positive`, `.data-table`, `.dashboard-grid`, `.sector-bar*`, `.price-flash-*`, etc.) remain defined, re-pointed at the new tokens, so not-yet-migrated pages render coherently.

- [ ] **Step 1: Write the failing test**

```tsx
// src/components/__tests__/theme-provider.test.tsx
import { render, screen, fireEvent } from '@testing-library/react';
import { useTheme, ThemeProvider } from '@/components/theme-provider';

function Probe() {
  const { theme, toggleTheme } = useTheme();
  return (
    <button onClick={toggleTheme} data-testid="probe">
      {theme}
    </button>
  );
}

describe('ThemeProvider', () => {
  it('defaults to dark and toggles to light, persisting choice', () => {
    localStorage.removeItem('mp-theme');
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>
    );
    const probe = screen.getByTestId('probe');
    expect(probe.textContent).toBe('dark');
    expect(document.documentElement.dataset.theme).toBe('dark');
    fireEvent.click(probe);
    expect(probe.textContent).toBe('light');
    expect(document.documentElement.dataset.theme).toBe('light');
    expect(localStorage.getItem('mp-theme')).toBe('light');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- theme-provider`
Expected: FAIL — module `@/components/theme-provider` not found.

- [ ] **Step 3: Write `src/components/theme-provider.tsx`**

```tsx
'use client';

import { createContext, useCallback, useContext, useEffect, useState } from 'react';

type Theme = 'dark' | 'light';

interface ThemeContextValue {
  theme: Theme;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);
const STORAGE_KEY = 'mp-theme';

function isTheme(v: string | null): v is Theme {
  return v === 'dark' || v === 'light';
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<Theme>('dark');

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (isTheme(stored)) setTheme(stored);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
  }, [theme]);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => {
      const next: Theme = prev === 'dark' ? 'light' : 'dark';
      localStorage.setItem(STORAGE_KEY, next);
      return next;
    });
  }, []);

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider');
  return ctx;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- theme-provider`
Expected: PASS (2 assertions in 1 test).

- [ ] **Step 5: Rewrite `tailwind.config.ts`**

```ts
import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['var(--font-inter)', 'system-ui', 'sans-serif'],
        mono: ['var(--font-jbmono)', 'ui-monospace', 'SFMono-Regular', 'Consolas', 'monospace'],
      },
      colors: {
        canvas: 'var(--canvas)',
        surface: {
          DEFAULT: 'var(--surface)',
          raised: 'var(--surface-raised)',
          hover: 'var(--surface-hover)',
        },
        line: {
          DEFAULT: 'var(--border-default)',
          subtle: 'var(--border-subtle)',
          strong: 'var(--border-strong)',
          focus: 'var(--border-focus)',
        },
        ink: {
          DEFAULT: 'var(--text-primary)',
          secondary: 'var(--text-secondary)',
          muted: 'var(--text-muted)',
        },
        pos: { DEFAULT: 'var(--green)', dim: 'var(--green-dim)' },
        neg: { DEFAULT: 'var(--red)', dim: 'var(--red-dim)' },
        warn: { DEFAULT: 'var(--amber)', dim: 'var(--amber-dim)' },
        sel: { DEFAULT: 'var(--blue)', dim: 'var(--blue-dim)' },
        teal: { DEFAULT: 'var(--teal)', dim: 'var(--teal-dim)' },
      },
    },
  },
  plugins: [],
}
export default config
```

- [ ] **Step 6: Rewrite `src/app/globals.css`**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

/* ===== Design tokens — dark (default) ===== */
:root {
  --canvas: #17181b;
  --surface: #1d1e22;
  --surface-raised: #24262b;
  --surface-hover: #2b2e34;

  --border-subtle: #2b2f35;
  --border-default: #3a3f47;
  --border-strong: #555b63;
  --border-focus: #4aa6d8;

  --text-primary: #e6e8eb;
  --text-secondary: #a4a9b1;
  --text-muted: #737a84;

  --teal: #3b9da0;
  --green: #8be879;
  --red: #ff5e62;
  --amber: #e4b455;
  --blue: #7d9fc7;

  --row-focused-bg: #17394b;

  --green-dim: rgba(139, 232, 121, 0.12);
  --red-dim: rgba(255, 94, 98, 0.12);
  --amber-dim: rgba(228, 180, 85, 0.14);
  --blue-dim: rgba(125, 159, 199, 0.14);
  --teal-dim: rgba(59, 157, 160, 0.14);

  /* legacy aliases — keep old class contracts working during migration */
  --bg-primary: var(--canvas);
  --bg-secondary: var(--surface);
  --bg-tertiary: var(--surface-raised);
  --text-secondary-legacy: var(--text-secondary);
  --green-bright: var(--green);
  --red-bright: var(--red);
  --blue-accent: var(--blue);
  --border-color: var(--border-default);
  --border-color-light: var(--border-strong);
}

/* ===== Design tokens — light ===== */
[data-theme='light'] {
  --canvas: #f6f7f5;
  --surface: #ffffff;
  --surface-raised: #efefec;
  --surface-hover: #e6e8e3;

  --border-subtle: #d9dcd7;
  --border-default: #c4c8c2;
  --border-strong: #9aa09a;
  --border-focus: #2b6ca3;

  --text-primary: #1c1e21;
  --text-secondary: #5a5f66;
  --text-muted: #8a9098;

  --teal: #1f7a7d;
  --green: #1e7d3c;
  --red: #c73a3e;
  --amber: #8a6415;
  --blue: #3d5a80;

  --row-focused-bg: #d6e9e2;
  --brand-wash: #d6e9e2;

  --green-dim: rgba(30, 125, 60, 0.10);
  --red-dim: rgba(199, 58, 62, 0.10);
  --amber-dim: rgba(138, 100, 21, 0.12);
  --blue-dim: rgba(61, 90, 128, 0.12);
  --teal-dim: rgba(31, 122, 125, 0.12);
}

html {
  height: 100%;
}

body {
  height: 100%;
  background: var(--canvas);
  color: var(--text-primary);
  font-size: 13px;
}

/* ===== Components ===== */
@layer components {
  .panel {
    background: var(--surface);
    border: 1px solid var(--border-subtle);
    border-radius: 2px;
  }

  .panel-title {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-secondary);
    font-weight: 600;
  }

  .btn {
    height: 28px;
    padding: 0 10px;
    border: 1px solid var(--border-default);
    border-radius: 3px;
    background: var(--surface-raised);
    color: var(--text-primary);
    font-size: 12px;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    cursor: pointer;
  }
  .btn:hover { background: var(--surface-hover); }
  .btn:focus-visible { outline: 1px solid var(--border-focus); outline-offset: 1px; }
  .btn-primary { border-color: var(--teal); color: var(--teal); }

  .kbd {
    display: inline-flex;
    align-items: center;
    height: 16px;
    padding: 0 4px;
    border: 1px solid var(--border-default);
    border-bottom-width: 2px;
    border-radius: 3px;
    background: var(--surface-raised);
    color: var(--text-muted);
    font-family: var(--font-jbmono), monospace;
    font-size: 10px;
    line-height: 1;
  }

  .input {
    height: 28px;
    padding: 0 8px;
    border: 1px solid var(--border-default);
    border-radius: 3px;
    background: var(--surface-raised);
    color: var(--text-primary);
    font-size: 12px;
  }
  .input:focus { outline: 1px solid var(--border-focus); outline-offset: 0; border-color: var(--border-focus); }

  .missing-cell {
    background: repeating-linear-gradient(-45deg, var(--surface-raised) 0 4px, var(--surface) 4px 8px);
    color: var(--text-muted);
  }
}

/* ===== Legacy classes, re-pointed at tokens (kept for un-migrated files) ===== */
.positive { color: var(--green); }
.negative { color: var(--red); }
.neutral { color: var(--text-muted); }
.positive-bg { background-color: var(--green-dim); }
.negative-bg { background-color: var(--red-dim); }
.neutral-bg { background-color: var(--surface-raised); }
.positive-border { border-color: var(--green-dim); }
.negative-border { border-color: var(--red-dim); }
.neutral-border { border-color: var(--border-default); }
.positive-intense { color: var(--green); font-weight: 600; }
.negative-intense { color: var(--red); font-weight: 600; }
.positive-bg-intense { background-color: var(--green-dim); }
.negative-bg-intense { background-color: var(--red-dim); }
.price-change { transition: color 0.3s ease, background-color 0.3s ease, border-color 0.3s ease; }
.text-positive { color: var(--green); }
.text-negative { color: var(--red); }
.bg-positive { background-color: var(--green-dim); }
.bg-negative { background-color: var(--red-dim); }
.session-timer { font-variant-numeric: tabular-nums; font-feature-settings: 'tnum'; }
.interactive-card { transition: border-color 0.15s ease; }
.interactive-card:hover { border-color: var(--border-default); }

.dashboard-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
  gap: 10px;
}
@media (min-width: 1024px) {
  .dashboard-grid-2 { grid-template-columns: repeat(2, 1fr); }
  .dashboard-grid-3 { grid-template-columns: repeat(3, 1fr); }
  .dashboard-grid-4 { grid-template-columns: repeat(4, 1fr); }
}
@media (min-width: 1400px) {
  .dashboard-grid { grid-template-columns: repeat(3, 1fr); }
}

.data-table { width: 100%; border-collapse: collapse; }
.data-table th {
  padding: 5px 8px;
  text-align: left;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border-default);
  background-color: var(--surface);
}
.data-table td {
  padding: 4px 8px;
  font-size: 12.5px;
  border-bottom: 1px solid var(--border-subtle);
  font-variant-numeric: tabular-nums;
}
.data-table tbody tr:hover { background-color: var(--surface-hover); }
.data-table tbody tr.row-focused {
  background-color: var(--row-focused-bg);
  outline: 1px solid var(--border-focus);
  outline-offset: -1px;
}
.data-table td.num, .data-table th.num { text-align: right; font-family: var(--font-jbmono), monospace; }

.sector-bar-container {
  position: relative;
  height: 1.25rem;
  background-color: var(--surface-raised);
  border-radius: 2px;
  overflow: hidden;
}
.sector-bar {
  height: 100%;
  transition: width 0.5s ease;
  display: flex;
  align-items: center;
  padding: 0 6px;
  font-size: 11px;
  font-weight: 600;
}
.sector-bar-positive { background: var(--green-dim); color: var(--green); border-right: 2px solid var(--green); }
.sector-bar-negative { background: var(--red-dim); color: var(--red); border-left: 2px solid var(--red); margin-left: auto; }

@layer utilities {
  .text-balance { text-wrap: balance; }
}

@keyframes slideInUp {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}
.animate-slide-in { animation: slideInUp 0.2s ease-out; }

@keyframes flashGreen {
  0% { background-color: var(--green-dim); }
  100% { background-color: transparent; }
}
@keyframes flashRed {
  0% { background-color: var(--red-dim); }
  100% { background-color: transparent; }
}
.price-flash-positive { animation: flashGreen 0.3s ease-out; }
.price-flash-negative { animation: flashRed 0.3s ease-out; }

::selection { background: var(--blue-dim); }
```

- [ ] **Step 7: Update `src/app/layout.tsx`** — add JetBrains Mono, ThemeProvider, no-flash script:

```tsx
import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { QueryProvider } from "@/providers/QueryProvider";
import { LayoutShell } from "@/components/LayoutShell";
import { ThemeProvider } from "@/components/theme-provider";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const jbMono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jbmono" });

export const metadata: Metadata = {
  title: "MarketPulse - Real-time Market Analysis",
  description: "Professional market internals analysis with macro economic insights",
};

const noFlashScript = `
(function(){try{var t=localStorage.getItem('mp-theme');if(t!=='light'&&t!=='dark'){t='dark';}
document.documentElement.dataset.theme=t;document.documentElement.style.colorScheme=t;}catch(e){}})();
`;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: noFlashScript }} />
      </head>
      <body className={`${inter.variable} ${jbMono.variable} font-sans`}>
        <ThemeProvider>
          <QueryProvider>
            <LayoutShell>{children}</LayoutShell>
          </QueryProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
```

- [ ] **Step 8: Verify**

Run: `npm run build` then `npm test`
Expected: build succeeds; all tests pass (theme-provider new green, no regressions).

- [ ] **Step 9: Commit** (deferred until user approves)

```bash
git add marketpulse-client/src/app/globals.css marketpulse-client/tailwind.config.ts marketpulse-client/src/app/layout.tsx marketpulse-client/src/components/theme-provider.tsx marketpulse-client/src/components/__tests__/theme-provider.test.tsx
git commit -m "feat(ui): jane street design tokens, theme provider, mono font"
```

---

### Task 2: Chart theming (`lib/chart-theme.ts`, ChartWidget, MultiLineChart)

**Files:**
- Create: `src/lib/chart-theme.ts`
- Modify: `src/components/ChartWidget.tsx`
- Modify: `src/app/research/compare/page.tsx` (MultiLineChart only — rest of page is Task 11)
- Test: `src/lib/__tests__/chart-theme.test.ts`

**Interfaces:**
- Consumes: `useTheme()` from Task 1; CSS vars from Task 1.
- Produces: `getChartTheme(): { layout: { background: { type: number; color: string }; textColor: string; fontFamily: string }; grid: { vertLines: { color: string }; horzLines: { color: string } }; crosshair... ; upColor: string; downColor: string; volumeUp: string; volumeDown: string; seriesPalette: string[] }` and `SERIES_PALETTE` (static fallback).

- [ ] **Step 1: Write the failing test**

```ts
// src/lib/__tests__/chart-theme.test.ts
import { getChartTheme, SERIES_PALETTE } from '@/lib/chart-theme';

describe('chart-theme', () => {
  it('exposes a 6-color series palette led by teal', () => {
    expect(SERIES_PALETTE).toHaveLength(6);
    expect(SERIES_PALETTE[0]).toMatch(/#3b9da0/i);
  });

  it('reads CSS variables from the document root', () => {
    document.documentElement.style.setProperty('--surface', '#123456');
    const t = getChartTheme();
    expect(t.layout.background.color.toLowerCase()).toBe('#123456');
  });

  it('falls back to SERIES_PALETTE colors for up/down candles', () => {
    const t = getChartTheme();
    expect(typeof t.upColor).toBe('string');
    expect(typeof t.downColor).toBe('string');
  });
});
```

- [ ] **Step 2: Run test to verify it fails** — Run: `npm test -- chart-theme`. Expected: FAIL, module not found.

- [ ] **Step 3: Implement `src/lib/chart-theme.ts`**

```ts
import { ColorType } from 'lightweight-charts';

export const SERIES_PALETTE = [
  '#3b9da0', // teal
  '#8be879', // green
  '#ff5e62', // coral
  '#7d9fc7', // blue
  '#e4b455', // amber
  '#b69bd8', // muted violet (rare)
] as const;

function cssVar(name: string, fallback: string): string {
  if (typeof window === 'undefined') return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

export interface ChartTheme {
  layout: {
    background: { type: typeof ColorType.Solid; color: string };
    textColor: string;
    fontFamily: string;
    fontSize: number;
  };
  grid: { vertLines: { color: string }; horzLines: { color: string } };
  rightPriceScale: { borderColor: string };
  timeScale: { borderColor: string };
  upColor: string;
  downColor: string;
  volumeUp: string;
  volumeDown: string;
  seriesPalette: readonly string[];
}

export function getChartTheme(): ChartTheme {
  const green = cssVar('--green', SERIES_PALETTE[1]);
  const red = cssVar('--red', SERIES_PALETTE[2]);
  const greenRgb = green.length === 7 ? hexToRgb(green) : { r: 139, g: 232, b: 121 };
  const redRgb = red.length === 7 ? hexToRgb(red) : { r: 255, g: 94, b: 98 };
  return {
    layout: {
      background: { type: ColorType.Solid, color: cssVar('--surface', '#1d1e22') },
      textColor: cssVar('--text-muted', '#737a84'),
      fontFamily: "var(--font-jbmono), ui-monospace, monospace",
      fontSize: 10,
    },
    grid: {
      vertLines: { color: cssVar('--border-subtle', '#2b2f35') },
      horzLines: { color: cssVar('--border-subtle', '#2b2f35') },
    },
    rightPriceScale: { borderColor: cssVar('--border-default', '#3a3f47') },
    timeScale: { borderColor: cssVar('--border-default', '#3a3f47') },
    upColor: green,
    downColor: red,
    volumeUp: `rgba(${greenRgb.r}, ${greenRgb.g}, ${greenRgb.b}, 0.3)`,
    volumeDown: `rgba(${redRgb.r}, ${redRgb.g}, ${redRgb.b}, 0.3)`,
    seriesPalette: SERIES_PALETTE,
  };
}

function hexToRgb(hex: string): { r: number; g: number; b: number } {
  const n = parseInt(hex.slice(1), 16);
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}
```

- [ ] **Step 4: Run test to verify it passes** — Run: `npm test -- chart-theme`. Expected: PASS.

- [ ] **Step 5: Re-theme `src/components/ChartWidget.tsx`**

Replace every hardcoded color constant with `getChartTheme()` values. Concretely:
1. Add imports: `import { getChartTheme } from '@/lib/chart-theme'; import { useTheme } from '@/components/theme-provider';`
2. In the component body: `const { theme } = useTheme();` and add `theme` to the `createChart` effect dependency array so options rebuild on toggle.
3. `createChart(el, { layout: { background: { type: chartTheme.layout.background.type, color: chartTheme.layout.background.color }, textColor: chartTheme.layout.textColor, fontSize: 10, fontFamily: chartTheme.layout.fontFamily }, grid: chartTheme.grid, rightPriceScale: chartTheme.rightPriceScale, timeScale: chartTheme.timeScale, ... })` where `const chartTheme = getChartTheme();`.
4. Candlestick series: `upColor: chartTheme.upColor, downColor: chartTheme.downColor, wickUpColor: chartTheme.upColor, wickDownColor: chartTheme.downColor, borderVisible: false`.
5. Volume histogram: color per bar via existing up/down logic but using `chartTheme.volumeUp` / `chartTheme.volumeDown`.
6. Loading/empty states: apply Global Constraints class map (`bg-gray-900`→`bg-surface`, etc.).

- [ ] **Step 6: Re-theme `MultiLineChart` in `src/app/research/compare/page.tsx`**

Same pattern: `const { theme } = useTheme();` in `MultiLineChart`, rebuild chart options from `getChartTheme()` on theme change, assign line colors from `chartTheme.seriesPalette` (index by series order instead of the hardcoded `['#fbbf24', '#34d399', '#60a5fa', '#f472b6', '#a78bfa']`), `lineWidth: 1` (was 2), keep rebasing logic untouched.

- [ ] **Step 7: Verify** — Run: `npm run build && npm test`. Expected: success.
- [ ] **Step 8: Commit (deferred)** — `git commit -m "feat(ui): theme-aware lightweight-charts via CSS var bridge"`

---

### Task 3: Shell chrome (LayoutShell, Sidebar, TopBar, icon)

**Files:**
- Modify: `src/components/LayoutShell.tsx`
- Modify: `src/components/Sidebar.tsx`
- Modify: `src/components/TopBar.tsx`
- Create: `src/app/icon.svg` (overwrite)

**Interfaces:**
- Consumes: `useTheme()` (Task 1), tokens/classes from Task 1. TopBar currently exposes brand link, search, live status, clock — keep all functionality, restyle + add theme toggle + palette trigger.
- Produces: TopBar renders `<button data-testid="theme-toggle">` (Sun/Moon icon) calling `toggleTheme()`, and a `<button data-testid="palette-trigger">` labeled `Search <kbd>Ctrl K</kbd>` that dispatches `window.dispatchEvent(new CustomEvent('mp:open-palette'))` (consumed by Task 4's CommandPalette). Sidebar active state: `bg-teal-dim text-teal border-l-2 border-teal`.

- [ ] **Step 1: Restyle `TopBar.tsx`**

Full replacement JSX structure (keep `formatTime`, query-state logic, search dropdown behavior identical):

```tsx
<header className="h-11 bg-surface border-b border-line-subtle px-3 flex items-center gap-3 shrink-0">
  <button onClick={onMenuToggle} className="lg:hidden p-1 text-ink-secondary hover:text-ink" aria-label="Toggle menu">
    <Menu size={16} />
  </button>

  <Link href="/" className="font-mono text-[13px] font-bold tracking-[0.12em] text-ink flex items-center gap-2">
    <span className="w-2 h-2 bg-teal inline-block" aria-hidden />
    MARKETPULSE
  </Link>

  <div className="flex-1 flex justify-center">
    <button
      onClick={() => window.dispatchEvent(new CustomEvent('mp:open-palette'))}
      data-testid="palette-trigger"
      className="hidden md:flex w-[280px] h-7 pl-2 pr-1.5 bg-surface-raised border border-line rounded-[3px] text-[12px] text-ink-muted text-left hover:border-line-strong items-center justify-between cursor-pointer"
    >
      <span className="flex items-center gap-1.5"><Search size={12} /> Search symbols, pages…</span>
      <span className="kbd">Ctrl K</span>
    </button>
  </div>

  {/* live status — StateDot pattern */}
  <div className="flex items-center gap-1.5 text-[11px] font-mono">
    {isConnected ? (
      <><span className="w-1.5 h-1.5 rounded-full bg-pos" /><span className="text-pos">LIVE</span></>
    ) : (
      <><span className="w-1.5 h-1.5 rounded-full bg-neg" /><span className="text-neg">OFFLINE</span></>
    )}
  </div>
  {lastUpdate && (
    <span className="hidden sm:block text-[11px] font-mono text-ink-muted">
      UPD {formatTime(lastUpdate)}
    </span>
  )}
  <button
    onClick={toggleTheme}
    data-testid="theme-toggle"
    aria-label="Toggle theme"
    className="p-1 text-ink-secondary hover:text-ink border border-line rounded-[3px] h-7 w-7 flex items-center justify-center"
  >
    {theme === 'dark' ? <Sun size={13} /> : <Moon size={13} />}
  </button>
  <div className="flex items-center gap-1.5 text-[11px] font-mono text-ink-secondary">
    <Clock size={12} />
    <span>{now ? formatTime(now) : '--:--:--'}</span>
  </div>
</header>
```

Add `const { theme, toggleTheme } = useTheme();` and imports `Sun, Moon` from lucide, `useTheme` from provider. Delete the old inline search dropdown block (its symbol-jump job moves to CommandPalette in Task 4; keep the `searchOpen` state removed cleanly).

- [ ] **Step 2: Restyle `Sidebar.tsx`**

Apply: container `w-[180px] bg-surface border-r border-line-subtle` (collapsed `w-12`); nav item base `h-7 px-2 text-[12px] text-ink-secondary hover:bg-surface-hover hover:text-ink flex items-center gap-2 border-l-2 border-transparent`; active `bg-teal-dim text-teal border-l-2 border-teal`; icon size 14; section label `panel-title`; disabled items `text-ink-muted cursor-not-allowed` with `SOON` tag instead of `Soon` badge styling. Keep collapse + mobile drawer logic unchanged (`LayoutShell` controls it).

- [ ] **Step 3: Restyle `LayoutShell.tsx`**

Apply the class map: main column `bg-canvas`, footer `h-6 text-[10px] font-mono text-ink-muted border-t border-line-subtle flex items-center px-3 gap-2` with content `DATA YAHOO FINANCE · MARKETPULSE v0.3.0` (uppercase, mono). Mobile drawer overlay `bg-canvas/80` no blur. Keep all responsive logic.

- [ ] **Step 4: New `src/app/icon.svg`** — concentric circles, teal on charcoal:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <rect width="32" height="32" rx="4" fill="#17181b"/>
  <circle cx="16" cy="16" r="10" fill="none" stroke="#3b9da0" stroke-width="1.5" opacity="0.4"/>
  <circle cx="16" cy="16" r="6" fill="none" stroke="#3b9da0" stroke-width="1.5" opacity="0.7"/>
  <circle cx="16" cy="16" r="2" fill="#8be879"/>
</svg>
```

- [ ] **Step 5: Verify** — Run: `npm run build`. Then Playwright: load `/`, screenshot dark; click `[data-testid="theme-toggle"]`, screenshot light. Expected: flat chrome, no gradients, palette button visible, toggle flips `data-theme`.
- [ ] **Step 6: Commit (deferred)** — `git commit -m "feat(ui): dense flat shell chrome, theme toggle, palette trigger, new mark"`

---

### Task 4: CommandPalette, KbdHelp, useRowNav

**Files:**
- Create: `src/components/CommandPalette.tsx`
- Create: `src/components/KbdHelp.tsx`
- Create: `src/hooks/useRowNav.ts`
- Create: `src/components/StateDot.tsx`
- Modify: `src/components/LayoutShell.tsx` (mount `<CommandPalette />` + `<KbdHelp />` once)
- Test: `src/hooks/__tests__/useRowNav.test.ts`, `src/components/__tests__/CommandPalette.test.tsx`

**Interfaces:**
- Consumes: `useTheme` (for a "Toggle theme" command), `useRouter`.
- Produces:
  - `useRowNav(count: number, opts?: { onEnter?: (index: number) => void; enabled?: boolean }): { focusedIndex: number; setFocusedIndex: (i: number) => void; handleKeyDown: (e: React.KeyboardEvent) => void }` — j/k/↑/↓ movement clamped, Enter fires `onEnter(focusedIndex)`, Home/End jump; `enabled: false` makes it a no-op.
  - `CommandPalette` — listens `Ctrl+K` / `Cmd+K` / `/` (only when target is not input/textarea/contenteditable) and `mp:open-palette` event; commands: navigate to each route (Dashboard `/`, Trending `/trending`, Charts `/chart/SPY`, Symbol `/symbol/SPY`, Research BTC `/research/BTC`, Compare `/research/compare`, Reports `/research/reports`), `Go to <SYM>` when query looks like a symbol (`/^[A-Z0-9.\-]{1,10}$/i` after trim+uppercase → `/chart/<SYM>`), and `Toggle light/dark theme`. Arrow keys move selection, Enter runs, Esc closes.
  - `StateDot({ state: 'live'|'offline'|'stale'|'error'; label?: string; age?: string })` — dot + uppercase label + optional age, mono 11px.
  - `KbdHelp` — `?` key opens overlay listing shortcuts; Esc closes. Pure static list.

- [ ] **Step 1: Write failing tests**

```ts
// src/hooks/__tests__/useRowNav.test.ts
import { renderHook } from '@testing-library/react';
import { useRowNav } from '@/hooks/useRowNav';

function key(k: string): React.KeyboardEvent {
  return { key: k, preventDefault: () => {} } as unknown as React.KeyboardEvent;
}

describe('useRowNav', () => {
  it('moves down with j and up with k, clamped', () => {
    const { result } = renderHook(() => useRowNav(3));
    result.current.handleKeyDown(key('j'));
    result.current.handleKeyDown(key('j'));
    result.current.handleKeyDown(key('j')); // clamp at 2
    expect(result.current.focusedIndex).toBe(2);
    result.current.handleKeyDown(key('k'));
    expect(result.current.focusedIndex).toBe(1);
  });

  it('fires onEnter with focused index', () => {
    const onEnter = jest.fn();
    const { result } = renderHook(() => useRowNav(3, { onEnter }));
    result.current.handleKeyDown(key('j'));
    result.current.handleKeyDown(key('Enter'));
    expect(onEnter).toHaveBeenCalledWith(1);
  });

  it('is a no-op when disabled', () => {
    const { result } = renderHook(() => useRowNav(3, { enabled: false }));
    result.current.handleKeyDown(key('j'));
    expect(result.current.focusedIndex).toBe(0);
  });
});
```

```tsx
// src/components/__tests__/CommandPalette.test.tsx
import { render, screen, fireEvent } from '@testing-library/react';
import { CommandPalette } from '@/components/CommandPalette';

jest.mock('next/navigation', () => ({ useRouter: () => ({ push: jest.fn() }) }));

describe('CommandPalette', () => {
  it('opens on mp:open-palette event and shows commands', () => {
    render(<CommandPalette />);
    window.dispatchEvent(new CustomEvent('mp:open-palette'));
    expect(screen.getByPlaceholderText(/search/i)).toBeInTheDocument();
    expect(screen.getByText(/dashboard/i)).toBeInTheDocument();
  });

  it('filters to symbol command for ticker-like input', () => {
    render(<CommandPalette />);
    window.dispatchEvent(new CustomEvent('mp:open-palette'));
    fireEvent.change(screen.getByPlaceholderText(/search/i), { target: { value: 'aapl' } });
    expect(screen.getByText(/go to aapl/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail** — Run: `npm test -- useRowNav CommandPalette`. Expected: FAIL, modules missing.

- [ ] **Step 3: Implement `src/hooks/useRowNav.ts`**

```ts
'use client';

import { useCallback, useState } from 'react';

export interface RowNavOptions {
  onEnter?: (index: number) => void;
  enabled?: boolean;
}

export function useRowNav(count: number, opts: RowNavOptions = {}) {
  const { onEnter, enabled = true } = opts;
  const [focusedIndex, setFocusedIndex] = useState(0);

  const move = useCallback(
    (delta: number) => {
      setFocusedIndex((prev) => Math.min(count - 1, Math.max(0, prev + delta)));
    },
    [count]
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!enabled) return;
      switch (e.key) {
        case 'j':
        case 'ArrowDown':
          e.preventDefault();
          move(1);
          break;
        case 'k':
        case 'ArrowUp':
          e.preventDefault();
          move(-1);
          break;
        case 'Home':
          e.preventDefault();
          setFocusedIndex(0);
          break;
        case 'End':
          e.preventDefault();
          setFocusedIndex(count - 1);
          break;
        case 'Enter':
          e.preventDefault();
          onEnter?.(focusedIndex);
          break;
        default:
          break;
      }
    },
    [enabled, move, count, onEnter, focusedIndex]
  );

  return { focusedIndex, setFocusedIndex, handleKeyDown };
}
```

- [ ] **Step 4: Implement `src/components/CommandPalette.tsx`**

```tsx
'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTheme } from '@/components/theme-provider';

interface Command {
  id: string;
  label: string;
  hint?: string;
  run: () => void;
}

const SYMBOL_RE = /^[A-Z0-9.\-]{1,10}$/;

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(0);
  const router = useRouter();
  const { toggleTheme } = useTheme();
  const inputRef = useRef<HTMLInputElement>(null);

  const close = useCallback(() => {
    setOpen(false);
    setQuery('');
    setSelected(0);
  }, []);

  useEffect(() => {
    const openPalette = () => setOpen(true);
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      const typing =
        target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen((o) => !o);
      } else if (e.key === '/' && !typing) {
        e.preventDefault();
        setOpen(true);
      } else if (e.key === 'Escape') {
        close();
      }
    };
    window.addEventListener('mp:open-palette', openPalette);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('mp:open-palette', openPalette);
      window.removeEventListener('keydown', onKey);
    };
  }, [close]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  const commands = useMemo<Command[]>(() => {
    const nav: Command[] = [
      { id: 'dashboard', label: 'Dashboard', hint: '/', run: () => router.push('/') },
      { id: 'trending', label: 'Trending', hint: '/trending', run: () => router.push('/trending') },
      { id: 'charts', label: 'Charts', hint: '/chart/SPY', run: () => router.push('/chart/SPY') },
      { id: 'symbol', label: 'Symbol', hint: '/symbol/SPY', run: () => router.push('/symbol/SPY') },
      { id: 'research', label: 'Research', hint: '/research/BTC', run: () => router.push('/research/BTC') },
      { id: 'compare', label: 'Compare assets', hint: '/research/compare', run: () => router.push('/research/compare') },
      { id: 'reports', label: 'Reports', hint: '/research/reports', run: () => router.push('/research/reports') },
      { id: 'theme', label: 'Toggle light/dark theme', run: toggleTheme },
    ];
    const q = query.trim().toUpperCase();
    if (q && SYMBOL_RE.test(q)) {
      nav.unshift({ id: `sym-${q}`, label: `Go to ${q}`, hint: `/chart/${q}`, run: () => router.push(`/chart/${q}`) });
    }
    return nav;
  }, [query, router, toggleTheme]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    return commands.filter((c) => c.label.toLowerCase().includes(q) || c.id.includes(q));
  }, [commands, query]);

  const runSelected = useCallback(
    (cmd: Command | undefined) => {
      if (!cmd) return;
      close();
      cmd.run();
    },
    [close]
  );

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-start justify-center pt-[15vh]" role="dialog" aria-label="Command palette">
      <div className="absolute inset-0 bg-canvas/70" onClick={close} />
      <div className="relative w-[480px] max-w-[92vw] panel shadow-none">
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setSelected(0);
          }}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') { e.preventDefault(); setSelected((s) => Math.min(filtered.length - 1, s + 1)); }
            if (e.key === 'ArrowUp') { e.preventDefault(); setSelected((s) => Math.max(0, s - 1)); }
            if (e.key === 'Enter') { e.preventDefault(); runSelected(filtered[selected]); }
          }}
          placeholder="Search symbols, pages, actions…"
          className="w-full h-9 bg-transparent border-0 border-b border-line-subtle px-3 text-[13px] font-mono text-ink placeholder:text-ink-muted focus:outline-none"
          aria-label="Search symbols pages actions"
        />
        <ul className="max-h-[320px] overflow-y-auto py-1">
          {filtered.map((c, i) => (
            <li
              key={c.id}
              onMouseEnter={() => setSelected(i)}
              onClick={() => runSelected(c)}
              className={`h-7 px-3 flex items-center justify-between cursor-pointer text-[12.5px] ${
                i === selected ? 'bg-sel-dim text-ink' : 'text-ink-secondary'
              }`}
            >
              <span>{c.label}</span>
              {c.hint && <span className="font-mono text-[10.5px] text-ink-muted">{c.hint}</span>}
            </li>
          ))}
          {filtered.length === 0 && (
            <li className="h-7 px-3 flex items-center text-[12px] text-ink-muted">No matches</li>
          )}
        </ul>
        <div className="border-t border-line-subtle px-3 h-6 flex items-center gap-2 text-[10px] font-mono text-ink-muted">
          <span className="kbd">↑↓</span> navigate <span className="kbd">↵</span> run <span className="kbd">esc</span> close
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Implement `src/components/KbdHelp.tsx`**

Overlay: `?` (shift+/) opens when not typing; Esc closes. Content — a `panel` at screen center with title `KEYBOARD SHORTCUTS` and a two-column table of: `Ctrl K` / `/` command palette, `?` this help, `j`/`k` or `↑`/`↓` row focus, `Enter` open focused row, `Esc` clear focus / close, `1-5` switch dashboard tabs (implemented in Task 5), theme toggle via palette. Each row `<kbd className="kbd">…</kbd> + label`. Same open/close effect pattern as CommandPalette (no input, focus trap not required).

- [ ] **Step 6: Implement `src/components/StateDot.tsx`**

```tsx
'use client';

export type DotState = 'live' | 'offline' | 'stale' | 'error';

const STATE_STYLE: Record<DotState, { dot: string; text: string; fallbackLabel: string }> = {
  live: { dot: 'bg-pos', text: 'text-pos', fallbackLabel: 'LIVE' },
  offline: { dot: 'bg-neg', text: 'text-neg', fallbackLabel: 'OFFLINE' },
  stale: { dot: 'bg-warn', text: 'text-warn', fallbackLabel: 'STALE' },
  error: { dot: 'bg-neg', text: 'text-neg', fallbackLabel: 'ERROR' },
};

export function StateDot({ state, label, age }: { state: DotState; label?: string; age?: string }) {
  const s = STATE_STYLE[state];
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] font-mono">
      <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} aria-hidden />
      <span className={s.text}>{label ?? s.fallbackLabel}</span>
      {age && <span className="text-ink-muted">{age}</span>}
    </span>
  );
}
```

- [ ] **Step 7: Mount in `LayoutShell.tsx`** — inside the outermost fragment (inside ThemeProvider tree, alongside Sidebar/main): add `<CommandPalette />` and `<KbdHelp />` after the main column.

- [ ] **Step 8: Run tests** — Run: `npm test -- useRowNav CommandPalette`. Expected: PASS.
- [ ] **Step 9: Verify** — Run: `npm run build`; Playwright: Ctrl+K opens palette, typing `aapl` shows `Go to AAPL`, Enter navigates to `/chart/AAPL`; `?` opens help.
- [ ] **Step 10: Commit (deferred)** — `git commit -m "feat(ui): command palette, keyboard help, row-nav hook, state dot"`

---

### Task 5: Dashboard decomposition + restyle (`ThreeColumnDashboard` → `dashboard/`)

**Files:**
- Create: `src/components/dashboard/CommandCenter.tsx`
- Create: `src/components/dashboard/CenterTabs.tsx`
- Create: `src/components/dashboard/AiChatPanel.tsx`
- Create: `src/components/dashboard/StatTile.tsx`
- Create: `src/components/dashboard/MiniTable.tsx`
- Modify: `src/components/ThreeColumnDashboard.tsx` (becomes thin data-fetching composition)

**Interfaces:**
- Consumes: existing data shapes from `src/types/market.ts` (`DashboardData` etc.), existing tab components (untouched here — Task 6 restyles them), `llm-chat.tsx`, `.data-table`, `.panel`, tokens.
- Produces: `ThreeColumnDashboard` keeps its default export + polling behavior + props signature (none). Internal split:
  - `StatTile({ label, value, delta?, mono? })` — dense tile: 11px uppercase label, 15–22px mono value, delta colored via sign.
  - `MiniTable({ title, columns, rows })` — thin `data-table` wrapper with `panel-title` header row (columns: `{ key: string; label: string; num?: boolean }[]`, rows: `Record<string, React.ReactNode>`).
  - `CommandCenter({ data })` — NQ hero block (price mono 22–28px + change + sparkline), breadth tiles, regime indicator, position calculator, session stats. Props: the same sub-objects `ThreeColumnDashboard` currently computes.
  - `CenterTabs` — tab strip (uppercase 11px tab labels, active = `text-teal border-b-2 border-teal`), `1-5` number-key tab switching, renders existing tab components per active tab, Overview tab content extracted here.
  - `AiChatPanel` — `panel` wrapper around `LlmChat` with `panel-title` header `AI ANALYST`.

**Steps:**

- [ ] **Step 1: Decompose.** Move JSX out of `ThreeColumnDashboard.tsx` into the five new files, passing data via props. Rules: `ThreeColumnDashboard` keeps `apiFetch` calls, polling `useEffect`, and all `useState` that spans columns; each new file gets only the props it needs; no logic changes, only moves. File must end < 120 lines.
- [ ] **Step 2: Restyle during the move** using the Global Constraints map plus: hero NQ price `font-mono text-2xl tabular-nums`; every numeric cell `font-mono tabular-nums text-[12.5px]`; sparkline container `h-8`; regime chip = `border rounded-[2px] px-1.5 h-5 text-[11px] font-mono` colored pos/neg/warn by regime value; position calculator inputs `input` class; tab strip per interface above.
- [ ] **Step 3: Wire number keys 1-5** in `CenterTabs` via a `useEffect` keydown listener (ignored while typing in inputs) setting active tab index.
- [ ] **Step 4: Verify** — Run: `npm run build`. Playwright: `/` renders all three columns dense and flat in dark and light; polling still updates (wait 60s or invalidate via devtools is enough to see no crash — data presence check is sufficient); tabs switch via click and keys `1-5`.
- [ ] **Step 5: Commit (deferred)** — `git commit -m "refactor(ui): decompose ThreeColumnDashboard into dense dashboard modules"`

---

### Task 6: Dashboard tab components restyle

**Files (Modify only, class-map application + density + mono numerics):**
- `src/components/MacroDashboard.tsx`
- `src/components/RiskManagerTab.tsx`
- `src/components/BacktestTab.tsx`
- `src/components/OptionsFlowTab.tsx`
- `src/components/StrategyTab.tsx`
- `src/components/YieldCurvePanel.tsx` — note: uses slate/sky/amber palette; map `slate-900/50`→`bg-surface-raised`, `sky-*`→`text-sel`/`text-teal`, `amber-*`→`text-warn`.

**Steps:**

- [ ] **Step 1: Restyle each file** with the Global Constraints map. Specifics per file:
  - *MacroDashboard*: regime card → `panel` + regime chip pattern from Task 5; 12-mo timeline grid cells `h-6` mono values with `bg-pos-dim`/`bg-neg-dim` fills; narrative in `text-[12.5px] text-ink-secondary`.
  - *RiskManagerTab*: P&L bars `h-3` with flat `bg-pos`/`bg-neg` fills (no gradients); drawdown meter `border border-line rounded-[2px]` with `bg-neg` fill; stat grid → `StatTile`-style density.
  - *BacktestTab*: form controls → `input`/`btn` classes; hero stats row 4 tiles mono; trades table → `data-table` with `num` right-aligned columns.
  - *OptionsFlowTab*: macro context strip = 3 inline mono stats; unusual-activity rows `bg-warn-dim` flag; chain tables `data-table`.
  - *StrategyTab*: signal cards → flat `panel` rows (not floating cards); Execute button `btn btn-primary`; performance strip mono.
  - All tables get sticky headers if scrolled (`sticky top-0 bg-surface` on `th`).
- [ ] **Step 2: Verify** — Run: `npm run build`; Playwright `/` → each tab (Overview/Backtests/Risk/Options/Strategy/Macro) screenshot dark+light; grep residue (Task 12 command) clean for these files.
- [ ] **Step 3: Commit (deferred)** — `git commit -m "style(ui): quant-density restyle for dashboard tabs"`

---

### Task 7: Shared primitives restyle

**Files (Modify):**
- `src/components/ui/Sparkline.tsx` — colors from `getComputedStyle` CSS vars (`--green`/`--red`) with static fallbacks `#8be879`/`#ff5e62`; stroke width 1; last-point dot r=1.5.
- `src/components/ui/LoadingSpinner.tsx` — spinner border `border-line` + `border-t-teal`; `SkeletonCard` → `panel` flat shimmer `bg-surface-raised animate-pulse`.
- `src/components/PriceCell.tsx` — value `font-mono tabular-nums`; chip `h-4 px-1 text-[10.5px] font-mono` `bg-pos-dim text-pos` / `bg-neg-dim text-neg`; flat, no rounded-full.
- `src/components/FiftyTwoWeekBar.tsx` — track `bg-surface-raised h-1 rounded-none`; fill tiered `bg-neg` / `bg-sel` / `bg-pos`; dot `w-1.5 h-1.5 bg-ink`.
- `src/components/AssetPicker.tsx` — trigger `btn`; menu `panel` with `p-0`, items `h-7 px-2 hover:bg-surface-hover`; selected `text-teal`; accent emerald→teal.
- `src/components/AgentTracePanel.tsx` — status pills → `StateDot`-pattern text `text-[10.5px] font-mono uppercase`; borders flat.
- `src/components/PipelineProgress.tsx` — phase bar `h-1 bg-surface-raised` fill `bg-teal`; labels 10.5px mono uppercase.

- [ ] **Step 1: Apply the per-file changes above** (each is a small, self-contained edit; no interface changes — props signatures stay identical).
- [ ] **Step 2: Verify** — Run: `npm run build && npm test`. Expected: pass.
- [ ] **Step 3: Commit (deferred)** — `git commit -m "style(ui): token-based shared primitives"`

---

### Task 8: Trending page (dense table + row keyboard nav)

**Files:**
- Modify: `src/app/trending/page.tsx`
- Modify: `src/app/page.tsx` (outer wrapper class swap only: `bg-gray-950` → `bg-canvas`)

**Steps:**

- [ ] **Step 1: Restyle** — tabs (gainers/losers/most_active) → flat uppercase strip (active `text-teal border-b-2 border-teal`); table → `.data-table` with `.num` columns for price/change/pct/volume/52W; symbol cell `font-mono text-ink`; header `sticky top-0`.
- [ ] **Step 2: Wire `useRowNav`** — `const { focusedIndex, handleKeyDown } = useRowNav(rows.length, { onEnter: (i) => router.push(`/chart/${rows[i].symbol}`) })`; table wrapper `tabIndex={0} onKeyDown={handleKeyDown}` `focus:outline-1 focus:outline-line-focus`; focused row gets class `row-focused`; scroll focused row into view via `ref` + `scrollIntoView({ block: 'nearest' })` effect on `focusedIndex`.
- [ ] **Step 3: Verify** — Run: `npm run build`; Playwright `/trending`: j/k moves focus ring, Enter opens chart page, `/` opens palette while focus not in input.
- [ ] **Step 4: Commit (deferred)** — `git commit -m "feat(ui): dense trending table with keyboard row nav"`

---

### Task 9: Chart + Symbol detail pages

**Files (Modify):**
- `src/app/chart/[symbol]/page.tsx` — timeframe buttons → `btn` group with `1-5` key hints (kbd chips), active `btn-primary`; side panel → `panel` + `StatTile` density; key stats mono; technical summary labels uppercase 11px.
- `src/app/symbol/[symbol]/page.tsx` — 8-tile stat grid → 4×2 dense `StatTile` grid; trend analysis bars flat `bg-pos`/`bg-neg`; support/resistance values mono; signals → regime-chip pattern.

**Steps:**

- [ ] **Step 1: Apply class map + density rules to both files** (ChartWidget itself already themed in Task 2).
- [ ] **Step 2: Verify** — Run: `npm run build`; Playwright `/chart/SPY` + `/symbol/SPY` dark+light screenshots; candles visible both themes.
- [ ] **Step 3: Commit (deferred)** — `git commit -m "style(ui): chart and symbol pages at quant density"`

---

### Task 10: Research chat + LLM chat visual pass

**Files (Modify):**
- `src/app/research/[asset]/page.tsx` — page header flat; example-query chips `btn`-like `h-6 text-[11px]`; message bubbles → flat rows: user `bg-surface-raised border-l-2 border-teal`, assistant `bg-surface` `border-l-2 border-line-subtle`, both `rounded-[2px] p-2 text-[12.5px]`; code blocks `font-mono text-[11.5px] bg-canvas border border-line-subtle`.
- `src/components/llm-chat.tsx` — **visual only**: outer panel `panel`; header `panel-title AI ANALYST` + model selector as `btn`; input row `input` + `btn btn-primary` send; streaming cursor `▌ text-teal animate-pulse`; bubble styles same as research chat; keep ALL WebSocket/streaming/markdown/model logic byte-identical.

**Steps:**

- [ ] **Step 1: Apply visual changes** to both files without touching streaming code paths (identify all `className` strings only).
- [ ] **Step 2: Verify** — Run: `npm run build`; Playwright `/research/BTC` loads, example chips render, input styled; `/` AI panel styled. Streaming behavior unchanged (code untouched — diff review confirms only className/markup changes).
- [ ] **Step 3: Commit (deferred)** — `git commit -m "style(ui): research and AI chat surfaces"`

---

### Task 11: Compare + Reports pages

**Files (Modify):**
- `src/app/research/compare/page.tsx` — form controls → `input`/`btn`; asset checkboxes → flat `accent-[var(--teal)]` squares with mono labels; chart container `panel` with `panel-title` `RELATIVE PERFORMANCE (REBASED 100)`; legend chips mono 11px. (MultiLineChart themed in Task 2.)
- `src/app/research/reports/page.tsx` — list → dense `data-table`-style rows; kind filter → flat uppercase strip.
- `src/app/research/reports/[id]/page.tsx` — metrics grid → `StatTile` density mono; params JSON → `font-mono text-[11.5px] bg-canvas border border-line-subtle p-2 rounded-[2px]`; equity/drawdown `<img>` wrapped in `panel` with titles.

**Steps:**

- [ ] **Step 1: Apply restyles.**
- [ ] **Step 2: Verify** — Run: `npm run build`; Playwright screenshots of all three routes dark+light.
- [ ] **Step 3: Commit (deferred)** — `git commit -m "style(ui): compare and reports pages"`

---

### Task 12: Final verification sweep

**Steps:**

- [ ] **Step 1: Full gates**

Run in `marketpulse-client/`:
```bash
npm run build
npm test
npm run lint
```
Expected: all pass, zero TS errors.

- [ ] **Step 2: Old-palette residue grep**

```bash
grep -rnE "emerald-|from-blue-500|to-purple-500|rounded-(xl|2xl)|shadow-(md|lg|xl|2xl)|bg-gray-9[0-9]{2}|bg-black\b" src/
```
Expected: only matches inside `globals.css` legacy-alias comments (none of these utility names should appear in `src/**/*.{tsx,ts}`).

- [ ] **Step 3: Visual QA (Playwright, both themes)**

Routes: `/`, `/trending`, `/chart/SPY`, `/symbol/SPY`, `/research/BTC`, `/research/compare`, `/research/reports`. For each: screenshot dark, toggle via `[data-testid="theme-toggle"]`, screenshot light. Checklist per route: no gradients, no shadows, 1px borders, mono numerics, panel titles uppercase, charts legible, no overflow/clipped columns, focused-row visible on trending.

- [ ] **Step 4: Functional smoke**

Dashboard poll fires (network tab shows 60s cadence), candles render `/chart/SPY`, chat streams on `/research/BTC` (if backend up; otherwise verify no client errors), Ctrl+K palette + j/k + `?` all functional.

- [ ] **Step 5: Report + commit batch (deferred until user approves)**

```bash
git add -A
git commit -m "feat(ui): jane street quant workstation redesign — all routes, dual theme"
```
