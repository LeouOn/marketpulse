'use client';

import { useParams } from 'next/navigation';
import Link from 'next/link';
import { useSymbolDetail, use52WRange, useSymbolStats } from '@/hooks/useSymbolDetail';
import { useTrendAnalysis } from '@/hooks/useMarketData';
import { FiftyTwoWeekBar } from '@/components/FiftyTwoWeekBar';
import { PriceCell } from '@/components/PriceCell';
import { StatTile } from '@/components/dashboard/StatTile';
import { formatVolume } from '@/lib/format';
import { ArrowLeft, BarChart3, TrendingUp, TrendingDown, Activity, AlertTriangle } from 'lucide-react';

function formatMarketCap(v: number): string {
  if (v >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(2)}M`;
  return `$${v.toLocaleString()}`;
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
      <div className="min-h-screen bg-canvas text-ink p-2.5">
        <div className="max-w-5xl mx-auto space-y-2.5">
          <div className="h-24 bg-surface-raised rounded-[2px] animate-pulse" />
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="h-14 bg-surface-raised rounded-[2px] animate-pulse" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (hasError) {
    return (
      <div className="min-h-screen bg-canvas text-ink p-2.5">
        <div className="max-w-5xl mx-auto flex flex-col items-center justify-center h-[60vh] text-ink-secondary">
          <AlertTriangle className="w-12 h-12 mb-4 text-neg" />
          <p className="text-lg mb-2 text-ink">Failed to load symbol data</p>
          <p className="text-sm text-ink-muted mb-4">{String(detailErrorObj || statsErrorObj || rangeErrorObj || 'Unknown error')}</p>
          <button
            onClick={() => { refetchDetail?.(); refetchStats?.(); refetchRange?.(); }}
            className="btn btn-primary"
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
    <div className="min-h-screen bg-canvas text-ink p-2.5">
      <div className="max-w-5xl mx-auto space-y-2.5">
        <div className="flex items-start justify-between">
          <div className="flex items-start gap-2.5">
            <Link
              href="/"
              className="btn mt-1"
            >
              <ArrowLeft className="w-4 h-4" />
            </Link>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-bold font-mono text-ink">{symbol}</h1>
                {change !== undefined && changePct !== undefined && (
                  change >= 0
                    ? <TrendingUp className="w-5 h-5 text-pos" />
                    : <TrendingDown className="w-5 h-5 text-neg" />
                )}
              </div>
              {detail?.name && (
                <p className="text-sm text-ink-secondary">{detail.name}</p>
              )}
            </div>
          </div>

          {currentPrice !== undefined && (
            <PriceCell price={currentPrice} change={change} changePct={changePct} />
          )}
        </div>

        {range52w && (
          <div className="panel p-2.5 space-y-2.5">
            <h3 className="panel-title">52-Week Range</h3>
            <FiftyTwoWeekBar
              currentPrice={range52w.current_price}
              high52w={range52w.high_52w}
              low52w={range52w.low_52w}
              showLabels
            />
            <div className="flex justify-between text-[11px] text-ink-muted font-mono tabular-nums">
              <span>Low: ${range52w.low_52w.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
              <span>High: ${range52w.high_52w.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
            </div>
          </div>
        )}

        <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
          <StatTile label="Market Cap" value={detail?.market_cap != null ? formatMarketCap(detail.market_cap) : '—'} mono />
          <StatTile label="P/E Ratio" value={detail?.pe_ratio != null ? detail.pe_ratio.toFixed(2) : '—'} mono />
          <StatTile label="Volume" value={detail?.volume != null ? formatVolume(detail.volume) : '—'} mono />
          <StatTile label="Avg Volume (20d)" value={stats?.avg_volume_20d != null ? formatVolume(stats.avg_volume_20d) : '—'} mono />
          <StatTile label="52W High" value={stats?.high_52w != null ? `$${stats.high_52w.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—'} mono />
          <StatTile label="52W Low" value={stats?.low_52w != null ? `$${stats.low_52w.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—'} mono />
          <StatTile label="From 52W High" value={stats?.pct_from_52w_high != null ? `${stats.pct_from_52w_high.toFixed(2)}%` : '—'} mono />
          <StatTile label="ATR (14)" value={stats?.atr_14 != null ? stats.atr_14.toFixed(2) : '—'} mono />
        </div>

        {range52w && (
          <div className="panel p-2.5 space-y-2.5">
            <h3 className="panel-title flex items-center gap-2">
              <Activity className="w-4 h-4" />
              52-Week Analysis
            </h3>
            <div className="space-y-2 text-[12.5px]">
              <p className="text-ink-secondary">
                Trading{' '}
                <span className="text-ink font-medium font-mono tabular-nums">{Math.abs(range52w.pct_from_high).toFixed(2)}%</span>{' '}
                below 52-week high of{' '}
                <span className="text-ink font-medium font-mono tabular-nums">
                  ${range52w.high_52w.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </span>
              </p>
              <p className="text-ink-secondary">
                Trading{' '}
                <span className="text-ink font-medium font-mono tabular-nums">{range52w.pct_from_low.toFixed(2)}%</span>{' '}
                above 52-week low of{' '}
                <span className="text-ink font-medium font-mono tabular-nums">
                  ${range52w.low_52w.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </span>
              </p>
            </div>
          </div>
        )}

      {trendData && (
        <div className="panel p-2.5">
          <h3 className="panel-title mb-2.5 flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-sel" />
            Trend Analysis
          </h3>

          {trendData.timeframe_consensus && (
            <div className="mb-2.5">
              <div className="panel-title mb-1">Timeframe Consensus</div>
              <div className="flex items-center gap-2.5 text-[12.5px]">
                {['bullish', 'bearish', 'neutral'].map((dir) => {
                  const count = trendData.timeframe_consensus[`${dir}_count`] ?? 0;
                  return (
                    <span key={dir} className={`font-mono tabular-nums ${dir === 'bullish' ? 'text-pos' : dir === 'bearish' ? 'text-neg' : 'text-ink-muted'}`}>
                      {count} {dir}
                    </span>
                  );
                })}
              </div>
            </div>
          )}

          {trendData.timeframes && (
            <div className="space-y-2 mb-2.5">
              {Object.entries(trendData.timeframes).map(([tf, data]: [string, any]) => (
                <div key={tf} className="flex items-center justify-between text-[11px]">
                  <span className="text-ink-muted font-mono w-12">{tf}</span>
                  <div className="flex-1 mx-2">
                    <div className="h-1 bg-surface-raised overflow-hidden">
                      <div
                        className={`h-full ${data?.direction?.includes('BULL') ? 'bg-pos' : data?.direction?.includes('BEAR') ? 'bg-neg' : 'bg-surface-hover'}`}
                        style={{ width: `${Math.min((data?.strength ?? 0) * 100, 100)}%` }}
                      />
                    </div>
                  </div>
                  <span className={`w-16 text-right font-mono tabular-nums ${data?.direction?.includes('BULL') ? 'text-pos' : data?.direction?.includes('BEAR') ? 'text-neg' : 'text-ink-muted'}`}>
                    {data?.direction?.replace('LY_', ' ') ?? '--'} ({((data?.strength ?? 0) * 100).toFixed(0)}%)
                  </span>
                </div>
              ))}
            </div>
          )}

          {trendData.key_levels && (
            <div className="grid grid-cols-2 gap-2 text-[11px]">
              {trendData.key_levels.support && (
                <div className="bg-pos-dim rounded-[2px] p-2">
                  <div className="panel-title">Support</div>
                  <div className="text-pos font-mono tabular-nums">{trendData.key_levels.support}</div>
                </div>
              )}
              {trendData.key_levels.resistance && (
                <div className="bg-neg-dim rounded-[2px] p-2">
                  <div className="panel-title">Resistance</div>
                  <div className="text-neg font-mono tabular-nums">{trendData.key_levels.resistance}</div>
                </div>
              )}
            </div>
          )}

          {trendData.signals && trendData.signals.length > 0 && (
            <div className="mt-2.5 pt-2.5 border-t border-line-subtle">
              <div className="panel-title mb-2">Active Signals</div>
              <div className="space-y-1">
                {trendData.signals.slice(0, 5).map((s: any, i: number) => (
                  <div key={i} className="flex items-center gap-2 text-[11px]">
                    <span
                      className={`border rounded-[2px] px-1.5 h-5 text-[11px] font-mono inline-flex items-center ${
                        s.direction === 'BULLISH'
                          ? 'border-pos text-pos'
                          : s.direction === 'BEARISH'
                          ? 'border-neg text-neg'
                          : 'border-line text-ink-muted'
                      }`}
                    >
                      {s.direction ?? 'NEUTRAL'}
                    </span>
                    <span className="text-ink-secondary">{s.type.replace(/_/g, ' ')}</span>
                    {s.timeframe && <span className="text-ink-muted font-mono ml-auto">{s.timeframe}</span>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

        <div className="flex items-center justify-between">
          <p className="text-[11px] text-ink-muted font-mono">
            Source: Yahoo Finance{stats?.date ? ` · Last updated: ${stats.date}` : ''}
          </p>
          <Link
            href={`/chart/${encodeURIComponent(symbol)}`}
            className="btn btn-primary"
          >
            <BarChart3 className="w-4 h-4" />
            Open Chart →
          </Link>
        </div>
      </div>
    </div>
  );
}
