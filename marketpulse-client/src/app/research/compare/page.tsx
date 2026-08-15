'use client';

/**
 * Cross-Asset Comparison view (W5 T24).
 *
 * STRICTLY SCOPED per Metis SC2: ONLY normalized total return (rebased to 100)
 * over a user-selected date range. No correlation matrix, no risk-adjusted
 * metrics, no per-asset metric tables, no portfolio optimization.
 *
 * Backed by `POST /api/research/compare` (T20) multi-asset path:
 *   request  = { assets: string[], strategy: string, start: string, end: string }
 *   response = {
 *     strategy, start, end,
 *     assets: {
 *       [asset]: {
 *         normalized_total_return: number[],  // starts at 1.0; we * 100 -> base 100
 *         index: string[],                    // parallel "YYYY-MM-DD 00:00:00" strings
 *         total_return_pct: number,
 *       } | { error: string }                 // per-asset failure (still success:true overall)
 *     }
 *   }
 */

import { useState, useRef, useEffect, FormEvent } from 'react';
import {
  createChart,
  CrosshairMode,
  LineSeries,
} from 'lightweight-charts';
import type { IChartApi, Time } from 'lightweight-charts';
import {
  GitCompare,
  Loader2,
  AlertTriangle,
  Activity,
  Info,
} from 'lucide-react';
import { apiFetch } from '@/lib/api';
import { getChartTheme, SERIES_PALETTE } from '@/lib/chart-theme';
import { useTheme } from '@/components/theme-provider';

// ----------------------------- Constants -----------------------------

// Exact casing required by POST /api/research/compare (AssetRegistry keys).
const ASSET_OPTIONS: Array<{ key: string; label: string }> = [
  { key: 'BTC', label: 'Bitcoin' },
  { key: 'GOLD', label: 'Gold (LBMA AM fix)' },
  { key: 'OIL', label: 'WTI Crude Oil (spot)' },
  { key: 'EQUITIES', label: 'US Broad Equities (S&P 500)' },
  { key: 'HOUSING', label: 'US Housing (Case-Shiller)' },
];

// Valid strategy names from src/research/strategies/__init__.py `_REGISTRY`.
const STRATEGY_OPTIONS = [
  'BuyAndHold',
  'DCAFixedAmount',
  'DCAValueAveraging',
  'MomentumTrend',
  'MeanReversionBollinger',
  'MeanReversionRSI',
  'LadderLimit',
  'RecurringFundingDCA',
  'HalvingCycleAccumulation',
  'CompositeAccumulation',
  'RealRateCycleAccumulation',
  'EarningsCycleAccumulation',
  'OPECCycleAccumulation',
  'MortgageCycleAccumulation',
];

const MIN_ASSETS = 2;
const MAX_ASSETS = 5;
const DEFAULT_START = '2010-01-01';

function todayISO(): string {
  return new Date().toISOString().substring(0, 10);
}

// ----------------------------- Types -----------------------------

interface AssetSeries {
  normalized_total_return: number[];
  index: string[];
  total_return_pct: number;
}

interface AssetError {
  error: string;
}

type AssetResult = AssetSeries | AssetError;

function isAssetError(r: AssetResult): r is AssetError {
  return typeof (r as AssetError).error === 'string';
}

interface CompareResponse {
  strategy: string;
  start: string;
  end: string;
  assets: Record<string, AssetResult>;
}

// ----------------------------- Chart -----------------------------

/**
 * Multi-asset line chart rendering one LineSeries per asset, all rebased to 100
 * at their first observation. Uses lightweight-charts (same lib as ChartWidget).
 *
 * Each series carries its own trading calendar (BTC=247d, GOLD/EQUITIES=252d,
 * HOUSING=monthly) so timestamps are NOT aligned across assets; lightweight-charts
 * handles the union time scale naturally.
 */
function MultiLineChart({ assets }: { assets: Record<string, AssetResult> }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const { theme } = useTheme();

  const validEntries = (
    Object.entries(assets).filter(([, r]) => !isAssetError(r)) as Array<[string, AssetSeries]>
  );

  useEffect(() => {
    const container = containerRef.current;
    if (!container || validEntries.length === 0) return;

    // Tear down any prior chart instance before rebuilding.
    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    let resizeObserver: ResizeObserver | null = null;
    const chartTheme = getChartTheme();

    try {
      const chart = createChart(container, {
        width: container.clientWidth,
        height: 520,
        layout: {
          background: {
            type: chartTheme.layout.background.type,
            color: chartTheme.layout.background.color,
          },
          textColor: chartTheme.layout.textColor,
          fontSize: chartTheme.layout.fontSize,
          fontFamily: chartTheme.layout.fontFamily,
        },
        grid: chartTheme.grid,
        crosshair: { mode: CrosshairMode.Normal },
        rightPriceScale: chartTheme.rightPriceScale,
        timeScale: {
          ...chartTheme.timeScale,
          timeVisible: false,
          secondsVisible: false,
        },
      });

      validEntries.forEach(([assetKey, series], i) => {
        const color = chartTheme.seriesPalette[i % chartTheme.seriesPalette.length];
        const lineSeries = chart.addSeries(LineSeries, {
          color,
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: true,
          crosshairMarkerVisible: true,
        });
        // Rebase to 100. API normalizes first value to 1.0; we enforce exactly
        // 100 at the start (defensive against any floating-point drift).
        const base = series.normalized_total_return[0] || 1.0;
        const data = series.index.map((ts, j) => ({
          time: ts as Time,
          value: (series.normalized_total_return[j] / base) * 100,
        }));
        lineSeries.setData(data);
      });

      chart.timeScale().fitContent();

      resizeObserver = new ResizeObserver((entries) => {
        if (entries.length > 0) {
          const { width } = entries[0].contentRect;
          chart.applyOptions({ width });
        }
      });
      resizeObserver.observe(container);

      chartRef.current = chart;
    } catch {
      chartRef.current = null;
    }

    return () => {
      resizeObserver?.disconnect();
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
    };
    // Rebuild only when the set of plottable assets changes. `assets` is a new
    // object reference per API response, so identity comparison suffices; we
    // additionally key off the count + a tight signature so the effect re-runs
    // even if React reuses the object (it doesn't today, but defensively).
    // `theme` is included so options rebuild on theme toggle.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    assets,
    validEntries.length,
    validEntries.map(([k, v]) => `${k}:${v.index.length}`).join('|'),
    theme,
  ]);

  if (validEntries.length === 0) {
    return (
      <div className="flex items-center justify-center h-[520px] bg-canvas border border-line-subtle rounded-[2px]">
        <p className="text-[12.5px] text-ink-muted">No plottable series in response.</p>
      </div>
    );
  }

  return (
    <div>
      <div ref={containerRef} className="w-full" />
      <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2">
        {validEntries.map(([assetKey, series], i) => {
          const color = SERIES_PALETTE[i % SERIES_PALETTE.length];
          const pct = series.total_return_pct;
          const positive = pct >= 0;
          return (
            <div key={assetKey} className="flex items-center gap-2">
              <span
                className="inline-block w-3 h-3 rounded-sm"
                style={{ backgroundColor: color }}
                aria-hidden
              />
              <span className="text-sm font-medium text-ink">{assetKey}</span>
              <span
                className={`text-sm font-semibold ${
                  positive ? 'text-emerald-400' : 'text-red-400'
                }`}
              >
                {positive ? '+' : ''}
                {pct.toFixed(2)}%
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ----------------------------- Page -----------------------------

export default function ComparePage() {
  const [selected, setSelected] = useState<string[]>(['GOLD', 'EQUITIES', 'HOUSING']);
  const [strategy, setStrategy] = useState<string>('BuyAndHold');
  const [start, setStart] = useState<string>(DEFAULT_START);
  const [end, setEnd] = useState<string>(todayISO());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CompareResponse | null>(null);

  function toggleAsset(key: string) {
    setSelected((curr) => {
      if (curr.includes(key)) return curr.filter((k) => k !== key);
      if (curr.length >= MAX_ASSETS) return curr; // hard cap at MAX_ASSETS
      return [...curr, key];
    });
  }

  async function onCompare(e: FormEvent) {
    e.preventDefault();
    if (selected.length < MIN_ASSETS || selected.length > MAX_ASSETS) {
      setError(`Select between ${MIN_ASSETS} and ${MAX_ASSETS} assets.`);
      return;
    }
    setError(null);
    setLoading(true);
    setResult(null);
    try {
      const data = await apiFetch<CompareResponse>('/research/compare', {
        method: 'POST',
        body: JSON.stringify({
          assets: selected,
          strategy,
          start,
          end,
        }),
      });
      setResult(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  const canCompare =
    selected.length >= MIN_ASSETS &&
    selected.length <= MAX_ASSETS &&
    !!strategy &&
    !!start &&
    !!end &&
    !loading;

  const failedAssets = result
    ? (Object.entries(result.assets).filter(([, r]) => isAssetError(r)) as Array<[string, AssetError]>)
    : [];

  return (
    <div className="min-h-screen bg-black text-white p-4 md:p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-start gap-3">
          <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400">
            <GitCompare className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-white">Cross-Asset Comparison</h1>
            <p className="text-sm text-gray-400 mt-1 max-w-3xl">
              Normalized total return (rebased to 100) across 2-5 assets over a shared
              date window. Powered by the same backtest engine as the BTC lab.
            </p>
          </div>
        </div>

        {/* Controls panel */}
        <form
          onSubmit={onCompare}
          className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-5"
        >
          {/* Assets */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-medium text-gray-300 flex items-center gap-2">
                <Activity className="w-4 h-4 text-blue-400" />
                Assets
                <span className="text-xs text-gray-500 font-normal">
                  {selected.length}/{MAX_ASSETS} selected (min {MIN_ASSETS})
                </span>
              </h2>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-2">
              {ASSET_OPTIONS.map((opt) => {
                const checked = selected.includes(opt.key);
                const disabled = !checked && selected.length >= MAX_ASSETS;
                return (
                  <label
                    key={opt.key}
                    className={`flex items-start gap-2 rounded-lg border p-3 transition-colors ${
                      checked
                        ? 'bg-emerald-500/10 border-emerald-500/50 cursor-pointer'
                        : disabled
                        ? 'bg-gray-900 border-gray-800 opacity-50 cursor-not-allowed'
                        : 'bg-gray-900 border-gray-800 hover:border-gray-700 cursor-pointer'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={disabled}
                      onChange={() => toggleAsset(opt.key)}
                      className="mt-0.5 accent-emerald-500"
                    />
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-white">{opt.key}</div>
                      <div className="text-xs text-gray-500 truncate">{opt.label}</div>
                    </div>
                  </label>
                );
              })}
            </div>
          </div>

          {/* Strategy + date range */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label
                htmlFor="strategy"
                className="text-xs text-gray-500 uppercase tracking-wider block mb-1"
              >
                Strategy
              </label>
              <select
                id="strategy"
                value={strategy}
                onChange={(e) => setStrategy(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
              >
                {STRATEGY_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label
                htmlFor="start"
                className="text-xs text-gray-500 uppercase tracking-wider block mb-1"
              >
                Start date
              </label>
              <input
                id="start"
                type="date"
                value={start}
                onChange={(e) => setStart(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
              />
            </div>
            <div>
              <label
                htmlFor="end"
                className="text-xs text-gray-500 uppercase tracking-wider block mb-1"
              >
                End date
              </label>
              <input
                id="end"
                type="date"
                value={end}
                onChange={(e) => setEnd(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
              />
            </div>
          </div>

          {/* Submit */}
          <div className="flex flex-wrap items-center gap-3 pt-4 border-t border-gray-800">
            <button
              type="submit"
              disabled={!canCompare}
              className="inline-flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 disabled:bg-gray-700 disabled:text-gray-500 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
            >
              {loading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <GitCompare className="w-4 h-4" />
              )}
              <span>{loading ? 'Running backtests…' : 'Compare'}</span>
            </button>
            <p className="text-xs text-gray-500">
              Multi-asset backtests can take 5-30s depending on the date range.
            </p>
          </div>
        </form>

        {/* Error */}
        {error && (
          <div
            role="alert"
            className="flex items-start gap-2 text-red-400 bg-red-900/20 border border-red-800 rounded-lg p-3"
          >
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
            <div className="text-sm">
              <p className="font-medium">Comparison failed.</p>
              <p className="text-red-300/80 mt-0.5">{error}</p>
              <p className="text-xs text-red-300/60 mt-1">
                Check API server + FRED_API_KEY.
              </p>
            </div>
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-8 flex flex-col items-center justify-center min-h-[240px]">
            <Loader2 className="w-8 h-8 text-emerald-400 animate-spin mb-3" />
            <p className="text-sm text-gray-400">
              Running {selected.length}-asset backtest with {strategy}…
            </p>
          </div>
        )}

        {/* Results */}
        {!loading && result && (
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-4">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <h3 className="text-sm font-medium text-gray-300 flex items-center gap-2">
                <Activity className="w-4 h-4 text-emerald-400" />
                Normalized total return (base = 100)
              </h3>
              <p className="text-xs text-gray-500 font-mono">
                {result.strategy} · {result.start} → {result.end}
              </p>
            </div>

            <MultiLineChart assets={result.assets} />

            {/* Per-asset errors (API surfaces these inline, overall success still true) */}
            {failedAssets.length > 0 && (
              <div className="mt-4 pt-4 border-t border-gray-800 space-y-2">
                <p className="text-xs uppercase tracking-wider text-gray-500">
                  Failed assets
                </p>
                {failedAssets.map(([assetKey, r]) => (
                  <div
                    key={assetKey}
                    className="flex items-start gap-2 text-xs"
                  >
                    <span className="font-mono text-gray-400 shrink-0">
                      {assetKey}:
                    </span>
                    <span className="text-red-400">{r.error}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Empty state */}
        {!loading && !result && !error && (
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-12 flex flex-col items-center justify-center text-center">
            <Info className="w-10 h-10 text-gray-600 mb-3" />
            <p className="text-sm text-gray-400">
              Select {MIN_ASSETS}-{MAX_ASSETS} assets, a strategy, and a date range, then hit Compare.
            </p>
            <p className="text-xs text-gray-600 mt-1">
              All series are rebased to 100 at the start date for direct comparison.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
