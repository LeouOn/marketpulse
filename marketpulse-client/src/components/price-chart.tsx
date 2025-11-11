'use client';

import { useState, useEffect } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { TrendingUp, TrendingDown } from 'lucide-react';
import { marketPulseAPI } from '@/lib/api';
import { PriceData } from '@/types/market';

interface PriceChartProps {
  symbol: string;
  timeframe?: '1Min' | '5Min' | '15Min' | '1Hour' | '1Day';
  limit?: number;
  height?: number;
}

export function PriceChart({
  symbol,
  timeframe = '5Min',
  limit = 100,
  height = 300,
}: PriceChartProps) {
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
          setError(response.error || 'Failed to load chart data');
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load chart data');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [symbol, timeframe, limit]);

  if (loading) {
    return (
      <div className="flex items-center justify-center" style={{ height }}>
        <div className="text-gray-400">Loading chart...</div>
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
        <div className="text-gray-400">No data available</div>
      </div>
    );
  }

  // Calculate price change
  const firstPrice = data[0]?.close || 0;
  const lastPrice = data[data.length - 1]?.close || 0;
  const priceChange = lastPrice - firstPrice;
  const priceChangePct = (priceChange / firstPrice) * 100;
  const isPositive = priceChange >= 0;

  // Format data for chart
  const chartData = data.map((item) => ({
    time: new Date(item.timestamp).toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
    }),
    price: item.close,
    high: item.high,
    low: item.low,
  }));

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold text-gray-300">{symbol}</h3>
          <div className="text-sm text-gray-400">{timeframe} Chart</div>
        </div>
        <div className="text-right">
          <div className="text-2xl font-bold text-white">
            ${lastPrice.toFixed(2)}
          </div>
          <div
            className={`flex items-center gap-1 text-sm ${
              isPositive ? 'text-green-400' : 'text-red-400'
            }`}
          >
            {isPositive ? (
              <TrendingUp className="w-4 h-4" />
            ) : (
              <TrendingDown className="w-4 h-4" />
            )}
            <span>
              {isPositive ? '+' : ''}
              {priceChange.toFixed(2)} ({isPositive ? '+' : ''}
              {priceChangePct.toFixed(2)}%)
            </span>
          </div>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          <XAxis
            dataKey="time"
            stroke="#9CA3AF"
            tick={{ fill: '#9CA3AF', fontSize: 12 }}
            minTickGap={30}
          />
          <YAxis
            stroke="#9CA3AF"
            tick={{ fill: '#9CA3AF', fontSize: 12 }}
            domain={['auto', 'auto']}
            tickFormatter={(value) => `$${value.toFixed(2)}`}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#1F2937',
              border: '1px solid #374151',
              borderRadius: '8px',
            }}
            labelStyle={{ color: '#9CA3AF' }}
            itemStyle={{ color: '#60A5FA' }}
            formatter={(value: number) => [`$${value.toFixed(2)}`, 'Price']}
          />
          <Legend />
          <Line
            type="monotone"
            dataKey="price"
            stroke="#60A5FA"
            strokeWidth={2}
            dot={false}
            name="Price"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
