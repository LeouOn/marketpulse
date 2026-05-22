'use client';

import { useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { useSymbolDetail, useHistoricalOHLC, use52WRange } from '@/hooks/useSymbolDetail';
import { ChartWidget } from '@/components/ChartWidget';
import { FiftyTwoWeekBar } from '@/components/FiftyTwoWeekBar';
import { ArrowLeft, BarChart3, Info } from 'lucide-react';

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
  const { data: ohlcResult, isLoading: ohlcLoading } = useHistoricalOHLC(symbol, tf.tf, tf.period);
  const { data: detail, isLoading: detailLoading } = useSymbolDetail(symbol);
  const { data: range52w } = use52WRange(symbol);

  const isLoading = ohlcLoading && detailLoading;
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
