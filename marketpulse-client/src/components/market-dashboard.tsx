'use client';

import { useState, useEffect } from 'react';
import { LineChart, Line, AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { TrendingUp, TrendingDown, Activity, AlertCircle, Wifi, WifiOff } from 'lucide-react';
import { MarketDashboard as DashboardData, MarketSymbol } from '@/types/market';
import { marketPulseAPI } from '@/lib/api';
import { useMarketWebSocket } from '@/hooks/useMarketWebSocket';
import { config } from '@/lib/config';
import { PriceChart } from './price-chart';
import { VolumeChart } from './volume-chart';

export function MarketDashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [usePolling, setUsePolling] = useState(!config.features.websocket);

  // WebSocket connection
  const {
    data: wsData,
    connected: wsConnected,
    error: wsError,
    reconnecting: wsReconnecting,
  } = useMarketWebSocket({
    autoConnect: !usePolling,
    onData: (newData) => {
      setData(newData);
      setLastUpdate(new Date());
      setError(null);
      setLoading(false);
    },
    onError: () => {
      // Fallback to polling if WebSocket fails
      if (!usePolling) {
        console.warn('WebSocket failed, falling back to polling');
        setUsePolling(true);
      }
    },
  });

  // Polling fallback
  const fetchData = async () => {
    try {
      const response = await marketPulseAPI.getDashboardData();
      if (response.success && response.data) {
        setData(response.data);
        setLastUpdate(new Date());
        setError(null);
      } else {
        setError(response.error || 'Failed to fetch data');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // Use polling if WebSocket is disabled or failed
    if (usePolling) {
      fetchData();
      const interval = setInterval(fetchData, config.polling.interval);
      return () => clearInterval(interval);
    }
  }, [usePolling]);

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
      {/* Header with last update time and connection status */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <Activity className="w-4 h-4" />
            <span>Last updated: {lastUpdate?.toLocaleTimeString()}</span>
          </div>
          {!usePolling && (
            <div className="flex items-center gap-2 text-sm">
              {wsConnected ? (
                <>
                  <Wifi className="w-4 h-4 text-green-400" />
                  <span className="text-green-400">Live</span>
                </>
              ) : wsReconnecting ? (
                <>
                  <Activity className="w-4 h-4 text-yellow-400 animate-pulse" />
                  <span className="text-yellow-400">Reconnecting...</span>
                </>
              ) : (
                <>
                  <WifiOff className="w-4 h-4 text-red-400" />
                  <span className="text-red-400">Disconnected</span>
                </>
              )}
            </div>
          )}
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

      {/* Price Charts */}
      {config.features.charts && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-gray-900 rounded-lg p-6 border border-gray-800">
            <PriceChart symbol="SPY" timeframe="5Min" limit={100} height={300} />
          </div>
          <div className="bg-gray-900 rounded-lg p-6 border border-gray-800">
            <PriceChart symbol="QQQ" timeframe="5Min" limit={100} height={300} />
          </div>
        </div>
      )}

      {/* Volume Charts */}
      {config.features.charts && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-gray-900 rounded-lg p-6 border border-gray-800">
            <VolumeChart symbol="SPY" timeframe="5Min" limit={50} height={200} />
          </div>
          <div className="bg-gray-900 rounded-lg p-6 border border-gray-800">
            <VolumeChart symbol="QQQ" timeframe="5Min" limit={50} height={200} />
          </div>
        </div>
      )}

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