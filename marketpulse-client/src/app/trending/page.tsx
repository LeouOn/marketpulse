'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useScreener } from '@/hooks/useScreenerData';
import { FiftyTwoWeekBar } from '@/components/FiftyTwoWeekBar';
import { Flame, TrendingUp, TrendingDown, BarChart3, RefreshCw } from 'lucide-react';
import { formatVolume } from '@/lib/format';
import type { ScreenerResult } from '@/types/market';

type ScreenerTab = 'gainers' | 'losers' | 'most_active';

const tabs: { key: ScreenerTab; label: string; icon: typeof TrendingUp }[] = [
  { key: 'gainers', label: 'Gainers', icon: TrendingUp },
  { key: 'losers', label: 'Losers', icon: TrendingDown },
  { key: 'most_active', label: 'Most Active', icon: BarChart3 },
];

const tabStyles: Record<ScreenerTab, string> = {
  gainers: 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30',
  losers: 'bg-red-500/20 text-red-400 border border-red-500/30',
  most_active: 'bg-blue-500/20 text-blue-400 border border-blue-500/30',
};

function RankBadge({ rank }: { rank: number }) {
  if (rank === 1) return <span className="font-bold text-yellow-400">#{rank}</span>;
  if (rank === 2) return <span className="font-bold text-gray-300">#{rank}</span>;
  if (rank === 3) return <span className="font-bold text-amber-700">#{rank}</span>;
  return <span className="text-gray-400">#{rank}</span>;
}

function SkeletonRows() {
  return (
    <>
      {Array.from({ length: 8 }).map((_, i) => (
        <tr key={i}>
          {Array.from({ length: 7 }).map((__, j) => (
            <td key={j} className="px-4 py-3 border-b border-gray-800">
              <div className="h-4 bg-gray-800 rounded animate-pulse" />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

export default function TrendingPage() {
  const [activeTab, setActiveTab] = useState<ScreenerTab>('gainers');
  const { data, isLoading, isError, dataUpdatedAt } = useScreener(activeTab);

  const results: ScreenerResult[] = data ?? [];

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-1">
          <Flame className="w-7 h-7 text-orange-400" />
          <h1 className="text-2xl font-bold text-white">Trending Stocks</h1>
        </div>
        <p className="text-gray-400 text-sm ml-10">
          Real-time market movers from Yahoo Finance
        </p>
      </div>

      <div className="flex gap-2 mb-6">
        {tabs.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-2 ${
              activeTab === key
                ? tabStyles[key]
                : 'bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-gray-300'
            }`}
          >
            <Icon className="w-4 h-4" />
            {label}
          </button>
        ))}
      </div>

      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="bg-gray-800">
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">
                #
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">
                Symbol
              </th>
              <th className="px-4 py-3 text-right text-xs font-semibold text-gray-400 uppercase tracking-wider">
                Price
              </th>
              <th className="px-4 py-3 text-right text-xs font-semibold text-gray-400 uppercase tracking-wider">
                Change %
              </th>
              <th className="px-4 py-3 text-right text-xs font-semibold text-gray-400 uppercase tracking-wider">
                Volume
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">
                52W Range
              </th>
              <th className="px-4 py-3 text-right text-xs font-semibold text-gray-400 uppercase tracking-wider">
                Action
              </th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <SkeletonRows />
            ) : isError || results.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-12 text-center">
                  <RefreshCw className="w-8 h-8 text-gray-600 mx-auto mb-3" />
                  <p className="text-gray-400">
                    No screener data available — market may be closed or data is loading
                  </p>
                </td>
              </tr>
            ) : (
              results.map((item, idx) => {
                const changeColor =
                  item.change_pct >= 0 ? 'text-emerald-400' : 'text-red-400';
                const sign = item.change_pct >= 0 ? '+' : '';

                return (
                  <tr
                    key={item.symbol}
                    className="border-b border-gray-800 hover:bg-gray-800/50"
                  >
                    <td className="px-4 py-3">
                      <RankBadge rank={item.rank ?? idx + 1} />
                    </td>
                    <td className="px-4 py-3">
                      <div className="font-semibold text-white">{item.symbol}</div>
                      {item.name && (
                        <div className="text-xs text-gray-500 truncate max-w-[180px]">
                          {item.name}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right text-white font-mono">
                      ${item.price.toFixed(2)}
                    </td>
                    <td className={`px-4 py-3 text-right font-mono font-medium ${changeColor}`}>
                      {sign}
                      {item.change_pct.toFixed(2)}%
                    </td>
                    <td className="px-4 py-3 text-right text-gray-300 font-mono">
                      {formatVolume(item.volume)}
                    </td>
                    <td className="px-4 py-3">
                      {item.high_52w && item.low_52w ? (
                        <FiftyTwoWeekBar
                          currentPrice={item.price}
                          high52w={item.high_52w}
                          low52w={item.low_52w}
                        />
                      ) : (
                        <span className="text-gray-600 text-xs">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Link
                        href={`/chart/${item.symbol}`}
                        className="text-blue-400 hover:text-blue-300 text-sm font-medium"
                      >
                        View Chart
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
        <div className="mt-3 text-xs text-gray-500 text-right">
          Last updated:{' '}
          {new Date(dataUpdatedAt).toLocaleTimeString()}
        </div>
      ) : null}
    </div>
  );
}
