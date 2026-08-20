'use client';

/**
 * Single report detail page.
 *
 * Shows full params + metrics + an equity curve PNG (if available).
 */

import { use } from 'react';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { ArrowLeft, BarChart3 } from 'lucide-react';
import { StatTile } from '@/components/dashboard/StatTile';
import { marketPulseAPI } from '@/lib/api';

export default function ReportDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data, isLoading, isError } = useQuery({
    queryKey: ['research', 'report', id],
    queryFn: () => marketPulseAPI.getResearchReport(id),
    refetchOnWindowFocus: false,
  });

  if (isLoading) {
    return <div className="text-center text-ink-muted py-12">Loading report...</div>;
  }
  if (isError || !data) {
    return <div className="text-center text-neg py-12">Report not found.</div>;
  }

  const params_dict = data.params ?? {};
  const metrics = data.metrics ?? {};
  const hasEquityChart = data.kind === 'backtest';

  return (
    <div className="max-w-6xl mx-auto px-2.5 py-2.5 space-y-2.5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <Link
            href="/research/reports"
            className="btn"
          >
            <ArrowLeft className="w-4 h-4" /> All reports
          </Link>
        </div>
        <div className="text-[11px] font-mono text-ink-muted">{data.id}</div>
      </div>

      <div className="panel p-2.5">
        <div className="flex items-center gap-2 mb-1">
          <span className="border border-teal rounded-[2px] px-1.5 h-5 text-[11px] font-mono inline-flex items-center text-teal">
            {data.kind}
          </span>
          {data.created_at && (
            <span className="text-[11px] text-ink-muted font-mono">
              {new Date(data.created_at).toLocaleString()}
            </span>
          )}
        </div>
        <h1 className="text-[15px] leading-tight font-semibold text-ink">
          {params_dict.strategy
            ? `Backtest: ${params_dict.strategy}${params_dict.scaling ? ` + ${params_dict.scaling}` : ''}`
            : params_dict.method
            ? `Monte Carlo: ${params_dict.method}`
            : 'Research Report'}
        </h1>
        {params_dict.start && params_dict.end && (
          <p className="text-[12.5px] text-ink-secondary font-mono">
            {params_dict.start} → {params_dict.end}
          </p>
        )}
      </div>

      {/* Equity chart (backtests only) */}
      {hasEquityChart && (
        <>
          <div className="panel p-2.5">
            <h2 className="panel-title mb-2 flex items-center gap-2">
              <BarChart3 className="w-3.5 h-3.5" /> Equity Curve
            </h2>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={marketPulseAPI.getResearchReportImageUrl(id, 'equity_png')}
              alt="Equity curve"
              className="w-full bg-canvas"
            />
          </div>
          <div className="panel p-2.5">
            <h2 className="panel-title mb-2 flex items-center gap-2">
              <BarChart3 className="w-3.5 h-3.5" /> Drawdown
            </h2>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={marketPulseAPI.getResearchReportImageUrl(id, 'drawdown_png')}
              alt="Drawdown"
              className="w-full bg-canvas"
            />
          </div>
        </>
      )}

      {/* Metrics grid */}
      <div className="panel p-2.5">
        <h2 className="panel-title mb-2.5">Metrics</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
          {Object.entries(metrics).map(([k, v]) => (
            <StatTile
              key={k}
              label={k.replace(/_/g, ' ')}
              value={typeof v === 'number' ? (Math.abs(v) < 0.01 && v !== 0 ? v.toExponential(2) : v.toFixed(4)) : String(v)}
              mono
            />
          ))}
        </div>
      </div>

      {/* Params */}
      <div className="panel p-2.5">
        <h2 className="panel-title mb-2.5">Parameters</h2>
        <pre className="font-mono text-[11.5px] bg-canvas border border-line-subtle p-2 rounded-[2px] text-ink overflow-x-auto">
          {JSON.stringify(params_dict, null, 2)}
        </pre>
      </div>
    </div>
  );
}
