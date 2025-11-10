'use client';

import { useState, useEffect } from 'react';
import { LineChart, Line, AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { TrendingUp, TrendingDown, Activity, AlertCircle } from 'lucide-react';
import { MarketDashboard as DashboardData, MarketSymbol } from '@/types/market';
import { marketPulseAPI } from '@/lib/api';

export function MarketDashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);

  const fetchData = async () => {
    try {
      const dashboardData = await marketPulseAPI.getDashboardData();
      setData(dashboardData);
      setLastUpdate(new Date());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000); // Update every 30 seconds
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-blue-400">Loading market data...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-900/20 border border-red-500/30 rounded-lg p-4">
        <div className="flex items-center gap-2 text-red-400">
          <AlertCircle className="w-5 h-5" />
          <span>Error: {error}</span>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="text-gray-400">No data available</div>
    );
  }

  const getBiasColor = (bias: string) => {
    switch (bias) {
      case 'BULLISH': return 'text-green-400';
      case 'BEARISH': return 'text-red-400';
      case 'MIXED': return 'text-yellow-400';
      default: return 'text-gray-400';
    }
  };

  const getVolatilityColor = (regime: string) => {
    switch (regime) {
      case 'EXTREME': return 'text-red-500';
      case 'HIGH': return 'text-orange-400';
      case 'NORMAL': return 'text-yellow-400';
      case 'LOW': return 'text-green-400';
      default: return 'text-gray-400';
    }
  };

  const renderSymbolCard = (symbol: MarketSymbol | undefined, label: string) => {
    if (!symbol) return null;

    const isPositive = symbol.change >= 0;
    const TrendIcon = isPositive ? TrendingUp : TrendingDown;
    const trendColor = isPositive ? 'text-green-400' : 'text-red-400';

    return (
      <div className="bg-gray-900 rounded-lg p-6 border border-gray-800">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-lg font-semibold text-gray-300">{label}</h3>
          <TrendIcon className={`w-5 h-5 ${trendColor}`} />
        </div>
        <div className="text-3xl font-bold text-white mb-1">
          ${symbol.price.toFixed(2)}
        </div>
        <div className={`text-sm ${trendColor}`}>
          {isPositive ? '+' : ''}{symbol.change.toFixed(2)} ({isPositive ? '+' : ''}{symbol.changePct.toFixed(2)}%)
        </div>
        <div className="text-xs text-gray-500 mt-2">
          Vol: {symbol.volume.toLocaleString()}
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-6">
      {/* Header with last update time */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm text-gray-400">
          <Activity className="w-4 h-4" />
          <span>Last updated: {lastUpdate?.toLocaleTimeString()}</span>
        </div>
        <button
          onClick={fetchData}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm font-medium transition-colors"
        >
          Refresh
        </button>
      </div>

      {/* Market Overview Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {renderSymbolCard(data.symbols.spy, 'SPY (Market)')}
        {renderSymbolCard(data.symbols.qqq, 'QQQ (Tech)')}
        {renderSymbolCard(data.symbols.vix, 'VIX (Volatility)')}
      </div>

      {/* Market Analysis */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-gray-900 rounded-lg p-6 border border-gray-800">
          <h3 className="text-lg font-semibold text-gray-300 mb-4">Market Bias</h3>
          <div className={`text-2xl font-bold ${getBiasColor(data.marketBias)}`}>
            {data.marketBias}
          </div>
        </div>

        <div className="bg-gray-900 rounded-lg p-6 border border-gray-800">
          <h3 className="text-lg font-semibold text-gray-300 mb-4">Volatility Regime</h3>
          <div className={`text-2xl font-bold ${getVolatilityColor(data.volatilityRegime)}`}>
            {data.volatilityRegime}
          </div>
        </div>
      </div>

      {/* Volume Flow */}
      <div className="bg-gray-900 rounded-lg p-6 border border-gray-800">
        <h3 className="text-lg font-semibold text-gray-300 mb-4">Volume Flow (60min)</h3>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="text-3xl font-bold text-white">
              {data.volumeFlow.totalVolume60min.toLocaleString()}
            </div>
            <div className="text-sm text-gray-400">Total Volume</div>
          </div>
          <div>
            <div className="text-3xl font-bold text-white">
              {data.volumeFlow.symbolsTracked}
            </div>
            <div className="text-sm text-gray-400">Symbols Tracked</div>
          </div>
        </div>
      </div>

      {/* AI Analysis */}
      {data.aiAnalysis && (
        <div className="bg-gray-900 rounded-lg p-6 border border-gray-800">
          <h3 className="text-lg font-semibold text-gray-300 mb-4">AI Analysis</h3>
          <div className="text-gray-400 whitespace-pre-wrap">
            {data.aiAnalysis}
          </div>
        </div>
      )}
    </div>
  );
}