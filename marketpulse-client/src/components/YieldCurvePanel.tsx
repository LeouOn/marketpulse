'use client';

import { useMemo } from 'react';
import { useYieldCurveCurrent, useYieldCurveAlerts } from '../hooks/useYieldCurveData';
import type { YieldCurveAlert } from '../types/market';

const TENOR_ORDER = ['3mo', '1y', '2y', '5y', '7y', '10y', '20y', '30y'] as const;
const SHAPE_BADGE_COLOR: Record<string, string> = {
  NORMAL: 'bg-emerald-500/20 text-emerald-400',
  FLAT: 'bg-amber-500/20 text-amber-400',
  INVERTED: 'bg-red-500/20 text-red-400',
  HUMPED: 'bg-sky-500/20 text-sky-400',
  INVERTED_HUMPED: 'bg-red-500/20 text-red-400',
};
const PRIORITY_COLOR: Record<string, string> = {
  LOW: 'text-slate-400',
  MEDIUM: 'text-sky-400',
  HIGH: 'text-amber-400',
  CRITICAL: 'text-red-400',
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
      <polyline points={points} fill="none" stroke="rgb(56 189 248)" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function SpreadBigNumber({ value, delta5d }: { value: number | null; delta5d: number | null }) {
  const color = value === null ? 'text-slate-500' : value > 0 ? 'text-emerald-400' : value < 0 ? 'text-red-400' : 'text-slate-300';
  const deltaColor = delta5d === null ? '' : delta5d > 0 ? 'text-emerald-400' : delta5d < 0 ? 'text-red-400' : 'text-slate-400';
  const arrow = delta5d === null ? '' : delta5d > 0 ? '▲' : delta5d < 0 ? '▼' : '·';
  return (
    <div className="flex items-baseline gap-3">
      <span className={`text-3xl font-bold ${color}`}>
        {value === null ? '—' : `${value > 0 ? '+' : ''}${value.toFixed(1)}`}
        <span className="text-sm font-normal text-slate-500 ml-1">bps</span>
      </span>
      {delta5d !== null && (
        <span className={`text-sm ${deltaColor}`}>{arrow} {Math.abs(delta5d).toFixed(1)} (5d)</span>
      )}
    </div>
  );
}

function RecessionGauge({ prob }: { prob: number | null }) {
  if (prob === null) return <div className="text-slate-500 text-sm">Recession prob: —</div>;
  const pct = (prob * 100).toFixed(0);
  const color = prob < 0.25 ? 'text-emerald-400' : prob < 0.50 ? 'text-amber-400' : 'text-red-400';
  return (
    <div className="text-sm">
      <span className="text-slate-400">NY Fed recession prob: </span>
      <span className={`font-bold ${color}`}>{pct}%</span>
    </div>
  );
}

function AlertRow({ a }: { a: YieldCurveAlert }) {
  return (
    <div className="py-2 border-b border-slate-800 last:border-b-0">
      <div className="flex items-baseline justify-between gap-2">
        <span className={`text-xs font-semibold ${PRIORITY_COLOR[a.priority] ?? ''}`}>[{a.priority}]</span>
        <span className="text-xs text-slate-500">{new Date(a.triggered_at).toLocaleString()}</span>
      </div>
      <div className="text-sm text-slate-300 mt-1">{a.rule_name}</div>
      <pre className="text-xs text-slate-400 mt-1 whitespace-pre-wrap font-mono">{a.message}</pre>
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
    <section className="rounded-lg border border-slate-800 bg-slate-900/50 p-4">
      <header className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-slate-200">US Treasury Yield Curve</h2>
        {snap?.stale && (
          <span className="text-xs text-amber-400">stale ({snap.days_since_update}d)</span>
        )}
      </header>

      {isLoading && <div className="text-sm text-slate-500">Loading…</div>}
      {isError && <div className="text-sm text-red-400">Failed to load curve data.</div>}

      {snap && (
        <div className="space-y-4">
          {/* Curve shape chart */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-slate-400">Curve shape</span>
              <span className={`text-xs px-2 py-0.5 rounded ${SHAPE_BADGE_COLOR[snap.shape] ?? ''}`}>
                {snap.shape} · {snap.shape_trend}
              </span>
            </div>
            <CurveChart curve={snap.curve} />
            <div className="flex justify-between text-[10px] text-slate-500 mt-1">
              {TENOR_ORDER.map((t) => <span key={t}>{t}</span>)}
            </div>
          </div>

          {/* 2s10s spread big number */}
          <div>
            <div className="text-xs text-slate-400 mb-1">2s/10s spread</div>
            <SpreadBigNumber
              value={snap.spreads['2s10s'] ?? null}
              delta5d={snap.deltas.spread_2s10s_delta_5d}
            />
          </div>

          <RecessionGauge prob={snap.recession_prob_nyfed} />

          {/* Recent alerts */}
          <div>
            <div className="text-xs text-slate-400 mb-2">Recent alerts (30d)</div>
            {alerts.length === 0 ? (
              <div className="text-xs text-slate-500">No alerts in window.</div>
            ) : (
              <div className="max-h-48 overflow-y-auto">
                {alerts.slice(0, 10).map((a, i) => <AlertRow key={i} a={a} />)}
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

export default YieldCurvePanel;