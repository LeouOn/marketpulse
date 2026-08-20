'use client';

/**
 * Saved reports browser (B10).
 *
 * Lists every backtest and Monte Carlo saved to the research backend.
 */

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { FileText, RefreshCw } from 'lucide-react';
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

  const kinds = [
    { key: null as string | null, label: 'All' },
    { key: 'backtest', label: 'Backtest' },
    { key: 'montecarlo', label: 'Monte Carlo' },
    { key: 'compare', label: 'Compare' },
  ];

  return (
    <div className="max-w-7xl mx-auto px-2.5 py-2.5">
      <div className="mb-2.5 flex items-center justify-between gap-2.5 flex-wrap">
        <div className="flex items-center gap-2.5">
          <FileText className="w-5 h-5 text-teal" />
          <div>
            <h1 className="text-[15px] leading-tight font-semibold text-ink">Research Reports</h1>
            <p className="text-[12.5px] text-ink-secondary">
              Every backtest and Monte Carlo run, persisted to disk + DB.
            </p>
          </div>
        </div>
        <button
          onClick={() => refetch()}
          className="btn"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      <div className="flex items-center gap-3 border-b border-line-subtle mb-2.5">
        {kinds.map((k) => (
          <button
            key={k.label}
            onClick={() => setKindFilter(k.key)}
            className={`pb-1.5 text-[11px] uppercase tracking-[0.08em] font-mono ${
              kindFilter === k.key ? 'text-teal border-b-2 border-teal' : 'text-ink-muted hover:text-ink'
            }`}
          >
            {k.label}
          </button>
        ))}
      </div>

      {isLoading && (
        <div className="text-center text-ink-muted py-12">Loading reports...</div>
      )}
      {isError && (
        <div className="text-center text-neg py-12">
          Failed to load reports. Make sure the backend is running.
        </div>
      )}
      {!isLoading && !isError && filtered.length === 0 && (
        <div className="text-center text-ink-muted py-12">
          <p>No reports yet.</p>
          <p className="text-[11px] mt-1">Run a backtest in the <Link href="/research" className="text-teal">Research</Link> page to create one.</p>
        </div>
      )}

      {!isLoading && !isError && filtered.length > 0 && (
        <div className="panel overflow-hidden">
          <table className="data-table">
            <thead>
              <tr>
                <th>Kind</th>
                <th>Id</th>
                <th>Params</th>
                <th className="num">Created</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <ReportRow key={r.id} report={r} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function ReportRow({ report }: { report: Report }) {
  const router = useRouter();
  const href = `/research/reports/${report.id}`;
  const m = report.metrics_summary ?? {};
  const paramPreview = report.params
    ? Object.entries(report.params)
        .slice(0, 4)
        .map(([k, v]) => `${k}=${typeof v === 'string' ? v : JSON.stringify(v)}`)
        .join('  ·  ')
    : '';
  return (
    <tr
      className="cursor-pointer"
      onClick={() => router.push(href)}
    >
      <td>
        <Link href={href} className="text-teal hover:text-ink font-mono text-[11px] uppercase tracking-[0.08em]">
          {report.kind}
        </Link>
      </td>
      <td className="font-mono text-ink-muted">{report.id}</td>
      <td className="text-ink-secondary truncate max-w-md">
        {paramPreview}
        {Object.keys(m).length > 0 && (
          <span className="ml-2 font-mono text-[11px] text-teal">
            {Object.entries(m)
              .slice(0, 3)
              .map(([k, v]) => `${k} ${typeof v === 'number' ? (v < 0.01 && v !== 0 ? v.toExponential(2) : v.toFixed(2)) : String(v)}`)
              .join(' · ')}
          </span>
        )}
      </td>
      <td className="num font-mono text-ink-muted">
        {report.created_at ? new Date(report.created_at).toLocaleString() : ''}
      </td>
    </tr>
  );
}
