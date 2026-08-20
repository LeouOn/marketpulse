'use client';

import { useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { useSymbolDetail, useHistoricalOHLC, use52WRange } from '@/hooks/useSymbolDetail';
import { useOHLCAnalysis } from '@/hooks/useMarketData';
import { ChartWidget } from '@/components/ChartWidget';
import { FiftyTwoWeekBar } from '@/components/FiftyTwoWeekBar';
import { formatVolume } from '@/lib/format';
import { ArrowLeft, BarChart3, Info, AlertTriangle } from 'lucide-react';

const TIMEFRAMES = [
  { label: '5m', period: '5d', tf: '5m' },
  { label: '15m', period: '5d', tf: '15m' },
  { label: '1h', period: '1mo', tf: '1h' },
  { label: '4h', period: '3mo', tf: '1d' },
  { label: '1D', period: '1y', tf: '1d' },
  { label: '1W', period: '2y', tf: '1wk' },
] as const;

export default function ChartPage() {
  const params = useParams();
  const symbol = params.symbol as string;
  const [activeIdx, setActiveIdx] = useState(4);

  const tf = TIMEFRAMES[activeIdx];
  const { data: ohlcResult, isLoading: ohlcLoading, isError: ohlcError, error: ohlcErrorObj, refetch: refetchOHLC } = useHistoricalOHLC(symbol, tf.tf, tf.period);
  const { data: detail, isLoading: detailLoading, isError: detailError, error: detailErrorObj, refetch: refetchDetail } = useSymbolDetail(symbol);
  const { data: range52w } = use52WRange(symbol);
  const { data: ohlcAnalysis } = useOHLCAnalysis(symbol);

  const isLoading = ohlcLoading || detailLoading;
  const hasError = ohlcError || detailError;
  const ohlcData = ohlcResult?.data ?? [];

  return (
    <div className="min-h-screen bg-canvas text-ink p-2.5">
      <div className="max-w-7xl mx-auto space-y-2.5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <Link
              href="/"
              className="btn"
            >
              <ArrowLeft className="w-4 h-4" />
            </Link>
            <div>
              <h1 className="text-xl font-bold text-ink">
                {detail?.name ?? symbol}
              </h1>
              <span className="text-[11px] uppercase tracking-[0.08em] text-ink-muted font-mono">{symbol}</span>
            </div>
          </div>

          <div className="flex items-center gap-2.5">
            {range52w && (
              <span className="text-[15px] leading-tight font-semibold font-mono tabular-nums text-ink">
                ${range52w.current_price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
            )}
            <Link
              href={`/symbol/${encodeURIComponent(symbol)}`}
              className="btn"
            >
              <Info className="w-3.5 h-3.5" />
              Details
            </Link>
          </div>
        </div>

        <div className="flex gap-1 overflow-x-auto pb-1">
          {TIMEFRAMES.map((t, i) => (
            <button
              key={t.label}
              onClick={() => setActiveIdx(i)}
              className={`btn whitespace-nowrap ${i === activeIdx ? 'btn-primary' : ''}`}
            >
              {i < 5 && <kbd className="kbd">{i + 1}</kbd>}
              {t.label}
            </button>
          ))}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-2.5">
          <div className="lg:col-span-3">
            {isLoading ? (
              <div className="w-full h-[500px] bg-surface-raised rounded-[2px] animate-pulse" />
            ) : hasError ? (
              <div className="flex flex-col items-center justify-center h-[500px] text-ink-secondary">
                <AlertTriangle className="w-12 h-12 mb-4 text-neg" />
                <p className="text-lg mb-2 text-ink">Failed to load chart data</p>
                <p className="text-sm text-ink-muted mb-4">{String(ohlcErrorObj || detailErrorObj || 'Unknown error')}</p>
                <button
                  onClick={() => { refetchOHLC?.(); refetchDetail?.(); }}
                  className="btn btn-primary"
                >
                  Retry
                </button>
              </div>
            ) : (
              <ChartWidget data={ohlcData} symbol={symbol} height={500} className="overflow-hidden" />
            )}
          </div>

          <div className="lg:col-span-1 space-y-2.5">
            {detailLoading ? (
              <>
                <div className="h-20 bg-surface-raised rounded-[2px] animate-pulse" />
                <div className="h-40 bg-surface-raised rounded-[2px] animate-pulse" />
              </>
            ) : (
              <>
                <div className="panel p-2.5 space-y-2">
                  <h3 className="panel-title">Symbol Info</h3>
                  <p className="text-ink font-medium">{detail?.name ?? symbol}</p>
                  {detail?.exchange && (
                    <p className="text-[11px] text-ink-muted">Exchange: {detail.exchange}</p>
                  )}
                  {detail?.sector && (
                    <p className="text-[11px] text-ink-muted">Sector: {detail.sector}</p>
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
                  </div>
                )}

                <div className="panel p-2.5 space-y-2">
                  <h3 className="panel-title">Key Stats</h3>
                  {detail?.avg_volume_20d != null && (
                    <div className="flex justify-between text-[12.5px]">
                      <span className="text-[11px] uppercase tracking-[0.08em] text-ink-secondary">Avg Volume (20d)</span>
                      <span className="font-mono tabular-nums text-ink">{formatVolume(detail.avg_volume_20d)}</span>
                    </div>
                  )}
                  {detail?.atr_14 != null && (
                    <div className="flex justify-between text-[12.5px]">
                      <span className="text-[11px] uppercase tracking-[0.08em] text-ink-secondary">ATR (14)</span>
                      <span className="font-mono tabular-nums text-ink">{detail.atr_14.toFixed(2)}</span>
                    </div>
                  )}
                  {detail?.sma_20 != null && (
                    <div className="flex justify-between text-[12.5px]">
                      <span className="text-[11px] uppercase tracking-[0.08em] text-ink-secondary">SMA 20</span>
                      <span className="font-mono tabular-nums text-ink">${detail.sma_20.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                    </div>
                  )}
                  {detail?.sma_50 != null && (
                    <div className="flex justify-between text-[12.5px]">
                      <span className="text-[11px] uppercase tracking-[0.08em] text-ink-secondary">SMA 50</span>
                      <span className="font-mono tabular-nums text-ink">${detail.sma_50.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                    </div>
                  )}
                  {detail?.sma_200 != null && (
                    <div className="flex justify-between text-[12.5px]">
                      <span className="text-[11px] uppercase tracking-[0.08em] text-ink-secondary">SMA 200</span>
                      <span className="font-mono tabular-nums text-ink">${detail.sma_200.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                    </div>
                  )}
                </div>

                {ohlcAnalysis && ohlcAnalysis.timeframes && (
                  <div className="panel p-2.5">
                    <h4 className="panel-title mb-2">Technical Analysis</h4>
                    {Object.entries(ohlcAnalysis.timeframes).map(([tf, data]: [string, any]) => (
                      <div key={tf} className="mb-2 last:mb-0">
                        <div className="flex items-center gap-2 text-[11px]">
                          <span className="text-ink-muted font-mono w-8">{tf.toUpperCase()}</span>
                          <span className={data?.trend?.direction?.includes('BULL') ? 'text-pos' : data?.trend?.direction?.includes('BEAR') ? 'text-neg' : 'text-ink-muted'}>
                            {data?.trend?.direction?.replace('LY_', ' ') ?? '--'}
                          </span>
                          <span className="text-ink-muted font-mono tabular-nums">
                            Str: {((data?.trend?.strength ?? 0) * 100).toFixed(0)}%
                          </span>
                        </div>
                        {data?.patterns?.length > 0 && (
                          <div className="ml-10 text-[10px] text-ink-muted">
                            {data.patterns.slice(0, 2).map((p: any) => p.type).join(', ')}
                          </div>
                        )}
                      </div>
                    ))}
                    {ohlcAnalysis.signals && ohlcAnalysis.signals.length > 0 && (
                      <div className="mt-2 pt-2 border-t border-line">
                        <div className="panel-title mb-1">Signals</div>
                        {ohlcAnalysis.signals.slice(0, 3).map((s: any, i: number) => (
                          <div key={i} className="flex items-center gap-1.5 text-[11px]">
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
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                <Link
                  href={`/symbol/${encodeURIComponent(symbol)}`}
                  className="btn btn-primary w-full justify-center"
                >
                  <BarChart3 className="w-4 h-4" />
                  Full Details →
                </Link>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
