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
