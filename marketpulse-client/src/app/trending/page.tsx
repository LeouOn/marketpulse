'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useScreener } from '@/hooks/useScreenerData';
import { useRowNav } from '@/hooks/useRowNav';
import { FiftyTwoWeekBar } from '@/components/FiftyTwoWeekBar';
import { Flame, RefreshCw } from 'lucide-react';
import { formatVolume } from '@/lib/format';
import type { ScreenerResult } from '@/types/market';

type ScreenerTab = 'gainers' | 'losers' | 'most_active';

const tabs: { key: ScreenerTab; label: string }[] = [
  { key: 'gainers', label: 'Gainers' },
  { key: 'losers', label: 'Losers' },
  { key: 'most_active', label: 'Most Active' },
];

function RankBadge({ rank }: { rank: number }) {
  let cls = 'font-mono text-ink-muted';
  if (rank === 1) cls = 'font-mono text-warn';
  else if (rank === 2) cls = 'font-mono text-ink-secondary';
  else if (rank === 3) cls = 'font-mono text-warn';
  return <span className={cls}>#{rank}</span>;
}

function SkeletonRows() {
  return (
    <>
      {Array.from({ length: 8 }).map((_, i) => (
        <tr key={i}>
          {Array.from({ length: 7 }).map((__, j) => (
            <td key={j} className="px-2 py-[3px]">
              <div className="h-3 bg-surface-raised animate-pulse" />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

export default function TrendingPage() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<ScreenerTab>('gainers');
  const { data, isLoading, isError, dataUpdatedAt } = useScreener(activeTab);
  const results: ScreenerResult[] = data ?? [];

  const { focusedIndex, setFocusedIndex, handleKeyDown } = useRowNav(
    results.length,
    {
      onEnter: (i) => {
        const row = results[i];
        if (row) router.push(`/chart/${row.symbol}`);
      },
    }
  );

  const rowRefs = useRef<(HTMLTableRowElement | null)[]>([]);

  // Keep refs array in sync with results length so out-of-range indices are trimmed
  useEffect(() => {
    rowRefs.current.length = results.length;
  }, [results.length]);

  // Scroll focused row into view on focusedIndex change
  useEffect(() => {
    const row = rowRefs.current[focusedIndex];
    if (row) row.scrollIntoView({ block: 'nearest' });
  }, [focusedIndex]);

  const handleTabChange = useCallback(
    (key: ScreenerTab) => {
      setActiveTab(key);
      setFocusedIndex(0);
    },
    [setFocusedIndex]
  );

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-1">
          <Flame className="w-7 h-7 text-warn" />
          <h1 className="text-2xl font-bold text-ink">Trending Stocks</h1>
        </div>
        <p className="text-ink-secondary text-sm ml-10">
          Real-time market movers from Yahoo Finance
        </p>
      </div>

      <div className="flex items-end justify-between mb-2.5 border-b border-line-subtle">
        <div className="flex gap-4">
          {tabs.map(({ key, label }) => {
            const isActive = activeTab === key;
            return (
              <button
                key={key}
                onClick={() => handleTabChange(key)}
                className={`px-1 pb-1.5 text-[11px] uppercase tracking-[0.08em] font-mono transition-colors ${
                  isActive
                    ? 'text-teal border-b-2 border-teal'
                    : 'text-ink-muted hover:text-ink'
                }`}
              >
                {label}
              </button>
            );
          })}
        </div>
        <div className="pb-1.5 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.08em] text-ink-muted">
          <span className="kbd">j</span>
          <span className="kbd">k</span>
          <span className="ml-1">navigate</span>
          <span className="kbd ml-1">↵</span>
          <span className="ml-1">open</span>
        </div>
      </div>

      <div
        className="panel overflow-hidden max-h-[600px] overflow-y-auto focus:outline focus:outline-1 focus:outline-line-focus"
        tabIndex={0}
        onKeyDown={handleKeyDown}
      >
        <table className="data-table">
          <thead>
            <tr>
              <th className="sticky top-0 bg-surface">#</th>
              <th className="sticky top-0 bg-surface">Symbol</th>
              <th className="num sticky top-0 bg-surface">Price</th>
              <th className="num sticky top-0 bg-surface">Change %</th>
              <th className="num sticky top-0 bg-surface">Volume</th>
              <th className="num sticky top-0 bg-surface">52W Range</th>
              <th className="num sticky top-0 bg-surface">Action</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <SkeletonRows />
            ) : isError || results.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-2 py-12 text-center">
                  <RefreshCw className="w-8 h-8 text-ink-muted mx-auto mb-3" />
                  <p className="text-ink-secondary">
                    No screener data available — market may be closed or data is loading
                  </p>
                </td>
              </tr>
            ) : (
              results.map((item, idx) => {
                const changeColor =
                  item.change_pct >= 0 ? 'text-pos' : 'text-neg';
                const sign = item.change_pct >= 0 ? '+' : '';
                const isFocused = idx === focusedIndex;

                return (
                  <tr
                    key={item.symbol}
                    ref={(el) => {
                      rowRefs.current[idx] = el;
                    }}
                    className={isFocused ? 'row-focused' : undefined}
                  >
                    <td>
                      <RankBadge rank={item.rank ?? idx + 1} />
                    </td>
                    <td>
                      <div className="font-mono text-ink">{item.symbol}</div>
                      {item.name && (
                        <div className="text-[11px] text-ink-muted truncate max-w-[180px]">
                          {item.name}
                        </div>
                      )}
                    </td>
                    <td className="num">${item.price.toFixed(2)}</td>
                    <td className={`num ${changeColor}`}>
                      {sign}
                      {item.change_pct.toFixed(2)}%
                    </td>
                    <td className="num">{formatVolume(item.volume)}</td>
                    <td className="num">
                      {item.high_52w && item.low_52w ? (
                        <FiftyTwoWeekBar
                          currentPrice={item.price}
                          high52w={item.high_52w}
                          low52w={item.low_52w}
                        />
                      ) : (
                        <span className="text-ink-muted text-[11px]">—</span>
                      )}
                    </td>
                    <td className="num">
                      <Link
                        href={`/chart/${item.symbol}`}
                        className="text-sel hover:text-ink text-[11px] uppercase tracking-[0.08em] font-mono"
                      >
                        Chart →
                      </Link>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {dataUpdatedAt ? (
        <div className="mt-2 text-[11px] text-ink-muted text-right font-mono">
          Last updated:{' '}
          {new Date(dataUpdatedAt).toLocaleTimeString()}
        </div>
      ) : null}
    </div>
  );
}
