'use client';

import { useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { useSymbolDetail, useHistoricalOHLC, use52WRange } from '@/hooks/useSymbolDetail';
import { useOHLCAnalysis } from '@/hooks/useMarketData';
import { ChartWidget } from '@/components/ChartWidget';
import { FiftyTwoWeekBar } from '@/components/FiftyTwoWeekBar';
import { ArrowLeft, BarChart3, Info, AlertTriangle } from 'lucide-react';

const TIMEFRAMES = [
  { label: '5m', period: '5d', tf: '5m' },
  { label: '15m', period: '5d', tf: '15m' },
  { label: '1h', period: '1mo', tf: '1h' },
  { label: '4h', period: '3mo', tf: '1d' },
  { label: '1D', period: '1y', tf: '1d' },
  { label: '1W', period: '2y', tf: '1wk' },
] as const;

function formatVolume(v: number): string {
  if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
  return v.toLocaleString();
}

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
    <div className="min-h-screen bg-black text-white p-4 md:p-6">
      <div className="max-w-7xl mx-auto space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link
              href="/"
              className="p-2 rounded-lg bg-gray-900 hover:bg-gray-800 transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
            </Link>
            <div>
              <h1 className="text-xl font-bold">
                {detail?.name ?? symbol}
              </h1>
              <span className="text-sm text-gray-500">{symbol}</span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {range52w && (
              <span className="text-lg font-semibold tabular-nums">
                ${range52w.current_price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
            )}
            <Link
              href={`/symbol/${encodeURIComponent(symbol)}`}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gray-900 hover:bg-gray-800 text-sm transition-colors"
            >
              <Info className="w-3.5 h-3.5" />
              Details
            </Link>
          </div>
        </div>

        <div className="flex gap-2 overflow-x-auto pb-1">
          {TIMEFRAMES.map((t, i) => (
            <button
              key={t.label}
              onClick={() => setActiveIdx(i)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors whitespace-nowrap ${
                i === activeIdx
                  ? 'bg-blue-500/20 text-blue-400 border-blue-500/30'
                  : 'bg-gray-800 text-gray-400 border-transparent hover:bg-gray-700'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
          <div className="lg:col-span-3">
            {isLoading ? (
              <div className="w-full h-[500px] bg-gray-900 rounded-xl animate-pulse" />
            ) : hasError ? (
              <div className="flex flex-col items-center justify-center h-[500px] text-gray-400">
                <AlertTriangle className="w-12 h-12 mb-4 text-red-400" />
                <p className="text-lg mb-2">Failed to load chart data</p>
                <p className="text-sm text-gray-500 mb-4">{String(ohlcErrorObj || detailErrorObj || 'Unknown error')}</p>
                <button
                  onClick={() => { refetchOHLC?.(); refetchDetail?.(); }}
                  className="px-4 py-2 bg-blue-500/20 text-blue-400 rounded-lg hover:bg-blue-500/30 transition-colors"
                >
                  Retry
                </button>
              </div>
            ) : (
              <ChartWidget data={ohlcData} symbol={symbol} height={500} className="rounded-xl overflow-hidden" />
            )}
          </div>

          <div className="lg:col-span-1 space-y-4">
            {detailLoading ? (
              <>
                <div className="h-20 bg-gray-900 rounded-xl animate-pulse" />
                <div className="h-40 bg-gray-900 rounded-xl animate-pulse" />
              </>
            ) : (
              <>
                <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-2">
                  <h3 className="text-sm font-medium text-gray-400">Symbol Info</h3>
                  <p className="text-white font-medium">{detail?.name ?? symbol}</p>
                  {detail?.exchange && (
                    <p className="text-xs text-gray-500">Exchange: {detail.exchange}</p>
                  )}
                  {detail?.sector && (
                    <p className="text-xs text-gray-500">Sector: {detail.sector}</p>
                  )}
                </div>

                {range52w && (
                  <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
                    <h3 className="text-sm font-medium text-gray-400">52-Week Range</h3>
                    <FiftyTwoWeekBar
                      currentPrice={range52w.current_price}
                      high52w={range52w.high_52w}
                      low52w={range52w.low_52w}
                      showLabels
                    />
                  </div>
                )}

                <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
                  <h3 className="text-sm font-medium text-gray-400">Key Stats</h3>
                  {detail?.avg_volume_20d != null && (
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-500">Avg Volume (20d)</span>
                      <span className="text-white">{formatVolume(detail.avg_volume_20d)}</span>
                    </div>
                  )}
                  {detail?.atr_14 != null && (
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-500">ATR (14)</span>
                      <span className="text-white">{detail.atr_14.toFixed(2)}</span>
                    </div>
                  )}
                  {detail?.sma_20 != null && (
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-500">SMA 20</span>
                      <span className="text-white">${detail.sma_20.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                    </div>
                  )}
                  {detail?.sma_50 != null && (
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-500">SMA 50</span>
                      <span className="text-white">${detail.sma_50.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                    </div>
                  )}
                  {detail?.sma_200 != null && (
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-500">SMA 200</span>
                      <span className="text-white">${detail.sma_200.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                    </div>
                  )}
                </div>

                {ohlcAnalysis && ohlcAnalysis.timeframes && (
                  <div className="bg-gray-800/50 rounded-lg p-3">
                    <h4 className="text-xs font-medium text-gray-400 mb-2">Technical Analysis</h4>
                    {Object.entries(ohlcAnalysis.timeframes).map(([tf, data]: [string, any]) => (
                      <div key={tf} className="mb-2 last:mb-0">
                        <div className="flex items-center gap-2 text-xs">
                          <span className="text-gray-500 w-8">{tf.toUpperCase()}</span>
                          <span className={data?.trend?.direction?.includes('BULL') ? 'text-emerald-400' : data?.trend?.direction?.includes('BEAR') ? 'text-red-400' : 'text-gray-400'}>
                            {data?.trend?.direction?.replace('LY_', ' ') ?? '--'}
                          </span>
                          <span className="text-gray-600">
                            Str: {((data?.trend?.strength ?? 0) * 100).toFixed(0)}%
                          </span>
                        </div>
                        {data?.patterns?.length > 0 && (
                          <div className="ml-10 text-[10px] text-gray-500">
                            {data.patterns.slice(0, 2).map((p: any) => p.type).join(', ')}
                          </div>
                        )}
                      </div>
                    ))}
                    {ohlcAnalysis.signals && ohlcAnalysis.signals.length > 0 && (
                      <div className="mt-2 pt-2 border-t border-gray-700">
                        <div className="text-[10px] text-gray-500 mb-1">Signals</div>
                        {ohlcAnalysis.signals.slice(0, 3).map((s: any, i: number) => (
                          <div key={i} className="flex items-center gap-1 text-[11px]">
                            <span className={s.direction === 'BULLISH' ? 'text-emerald-400' : s.direction === 'BEARISH' ? 'text-red-400' : 'text-gray-400'}>
                              {s.direction === 'BULLISH' ? '▲' : s.direction === 'BEARISH' ? '▼' : '◆'}
                            </span>
                            <span className="text-gray-400">{s.type.replace(/_/g, ' ')}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                <Link
                  href={`/symbol/${encodeURIComponent(symbol)}`}
                  className="flex items-center justify-center gap-2 w-full px-4 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium transition-colors"
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
