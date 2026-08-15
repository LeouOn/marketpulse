'use client';

import { useEffect, useRef } from 'react';
import {
  createChart,
  CrosshairMode,
  CandlestickSeries,
  HistogramSeries,
} from 'lightweight-charts';
import type { IChartApi, Time } from 'lightweight-charts';

import type { OHLCVBar } from '@/types/market';
import { getChartTheme } from '@/lib/chart-theme';
import { useTheme } from '@/components/theme-provider';

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
  const { theme } = useTheme();

  useEffect(() => {
    const container = chartContainerRef.current;
    if (!container || data.length === 0) return;

    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    const chartTheme = getChartTheme();

    try {
      const chart = createChart(container, {
        width: container.clientWidth,
        height,
        layout: {
          background: {
            type: chartTheme.layout.background.type,
            color: chartTheme.layout.background.color,
          },
          textColor: chartTheme.layout.textColor,
          fontSize: chartTheme.layout.fontSize,
          fontFamily: chartTheme.layout.fontFamily,
        },
        grid: chartTheme.grid,
        crosshair: { mode: CrosshairMode.Normal },
        rightPriceScale: chartTheme.rightPriceScale,
        timeScale: {
          ...chartTheme.timeScale,
          timeVisible: true,
          secondsVisible: false,
        },
      });

      const candlestickSeries = chart.addSeries(CandlestickSeries, {
        upColor: chartTheme.upColor,
        downColor: chartTheme.downColor,
        borderUpColor: chartTheme.upColor,
        borderDownColor: chartTheme.downColor,
        wickUpColor: chartTheme.upColor,
        wickDownColor: chartTheme.downColor,
        borderVisible: false,
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
          color: chartTheme.volumeUp,
          priceFormat: { type: 'volume' },
          priceScaleId: 'volume',
        });
        chart.priceScale('volume').applyOptions({
          scaleMargins: { top: 0.8, bottom: 0 },
        });
        const volumeData = data.map((bar) => ({
          time: parseTimestamp(bar.timestamp),
          value: bar.volume,
          color: bar.close >= bar.open ? chartTheme.volumeUp : chartTheme.volumeDown,
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
  }, [data, height, showVolume, theme]);

  if (data.length === 0) {
    return (
      <div
        className={`flex items-center justify-center bg-surface border border-line-subtle rounded-[2px] ${className ?? ''}`}
        style={{ height }}
      >
        <p className="text-ink-muted text-[12.5px] font-mono">
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
