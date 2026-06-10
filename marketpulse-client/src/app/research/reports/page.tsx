'use client';

/**
 * Saved reports browser (B10).
 *
 * Lists every backtest and Monte Carlo saved to the research backend.
 */

import { useState } from 'react';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { FileText, BarChart3, FlaskConical, RefreshCw } from 'lucide-react';
import { marketPulseAPI } from '@/lib/api';

interface Report {
  id: string;
  kind: string;
  created_at?: string;
  params?: Record<string, any>;
  metrics_summary?: Record<string, any>;
}

export default function ReportsPage() {
  const { data, isLoading, isError, refetch, dataUpdatedAt } = useQuery({
    queryKey: ['research', 'reports'],
    queryFn: () => marketPulseAPI.listResearchReports({ limit: 100 }),
    refetchOnWindowFocus: false,
  });

  const [kindFilter, setKindFilter] = useState<string | null>(null);

  const reports: Report[] = data?.reports ?? [];
  const filtered = kindFilter ? reports.filter((r) => r.kind === kindFilter) : reports;

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <FileText className="w-7 h-7 text-emerald-400" />
          <div>
            <h1 className="text-2xl font-bold text-white">Research Reports</h1>
            <p className="text-sm text-gray-400">
              Every backtest and Monte Carlo run, persisted to disk + DB.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={kindFilter ?? ''}
            onChange={(e) => setKindFilter(e.target.value || null)}
            className="bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-white"
          >
            <option value="">All</option>
            <option value="backtest">Backtest</option>
            <option value="montecarlo">Monte Carlo</option>
            <option value="compare">Compare</option>
          </select>
          <button
            onClick={() => refetch()}
            className="bg-gray-800 hover:bg-gray-700 text-gray-200 px-3 py-1.5 rounded text-sm flex items-center gap-1.5"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
        </div>
      </div>

      {isLoading && (
        <div className="text-center text-gray-500 py-12">Loading reports...</div>
      )}
      {isError && (
        <div className="text-center text-red-400 py-12">
          Failed to load reports. Make sure the backend is running.
        </div>
      )}
      {!isLoading && !isError && filtered.length === 0 && (
        <div className="text-center text-gray-500 py-12">
          <p>No reports yet.</p>
          <p className="text-xs mt-1">Run a backtest in the <Link href="/research" className="text-emerald-400">Research</Link> page to create one.</p>
        </div>
      )}

      <div className="space-y-3">
        {filtered.map((r) => (
          <ReportRow key={r.id} report={r} />
        ))}
      </div>
    </div>
  );
}

function ReportRow({ report }: { report: Report }) {
  const Icon = report.kind === 'backtest' ? BarChart3 : report.kind === 'montecarlo' ? FlaskConical : FileText;
  const m = report.metrics_summary ?? {};
  return (
    <Link
      href={`/research/reports/${report.id}`}
      className="block bg-gray-900 border border-gray-800 hover:border-emerald-500/50 rounded-lg p-4 transition-colors"
    >
      <div className="flex items-start gap-3">
        <Icon className="w-5 h-5 text-emerald-400 mt-0.5 shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 text-sm">
            <span className="font-mono bg-emerald-500/10 text-emerald-400 px-2 py-0.5 rounded">
              {report.kind}
            </span>
            <span className="text-gray-500 text-xs font-mono truncate">{report.id}</span>
            {report.created_at && (
              <span className="ml-auto text-xs text-gray-500">
                {new Date(report.created_at).toLocaleString()}
              </span>
            )}
          </div>
          {report.params && Object.keys(report.params).length > 0 && (
            <div className="text-xs text-gray-400 mt-1 truncate">
              {Object.entries(report.params)
                .slice(0, 4)
                .map(([k, v]) => `${k}=${typeof v === 'string' ? v : JSON.stringify(v)}`)
                .join('  ·  ')}
            </div>
          )}
          {Object.keys(m).length > 0 && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-2">
              {Object.entries(m).map(([k, v]) => (
                <div key={k} className="bg-gray-800/60 rounded px-2 py-1">
                  <div className="text-[10px] uppercase text-gray-500 tracking-wide">{k.replace(/_/g, ' ')}</div>
                  <div className="text-sm text-emerald-300 font-mono">
                    {typeof v === 'number' ? (v < 0.01 && v !== 0 ? v.toExponential(2) : v.toFixed(2)) : String(v)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </Link>
  );
}
