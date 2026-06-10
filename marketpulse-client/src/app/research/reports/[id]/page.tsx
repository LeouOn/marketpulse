'use client';

/**
 * Single report detail page.
 *
 * Shows full params + metrics + an equity curve PNG (if available).
 */

import { use } from 'react';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { ArrowLeft, BarChart3, Download } from 'lucide-react';
import { marketPulseAPI } from '@/lib/api';

export default function ReportDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data, isLoading, isError } = useQuery({
    queryKey: ['research', 'report', id],
    queryFn: () => marketPulseAPI.getResearchReport(id),
    refetchOnWindowFocus: false,
  });

  if (isLoading) {
    return <div className="text-center text-gray-500 py-12">Loading report...</div>;
  }
  if (isError || !data) {
    return <div className="text-center text-red-400 py-12">Report not found.</div>;
  }

  const params_dict = data.params ?? {};
  const metrics = data.metrics ?? {};
  const hasEquityChart = data.kind === 'backtest';

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link
            href="/research/reports"
            className="text-gray-400 hover:text-emerald-400 flex items-center gap-1 text-sm"
          >
            <ArrowLeft className="w-4 h-4" /> All reports
          </Link>
        </div>
        <div className="text-xs font-mono text-gray-500">{data.id}</div>
      </div>

      <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
        <div className="flex items-center gap-2 mb-1">
          <span className="font-mono bg-emerald-500/10 text-emerald-400 px-2 py-0.5 rounded text-sm">
            {data.kind}
          </span>
          {data.created_at && (
            <span className="text-xs text-gray-500">
              {new Date(data.created_at).toLocaleString()}
            </span>
          )}
        </div>
        <h1 className="text-xl font-bold text-white">
          {params_dict.strategy
            ? `Backtest: ${params_dict.strategy}${params_dict.scaling ? ` + ${params_dict.scaling}` : ''}`
            : params_dict.method
            ? `Monte Carlo: ${params_dict.method}`
            : 'Research Report'}
        </h1>
        {params_dict.start && params_dict.end && (
          <p className="text-sm text-gray-400">
            {params_dict.start} → {params_dict.end}
          </p>
        )}
      </div>

      {/* Equity chart (backtests only) */}
      {hasEquityChart && (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <h2 className="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2">
            <BarChart3 className="w-4 h-4" /> Equity Curve
          </h2>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={marketPulseAPI.getResearchReportImageUrl(id, 'equity_png')}
            alt="Equity curve"
            className="w-full bg-gray-950 rounded"
          />
          <h2 className="text-sm font-semibold text-gray-300 mt-4 mb-3 flex items-center gap-2">
            <BarChart3 className="w-4 h-4" /> Drawdown
          </h2>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={marketPulseAPI.getResearchReportImageUrl(id, 'drawdown_png')}
            alt="Drawdown"
            className="w-full bg-gray-950 rounded"
          />
        </div>
      )}

      {/* Metrics grid */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
        <h2 className="text-sm font-semibold text-gray-300 mb-3">Metrics</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {Object.entries(metrics).map(([k, v]) => (
            <div key={k} className="bg-gray-800/60 rounded px-3 py-2">
              <div className="text-[10px] uppercase text-gray-500 tracking-wide">{k.replace(/_/g, ' ')}</div>
              <div className="text-sm text-emerald-300 font-mono">
                {typeof v === 'number' ? (Math.abs(v) < 0.01 && v !== 0 ? v.toExponential(2) : v.toFixed(4)) : String(v)}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Params */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
        <h2 className="text-sm font-semibold text-gray-300 mb-3">Parameters</h2>
        <pre className="text-xs text-gray-300 overflow-x-auto">
          {JSON.stringify(params_dict, null, 2)}
        </pre>
      </div>
    </div>
  );
}
