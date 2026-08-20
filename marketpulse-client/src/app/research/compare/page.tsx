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
      <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1">
        {validEntries.map(([assetKey, series], i) => {
          const color = SERIES_PALETTE[i % SERIES_PALETTE.length];
          const pct = series.total_return_pct;
          const positive = pct >= 0;
          return (
            <div key={assetKey} className="flex items-center gap-1.5">
              <span
                className="inline-block w-2 h-2"
                style={{ backgroundColor: color }}
                aria-hidden
              />
              <span className="text-[11px] font-mono text-ink">{assetKey}</span>
              <span
                className={`text-[11px] font-mono tabular-nums ${
                  positive ? 'text-pos' : 'text-neg'
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
    <div className="min-h-screen bg-canvas text-ink p-2.5">
      <div className="max-w-7xl mx-auto space-y-2.5">
        {/* Header */}
        <div className="flex items-start gap-2.5">
          <div className="p-1.5 bg-teal-dim text-teal rounded-[2px]">
            <GitCompare className="w-4 h-4" />
          </div>
          <div>
            <h1 className="text-[15px] leading-tight font-semibold text-ink">Cross-Asset Comparison</h1>
            <p className="text-[12.5px] text-ink-secondary mt-1 max-w-3xl">
              Normalized total return (rebased to 100) across 2-5 assets over a shared
              date window. Powered by the same backtest engine as the BTC lab.
            </p>
          </div>
        </div>

        {/* Controls panel */}
        <form
          onSubmit={onCompare}
          className="panel p-2.5 space-y-2.5"
        >
          {/* Assets */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <h2 className="panel-title flex items-center gap-2">
                <Activity className="w-3.5 h-3.5 text-sel" />
                Assets
                <span className="text-[11px] text-ink-muted font-mono font-normal normal-case tracking-normal">
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
                    className={`flex items-start gap-2 border p-2 rounded-[2px] ${
                      checked
                        ? 'bg-teal-dim border-teal cursor-pointer'
                        : disabled
                        ? 'bg-surface border-line-subtle opacity-50 cursor-not-allowed'
                        : 'bg-surface border-line-subtle hover:border-line cursor-pointer'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={disabled}
                      onChange={() => toggleAsset(opt.key)}
                      className="mt-0.5 accent-[var(--teal)]"
                    />
                    <div className="min-w-0">
                      <div className="text-[12.5px] font-mono font-medium text-ink">{opt.key}</div>
                      <div className="text-[11px] text-ink-muted truncate">{opt.label}</div>
                    </div>
                  </label>
                );
              })}
            </div>
          </div>

          {/* Strategy + date range */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5">
            <div>
              <label
                htmlFor="strategy"
                className="panel-title block mb-1"
              >
                Strategy
              </label>
              <select
                id="strategy"
                value={strategy}
                onChange={(e) => setStrategy(e.target.value)}
                className="input w-full"
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
                className="panel-title block mb-1"
              >
                Start date
              </label>
              <input
                id="start"
                type="date"
                value={start}
                onChange={(e) => setStart(e.target.value)}
                className="input w-full"
              />
            </div>
            <div>
              <label
                htmlFor="end"
                className="panel-title block mb-1"
              >
                End date
              </label>
              <input
                id="end"
                type="date"
                value={end}
                onChange={(e) => setEnd(e.target.value)}
                className="input w-full"
              />
            </div>
          </div>

          {/* Submit */}
          <div className="flex flex-wrap items-center gap-2.5 pt-2.5 border-t border-line-subtle">
            <button
              type="submit"
              disabled={!canCompare}
              className="btn btn-primary disabled:opacity-50"
            >
              {loading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <GitCompare className="w-4 h-4" />
              )}
              <span>{loading ? 'Running backtests\u2026' : 'Compare'}</span>
            </button>
            <p className="text-[11px] text-ink-muted">
              Multi-asset backtests can take 5-30s depending on the date range.
            </p>
          </div>
        </form>

        {/* Error */}
        {error && (
          <div
            role="alert"
            className="flex items-start gap-2 text-neg bg-neg-dim border border-line rounded-[2px] p-2.5"
          >
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
            <div className="text-[12.5px]">
              <p className="font-medium text-ink">Comparison failed.</p>
              <p className="text-neg mt-0.5">{error}</p>
              <p className="text-[11px] text-ink-muted mt-1">
                Check API server + FRED_API_KEY.
              </p>
            </div>
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="panel p-8 flex flex-col items-center justify-center min-h-[240px]">
            <Loader2 className="w-8 h-8 text-teal animate-spin mb-3" />
            <p className="text-[12.5px] text-ink-secondary">
              Running {selected.length}-asset backtest with {strategy}{'\u2026'}
            </p>
          </div>
        )}

        {/* Results */}
        {!loading && result && (
          <div className="panel p-2.5 space-y-2.5">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <h3 className="panel-title flex items-center gap-2">
                <Activity className="w-3.5 h-3.5 text-teal" />
                Relative Performance (Rebased 100)
              </h3>
              <p className="text-[11px] text-ink-muted font-mono">
                {result.strategy} · {result.start} → {result.end}
              </p>
            </div>

            <MultiLineChart assets={result.assets} />

            {/* Per-asset errors (API surfaces these inline, overall success still true) */}
            {failedAssets.length > 0 && (
              <div className="mt-2.5 pt-2.5 border-t border-line-subtle space-y-2">
                <p className="panel-title">
                  Failed assets
                </p>
                {failedAssets.map(([assetKey, r]) => (
                  <div
                    key={assetKey}
                    className="flex items-start gap-2 text-[11px]"
                  >
                    <span className="font-mono text-ink-muted shrink-0">
                      {assetKey}:
                    </span>
                    <span className="text-neg">{r.error}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Empty state */}
        {!loading && !result && !error && (
          <div className="panel p-12 flex flex-col items-center justify-center text-center">
            <Info className="w-8 h-8 text-ink-muted mb-3" />
            <p className="text-[12.5px] text-ink-secondary">
              Select {MIN_ASSETS}-{MAX_ASSETS} assets, a strategy, and a date range, then hit Compare.
            </p>
            <p className="text-[11px] text-ink-muted mt-1">
              All series are rebased to 100 at the start date for direct comparison.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
