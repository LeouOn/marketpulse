'use client';

import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
// Use basic icons that should be available
const ActivityIcon = () => (
  <div className="w-4 h-4 bg-blue-400 rounded-full" />
);

const TrendingUpIcon = () => (
  <div className="w-4 h-4 bg-green-400 rounded-sm" style={{clipPath: 'polygon(0 100%, 50% 0%, 100% 50%)'}} />
);

const TrendingDownIcon = () => (
  <div className="w-4 h-4 bg-red-400 rounded-sm" style={{clipPath: 'polygon(0 0%, 50% 100%, 100% 50%)'}} />
);

const RefreshIcon = () => (
  <div className="w-4 h-4 border-2 border-blue-400 rounded-full" />
);

const DollarSignIcon = () => (
  <div className="w-4 h-4 flex items-center justify-center text-blue-400 font-bold">$</div>
);

const ZapIcon = () => (
  <div className="w-4 h-4 bg-yellow-400 rounded" />
);

const GlobeIcon = () => (
  <div className="w-4 h-4 bg-purple-400 rounded-full" />
);

const EyeIcon = () => (
  <div className="w-4 h-4 bg-indigo-400 rounded-full" />
);

const CheckIcon = () => (
  <div className="w-4 h-4 bg-green-400 rounded-sm flex items-center justify-center text-white">✓</div>
);

const AlertIcon = () => (
  <div className="w-4 h-4 bg-red-400 rounded-sm flex items-center justify-center text-white">!</div>
);

interface MarketData {
  symbol: string;
  price: number;
  change: number;
  change_pct: number;
  volume: number;
  timestamp: string;
}

interface DashboardResponse {
  success: boolean;
  data: {
    marketBias?: string;
    volatilityRegime?: string;
    symbols?: Record<string, MarketData>;
    volumeFlow?: {
      total_volume_60min: number;
      symbols_tracked: number;
    };
    market_session?: string;
    economic_sentiment?: string;
    risk_appetite?: string;
    sector_performance?: Record<string, number>;
  } | Record<string, MarketData>;
  error: string | null;
  timestamp: string;
}

export function ConnectedMarketDashboard() {
  const [dashboardData, setDashboardData] = useState<DashboardResponse | null>(null);
  const [macroData, setMacroData] = useState<DashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);

      // Fetch both dashboard and macro data
      const [dashboardResponse, macroResponse] = await Promise.all([
        fetch('http://localhost:8000/api/market/dashboard'),
        fetch('http://localhost:8000/api/market/macro')
      ]);

      const dashboard = await dashboardResponse.json();
      const macro = await macroResponse.json();

      setDashboardData(dashboard);
      setMacroData(macro);
      setLastUpdate(new Date());

    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch market data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    // Refresh every 60 seconds
    const interval = setInterval(fetchData, 60000);
    return () => clearInterval(interval);
  }, []);

  const getBiasColor = (bias: string) => {
    switch (bias?.toLowerCase()) {
      case 'bullish': return 'text-green-400 bg-green-400/10 border-green-400/20';
      case 'bearish': return 'text-red-400 bg-red-400/10 border-red-400/20';
      case 'mixed': return 'text-yellow-400 bg-yellow-400/10 border-yellow-400/20';
      default: return 'text-gray-400 bg-gray-400/10 border-gray-400/20';
    }
  };

  const getVolatilityColor = (regime: string) => {
    switch (regime?.toLowerCase()) {
      case 'extreme': return 'text-red-500 bg-red-500/10 border-red-500/20';
      case 'high': return 'text-orange-400 bg-orange-400/10 border-orange-400/20';
      case 'normal': return 'text-yellow-400 bg-yellow-400/10 border-yellow-400/20';
      case 'low': return 'text-green-400 bg-green-400/10 border-green-400/20';
      default: return 'text-gray-400 bg-gray-400/10 border-gray-400/20';
    }
  };

  const formatPrice = (price: number, symbol: string) => {
    if (symbol.includes('-USD')) {
      return `$${price.toLocaleString()}`;
    }
    return `$${price.toFixed(2)}`;
  };

  const formatChange = (change: number, changePct: number) => {
    const sign = change >= 0 ? '+' : '';
    const isPositive = change >= 0;
    const isNeutral = Math.abs(change) < 0.01; // Consider very small changes as neutral

    return {
      value: `${sign}${change.toFixed(2)} (${sign}${changePct.toFixed(2)}%)`,
      color: isNeutral ? 'neutral' : (isPositive ? 'positive' : 'negative'),
      colorClass: isNeutral ? 'text-neutral' : (isPositive ? 'text-positive' : 'text-negative'),
      bgClass: isNeutral ? 'neutral-bg' : (isPositive ? 'positive-bg' : 'negative-bg'),
      borderClass: isNeutral ? 'neutral-border' : (isPositive ? 'positive-border' : 'negative-border'),
      icon: change >= 0 ? TrendingUpIcon : TrendingDownIcon
    };
  };

  const formatVolume = (volume: number) => {
    if (volume >= 1e9) return `${(volume / 1e9).toFixed(1)}B`;
    if (volume >= 1e6) return `${(volume / 1e6).toFixed(1)}M`;
    if (volume >= 1e3) return `${(volume / 1e3).toFixed(1)}K`;
    return volume.toString();
  };

  const getMacroIcon = (symbol: string) => {
    switch (symbol) {
      case 'DXY': return DollarSignIcon;
      case 'GC': return ActivityIcon;
      case 'CL': return ActivityIcon;
      case 'BTC': return ActivityIcon;
      case 'ETH': case 'SOL': case 'XRP': return ActivityIcon;
      case 'TNX': return ActivityIcon;
      default: return ActivityIcon;
    }
  };

  const getMacroLabel = (symbol: string) => {
    switch (symbol) {
      case 'DXY': return 'US Dollar';
      case 'GC': return 'Gold';
      case 'CL': return 'Crude Oil';
      case 'BTC': return 'Bitcoin';
      case 'ETH': return 'Ethereum';
      case 'SOL': return 'Solana';
      case 'XRP': return 'Ripple';
      case 'TNX': return '10Y Treasury';
      default: return symbol;
    }
  };

  if (loading && !dashboardData && !macroData) {
    return (
      <div className="min-h-screen bg-gray-950 text-white p-6">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-center justify-center h-96">
            <RefreshIcon />
            <span className="text-xl text-gray-300 ml-3">Loading market data...</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-950 text-white p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex justify-between items-center mb-8">
          <div>
            <h1 className="text-4xl font-bold bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent">
              MarketPulse Live Dashboard
            </h1>
            <p className="text-gray-400 mt-2">Real-time market data and analysis</p>
          </div>
          <div className="flex items-center gap-4">
            {lastUpdate && (
              <span className="text-sm text-gray-400">
                Last updated: {lastUpdate.toLocaleTimeString()}
              </span>
            )}
            <button
              onClick={fetchData}
              disabled={loading}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors disabled:opacity-50"
            >
              <RefreshIcon />
              <span className={loading ? 'animate-pulse' : ''}>Refresh</span>
            </button>
          </div>
        </div>

        {error && (
          <div className="mb-6 p-4 bg-red-500/10 border border-red-500/20 rounded-lg flex items-center gap-3">
            <AlertIcon />
            <span className="text-red-300">{error}</span>
          </div>
        )}

        {/* Market Overview */}
        {dashboardData?.data && 'marketBias' in dashboardData.data && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className={`p-6 rounded-xl border ${getBiasColor(dashboardData.data.marketBias || '')}`}
            >
              <h3 className="text-lg font-semibold mb-2">Market Bias</h3>
              <p className="text-2xl font-bold capitalize">{dashboardData.data.marketBias || 'Unknown'}</p>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 }}
              className={`p-6 rounded-xl border ${getVolatilityColor(dashboardData.data.volatilityRegime || '')}`}
            >
              <h3 className="text-lg font-semibold mb-2">Volatility Regime</h3>
              <p className="text-2xl font-bold capitalize">{dashboardData.data.volatilityRegime || 'Unknown'}</p>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
              className="p-6 bg-gray-900/50 border border-gray-800/50 rounded-xl"
            >
              <h3 className="text-lg font-semibold mb-2">Market Session</h3>
              <p className="text-2xl font-bold">{dashboardData.data.market_session || 'Unknown'}</p>
            </motion.div>
          </div>
        )}

        {/* Major Indices */}
        {dashboardData?.data && 'symbols' in dashboardData.data && dashboardData.data.symbols && (
          <div className="mb-8">
            <h2 className="text-2xl font-bold mb-4 flex items-center gap-2">
              <EyeIcon />
              Major Indices
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {Object.entries(dashboardData.data.symbols).map(([symbol, data], index) => {
                if (data.price === 0) return null;
                const changeInfo = formatChange(data.change, data.change_pct);
                // Normalize symbol for display (remove ^ prefix)
                const displaySymbol = symbol.replace('^', '');
                const CustomIcon = displaySymbol.toUpperCase() === 'SPY' ? ActivityIcon :
                           displaySymbol.toUpperCase() === 'QQQ' ? ActivityIcon :
                           displaySymbol.toUpperCase() === 'VIX' ? ZapIcon : ActivityIcon;

                return (
                  <motion.div
                    key={symbol}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: index * 0.1 }}
                    className={`bg-gray-900/50 backdrop-blur rounded-xl p-6 border border-gray-800/50 hover:border-gray-700/50 transition-all price-change ${changeInfo.borderClass}`}
                  >
                    <div className="flex items-center justify-between mb-4">
                      <div className="flex items-center gap-3">
                        <CustomIcon />
                        <span className="text-lg font-bold">{displaySymbol.toUpperCase()}</span>
                      </div>
                      <changeInfo.icon />
                    </div>
                    <div className="space-y-2">
                      <div className="text-2xl font-bold">{formatPrice(data.price, displaySymbol)}</div>
                      <div className={`text-sm font-medium price-change ${changeInfo.colorClass}`}>
                        {changeInfo.value}
                      </div>
                      <div className="text-xs text-gray-400">
                        Volume: {formatVolume(data.volume)}
                      </div>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          </div>
        )}

        {/* Macro Economic Indicators */}
        {macroData?.data && (
          <div className="mb-8">
            <h2 className="text-2xl font-bold mb-4 flex items-center gap-2">
              <GlobeIcon />
              Macro Economic Indicators
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {Object.entries(macroData.data).map(([symbol, data], index) => {
                if (typeof data !== 'object' || !('price' in data)) return null;

                const marketData = data as MarketData;
                const changeInfo = formatChange(marketData.change, marketData.change_pct);
                const CustomIcon = getMacroIcon(symbol);

                return (
                  <motion.div
                    key={symbol}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: index * 0.05 }}
                    className={`bg-gray-900/50 backdrop-blur rounded-xl p-4 border border-gray-800/50 hover:border-gray-700/50 transition-all price-change ${changeInfo.borderClass}`}
                  >
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <CustomIcon />
                        <span className="font-medium text-sm">{getMacroLabel(symbol)}</span>
                      </div>
                      <changeInfo.icon />
                    </div>
                    <div className="space-y-1">
                      <div className="text-xl font-bold">{formatPrice(marketData.price, symbol)}</div>
                      <div className={`text-xs font-medium price-change ${changeInfo.colorClass}`}>
                        {changeInfo.value}
                      </div>
                      <div className="text-xs text-gray-500">
                        Vol: {formatVolume(marketData.volume)}
                      </div>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          </div>
        )}

        {/* Economic Context */}
        {macroData?.data && 'market_session' in macroData.data && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="bg-gray-900/50 border border-gray-800/50 rounded-xl p-6"
            >
              <h3 className="text-lg font-semibold mb-2 text-blue-400">Economic Sentiment</h3>
              <p className="text-xl font-bold capitalize">{macroData.data.economic_sentiment || 'Unknown'}</p>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 }}
              className="bg-gray-900/50 border border-gray-800/50 rounded-xl p-6"
            >
              <h3 className="text-lg font-semibold mb-2 text-green-400">Risk Appetite</h3>
              <p className="text-xl font-bold capitalize">{macroData.data.risk_appetite || 'Unknown'}</p>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
              className="bg-gray-900/50 border border-gray-800/50 rounded-xl p-6"
            >
              <h3 className="text-lg font-semibold mb-2 text-purple-400">Data Status</h3>
              <div className="flex items-center gap-2">
                <CheckIcon />
                <span className="text-sm">API Connected</span>
              </div>
            </motion.div>
          </div>
        )}
      </div>
    </div>
  );
}