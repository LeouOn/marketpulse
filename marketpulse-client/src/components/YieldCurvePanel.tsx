'use client';

import { useMemo } from 'react';
import { useYieldCurveCurrent, useYieldCurveAlerts } from '../hooks/useYieldCurveData';
import type { YieldCurveAlert } from '../types/market';

const TENOR_ORDER = ['3mo', '1y', '2y', '5y', '7y', '10y', '20y', '30y'] as const;

const SHAPE_TONE: Record<string, { text: string; bg: string; border: string }> = {
  NORMAL: { text: 'text-pos', bg: 'bg-pos-dim', border: 'border-pos' },
  FLAT: { text: 'text-warn', bg: 'bg-warn-dim', border: 'border-warn' },
  INVERTED: { text: 'text-neg', bg: 'bg-neg-dim', border: 'border-neg' },
  HUMPED: { text: 'text-sel', bg: 'bg-sel-dim', border: 'border-sel' },
  INVERTED_HUMPED: { text: 'text-neg', bg: 'bg-neg-dim', border: 'border-neg' },
};

const PRIORITY_TONE: Record<string, string> = {
  LOW: 'text-ink-muted',
  MEDIUM: 'text-sel',
  HIGH: 'text-warn',
  CRITICAL: 'text-neg',
};

function CurveChart({ curve }: { curve: Record<string, number> }) {
  const points = useMemo(() => {
    const pts = TENOR_ORDER
      .map((t, i) => ({ x: i, y: curve[t] }))
      .filter((p) => p.y !== undefined);
    if (pts.length < 2) return '';
    const xs = pts.map((p) => p.x);
    const ys = pts.map((p) => p.y!);
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const minY = Math.min(...ys), maxY = Math.max(...ys);
    const range = maxY - minY || 1;
    return pts
      .map((p) => {
        const x = ((p.x - minX) / (maxX - minX || 1)) * 100;
        const y = 100 - ((p.y! - minY) / range) * 100;
        return `${x.toFixed(2)},${y.toFixed(2)}`;
      })
      .join(' ');
  }, [curve]);

  return (
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="w-full h-32">
      <polyline
        points={points}
        fill="none"
        stroke="var(--blue)"
        strokeWidth="1.5"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

function SpreadBigNumber({ value, delta5d }: { value: number | null; delta5d: number | null }) {
  const color = value === null ? 'text-ink-muted' : value > 0 ? 'text-pos' : value < 0 ? 'text-neg' : 'text-ink';
  const deltaColor = delta5d === null ? '' : delta5d > 0 ? 'text-pos' : delta5d < 0 ? 'text-neg' : 'text-ink-muted';
  const arrow = delta5d === null ? '' : delta5d > 0 ? '▲' : delta5d < 0 ? '▼' : '·';
  return (
    <div className="flex items-baseline gap-3">
      <span className={`text-[18px] font-bold font-mono tabular-nums ${color}`}>
        {value === null ? '—' : `${value > 0 ? '+' : ''}${value.toFixed(1)}`}
        <span className="text-[11px] font-normal text-ink-muted ml-1">bps</span>
      </span>
      {delta5d !== null && (
        <span className={`text-[11px] font-mono tabular-nums ${deltaColor}`}>
          {arrow} {Math.abs(delta5d).toFixed(1)} (5d)
        </span>
      )}
    </div>
  );
}

function RecessionGauge({ prob }: { prob: number | null }) {
  if (prob === null) return <div className="text-ink-muted text-[12px]">Recession prob: —</div>;
  const pct = (prob * 100).toFixed(0);
  const color = prob < 0.25 ? 'text-pos' : prob < 0.50 ? 'text-warn' : 'text-neg';
  return (
    <div className="text-[12px]">
      <span className="text-ink-secondary">NY Fed recession prob: </span>
      <span className={`font-mono tabular-nums font-bold ${color}`}>{pct}%</span>
    </div>
  );
}

function AlertRow({ a }: { a: YieldCurveAlert }) {
  return (
    <div className="py-1.5 border-b border-line-subtle last:border-b-0">
      <div className="flex items-baseline justify-between gap-2">
        <span className={`text-[11px] font-mono font-semibold ${PRIORITY_TONE[a.priority] ?? 'text-ink-muted'}`}>
          [{a.priority}]
        </span>
        <span className="text-[11px] text-ink-muted font-mono tabular-nums">
          {new Date(a.triggered_at).toLocaleString()}
        </span>
      </div>
      <div className="text-[12.5px] text-ink mt-0.5">{a.rule_name}</div>
      <pre className="text-[11px] text-ink-secondary mt-0.5 whitespace-pre-wrap font-mono">{a.message}</pre>
    </div>
  );
}

export function YieldCurvePanel() {
  const currentQ = useYieldCurveCurrent();
  const alertsQ = useYieldCurveAlerts(30);

  const snap = currentQ.data;
  const alerts = alertsQ.data ?? [];
  const isLoading = currentQ.isLoading;
  const isError = currentQ.isError;

  return (
    <section className="panel">
      <div className="border-b border-line-subtle px-3 h-8 flex items-center justify-between">
        <span className="panel-title">US Treasury Yield Curve</span>
        {snap?.stale && (
          <span className="text-[11px] text-warn font-mono">
            stale ({snap.days_since_update}d)
          </span>
        )}
      </div>

      <div className="p-2.5">
        {isLoading && <div className="text-[12px] text-ink-muted">Loading…</div>}
        {isError && <div className="text-[12px] text-neg">Failed to load curve data.</div>}

        {snap && (
          <div className="space-y-3">
            {/* Curve shape chart */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-[11px] uppercase tracking-[0.08em] text-ink-secondary">
                  Curve shape
                </span>
                <span
                  className={`border rounded-[2px] px-1.5 h-5 text-[11px] font-mono inline-flex items-center ${
                    (SHAPE_TONE[snap.shape] ?? { text: 'text-ink-muted', bg: 'bg-surface-hover', border: 'border-line' }).border
                  } ${(SHAPE_TONE[snap.shape] ?? { text: 'text-ink-muted' }).text}`}
                >
                  {snap.shape} · {snap.shape_trend}
                </span>
              </div>
              <CurveChart curve={snap.curve} />
              <div className="flex justify-between text-[10px] text-ink-muted mt-1 font-mono tabular-nums">
                {TENOR_ORDER.map((t) => <span key={t}>{t}</span>)}
              </div>
            </div>

            {/* 2s10s spread big number */}
            <div>
              <div className="text-[11px] uppercase tracking-[0.08em] text-ink-secondary mb-1">
                2s/10s spread
              </div>
              <SpreadBigNumber
                value={snap.spreads['2s10s'] ?? null}
                delta5d={snap.deltas.spread_2s10s_delta_5d}
              />
            </div>

            <RecessionGauge prob={snap.recession_prob_nyfed} />

            {/* Recent alerts */}
            <div>
              <div className="text-[11px] uppercase tracking-[0.08em] text-ink-secondary mb-1.5">
                Recent alerts (30d)
              </div>
              {alerts.length === 0 ? (
                <div className="text-[11px] text-ink-muted">No alerts in window.</div>
              ) : (
                <div className="max-h-48 overflow-y-auto">
                  {alerts.slice(0, 10).map((a, i) => <AlertRow key={i} a={a} />)}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

export default YieldCurvePanel;