'use client';

import { useEffect, useRef, useCallback } from 'react';
import {
  createChart,
  ColorType,
  CrosshairMode,
  CandlestickSeries,
  HistogramSeries,
} from 'lightweight-charts';
import type { IChartApi, Time } from 'lightweight-charts';

import type { OHLCVBar } from '@/types/market';

interface ChartWidgetProps {
  data: OHLCVBar[];
  symbol: string;
  height?: number;
  showVolume?: boolean;
  className?: string;
}

function parseTimestamp(ts: string): Time {
  if (ts.includes('T')) {
    return ts.replace('T', ' ').replace('Z', '').substring(0, 19) as Time;
  }
  return ts as Time;
}

export function ChartWidget({
  data,
  symbol,
  height = 500,
  showVolume = true,
  className,
}: ChartWidgetProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  const buildChart = useCallback(() => {
    const container = chartContainerRef.current;
    if (!container || data.length === 0) return;

    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    try {
      const chart = createChart(container, {
        width: container.clientWidth,
        height,
        layout: {
          background: { type: ColorType.Solid, color: '#0a0a0a' },
          textColor: '#a0a0a0',
        },
        grid: {
          vertLines: { color: '#1a1a1a' },
          horzLines: { color: '#1a1a1a' },
        },
        crosshair: { mode: CrosshairMode.Normal },
        rightPriceScale: { borderColor: '#333333' },
        timeScale: {
          borderColor: '#333333',
          timeVisible: true,
          secondsVisible: false,
        },
      });

      const candlestickSeries = chart.addSeries(CandlestickSeries, {
        upColor: '#10b981',
        downColor: '#ef4444',
        borderDownColor: '#ef4444',
        borderUpColor: '#10b981',
        wickDownColor: '#ef4444',
        wickUpColor: '#10b981',
      });

      const candleData = data.map((bar) => ({
        time: parseTimestamp(bar.timestamp),
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
      }));
      candlestickSeries.setData(candleData);

      if (showVolume) {
        const volumeSeries = chart.addSeries(HistogramSeries, {
          color: '#333333',
          priceFormat: { type: 'volume' },
          priceScaleId: 'volume',
        });
        chart.priceScale('volume').applyOptions({
          scaleMargins: { top: 0.8, bottom: 0 },
        });
        const volumeData = data.map((bar) => ({
          time: parseTimestamp(bar.timestamp),
          value: bar.volume,
          color:
            bar.close >= bar.open
              ? 'rgba(16, 185, 129, 0.3)'
              : 'rgba(239, 68, 68, 0.3)',
        }));
        volumeSeries.setData(volumeData);
      }

      chart.timeScale().fitContent();

      const resizeObserver = new ResizeObserver((entries) => {
        if (entries.length > 0) {
          const { width } = entries[0].contentRect;
          chart.applyOptions({ width });
        }
      });
      resizeObserver.observe(container);

      chartRef.current = chart;

      return () => {
        resizeObserver.disconnect();
        chart.remove();
        chartRef.current = null;
      };
    } catch {
      chartRef.current = null;
    }
  }, [data, height, showVolume]);

  useEffect(() => {
    const cleanup = buildChart();
    return () => {
      cleanup?.();
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
    };
  }, [buildChart]);

  if (data.length === 0) {
    return (
      <div
        className={`flex items-center justify-center bg-[#0a0a0a] rounded-lg ${className ?? ''}`}
        style={{ height }}
      >
        <p className="text-neutral-500 text-sm">
          No chart data available for {symbol}
        </p>
      </div>
    );
  }

  return (
    <div className={className}>
      <div ref={chartContainerRef} className="w-full" />
    </div>
  );
}
