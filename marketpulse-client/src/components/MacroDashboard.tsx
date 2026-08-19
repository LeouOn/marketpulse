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
import { YieldCurvePanel } from './YieldCurvePanel';

// ---------------------------------------------------------------------------
// Regime tone map — maps each regime to design-token color classes so we
// don't ship ad-hoc hex anywhere. Token-based colors stay theme-aware.
// ---------------------------------------------------------------------------
type RegimeKey =
  | 'RISK_ON'
  | 'DEFLATION_SCARE'
  | 'INFLATION_ACCEL'
  | 'REAL_YIELD_SHOCK'
  | 'RECESSION';

const REGIME_TONE: Record<
  RegimeKey,
  { text: string; dim: string; bar: string; border: string }
> = {
  RISK_ON: {
    text: 'text-pos',
    dim: 'bg-pos-dim',
    bar: 'bg-pos',
    border: 'border-pos',
  },
  DEFLATION_SCARE: {
    text: 'text-sel',
    dim: 'bg-sel-dim',
    bar: 'bg-sel',
    border: 'border-sel',
  },
  INFLATION_ACCEL: {
    text: 'text-warn',
    dim: 'bg-warn-dim',
    bar: 'bg-warn',
    border: 'border-warn',
  },
  REAL_YIELD_SHOCK: {
    text: 'text-teal',
    dim: 'bg-teal-dim',
    bar: 'bg-teal',
    border: 'border-teal',
  },
  RECESSION: {
    text: 'text-neg',
    dim: 'bg-neg-dim',
    bar: 'bg-neg',
    border: 'border-neg',
  },
};

const FALLBACK_TONE = {
  text: 'text-ink-muted',
  dim: 'bg-surface-hover',
  bar: 'bg-ink-muted',
  border: 'border-line',
};

const REGIME_ORDER: ReadonlyArray<RegimeKey> = [
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
    className={`bg-surface-raised animate-pulse rounded-[2px] ${className}`}
    aria-hidden="true"
  />
);

const ErrorBanner: React.FC<{ message: string; onRetry: () => void }> = ({
  message,
  onRetry,
}) => (
  <div className="p-2.5 bg-neg-dim border border-line rounded-[2px] text-neg text-[12.5px] flex items-start gap-2">
    <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
    <div className="flex-1">
      <p className="font-semibold text-neg">Macro data unavailable</p>
      <p className="text-neg/80 mt-0.5 text-[11px] text-ink-secondary">{message}</p>
    </div>
    <button
      onClick={onRetry}
      className="ml-2 underline shrink-0 text-neg hover:text-ink"
    >
      Retry
    </button>
  </div>
);

const RegimeChip: React.FC<{ regime: string | null | undefined }> = ({ regime }) => {
  if (!regime) {
    return (
      <span className="border border-line rounded-[2px] px-1.5 h-5 text-[11px] font-mono inline-flex items-center text-ink-muted">
        —
      </span>
    );
  }
  const tone = REGIME_TONE[regime as RegimeKey] ?? FALLBACK_TONE;
  return (
    <span
      className={`border rounded-[2px] px-1.5 h-5 text-[11px] font-mono inline-flex items-center ${tone.border} ${tone.text}`}
    >
      {REGIME_LABELS[regime] ?? regime}
    </span>
  );
};

const ProbabilityBar: React.FC<{
  regime: RegimeKey;
  value: number | undefined;
}> = ({ regime, value }) => {
  const pct = value == null ? 0 : Math.max(0, Math.min(1, value)) * 100;
  const tone = REGIME_TONE[regime];
  return (
    <div className="flex items-center gap-3">
      <span className="text-[12px] text-ink-secondary w-32 shrink-0">
        {REGIME_LABELS[regime] ?? regime}
      </span>
      <div className="flex-1 h-2.5 bg-surface-raised rounded-[2px] overflow-hidden">
        <div
          className={`h-full ${tone.bar} transition-all duration-500 ease-out`}
          style={{ width: `${pct}%`, opacity: value == null ? 0.25 : 1 }}
        />
      </div>
      <span
        className={`text-[11px] font-mono tabular-nums w-12 text-right shrink-0 ${
          value == null ? 'text-ink-muted' : tone.text
        }`}
      >
        {value == null ? '—' : `${pct.toFixed(1)}%`}
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
  const dominantRegime: RegimeKey | '' =
    current && (current.regime as RegimeKey) in REGIME_TONE
      ? (current.regime as RegimeKey)
      : '';
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
    <div className="space-y-2.5">
      <YieldCurvePanel />
      {friendlyError && (
        <ErrorBanner
          message={friendlyError}
          onRetry={() => setRefreshKey((k) => k + 1)}
        />
      )}

      {/* ============================================================= */}
      {/* SECTION 1 of 3: Current Regime Card                            */}
      {/* ============================================================= */}
      <section data-macro-section="regime-card" className="panel">
        <div className="border-b border-line-subtle px-3 h-8 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Globe className="w-3.5 h-3.5 text-sel" />
            <span className="panel-title">Current Regime</span>
          </div>
          {current?.source && (
            <span className="text-[10px] uppercase tracking-[0.08em] text-ink-muted font-mono">
              source: {current.source}
            </span>
          )}
        </div>

        <div className="p-2.5">
          {loading && !current ? (
            <div className="space-y-4">
              <SkeletonBox className="h-5 w-48" />
              <div className="space-y-2 pt-2">
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
            <div>
              {/* Regime chip + timestamp */}
              <div className="flex items-center gap-2 mb-4">
                <RegimeChip regime={dominantRegime} />
                {current?.timestamp && (
                  <span className="text-[11px] text-ink-muted font-mono tabular-nums">
                    as of {current.timestamp.slice(0, 10)}
                  </span>
                )}
              </div>

              {/* 5 probability bars */}
              <div className="space-y-2 mb-4">
                {REGIME_ORDER.map((regime) => (
                  <ProbabilityBar
                    key={regime}
                    regime={regime}
                    value={current?.probs?.[regime]}
                  />
                ))}
              </div>

              {/* Alpha slider */}
              <div className="bg-surface-raised border border-line rounded-[2px] p-2.5">
                <div className="flex items-center justify-between mb-2">
                  <label
                    htmlFor="alpha-slider"
                    className="flex items-center gap-1.5 text-[12px] font-medium text-ink-secondary"
                  >
                    <Sliders className="w-3.5 h-3.5" />
                    Alpha Blend
                    <span className="text-ink-muted font-normal normal-case tracking-normal text-[11px]">
                      (0 = pure LLM · 1 = pure rules)
                    </span>
                  </label>
                  <span
                    className="text-[11px] font-mono tabular-nums text-sel"
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
                  className="w-full accent-teal cursor-pointer"
                  data-testid="alpha-slider"
                />
              </div>
            </div>
          )}
        </div>
      </section>

      {/* ============================================================= */}
      {/* SECTION 2 of 3: 12-Month Regime Timeline                       */}
      {/* ============================================================= */}
      <section data-macro-section="timeline" className="panel">
        <div className="border-b border-line-subtle px-3 h-8 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Calendar className="w-3.5 h-3.5 text-teal" />
            <span className="panel-title">12-Month Regime History</span>
          </div>
          <span className="text-[11px] text-ink-muted font-mono">
            last 12 months · monthly dominant regime
          </span>
        </div>

        <div className="p-2.5">
          {/* Legend */}
          <div className="flex flex-wrap gap-x-4 gap-y-1 mb-3">
            {REGIME_ORDER.map((r) => {
              const tone = REGIME_TONE[r];
              return (
                <div key={r} className="flex items-center gap-1.5">
                  <span
                    className={`w-2 h-2 rounded-[1px] ${tone.dim} border ${tone.border}`}
                    aria-hidden="true"
                  />
                  <span className="text-[11px] text-ink-secondary">
                    {REGIME_LABELS[r]}
                  </span>
                </div>
              );
            })}
          </div>

          {/* 12 cells, oldest -> newest, left -> right */}
          <div
            className="grid gap-1"
            style={{ gridTemplateColumns: `repeat(${TIMELINE_MONTHS}, minmax(0, 1fr))` }}
            data-testid="timeline-cells"
          >
            {timelineBuckets.map(({ monthKey, monthLabel, record }) => {
              const regime = (record?.dominant_regime ?? '') as RegimeKey | '';
              const tone = regime ? REGIME_TONE[regime] : null;
              const hasData = Boolean(record && tone);
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
                    className={`w-full h-6 rounded-[2px] border transition-colors duration-300 ${
                      hasData
                        ? `${tone!.dim} ${tone!.border}`
                        : 'bg-transparent border-line-subtle'
                    }`}
                    data-testid={`timeline-cell-${monthKey}`}
                    data-regime={regime || undefined}
                  />
                  <span className="text-[10px] text-ink-muted mt-1 font-mono tabular-nums">
                    {monthLabel}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* ============================================================= */}
      {/* SECTION 3 of 3: LLM Narrator Panel                             */}
      {/* ============================================================= */}
      <section data-macro-section="narrator" className="panel">
        <div className="border-b border-line-subtle px-3 h-8 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Bot className="w-3.5 h-3.5 text-pos" />
            <span className="panel-title">Regime Narrative</span>
          </div>
          <button
            onClick={() => setRefreshKey((k) => k + 1)}
            disabled={loading}
            className="btn"
            title="Refresh narrative"
          >
            <RefreshCw
              className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`}
            />
            <span className="text-[11px]">Refresh</span>
          </button>
        </div>

        <div className="p-2.5">
          {/* Scrolling text area */}
          <div
            className="bg-surface-raised border border-line-subtle rounded-[2px] p-2.5 max-h-80 overflow-y-auto"
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
              <pre className="whitespace-pre-wrap text-[12.5px] text-ink-secondary font-sans leading-relaxed">
                {current.narrative}
              </pre>
            ) : (
              <p className="text-[12.5px] text-ink-muted italic">
                No narrative available for the current regime.
              </p>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}