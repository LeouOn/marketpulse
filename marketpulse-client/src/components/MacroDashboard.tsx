'use client';

/**
 * MacroDashboard -- W5 T23 (Metis SC1 lockdown).
 *
 * STRICT SCOPE: Exactly 3 sections, queried via `[data-macro-section]`.
 *   1. `regime-card`  : current regime label + 5 probability bars + alpha slider
 *   2. `timeline`     : last 12 months regime history (12 monthly cells)
 *   3. `narrator`     : LLM narrator text panel (scrolling)
 *
 * Do NOT add a 4th element. Out-of-scope items (factor decomposition,
 * threshold UI, full heatmap) are explicitly forbidden by SC1.
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Globe,
  Bot,
  Sliders,
  AlertCircle,
  RefreshCw,
  Calendar,
} from 'lucide-react';
import { apiFetch } from '../lib/api';

// ---------------------------------------------------------------------------
// Design tokens -- 3 of 5 align with globals.css CSS vars
// (RISK_ON=--green-bright, DEFLATION_SCARE=--blue-accent, RECESSION=--red-bright).
// INFLATION_ACCEL (amber) + REAL_YIELD_SHOCK (violet) are standard Tailwind
// accents already used elsewhere in the dashboard (e.g. text-purple-400,
// text-yellow-400 in ThreeColumnDashboard).
// ---------------------------------------------------------------------------
const REGIME_COLORS: Record<string, string> = {
  RISK_ON: '#10b981', // green  (--green-bright)
  DEFLATION_SCARE: '#3b82f6', // blue   (--blue-accent)
  INFLATION_ACCEL: '#f59e0b', // amber
  REAL_YIELD_SHOCK: '#8b5cf6', // violet
  RECESSION: '#ef4444', // red    (--red-bright)
};

const REGIME_ORDER: ReadonlyArray<keyof typeof REGIME_COLORS> = [
  'RISK_ON',
  'DEFLATION_SCARE',
  'INFLATION_ACCEL',
  'REAL_YIELD_SHOCK',
  'RECESSION',
];

const REGIME_LABELS: Record<string, string> = {
  RISK_ON: 'Risk On',
  DEFLATION_SCARE: 'Deflation Scare',
  INFLATION_ACCEL: 'Inflation Accel',
  REAL_YIELD_SHOCK: 'Real Yield Shock',
  RECESSION: 'Recession',
};

// Broad-market proxy for the "current regime" view. Per SC1 the regime itself
// is global (driven by macro factors, not asset-specific). EQUITIES (SPY) is
// the most representative risk asset on the registered AssetRegistry.
const DEFAULT_ASSET = 'EQUITIES';
const DEFAULT_ALPHA = 0.7;
const TIMELINE_MONTHS = 12;

// ---------------------------------------------------------------------------
// API response shapes (matches src/api/research_router.py)
// ---------------------------------------------------------------------------
interface RegimeRecord {
  date: string;
  dominant_regime: string;
  RISK_ON?: number;
  DEFLATION_SCARE?: number;
  INFLATION_ACCEL?: number;
  REAL_YIELD_SHOCK?: number;
  RECESSION?: number;
}

interface RegimeTapeResponse {
  regimes: RegimeRecord[];
  count: number;
  start: string | null;
  end: string | null;
}

interface CurrentRegimeResponse {
  asset: string;
  regime: string;
  probs: Record<string, number>;
  source: string;
  narrative: string;
  timestamp: string | null;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Format `YYYY-MM-DD` for query params (UTC, no time component). */
function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

/** Bucket the daily regime tape into the last N months (last record per month wins). */
function bucketByMonth(records: RegimeRecord[], monthCount: number): Array<{
  monthKey: string;
  monthLabel: string;
  record: RegimeRecord | null;
}> {
  // Bucket by YYYY-MM, last record wins (most recent observation in the month).
  const byMonth = new Map<string, RegimeRecord>();
  for (const rec of records) {
    const monthKey = rec.date.slice(0, 7); // YYYY-MM
    byMonth.set(monthKey, rec); // later records overwrite
  }

  // Build the last N months (including the current month), oldest first.
  const out: Array<{ monthKey: string; monthLabel: string; record: RegimeRecord | null }> = [];
  const now = new Date();
  for (let i = monthCount - 1; i >= 0; i--) {
    const d = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - i, 1));
    const monthKey = `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`;
    const monthLabel = d.toLocaleDateString('en-US', {
      month: 'short',
      year: '2-digit',
      timeZone: 'UTC',
    });
    out.push({ monthKey, monthLabel, record: byMonth.get(monthKey) ?? null });
  }
  return out;
}

// ---------------------------------------------------------------------------
// Sub-components (kept local; not exported -- only MacroDashboard is public)
// ---------------------------------------------------------------------------

const SkeletonBox: React.FC<{ className?: string }> = ({ className = '' }) => (
  <div
    className={`bg-gray-800/60 rounded animate-pulse ${className}`}
    aria-hidden="true"
  />
);

const ErrorBanner: React.FC<{ message: string; onRetry: () => void }> = ({
  message,
  onRetry,
}) => (
  <div className="p-4 bg-red-900/20 border border-red-500/30 rounded-lg text-red-400 text-sm flex items-start gap-2">
    <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
    <div className="flex-1">
      <p className="font-semibold text-red-300">Macro data unavailable</p>
      <p className="text-red-400/80 mt-1 text-xs">{message}</p>
    </div>
    <button
      onClick={onRetry}
      className="ml-2 underline shrink-0 hover:text-red-200"
    >
      Retry
    </button>
  </div>
);

const ProbabilityBar: React.FC<{
  regime: string;
  value: number | undefined;
}> = ({ regime, value }) => {
  const pct = value == null ? 0 : Math.max(0, Math.min(1, value)) * 100;
  const color = REGIME_COLORS[regime] ?? '#6b7280';
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-gray-400 w-32 shrink-0">
        {REGIME_LABELS[regime] ?? regime}
      </span>
      <div className="flex-1 h-2.5 bg-gray-800 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500 ease-out"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
      <span
        className="text-xs font-mono w-12 text-right shrink-0"
        style={{ color: value == null ? '#6b7280' : color }}
      >
        {value == null ? '--' : `${pct.toFixed(1)}%`}
      </span>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function MacroDashboard() {
  // --- State ---
  const [tape, setTape] = useState<RegimeTapeResponse | null>(null);
  const [current, setCurrent] = useState<CurrentRegimeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [alpha, setAlpha] = useState(DEFAULT_ALPHA);
  const [refreshKey, setRefreshKey] = useState(0);

  // --- Data fetching ---
  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const end = new Date();
      const start = new Date(
        Date.UTC(end.getUTCFullYear(), end.getUTCMonth() - TIMELINE_MONTHS, 1),
      );
      const startStr = isoDate(start);
      const endStr = isoDate(end);

      const [tapeRes, currentRes] = await Promise.allSettled([
        apiFetch<RegimeTapeResponse>(
          `/research/regimes?start=${encodeURIComponent(startStr)}&end=${encodeURIComponent(endStr)}`,
        ),
        apiFetch<CurrentRegimeResponse>(
          `/research/${encodeURIComponent(DEFAULT_ASSET)}/regime?date=${encodeURIComponent(
            endStr,
          )}&alpha=${alpha.toFixed(2)}`,
        ),
      ]);

      if (tapeRes.status === 'fulfilled') {
        setTape(tapeRes.value);
      } else {
        // Non-fatal: timeline is allowed to be empty while current card still renders.
        setTape(null);
      }

      if (currentRes.status === 'fulfilled') {
        setCurrent(currentRes.value);
      } else {
        // Current regime failure is fatal -- the card is the primary element.
        const reason = (currentRes.reason as Error)?.message ?? 'Unknown error';
        setCurrent(null);
        setError(reason);
      }
    } catch (err) {
      const reason = err instanceof Error ? err.message : 'Unknown error';
      setError(reason);
      setCurrent(null);
    } finally {
      setLoading(false);
    }
  }, [alpha]);

  useEffect(() => {
    // fetchData is async; setState calls fire after `await`, not synchronously.
    // Mirrors the established pattern in ThreeColumnDashboard.tsx:145.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchData();
    // refreshKey lets the Retry button force a refetch without changing alpha.
  }, [fetchData, refreshKey]);

  // --- Derived state ---
  const dominantRegime = current?.regime ?? '';
  const dominantColor = REGIME_COLORS[dominantRegime] ?? '#6b7280';
  const timelineBuckets = useMemo(
    () => bucketByMonth(tape?.regimes ?? [], TIMELINE_MONTHS),
    [tape],
  );

  // Friendly FRED-specific error message.
  const friendlyError = useMemo(() => {
    if (!error) return null;
    const lower = error.toLowerCase();
    if (
      lower.includes('fred') ||
      lower.includes('503') ||
      lower.includes('macro') ||
      lower.includes('factor')
    ) {
      return 'Macro factor data unavailable. Check FRED_API_KEY configuration in the backend environment.';
    }
    return error;
  }, [error]);

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <div className="space-y-6">
      {friendlyError && (
        <ErrorBanner
          message={friendlyError}
          onRetry={() => setRefreshKey((k) => k + 1)}
        />
      )}

      {/* ============================================================= */}
      {/* SECTION 1 of 3: Current Regime Card                            */}
      {/* ============================================================= */}
      <section
        data-macro-section="regime-card"
        className="bg-gray-900 border border-gray-700 rounded-lg p-5 relative overflow-hidden"
      >
        {/* Dominant-regime accent stripe -- uses the live regime color so the */}
        {/* card visually "becomes" the regime when state changes.             */}
        <div
          className="absolute left-0 top-0 bottom-0 w-1.5 transition-colors duration-500"
          style={{ backgroundColor: dominantColor }}
          aria-hidden="true"
        />
        <div className="flex items-start justify-between gap-4 mb-5 pl-2">
          <div className="flex items-center gap-2">
            <Globe className="w-5 h-5 text-blue-400" />
            <h3 className="text-lg font-semibold text-white">Current Regime</h3>
          </div>
          {current?.source && (
            <span className="text-[10px] uppercase tracking-wider text-gray-500 font-mono">
              source: {current.source}
            </span>
          )}
        </div>

        {loading && !current ? (
          <div className="pl-2 space-y-4">
            <SkeletonBox className="h-10 w-72" />
            <div className="space-y-2.5 pt-2">
              {REGIME_ORDER.map((r) => (
                <div key={r} className="flex items-center gap-3">
                  <SkeletonBox className="h-3 w-32" />
                  <SkeletonBox className="h-2.5 flex-1" />
                  <SkeletonBox className="h-3 w-12" />
                </div>
              ))}
            </div>
            <SkeletonBox className="h-9 w-full mt-2" />
          </div>
        ) : (
          <div className="pl-2">
            {/* Big regime label */}
            <div className="mb-5">
              <div
                className="text-3xl lg:text-4xl font-bold tracking-tight transition-colors duration-500"
                style={{ color: dominantColor }}
                data-testid="regime-label"
              >
                {dominantRegime
                  ? REGIME_LABELS[dominantRegime] ?? dominantRegime
                  : '—'}
              </div>
              {current?.timestamp && (
                <div className="text-xs text-gray-500 mt-1 font-mono">
                  as of {current.timestamp.slice(0, 10)}
                </div>
              )}
            </div>

            {/* 5 probability bars */}
            <div className="space-y-2.5 mb-5">
              {REGIME_ORDER.map((regime) => (
                <ProbabilityBar
                  key={regime}
                  regime={regime}
                  value={current?.probs?.[regime]}
                />
              ))}
            </div>

            {/* Alpha slider */}
            <div className="bg-gray-800/40 border border-gray-700/60 rounded-md p-3">
              <div className="flex items-center justify-between mb-2">
                <label
                  htmlFor="alpha-slider"
                  className="flex items-center gap-1.5 text-xs font-medium text-gray-300"
                >
                  <Sliders className="w-3.5 h-3.5" />
                  Alpha Blend
                  <span className="text-gray-500 font-normal normal-case tracking-normal">
                    (0 = pure LLM · 1 = pure rules)
                  </span>
                </label>
                <span
                  className="text-xs font-mono font-semibold text-blue-300"
                  data-testid="alpha-value"
                >
                  {alpha.toFixed(2)}
                </span>
              </div>
              <input
                id="alpha-slider"
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={alpha}
                onChange={(e) => setAlpha(parseFloat(e.target.value))}
                className="w-full accent-blue-500 cursor-pointer"
                data-testid="alpha-slider"
              />
            </div>
          </div>
        )}
      </section>

      {/* ============================================================= */}
      {/* SECTION 2 of 3: 12-Month Regime Timeline                       */}
      {/* ============================================================= */}
      <section
        data-macro-section="timeline"
        className="bg-gray-900 border border-gray-700 rounded-lg p-5"
      >
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Calendar className="w-5 h-5 text-purple-400" />
            <h3 className="text-lg font-semibold text-white">
              12-Month Regime History
            </h3>
          </div>
          <span className="text-xs text-gray-500">
            last 12 months · monthly dominant regime
          </span>
        </div>

        {/* Legend */}
        <div className="flex flex-wrap gap-x-4 gap-y-1.5 mb-4">
          {REGIME_ORDER.map((r) => (
            <div key={r} className="flex items-center gap-1.5">
              <span
                className="w-2.5 h-2.5 rounded-sm"
                style={{ backgroundColor: REGIME_COLORS[r] }}
                aria-hidden="true"
              />
              <span className="text-[11px] text-gray-400">
                {REGIME_LABELS[r]}
              </span>
            </div>
          ))}
        </div>

        {/* 12 cells, oldest -> newest, left -> right */}
        <div
          className="grid gap-1.5"
          style={{ gridTemplateColumns: `repeat(${TIMELINE_MONTHS}, minmax(0, 1fr))` }}
          data-testid="timeline-cells"
        >
          {timelineBuckets.map(({ monthKey, monthLabel, record }) => {
            const regime = record?.dominant_regime ?? '';
            const color = REGIME_COLORS[regime];
            const hasData = Boolean(record && color);
            return (
              <div
                key={monthKey}
                className="flex flex-col items-center text-center"
                title={
                  hasData
                    ? `${monthLabel}: ${REGIME_LABELS[regime] ?? regime}`
                    : `${monthLabel}: no data`
                }
              >
                <div
                  className="w-full h-10 rounded-md transition-colors duration-300 border"
                  style={{
                    backgroundColor: hasData ? color : 'transparent',
                    borderColor: hasData ? color : '#374151',
                    opacity: hasData ? 0.85 : 0.4,
                  }}
                  data-testid={`timeline-cell-${monthKey}`}
                  data-regime={regime || undefined}
                />
                <span className="text-[10px] text-gray-500 mt-1 font-mono">
                  {monthLabel}
                </span>
              </div>
            );
          })}
        </div>
      </section>

      {/* ============================================================= */}
      {/* SECTION 3 of 3: LLM Narrator Panel                             */}
      {/* ============================================================= */}
      <section
        data-macro-section="narrator"
        className="bg-gray-900 border border-gray-700 rounded-lg p-5"
      >
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Bot className="w-5 h-5 text-green-400" />
            <h3 className="text-lg font-semibold text-white">
              Regime Narrative
            </h3>
          </div>
          <button
            onClick={() => setRefreshKey((k) => k + 1)}
            disabled={loading}
            className="p-1.5 bg-gray-800 hover:bg-gray-700 rounded-md transition-colors text-gray-400 hover:text-white disabled:opacity-50"
            title="Refresh narrative"
          >
            <RefreshCw
              className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`}
            />
          </button>
        </div>

        {/* Scrolling text area */}
        <div
          className="bg-gray-950/60 border border-gray-800 rounded-md p-4 max-h-80 overflow-y-auto"
          data-testid="narrator-text"
        >
          {loading && !current ? (
            <div className="space-y-2">
              <SkeletonBox className="h-3 w-full" />
              <SkeletonBox className="h-3 w-11/12" />
              <SkeletonBox className="h-3 w-4/5" />
              <SkeletonBox className="h-3 w-full" />
              <SkeletonBox className="h-3 w-3/4" />
            </div>
          ) : current?.narrative ? (
            <pre className="whitespace-pre-wrap text-sm text-gray-300 font-sans leading-relaxed">
              {current.narrative}
            </pre>
          ) : (
            <p className="text-sm text-gray-600 italic">
              No narrative available for the current regime.
            </p>
          )}
        </div>
      </section>
    </div>
  );
}
