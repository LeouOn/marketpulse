'use client';

import { useState, useEffect } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { Activity } from 'lucide-react';
import { marketPulseAPI } from '@/lib/api';
import { PriceData } from '@/types/market';

interface VolumeChartProps {
  symbol: string;
  timeframe?: '1Min' | '5Min' | '15Min' | '1Hour' | '1Day';
  limit?: number;
  height?: number;
}

export function VolumeChart({
  symbol,
  timeframe = '5Min',
  limit = 50,
  height = 200,
}: VolumeChartProps) {
  const [data, setData] = useState<PriceData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const response = await marketPulseAPI.getHistoricalData({
          symbol,
          timeframe,
          limit,
        });

        if (response.success && response.data) {
          setData(response.data);
          setError(null);
        } else {
          setError(response.error || 'Failed to load volume data');
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load volume data');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [symbol, timeframe, limit]);

  if (loading) {
    return (
      <div className="flex items-center justify-center" style={{ height }}>
        <div className="text-gray-400">Loading volume data...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center" style={{ height }}>
        <div className="text-red-400">{error}</div>
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center" style={{ height }}>
        <div className="text-gray-400">No volume data available</div>
      </div>
    );
  }

  // Calculate average volume
  const avgVolume = data.reduce((sum, item) => sum + item.volume, 0) / data.length;
  const totalVolume = data.reduce((sum, item) => sum + item.volume, 0);

  // Format data for chart
  const chartData = data.map((item) => {
    // Determine color based on price movement
    const priceChange = item.close - item.open;
    const isGreen = priceChange >= 0;

    return {
      time: new Date(item.timestamp).toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit',
      }),
      volume: item.volume,
      fill: isGreen ? '#34D399' : '#F87171', // green-400 or red-400
    };
  });

  const formatVolume = (value: number): string => {
    if (value >= 1000000) {
      return `${(value / 1000000).toFixed(1)}M`;
    } else if (value >= 1000) {
      return `${(value / 1000).toFixed(1)}K`;
    }
    return value.toString();
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Activity className="w-5 h-5 text-blue-400" />
          <h3 className="text-lg font-semibold text-gray-300">Volume Flow</h3>
        </div>
        <div className="text-right">
          <div className="text-sm text-gray-400">Total Volume</div>
          <div className="text-xl font-bold text-white">
            {formatVolume(totalVolume)}
          </div>
          <div className="text-xs text-gray-500">
            Avg: {formatVolume(avgVolume)}
          </div>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          <XAxis
            dataKey="time"
            stroke="#9CA3AF"
            tick={{ fill: '#9CA3AF', fontSize: 10 }}
            minTickGap={20}
          />
          <YAxis
            stroke="#9CA3AF"
            tick={{ fill: '#9CA3AF', fontSize: 10 }}
            tickFormatter={formatVolume}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#1F2937',
              border: '1px solid #374151',
              borderRadius: '8px',
            }}
            labelStyle={{ color: '#9CA3AF' }}
            formatter={(value: number) => [formatVolume(value), 'Volume']}
            cursor={{ fill: 'rgba(55, 65, 81, 0.3)' }}
          />
          <Bar dataKey="volume" fill="#60A5FA" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
