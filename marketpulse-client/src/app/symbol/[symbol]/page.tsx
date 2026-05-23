'use client';

import { useParams } from 'next/navigation';
import Link from 'next/link';
import { useSymbolDetail, use52WRange, useSymbolStats } from '@/hooks/useSymbolDetail';
import { useTrendAnalysis } from '@/hooks/useMarketData';
import { FiftyTwoWeekBar } from '@/components/FiftyTwoWeekBar';
import { PriceCell } from '@/components/PriceCell';
import { ArrowLeft, BarChart3, TrendingUp, TrendingDown, Activity, AlertTriangle } from 'lucide-react';

function formatMarketCap(v: number): string {
  if (v >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(2)}M`;
  return `$${v.toLocaleString()}`;
}

function formatVolume(v: number): string {
  if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
  return v.toLocaleString();
}

function StatCard({ label, value }: { label: string; value: string | undefined }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
      <p className="text-xs text-gray-500 uppercase tracking-wider">{label}</p>
      <p className="text-lg font-semibold text-white mt-1">{value ?? '—'}</p>
    </div>
  );
}

export default function SymbolDetailPage() {
  const params = useParams();
  const symbol = params.symbol as string;

  const { data: detail, isLoading: detailLoading, isError: detailError, error: detailErrorObj, refetch: refetchDetail } = useSymbolDetail(symbol);
  const { data: stats, isLoading: statsLoading, isError: statsError, error: statsErrorObj, refetch: refetchStats } = useSymbolStats(symbol);
  const { data: range52w, isLoading: rangeLoading, isError: rangeError, error: rangeErrorObj, refetch: refetchRange } = use52WRange(symbol);
  const { data: trendData } = useTrendAnalysis(symbol);

  const isLoading = detailLoading || statsLoading || rangeLoading;
  const hasError = detailError || statsError || rangeError;

  if (isLoading) {
    return (
      <div className="min-h-screen bg-black text-white p-4 md:p-6">
        <div className="max-w-5xl mx-auto space-y-6">
          <div className="h-24 bg-gray-900 rounded-xl animate-pulse" />
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="h-20 bg-gray-900 rounded-xl animate-pulse" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (hasError) {
    return (
      <div className="min-h-screen bg-black text-white p-4 md:p-6">
        <div className="max-w-5xl mx-auto flex flex-col items-center justify-center h-[60vh] text-gray-400">
          <AlertTriangle className="w-12 h-12 mb-4 text-red-400" />
          <p className="text-lg mb-2">Failed to load symbol data</p>
          <p className="text-sm text-gray-500 mb-4">{String(detailErrorObj || statsErrorObj || rangeErrorObj || 'Unknown error')}</p>
          <button
            onClick={() => { refetchDetail?.(); refetchStats?.(); refetchRange?.(); }}
            className="px-4 py-2 bg-blue-500/20 text-blue-400 rounded-lg hover:bg-blue-500/30 transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  const currentPrice = range52w?.current_price;
  const change = detail?.change;
  const changePct = detail?.change_pct;

  return (
    <div className="min-h-screen bg-black text-white p-4 md:p-6">
      <div className="max-w-5xl mx-auto space-y-6">
        <div className="flex items-start justify-between">
          <div className="flex items-start gap-3">
            <Link
              href="/"
              className="p-2 rounded-lg bg-gray-900 hover:bg-gray-800 transition-colors mt-1"
            >
              <ArrowLeft className="w-4 h-4" />
            </Link>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-bold">{symbol}</h1>
                {change !== undefined && changePct !== undefined && (
                  change >= 0
                    ? <TrendingUp className="w-5 h-5 text-emerald-400" />
                    : <TrendingDown className="w-5 h-5 text-red-400" />
                )}
              </div>
              {detail?.name && (
                <p className="text-sm text-gray-400">{detail.name}</p>
              )}
            </div>
          </div>

          {currentPrice !== undefined && (
            <PriceCell price={currentPrice} change={change} changePct={changePct} />
          )}
        </div>

        {range52w && (
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-3">
            <h3 className="text-sm font-medium text-gray-400">52-Week Range</h3>
            <FiftyTwoWeekBar
              currentPrice={range52w.current_price}
              high52w={range52w.high_52w}
              low52w={range52w.low_52w}
              showLabels
            />
            <div className="flex justify-between text-xs text-gray-500">
              <span>Low: ${range52w.low_52w.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
              <span>High: ${range52w.high_52w.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
            </div>
          </div>
        )}

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatCard label="Market Cap" value={detail?.market_cap != null ? formatMarketCap(detail.market_cap) : undefined} />
          <StatCard label="P/E Ratio" value={detail?.pe_ratio != null ? detail.pe_ratio.toFixed(2) : undefined} />
          <StatCard label="Volume" value={detail?.volume != null ? formatVolume(detail.volume) : undefined} />
          <StatCard label="Avg Volume (20d)" value={stats?.avg_volume_20d != null ? formatVolume(stats.avg_volume_20d) : undefined} />
          <StatCard label="52W High" value={stats?.high_52w != null ? `$${stats.high_52w.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : undefined} />
          <StatCard label="52W Low" value={stats?.low_52w != null ? `$${stats.low_52w.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : undefined} />
          <StatCard label="From 52W High" value={stats?.pct_from_52w_high != null ? `${stats.pct_from_52w_high.toFixed(2)}%` : undefined} />
          <StatCard label="ATR (14)" value={stats?.atr_14 != null ? stats.atr_14.toFixed(2) : undefined} />
        </div>

        {range52w && (
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-4">
            <h3 className="text-sm font-medium text-gray-400 flex items-center gap-2">
              <Activity className="w-4 h-4" />
              52-Week Analysis
            </h3>
            <div className="space-y-2 text-sm">
              <p className="text-gray-300">
                Trading{' '}
                <span className="text-white font-medium">{Math.abs(range52w.pct_from_high).toFixed(2)}%</span>{' '}
                below 52-week high of{' '}
                <span className="text-white font-medium">
                  ${range52w.high_52w.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </span>
              </p>
              <p className="text-gray-300">
                Trading{' '}
                <span className="text-white font-medium">{range52w.pct_from_low.toFixed(2)}%</span>{' '}
                above 52-week low of{' '}
                <span className="text-white font-medium">
                  ${range52w.low_52w.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </span>
              </p>
            </div>
          </div>
        )}

      {trendData && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <h3 className="text-sm font-medium text-gray-300 mb-3 flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-blue-400" />
            Trend Analysis
          </h3>

          {trendData.timeframe_consensus && (
            <div className="mb-3">
              <div className="text-xs text-gray-500 mb-1">Timeframe Consensus</div>
              <div className="flex items-center gap-3 text-sm">
                {['bullish', 'bearish', 'neutral'].map((dir) => {
                  const count = trendData.timeframe_consensus[`${dir}_count`] ?? 0;
                  return (
                    <span key={dir} className={dir === 'bullish' ? 'text-emerald-400' : dir === 'bearish' ? 'text-red-400' : 'text-gray-400'}>
                      {count} {dir}
                    </span>
                  );
                })}
              </div>
            </div>
          )}

          {trendData.timeframes && (
            <div className="space-y-2 mb-3">
              {Object.entries(trendData.timeframes).map(([tf, data]: [string, any]) => (
                <div key={tf} className="flex items-center justify-between text-xs">
                  <span className="text-gray-500 w-12">{tf}</span>
                  <div className="flex-1 mx-2">
                    <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${data?.direction?.includes('BULL') ? 'bg-emerald-500' : data?.direction?.includes('BEAR') ? 'bg-red-500' : 'bg-gray-600'}`}
                        style={{ width: `${Math.min((data?.strength ?? 0) * 100, 100)}%` }}
                      />
                    </div>
                  </div>
                  <span className={`w-16 text-right ${data?.direction?.includes('BULL') ? 'text-emerald-400' : data?.direction?.includes('BEAR') ? 'text-red-400' : 'text-gray-400'}`}>
                    {data?.direction?.replace('LY_', ' ') ?? '--'} ({((data?.strength ?? 0) * 100).toFixed(0)}%)
                  </span>
                </div>
              ))}
            </div>
          )}

          {trendData.key_levels && (
            <div className="grid grid-cols-2 gap-2 text-xs">
              {trendData.key_levels.support && (
                <div className="bg-emerald-500/5 rounded p-2">
                  <div className="text-gray-500">Support</div>
                  <div className="text-emerald-400 font-medium">{trendData.key_levels.support}</div>
                </div>
              )}
              {trendData.key_levels.resistance && (
                <div className="bg-red-500/5 rounded p-2">
                  <div className="text-gray-500">Resistance</div>
                  <div className="text-red-400 font-medium">{trendData.key_levels.resistance}</div>
                </div>
              )}
            </div>
          )}

          {trendData.signals && trendData.signals.length > 0 && (
            <div className="mt-3 pt-3 border-t border-gray-800">
              <div className="text-xs text-gray-500 mb-2">Active Signals</div>
              <div className="space-y-1">
                {trendData.signals.slice(0, 5).map((s: any, i: number) => (
                  <div key={i} className="flex items-center gap-2 text-xs">
                    <span className={s.direction === 'BULLISH' ? 'text-emerald-400' : s.direction === 'BEARISH' ? 'text-red-400' : 'text-gray-400'}>
                      {s.direction === 'BULLISH' ? '▲' : s.direction === 'BEARISH' ? '▼' : '◆'}
                    </span>
                    <span className="text-gray-400">{s.type.replace(/_/g, ' ')}</span>
                    {s.timeframe && <span className="text-gray-600 ml-auto">{s.timeframe}</span>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

        <div className="flex items-center justify-between">
          <p className="text-xs text-gray-600">
            Source: Yahoo Finance{stats?.date ? ` · Last updated: ${stats.date}` : ''}
          </p>
          <Link
            href={`/chart/${encodeURIComponent(symbol)}`}
            className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
          >
            <BarChart3 className="w-4 h-4" />
            Open Chart →
          </Link>
        </div>
      </div>
    </div>
  );
}
